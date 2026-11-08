import asyncio
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(HERE/'vertex-media'))
sys.path.insert(0,'/MaiMBot')
from task_core import classify,addressed,safe_name,input_text,validate_artifact,completion_segments
from task_broker import Jobs
from vertex_responses_gateway import Gateway,events
from vertex_media_core import Ledger
from completion_notifications import Completions
spec=importlib.util.spec_from_file_location('code_task_plugin',HERE/'plugin.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
CodeTasks=module.CodeTasks

def message(text='给我用html做个奶龙骑自行车的动画',owner='123456',group='759110805',session='group-session',mid='msg1'):
    return dict(platform='qq',session_id=session,message_id=mid,is_at=True,
        message_info={'user_info':{'user_id':owner},'group_info':{'group_id':group} if group else None},
        raw_message=[{'type':'text','data':text}])

def request(**kwargs):
    return dict(session='group-session',owner='123456',group='759110805',message='m1',prompt='做个简单html网页',operation='web',**kwargs)

class Policy(unittest.TestCase):
    def test_classification(self):
        for text,expected in [('给我用html做个奶龙骑自行车的动画','web'),('/做网页 奶龙骑车','web'),
            ('帮我写个网页，不要CDN','web'),('把这个文件的标题改成大肥鱼','edit'),('/改文件 标题改成红色','edit'),
            ('/任务状态','status'),('/取消任务','cancel'),('/重发文件','resend'),
            ('怎么做一个HTML网页？',None),('如果有人要求写代码怎么办？',None),('现在还活着吗',None),
            ('不要写网页了',None),('把图片的头发改成红色',None),('帮我画一张图',None)]:
            with self.subTest(text=text):self.assertEqual(classify(text),expected)
    def test_addressed_group_only(self):
        self.assertTrue(addressed(message(),'任务'))
        self.assertFalse(addressed(message(group=''),'任务'))
        self.assertFalse(addressed(dict(message(),is_at=False),'帮我写网页'))
    def test_filename_traversal_binary_and_size(self):
        for name in ['../x.html','/tmp/a.py','a\\b.py','.hidden.py','bad.exe']:
            with self.assertRaises(ValueError):safe_name(name)
        for data in [b'a\x00b',b'a'*65537]:
            with self.assertRaises(ValueError):input_text(data,'a.txt')
    def test_artifact_and_symlink(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root);(p/'index.html').write_text('<html><body>ok</body></html>')
            self.assertGreater(validate_artifact(p,'index.html')['bytes'],0)
            (p/'bad.html').write_text('<html>incomplete')
            with self.assertRaises(ValueError):validate_artifact(p,'bad.html')
            (p/'alias.html').symlink_to(p/'index.html')
            with self.assertRaises(ValueError):validate_artifact(p,'alias.html')
    def test_real_at_component(self):
        self.assertEqual(completion_segments('123456','完成')[0],{'type':'at','data':{'target_user_id':'123456'}})

class Broker(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.jobs=Jobs(self.temp.name,runner=lambda jid:None)
    def tearDown(self):self.jobs.pool.shutdown(wait=True);self.temp.cleanup()
    def test_dedup_original_owner_scope(self):
        j=self.jobs.prepare(request());self.assertEqual(j['status'],'prepared')
        self.assertEqual(j['id'],self.jobs.prepare(request())['id'])
        with self.assertRaises(ValueError):self.jobs.scoped(j['id'],'other-group',j['owner'])
        with self.assertRaises(ValueError):self.jobs.scoped(j['id'],j['session'],'654321')
        with self.assertRaises(ValueError):self.jobs.prepare(dict(request(),message='m2'))
    def test_queue_bound_and_independent_users(self):
        for i in range(8):self.jobs.prepare(dict(request(),owner=str(100+i),message=str(i)))
        with self.assertRaises(ValueError):self.jobs.prepare(dict(request(),owner='999',message='ninth'))
    def test_ack_failure_releases_reservation(self):
        j=self.jobs.prepare(request());self.jobs.action(j['id'],dict(session=j['session'],owner=j['owner'],action='abandon'))
        self.assertEqual(self.jobs.read(j['id'])['status'],'cancelled')
        self.assertEqual(self.jobs.prepare(dict(request(),message='next'))['status'],'prepared')
    def test_restart_does_not_regenerate(self):
        j=self.jobs.prepare(request());other=Jobs(self.temp.name,runner=lambda _:self.fail('must not run'))
        self.assertEqual(other.read(j['id'])['status'],'interrupted');other.pool.shutdown()
    def test_claim_not_duplicate(self):
        j=self.jobs.prepare(request());scope=dict(session=j['session'],owner=j['owner'],action='claim')
        self.jobs.action(j['id'],scope)
        with self.assertRaises(ValueError):self.jobs.action(j['id'],scope)
    def test_no_private_job(self):
        with self.assertRaises(ValueError):self.jobs.prepare(dict(request(),group=''))

class Plugin(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.p=CodeTasks();self.p._plugin_config_instance=module.Config();self.p.intakes=set()
        self.p._ctx=SimpleNamespace(send=SimpleNamespace(text=AsyncMock(return_value={'sent':True}),hybrid=AsyncMock(return_value={'sent':True}),custom=AsyncMock(return_value={'sent':True})))
    async def test_native_sdk_contract(self):
        from src.plugin_runtime.runner.plugin_loader import PluginLoader
        PluginLoader._validate_sdk_plugin_contract('local.code-tasks',self.p)
        self.assertEqual(len(self.p.get_components()),1)
    async def test_chat_not_blocked_by_worker(self):
        event=asyncio.Event();self.p.accept=AsyncMock(side_effect=lambda *a:None)
        async def slow(*a):await event.wait()
        self.p.accept=slow
        result=await asyncio.wait_for(self.p.receive(message()),.2)
        self.assertEqual(result['action'],'abort')
        result=await asyncio.wait_for(self.p.receive(message('你好')), .2)
        self.assertEqual(result['action'],'continue')
        event.set();await asyncio.gather(*self.p.intakes)
    async def test_ack_before_start(self):
        order=[]
        async def broker(path,payload=None):
            order.append(payload.get('action') or 'prepare')
            return {'job':dict(id='a'*32,status='prepared')}
        async def ack(*a,**k):order.append('ack');return {'sent':True}
        self.p.broker=broker;self.p._ctx.send.text=ack
        await self.p.accept(message(),'做个html','123456','759110805','group-session','web')
        self.assertEqual(order,['prepare','ack','start'])
    async def test_failed_ack_never_starts(self):
        order=[]
        async def broker(path,payload=None):
            order.append(payload.get('action') or 'prepare');return {'job':dict(id='a'*32,status='prepared')}
        self.p.broker=broker;self.p._ctx.send.text=AsyncMock(return_value={'sent':False})
        await self.p.accept(message(),'做个html','123456','759110805','group-session','web')
        self.assertEqual(order,['prepare','abandon'])
    async def test_file_in_original_group_then_at_original_owner(self):
        with tempfile.TemporaryDirectory() as root:
            self.p.config.plugin.jobs_dir=root;jid='b'*32;p=Path(root)/jid/'work';p.mkdir(parents=True)
            raw=b'<html>ok</html>';(p/'index.html').write_bytes(raw)
            j=dict(id=jid,status='ready',session='original-group',owner='123456',group='759110805',filename='index.html',sha256=hashlib.sha256(raw).hexdigest())
            actions=[]
            async def broker(path,payload=None):actions.append(payload['action']);return {}
            self.p.broker=broker
            await self.p.deliver(j)
            self.assertEqual(self.p._ctx.send.custom.call_args.args[2],'original-group')
            at=self.p._ctx.send.hybrid.call_args
            self.assertEqual(at.args[0][0]['data']['target_user_id'],'123456');self.assertEqual(at.args[1],'original-group')
            self.assertEqual(actions,['claim','artifact_sent','notified'])
    async def test_uncertain_file_never_says_delivered(self):
        with tempfile.TemporaryDirectory() as root:
            self.p.config.plugin.jobs_dir=root;jid='c'*32;p=Path(root)/jid/'work';p.mkdir(parents=True)
            raw=b'<html>ok</html>';(p/'index.html').write_bytes(raw)
            self.p._ctx.send.custom=AsyncMock(return_value={'sent':False})
            self.p.broker=AsyncMock(return_value={})
            await self.p.deliver(dict(id=jid,status='ready',session='group',owner='123456',filename='index.html',sha256=hashlib.sha256(raw).hexdigest()))
            self.assertEqual(self.p._ctx.send.hybrid.await_count,0)
            self.assertEqual(self.p.broker.call_args.args[1]['action'],'delivery_failed')

class Media(unittest.IsolatedAsyncioTestCase):
    async def test_original_owner_survives_retries_and_restart(self):
        with tempfile.TemporaryDirectory() as root:
            now=[1000.0];ledger=Ledger(root,clock=lambda:now[0]);n=Completions(ledger)
            m=message('画图');n.remember(m,'image','generate');job,_=ledger.reserve(m['session_id'],m['message_id'],'image')
            self.assertEqual(n.due(),[])
            # A later speaker must never become the stored owner of this job.
            n.remember(dict(m,message_info=message(owner='654321')['message_info']),'image','generate')
            ledger.finish(job['id'],'sent',asset=job['id']+'.png');now[0]+=6
            n=Completions(Ledger(root,clock=lambda:now[0]));sender=AsyncMock(return_value={'sent':True})
            await n.flush(sender);await n.flush(sender)
            self.assertEqual(sender.await_count,1)
            self.assertEqual(sender.call_args.args[0][0]['data']['target_user_id'],'123456')
            self.assertEqual(sender.call_args.args[1],m['session_id'])
    async def test_private_images_never_create_group_mentions(self):
        with tempfile.TemporaryDirectory() as root:
            n=Completions(Ledger(root));n.remember(message(group=''),'image','generate')
            with n.ledger.transaction() as db:self.assertEqual(db.execute('SELECT count(*) FROM media_completions').fetchone()[0],0)

class Protocol(unittest.TestCase):
    def test_forced_model_thinking_and_tool_schema(self):
        with tempfile.TemporaryDirectory() as root:
            g=Gateway({},'secret',Path(root)/'audit');body,mapping,history=g.translate({'input':'test','model':'wrong','tools':[{'type':'namespace','name':'functions','tools':[{'type':'custom','name':'apply_patch'}]}]})
            self.assertEqual(body['generationConfig']['thinkingConfig']['thinkingLevel'],'MEDIUM')
            self.assertEqual(next(iter(mapping.values()))['name'],'apply_patch')
    def test_signatures_and_job_isolation(self):
        with tempfile.TemporaryDirectory() as root:
            g=Gateway({},'secret',Path(root)/'audit');jid='a'*32
            token=jid+'.'+hmac.new(b'secret',jid.encode(),hashlib.sha256).hexdigest();child=g.authorize_job(token)
            child.signatures['call1']={'alias':'tool_alias','part':{'functionCall':{'name':'tool_alias','args':{}},'thoughtSignature':'signature'}}
            body,_,_=child.translate({'input':[{'type':'function_call','call_id':'call1'},{'type':'function_call_output','call_id':'call1','output':'ok'}]})
            self.assertEqual(body['contents'][0]['parts'][0]['thoughtSignature'],'signature')
            with self.assertRaises(ValueError):g.translate({'input':[{'type':'function_call','call_id':'call1'}]})
            for _ in range(15):g.authorize_job(token)
            with self.assertRaises(ValueError):g.authorize_job(token)
            with self.assertRaises(ValueError):g.authorize_job('secret')

if __name__=='__main__':unittest.main(verbosity=2)
