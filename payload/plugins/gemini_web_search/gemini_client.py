"""Gemini Google Search client for Magpie's Anthropic-compatible endpoint."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


SEARCH_SYSTEM_PROMPT = (
    "You are a web search tool. Search the web for what is asked and report what the "
    "results say: the facts that answer it, as specifically as they are given "
    "(numbers, dates, versions, names), each with the title of its page. "
    "Answer in the same language as the user's question. Do not answer from memory, "
    "do not invent or guess URLs, and do not add unrelated advice. The calling tool "
    "will append the actual source URLs returned by Google Search. Be concise."
)


class GeminiSearchError(Exception):
    """A safe error that can be returned to the planner."""


@dataclass(frozen=True, slots=True)
class SearchSource:
    title: str
    url: str


@dataclass(frozen=True, slots=True)
class SearchOutcome:
    text: str
    sources: tuple[SearchSource, ...]
    queries: tuple[str, ...]


class GeminiSearchClient:
    """Call Gemini with the hosted web-search tool and parse grounded sources."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_output_tokens: int,
        max_uses: int,
    ) -> None:
        self._endpoint = base_url.rstrip("/") + "/messages"
        self._api_key = api_key
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._max_uses = max_uses
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=min(15.0, timeout_seconds)),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def search(
        self,
        query: str,
        *,
        original_question: str = "",
        max_sources: int = 8,
    ) -> SearchOutcome:
        """Run one grounded Google Search request through Gemini."""

        user_content = "Search the web for: " + query
        if original_question:
            user_content += "\nThe original user question is: " + original_question
        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_output_tokens,
            "stream": False,
            "system": SEARCH_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_content}],
            "tools": [
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": self._max_uses,
                }
            ],
        }
        try:
            response = await self._client.post(
                self._endpoint,
                headers={
                    "Authorization": "Bearer " + self._api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            raise GeminiSearchError("Gemini 联网搜索超时") from exc
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:500].replace("\n", " ")
            raise GeminiSearchError(
                f"Gemini 搜索接口返回 HTTP {exc.response.status_code}: {body}"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise GeminiSearchError(f"Gemini 搜索请求失败: {exc}") from exc

        blocks = data.get("content")
        if not isinstance(blocks, list):
            raise GeminiSearchError("Gemini 搜索响应缺少 content 数组")

        texts: list[str] = []
        sources: list[SearchSource] = []
        queries: list[str] = []
        seen_urls: set[str] = set()
        searched = False
        for block in blocks:
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type") or "")
            if block_type == "text":
                text = str(block.get("text") or "").strip()
                if text:
                    texts.append(text)
                continue
            if block_type == "server_tool_use":
                searched = True
                tool_input = block.get("input")
                if isinstance(tool_input, dict):
                    query_text = str(tool_input.get("query") or "").strip()
                    if query_text and query_text not in queries:
                        queries.append(query_text)
                continue
            if block_type != "web_search_tool_result":
                continue
            searched = True
            raw_results = block.get("content")
            if not isinstance(raw_results, list):
                continue
            for raw_result in raw_results:
                if not isinstance(raw_result, dict):
                    continue
                url = str(raw_result.get("url") or "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                title = str(raw_result.get("title") or url).strip()
                sources.append(SearchSource(title=title, url=url))
                if len(sources) >= max_sources:
                    break

        if not searched:
            raise GeminiSearchError("Gemini 没有执行 Google 搜索，拒绝使用未检索的记忆作答")
        if not sources:
            raise GeminiSearchError("Gemini 已尝试搜索，但没有返回可核验的来源")

        summary = "\n\n".join(texts).strip()
        if not summary:
            summary = "Gemini 已完成搜索，但没有生成摘要。请根据下方来源判断。"
        return SearchOutcome(
            text=summary,
            sources=tuple(sources),
            queries=tuple(queries),
        )
