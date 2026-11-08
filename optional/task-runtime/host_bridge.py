"""Private MaiWork Responses gateway and bounded, networkless Docker execution."""
import argparse
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import threading
import time
import tomllib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = '1.2.0'

NAME = re.compile(r'[A-Za-z0-9_-]{1,64}')
WORKER_IMAGE = 'qqbridge-codex-worker:0.1.0'

def workspace(root, name, cwd=''):
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ValueError('Invalid workspace')
    root = Path(root).resolve(strict=True)
    target = root / name
    if target.is_symlink():
        raise ValueError('Workspace symlink')
    target.mkdir(mode=0o755, exist_ok=True)
    if target.resolve().parent != root:
        raise ValueError('Workspace escape')
    if not isinstance(cwd, str) or cwd.startswith('/') or '..' in Path(cwd).parts:
        raise ValueError('Invalid working directory')
    current = target
    for part in Path(cwd).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('Working directory symlink')
    if not current.is_dir() or not current.resolve().is_relative_to(target.resolve()):
        raise ValueError('Working directory outside workspace')
    return target, '/work' + ('/' + cwd if cwd else '')

def docker_argv(root, name, command, cwd='', seconds=120, container=''):
    if not isinstance(command, str) or not 0 < len(command) <= 65536:
        raise ValueError('Invalid command')
    target, workdir = workspace(root, name, cwd)
    return ['docker', 'run', '--rm', '--name', container,
            '--network=none', '--read-only', '--cap-drop=ALL',
            '--security-opt=no-new-privileges', '--memory=384m', '--memory-swap=384m',
            '--cpus=0.5', '--pids-limit=96', '--ulimit', 'fsize=20971520:20971520',
            '--tmpfs', '/tmp:rw,nosuid,nodev,size=64m',
            '--mount', 'type=bind,src=' + str(target) + ',dst=/work',
            '--workdir', workdir, '--env', 'HOME=/tmp', '--env', 'LANG=C.UTF-8',
            '--entrypoint', '/bin/bash', WORKER_IMAGE, '-lc', command]

class Bridge:
    def __init__(self, root, token, gateway):
        self.root, self.token, self.gateway = Path(root), token, gateway
        self.execution = threading.BoundedSemaphore(1)
        self.models = threading.BoundedSemaphore(3)

    def run(self, request):
        # A caller never chooses an image, mount source, network, or Docker option.
        name = 'qqbridge-mw-' + secrets.token_hex(10)
        seconds = max(1, min(120, int(request.get('timeout_s', 120))))
        argv = docker_argv(self.root, request.get('workspace'), request.get('command'),
                           request.get('cwd', ''), seconds, name)
        if not self.execution.acquire(timeout=5):
            raise ValueError('Execution busy; try later')
        started = time.monotonic()
        proc = None
        try:
            import tempfile
            # Output is bounded by a tmpfs-backed temporary file, never unbounded RAM.
            with tempfile.TemporaryFile(dir='/dev/shm') as out, tempfile.TemporaryFile(dir='/dev/shm') as err:
                proc = subprocess.Popen(argv, stdout=out, stderr=err)
                timed_out = False
                while proc.poll() is None:
                    if time.monotonic() - started > seconds or out.tell() + err.tell() > 2 * 1024 * 1024:
                        timed_out = True
                        subprocess.run(['docker', 'kill', name], capture_output=True, timeout=10)
                        proc.kill()
                        break
                    time.sleep(0.1)
                proc.wait(timeout=10)
                def tail(f):
                    f.seek(0, 2); n=f.tell(); f.seek(max(0,n-20000))
                    return f.read().decode('utf-8', errors='replace')
                return {'exit_code': proc.returncode, 'stdout': tail(out), 'stderr': tail(err),
                        'ms': int((time.monotonic()-started)*1000), 'timed_out': timed_out, 'oom': False}
        finally:
            if proc is not None and proc.poll() is None:
                proc.kill()
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=15)
            self.execution.release()

def handler(bridge):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def reply(self, status, data):
            raw=json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status); self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(raw))); self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass
        def do_GET(self):
            if self.path=='/health': return self.reply(200, {'ok':True,'model':'gemini-3.8-flash','version':VERSION,'thinking':'per-request'})
            return self.reply(404, {'error':{'message':'Unknown endpoint'}})
        def do_POST(self):
            self.connection.settimeout(150)
            if not hmac.compare_digest(self.headers.get('Authorization',''), 'Bearer '+bridge.token):
                return self.reply(401, {'error':{'message':'Unauthorized'}})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=1024*1024: raise ValueError('Request size')
                request=json.loads(self.rfile.read(size))
                if self.path=='/run': return self.reply(200,bridge.run(request))
                if self.path not in ['/responses','/v1/responses']: return self.reply(404,{'error':{'message':'Unknown endpoint'}})
                if not bridge.models.acquire(timeout=5): raise ValueError('Model busy')
                try:
                    # Gateway.run uses fine-grained internal locking around state/audit updates
                    # while keeping network I/O concurrent up to BoundedSemaphore(3).
                    result=bridge.gateway.run(request)
                    if not request.get('stream'):return self.reply(200,result)
                    self.send_response(200);self.send_header('Content-Type','text/event-stream')
                    self.send_header('Cache-Control','no-cache');self.end_headers()
                    for event in bridge.events(result):
                        self.wfile.write(('event: '+event['type']+'\ndata: '+json.dumps(event)+'\n\n').encode());self.wfile.flush()
                    return
                finally:bridge.models.release()
            except (BrokenPipeError,ConnectionResetError):pass
            except Exception as exc:
                # Avoid sending upstream errors containing requests or credentials.
                self.reply(502,{'error':{'message':'MaiWork bridge request failed: '+type(exc).__name__}})
    return Handler

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--token-file',required=True)
    p.add_argument('--config',required=True);p.add_argument('--gateway-source',required=True)
    p.add_argument('--audit',required=True);p.add_argument('--bind',default='172.18.0.1');p.add_argument('--port',type=int,default=18654)
    a=p.parse_args()
    spec=importlib.util.spec_from_file_location('mw_vertex_adapter',a.gateway_source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    cfg=tomllib.loads(Path(a.config).read_text())
    provider=next(x for x in cfg['api_providers'] if x['name']=='VertexGlobal')
    gateway=module.Gateway(provider,'',a.audit)
    # Text-only task model; chat and media gateways remain unchanged.
    Path(a.root).mkdir(parents=True,exist_ok=True)
    bridge=Bridge(a.root,Path(a.token_file).read_text().strip(),gateway)
    bridge.events=module.events
    server=ThreadingHTTPServer((a.bind,a.port),handler(bridge))
    server.serve_forever()

if __name__=='__main__':main()
