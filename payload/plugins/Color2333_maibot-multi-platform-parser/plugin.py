# -*- coding: utf-8 -*-
"""MaiBot adapter for Zhalslar/astrbot_plugin_parser core parsers."""
from __future__ import annotations

from .factcheck_intent import explicit_factcheck_request

import asyncio
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from maibot_sdk import Field, HookHandler, MaiBotPlugin, PluginConfigBase
from maibot_sdk.types import HookMode, HookOrder

PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from .core.config import PluginConfig as CorePluginConfig
from .core.data import DynamicContent, GraphicsContent, ImageContent, ParseResult, TextContent, VideoContent
from .core.download import Downloader
from .core.exception import ParseException
from .core.parsers import BaseParser
from .sender import bind_sender, ApiSettings, image_segment, send_group_forward, send_image, send_text, send_video, text_segment

URL_RE = re.compile(r"https?://[^\s\]\)）>\"']+")


class PluginSectionConfig(PluginConfigBase):
    name: str = Field(default="multi_platform_parser", description="插件名称")
    config_version: str = Field(default="1.0.0", description="配置文件版本")
    version: str = Field(default="1.0.0", description="插件版本")
    enabled: bool = Field(default=True, description="是否启用插件")


class ParserSectionConfig(PluginConfigBase):
    enabled_platforms: list[str] = Field(
        default=["douyin", "xhs", "xiaoheihe"],
        description="启用的平台。B站默认由现有 Bilibili 插件处理，避免重复回复。",
    )
    group_whitelist: list[str] = Field(default_factory=list, description="只在这些 QQ 群自动解析；空列表表示所有群")
    block_ai_reply: bool = Field(default=True, description="命中链接后阻止麦麦继续触发普通聊天")
    debounce_seconds: int = Field(default=120, description="同一会话同一链接去重时间，单位秒", ge=0)
    max_images: int = Field(default=9, description="单条链接最多发送图片数", ge=1, le=30)
    max_text_chars: int = Field(default=700, description="摘要正文最大字符数", ge=80, le=3000)
    send_images: bool = Field(default=True, description="是否发送图片")
    send_video: bool = Field(default=True, description="是否发送视频")
    use_forward_for_multi: bool = Field(default=True, description="群聊多图/图文是否使用合并转发")
    source_max_size_mb: int = Field(default=80, description="单个媒体最大下载大小 MB", ge=1, le=300)
    source_max_minutes: int = Field(default=8, description="视频最大时长分钟数", ge=1, le=60)


class NetworkSectionConfig(PluginConfigBase):
    proxy: str = Field(default="", description="解析/下载代理，例如 http://127.0.0.1:7890；留空不用代理")
    use_proxy_platforms: list[str] = Field(default=[], description="需要走代理的平台名")
    common_timeout: int = Field(default=30, description="普通请求超时秒数", ge=5, le=120)
    download_timeout: int = Field(default=120, description="下载超时秒数", ge=10, le=600)
    download_retry_times: int = Field(default=1, description="下载重试次数", ge=0, le=5)


class CookieSectionConfig(PluginConfigBase):
    douyin: str = Field(default="", description="抖音 Cookie，可选")
    xhs: str = Field(default="", description="小红书 Cookie，可选")
    xiaoheihe: str = Field(default="", description="小黑盒 Cookie，可选")
    bilibili: str = Field(default="", description="B站 Cookie，可选")


class ApiConfig(PluginConfigBase):
    host: str = Field(default="127.0.0.1", description="OneBot HTTP API 主机")
    port: int = Field(default=3000, description="OneBot HTTP API 端口", ge=1, le=65535)
    token: str = Field(default="", description="OneBot HTTP API Token")
    bot_uin: str = Field(default="", description="发送合并转发节点时使用的 bot QQ")


class PluginConfig(PluginConfigBase):
    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)
    parser: ParserSectionConfig = Field(default_factory=ParserSectionConfig)
    network: NetworkSectionConfig = Field(default_factory=NetworkSectionConfig)
    cookies: CookieSectionConfig = Field(default_factory=CookieSectionConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)


