#!/usr/bin/env python3
"""SG-side connection watchdog and saved-image sender, version 0.5.0.

Only retries completed assets. Does not import or call any model client.
"""
from datetime import datetime, timezone
from contextlib import closing
import base64
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import tomllib

ROOT = Path('/root/qqbridge/instances/default')
PLUGIN = ROOT / 'plugins/vertex-media'
STATE = ROOT / 'data/connection-recovery/state.json'


def restart_due(state, now, online, started):
    """Allow restart after 60s offline, 120s startup grace, <=3/hour, >=5min apart."""
    history = [t for t in state.get('restarts', []) if now - t < 3600]
    state['restarts'] = history
    if online:
        state['offline_since'] = None
        return False
    if now - started < 120:
        state['offline_since'] = None
        return False
    if state.get('offline_since') is None:
        state['offline_since'] = now
    if now - state['offline_since'] < 60:
        return False
    return len(history) < 3 and (not history or now - history[-1] >= 300)


def target_for_session(root, session, bot_id):
    with closing(sqlite3.connect(root / 'data/MaiBot.db')) as db:
        db.row_factory = sqlite3.Row
        row = db.execute('SELECT platform,account_id,group_id,user_id FROM chat_sessions WHERE session_id=?', (session,)).fetchone()
    if not row or row['platform'] != 'qq' or (row['account_id'] and str(row['account_id']) != str(bot_id)):
        return None
    group = str(row['group_id'] or '').strip()
    target = group or str(row['user_id'] or '').strip()
    if not target.isdigit() or int(target) <= 0:
        return None
    policy = tomllib.loads((root / 'config/adapter_policy.toml').read_text())
    rule = policy.get('defaults', {}).get('group' if group else 'private', {})
    def contains(values):
        return any(str(v) == target or str(v) == 'qq:' + target for v in values)
    if contains(rule.get('deny_ids', [])):
        return None
    allowed = contains(rule.get('allow_ids', [])) or rule.get('default_action') == 'allow'
    return ('send_group_msg' if group else 'send_private_msg', {'group_id' if group else 'user_id': int(target)}) if allowed else None


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    staging = STATE.with_suffix('.next')
    staging.write_text(json.dumps(state))
    staging.chmod(0o600)
    os.replace(staging, STATE)


def main():
    sys.path.insert(0, str(PLUGIN))
    from vertex_media_core import Ledger
    from image_delivery import ImageDelivery
    spec = importlib.util.spec_from_file_location('qqbridge_onebot', '/root/qqbridge/current/wsl/onebot.py')
    onebot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(onebot)
    env = onebot.load_env(ROOT / '.env')
    def call(action, params=None):
        # Credentials remain in process memory, never command arguments or logs.
        return onebot.call('127.0.0.1', int(env.get('ONEBOT_PORT', '3001')), env['ONEBOT_TOKEN'], action, params or {})
    try:
        state = json.loads(STATE.read_text())
    except (OSError, ValueError):
        state = {'offline_since': None, 'restarts': []}
    now = time.time()
    try:
        info = json.loads(subprocess.check_output(['docker', 'inspect', 'qqbridge-napcat'], timeout=10, text=True))[0]
        started = datetime.fromisoformat(info['State']['StartedAt'].replace('Z', '+00:00')).timestamp()
        status = call('get_status')
        online = status.get('online') is True and status.get('good') is not False
    except Exception:
        online, started = False, 0
    restart = restart_due(state, now, online, started)
    if restart:
        # Persist the throttle before asking Docker, even if Docker fails or this process dies.
        state['restarts'].append(now)
        state['offline_since'] = None
        save_state(state)
        result = subprocess.run(['docker', 'restart', 'qqbridge-napcat'], capture_output=True, timeout=45)
        print('recovery: NapCat restart requested; result=' + str(result.returncode), flush=True)
        return
    save_state(state)
    if not online:
        print('recovery: offline; saved images retained; restart throttle enforced', flush=True)
        return
    ledger = Ledger(ROOT / 'data/vertex-media')
    delivery = ImageDelivery(ledger)
    jobs = delivery.due()
    if not jobs:
        return
    login = call('get_login_info')
    bot_id = str(login.get('user_id', ''))
    if not bot_id.isdigit():
        return
    deliver_pending(ROOT, ledger, delivery, bot_id, call)


