"""Verify a current request before the random gallery can send anything."""
import time
from .media_intent import image_intent


async def current_random_request(plugin, kwargs):
    session = str(kwargs.get('stream_id') or '')
    if not session:
        return None
    now = time.time()
    result = await plugin.ctx.message.get_by_time_in_chat(
        session, str(now - 600), str(now), limit=6, limit_mode='latest',
        filter_mai=True, filter_command=False, include_binary_data=False)
    messages = result.get('messages', []) if isinstance(result, dict) else result if isinstance(result, list) else []
    uid = str(kwargs.get('user_id') or '')
    messages = [m for m in messages if isinstance(m, dict) and m.get('session_id') == session
                and m.get('message_id') and not m.get('is_notify')
                and 0 <= now - float(m.get('timestamp', 0)) <= 600
                and (not uid or str(((m.get('message_info') or {}).get('user_info') or {}).get('user_id', '')) == uid)]
    if not messages:
        return None
    msg = max(messages, key=lambda m: float(m.get('timestamp', 0)))
    text = ' '.join(str(s.get('data') if isinstance(s.get('data'), str) else (s.get('data') or {}).get('text', ''))
                    for s in msg.get('raw_message', []) if isinstance(s, dict) and s.get('type') == 'text')
    if image_intent(text) != 'random':
        return None
    key = (session, str(msg['message_id']))
    seen = getattr(plugin, '_random_requests_seen', {})
    seen = {k: t for k, t in seen.items() if now - t <= 600}
    plugin._random_requests_seen = seen
    if key in seen:
        return None
    seen[key] = now
    return msg
