import asyncio
from contextlib import closing
import hashlib
import io
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from PIL import Image
from image_delivery import ImageDelivery, MAX_ATTEMPTS, transport_image
from vertex_media_core import Ledger, MediaService
from qqbridge_recovery import restart_due, deliver_pending, target_for_session


def png():
    out = io.BytesIO()
    Image.new('RGB', (256, 256), 'blue').save(out, 'PNG')
    return out.getvalue()


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'data').mkdir()
        (self.root / 'config').mkdir()
        self.policy = self.root / 'config/adapter_policy.toml'
        self.policy.write_text('[defaults.group]\ndefault_action="block"\nallow_ids=["759110805"]\n')
        with closing(sqlite3.connect(self.root / 'data/MaiBot.db')) as db:
            db.execute('create table chat_sessions(session_id text,platform text,account_id text,group_id text,user_id text)')
            db.execute("insert into chat_sessions values('g','qq','2701699473','759110805','')")
            db.commit()
        self.clock = [1000000.0]
        self.ledger = Ledger(self.root / 'data/vertex-media', clock=lambda: self.clock[0])
        self.backend = SimpleNamespace(generate=AsyncMock(return_value=(png(), 'image/png')))
        self.sender = AsyncMock(return_value={'sent': False, 'message_id': None})
        self.service = MediaService(self.ledger, self.backend, self.sender)
        self.prepare = lambda path, root: transport_image(path)

    async def failed_job(self):
        result = await self.service.run('image', 'g', 'm', '鲸鱼')
        self.assertFalse(result['success'])
        return self.ledger.get(result['job_id'], 'g')

    async def test_failed_send_restart_then_recovery_no_generation_no_charge(self):
        job = await self.failed_job()
        quota = self.ledger.quota()
        before = hashlib.sha256(self.service.asset_path(job).read_bytes()).hexdigest()
        self.clock[0] += 31
        reopened = Ledger(self.ledger.root, clock=lambda: self.clock[0])
        delivery = ImageDelivery(reopened)
        call = Mock(return_value={'message_id': 123})
        deliver_pending(self.root, reopened, delivery, '2701699473', call, self.prepare)
        self.assertEqual(call.call_args.args[0], 'send_group_msg')
        self.assertEqual(call.call_args.args[1]['group_id'], 759110805)
        self.assertEqual(reopened.get(job['id'], 'g')['state'], 'sent')
        self.assertEqual(self.ledger.quota(), quota)
        self.backend.generate.assert_awaited_once()
        self.assertEqual(hashlib.sha256(self.service.asset_path(job).read_bytes()).hexdigest(), before)
        deliver_pending(self.root, reopened, delivery, '2701699473', call, self.prepare)
        self.assertEqual(call.call_count, 1)
        with reopened.transaction() as db:
            self.assertEqual(db.execute('select receipt from image_deliveries where job=?', (job['id'],)).fetchone()[0], '123')

    async def test_lock_blocks_manual_and_automatic_race(self):
        job = await self.failed_job()
        self.clock[0] += 31
        delivery = ImageDelivery(self.ledger)
        call = Mock(return_value={'message_id': 123})
        with self.service.image_delivery.lock(job['id']) as acquired:
            self.assertTrue(acquired)
            deliver_pending(self.root, self.ledger, delivery, '2701699473', call, self.prepare)
            call.assert_not_called()

    async def test_missing_receipt_not_success_and_bounded_retries(self):
        job = await self.failed_job()
        delivery = self.service.image_delivery
        call = Mock(return_value={})
        for i in range(MAX_ATTEMPTS + 3):
            self.clock[0] += 1801
            deliver_pending(self.root, self.ledger, delivery, '2701699473', call, self.prepare)
        self.assertEqual(call.call_count, MAX_ATTEMPTS - 1)
        self.assertEqual(self.ledger.get(job['id'], 'g')['state'], 'delivery_failed')
        self.backend.generate.assert_awaited_once()
        with self.ledger.transaction() as db:
            row = db.execute('select status,attempts from image_deliveries where job=?', (job['id'],)).fetchone()
            self.assertEqual(tuple(row), ('paused', MAX_ATTEMPTS))

    async def test_removed_group_and_wrong_account_cannot_receive(self):
        await self.failed_job()
        self.clock[0] += 31
        self.assertIsNone(target_for_session(self.root, 'g', 'another-account'))
        self.policy.write_text('[defaults.group]\ndefault_action="block"\nallow_ids=[]\n')
        call = Mock()
        deliver_pending(self.root, self.ledger, self.service.image_delivery, '2701699473', call, self.prepare)
        call.assert_not_called()

    async def test_missing_asset_never_regenerates(self):
        job = await self.failed_job()
        self.service.asset_path(job).unlink()
        self.clock[0] += 31
        call = Mock()
        deliver_pending(self.root, self.ledger, self.service.image_delivery, '2701699473', call, self.prepare)
        call.assert_not_called()
        self.backend.generate.assert_awaited_once()

    async def test_crash_after_image_saved_before_initial_send_is_recovered(self):
        job, _ = self.ledger.reserve('g', 'crash', 'image')
        self.ledger.start_attempt(job['id'])
        self.service.asset_path(job).write_bytes(png())
        # Simulate a process dying before committing the completed asset to the ledger.
        self.clock[0] += 121
        call = Mock(return_value={'message_id': 456})
        deliver_pending(self.root, self.ledger, ImageDelivery(self.ledger), '2701699473', call, self.prepare)
        call.assert_called_once()
        self.backend.generate.assert_not_awaited()

    async def test_confirmed_initial_receipt_is_not_queued_again(self):
        self.sender.return_value = {'sent': True, 'message_id': '789'}
        result = await self.service.run('image', 'g', 'm', '鲸鱼')
        self.assertTrue(result['success'])
        self.assertEqual(self.service.image_delivery.due(), [])


class WatchdogTests(unittest.TestCase):
    def test_offline_threshold_recovery_and_startup_grace(self):
        state = {}
        self.assertFalse(restart_due(state, 1000, False, 950))
        self.assertFalse(restart_due(state, 1200, False, 0))
        self.assertFalse(restart_due(state, 1230, False, 0))
        self.assertTrue(restart_due(state, 1260, False, 0))
        self.assertFalse(restart_due(state, 1261, True, 0))
        self.assertIsNone(state['offline_since'])

    def test_cooldown_and_hourly_cap_survive_healthy_intervals(self):
        state = {'offline_since': 1000, 'restarts': [1100]}
        self.assertFalse(restart_due(state, 1300, False, 0))
        self.assertTrue(restart_due(state, 1400, False, 0))
        state['restarts'] = [1100, 1400, 1700]
        self.assertFalse(restart_due(state, 2300, False, 0))
        self.assertFalse(restart_due(state, 2301, True, 0))
        self.assertEqual(len(state['restarts']), 3)


if __name__ == '__main__':
    unittest.main()
