"""Bounded Codex Responses adapter for one Vertex Flash worker. No filesystem tools."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import hmac
import json
import os
import re
from pathlib import Path
import secrets
import threading
import time
import tomllib
import urllib.request
import urllib.error
import uuid

VERSION = '1.2.0'
MODEL = 'gemini-3.8-flash'
MAX_OUTPUT_TOKENS_CEILING = 32768
DEFAULT_MAX_OUTPUT_TOKENS = 16384


class Gateway:
    def __init__(self, provider, token, audit):
        self.provider, self.token, self.audit = provider, token, Path(audit)
        self.calls, self.saved, self.signatures = {}, {}, {}
        self.lock = threading.Lock()
        self.jobs = {}
        self.started = time.monotonic()
        self.attempts = 0

    def authorize_job(self, token):
        if not re.fullmatch(r'[a-f0-9]{32}\.[a-f0-9]{64}',token):raise ValueError('Unauthorized')
        jid,signature=token.split('.')
        expected=hmac.new(self.token.encode(),jid.encode(),hashlib.sha256).hexdigest()
        if not secrets.compare_digest(signature,expected):raise ValueError('Unauthorized')
        with self.lock:
            for old in list(self.jobs):
                if time.monotonic()-self.jobs[old].started>600:del self.jobs[old]
            if jid not in self.jobs:
                if len(self.jobs)>=16:
                    oldest=next(iter(self.jobs));del self.jobs[oldest]
                self.jobs[jid]=Gateway(self.provider,'',self.audit)
            child=self.jobs[jid]
            if child.attempts>=16 or time.monotonic()-child.started>360:raise ValueError('Task request budget exceeded')
            child.attempts+=1
            return child

    def translate(self, request):
        declarations, mapping = [], {}
        def tool(t, namespace=''):
            kind = t.get('type')
            if kind == 'namespace':
                for nested in t.get('tools', []): tool(nested, t.get('name', ''))
            elif kind in ('function', 'custom'):
                name = t['name']
                alias = 'tool_' + hashlib.sha256((namespace + '.' + name).encode()).hexdigest()[:16]
                mapping[alias] = {'name': name, 'namespace': namespace, 'type': kind}
                schema = t.get('parameters') or {'type': 'object', 'properties': {'input': {'type': 'string'}}, 'required': ['input']}
                declarations.append({'name': alias, 'description': t.get('description', '') + (f'\nOriginal tool name: {namespace}.{name}' if namespace else f'\nOriginal tool name: {name}'), 'parametersJsonSchema': schema})
        for t in request.get('tools', []): tool(t)
        history = request.get('input', [])
        if isinstance(history, str): history = [{'role': 'user', 'content': history}]
        if not isinstance(history,list) or len(history)>300:raise ValueError('History too large')
        parent = request.get('previous_response_id')
        with self.lock:
            saved_snapshot = dict(self.saved)
            signatures_snapshot = dict(self.signatures)
        if parent:
            if parent not in saved_snapshot: raise ValueError('Unknown previous_response_id')
            history = saved_snapshot[parent] + history
        contents, instructions = [], [request.get('instructions') or '']
        def append(role, part):
            if contents and contents[-1]['role'] == role: contents[-1]['parts'].append(part)
            else: contents.append({'role': role, 'parts': [part]})
        for item in history:
            typ = item.get('type', 'message')
            if typ in ('function_call', 'custom_tool_call'):
                saved = signatures_snapshot.get(item.get('call_id'))
                if saved is None: raise ValueError('Unknown tool call')
                append('model', deepcopy(saved['part']))
            elif typ in ('function_call_output', 'custom_tool_call_output'):
                saved = signatures_snapshot.get(item.get('call_id'))
                if saved is None: raise ValueError('Unknown tool output')
                output = item.get('output', '')
                part = {'name': saved['alias'], 'response': {'output': output}}
                if saved['part'].get('functionCall', {}).get('id'): part['id'] = saved['part']['functionCall']['id']
                append('user', {'functionResponse': part})
            elif typ in ('message', None):
                role = item.get('role', 'user')
                content = item.get('content', '')
                text = content if isinstance(content, str) else '\n'.join(p.get('text', '') for p in content if p.get('type') in ('input_text', 'output_text', 'text'))
                if role in ('system', 'developer'): instructions.append(text)
                elif text: append('model' if role == 'assistant' else 'user', {'text': text})
        if not contents: raise ValueError('Empty input')
        # Responses accepts assistant-prefill histories; Vertex requires a user turn.
        # Never fabricate tool results: an outstanding call must be answered by its caller.
        if contents[-1]['role'] == 'model':
            if any('functionCall' in p for p in contents[-1]['parts']):
                raise ValueError('Missing tool output')
            append('user', {'text': 'Continue the pending request from the assistant message above. Use tools if needed.'})
        effort = str((request.get('reasoning') or {}).get('effort') or 'medium').upper()
        if effort not in ('LOW', 'MEDIUM', 'HIGH'):
            raise ValueError('Unsupported reasoning effort')
        max_tokens = request.get('max_output_tokens', DEFAULT_MAX_OUTPUT_TOKENS)
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 1:
            raise ValueError('Invalid max_output_tokens')
        body = {'contents': contents, 'generationConfig': {'temperature': 0.2, 'maxOutputTokens': min(MAX_OUTPUT_TOKENS_CEILING, max_tokens),
                'thinkingConfig': {'thinkingLevel': effort, 'includeThoughts': False}}}
        output_format = ((request.get('text') or {}).get('format') or {})
        if output_format.get('type') in ('json_object', 'json_schema'):
            body['generationConfig']['responseMimeType'] = 'application/json'
            if output_format.get('type') == 'json_schema':
                body['generationConfig']['responseJsonSchema'] = output_format['schema']
        if any(instructions): body['systemInstruction'] = {'parts': [{'text': '\n\n'.join(x for x in instructions if x)}]}
        if declarations:
            body['tools'] = [{'functionDeclarations': declarations}]
            choice = request.get('tool_choice', 'auto')
            mode = {'auto': 'AUTO', 'none': 'NONE', 'required': 'ANY'}.get(choice) if isinstance(choice, str) else None
            config = {'mode': mode or 'ANY'}
            if isinstance(choice, dict) and choice.get('type') == 'function':
                aliases = [alias for alias, original in mapping.items() if original['name'] == choice.get('name')]
                if len(aliases) != 1:
                    raise ValueError('Unknown or ambiguous tool choice')
                config['allowedFunctionNames'] = aliases
            elif mode is None:
                raise ValueError('Unsupported tool choice')
            body['toolConfig'] = {'functionCallingConfig': config}
        return body, mapping, history

    def run(self, request):
        body, mapping, history = self.translate(request)
        base = self.provider['base_url'].rstrip('/')
        url = base + '/models/' + MODEL + ':generateContent'
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
            'Content-Type': 'application/json', 'x-goog-api-key': self.provider['api_key']})
        started = time.monotonic()
        # No environment proxy or implicit retries. Credentials never enter the worker.
        client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with client.open(req, timeout=120) as response: data = json.load(response)
        except urllib.error.HTTPError as exc:
            try: detail = json.loads(exc.read()).get('error', {}).get('message', '')
            except Exception: detail = ''
            print('VERTEX_API_ERROR', exc.code, str(detail).replace(self.provider['api_key'], '[redacted]')[:500], flush=True)
            raise
        candidates = data.get('candidates') or []
        if not candidates: raise ValueError('Vertex returned no candidate')
        candidate = candidates[0]
        finish_reason = candidate.get('finishReason')
        if finish_reason in (None, 'STOP'):
            status = 'completed'
            incomplete_details = None
        elif finish_reason == 'MAX_TOKENS':
            status = 'incomplete'
            incomplete_details = {'reason': 'max_output_tokens'}
        else:
            raise ValueError('Vertex finish reason: ' + str(finish_reason))
        parts = candidate.get('content', {}).get('parts', [])
        output = []
        new_signatures = {}
        text = ''.join(p.get('text', '') for p in parts if not p.get('thought'))
        if text:
            output.append({'type': 'message', 'id': 'msg_' + uuid.uuid4().hex, 'status': status, 'role': 'assistant',
                           'content': [{'type': 'output_text', 'text': text, 'annotations': []}]})
        for part in parts:
            call = part.get('functionCall')
            if not call: continue
            alias = call['name']
            original = mapping[alias]
            call_id = 'call_' + uuid.uuid4().hex
            new_signatures[call_id] = {'alias': alias, 'part': deepcopy(part)}
            if original['type'] == 'custom':
                item = {'type': 'custom_tool_call', 'id': 'ctc_' + uuid.uuid4().hex, 'call_id': call_id,
                        'name': original['name'], 'input': str(call.get('args', {}).get('input', ''))}
            else:
                item = {'type': 'function_call', 'id': 'fc_' + uuid.uuid4().hex, 'call_id': call_id,
                        'name': original['name'], 'arguments': json.dumps(call.get('args', {}), ensure_ascii=False)}
            if original['namespace']: item['namespace'] = original['namespace']
            output.append(item)
        if not output and status == 'incomplete':
            output.append({'type': 'message', 'id': 'msg_' + uuid.uuid4().hex, 'status': 'incomplete', 'role': 'assistant',
                           'content': [{'type': 'output_text', 'text': '', 'annotations': []}]})
        if not output: raise ValueError('No text or tool call')
        usage = data.get('usageMetadata', {})
        thoughts = usage.get('thoughtsTokenCount', 0)
        result = {'id': 'resp_' + uuid.uuid4().hex, 'object': 'response', 'created_at': int(time.time()), 'status': status,
                  'error': None, 'incomplete_details': incomplete_details, 'model': MODEL, 'output': output,
                  'usage': {'input_tokens': usage.get('promptTokenCount', 0), 'output_tokens': usage.get('candidatesTokenCount', 0) + thoughts,
                            'total_tokens': usage.get('totalTokenCount', 0), 'input_tokens_details': {'cached_tokens': usage.get('cachedContentTokenCount', 0)},
                            'output_tokens_details': {'reasoning_tokens': thoughts}}}
        audit_line = json.dumps({
            'time': time.time(),
            'model': MODEL,
            'thinking': body['generationConfig']['thinkingConfig']['thinkingLevel'],
            'max_output_tokens': body['generationConfig']['maxOutputTokens'],
            'finish': finish_reason,
            'status': status,
            'seconds': round(time.monotonic() - started, 3),
            'tool_count': len(mapping),
            'input_items': len(history),
            'outputs': [x['type'] for x in output],
            'usage': result['usage'],
        }) + '\n'
        with self.lock:
            self.signatures.update(new_signatures)
            if len(self.signatures) > 12000:
                for key in list(self.signatures)[:1000]:
                    self.signatures.pop(key, None)
            self.saved[result['id']] = history + output
            if len(self.saved) > 64:
                self.saved.pop(next(iter(self.saved)))
            self.audit.parent.mkdir(parents=True, exist_ok=True)
            with self.audit.open('a', encoding='utf-8') as f:
                f.write(audit_line)
        return result


def events(response):
    initial = dict(response, status='in_progress', output=[], usage=None)
    yield {'type': 'response.created', 'response': initial}
    yield {'type': 'response.in_progress', 'response': initial}
    for i, item in enumerate(response['output']):
        if item['type'] == 'message':
            yield {'type': 'response.output_item.added', 'output_index': i, 'item': dict(item, status='in_progress', content=[])}
            part = item['content'][0]
            yield {'type': 'response.content_part.added', 'output_index': i, 'item_id': item['id'], 'content_index': 0, 'part': dict(part, text='')}
            yield {'type': 'response.output_text.delta', 'output_index': i, 'item_id': item['id'], 'content_index': 0, 'delta': part['text']}
            yield {'type': 'response.output_text.done', 'output_index': i, 'item_id': item['id'], 'content_index': 0, 'text': part['text']}
            yield {'type': 'response.content_part.done', 'output_index': i, 'item_id': item['id'], 'content_index': 0, 'part': part}
        else:
            field = 'input' if item['type'] == 'custom_tool_call' else 'arguments'
            yield {'type': 'response.output_item.added', 'output_index': i, 'item': dict(item, **{field: ''})}
            prefix = 'response.custom_tool_call_input' if field == 'input' else 'response.function_call_arguments'
            yield {'type': prefix + '.delta', 'output_index': i, 'item_id': item['id'], 'delta': item[field]}
            yield {'type': prefix + '.done', 'output_index': i, 'item_id': item['id'], field: item[field]}
        yield {'type': 'response.output_item.done', 'output_index': i, 'item': item}
    terminal_type = 'response.incomplete' if response.get('status') == 'incomplete' else 'response.completed'
    yield {'type': terminal_type, 'response': response}


def handler(gateway):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def reply(self, status, payload):
            raw = json.dumps(payload).encode()
            self.send_response(status); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
        def do_GET(self):
            if self.path == '/health': return self.reply(200, {'ok': True, 'model': MODEL, 'version': VERSION, 'thinking': 'per-request'})
            return self.reply(404, {'error': {'message': 'Unknown endpoint'}})
        def do_POST(self):
            try:job_gateway=gateway.authorize_job(self.headers.get('Authorization','').removeprefix('Bearer '))
            except ValueError:
                return self.reply(401, {'error': {'message': 'Unauthorized'}})
            if self.path not in ('/responses', '/v1/responses'):
                return self.reply(404, {'error': {'message': 'Unsupported endpoint'}})
            try:
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 512 * 1024: raise ValueError('Request size')
                request = json.loads(self.rfile.read(length))
                result = job_gateway.run(request)
                if not request.get('stream'): return self.reply(200, result)
                self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.send_header('Cache-Control', 'no-cache'); self.end_headers()
                for sequence, event in enumerate(events(result)):
                    event['sequence_number'] = sequence
                    self.wfile.write(('event: ' + event['type'] + '\ndata: ' + json.dumps(event, ensure_ascii=False) + '\n\n').encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError): pass
            except Exception as exc:
                # No upstream response bodies, credentials, or raw prompts in logs.
                reason=str(exc) if isinstance(exc,ValueError) and (str(exc).startswith('Vertex finish reason: ') or str(exc) in ('Unknown previous_response_id','Unknown tool call','Unknown tool output','No text or tool call','Vertex returned no candidate','History too large','Request size','Empty input')) else ''
                print('GATEWAY_ERROR', type(exc).__name__, getattr(exc, 'code', ''),reason, flush=True)
                return self.reply(502, {'error': {'message': 'Vertex adapter request failed: ' + type(exc).__name__, 'type': 'server_error'}})
    return Handler


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(); p.add_argument('--config', required=True); p.add_argument('--token-file', required=True); p.add_argument('--bind', default='127.0.0.1'); p.add_argument('--port', type=int, default=18651); p.add_argument('--audit', required=True)
    a = p.parse_args()
    cfg = tomllib.loads(Path(a.config).read_text())
    provider = next(p for p in cfg['api_providers'] if p['name'] == 'VertexGlobal')
    gateway = Gateway(provider, Path(a.token_file).read_text().strip(), a.audit)
    ThreadingHTTPServer((a.bind, a.port), handler(gateway)).serve_forever()
