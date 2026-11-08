"""Read-only reconciliation; local IDs and history presence are not receipts."""
import hashlib
from pathlib import Path
import re

HISTORY_LIMIT = 100
HASH = re.compile(r'(?<![a-fA-F0-9])([a-fA-F0-9]{32})(?![a-fA-F0-9])')


def file_name(record):
    return 'image-' + record['job'] + '.png'


def _status(message, all_messages):
    evidence = message.get('qqbridge_delivery')
    if not isinstance(evidence, dict) or evidence.get('version') != 1:
        return 'unknown'
    status = evidence.get('send_status')
    if type(status) is not int or not evidence.get('native_message_id'):
        return 'unknown'
    if status == 0:
        return 'failed'
    seq = str(evidence.get('server_sequence', ''))
    if status != 2 or not seq.isdigit() or int(seq) <= 0 or seq != str(message.get('real_seq', '')):
        return 'unknown'
    for other in all_messages:
        if other is not message and str(other.get('real_seq', '')) == seq:
            other_evidence = other.get('qqbridge_delivery') or {}
            if other_evidence.get('native_message_id') != evidence['native_message_id']:
                return 'unknown'
    return 'confirmed'


def check_history(call, target, bot_id, transport, record, now):
    return _check(call, target, bot_id, transport, record, now, 'image')


def check_file_history(call, target, bot_id, original, record, now):
    outcome, receipt = _check(call, target, bot_id, original, record, now, 'file')
    if outcome == 'found' or target[0] != 'send_group_msg':
        return outcome, receipt
    try:
        entries = call('get_group_root_files', {'group_id': target[1]['group_id'], 'file_count': 100})['files']
        for item in entries:
            if (item.get('file_name') == file_name(record)
                    and str(item.get('uploader')) == str(bot_id)
                    and int(item.get('file_size', -1)) == Path(original).stat().st_size
                    and float(item.get('upload_time', 0)) >= float(record['last_attempt']) - 2
                    and item.get('file_id')):
                return 'found', 'file:' + str(item['file_id'])
    except Exception:
        pass
    return outcome, receipt


def _check(call, target, bot_id, asset, record, now, kind):
    path = Path(asset)
    if not path.is_file() or now - float(record['last_attempt']) < 60:
        return 'unknown', ''
    lower = float(record['first_queued']) - 2
    digest = hashlib.md5(path.read_bytes()).hexdigest().lower()
    size = path.stat().st_size
    is_group = target[0] == 'send_group_msg'
    key = 'group_id' if is_group else 'user_id'
    try:
        data = call('get_group_msg_history' if is_group else 'get_friend_msg_history',
                    {key: target[1][key], 'count': HISTORY_LIMIT, 'reverseOrder': False})
        messages = data.get('messages')
        if not isinstance(messages, list):
            return 'unknown', ''
        times = []
        ambiguous = False
        for message in messages:
            if not isinstance(message, dict):
                return 'unknown', ''
            stamp = float(message['time'])
            times.append(stamp)
            if is_group and str(message.get('group_id', target[1][key])) != str(target[1][key]):
                return 'unknown', ''
            if stamp < lower or stamp > now + 5:
                continue
            sender = str((message.get('sender') or {}).get('user_id', message.get('user_id', '')))
            if sender != str(bot_id):
                continue
            segments = message.get('message')
            if not isinstance(segments, list):
                return 'unknown', ''
            for segment in segments:
                if not isinstance(segment, dict) or segment.get('type') != kind:
                    continue
                content = segment.get('data') or {}
                if not isinstance(content, dict):
                    return 'unknown', ''
                hashes = set()
                for field in ('file', 'url', 'md5'):
                    hashes.update(h.lower() for h in HASH.findall(str(content.get(field, ''))))
                matches = digest in hashes if kind == 'image' else content.get('name') == file_name(record)
                if matches:
                    status = _status(message, messages)
                    if status == 'confirmed' and message.get('message_id'):
                        return 'found', str(message['message_id'])
                    if status != 'failed':
                        ambiguous = True
                elif kind == 'image' and not hashes and str(content.get('file_size', '')) == str(size):
                    ambiguous = True
        covered = len(messages) < HISTORY_LIMIT or (times and min(times) <= lower)
        return ('absent' if covered and not ambiguous else 'unknown'), ''
    except Exception:
        return 'unknown', ''
