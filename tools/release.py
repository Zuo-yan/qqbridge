#!/usr/bin/env python3
"""Build a deterministic package from tracked files; never include runtime data."""
import argparse
import ast
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--refresh-manifest', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    names = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z']).decode().split('\0')
    names = sorted(n for n in names if n and not n.startswith(('.github/', '.git/')) and n != 'manifest.json')
    version = (root / 'VERSION').read_text(encoding='utf-8').strip()
    manifest_path = root / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest['package_version'] != version:
        raise SystemExit('VERSION and manifest package_version disagree')
    files = {}
    sensitive = re.compile(rb'(?i)(?:sk-[a-z0-9_-]{20,}|gh[pousr]_[a-z0-9]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
    for name in names:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise SystemExit('Tracked entry is missing or a symlink: ' + name)
        if path.suffix in {'.pyc', '.zip', '.db', '.sqlite3', '.log'} or '__pycache__' in path.parts or path.name == '.env':
            raise SystemExit('Runtime artifact cannot be released: ' + name)
        data = path.read_bytes()
        if sensitive.search(data):
            raise SystemExit('Possible credential in tracked file: ' + name)
        if path.suffix == '.ps1' and not data.startswith(b'\xef\xbb\xbf'):
            raise SystemExit('PowerShell 5.1 script lacks UTF-8 BOM: ' + name)
        if path.suffix == '.sh' and b'\r' in data:
            raise SystemExit('Bash script has CRLF: ' + name)
        if path.suffix == '.py':
            ast.parse(data.decode('utf-8-sig'), filename=name)
        files[name] = {'sha256': digest(data), 'size': len(data)}
    if args.refresh_manifest:
        manifest['files'] = files
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    elif manifest['files'] != files:
        raise SystemExit('Manifest differs from tracked package. Review source then use --refresh-manifest before packaging.')
    subprocess.run(['python', '-I', str(root / 'wsl/package_verify.py'), '--root', str(root)], check=True)
    print('PASS syntax/encoding/credential-pattern checks:', len(files), 'tracked package files')
    if args.output is None:
        return
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f'qqbridge-v{version}.zip'
    if archive.exists():
        raise SystemExit('Output already exists; choose a new empty release directory')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for name in sorted([*names, 'manifest.json']):
            info = zipfile.ZipInfo(f'qqbridge-v{version}/{name}', date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if name.endswith('.sh') else 0o100644) << 16
            bundle.writestr(info, (root / name).read_bytes())
    checksum = digest(archive.read_bytes())
    archive.with_suffix('.zip.sha256').write_text(checksum + '  ' + archive.name + '\n', encoding='ascii')
    print(archive)
    print('SHA256', checksum)


if __name__ == '__main__':
    main()
