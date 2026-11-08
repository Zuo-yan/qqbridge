"""Local input checks. Never attach chat history or the original question."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

from gemini_client import GeminiSearchError


_SENSITIVE = re.compile(
    r"(?i)(?:bearer\s+\S+|AIza[\w-]{20,}|sk-[\w-]{12,}|"
    r"(?:api[_ -]?key|password|token|secret|密码|密钥|身份证|手机号|聊天记录|私聊|非公开)"
    r"|[\w.+-]+@[\w.-]+\.[a-z]{2,}|\b\d{7,18}[xX]?\b|"
    r"\b(?:\d{1,3}\.){3}\d{1,3}\b)"
)


def public_url(url: object) -> bool:
    if not isinstance(url, str) or len(url) > 8192 or any(ord(c) < 33 for c in url):
        return False
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").rstrip(".").lower()
        if parts.scheme not in {"http", "https"} or not host or parts.username or parts.password:
            return False
        if parts.port is not None and not 1 <= parts.port <= 65535:
            return False
        if host == "localhost" or host.endswith((".local", ".internal", ".localhost")):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return "." in host
    except ValueError:
        return False


def validate_query(query: object) -> str:
    if not isinstance(query, str):
        raise GeminiSearchError("query 必须是字符串")
    normalized = " ".join(query.split())
    if not normalized or len(normalized) > 256:
        raise GeminiSearchError("query 必须为 1–256 字符")
    if _SENSITIVE.search(normalized):
        raise GeminiSearchError("查询含疑似私人信息或凭据，请改为不含私人上下文的公开关键词")
    # Search URLs may disclose credentials in query/fragment/path; use gemini_fetch.
    if re.search(r"(?i)https?://|www\.", normalized):
        raise GeminiSearchError("读取公开链接请显式调用 gemini_fetch，不将链接送入搜索服务")
    return normalized


def clean_text(text: str, secrets: tuple[str, ...] = ()) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return re.sub(r"(?i)(?:bearer\s+\S+|AIza[\w-]{20,}|sk-[\w-]{12,})", "[REDACTED]", text)


def validate_fetch_url(url: object) -> str:
    if not isinstance(url, str) or not public_url(url.strip()):
        raise GeminiSearchError("只允许不含鉴权信息的公开 http/https 网页")
    normalized = url.strip()
    if re.search(r"(?i)(?:[?&#](?:key|api_key|token|access_token|password|signature|x-amz-[^=]+)=)", normalized):
        raise GeminiSearchError("拒绝向网页服务发送含凭据的链接")
    return normalized
