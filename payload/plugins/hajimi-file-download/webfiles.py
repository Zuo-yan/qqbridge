"""Bounded internet file search. Public network only; binary never enters an LLM."""
import asyncio
import hashlib
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
import re
import socket
import time
from urllib.parse import quote, unquote, urlencode, urljoin, urlsplit
import xml.etree.ElementTree as ET

import aiohttp


SUFFIXES = ('.apk', '.zip', '.7z', '.rar', '.exe', '.msi', '.msix', '.deb', '.rpm',
            '.appimage', '.dmg', '.pkg', '.pdf', '.doc', '.docx', '.xlsx', '.xls',
            '.pptx', '.ppt', '.txt', '.md', '.csv', '.json', '.jar', '.tar.gz',
            '.tgz', '.gz', '.xz', '.bz2', '.zst', '.py', '.js', '.ts', '.java', '.kt',
            '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.mp4', '.mkv', '.mov',
            '.mp3', '.flac', '.wav', '.apk.1', '.iso', '.bin', '.apkx', '.apks', '.xapk')


def public_url(url):
    p = urlsplit(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError('只接受公网HTTPS地址')
    host = p.hostname.rstrip('.').lower()
    if host in ('localhost', 'metadata.google.internal') or '.' not in host:
        raise ValueError('不允许内网地址')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if host.endswith(('.local', '.internal', '.localhost', '.lan')):
            raise ValueError('不允许内网域名')
    else:
        if not address.is_global:
            raise ValueError('不允许非公网IP')
    return url


class PublicResolver(aiohttp.abc.AbstractResolver):
    """Validate actual DNS answers handed to the connector; no separate TOCTOU lookup."""
    def __init__(self):
        self.resolver = aiohttp.resolver.DefaultResolver()

    async def resolve(self, host, port=0, family=socket.AF_INET):
        results = await self.resolver.resolve(host, port, family)
        if not results or any(not ipaddress.ip_address(r['host']).is_global for r in results):
            raise OSError('拒绝解析到非公网IP的下载域名')
        return results

    async def close(self):
        await self.resolver.close()


def filename(url, disposition=''):
    from email.message import Message
    message = Message()
    message['Content-Disposition'] = disposition
    raw = message.get_filename() or unquote(urlsplit(url).path.rsplit('/', 1)[-1]) or 'download.bin'
    name = re.sub(r'[^\w.()+\- ]', '_', raw.replace('\\', '/').rsplit('/', 1)[-1])[:160].strip(' .')
    return name or 'download.bin'


def file_link(url):
    return urlsplit(url).path.lower().endswith(SUFFIXES)


class Links(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base, self.links, self.text = base, [], []
        self.anchor = None
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style', 'noscript'):
            self.hidden += 1
        if tag == 'a' and attrs.get('href'):
            url = urljoin(self.base, attrs['href'])
            try:
                public_url(url)
            except ValueError:
                self.anchor = None
                return
            self.anchor = {'url': url, 'title': attrs.get('title', '')[:120]}
            if len(self.links) < 250:
                self.links.append(self.anchor)

    def handle_endtag(self, tag):
        if tag == 'a':
            self.anchor = None
        if tag in ('script', 'style', 'noscript'):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            if len(self.text) < 1000:
                self.text.append(data.strip())
            if self.anchor:
                self.anchor['title'] = (self.anchor['title'] + ' ' + data.strip())[:180]


class WebHTTP:
    def __init__(self, session):
        self.session = session

    async def fetch(self, url, limit, sink=None, inspect=False):
        for _ in range(7):
            public_url(url)
            async with self.session.get(url, allow_redirects=False) as response:
                if response.status in (301, 302, 303, 307, 308):
                    url = urljoin(url, response.headers['Location'])
                    continue
                response.raise_for_status()
                kind = response.headers.get('Content-Type', '').lower()
                name = filename(url, response.headers.get('Content-Disposition', ''))
                info = {'url': url, 'name': name, 'type': kind,
                        'size': int(response.headers.get('Content-Length', 0))}
                binary = ('attachment' in response.headers.get('Content-Disposition', '').lower()
                          or (file_link(url) and 'text/html' not in kind)
                          or kind.startswith(('application/pdf', 'application/octet-stream', 'application/zip')))
                if inspect and binary:
                    return {**info, 'download': True}
                if info['size'] > limit:
                    raise ValueError('远端内容超过大小上限')
                if sink and 'text/html' in kind:
                    raise ValueError('服务器返回的是网页，不是所需文件')
                chunks, total = [], 0
                async for chunk in response.content.iter_chunked(256 * 1024):
                    total += len(chunk)
                    if total > limit:
                        raise ValueError('远端内容超过大小上限')
                    if sink:
                        sink.write(chunk)
                    else:
                        chunks.append(chunk)
                return {**info, 'size': total, 'data': b''.join(chunks)}
        raise ValueError('重定向次数过多')

    async def search(self, query):
        url = 'https://www.bing.com/search?' + urlencode({'format': 'rss', 'q': query[:300]})
        result = await self.fetch(url, 512 * 1024)
        root = ET.fromstring(result['data'])
        items = []
        for node in root.findall('./channel/item')[:8]:
            link = node.findtext('link', '')
            try:
                public_url(link)
            except ValueError:
                continue
            items.append({'url': link, 'title': node.findtext('title', '')[:150],
                          'description': node.findtext('description', '')[:220]})
        if not items:
            raise ValueError('没有取得有效搜索结果')
        return items

    async def page(self, url):
        p = urlsplit(url)
        repo = re.match(r'^/([^/]+)/([^/]+)(?:/releases(?:/tag/([^/]+))?)?/?$', p.path)
        if p.hostname == 'github.com' and repo:
            owner, name, tag = repo.groups()
            name = name.removesuffix(".git")
            endpoint = f'https://api.github.com/repos/{owner}/{name}/releases/'
            endpoint += 'tags/' + quote(unquote(tag), safe='') if tag else 'latest'
            try:
                release = json.loads((await self.fetch(endpoint, 2 * 1024 * 1024))['data'])
            except aiohttp.ClientResponseError as exc:
                if exc.status != 404: raise
                await self.fetch(f'https://api.github.com/repos/{owner}/{name}', 2 * 1024 * 1024)
                return {'url': url, 'links': [{'url': f'https://api.github.com/repos/{owner}/{name}/zipball', 'title': '源码ZIP（没有找到发布包）', 'archive': True}], 'excerpt':'无正式发布包，只有源码归档；需要请求者确认。'}
            assets = [{'url': a['browser_download_url'], 'title': a['name'], 'size': int(a['size']),
                       'sha256': (a.get('digest') or '').removeprefix('sha256:')}
                      for a in release.get('assets', []) if file_link(a['name'])]
            return {'url': url, 'links': assets[:80], 'excerpt': str(release.get('tag_name', ''))}
        result = await self.fetch(url, 1024 * 1024, inspect=True)
        if result.get('download'):
            return result
        raw = result['data'].decode('utf-8', errors='replace')
        parser = Links(result['url'])
        parser.feed(raw)
        links = {x['url']: x for x in parser.links}
        # Generic deep scan: installer URLs often live in inline/bundled JS or
        # JSON configs rather than <a> tags (QQ/WeChat-style single-page sites).
        scripts = [urljoin(result['url'], m.group(1))
                   for m in re.finditer(r'(?:src|href)=["\']([^"\']+\.js[^"\']*)["\']', raw)][:4]
        for script_url in scripts:
            try:
                blob = (await self.fetch(script_url, 2 * 1024 * 1024))['data'].decode('utf-8', 'replace')
            except Exception:
                continue
            for found in self._file_urls(blob):
                links.setdefault(found, {'url': found, 'title': filename(found)})
            for config in [m.group() for m in re.finditer(r'https://[^"\'<>\s\\]+\.json[^"\'<>\s\\]*', blob)][:3]:
                try:
                    data = (await self.fetch(config, 512 * 1024))['data'].decode('utf-8', 'replace')
                except Exception:
                    continue
                for found in self._file_urls(data):
                    links.setdefault(found, {'url': found, 'title': filename(found)})
        for found in self._file_urls(raw):
            links.setdefault(found, {'url': found, 'title': filename(found)})
        links = list(links.values())
        if p.hostname == 'im.qq.com':
            try:
                for item in await self.qq_android():
                    if item['url'] not in {x['url'] for x in links}:links.append(item)
            except (aiohttp.ClientError,ValueError,KeyError):
                pass
        # Direct file links stay first; interactive downloads keep priority over generic navigation.
        rank = lambda x: (0 if file_link(x['url']) else
                          1 if re.search(r'download|release|下载|win|windows|\.exe|\.msi|installer', x['title'] + x['url'], re.I) else 2)
        links.sort(key=rank)
        return {'url': result['url'], 'links': links[:80], 'excerpt': ' '.join(parser.text)[:1500]}

    async def qq_android(self):
        data = json.loads((await self.fetch(
            'https://qq-web.cdn-go.cn/im.qq.com_new/latest/rainbow/mobileConfig.json',
            512 * 1024))['data'])['android']
        candidates = [
            {'url': data.get('x64Link'), 'title': "QQ Android arm64（版本以文件名为准）"},
            {'url': data.get('x32Link'), 'title': "QQ Android armeabi-v7a（可能为旧版，版本以文件名为准）"},
        ]
        return [x for x in candidates if x['url']]

    def _file_urls(self, blob):
        found = []
        for match in re.finditer(r'https://[^"\'<>\s\\]+', blob):
            url = match.group().rstrip(');,.')
            if not file_link(url):
                continue
            try:
                public_url(url)
            except ValueError:
                continue
            found.append(url)
        return found