def prepare_transport(original, root):
    container_path = str(Path('/MaiMBot') / original.relative_to(root))
    command = ['docker', 'exec', '-e', 'PYTHONPATH=/MaiMBot/plugins/vertex-media', 'qqbridge-maibot',
               '/MaiMBot/.venv/bin/python', '-c',
               'from image_delivery import transport_image; import sys; transport_image(sys.argv[1])', container_path]
    subprocess.run(command, capture_output=True, timeout=20, check=True)
    return original.with_suffix('.delivery.jpg')


def deliver_pending(root, ledger, delivery, bot_id, call, prepare=prepare_transport):
    for job in delivery.due():
        with delivery.lock(job['id']) as acquired:
            if not acquired:
                continue
            # Recheck under the same cross-process lock used by manual/initial delivery.
            if job['id'] not in {row['id'] for row in delivery.due()}:
                continue
            target = target_for_session(root, job['session'], bot_id)
            if target is None:
                delivery.pause(job['id'], 'session_or_policy_blocked')
                continue
            original = (ledger.root / job['asset']).resolve()
            if original.parent != ledger.root or original.name != job['id'] + '.png' or not original.is_file():
                delivery.pause(job['id'], 'asset_missing_or_invalid')
                continue
            record = delivery.record(job['id'])
            if record and record['attempts']:
                from delivery_history import check_history, check_file_history
                checker = check_file_history if record.get('channel') == 'file' else check_history
                asset = original if record.get('channel') == 'file' else original.with_suffix('.delivery.jpg')
                outcome, receipt = checker(call, target, bot_id, asset, record, ledger.clock())
                if outcome == 'found':
                    delivery.finish(job['id'], True, receipt=receipt)
                    print('recovery: existing image confirmed in history; job=' + job['id'], flush=True)
                    continue
                if not delivery.verification(job['id'], outcome):
                    continue
            if record and record.get('channel') == 'file':
                delivery.pause(job['id'], 'file_delivery_failed')
                continue
            if record and record['attempts'] >= 2:
                if not delivery.begin_file(job['id']):
                    continue
                try:
                    from delivery_history import file_name
                    action, params = target
                    params = dict(params)
                    params.update(file='base64://' + base64.b64encode(original.read_bytes()).decode('ascii'),
                                  name=file_name(record))
                    result = call('upload_group_file' if action == 'send_group_msg' else 'upload_private_file', params)
                    receipt = result.get('file_id') if isinstance(result, dict) else None
                    delivery.finish(job['id'], bool(receipt), receipt='file:' + str(receipt) if receipt else '',
                                    error='file_receipt_unknown')
                    print('recovery: original-file fallback attempted; job=' + job['id'], flush=True)
                except Exception:
                    delivery.finish(job['id'], False, error='file_receipt_unknown')
                break
            if not delivery.begin(job['id']):
                continue
            try:
                transport = prepare(original, root)
                data = transport.read_bytes()
                if not data.startswith(b'\xff\xd8') or len(data) > 10 * 1024 * 1024:
                    raise ValueError('Invalid transport image')
                action, params = target
                params['message'] = [{'type': 'image', 'data': {'file': 'base64://' + base64.b64encode(data).decode('ascii')}}]
                result = call(action, params)
                receipt = result.get('message_id') if isinstance(result, dict) else None
                if not receipt or str(receipt) == '0':
                    raise ValueError('Missing delivery receipt')
                delivery.finish(job['id'], True, receipt=receipt)
                print('recovery: saved image sent; job=' + job['id'] + '; receipt=' + str(receipt), flush=True)
            except Exception:
                # Never log external exceptions, image bytes, URLs, or credentials.
                delivery.finish(job['id'], False, error='transport_failed')
                print('recovery: saved image retained for bounded retry; job=' + job['id'], flush=True)
            break  # At most one image per timer tick, never replay a backlog as a burst.


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('recovery: check failed; type=' + type(error).__name__, flush=True)
        raise SystemExit(1)
