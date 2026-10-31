"""Account-wide appearance presets. No model tools or persona hooks."""
import asyncio
import base64
from contextlib import closing
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

import aiohttp
from PIL import Image, ImageOps

MAX_IMAGE = 2 * 1024 * 1024
COOLDOWN = 300


class QQOfflineError(RuntimeError):
    pass


class OneBot:
    async def call(self, action, params):
        try:
            return await self._call(action,params)
        except (aiohttp.ClientConnectorError,aiohttp.WSServerHandshakeError,TimeoutError) as exc:
            raise QQOfflineError('QQ 当前未登录或连接不可用，请先在 NapCat 完成登录后重试。') from exc

    async def _call(self, action, params):
        # Reuse the private container network and runtime token.
        token = os.environ.get('QQBRIDGE_ONEBOT_TOKEN', '')
        if not token:
            raise QQOfflineError('OneBot 令牌未配置')
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=35)) as client:
            async with client.ws_connect('ws://napcat:3001', headers={
                'Authorization': 'Bearer ' + token
            }) as ws:
                echo = uuid.uuid4().hex
                await ws.send_json({'action': action, 'params': params, 'echo': echo})
                while True:
                    msg = await ws.receive_json()
                    if msg.get('echo') != echo:
                        continue
                    if msg.get('status') != 'ok' or msg.get('retcode', 0) != 0:
                        raise RuntimeError('QQ 拒绝操作（返回码 %s）' % msg.get('retcode', '未知'))
                    return msg.get('data') or {}

    async def identity(self):
        info = await self.call('get_login_info', {})
        expected = os.environ.get('QQBRIDGE_BOT_QQ', '').strip()
        if expected and str(info.get('user_id')) != expected:
            raise RuntimeError('QQ 账号与配置不一致，已停止')
        detail = await self.call('get_stranger_info', {'user_id': int(info['user_id']), 'no_cache': True})
        return {'user_id': str(info['user_id']), 'nickname': detail.get('nickname') or info.get('nickname', '')}

    async def avatar(self, user_id):
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as client:
            async with client.get('https://q1.qlogo.cn/g', params={'b': 'qq', 'nk': user_id, 's': '640'}) as r:
                r.raise_for_status()
                raw = await r.content.read(MAX_IMAGE + 1)
                if len(raw) > MAX_IMAGE:
                    raise ValueError('当前头像超过 2 MB，无法自动备份')
                return raw


