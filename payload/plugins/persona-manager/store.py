"""Transactional persona cards, publication history and per-session selections."""
from contextlib import closing
from pathlib import Path
import sqlite3
import time


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS cards(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL,
                    draft_body TEXT NOT NULL, draft_notes TEXT NOT NULL DEFAULT '', original TEXT NOT NULL DEFAULT '',
                    published_id INTEGER);
                CREATE TABLE IF NOT EXISTS versions(id INTEGER PRIMARY KEY, card_id INTEGER NOT NULL,
                    body TEXT NOT NULL, notes TEXT NOT NULL, created REAL NOT NULL,
                    FOREIGN KEY(card_id) REFERENCES cards(id));
                CREATE TABLE IF NOT EXISTS sessions(session_id TEXT PRIMARY KEY, card_id INTEGER NOT NULL,
                    switched REAL NOT NULL, FOREIGN KEY(card_id) REFERENCES cards(id));
                CREATE TABLE IF NOT EXISTS managers(qq TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS jobs(session_id TEXT PRIMARY KEY, target TEXT NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL);
            ''')
            fields={r[1] for r in db.execute('PRAGMA table_info(sessions)')}
            if 'summary' not in fields:
                db.execute("ALTER TABLE sessions ADD COLUMN summary TEXT NOT NULL DEFAULT ''")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def seed(self, name, body, original):
        with closing(self.connect()) as db, db:
            if db.execute('SELECT 1 FROM cards WHERE name=?', (name,)).fetchone(): return
            cur = db.execute('INSERT INTO cards(name,draft_body,original) VALUES (?,?,?)', (name,body,original))
            version = db.execute('INSERT INTO versions(card_id,body,notes,created) VALUES (?,?,?,?)', (cur.lastrowid,body,'',time.time())).lastrowid
            db.execute('UPDATE cards SET published_id=? WHERE id=?', (version,cur.lastrowid))

    def cards(self):
        with closing(self.connect()) as db:
            return [dict(r) for r in db.execute('SELECT id,name,draft_body,draft_notes,original,published_id FROM cards ORDER BY id')]

    def save_draft(self, name, body, notes='', original=''):
        name, body = name.strip(), body.strip()
        if not name or len(name)>80 or not body or len(body.encode())>45000 or len(notes)>4000 or len(original.encode())>45000:
            raise ValueError('名称或正文为空，或内容超过限制')
        with closing(self.connect()) as db, db:
            db.execute('INSERT INTO cards(name,draft_body,draft_notes,original) VALUES (?,?,?,?) ON CONFLICT(name) DO UPDATE SET draft_body=excluded.draft_body,draft_notes=excluded.draft_notes', (name,body,notes,original))

    def publish(self, name):
        with closing(self.connect()) as db, db:
            row = db.execute('SELECT * FROM cards WHERE name=?',(name,)).fetchone()
            if not row: raise ValueError('人设不存在')
            version=db.execute('INSERT INTO versions(card_id,body,notes,created) VALUES (?,?,?,?)',(row['id'],row['draft_body'],row['draft_notes'],time.time())).lastrowid
            db.execute('UPDATE cards SET published_id=? WHERE id=?',(version,row['id']))
            return version

    def history(self, name):
        with closing(self.connect()) as db:
            return [dict(r) for r in db.execute('SELECT v.id,v.body,v.notes,v.created FROM versions v JOIN cards c ON c.id=v.card_id WHERE c.name=? ORDER BY v.id DESC',(name,))]

    def rollback(self, name, version):
        with closing(self.connect()) as db, db:
            row=db.execute('SELECT v.* FROM versions v JOIN cards c ON c.id=v.card_id WHERE c.name=? AND v.id=?',(name,version)).fetchone()
            if not row: raise ValueError('版本不存在')
            db.execute('UPDATE cards SET published_id=?,draft_body=?,draft_notes=? WHERE id=?',(version,row['body'],row['notes'],row['card_id']))

    def select(self, session, name, summary='', cutoff=None, expected=None, complete_job=False):
        if not session: raise ValueError('缺少会话')
        with closing(self.connect()) as db, db:
            row=db.execute('SELECT id FROM cards WHERE name=? AND published_id IS NOT NULL',(name,)).fetchone()
            if not row: raise ValueError('未找到已发布的人设')
            old=db.execute('SELECT card_id,switched FROM sessions WHERE session_id=?',(session,)).fetchone()
            actual=(old['card_id'],old['switched']) if old else None
            if actual != expected: raise ValueError('会话已被其他操作切换，请重试')
            db.execute('INSERT INTO sessions(session_id,card_id,switched,summary) VALUES (?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET card_id=excluded.card_id,switched=excluded.switched,summary=excluded.summary',(session,row['id'],cutoff or time.time(),summary))
            if complete_job:
                db.execute("UPDATE jobs SET status='done',message=? WHERE session_id=?",('已切换为：'+name+'。',session))

    def selection_token(self, session):
        with closing(self.connect()) as db:
            row=db.execute('SELECT card_id,switched FROM sessions WHERE session_id=?',(session,)).fetchone()
            return (row['card_id'],row['switched']) if row else None

    def current(self, session):
        with closing(self.connect()) as db:
            row=db.execute('SELECT c.name,v.id,v.body,v.notes,s.switched,s.summary FROM cards c JOIN versions v ON v.id=c.published_id LEFT JOIN sessions s ON s.card_id=c.id AND s.session_id=? WHERE c.id=COALESCE((SELECT card_id FROM sessions WHERE session_id=?),(SELECT id FROM cards WHERE name=?))',(session,session,'哈基米')).fetchone()
            if not row: raise ValueError('默认人设未发布')
            return dict(row)

    def managers(self):
        with closing(self.connect()) as db: return [r[0] for r in db.execute('SELECT qq FROM managers ORDER BY qq')]

    def set_managers(self, values):
        values = set(str(x).strip() for x in values if str(x).strip())
        if not values or any(not x.isdigit() or len(x)>20 for x in values): raise ValueError('请保留至少一个有效的 QQ 号码')
        with closing(self.connect()) as db, db:
            db.execute('DELETE FROM managers')
            db.executemany('INSERT INTO managers VALUES (?)',[(v,) for v in values])

    def recover_jobs(self):
        with closing(self.connect()) as db, db:
            db.execute("UPDATE jobs SET status='failed',message='服务重启，切换未完成，请重试' WHERE status='running'")

    def start_job(self, session, target):
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM jobs WHERE session_id=?',(session,)).fetchone()
            if row and row['status']=='running':
                if row['target']!=target: raise ValueError('该会话已有切换任务，请稍候')
                db.commit(); return False
            db.execute("INSERT INTO jobs VALUES (?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET target=excluded.target,status=excluded.status,message=excluded.message",(session,target,'running','正在整理近期对话'))
            db.commit(); return True

    def finish_job(self, session, status, message):
        with closing(self.connect()) as db, db:
            db.execute('UPDATE jobs SET status=?,message=? WHERE session_id=?',(status,message,session))

    def job(self, session):
        with closing(self.connect()) as db:
            row=db.execute('SELECT target,status,message FROM jobs WHERE session_id=?',(session,)).fetchone()
            return dict(row) if row else {'status':'unknown','message':'没有找到切换任务'}
