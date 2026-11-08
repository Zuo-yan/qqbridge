"""Vertex generateContent via existing httpx; credentials stay in process memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import tomllib
from typing import Any
from urllib.parse import urlsplit

import httpx

from gemini_client import GeminiSearchError, SearchCitation, SearchOutcome, SearchSource, SEARCH_SYSTEM_PROMPT
from vertex_search_privacy import clean_text, public_url, validate_query


@dataclass(frozen=True, repr=False)
class VertexCredentials:
    endpoint: str
    headers: dict[str, str] = field(repr=False)
    params: dict[str, str] = field(repr=False)
    secrets: tuple[str, ...] = field(repr=False)


def load_primary_provider(path: str, model: str, region: str = "global", auth_mode: str = "api_key") -> VertexCredentials:
    """Read current provider on every request; never persist or log credentials."""
    try:
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        providers = data.get("api_providers", [])
        matches = [p for p in providers if isinstance(p, dict) and p.get("name") == "PrimaryProvider"]
        if len(matches) != 1:
            raise ValueError
        provider = matches[0]
        key = provider.get("api_key", "")
        base = provider.get("base_url", "").rstrip("/")
        u = urlsplit(base)
        if (not isinstance(key, str) or not key.strip() or u.scheme != "https"
                or not re.fullmatch(r"(?:[a-z0-9-]+-)?aiplatform\.googleapis\.com", u.hostname or "")
                or u.username or u.password or u.query or u.fragment or u.port not in (None, 443)):
            raise ValueError
        if not re.fullmatch(r"[a-zA-Z0-9._-]{1,128}", model):
            raise ValueError
        if not re.fullmatch(r"[a-z0-9-]{1,64}", region):
            raise ValueError
        # Accept both the current regional publisher base and Express/global roots.
        path_part = u.path.rstrip("/")
        if path_part in {"", "/v1", "/v1beta1"}:
            base = base + ("/v1" if not path_part else "") + "/publishers/google"
        elif not re.fullmatch(
            r"/v1(?:beta1)?/(?:projects/[a-zA-Z0-9._:-]+/locations/[a-z0-9-]+/)?publishers/google(?:/models)?",
            path_part,
        ):
            raise ValueError
        if base.endswith("/models"):
            base = base[:-7]
        # Search-only region override; preserve project, API version and auth.
        if "/projects/" in base:
            base = re.sub(r"/locations/[a-z0-9-]+/", f"/locations/{region}/", base)
            host = "aiplatform.googleapis.com" if region == "global" else f"{region}-aiplatform.googleapis.com"
            base = "https://" + host + urlsplit(base).path
        elif region != "global":
            raise ValueError  # Express Mode is global only.
        endpoint = f"{base}/models/{model}:generateContent"
        headers = dict(provider.get("default_headers", {}))
        params = dict(provider.get("default_query", {}))
        if not all(isinstance(k, str) and isinstance(v, str) for m in (headers, params) for k, v in m.items()):
            raise ValueError
        # Avoid redirect/host overrides and ambiguous authentication.
        if any(k.lower() in {"host", "content-length"} for k in headers):
            raise ValueError
        # GeminiClient uses genai.Client(api_key=...), irrespective of legacy
        # auth_type in TOML. Do NOT send that API key as an OAuth bearer token.
        headers = {k: v for k, v in headers.items() if k.lower() not in {"authorization", "x-goog-api-key"}}
        params = {k: v for k, v in params.items() if k.lower() not in {"key", "api_key", "access_token"}}
        if auth_mode == "oauth":
            headers["Authorization"] = "Bearer " + key
        elif auth_mode == "api_key":
            headers["x-goog-api-key"] = key
        else:
            raise ValueError
        secrets = tuple({key, *headers.values(), *params.values()} - {""})
        return VertexCredentials(endpoint, headers, params, secrets)
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        raise GeminiSearchError("无法读取有效的 PrimaryProvider Vertex 配置（不回显配置或凭据）") from None


def _get(data: dict, camel: str, snake: str, default: Any = None) -> Any:
    return data.get(camel, data.get(snake, default))


def parse_grounding(data: Any, max_sources: int, secrets: tuple[str, ...] = ()) -> SearchOutcome:
    """Parse REST JSON or SDK model_dump(by_alias=False) without mixing candidates."""
    if not isinstance(data, dict) or not isinstance(data.get("candidates"), list):
        raise GeminiSearchError("Vertex 响应缺少 candidates")
    for candidate in data["candidates"]:
        if not isinstance(candidate, dict):
            continue
        metadata = _get(candidate, "groundingMetadata", "grounding_metadata", {})
        if not isinstance(metadata, dict):
            continue
        chunks = _get(metadata, "groundingChunks", "grounding_chunks", [])
        if not isinstance(chunks, list):
            continue
        sources: list[SearchSource] = []
        index_map: dict[int, int] = {}
        seen: dict[str, int] = {}
        for i, chunk in enumerate(chunks):
            web = chunk.get("web", {}) if isinstance(chunk, dict) else {}
            if not isinstance(web, dict):
                continue
            url = web.get("uri", "")
            if not public_url(url) or any(s and s in url for s in secrets):
                continue
            if url not in seen:
                if len(sources) >= max(1, min(max_sources, 20)):
                    continue
                seen[url] = len(sources)
                sources.append(SearchSource(clean_text(str(web.get("title") or url), secrets)[:500], url))
            index_map[i] = seen[url]
        if not sources:
            continue
        # Emit only provider-backed segments, not ungrounded model prose/guessed links.
        citations: list[SearchCitation] = []
        supports = _get(metadata, "groundingSupports", "grounding_supports", [])
        content = candidate.get("content") or {}
        parts = content.get("parts", []) if isinstance(content, dict) else []
        answer_parts = {i: p.get("text", "") for i, p in enumerate(parts) if isinstance(p, dict)
                        and not p.get("thought") and isinstance(p.get("text"), str)} if isinstance(parts, list) else {}
        for support in supports[:100] if isinstance(supports, list) else []:
            if not isinstance(support, dict):
                continue
            segment = support.get("segment") or {}
            if not isinstance(segment, dict):
                continue
            indices = _get(support, "groundingChunkIndices", "grounding_chunk_indices", [])
            if not isinstance(indices, list):
                continue
            refs = tuple(dict.fromkeys(index_map[i] for i in indices if type(i) is int and i in index_map))
            text = segment.get("text", "")
            # SDK/REST offsets are UTF-8 byte offsets, scoped to a content part.
            if not text:
                part_index = _get(segment, "partIndex", "part_index", 0) or 0
                start = _get(segment, "startIndex", "start_index", 0) or 0
                end = _get(segment, "endIndex", "end_index")
                if (type(part_index) is int and part_index in answer_parts
                        and type(start) is int and type(end) is int and 0 <= start < end):
                    try:
                        text = answer_parts[part_index].encode("utf-8")[start:end].decode("utf-8")
                    except UnicodeDecodeError:
                        continue
            if refs and isinstance(text, str) and text.strip():
                text = clean_text(text.strip(), secrets)
                text = re.sub(r"https?://[^\s<>\])]+", "[网址见来源]", text)
                citation = SearchCitation(text[:12000], refs)
                if citation not in citations:
                    citations.append(citation)
        queries = _get(metadata, "webSearchQueries", "web_search_queries", [])
        queries = tuple(clean_text(q, secrets)[:256] for q in queries[:10] if isinstance(q, str)) if isinstance(queries, list) else ()
        summary = "\n".join(c.text + " " + "".join(f"[{i + 1}]" for i in c.source_indices) for c in citations)
        if not summary:
            summary = "Google 返回了 grounding 来源，但未提供可映射的逐句引文；请显式读取来源核验，不据模型记忆补写摘要。"
        return SearchOutcome(summary, tuple(sources), queries, tuple(citations))
    raise GeminiSearchError("Vertex 未返回可核验的 Google Search grounding 来源；不能声称已联网搜索")


class VertexSearchClient:
    def __init__(self, *, model_config_path: str, model: str, timeout_seconds: float,
                 max_output_tokens: int, thinking_low: bool = True, region: str = "global",
                 auth_mode: str = "api_key", thinking_level: str = "MEDIUM") -> None:
        self._config_path = model_config_path
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._thinking_level = (thinking_level or "").upper() if thinking_low else "OFF" 
        self._region = region
        self._auth_mode = auth_mode
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=min(15., timeout_seconds)),
            follow_redirects=False,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def search(self, query: str, *, original_question: str = "", max_sources: int = 8) -> SearchOutcome:
        del original_question
        query = validate_query(query)
        credentials = load_primary_provider(self._config_path, self._model, self._region, self._auth_mode)
        if any(secret and secret in query for secret in credentials.secrets):
            raise GeminiSearchError("查询含凭据信息，已拒绝外发")
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": "Search the web for: " + query}]}],
            "systemInstruction": {"parts": [{"text": SEARCH_SYSTEM_PROMPT}]},
            "tools": [{"googleSearch": {}}],
            "generationConfig": {"maxOutputTokens": self._max_output_tokens},
        }
        if self._thinking_level in {"MEDIUM", "HIGH", "LOW"}:
            payload["generationConfig"]["thinkingConfig"] = {"thinkingLevel": self._thinking_level}
        else:
            payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
        try:
            response = await self._client.post(credentials.endpoint, headers=credentials.headers,
                                               params=credentials.params, json=payload)
            if response.status_code != 200:
                # No body, URL, headers, request id, or original exception: all can contain secrets.
                raise GeminiSearchError(f"Vertex 搜索接口返回 HTTP {response.status_code}（响应详情已隐藏）")
            data = response.json()
        except httpx.TimeoutException:
            raise GeminiSearchError("Vertex 搜索超时") from None
        except (httpx.HTTPError, ValueError):
            raise GeminiSearchError("Vertex 搜索请求或响应解析失败（详情已隐藏）") from None
        return parse_grounding(data, max_sources, credentials.secrets)
