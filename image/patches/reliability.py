"""Failure handling shared by Planner, Replyer and context compaction.

No provider changes or policy-refusal retries. Imports of MaiBot are lazy so the
failure paths can be tested without launching a second application runtime.
"""
import asyncio
import base64
import gzip
import hashlib
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path

VERSION = '2026.10.28.9'
REASONING_PLACEHOLDER = '我应该根据我上面思考的内容进行反思，重新思考我下一步的行动，我需要分析当前场景，对话，然后直接输出我的想法：'
FAILURE_EMOJI_PATH = Path('/MaiMBot/data/reply-reliability/fox-server-no-response.png')

_POLICY_TEXT_REPLACEMENTS = (
    (re.compile(r'来点(?:涩|色|黄)的', re.IGNORECASE), '来点风格化的'),
    (re.compile(r'色图|涩图', re.IGNORECASE), '图片'),
    (re.compile(r'(?:，|,\s*)?R18\s*=\s*false', re.IGNORECASE), ''),
    (re.compile(r'R18|NSFW|成人向|成人内容', re.IGNORECASE), '受限内容'),
    (re.compile(r'性感', re.IGNORECASE), '风格化'),
)
_POLICY_SENSITIVE_TEXT = re.compile(
    r'名器|色情|涩情|色图|涩图|成人内容|成人向|裸体|裸露|性行为|性交|R18|NSFW'
    r'|朝鲜.{0,16}(?:侵袭|入侵|战争)',
    re.IGNORECASE,
)


def sanitize_policy_sensitive_text(text):
    """Neutralize provider-sensitive wording in internal, non-user injections."""
    normalized = str(text or '')
    for pattern, replacement in _POLICY_TEXT_REPLACEMENTS:
        normalized = pattern.sub(replacement, normalized)
    return normalized


def policy_sensitive_text(text):
    """Recognize explicit terms that should not be retried as a benign message."""
    return bool(_POLICY_SENSITIVE_TEXT.search(str(text or '')))


class ProviderResponseFailure(ValueError):
    def __init__(self, kind):
        self.kind = kind
        super().__init__('provider_response_' + kind)


def response_failure_kind(text):
    """Recognize service errors, never ordinary conversational disagreement."""
    text = (text or '').strip()
    lowered = text.lower()
    if lowered.startswith('the prompt could not be submitted.'):
        return 'policy' if any(w in lowered for w in ('sensitive words', 'prohibited', 'policy', 'safety')) else 'technical'
    if lowered.startswith(('prompt blocked due to safety', 'request blocked by safety', 'blocked by safety settings')):
        return 'policy'
    if lowered.startswith(('service unavailable', 'upstream request failed', 'upstream connect error', 'rate limit exceeded')):
        return 'technical'
    return None


def transient_exception(exc):
    if isinstance(exc, ProviderResponseFailure):
        return exc.kind == 'technical'
    if any(word in str(exc).lower() for word in ('prohibited use policy', 'blocked by safety', 'sensitive words')):
        return False
    status = getattr(exc, 'status_code', None)
    if status is not None:
        return status in (408, 429, 500, 502, 503, 504)
    return isinstance(exc, (TimeoutError, ConnectionError))


def exception_failure_kind(exc):
    if isinstance(exc, ProviderResponseFailure):
        return exc.kind
    if any(word in str(exc).lower() for word in ('prohibited use policy', 'blocked by safety', 'sensitive words')):
        return 'policy'
    return 'technical'


async def retry_transient(operation, *, delay=0.5):
    """Retry the unchanged request once, before any action or delivery occurs."""
    for attempt in range(2):
        try:
            return await operation()
        except Exception as exc:
            if attempt or not transient_exception(exc):
                raise
            await asyncio.sleep(delay)


def is_internal_failure_text(text):
    return bool(response_failure_kind(text)) or (text or '').strip() == REASONING_PLACEHOLDER


def parse_state_json(text):
    """Only tolerate a single Markdown code fence, never fabricate missing data."""
    if kind := response_failure_kind(text):
        raise ProviderResponseFailure(kind)
    raw = (text or '').strip()
    if raw.startswith('```'):
        match = re.fullmatch(r'```(?:json)?\s*\n([\s\S]*?)\n```', raw, re.IGNORECASE)
        if not match:
            raise ValueError('Invalid JSON fence')
        raw = match.group(1)
    parsed = json.loads(raw)
    keys = {'topics', 'background', 'progress', 'pending', 'agreements'}
    if not isinstance(parsed, dict) or set(parsed) != keys:
        raise ValueError('Invalid conversation-state fields')
    if not all(isinstance(v, list) and all(isinstance(x, str) for x in v) for v in parsed.values()):
        raise ValueError('Conversation-state fields must be string arrays')
    return parsed


