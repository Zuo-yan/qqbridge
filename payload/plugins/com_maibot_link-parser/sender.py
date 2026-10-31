"""MaiBot SDK sender adapter; retains the parsers' segment helper interface."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import unquote, urlsplit
import shutil
from typing import Any

_ctx = None
SHARED_MEDIA_ROOT = Path('/MaiMBot/data/link-parser-sdk')
MessageSegment = dict[str, Any]

@dataclass
class ApiSettings:
    host: str = '127.0.0.1'
    port: int = 3000
    token: str = ''
    bot_uin: str = ''

def bind_sender(ctx):
    global _ctx
    _ctx = ctx

def _stream(message):
    sid = message.get('session_id') or message.get('stream_id')
    if not _ctx or not sid:
        raise ValueError('Parser delivery requires the current host session; refusing to guess a target')
    return str(sid)

def _sent(result):
    return result.get('sent') is True if isinstance(result,dict) else result is True

def text_segment(text):
    return {'type':'text','data':{'text':text}}

def image_segment(path):
    return {'type':'image','data':{'file':str(path)}}

def get_user_id(message):
    return str((message.get('message_info',{}).get('user_info') or {}).get('user_id') or '')

def get_group_id(message):
    return str((message.get('message_info',{}).get('group_info') or {}).get('group_id') or '')

def is_private_message(message):
    return not get_group_id(message)

def _reference(value, folder):
    value=str(value)
    if value.startswith(('https://','http://','base64://')):
        return value
    path=Path(unquote(urlsplit(value).path)) if value.startswith('file://') else Path(value)
    if not path.is_file():
        raise FileNotFoundError('Parser media is missing')
    # The downloader can live in plugins/ or runtime/. Only this data directory
    # is mounted at the same path in both MaiBot and NapCat.
    target=Path(folder)/path.name
    if target.exists():
        import uuid
        target=target.with_name(uuid.uuid4().hex+path.suffix)
    shutil.copyfile(path,target)
    return target.as_uri()

async def send_text(message,text,api):
    return _sent(await _ctx.send.text(text,_stream(message),return_details=True))

async def _media(message,path,kind):
    sid=_stream(message)
    SHARED_MEDIA_ROOT.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(prefix='delivery-',dir=SHARED_MEDIA_ROOT) as temp:
        ref=_reference(path,temp)
        return _sent(await _ctx.send.custom(kind,{'file':ref},sid,return_details=True,timeout_ms=120000))

async def send_image(message,path,api):
    return await _media(message,path,'imageurl')

async def send_video(message,path,api):
    return await _media(message,path,'videourl')

async def send_forward(message,nodes,api):
    sid=_stream(message)
    if not nodes:
        return True
    SHARED_MEDIA_ROOT.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(prefix='forward-',dir=SHARED_MEDIA_ROOT) as temp:
        messages=[]
        for node in nodes:
            segments=[]
            for segment in node:
                kind=segment.get('type');data=segment.get('data') or {}
                if kind=='text':segments.append({'type':'text','content':str(data.get('text',''))})
                elif kind=='image':segments.append({'type':'dict','data':{'type':'imageurl','data':{'file':_reference(data['file'],temp)}}})
                else:raise ValueError('Unsupported parser forward segment: '+str(kind))
            messages.append({'user_id':str(getattr(api,'bot_uin','') or ''),'nickname':'链接解析','segments':segments})
        return _sent(await _ctx.send.forward(messages,sid,return_details=True,timeout_ms=120000))

async def send_group_forward(message,nodes,api):
    return await send_forward(message,nodes,api)
