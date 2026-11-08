"""Small artifact-task policy and file validation, independent of QQ and Codex."""
import ast
import hashlib
import json
from pathlib import Path
import re
import tomllib

VERSION='0.2.1'
MAX_INPUT=64*1024
MAX_OUTPUT=128*1024
ALLOWED={'.html','.htm','.css','.js','.mjs','.json','.py','.txt','.md','.yaml','.yml','.toml','.csv','.svg','.xml','.sql'}
BOT='2701699473'
BOT_ALIASES=r'(?:大肥鱼下士|大肥鱼|肥鱼|2701699473)'

def request_text(text):
    """Copied @ text is not a platform AtComponent, but can still address us."""
    value=text.strip()
    for _ in range(5):
        updated=re.sub(r'^(?:[@＠]'+BOT_ALIASES+r'(?=[\s，,：:！!？?。]|给我|帮我|请|去|写|做|制作|生成|执行|完成|$)|'+BOT_ALIASES+r'(?=[，,\s：:]))[\s，,：:！!？?。]*','',value,count=1)
        if updated==value:break
        value=updated
    return value

def quote_directive(text):
    value=request_text(text)
    if re.fullmatch(r'(?:请|麻烦|帮我|给我|去|来|\s)*(?:完成|执行|做|处理|照着做|照着写)(?:一下|下|一遍)?(?:这个|这条|上面的?|引用的?|刚才的?)?(?:任务|要求|需求|网页|页面|代码|文件)?(?:一下|吧|。|！|!|\s)*',value):return 'execute'
    if re.fullmatch(r'(?:就)?(?:按|照)(?:这个|这条|上面的?|引用的?)(?:来)?(?:做|写|执行)(?:吧|。|！|!|\s)*',value):return 'execute'
    if re.fullmatch(r'(?:去吧|做吧|开始吧|可以|行|好的|好|就这样|按你说的做|同意)[。！!\s]*',value):return 'confirm'
    return None

def plain(message):
    return ' '.join(s['data'] if isinstance(s.get('data'),str) else str((s.get('data') or {}).get('text','')) for s in message.get('raw_message',[]) if s.get('type')=='text').strip()

def identity(message):
    info=message.get('message_info',{})
    return str(info.get('user_info',{}).get('user_id','')),str((info.get('group_info') or {}).get('group_id',''))

def reply_target(message):
    if message.get('reply_to'):return str(message['reply_to'])
    for segment in message.get('raw_message',[]):
        if segment.get('type')!='reply':continue
        data=segment.get('data')
        target=(data.get('target_message_id') or data.get('id')) if isinstance(data,dict) else data
        if target:return str(target)
    return ''

def source_files(message):
    """QQ group uploads are notices, with the original file in trusted metadata."""
    files=[s['data'] for s in message.get('raw_message',[]) if s.get('type')=='file' and isinstance(s.get('data'),dict)]
    info=message.get('message_info') or {}
    notice=(info.get('additional_config') or {}).get('napcat_notice_payload') or {}
    owner,group=identity(message)
    if notice.get('notice_type')=='group_upload' and str(notice.get('group_id'))==group and str(notice.get('user_id'))==owner and isinstance(notice.get('file'),dict):
        file=notice['file'];files.append(dict(file,file_id=file.get('id') or file.get('file_id'),name=file.get('name') or file.get('file')))
    return files

def classify(text):
    """Only actual user task directives; examples and quoted code are not commands."""
    outer=re.sub(r'```[\s\S]*?```','',request_text(text)).strip()
    if re.search(r'^(?:不要|别|不用|不需要|无需)(?:帮我)?(?:写|做|改|生成)',outer):return None
    if re.fullmatch(r'/?(?:任务状态|查看任务|取消任务|重发文件)\s*',outer):return 'status' if '状态' in outer or '查看' in outer else 'cancel' if '取消' in outer else 'resend'
    if re.match(r'^/(?:做网页|写代码|改文件)\s+',outer):
        return 'edit' if outer.startswith('/改文件') else 'web' if outer.startswith('/做网页') else 'code'
    if re.search(r'^(?:如果|假如|示例|举例|怎么|如何|为什么|解释|介绍|是否)',outer):return None
    if not re.search(r'写|做|制作|生成|改|修改|编辑|修复|加上|改成|换成',outer):return None
    if not re.search(r'文件|代码|网页|页面|静态|html|css|javascript|python|脚本|\.py\b|\.json\b|\.html\b|\bpdf\b|PDF',outer,re.I):return None
    if re.search(r'pdf',outer,re.I):return 'edit'
    if re.search(r'(?:改|编辑|修复|加上|换成).{0,15}(?:文件|代码|网页|页面|脚本)|(?:文件|代码|网页|页面|脚本).{0,15}(?:改|编辑|修复|加上|换成)',outer) and not re.search(r'^(?:帮我|给我)?(?:重新)?(?:写|做|生成)',outer):return 'edit'
    return 'web' if re.search(r'网页|页面|html|静态',outer,re.I) else 'code'