class Appearance:
    def __init__(self, root, names, gateway=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.dbpath = self.root / 'appearance.sqlite3'
        first_setup = not self.dbpath.exists()
        self.gateway = gateway or OneBot()
        self.tasks = set()
        self.lock = asyncio.Lock()
        with closing(self.db()) as db, db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS presets(name TEXT PRIMARY KEY,nickname TEXT NOT NULL DEFAULT '',avatar TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1),last_attempt REAL NOT NULL DEFAULT 0,current TEXT NOT NULL DEFAULT '',job TEXT NOT NULL DEFAULT '{}');
                CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY,created REAL NOT NULL,actor TEXT NOT NULL,target TEXT NOT NULL,result TEXT NOT NULL);
                INSERT OR IGNORE INTO state(id) VALUES(1);
            ''')
            if first_setup:
                for name in names:
                    db.execute('INSERT OR IGNORE INTO presets(name) VALUES(?)', (name,))
            state = json.loads(db.execute('SELECT job FROM state WHERE id=1').fetchone()[0])
            if state.get('status') == 'running':
                state.update(status='unknown', message='上次操作被重启打断；请核对 QQ 实际资料后再切换。')
                db.execute("UPDATE state SET current='',job=? WHERE id=1", (json.dumps(state, ensure_ascii=False),))
                db.execute('INSERT INTO history(created,actor,target,result) VALUES(?,?,?,?)',
                           (time.time(), state.get('actor','system'),state.get('target',''),json.dumps(state,ensure_ascii=False)))

    def db(self):
        db = sqlite3.connect(self.dbpath, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def image(self, raw):
        if not raw or len(raw) > MAX_IMAGE:
            raise ValueError('请选择不超过 2 MB 的 PNG 或 JPG 图片')
        try:
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in ('PNG', 'JPEG') or image.width * image.height > 16000000:
                    raise ValueError('图片格式或尺寸不支持')
                image.load()
                image = ImageOps.exif_transpose(image).convert('RGB')
                image = ImageOps.fit(image, (640, 640))
                output = io.BytesIO()
                image.save(output, format='JPEG', quality=92)
        except Exception as exc:
            raise ValueError('无法读取图片，请使用有效的 PNG 或 JPG') from exc
        data = output.getvalue()
        digest = hashlib.sha256(data).hexdigest()
        path = self.root / (digest + '.jpg')
        if not path.exists():
            path.write_bytes(data)
        return digest

    def image_bytes(self, digest):
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('头像文件标识无效')
        return (self.root / (digest + '.jpg')).read_bytes()

    def snapshot(self):
        with closing(self.db()) as db:
            presets = [dict(r) for r in db.execute('SELECT * FROM presets ORDER BY rowid')]
            state = dict(db.execute('SELECT * FROM state WHERE id=1').fetchone())
            logs = [dict(r) for r in db.execute('SELECT * FROM history ORDER BY id DESC LIMIT 20')]
        for p in presets:
            p['ready'] = bool(p['nickname'] and p['avatar'])
            p['preview'] = self.preview(p['avatar']) if p['avatar'] else ''
        return {'presets': presets, 'current': state['current'], 'job': json.loads(state['job']),
                'cooldown_seconds': max(0, int(state['last_attempt'] + COOLDOWN - time.time() + 0.99)),
                'history': logs}

    def preview(self, digest):
        with Image.open(io.BytesIO(self.image_bytes(digest))) as image:
            image.thumbnail((96,96))
            output=io.BytesIO()
            image.save(output,format='JPEG',quality=65)
        return 'data:image/jpeg;base64,'+base64.b64encode(output.getvalue()).decode()

    async def save(self, name, nickname, image_base64=''):
        name, nickname = name.strip(), nickname.strip()
        if not name or len(name) > 80 or not nickname or len(nickname.encode('utf-8')) > 60 or any(ord(c)<32 for c in name+nickname):
            raise ValueError('请填写预设名和昵称；昵称最多 60 字节，不能包含控制字符')
        if name == '默认外观':
            raise ValueError('默认外观是恢复备份，请使用其他预设名')
        raw = None
        if image_base64:
            if len(image_base64) > (MAX_IMAGE*4//3+8):
                raise ValueError('头像超过 2 MB')
            try: raw = base64.b64decode(image_base64, validate=True)
            except Exception as exc: raise ValueError('头像编码无效') from exc
        async with self.lock:
            digest = await asyncio.to_thread(self.image, raw) if raw is not None else ''
            with closing(self.db()) as db, db:
                prior = db.execute('SELECT * FROM presets WHERE name=?', (name,)).fetchone()
                digest = digest or (prior['avatar'] if prior else '')
                if not digest: raise ValueError('请上传头像后再保存')
                if not prior and db.execute('SELECT count(*) FROM presets').fetchone()[0] >= 30: raise ValueError('最多保存 30 套外观')
                db.execute('INSERT INTO presets VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET nickname=excluded.nickname,avatar=excluded.avatar', (name,nickname,digest))
        return {'ok':True}

    async def capture(self):
        with closing(self.db()) as db:
            old = db.execute("SELECT * FROM presets WHERE name='默认外观'").fetchone()
        if old and old['avatar'] and old['nickname']:
            return
        info = await self.gateway.identity()
        raw = await self.gateway.avatar(info['user_id'])
        digest = await asyncio.to_thread(self.image, raw)
        with closing(self.db()) as db, db:
            db.execute('INSERT OR IGNORE INTO presets VALUES(?,?,?)', ('默认外观',info['nickname'],digest))

    async def capture_default(self):
        with closing(self.db()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            prior=json.loads(db.execute('SELECT job FROM state WHERE id=1').fetchone()[0])
            if prior.get('status')=='running': raise ValueError('已有外观任务，请稍后备份')
            job={'status':'running','kind':'capture','target':'默认外观','actor':'webui:authenticated','message':'正在备份当前外观'}
            db.execute('UPDATE state SET job=? WHERE id=1',(json.dumps(job,ensure_ascii=False),))
        async def run():
            try:
                async with self.lock: await self.capture()
                job.update(status='done',message='默认外观已备份，可在列表中选择恢复。')
            except asyncio.CancelledError:
                job.update(status='unknown',message='备份被中断，请重新检查。')
                raise
            except Exception as exc:
                job.update(status='failed',message=str(exc) if isinstance(exc,QQOfflineError) else '备份失败，请检查 QQ 连接和头像下载。')
            finally: self.persist(job,final=True)
        task=asyncio.create_task(run()); self.tasks.add(task);task.add_done_callback(self.tasks.discard)
        return job

    def start(self, name, actor):
        with closing(self.db()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM state WHERE id=1').fetchone()
            if json.loads(row['job']).get('status') == 'running': raise ValueError('已有全局外观切换任务，请稍候')
            if time.time() - row['last_attempt'] < COOLDOWN: raise ValueError('外观切换冷却中，请稍后重试（最多 5 分钟）')
            preset = db.execute('SELECT * FROM presets WHERE name=?', (name,)).fetchone()
            if not preset or not preset['nickname'] or not preset['avatar']: raise ValueError('该外观尚未配置完整，请先在网页保存头像和昵称')
            job = {'id':uuid.uuid4().hex,'status':'running','actor':actor,'target':name,'nickname':'pending','avatar':'pending','message':'正在切换账号全局外观'}
            db.execute('UPDATE state SET last_attempt=?,job=? WHERE id=1', (time.time(),json.dumps(job,ensure_ascii=False)))
        task = asyncio.create_task(self.run(dict(preset), job))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return job

    async def run(self, preset, job):
        try:
            async with self.lock:
                # Capture a recovery preset before the first mutation.
                await self.capture()
                await self.gateway.identity()
                image = base64.b64encode(self.image_bytes(preset['avatar'])).decode()
                for field, action, params in [
                    ('nickname','set_qq_profile',{'nickname':preset['nickname']}),
                    ('avatar','set_qq_avatar',{'file':'base64://'+image})
                ]:
                    job[field] = 'unknown'
                    self.persist(job)
                    try:
                        await self.gateway.call(action, params)
                        job[field] = 'accepted'
                    except Exception:
                        job[field] = 'failed_or_unknown'
                    self.persist(job)
                try:
                    info = await self.gateway.identity()
                    job['observed_nickname'] = info['nickname']
                    job['nickname_verified'] = info['nickname'] == preset['nickname']
                except Exception:
                    job['nickname_verified'] = False
                accepted = all(job[k]=='accepted' for k in ('nickname','avatar'))
                job['status'] = 'done' if accepted and job['nickname_verified'] else 'partial'
                job['message'] = ('QQ 已接受头像修改，昵称已回读核对；头像展示可能受缓存或审核影响。' if job['status']=='done' else '外观未全部确认成功，请核对 QQ 实际资料；可在冷却结束后重试或切换默认外观。')
        except asyncio.CancelledError:
            job.update(status='unknown',message='操作中断，请核对 QQ 实际资料。')
            raise
        except Exception as exc:
            job.update(status='failed',message=str(exc) if isinstance(exc,QQOfflineError) else '读取账号或备份外观失败，已停止；请检查 QQ 连接和头像下载。')
        finally:
            self.persist(job, final=True)

    def persist(self, job, final=False):
        with closing(self.db()) as db, db:
            db.execute('UPDATE state SET job=? WHERE id=1', (json.dumps(job,ensure_ascii=False),))
            if final:
                if job.get('kind')!='capture':
                    db.execute('UPDATE state SET current=? WHERE id=1', (job['target'] if job['status']=='done' else '',))
                db.execute('INSERT INTO history(created,actor,target,result) VALUES(?,?,?,?)', (time.time(),job['actor'],job['target'],json.dumps(job,ensure_ascii=False)))

    async def close(self):
        for task in list(self.tasks): task.cancel()
        await asyncio.gather(*list(self.tasks), return_exceptions=True)
