"""Convert accidentally drafted HTML documents into durable group file deliveries."""
import base64
from contextlib import closing
import hashlib
from pathlib import Path
import re
import sqlite3
import time
from task_core import safe_name,MAX_OUTPUT

def html_document(text):
    """None for normal conversation/snippets; reject truncated whole documents."""
    fenced=re.search(r'```(?:html|htm)\s*\n([\s\S]*?)```',text,re.I)
    candidate=fenced.group(1).strip() if fenced else text
    match=re.search(r'(?:<!doctype\s+html[^>]*>\s*)?<html\b[\s\S]*?</html\s*>',candidate,re.I)
    if match:document=match.group(0)
    elif re.search(r'<!doctype\s+html|<html\b',candidate,re.I):raise ValueError('网页内容没有完整生成，请重新发起文件任务。')
    elif fenced and len(candidate)>300 and re.search(r'<(?:head|body|style|script)\b',candidate,re.I):
        document='<!doctype html><html lang="zh-CN">'+candidate+'</html>'
    else:return None
    if len(document.encode())>MAX_OUTPUT:raise ValueError('网页超过单文件大小限制，请缩小要求后重试。')
    filename='网页.html'
    match=re.search(r'(?:保存成|保存为|另存为)\s*[`“"\s]*([\w.\-]{1,80}\.html)\b',text,re.I)
    if match:
        try:filename=safe_name(match.group(1))
        except ValueError:pass
    return filename,document


class OutboundGuard:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.db=self.root/'guard.sqlite3'
        with closing(self.connect()) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS deliveries (
                id TEXT PRIMARY KEY, session TEXT NOT NULL, owner TEXT NOT NULL, group_id TEXT NOT NULL,
                filename TEXT NOT NULL, state TEXT NOT NULL, notified INTEGER NOT NULL DEFAULT 0,
                attempts INTEGER NOT NULL DEFAULT 0, updated REAL NOT NULL)''');db.commit()
    def connect(self):
        db=sqlite3.connect(self.db,timeout=5);db.row_factory=sqlite3.Row;return db
    def capture(self,message,owner,group,filename,document):
        raw=document.encode();session=message['session_id']
        jid=hashlib.sha256((session+'\0'+message['message_id']+'\0').encode()+raw).hexdigest()[:32]
        folder=self.root/jid;folder.mkdir(exist_ok=True)
        (folder/filename).write_bytes(raw)
        with closing(self.connect()) as db:
            db.execute("INSERT OR IGNORE INTO deliveries(id,session,owner,group_id,filename,state,updated) VALUES(?,?,?,?,?,'prepared',?)",(jid,session,owner,group,filename,time.time()));db.commit()
        return jid,{'type':'file','data':{'name':filename,'size':len(raw),'url':'base64://'+base64.b64encode(raw).decode()}}
    def finish(self,jid,sent):
        with closing(self.connect()) as db:
            db.execute('UPDATE deliveries SET state=?,updated=? WHERE id=?',('sent' if sent else 'failed',time.time(),jid));db.commit()
    async def flush(self,mention):
        with closing(self.connect()) as db:
            jobs=[dict(j) for j in db.execute("SELECT * FROM deliveries WHERE state='sent' AND notified=0 AND owner!='' AND attempts<3 AND updated<?",(time.time()-2,))]
        for j in jobs:
            with closing(self.connect()) as db:
                db.execute('UPDATE deliveries SET attempts=attempts+1,updated=? WHERE id=?',(time.time(),j['id']));db.commit()
            try:
                result=await mention(j['session'],j['owner'],'做好啦，'+j['filename']+' 已作为文件发在群里了！')
                sent=result.get('sent') is True if isinstance(result,dict) else result is True
            except Exception:sent=False
            if sent:
                with closing(self.connect()) as db:db.execute('UPDATE deliveries SET notified=1 WHERE id=?',(j['id'],));db.commit()
