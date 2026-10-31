"""Safe public-web page fetcher used by the Gemini search plugin."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
import ipaddress
import re
import socket
from typing import Final
from urllib.parse import urljoin, urlsplit

import httpx


_REDIRECT_STATUS: Final = frozenset({301, 302, 303, 307, 308})
_TEXT_CONTENT_TYPES: Final = (
    "text/",
    "application/json",
    "application/ld+json",
    "application/xhtml+xml",
    "application/xml",
    "application/rss+xml",
    "application/atom+xml",
)


class PageFetchError(Exception):
    """A safe page-fetch error."""


@dataclass(frozen=True, slots=True)
class FetchOutcome:
    url: str
    title: str
    content: str


class _TextExtractor(HTMLParser):
    """Extract readable text while dropping scripts and styles."""

    _SKIP_TAGS: Final = frozenset({"script", "style", "noscript", "svg", "canvas"})
    _BLOCK_TAGS: Final = frozenset(
        {
            "article",
            "aside",
            "blockquote",
            "br",
            "div",
            "footer",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "header",
            "li",
            "main",
            "ol",
            "p",
            "pre",
            "section",
            "table",
            "tr",
            "ul",
        }
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._title_depth = 0
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "title":
            self._title_depth += 1
        if tag in self._BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if tag == "title" and self._title_depth:
            self._title_depth -= 1
        if tag in self._BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._title_depth:
            self.title_parts.append(data)
        if not self._skip_depth:
            self.text_parts.append(data)

    def title(self) -> str:
        return _clean_text(" ".join(self.title_parts))

    def text(self) -> str:
        return _clean_text(" ".join(self.text_parts))


def _clean_text(text: str) -> str:
    text = unescape(text).replace("\u00a0", " ")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class SafePageFetcher:
    """Fetch public HTTP(S) pages with DNS and redirect checks."""

    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_bytes: int,
        max_redirects: int,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_bytes = max_bytes
        self._max_redirects = max_redirects
        self._client = httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(timeout_seconds, connect=min(15.0, timeout_seconds)),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; MaiBot-Gemini-Fetch/1.0; "
                    "+https://github.com/yetone/magpie)"
                )
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch(self, url: str, *, max_chars: int) -> FetchOutcome:
        current = url.strip()
        for redirect_index in range(self._max_redirects + 1):
            await self._validate_public_url(current)
            try:
                async with self._client.stream("GET", current) as response:
                    if response.status_code in _REDIRECT_STATUS:
                        location = response.headers.get("location", "").strip()
                        if not location:
                            raise PageFetchError("网页返回重定向，但缺少 Location")
                        if redirect_index >= self._max_redirects:
                            raise PageFetchError("网页重定向次数过多")
                        current = urljoin(current, location)
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").lower()
                    if content_type and not content_type.startswith(_TEXT_CONTENT_TYPES):
                        raise PageFetchError(
                            f"该地址不是可读文本页面，Content-Type={content_type[:120]}"
                        )
                    content_length = response.headers.get("content-length")
                    if content_length:
                        try:
                            if int(content_length) > self._max_bytes:
                                raise PageFetchError("网页正文超过大小上限")
                        except ValueError:
                            pass
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > self._max_bytes:
                            raise PageFetchError("网页正文超过大小上限")
                        chunks.append(chunk)
                    raw = b"".join(chunks)
                    encoding = response.encoding or "utf-8"
                    decoded = raw.decode(encoding, errors="replace")
                    final_url = str(response.url)
            except PageFetchError:
                raise
            except httpx.TimeoutException as exc:
                raise PageFetchError("网页抓取超时") from exc
            except httpx.HTTPStatusError as exc:
                raise PageFetchError(
                    f"网页返回 HTTP {exc.response.status_code}"
                ) from exc
            except httpx.HTTPError as exc:
                raise PageFetchError(f"网页抓取失败: {exc}") from exc

            parser = _TextExtractor()
            if "html" in content_type or not content_type:
                parser.feed(decoded)
                title = parser.title()
                text = parser.text()
            else:
                title = ""
                text = _clean_text(decoded)
            if not text:
                raise PageFetchError("网页没有可读取的文本正文")
            if max_chars > 0 and len(text) > max_chars:
                text = text[:max_chars].rstrip() + "\n\n[正文已截断]"
            return FetchOutcome(url=final_url, title=title, content=text)
        raise PageFetchError("网页重定向次数过多")

    async def _validate_public_url(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"}:
            raise PageFetchError("只允许 http/https 地址")
        if not parts.hostname or parts.username or parts.password:
            raise PageFetchError("网页地址缺少有效主机名，或包含用户名密码")
        hostname = parts.hostname.rstrip(".").lower()
        if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(
            (".local", ".internal", ".localhost")
        ):
            raise PageFetchError("不允许抓取本机或内部网络地址")
        port = parts.port or (443 if parts.scheme == "https" else 80)
        try:
            records = await asyncio.to_thread(
                socket.getaddrinfo,
                hostname,
                port,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise PageFetchError(f"无法解析网页主机: {hostname}") from exc
        addresses = {
            str(record[4][0]).split("%", 1)[0]
            for record in records
            if len(record) >= 5 and record[4]
        }
        if not addresses:
            raise PageFetchError("网页主机没有可用的 IP 地址")
        for address in addresses:
            try:
                ip = ipaddress.ip_address(address)
            except ValueError as exc:
                raise PageFetchError("网页主机解析结果无效") from exc
            if not ip.is_global:
                raise PageFetchError("不允许抓取私有、回环或保留地址")
