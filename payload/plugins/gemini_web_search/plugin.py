"""Gemini Google Search and safe page-fetch tools for MaiBot."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from pathlib import Path
import sys
from time import monotonic
from typing import Any
from typing import Literal

from maibot_sdk import Field, MaiBotPlugin, PluginConfigBase, Tool
from maibot_sdk.types import ToolParameterInfo, ToolParamType

PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from fetch_client import FetchOutcome, PageFetchError, SafePageFetcher
from gemini_client import (
    GeminiSearchClient,
    GeminiSearchError,
    SearchOutcome,
)
from vertex_search_client import VertexSearchClient
from deepseek_search_client import DeepSeekSearchClient
from vertex_search_privacy import validate_query, validate_fetch_url


class PluginSectionConfig(PluginConfigBase):
    __ui_label__ = "插件"
    __ui_icon__ = "package"
    __ui_order__ = 0

    enabled: bool = Field(
        default=True,
        description="是否启用 Gemini 联网搜索与网页抓取工具",
    )
    config_version: str = Field(
        default="1.3.0",
        description="配置文件版本号",
        json_schema_extra={"disabled": True},
    )


class ProviderConfig(PluginConfigBase):
    __ui_label__ = "Vertex / Magpie"
    __ui_icon__ = "sparkles"
    __ui_order__ = 1

    backend: Literal["deepseek", "vertex", "magpie"] = Field(
        default="vertex", description="DeepSeek 独立搜索优先，失败时限时回退到 Vertex",
    )
    deepseek_credential_path: str = Field(default="/MaiMBot/config/deepseek-search.key", description="DeepSeek 密钥文件路径")
    model_config_path: str = Field(
        default="/MaiMBot/config/model_config.toml",
        description="运行时只读 PrimaryProvider 的凭据和 Vertex 地址；不保存密钥副本",
    )
    region: str = Field(
        default="global",
        description="仅搜索使用的 Vertex 区域；从 PrimaryProvider 保留 project/key 派生，不修改主模型区域",
    )
    auth_mode: Literal["api_key", "oauth"] = Field(
        default="api_key",
        description="默认遵循 GeminiClient：api_key 使用 x-goog-api-key，忽略遗留 auth_type；仅明确提供 OAuth token 时选择 oauth",
    )
    thinking_level: Literal["MEDIUM", "HIGH", "LOW", "OFF"] = Field(
        default="MEDIUM",
        description="Flash 搜索模型的思考档位，默认 MEDIUM，不使用最低档；不影响 Argon LOW",
    )
    magpie_model: str = Field(
        default="antigravity/gemini-3.8-flash", description="仅 Magpie 后端使用的模型标识",
    )

    base_url: str = Field(
        default="http://magpie-dfy:3425/v1",
        description="Magpie 的 Anthropic 兼容接口根地址",
    )
    api_key: str = Field(
        default="",
        description="Magpie gateway key",
        repr=False,
        json_schema_extra={"x-widget": "password"},
    )
    model: str = Field(
        default="gemini-3.8-flash",
        description="Vertex 搜索模型 ID，可独立替换为主线程实测 ID",
    )
    timeout_seconds: float = Field(
        default=90.0,
        ge=10.0,
        le=180.0,
        description="单次 Gemini 搜索请求超时（秒）",
    )


class SearchConfig(PluginConfigBase):
    __ui_label__ = "联网搜索"
    __ui_icon__ = "search"
    __ui_order__ = 2

    default_sources: int = Field(
        default=6,
        ge=1,
        le=20,
        description="模型未指定数量时最多返回多少个来源",
    )
    max_sources: int = Field(
        default=10,
        ge=1,
        le=20,
        description="单次搜索最多返回多少个来源",
    )
    max_output_tokens: int = Field(
        default=1800,
        ge=600,
        le=4000,
        description="Gemini 搜索摘要的最大输出 token",
    )
    max_output_chars: int = Field(
        default=12000,
        ge=1000,
        le=30000,
        description="返回给 Planner 的总字符上限",
    )
    cache_ttl_seconds: int = Field(
        default=300,
        ge=0,
        le=86400,
        description="相同查询的结果缓存时间；0 表示不缓存",
    )
    max_uses: int = Field(
        default=3,
        ge=1,
        le=5,
        description="仅 Magpie：单次回答最多执行几次 Google Search；Vertex API 无对应硬限制",
    )


class FetchConfig(PluginConfigBase):
    __ui_label__ = "网页抓取"
    __ui_icon__ = "file-text"
    __ui_order__ = 3

    max_content_chars: int = Field(
        default=10000,
        ge=1000,
        le=50000,
        description="网页正文返回给 Planner 的最大字符数",
    )
    max_bytes: int = Field(
        default=5_000_000,
        ge=100_000,
        le=10_000_000,
        description="网页下载大小上限（字节）",
    )
    timeout_seconds: float = Field(
        default=30.0,
        ge=5.0,
        le=90.0,
        description="网页抓取超时（秒）",
    )
    max_redirects: int = Field(
        default=5,
        ge=0,
        le=10,
        description="网页最多跟随多少次重定向",
    )


class GeminiWebSearchConfig(PluginConfigBase):
    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    fetch: FetchConfig = Field(default_factory=FetchConfig)


class GeminiWebSearchPlugin(MaiBotPlugin):
    config_model = GeminiWebSearchConfig

    def __init__(self) -> None:
        super().__init__()
        self._search_client: GeminiSearchClient | VertexSearchClient | None = None
        self._fetcher: SafePageFetcher | None = None
        self._rebuild_lock = asyncio.Lock()
        self._cache: OrderedDict[
            tuple[str, str, int],
            tuple[float, SearchOutcome],
        ] = OrderedDict()

    async def on_load(self) -> None:
        await self._rebuild_clients()
        if self.config.provider.backend == "magpie" and not self.config.provider.api_key.strip():
            self.ctx.logger.warning(
                "Gemini 联网搜索未配置 Magpie gateway key，工具调用会返回错误"
            )
        else:
            self.ctx.logger.info(
                "联网搜索已加载：gemini_search 使用配置的搜索后端（DeepSeek 优先、Vertex 备用），"
                "gemini_fetch 使用安全网页抓取"
            )

    async def on_unload(self) -> None:
        await self._close_clients()
        self.ctx.logger.info("Gemini 联网搜索已卸载")

    async def on_config_update(
        self,
        scope: str,
        config_data: dict[str, Any],
        version: str,
    ) -> None:
        del scope, config_data, version
        self._cache.clear()
        await self._rebuild_clients()
        self.ctx.logger.info("Gemini 联网搜索配置已热更新")

    async def _rebuild_clients(self) -> None:
        async with self._rebuild_lock:
            await self._close_clients()
            provider = self.config.provider
            if provider.backend in {"vertex", "deepseek"}:
                self._search_client = VertexSearchClient(
                    model_config_path=provider.model_config_path,
                    model=provider.model,
                    timeout_seconds=provider.timeout_seconds,
                    max_output_tokens=self.config.search.max_output_tokens,
                    thinking_level=provider.thinking_level,
                    region=provider.region,
                    auth_mode=provider.auth_mode,
                )
                if provider.backend == "deepseek":
                    self._search_client = DeepSeekSearchClient(fallback=self._search_client, credential_path=provider.deepseek_credential_path)
            else:
                self._search_client = GeminiSearchClient(
                    base_url=provider.base_url,
                    api_key=provider.api_key,
                    model=provider.magpie_model,
                    timeout_seconds=provider.timeout_seconds,
                    max_output_tokens=self.config.search.max_output_tokens,
                    max_uses=self.config.search.max_uses,
                )
            fetch = self.config.fetch
            self._fetcher = SafePageFetcher(
                timeout_seconds=fetch.timeout_seconds,
                max_bytes=fetch.max_bytes,
                max_redirects=fetch.max_redirects,
            )

    async def _close_clients(self) -> None:
        search_client, self._search_client = self._search_client, None
        fetcher, self._fetcher = self._fetcher, None
        if search_client is not None:
            await search_client.close()
        if fetcher is not None:
            await fetcher.close()

    @staticmethod
    def _error(action: str, message: str) -> dict[str, Any]:
        return {"success": False, "error": f"{action}失败：{message}"}

    def _normalize_sources(self, count: int | None) -> int:
        if type(count) is not int:
            count = self.config.search.default_sources
        return max(1, min(count, self.config.search.max_sources))

    def _cache_get(
        self,
        key: tuple[str, str, int],
    ) -> SearchOutcome | None:
        ttl = self.config.search.cache_ttl_seconds
        if ttl <= 0:
            return None
        item = self._cache.get(key)
        if item is None:
            return None
        expires_at, outcome = item
        if monotonic() >= expires_at:
            self._cache.pop(key, None)
            return None
        self._cache.move_to_end(key)
        return outcome

    def _cache_put(
        self,
        key: tuple[str, str, int],
        outcome: SearchOutcome,
    ) -> None:
        ttl = self.config.search.cache_ttl_seconds
        if ttl <= 0:
            return
        self._cache[key] = (monotonic() + ttl, outcome)
        self._cache.move_to_end(key)
        while len(self._cache) > 128:
            self._cache.popitem(last=False)

    @staticmethod
    def _format_search(outcome: SearchOutcome, max_chars: int) -> str:
        lines = [
            "联网搜索结果（实际后端见下文）",
            "检索到的资料：",
            outcome.text.strip(),
        ]
        if outcome.queries:
            lines.extend(("", "实际搜索词：" + "；".join(outcome.queries)))
        lines.extend(("", "可核验来源："))
        for index, source in enumerate(outcome.sources, 1):
            lines.append(f"{index}. {source.title} — {source.url}")
        lines.extend(
            (
                "",
                "回答时只使用以上检索资料，引用相关来源；来源不足时明确说明，不要补编。",
            )
        )
        result = "\n".join(lines).strip()
        if len(result) > max_chars:
            result = result[:max_chars].rstrip() + "\n\n[搜索结果已截断]"
        return result

    @Tool(
        "gemini_search",
        description=(
            "联网检索实时公开网页：DeepSeek 独立搜索优先，Gemini 备用。"
            "仅在问题需要外部公开资料时显式调用，普通闲聊不调用。"
            "先提炼不含私人信息的公开关键词并设置 public_query=true；"
            "禁止发送非公开聊天、身份信息、凭据、群号或原始聊天上下文。"
            "知识可能过时、"
            "信息不完整、需要最新新闻/版本/价格/人物近况/作品资料/事实核查时优先使用。"
            "query 应写成具体搜索关键词；返回检索摘要和 Google Search 实际找到的来源。"
        ),
        parameters=[
            ToolParameterInfo(
                name="public_query",
                param_type=ToolParamType.BOOLEAN,
                description="仅当 query 已去除所有私人聊天与身份上下文、只含公开检索关键词时设为 true。",
                required=True,
            ),
            ToolParameterInfo(
                name="query",
                param_type=ToolParamType.STRING,
                description="搜索关键词，1-128 字符；应尽量具体。",
                required=True,
            ),
            ToolParameterInfo(
                name="ori_question",
                param_type=ToolParamType.STRING,
                description="旧接口兼容字段；忽略此字段，绝不外发或缓存原始问题。",
                required=False,
            ),
            ToolParameterInfo(
                name="count",
                param_type=ToolParamType.INTEGER,
                description="最多返回多少个来源，可选；超过插件上限时截断。",
                required=False,
            ),
        ],
        visibility="visible",
    )
    async def gemini_search(
        self,
        query: str = "",
        ori_question: str = "",
        count: int | None = None,
        public_query: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del kwargs, ori_question
        if not self.config.plugin.enabled:
            return self._error("联网搜索", "插件已在配置中停用")
        if public_query is not True:
            return self._error("联网搜索", "须显式确认 public_query=true，且只提交公开检索关键词")
        try:
            normalized_query = validate_query(query)
        except GeminiSearchError as exc:
            return self._error("联网搜索", str(exc))
        max_sources = self._normalize_sources(count)
        provider = self.config.provider
        key = (normalized_query, f"{provider.backend}:{provider.model}:{provider.region}:{provider.auth_mode}:{provider.thinking_level}:{provider.magpie_model}", max_sources)
        outcome = self._cache_get(key)
        cache_hit = outcome is not None
        if outcome is None:
            if self._search_client is None:
                return self._error("联网搜索", "Gemini 搜索客户端尚未初始化")
            try:
                outcome = await self._search_client.search(
                    normalized_query,
                    max_sources=max_sources,
                )
            except GeminiSearchError as exc:
                return {**self._error("联网搜索", str(exc)), "must_reply": True, "user_notice": "这次联网搜索超时或服务暂不可用，暂时没查到可靠结果，请稍后再试。"}
            self._cache_put(key, outcome)
        return {
            "success": True,
            "content": self._format_search(
                outcome,
                self.config.search.max_output_chars,
            ),
            "sources": [
                {"title": source.title, "url": source.url}
                for source in outcome.sources
            ],
            "cache_hit": cache_hit,
            "grounded": bool(outcome.sources),
            "citations": [
                {"text": citation.text, "source_indices": list(citation.source_indices)}
                for citation in outcome.citations
            ],
        }

    @Tool(
        "gemini_fetch",
        description=(
            "读取一个公开 http/https 网页的可读正文。需要打开用户给出的链接、"
            "核对原文或搜索摘要不足时使用。只允许公开互联网地址，"
            "自动拒绝本机、私网、保留地址和二进制文件。"
        ),
        parameters=[
            ToolParameterInfo(
                name="url",
                param_type=ToolParamType.STRING,
                description="要读取的公开网页 URL。",
                required=True,
            ),
        ],
        visibility="visible",
    )
    async def gemini_fetch(self, url: str = "", **kwargs: Any) -> dict[str, Any]:
        del kwargs
        if not self.config.plugin.enabled:
            return self._error("网页抓取", "插件已在配置中停用")
        try:
            normalized_url = validate_fetch_url(url)
        except GeminiSearchError as exc:
            return self._error("网页抓取", str(exc))
        if self._fetcher is None:
            return self._error("网页抓取", "网页抓取客户端尚未初始化")
        try:
            outcome: FetchOutcome = await self._fetcher.fetch(
                normalized_url,
                max_chars=self.config.fetch.max_content_chars,
            )
        except PageFetchError as exc:
            return self._error("网页抓取", str(exc))
        title = outcome.title or outcome.url
        return {
            "success": True,
            "content": (
                f"网页：{title}\n"
                f"地址：{outcome.url}\n\n"
                f"{outcome.content}"
            ),
        }


def create_plugin() -> GeminiWebSearchPlugin:
    """Create the plugin instance expected by the MaiBot runner."""

    return GeminiWebSearchPlugin()
