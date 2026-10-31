"""Recognize explicit explanation/check requests without reading quoted/OCR text as commands."""
import re

BOT_ID = ''
INTENT = re.compile(r'解释|讲讲|分析一下|分析下|分析这|查证|核实|辟谣|真假|真伪|真的吗|真的假的|是真的吗|是不是真的|是否真实|是否为真|是不是(?:真的|假的|谣言)|是否属实|靠不靠谱|什么东西|是什么|这是啥|啥东西|怎么回事|识别一下|认一下')
DECLINE = re.compile(r'闭嘴|没问你|别插[嘴话]|别回|不要回复|不用回复|别解释|不要解释|不用解释|不要查|不用查|别查|不用核实')

def explicit_factcheck_request(message, is_bot=None):
    if is_bot is None:
        is_bot = lambda uid: bool(BOT_ID) and str(uid) == BOT_ID
    if isinstance(message, dict):
        if message.get('is_notify') or message.get('is_command'):
            return False
        info=message.get('message_info') or {}
        user=info.get('user_info') or {}
        if not str(user.get('user_id') or ''):
            return False
        if is_bot(str(user.get('user_id') or '')):
            return False
        group=info.get('group_info')
        parts=message.get('raw_message') or []
        if not isinstance(parts,list):
            return False
    else:
        if message.is_notify or message.is_command:
            return False
        if is_bot(str(message.message_info.user_info.user_id or '')):
            return False
        group=message.message_info.group_info
        parts=message.raw_message.components
    texts=[];ats=[];quoted=False
    for part in parts:
        if isinstance(part,dict):
            kind=part.get('type') or part.get('format_name')
            data=part.get('data')
            if kind=='text':
                texts.append(data if isinstance(data,str) else str((data or {}).get('text','')) if isinstance(data,dict) else str(part.get('text') or ''))
            elif kind=='at':
                ats.append(str(data if isinstance(data,(str,int)) else (data or {}).get('target_user_id') or (data or {}).get('user_id') or part.get('target_user_id') or ''))
            elif kind=='reply':quoted=True
        else:
            kind=part.format_name
            if kind=='text':texts.append(part.text)
            elif kind=='at':ats.append(str(part.target_user_id))
            elif kind=='reply':quoted=True
    text=' '.join(texts).strip()
    if not text or not INTENT.search(text) or DECLINE.search(text):
        return False
    if any(not is_bot(uid) for uid in ats):
        return False
    named=bool(re.match(r'^\s*@?(?:大肥鱼|肥鱼)(?:[\s，,:：]|$)',text))
    return bool(not group or quoted or named or any(is_bot(uid) for uid in ats))