def archive_compaction(session_id, records, *, summary='', root=None):
    """Durably archive complete source text before replacing working context."""
    if root is None:
        from src.common.paths import get_instance_root
        root = get_instance_root() / 'data' / 'reply-reliability' / 'compaction'
    directory = Path(root) / hashlib.sha256(str(session_id).encode()).hexdigest()[:24]
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / f'{time.time_ns()}-{uuid.uuid4().hex[:8]}.json.gz'
    temp = path.with_suffix('.tmp')
    payload = json.dumps({'version': VERSION, 'session_id': str(session_id), 'source_records': records, 'summary': summary}, ensure_ascii=False).encode()
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as raw:
        with gzip.GzipFile(fileobj=raw, mode='wb') as zipped:
            zipped.write(payload)
        raw.flush()
        os.fsync(raw.fileno())
    os.replace(temp, path)
    return path


_STOP_REQUEST = re.compile(
    r'^(?:请|先|你)?(?:别回(?:复)?|不要回(?:复)?|不用回(?:复)?|安静|闭嘴|别插话|没问你)'
)


def _has_pending_stop_request(runtime):
    """Only a queued stop request should suppress a failure notice.

    Images and follow-up text commonly arrive after an @ mention while the
    Planner is still running. They are part of the same conversational turn and
    must not make the addressed failure silent.
    """
    start = getattr(runtime, '_last_processed_index', 0)
    pending = getattr(runtime, 'message_cache', [])[start:]
    for message in pending:
        text = getattr(message, 'processed_plain_text', '') or ''
        text = re.sub(r'@\S+\s*', '', str(text)).strip()
        if _STOP_REQUEST.match(text):
            return True
    return False


def notice_eligible(runtime, target, *, is_self=None):
    if target is None or target.is_notify or target.session_id != runtime.session_id:
        return False
    if is_self is None:
        from src.chat.utils.utils import is_bot_self
        is_self = is_bot_self
    if is_self(target.platform, target.message_info.user_info.user_id):
        return False
    if str(target.message_id) in getattr(runtime, '_dfy_delivered_reply_targets', set()):
        return False
    if _has_pending_stop_request(runtime):
        return False  # A queued stop request takes precedence.
    text = getattr(target, 'processed_plain_text', '') or ''
    text = re.sub(r'@\S+\s*', '', text).strip()
    if _STOP_REQUEST.match(text):
        return False
    return (not runtime.chat_stream.is_group_session) or bool(target.is_at or target.is_mentioned)


async def notify_failure(
    runtime,
    target,
    kind,
    *,
    sender=None,
    text_sender=None,
    emoji_path=None,
    now=None,
    is_self=None,
):
    """Send the fixed failure sticker to an addressed user; no LLM, no repeats."""
    if not notice_eligible(runtime, target, is_self=is_self):
        return False
    now = time.monotonic() if now is None else now
    gate = getattr(runtime, '_dfy_failure_notice_gate', None)
    if gate is None:
        gate = runtime._dfy_failure_notice_gate = {'attempted': set(), 'last': -1e9}
    message_id = str(target.message_id)
    if message_id in gate['attempted'] or now - gate['last'] < 15:
        return False
    gate['attempted'].add(message_id)  # Reserve before awaiting an ambiguous delivery.
    if len(gate['attempted']) > 256:
        gate['attempted'] = {message_id}
    gate['last'] = now
    texts = {
        'policy': '这条内容触发了 Gemini 的上游内容限制，本喵没法继续展开。聊天记录没有删，其他正常消息可以照常聊。',
        'technical': '这次模型请求失败了，暂时没能回上。稍后再试一下。',
        'empty': '这次没生成有效回复，稍后再叫本喵一下。',
    }
    path = Path(emoji_path or FAILURE_EMOJI_PATH)
    try:
        emoji_base64 = base64.b64encode(path.read_bytes()).decode('ascii')
    except Exception:
        logging.getLogger('reply_reliability').exception('Failure sticker is unavailable; using text fallback')
    else:
        if sender is None:
            from src.services.send_service import emoji_to_stream_with_message
            sender = emoji_to_stream_with_message
        try:
            sent = await sender(
                emoji_base64=emoji_base64,
                stream_id=runtime.session_id,
                storage_message=True,
                set_reply=True,
                reply_message=target,
                sync_to_maisaka_history=False,
            )
        except Exception:
            logging.getLogger('reply_reliability').exception(
                'Failure sticker delivery failed; not retrying an ambiguous send'
            )
            return False
        if sent is not None:
            return True

    if text_sender is None:
        from src.services.send_service import text_to_stream_with_message
        text_sender = text_to_stream_with_message
    try:
        sent = await text_sender(
            text=texts.get(kind, texts['technical']),
            stream_id=runtime.session_id,
            set_reply=True,
            reply_message=target,
            sync_to_maisaka_history=False,
        )
    except Exception:
        logging.getLogger('reply_reliability').exception('Failure notice delivery failed; not retrying an ambiguous send')
        return False
    return sent is not None
