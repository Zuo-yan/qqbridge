"""QQ group artifact tasks. Flash MEDIUM Codex jobs never enter the chat Replyer."""
import asyncio,base64,ipaddress,json,re,socket,time,sys
from pathlib import Path
from urllib.parse import urlsplit,urlencode
import aiohttp
from maibot_sdk import MaiBotPlugin,PluginConfigBase,Field,HookHandler
from maibot_sdk.types import HookMode,HookOrder,ErrorPolicy
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0,str(Path(__file__).resolve().parent))
from task_core import classify,plain,identity,addressed,scope_error,input_text,safe_name,completion_segments,source_files,request_text,quote_directive,reply_target
from outbound_guard import OutboundGuard,html_document

class Section(PluginConfigBase):
    enabled:bool=Field(default=True,description='启用原群后台文件任务')
    config_version:str=Field(default='0.2.1',description='插件版本')
    allowed_groups:list[str]=Field(default_factory=lambda:['759110805','764683963'],description='已有开放群；不在私聊投递群任务结果')
    broker_url:str=Field(default='http://172.18.0.1:18652',description='宿主隔离任务服务')
    token_file:str=Field(default='/MaiMBot/plugins/code-tasks/data/broker-token',description='内部访问令牌文件，仅路径')
    jobs_dir:str=Field(default='/MaiMBot/data/code-tasks/jobs',description='持久化任务成品目录')
class Config(PluginConfigBase):
    plugin:Section=Field(default_factory=Section)

def sent(result):return result.get('sent') is True if isinstance(result,dict) else result is True

class PublicResolver(aiohttp.abc.AbstractResolver):
    async def resolve(self,host,port=0,family=socket.AF_INET):
        records=await asyncio.get_running_loop().getaddrinfo(host,port,type=socket.SOCK_STREAM,family=family)
        output=[]
        for fam,_,_,_,address in records:
            if not ipaddress.ip_address(address[0]).is_global:raise ValueError('文件下载地址不可用')
            output.append({'hostname':host,'host':address[0],'port':port,'family':fam,'proto':0,'flags':socket.AI_NUMERICHOST})
        return output
    async def close(self):pass