class MultiPlatformParserPlugin(MaiBotPlugin):
    """自动解析抖音、小红书、小黑盒等社媒链接。"""

    config_model = PluginConfig
    config_reload_subscriptions: tuple[str, ...] = ()

    _downloader: Downloader | None = None
    _parsers: list[BaseParser] = []
    _recent: dict[tuple[str, str], float] = {}

    async def on_load(self) -> None:
        bind_sender(self.ctx)
        if not self.config.plugin.enabled:
            self.ctx.logger.info("Multi platform parser disabled")
            return
        core_cfg = self._build_core_config()
        self._downloader = Downloader(core_cfg)

        enabled = set(core_cfg.parser.enabled_platforms())
        self._parsers = [
            parser_cls(core_cfg, self._downloader)
            for parser_cls in BaseParser.get_all_subclass()
            if parser_cls.platform.name in enabled
        ]
        names = ", ".join(parser.platform.display_name for parser in self._parsers) or "none"
        self.ctx.logger.info("Multi platform parser loaded: %s", names)

    async def on_unload(self) -> None:
        for parser in self._parsers:
            await parser.close_session()
        self._parsers = []
        if self._downloader is not None:
            await self._downloader.close()
            self._downloader = None
        self.ctx.logger.info("Multi platform parser unloaded")

    async def on_config_update(self, scope: str, config_data: dict[str, object], version: str) -> None:
        del scope, config_data
        self.ctx.logger.info("Multi platform parser config updated to %s", version)

    @HookHandler(
        hook="chat.receive.after_process",
        name="multi_platform_parser_hook",
        description="自动解析抖音/小红书/小黑盒等平台链接",
        mode=HookMode.BLOCKING,
        order=HookOrder.EARLY,
    )
    async def handle_link(self, **kwargs) -> dict[str, Any] | None:
        if not self.config.plugin.enabled or not self._parsers:
            return None

        message: dict[str, Any] = kwargs.get("message", {}) or {}
        if explicit_factcheck_request(message):
            return {"action": "continue"}

        if not self._is_allowed_group(message):
            return None

        source = self._message_source(message)
        candidates = self._extract_urls(source)
        matched: tuple[BaseParser, str, Any, str] | None = None
        for url in candidates:
            for parser in self._parsers:
                try:
                    keyword, searched = parser.search_url(url)
                    matched = (parser, keyword, searched, url)
                    break
                except ParseException:
                    continue
            if matched:
                break

        if not matched:
            return None

        parser, keyword, searched, url = matched
        session_id = str(message.get("session_id", "") or self._group_or_user_id(message) or "unknown")
        if self._is_recent(session_id, url):
            return {"action": "abort"} if self.config.parser.block_ai_reply else None

        self.ctx.logger.info("Multi platform link detected: %s %s", parser.platform.display_name, url)
        asyncio.create_task(self._process_task(parser, keyword, searched, url, message))

        if self.config.parser.block_ai_reply:
            return {"action": "abort"}
        return None

    async def _process_task(self, parser: BaseParser, keyword: str, searched: Any, url: str, message: dict[str, Any]) -> None:
        try:
            result = await parser.parse(keyword, searched)
            if not result.url:
                result.url = url
            await self._send_result(message, result)
        except Exception as exc:
            self.ctx.logger.warning("Multi platform parser failed for %s: %s", url, exc)
            await send_text(message, f"这个链接解析失败了：{exc}", self.config.api)

    async def _send_result(self, message: dict[str, Any], result: ParseResult) -> None:
        header = self._format_header(result)
        text_nodes: list[list[dict[str, Any]]] = []
        media_items = self._flatten_contents(result)

        if header:
            text_nodes.append([text_segment(header)])

        image_nodes: list[list[dict[str, Any]]] = []
        videos: list[VideoContent | DynamicContent] = []

        image_count = 0
        for content in media_items:
            if isinstance(content, TextContent):
                if content.text:
                    text_nodes.append([text_segment(self._truncate(content.text, self.config.parser.max_text_chars))])
            elif isinstance(content, GraphicsContent):
                if content.text:
                    image_nodes.append([text_segment(self._truncate(content.text, self.config.parser.max_text_chars))])
                if self.config.parser.send_images and image_count < self.config.parser.max_images:
                    path = await content.get_path()
                    image_nodes.append([image_segment(path)])
                    image_count += 1
            elif isinstance(content, ImageContent):
                if self.config.parser.send_images and image_count < self.config.parser.max_images:
                    path = await content.get_path()
                    image_nodes.append([image_segment(path)])
                    image_count += 1
            elif isinstance(content, (VideoContent, DynamicContent)):
                videos.append(content)

        nodes = text_nodes + image_nodes
        sent_forward = False
        if self.config.parser.use_forward_for_multi and len(nodes) > 1 and self._get_group_id(message):
            sent_forward = await send_group_forward(message, nodes, self.config.api)

        if not sent_forward:
            if header:
                await send_text(message, header, self.config.api)
            for node in image_nodes:
                segment = node[0]
                if segment.get("type") == "text":
                    await send_text(message, segment["data"]["text"], self.config.api)
                elif segment.get("type") == "image":
                    await send_image(message, self._path_from_file_segment(segment), self.config.api)

        if self.config.parser.send_video:
            for video in videos[:1]:
                path = await video.get_path()
                await send_video(message, path, self.config.api)

    def _build_core_config(self) -> CorePluginConfig:
        data_dir = Path(__file__).resolve().parents[2] / "data" / "multi_platform_parser"
        return CorePluginConfig(
            data_dir=data_dir,
            enabled_platforms=list(self.config.parser.enabled_platforms),
            proxy=(self.config.network.proxy or "").strip() or None,
            source_max_size=self.config.parser.source_max_size_mb,
            source_max_minute=self.config.parser.source_max_minutes,
            debounce_interval=self.config.parser.debounce_seconds,
            download_timeout=self.config.network.download_timeout,
            download_retry_times=self.config.network.download_retry_times,
            common_timeout=self.config.network.common_timeout,
            bilibili_cookies=self.config.cookies.bilibili,
            douyin_cookies=self.config.cookies.douyin,
            xhs_cookies=self.config.cookies.xhs,
            xiaoheihe_cookies=self.config.cookies.xiaoheihe,
            use_proxy_platforms=list(self.config.network.use_proxy_platforms),
        )

    def _format_header(self, result: ParseResult) -> str:
        parts = [f"{result.platform.display_name}解析"]
        if result.author and result.author.name:
            parts.append(f"作者：{result.author.name}")
        if result.title:
            parts.append(f"标题：{self._truncate(result.title, 120)}")
        if result.text:
            parts.append(self._truncate(result.text, self.config.parser.max_text_chars))
        if result.extra_info:
            parts.append(str(result.extra_info))
        if result.url:
            parts.append(f"链接：{result.url}")
        return "\n".join(part for part in parts if part)

    def _flatten_contents(self, result: ParseResult) -> list[Any]:
        contents: list[Any] = []
        if result.send_groups:
            for group in result.send_groups:
                contents.extend(group.contents)
        else:
            contents.extend(result.contents)
        if result.repost:
            contents.extend(self._flatten_contents(result.repost))
        return contents

    def _message_source(self, message: dict[str, Any]) -> str:
        parts = [str(message.get("processed_plain_text", "") or "")]
        for seg in message.get("raw_message", []) or []:
            if not isinstance(seg, dict):
                continue
            data = seg.get("data", {})
            if isinstance(data, dict):
                for key in ("url", "source_url", "jumpUrl", "content"):
                    value = data.get(key)
                    if value:
                        parts.append(str(value))
        return "\n".join(parts)

    def _extract_urls(self, text: str) -> list[str]:
        seen: set[str] = set()
        urls: list[str] = []
        for match in URL_RE.finditer(text):
            url = match.group(0).rstrip(".,，。!！?？")
            if url not in seen:
                seen.add(url)
                urls.append(url)
        return urls

    def _is_allowed_group(self, message: dict[str, Any]) -> bool:
        group_id = self._get_group_id(message)
        if not group_id:
            return True
        whitelist = [str(item) for item in self.config.parser.group_whitelist if str(item).strip()]
        return not whitelist or group_id in whitelist

    def _is_recent(self, session_id: str, url: str) -> bool:
        interval = int(self.config.parser.debounce_seconds)
        if interval <= 0:
            return False
        now = time.time()
        key = (session_id, url)
        expires_at = self._recent.get(key, 0)
        self._recent[key] = now + interval
        for old_key, old_expires in list(self._recent.items()):
            if old_expires < now:
                self._recent.pop(old_key, None)
        return expires_at > now

    def _group_or_user_id(self, message: dict[str, Any]) -> str | None:
        return self._get_group_id(message) or self._get_user_id(message)

    @staticmethod
    def _truncate(text: str, max_chars: int) -> str:
        text = str(text or "").strip()
        if len(text) <= max_chars:
            return text
        return text[: max(0, max_chars - 1)].rstrip() + "…"

    @staticmethod
    def _path_from_file_segment(segment: dict[str, Any]) -> Path:
        file_value = str(segment.get("data", {}).get("file", ""))
        if file_value.startswith("file://"):
            parsed = urllib.parse.urlparse(file_value)
            return Path(urllib.request.url2pathname(parsed.path))
        return Path(file_value)

    @staticmethod
    def _get_group_id(message: dict[str, Any]) -> str | None:
        message_info = message.get("message_info", {})
        group_info = message_info.get("group_info") if isinstance(message_info, dict) else None
        group_id = group_info.get("group_id") if isinstance(group_info, dict) else None
        return str(group_id) if group_id else None

    @staticmethod
    def _get_user_id(message: dict[str, Any]) -> str | None:
        message_info = message.get("message_info", {})
        user_info = message_info.get("user_info", {}) if isinstance(message_info, dict) else {}
        user_id = user_info.get("user_id") if isinstance(user_info, dict) else None
        return str(user_id) if user_id else None


def create_plugin() -> MultiPlatformParserPlugin:
    return MultiPlatformParserPlugin()
