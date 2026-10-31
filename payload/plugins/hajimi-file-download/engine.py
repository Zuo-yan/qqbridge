"""Bounded file transfer engine. No execution, extraction, or LLM byte payloads."""
import asyncio
import hashlib
import logging
import random
import re
import shutil
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

LIMIT = 1024**3
RESERVE = 2 * LIMIT
START_NOTICES=('好，帮你下。','好的，稍等一下喵。','行，我去下。')
DONE_NOTICES=('下好传上来了喵。','文件已经传好了。','下载上传都完成啦。')

def receipt_state(result):
    if not isinstance(result, dict):
        return 'unknown'
    if result.get('retcode', 0) != 0 or result.get('status') in ('failed','error') or result.get('success') is False:
        return 'failed'
    if result.get('status') == 'ok' and result.get('retcode') == 0:
        return 'success'
    return 'unknown'

class Transfers:
    def __init__(self, root, http, send, upload, free=None, audit=None):
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
        self.http,self.send,self.upload=http,send,upload
        self.free=free or (lambda:shutil.disk_usage(self.root).free)
        self.audit=audit or (lambda detail:logging.getLogger(__name__).info('file_download_result %s',detail))
        self.jobs={}; self.users={}; self.chats={}; self.lock=asyncio.Lock()

    async def start(self, stream, user, group, spec):
        async with self.lock:
            now=time.monotonic()
            if stream in self.jobs: raise ValueError('当前会话已有任务，请等待或由发起人取消。')
            if len(self.jobs)>=3:raise ValueError('三个会话任务均在进行中，请稍后再试。')
            if now-self.users.get(user,-1e9)<60 or (group and now-self.chats.get(group,-1e9)<30):
                raise ValueError('请求过于频繁，请稍后再试。')
            if int(spec.get('size') or 0)>LIMIT: raise ValueError('文件超过1 GiB，请使用来源链接。')
            if self.free() < RESERVE+(len(self.jobs)+1)*LIMIT: raise ValueError('可用磁盘不足，需保留2 GiB并预留并发任务空间。')
            self.users[user]=now; self.chats[group or stream]=now
            task=asyncio.create_task(self.run(stream,user,group,dict(spec)))
            self.jobs[stream]=(user,task,'download')
            task.add_done_callback(lambda finished:self.finished(stream,finished))
            return '任务已受理，插件会报告开始和最终结果；请结束本轮，不重复发起或声称上传成功。'

    def finished(self,stream,task):
        job=self.jobs.get(stream)
        if job and job[1] is task:self.jobs.pop(stream,None)
        if not task.cancelled() and task.exception():
            logging.getLogger(__name__).error('file transfer task failed',exc_info=task.exception())

    async def cancel(self,stream,user):
        job=self.jobs.get(stream)
        if not job or job[0]!=user: return '没有你可取消的任务。'
        if job[2]=='upload': return '上传已经开始，暂时无法确认取消；请等待回执，可能无法撤回。'
        # Let run() enter its try/finally even when cancellation arrives immediately.
        await asyncio.sleep(0)
        if self.jobs.get(stream) and self.jobs[stream][2]=='upload':
            return '上传已经开始，可能无法撤回。'
        job[1].cancel(); return '已请求取消下载。'

    async def run(self,stream,user,group,spec):
        path=self.root/(uuid.uuid4().hex+'.download')
        success=False; uploading=False
        try:
            size=int(spec.get('size') or 0)
            await self.send(random.choice(START_NOTICES),stream)
            guard=Guard(path,self)
            with path.open('wb') as raw:
                guard.raw=raw
                info=await asyncio.wait_for(self.http.fetch(spec['url'],LIMIT,guard),900)
            if not info['size']: raise ValueError('下载结果为空。')
            if size and size!=info['size']: raise ValueError('文件大小与发布信息不符。')
            digest=await asyncio.to_thread(hash_file,path)
            expected=spec.get('sha256','')
            if expected and (not re.fullmatch('[a-fA-F0-9]{64}',expected) or digest!=expected.lower()): raise ValueError('文件校验不符，未上传。')
            with path.open('rb') as f: prefix=f.read(512).lstrip().lower()
            if prefix.startswith((b'<html',b'<!doctype html')): raise ValueError('下载得到网页，并非文件。')
            if spec['name'].lower().endswith(('.apk','.zip','.apks','.xapk')) and not prefix.startswith(b'pk'): raise ValueError('压缩包/APK格式不符。')
            if spec['name'].lower().endswith('.exe') and not prefix.startswith(b'mz'): raise ValueError('EXE格式不符。')
            path.chmod(0o644)
            uploading=True; self.jobs[stream]=(user,asyncio.current_task(),'upload')
            result=await asyncio.wait_for(self.upload(group,user,path,spec['name']),900)
            state=receipt_state(result)
            success=state=='success'
            try:
                self.audit({'state':state,'stream':stream,'name':spec['name'],'bytes':info['size'],'sha256':digest,'publisher_hash_matched':bool(expected),'official_signature_verified':False,'source':urlsplit(spec['source'])._replace(query='',fragment='').geturl()})
            except Exception:
                logging.getLogger(__name__).warning('Could not write file transfer audit record')
            status={'success':random.choice(DONE_NOTICES),'failed':'上传失败了，请稍后再试。','unknown':'还没确认上传是否成功，请检查文件是否收到。'}[state]
            await self.send(status,stream)
        except asyncio.CancelledError:
            await self.send('下载已取消。' if not uploading else '上传被中断，结果不明，请检查是否收到。',stream)
        except Exception as exc:
            await self.send(f"文件任务未完成：{type(exc).__name__}: {str(exc)[:200]}\n来源：{spec['source']}",stream)
        finally:
            job=self.jobs.get(stream)
            if job and job[1] is asyncio.current_task():self.jobs.pop(stream,None)
            if path.exists():
                if success or not uploading: path.unlink(missing_ok=True)
                else:path.touch()  # Retain for one hour from upload completion/failure.

    def clean(self):
        active={j[1] for j in self.jobs.values()}
        if active: return
        for p in self.root.glob('*.download'):
            if p.is_file() and not p.is_symlink() and time.time()-p.stat().st_mtime>3600: p.unlink()

def hash_file(path):
    with path.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

class Guard:
    def __init__(self,path,engine): self.path,self.engine,self.raw=path,engine,None
    def write(self,data):
        if self.engine.free()-len(data)<RESERVE: raise ValueError('磁盘保护：至少预留2 GiB。')
        return self.raw.write(data)