class CodeTasks(MaiBotPlugin):
    config_model=Config
    async def on_load(self):
        self.intakes=set()
        self.guard=OutboundGuard(Path(self.config.plugin.jobs_dir).parent/'html-delivery-guard')
        self.http=aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20),trust_env=False)
        self.poller=asyncio.create_task(self.poll())
        self.ctx.logger.info('code-tasks 0.2.1 loaded: Codex SDK / Vertex Flash MEDIUM; group-only delivery; full HTML file guard')
    async def on_unload(self):
        for intake in self.intakes:intake.cancel()
        await asyncio.gather(*self.intakes,return_exceptions=True)
        self.poller.cancel();await asyncio.gather(self.poller,return_exceptions=True);await self.http.close()
    async def on_config_update(self,*args,**kwargs):pass
    async def broker(self,path,payload=None):
        token=Path(self.config.plugin.token_file).read_text().strip()
        async with self.http.request('POST' if payload is not None else 'GET',self.config.plugin.broker_url+path,json=payload,headers={'Authorization':'Bearer '+token}) as response:
            data=await response.json()
            if response.status!=200:raise ValueError(data.get('error','后台任务服务暂不可用'))
            return data
    async def mention(self,session,owner,text):
        return await self.ctx.send.hybrid(completion_segments(owner,text),session,return_details=True)
    async def get_message(self,session,mid):
        result=await self.ctx.message.get_by_id(mid,stream_id=session,include_binary_data=False)
        m=result.get('message',result) if isinstance(result,dict) else None
        return m if isinstance(m,dict) and m.get('session_id')==session else None
    async def source(self,current,session,owner):
        _,group=identity(current)
        if not current.get('reply_to') and reply_target(current):current=dict(current,reply_to=reply_target(current))
        candidates=[current]
        if current.get('reply_to'):
            quoted=await self.get_message(session,str(current['reply_to']))
            if quoted:candidates.append(quoted)
        else:
            now=time.time()
            result=await self.ctx.message.get_by_time_in_chat(session,str(now-600),str(now),limit=20,limit_mode='latest',filter_mai=True,filter_command=False,include_binary_data=False)
            recent=result.get('messages',[]) if isinstance(result,dict) else result if isinstance(result,list) else []
            candidates.extend(sorted(recent,key=lambda m:float(m.get('timestamp') or 0),reverse=True))
        for message in candidates:
            uid,_=identity(message)
            if message is not current and not current.get('reply_to') and uid!=owner:continue
            files=source_files(message)
            if not files and plain(message).startswith('[文件]') and message.get('message_id'):
                result=await self.ctx.call_capability('api.call',api_name='adapter.napcat.message.get_msg',version='1',args={'message_id':message['message_id']},timeout_ms=15000)
                for _ in range(3):
                    if isinstance(result,dict) and isinstance(result.get('data'),dict):result=result['data']
                if isinstance(result,dict) and str(result.get('group_id') or group)==group:
                    files=[s['data'] for s in result.get('message',[]) if isinstance(s,dict) and s.get('type')=='file' and isinstance(s.get('data'),dict)]
            if len(files)>1:raise ValueError('一次只能改一个文件，请引用具体的文件。')
            if files:
                data=files[0];name=safe_name(str(data.get('name') or data.get('file_name') or data.get('file') or 'task.txt'))
                try:size=int(data.get('size') or 0)
                except (TypeError,ValueError):size=0
                if size>64*1024:raise ValueError('只支持64KB以内的文本或代码文件。')
                if data.get('base64'):
                    raw=base64.b64decode(data['base64'],validate=True)
                else:
                    url=str(data.get('url') or '')
                    if not url and (data.get('file_id') or data.get('id')):
                        _,source_group=identity(message)
                        params={'group_id':source_group,'file_id':data.get('file_id') or data.get('id')}
                        if data.get('busid') is not None:params['busid']=data['busid']
                        result=await self.ctx.call_capability('api.call',api_name='adapter.napcat.file.get_group_file_url',version='1',args={'params':params},timeout_ms=15000)
                        for _ in range(3):
                            if isinstance(result,dict) and isinstance(result.get('data'),dict):result=result['data']
                        url=str(result.get('url') or '') if isinstance(result,dict) else ''
                    raw=await self.download_file(url)
                return name,input_text(raw,name)
        fenced=re.search(r'```([\w+-]*)\s*\n([\s\S]*?)\n```',plain(current))
        if fenced:
            lang=fenced.group(1).lower();ext={'python':'.py','py':'.py','html':'.html','javascript':'.js','js':'.js','json':'.json','css':'.css','toml':'.toml'}.get(lang,'.txt')
            name='edited'+ext;return name,input_text(fenced.group(2).encode(),name)
        # A user's own latest artifact can be the basis for an explicit follow-up edit.
        latest=(await self.broker('/latest?'+urlencode({'session':session,'owner':owner}))).get('job')
        if latest and latest['status']=='ready' and time.time()-latest.get('finished',0)<600:
            name=safe_name(latest['filename']);path=Path(self.config.plugin.jobs_dir)/latest['id']/'work'/name
            if path.is_symlink():raise ValueError('原文件不可用')
            return name,input_text(path.read_bytes(),name)
        raise ValueError('请先上传或引用一个64KB以内的文本/代码文件，再说要怎么改。')
    async def download_file(self,url):
        for _ in range(3):
            u=urlsplit(url);host=(u.hostname or '').lower()
            if u.scheme not in ('http','https') or u.username or u.password or not any(host==d or host.endswith('.'+d) for d in ('qq.com','qq.com.cn','qpic.cn','myqcloud.com')):raise ValueError('没有取得可读取的QQ文件链接，请重新上传。')
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(resolver=PublicResolver()),timeout=aiohttp.ClientTimeout(total=15),trust_env=False) as http:
                async with http.get(url,allow_redirects=False) as response:
                    if response.status in (301,302,303,307,308):
                        from urllib.parse import urljoin
                        url=urljoin(url,response.headers.get('Location',''));continue
                    if response.status!=200:raise ValueError('QQ文件下载失败，请重新上传。')
                    chunks=[];total=0
                    async for chunk in response.content.iter_chunked(16384):
                        total+=len(chunk)
                        if total>64*1024:raise ValueError('文件超过64KB。')
                        chunks.append(chunk)
                    return b''.join(chunks)
        raise ValueError('QQ文件链接跳转过多。')
    async def control(self,kind,session,owner):
        j=(await self.broker('/latest?'+urlencode({'session':session,'owner':owner}))).get('job')
        if not j:return '你在本群还没有文件任务。'
        if kind in ('cancel','resend'):
            j=(await self.broker('/jobs/'+j['id'],{'session':session,'owner':owner,'action':kind}))['job']
        labels={'prepared':'待启动','queued':'排队中','running':'处理中','ready':'已完成','failed':'未完成','refused':'超出范围','cancelled':'已取消','interrupted':'因重启中断'}
        return '你的任务 '+j['id'][:8]+'：'+labels.get(j['status'],j['status'])+'。'+('成品发送失败，可用 /重发文件 重发已保存的成品。' if j.get('notice_state')=='delivery_failed' else '')
    @HookHandler('chat.receive.after_process',name='code_task_inbox',description='明确的群聊小文件任务独立后台执行，不占用聊天回复',mode=HookMode.BLOCKING,order=HookOrder.EARLY,error_policy=ErrorPolicy.SKIP)
    async def receive(self,message=None,**kwargs):
        m=message or {};original_text=plain(m);owner,group=identity(m);session=str(m.get('session_id') or '')
        if not self.config.plugin.enabled or m.get('platform')!='qq' or group not in self.config.plugin.allowed_groups or not owner.isdigit() or owner=='2701699473' or m.get('is_notify') or not session:return {'action':'continue'}
        explicitly_addressed=addressed(m,original_text)
        if not m.get('reply_to') and reply_target(m):m=dict(m,reply_to=reply_target(m))
        text=request_text(original_text)
        kind=classify(text)
        directive=quote_directive(text) if kind is None and explicitly_addressed else None
        if directive and m.get('reply_to'):
            try:
                seen=set();mid=str(m['reply_to'])
                async with asyncio.timeout(2):
                    for _ in range(3):
                        if not mid or mid in seen:break
                        seen.add(mid);quoted=await self.get_message(session,mid)
                        if not quoted:break
                        quoted_owner=identity(quoted)[0]
                        if directive=='confirm' and quoted_owner!='2701699473':break
                        proposal=request_text(plain(quoted));proposed=classify(proposal)
                        if quoted_owner=='2701699473' and re.search(r'(?:做成|做个|制作|生成|写|做).{0,18}(?:网页|html)',proposal,re.I):proposed='web'
                        if proposed in ('web','code','edit'):
                            kind=proposed
                            text='请执行以下本群引用任务，交付实际文件。'+('网页制作。' if kind=='web' else '')+'\n引用作者：'+quoted_owner+'；本次任务发起人：'+owner+'。\n'+proposal+'\n当前用户明确要求：'+text
                            if kind=='edit' and reply_target(quoted):m=dict(m,reply_to=reply_target(quoted))
                            break
                        if re.match(r'^(?:不要|别|不用|不需要|无需)',proposal):break
                        mid=reply_target(quoted)
            except Exception:pass
        if directive=='execute' and kind is None:
            try:await self.mention(session,owner,'本鱼没找到引用里的具体任务，请直接描述要做的网页，或引用那条写明要求的消息。')
            except Exception:pass
            return {'action':'abort'}
        if kind is None or not explicitly_addressed:return {'action':'continue'}
        self.ctx.logger.info('code_task_inbox routed kind=%s session=%s message=%s',kind,session,str(m.get('message_id') or ''))
        if len(self.intakes)>=8:
            await self.mention(session,owner,'后台受理队列已满，请稍后再试。')
            return {'action':'abort'}
        task=asyncio.create_task(self.accept(m,text,owner,group,session,kind))
        self.intakes.add(task);task.add_done_callback(self.intakes.discard)
        return {'action':'abort'}
    async def accept(self,m,text,owner,group,session,kind):
        j=None
        try:
            if kind in ('status','cancel','resend'):
                await self.ctx.send.text(await self.control(kind,session,owner),session)
                return {'action':'abort'}
            if reason:=scope_error(text):raise ValueError(reason)
            source_name,source_text=('','')
            if kind=='edit':source_name,source_text=await self.source(m,session,owner)
            j=(await self.broker('/prepare',{'session':session,'group':group,'owner':owner,'message':str(m.get('message_id') or ''),'prompt':text,'operation':kind,'source_name':source_name,'source_text':source_text}))['job']
            if j['status']=='prepared':
                acknowledgement=await self.ctx.send.text('好的，本鱼开始做啦，完成后把文件发在这个群里并叫你！',session,return_details=True)
                if not sent(acknowledgement):
                    await self.broker('/jobs/'+j['id'],{'session':session,'owner':owner,'action':'abandon'})
                    raise ValueError('开始提示发送失败，暂未启动生成。')
                await self.broker('/jobs/'+j['id'],{'session':session,'owner':owner,'action':'start'})
            else:await self.ctx.send.text('这条请求已经受理，可用 /任务状态 查看进度。',session)
        except ValueError as exc:await self.mention(session,owner,str(exc)[:300])
        except Exception:await self.mention(session,owner,'后台任务暂时没能受理，请稍后重试。')
        return {'action':'abort'}
    async def poll(self):
        while True:
            try:
                events=(await self.broker('/events')).get('jobs',[])
                for j in events:await self.deliver(j)
            except asyncio.CancelledError:raise
            except Exception:pass
            try:await self.guard.flush(self.mention)
            except asyncio.CancelledError:raise
            except Exception:pass
            await asyncio.sleep(2)
    async def deliver(self,j):
        scope={'session':j['session'],'owner':j['owner']}
        try:await self.broker('/jobs/'+j['id'],dict(scope,action='claim'))
        except Exception:return
        try:
            if j['status']=='ready':
                if not j.get('artifact_sent'):
                    name=safe_name(j['filename']);path=Path(self.config.plugin.jobs_dir)/j['id']/'work'/name
                    if path.is_symlink() or len(path.read_bytes())>128*1024:raise ValueError('成品无效')
                    import hashlib
                    raw=path.read_bytes()
                    if hashlib.sha256(raw).hexdigest()!=j['sha256']:raise ValueError('成品校验失败')
                    result=await self.ctx.send.custom('file',{'name':name,'size':len(raw),'url':'base64://'+base64.b64encode(raw).decode()},j['session'],return_details=True,storage_message=False,processed_plain_text='[文件] '+name)
                    if not sent(result):raise ValueError('文件发送未确认')
                    await self.broker('/jobs/'+j['id'],dict(scope,action='artifact_sent'))
                result=await self.mention(j['session'],j['owner'],'做好啦，'+j['filename']+' 已经发在群里了！')
            else:result=await self.mention(j['session'],j['owner'],j.get('summary') or '这次任务未能完成，请缩小需求后重试。')
            if not sent(result):raise ValueError('完成提醒未确认')
            await self.broker('/jobs/'+j['id'],dict(scope,action='notified'))
        except Exception:
            await self.broker('/jobs/'+j['id'],dict(scope,action='delivery_failed'))

    @HookHandler('send_service.before_send',name='html_file_guard',description='完整HTML统一转换为群文件，禁止聊天刷整页代码',mode=HookMode.BLOCKING,order=HookOrder.LATE,error_policy=ErrorPolicy.SKIP)
    async def guard_html(self,message=None,**kwargs):
        m=message or {};_,group=identity(m);session=str(m.get('session_id') or '')
        if m.get('platform')!='qq' or group not in self.config.plugin.allowed_groups or not session:return {'action':'continue'}
        text=plain(m)
        try:document=html_document(text)
        except ValueError as exc:
            clean=dict(m,raw_message=[{'type':'text','data':str(exc)}],processed_plain_text=str(exc))
            return {'action':'continue','modified_kwargs':dict(kwargs,message=clean)}
        if document is None:return {'action':'continue'}
        try:
            owner='';mid=kwargs.get('reply_message_id') or reply_target(m)
            if mid:
                try:
                    async with asyncio.timeout(1.5):quoted=await self.get_message(session,str(mid))
                    if quoted:owner=identity(quoted)[0]
                except Exception:pass
            if not owner or owner=='2701699473':
                owner=next((str((s.get('data') or {}).get('target_user_id','')) for s in m.get('raw_message',[]) if s.get('type')=='at' and isinstance(s.get('data'),dict)),'')
            if not owner.isdigit() or owner=='2701699473':owner=''
            name,content=document
            jid,segment=self.guard.capture(m,owner,group,name,content)
            info=dict(m.get('message_info') or {});extra=dict(info.get('additional_config') or {});extra['code_task_guard_id']=jid;info['additional_config']=extra
            clean=dict(m,message_info=info,raw_message=[segment],processed_plain_text='[文件] '+name)
            self.ctx.logger.info('html_file_guard: converted full document to group file')
            return {'action':'continue','modified_kwargs':dict(kwargs,message=clean,set_reply=False,reply_message_id='',storage_message=False,typing=False)}
        except Exception:
            clean=dict(m,raw_message=[{'type':'text','data':'网页文件打包失败，请用 /做网页 重新发起任务。'}],processed_plain_text='网页文件打包失败')
            return {'action':'continue','modified_kwargs':dict(kwargs,message=clean)}

    @HookHandler('send_service.after_send',name='html_file_receipt',description='网页文件确认发送后在原群@原请求者',mode=HookMode.BLOCKING,order=HookOrder.LATE,error_policy=ErrorPolicy.SKIP)
    async def guard_receipt(self,message=None,sent=False,**kwargs):
        jid=(((message or {}).get('message_info') or {}).get('additional_config') or {}).get('code_task_guard_id')
        if isinstance(jid,str) and re.fullmatch('[a-f0-9]{32}',jid):self.guard.finish(jid,sent is True)
        return {'action':'continue'}

def create_plugin():return CodeTasks()
