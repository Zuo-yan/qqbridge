"""Short conversation leases; no model calls and no automatic message sending."""
import re
import time

STOP = re.compile(r"没问你|闭嘴|别插[嘴话]|别回[了复]?|不用[你再]*回[了复]?|不要[再]*回复|别说了|先别说")


class ConversationLease:
    def __init__(self, ttl=300.0, clock=time.monotonic):
        self.ttl, self.clock = ttl, clock
        self.sender = None
        self.until = 0.0
        self.revoked = {}

    def _parts(self, message, is_bot):
        info = message.message_info
        sender = str(info.user_info.user_id or "")
        if (not info.group_info or not sender or message.is_notify
                or message.is_command or is_bot(sender)):
            return sender, False, False
        parts = message.raw_message.components
        text = "".join(getattr(c, 'text', '') for c in parts
                       if c.format_name == 'text')
        ats = [str(c.target_user_id) for c in parts if c.format_name == 'at']
        quotes = [getattr(c, 'target_message_sender_id', None)
                  for c in parts if c.format_name == 'reply']
        # Explicit addressing takes precedence over a quoted bot message.
        redirected = (any(not is_bot(uid) for uid in ats)
                      or (not ats and any(not uid or not is_bot(str(uid)) for uid in quotes)))
        return sender, True, redirected or bool(STOP.search(text))

    def observe(self, message, is_bot):
        sender, valid, cancel = self._parts(message, is_bot)
        if cancel:
            self.revoked[sender] = self.clock()
            if len(self.revoked) > 128:
                self.revoked.pop(next(iter(self.revoked)))
            if self.sender == sender:
                self.sender, self.until = None, 0.0
        return valid and not cancel and self.sender == sender and self.clock() < self.until

    def record_success(self, target, is_bot, *, started_at):
        sender, valid, cancel = self._parts(target, is_bot)
        # A late response must not reopen a conversation the human already ended.
        if not valid or cancel or self.revoked.get(sender, -1) >= started_at:
            return
        self.sender, self.until = sender, self.clock() + self.ttl


"""Recognize explicit explanation/check requests without reading quoted/OCR text as commands."""
import re
import os

BOT_ID = os.environ.get("QQBRIDGE_BOT_QQ", "").strip()
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
