"""Persistent bounded jobs; trusted QQ plugin is the only submitter. No chat model routing."""
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import hashlib,json,os,re,secrets,subprocess,threading,time
from pathlib import Path
from task_core import MAX_INPUT,scope_error,safe_name

EXPERIMENT=Path('/root/qqbridge/experiments/codex-flash-20261106')

class Jobs:
    def __init__(self,root,runner=None):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.pool=ThreadPoolExecutor(max_workers=1)
        self.runner=runner or self.execute;self.processes={}
        for path in self.root.glob('*/job.json'):
            record=json.loads(path.read_text())
            if record['status'] in ('prepared','queued','running'):
                record.update(status='interrupted',summary='任务因服务重启中断，未自动重新生成。')
                self.save(record)
            elif record['notice_state']=='claimed':
                record['notice_state']='delivery_failed';self.save(record)
    def read(self,jid):
        if not re.fullmatch('[a-f0-9]{32}',jid):raise ValueError('任务编号无效')
        return json.loads((self.root/jid/'job.json').read_text())
    def save(self,j):
        folder=self.root/j['id'];folder.mkdir(exist_ok=True)
        tmp=folder/'job.tmp';tmp.write_text(json.dumps(j,ensure_ascii=False,indent=2));os.replace(tmp,folder/'job.json')
    def all(self):return [json.loads(p.read_text()) for p in self.root.glob('*/job.json')]
    def scoped(self,jid,session,owner):
        j=self.read(jid)
        if j['session']!=session or j['owner']!=owner:raise ValueError('任务不属于当前发起人或群聊')
        return j
    def public(self,j):return {k:v for k,v in j.items() if k not in ('prompt','source_text')}
    def prepare(self,r):
        for key in ('session','owner','group','message','prompt','operation'):
            if not isinstance(r.get(key),str) or not r[key]:raise ValueError('缺少任务请求字段')
        if not r['owner'].isdigit() or not r['group'].isdigit():raise ValueError('仅支持原群任务交付')
        if r['operation'] not in ('web','code','edit'):raise ValueError('任务类型无效')
        if reason:=scope_error(r['prompt']):raise ValueError(reason)
        if len(r.get('source_text','').encode())>MAX_INPUT:raise ValueError('文件超过64KB')
        if '\x00' in r.get('source_text',''):raise ValueError('文件不能包含二进制数据')
        if r.get('source_name'):safe_name(r['source_name'])
        if r['operation']=='edit' and not r.get('source_name'):raise ValueError('请上传或引用要修改的文本文件')
        jid=hashlib.sha256((r['session']+'\0'+r['message']).encode()).hexdigest()[:32]
        with self.lock:
            if (self.root/jid/'job.json').exists():return self.public(self.read(jid))
            active=[j for j in self.all() if j['status'] in ('prepared','queued','running')]
            if any(j['owner']==r['owner'] and j['session']==r['session'] for j in active):raise ValueError('你在本群已有一个任务处理中，可先发 /任务状态 查看。')
            if len(active)>=8:raise ValueError('后台任务队列已满，请稍后再试。')
            j=dict(r,id=jid,status='prepared',notice_state='pending',artifact_sent=False,created=time.time(),model='gemini-3.8-flash',thinking='MEDIUM')
            self.save(j)
            (self.root/jid/'request.json').write_text(json.dumps(j,ensure_ascii=False,indent=2))
            return self.public(j)
    def start(self,jid):
        with self.lock:
            j=self.read(jid)
            if j['status']=='prepared':
                j['status']='queued';self.save(j);self.pool.submit(self.runner,jid)
            return self.public(j)
    def execute(self,jid):
        with self.lock:
            j=self.read(jid)
            if j['status']!='queued':return
            j['status']='running';self.save(j)
        folder=self.root/jid
        with (folder/'runner.log').open('wb') as log:
            with self.lock:
                if self.read(jid)['status']=='cancelled':return
                process=subprocess.Popen([str(EXPERIMENT/'.venv-sdk/bin/python'),str(EXPERIMENT/'run_task.py'),str(folder)],stdout=log,stderr=log)
                self.processes[jid]=process
            try:process.wait(timeout=330)
            except subprocess.TimeoutExpired:
                process.kill();process.wait(timeout=10);subprocess.run(['docker','rm','-f','qqbridge-code-'+jid],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
            finally:self.processes.pop(jid,None)
        with self.lock:
            j=self.read(jid)
            if j['status']=='cancelled':return
            result_path=folder/'result.json'
            result=json.loads(result_path.read_text()) if result_path.exists() else {'status':'failed','summary':'后台任务超时或被中断，没有可交付的成品。'}
            j.update(result,finished=time.time());self.save(j)
    def action(self,jid,r):
        with self.lock:
            j=self.scoped(jid,r['session'],r['owner']);action=r['action']
            if action=='start':return self.start(jid)
            if action=='claim':
                if j['notice_state']!='pending':raise ValueError('通知已被领取')
                j['notice_state']='claimed'
            elif action=='artifact_sent':j['artifact_sent']=True
            elif action=='notified':j['notice_state']='sent'
            elif action=='delivery_failed':j['notice_state']='delivery_failed'
            elif action=='resend':
                if j['status']!='ready':raise ValueError('该任务没有已保存成品')
                j.update(notice_state='pending',artifact_sent=False)
            elif action=='abandon':
                if j['status']=='prepared':j.update(status='cancelled',notice_state='sent',summary='开始提示未送达，未启动生成。')
            elif action=='cancel':
                if j['status'] in ('prepared','queued','running'):
                    j.update(status='cancelled',notice_state='pending',summary='任务已取消。')
                    if p:=self.processes.get(jid):p.terminate()
                    subprocess.run(['docker','rm','-f','qqbridge-code-'+jid],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
            else:raise ValueError('无效任务操作')
            self.save(j);return self.public(j)

def handler(jobs,token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,obj):
            data=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def auth(self):return secrets.compare_digest(self.headers.get('Authorization',''),'Bearer '+token)
        def do_GET(self):
            if not self.auth():return self.reply(401,{'error':'unauthorized'})
            try:
                from urllib.parse import urlsplit,parse_qs
                url=urlsplit(self.path);q={k:v[0] for k,v in parse_qs(url.query).items()}
                with jobs.lock:
                    if url.path=='/health':return self.reply(200,{'ok':True,'model':'gemini-3.8-flash','thinking':'MEDIUM'})
                    if url.path=='/events':return self.reply(200,{'jobs':[jobs.public(j) for j in jobs.all() if j['status'] in ('ready','failed','refused','interrupted','cancelled') and j['notice_state']=='pending']})
                    if url.path=='/latest':
                        found=[j for j in jobs.all() if j['session']==q.get('session') and j['owner']==q.get('owner')]
                        return self.reply(200,{'job':jobs.public(max(found,key=lambda j:j['created'])) if found else None})
                    if url.path.startswith('/jobs/'):return self.reply(200,{'job':jobs.public(jobs.scoped(url.path.split('/')[-1],q['session'],q['owner']))})
                return self.reply(404,{'error':'not found'})
            except Exception:return self.reply(400,{'error':'任务查询失败'})
        def do_POST(self):
            if not self.auth():return self.reply(401,{'error':'unauthorized'})
            try:
                length=int(self.headers.get('Content-Length',0))
                if not 0<length<=256*1024:raise ValueError('请求过大')
                r=json.loads(self.rfile.read(length))
                if self.path=='/prepare':j=jobs.prepare(r)
                elif self.path.startswith('/jobs/'):j=jobs.action(self.path.split('/')[-1],r)
                else:return self.reply(404,{'error':'not found'})
                return self.reply(200,{'job':j})
            except ValueError as exc:return self.reply(400,{'error':str(exc)[:300]})
            except Exception:return self.reply(500,{'error':'后台任务服务内部错误'})
    return Handler

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--bind',required=True);p.add_argument('--token-file',required=True);p.add_argument('--port',type=int,default=18652);a=p.parse_args()
    ThreadingHTTPServer((a.bind,a.port),handler(Jobs(a.root),Path(a.token_file).read_text().strip())).serve_forever()
