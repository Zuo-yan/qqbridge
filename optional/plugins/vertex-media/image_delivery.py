"""Persistent image delivery receipts and retry scheduling. Never generates media."""
from contextlib import contextmanager
import os
from pathlib import Path
import re

VERSION = '0.5.0'
RETRY_DELAYS = (30, 60, 120, 300, 600, 1200)
MAX_ATTEMPTS = 2  # Initial image plus one verified retry, then one file fallback.
MAX_AGE = 24 * 60 * 60


def transport_image(path):
    """Keep the original PNG; cache a smaller QQ-compatible transport copy."""
    from PIL import Image
    path = Path(path)
    target = path.with_suffix('.delivery.jpg')
    if target.exists() and target.stat().st_mtime_ns >= path.stat().st_mtime_ns:
        return target
    with Image.open(path) as image:
        image.load()
        image = image.convert('RGB')
        image.thumbnail((1024, 1024))
        staging = target.with_suffix('.jpg.part')
        with staging.open('wb') as output:
            image.save(output, 'JPEG', quality=92, optimize=True)
            output.flush()
            os.fsync(output.fileno())
        os.replace(staging, target)
    return target


class ImageDelivery:
    def __init__(self, ledger):
        self.ledger = ledger
        with ledger.transaction() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS image_deliveries (
                job TEXT PRIMARY KEY, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                first_queued REAL NOT NULL, last_attempt REAL NOT NULL DEFAULT 0,
                next_retry REAL NOT NULL DEFAULT 0, receipt TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT '')''')
            columns = {row[1] for row in db.execute('PRAGMA table_info(image_deliveries)')}
            for name, definition in [('verified_absent', 'INTEGER NOT NULL DEFAULT 0'),
                                     ('last_check', 'REAL NOT NULL DEFAULT 0'),
                                     ('channel', "TEXT NOT NULL DEFAULT 'image'"),
                                     ('file_attempts', 'INTEGER NOT NULL DEFAULT 0')]:
                if name not in columns:
                    db.execute(f'ALTER TABLE image_deliveries ADD COLUMN {name} {definition}')
            db.execute('''CREATE TABLE IF NOT EXISTS media_notices (
                job TEXT NOT NULL, event TEXT NOT NULL, created REAL NOT NULL,
                PRIMARY KEY(job,event))''')

    def claim_notice(self, job_id, event):
        with self.ledger.transaction() as db:
            return db.execute('INSERT OR IGNORE INTO media_notices VALUES(?,?,?)',
                              (job_id, event, self.ledger.clock())).rowcount == 1

    def record(self, job_id):
        with self.ledger.transaction() as db:
            row = db.execute('SELECT * FROM image_deliveries WHERE job=?', (job_id,)).fetchone()
            return dict(row) if row else None

    def verification(self, job_id, outcome):
        # No send attempt is consumed by unavailable or incomplete history.
        now = self.ledger.clock()
        with self.ledger.transaction() as db:
            row = db.execute('SELECT * FROM image_deliveries WHERE job=?', (job_id,)).fetchone()
            if not row or row['status'] in ('sent', 'paused'):
                return False
            previous = row['last_check']
            checks = row['verified_absent'] + 1 if outcome == 'absent' else 0
            db.execute('UPDATE image_deliveries SET verified_absent=?,last_check=?,next_retry=?,error=? WHERE job=?',
                       (checks, now, now + 30, 'history_' + outcome, job_id))
            return (outcome == 'absent' and checks >= 2 and now - previous >= 25
                    and now - row['last_attempt'] >= 60)

    @contextmanager
    def lock(self, job_id):
        import fcntl
        if not re.fullmatch(r'[a-f0-9]{32}', job_id):
            raise ValueError('Invalid image job identifier')
        path = self.ledger.root / (job_id + '.delivery.lock')
        with path.open('a') as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def enqueue(self, job, *, explicit_resend=False):
        now = self.ledger.clock()
        with self.ledger.transaction() as db:
            db.execute("INSERT OR IGNORE INTO image_deliveries(job,status,first_queued) VALUES(?,'pending',?)", (job['id'], now))
            if explicit_resend:
                db.execute("UPDATE image_deliveries SET status='pending',attempts=0,first_queued=?,next_retry=0,receipt='',error='',verified_absent=0,last_check=0,channel='image',file_attempts=0 WHERE job=?", (now, job['id']))

    def begin(self, job_id):
        now = self.ledger.clock()
        with self.ledger.transaction() as db:
            row = db.execute('SELECT * FROM image_deliveries WHERE job=?', (job_id,)).fetchone()
            if not row or row['status'] in ('sent', 'paused'):
                return False
            if row['attempts'] >= MAX_ATTEMPTS or now - row['first_queued'] > MAX_AGE:
                db.execute("UPDATE image_deliveries SET status='paused',error='retry_limit' WHERE job=?", (job_id,))
                return False
            db.execute("UPDATE image_deliveries SET status='sending',attempts=attempts+1,last_attempt=?,next_retry=?,verified_absent=0,last_check=0 WHERE job=?", (now, now + 120, job_id))
            return True

    def finish(self, job_id, sent, *, receipt='', error='delivery_failed'):
        now = self.ledger.clock()
        with self.ledger.transaction() as db:
            row = db.execute('SELECT * FROM image_deliveries WHERE job=?', (job_id,)).fetchone()
            if sent:
                db.execute("UPDATE image_deliveries SET status='sent',receipt=?,next_retry=0,error='' WHERE job=?", (str(receipt or ''), job_id))
                db.execute("UPDATE jobs SET state='sent',updated=?,error='' WHERE id=?", (now, job_id))
            else:
                attempt = row['attempts'] if row else MAX_ATTEMPTS
                paused = False  # Reconcile the second image attempt before file fallback.
                delay = RETRY_DELAYS[min(max(attempt - 1, 0), len(RETRY_DELAYS) - 1)]
                db.execute('UPDATE image_deliveries SET status=?,next_retry=?,error=? WHERE job=?', ('paused' if paused else 'pending', now + delay, error, job_id))
                db.execute("UPDATE jobs SET state='delivery_failed',updated=? WHERE id=?", (now, job_id))

    def begin_file(self, job_id):
        now = self.ledger.clock()
        with self.ledger.transaction() as db:
            row = db.execute("SELECT * FROM image_deliveries WHERE job=?", (job_id,)).fetchone()
            if (not row or row["status"] not in ("pending", "sending")
                    or row["attempts"] < MAX_ATTEMPTS or row["file_attempts"]
                    or now - row["first_queued"] > MAX_AGE):
                return False
            db.execute("UPDATE image_deliveries SET channel='file',file_attempts=1,status='sending',"
                       "last_attempt=?,next_retry=?,verified_absent=0,last_check=0 WHERE job=?",
                       (now, now + 60, job_id))
            return True

    def pause(self, job_id, reason):
        with self.ledger.transaction() as db:
            db.execute("UPDATE image_deliveries SET status='paused',error=? WHERE job=?", (reason, job_id))

    def due(self):
        now = self.ledger.clock()
        with self.ledger.transaction() as db:
            # Recover the narrow crash window after fsync/rename but before asset DB commit.
            for row in db.execute("SELECT id FROM jobs WHERE kind='image' AND asset='' AND state IN ('generating','uncertain') AND updated>?", (now - MAX_AGE,)).fetchall():
                path = self.ledger.root / (row['id'] + '.png')
                if path.is_file() and path.resolve().parent == self.ledger.root:
                    with path.open('rb') as stream:
                        complete_png = stream.read(8) == b'\x89PNG\r\n\x1a\n'
                    if complete_png:
                        db.execute("UPDATE jobs SET state='ready',asset=? WHERE id=?", (path.name, row['id']))
            # Import completed, unsent images left by a crash before enqueue. No uncertain generation.
            db.execute('''INSERT OR IGNORE INTO image_deliveries(job,status,first_queued,next_retry)
                SELECT id,'pending',updated,updated+120 FROM jobs
                WHERE kind='image' AND asset!='' AND state IN ('ready','delivery_failed','uncertain')
                  AND updated>?''', (now - MAX_AGE,))
            db.execute("UPDATE image_deliveries SET status='paused',error='expired' WHERE status IN ('pending','sending') AND first_queued<?", (now - MAX_AGE,))
            rows = db.execute('''SELECT j.* FROM image_deliveries d JOIN jobs j ON j.id=d.job
                WHERE d.status IN ('pending','sending') AND d.next_retry<=? AND d.attempts<=?
                AND j.kind='image' AND j.asset!='' AND j.state IN ('ready','delivery_failed','uncertain')
                ORDER BY d.next_retry,d.first_queued LIMIT 10''', (now, MAX_ATTEMPTS)).fetchall()
            return [dict(row) for row in rows]