def addressed(message,text):
    _,group=identity(message)
    if not group:return False
    if text.lstrip().startswith(('/做网页 ','/写代码 ','/改文件 ','/任务状态','/查看任务','/取消任务','/重发文件')):return True
    for s in message.get('raw_message',[]):
        if s.get('type')=='at' and isinstance(s.get('data'),dict) and str(s['data'].get('target_user_id'))==BOT:return True
    return bool(message.get('is_at') or message.get('is_mentioned') or request_text(text)!=text.strip())

def scope_error(text):
    if len(text)>4000:return '要求太长了，请缩成一个简单网页或单文件修改任务。'
    if re.search(r'(?:编辑|改|修改|生成|制作|做).{0,35}pdf',text,re.I) and not re.search(r'网页|html',text,re.I):
        return '当前任务通道支持静态HTML与文本代码文件，暂不直接读取或编辑PDF。可以明确要求制作HTML文件。'
    if re.search(r'部署上线|部署到|连接(?:真实)?数据库|接入支付|搭建.{0,8}(?:后端|全栈)|完整.{0,8}(?:电商|大型项目|网游)|训练.{0,8}模型|(?:执行|运行).{0,5}(?:上传|这个|这份).{0,5}(?:代码|脚本)|修改.{0,8}(?:服务器|系统文件)|克隆.{0,10}仓库',text):
        return '这超出简单静态网页和单文件修改的范围啦。本鱼这条通道先不接后端、部署或完整项目，请缩小需求。'
    return ''

def safe_name(name):
    if not isinstance(name,str) or name!=Path(name).name or '/' in name or '\\' in name or name.startswith('.') or not re.fullmatch(r'[\w. ()\-]{1,100}',name):
        raise ValueError('文件名无效')
    if Path(name).suffix.lower() not in ALLOWED:raise ValueError('目前仅支持单个文本、代码或HTML文件')
    return name

def input_text(raw,name):
    safe_name(name)
    if len(raw)>MAX_INPUT or b'\x00' in raw:raise ValueError('只支持64KB以内的文本或代码文件')
    for encoding in ('utf-8-sig','gb18030'):
        try:return raw.decode(encoding)
        except UnicodeError:continue
    raise ValueError('无法读取文件文字编码')

def validate_artifact(work,filename):
    safe_name(filename)
    work=Path(work).resolve();target=work/filename
    if target.is_symlink() or not target.is_file() or target.resolve().parent!=work:raise ValueError('交付文件不在任务目录')
    data=target.read_bytes()
    if not 0<len(data)<=MAX_OUTPUT or b'\x00' in data:raise ValueError('成品为空、过大或不是文本文件')
    text=data.decode('utf-8-sig');ext=target.suffix.lower()
    if ext in {'.html','.htm'}:
        if not re.search(r'<html\b',text,re.I) or not re.search(r'</html\s*>',text,re.I):raise ValueError('HTML结构不完整')
        if len(re.findall(r'<script\b',text,re.I))!=len(re.findall(r'</script\s*>',text,re.I)):raise ValueError('脚本标签不完整')
    elif ext=='.py':ast.parse(text)
    elif ext=='.json':json.loads(text)
    elif ext=='.toml':tomllib.loads(text)
    return {'filename':filename,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}

def completion_segments(owner,text):
    if not str(owner).isdigit():raise ValueError('发起人QQ无效')
    return [{'type':'at','data':{'target_user_id':str(owner)}},{'type':'text','data':' '+text}]
