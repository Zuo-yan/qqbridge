"""
麦麦!来点二次元图片! — MaiBot 插件
==================================

基于 cnmiw.com (MirlKoi API) 的随机二次元图片插件。

功能：
1. 用户发色图关键词（涩图/色图/setu…）时 → 随机发一张色图
2. 用户发无色图关键词（来点图/美图/二次元…）时 → 随机发一张无色图
3. 按需直连 API 取图，原图直发不压缩
4. 群聊/私聊黑白名单（参考 napcat 适配器），@触发，冷却防刷，近期去重

依赖：httpx
"""

from __future__ import annotations

import asyncio
import base64
import time
from collections import deque
from typing import Any, ClassVar, Iterable

from maibot_sdk import CONFIG_RELOAD_SCOPE_SELF, Command, MaiBotPlugin, Tool
from maibot_sdk.types import ToolParameterInfo, ToolParamType

from .config import CONFIG_SCHEMA_VERSION, PixivCrawlerConfig
from .media_intent import image_intent
from .random_request_guard import current_random_request

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

# ═══════════════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════════════

# 下载图片时统一带这个 Referer：sinaimg.cn 直链需要它，CDN(setu.iw233.top)忽略它，两条链路都通
IMAGE_REFERER = "https://weibo.com/"
IMAGE_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

# Command 路由用的关键词联合正则（装饰器静态求值，无法读 config）。
# 这只是"接住"消息用，真正分桶由 handler 读 config.send.nsfw_keywords / sfw_keywords 决定。
# 故意列举常见词，避免 r".+" 宽匹配吞掉别的插件命令（v3.2.3 教训）。
ROUTE_PATTERN = (
    r"(?:^|.*)(?:"
    r"涩图|色图|瑟图|来点涩图|来点色图|setu|r18|"
    r"来点图|来张图|看看腿|来点腿|来点二次元图片|来点二次元图|二次元|美图|无色图|来点老婆|来点好康"
    r")(?:.*|$)"
)


# ═══════════════════════════════════════════════════════════════════════
# 主插件类
# ═══════════════════════════════════════════════════════════════════════


class PixivCrawlerPlugin(MaiBotPlugin):
    config_model = PixivCrawlerConfig

    # 本插件只关心自身配置热重载
    config_reload_subscriptions: ClassVar[Iterable[str]] = ()

    def __init__(self) -> None:
        super().__init__()
        self._last_send_time: float = 0.0
        # 近期已发 URL 去重缓存：集合做 O(1) 查询，deque 维持插入顺序用于淘汰
        self._sent_url_set: set[str] = set()
        self._sent_url_order: deque[str] = deque()
        self._sent_max: int = 500

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def on_load(self) -> None:
        self.ctx.logger.info("[SetuPlugin] 插件已加载 (v%s, cnmiw API)", CONFIG_SCHEMA_VERSION)
        if not self.config.plugin.enabled:
            self.ctx.logger.info("[SetuPlugin] 总开关已关闭，跳过初始化")
            return
        if not HAS_HTTPX:
            self.ctx.logger.error("[SetuPlugin] httpx 未安装，插件无法运行！")
            return
        self._sent_max = max(1, int(self.config.send.dedup_max_size))
        self.ctx.logger.info(
            "[SetuPlugin] 就绪：色图=%s 无色图=%s 去重=%s",
            self.config.send.nsfw_allowed,
            self.config.send.sfw_allowed,
            self.config.send.dedup_enabled,
        )

    async def on_unload(self) -> None:
        self.ctx.logger.info("[SetuPlugin] 插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict[str, Any], version: str) -> None:
        if scope != CONFIG_RELOAD_SCOPE_SELF:
            return
        self.ctx.logger.info("[SetuPlugin] 配置已更新, v=%s", version)
        if not HAS_HTTPX:
            return
        new_max = max(1, int(self.config.send.dedup_max_size))
        if new_max != self._sent_max:
            self._sent_max = new_max
            self._trim_sent_cache()

    # ── 访问控制 ───────────────────────────────────────────────────────

    def _extract_chat_context(self, kwargs: dict) -> tuple[str, str, bool]:
        """提取 (group_id, user_id, is_group)，均为字符串。

        兼容 Command 路径（顶层直接有 group_id/user_id）和 Tool 路径
        （嵌套在 message.message_info 里）。
        """
        group_id = str(kwargs.get("group_id", "") or "")
        user_id = str(kwargs.get("user_id", "") or "")
        has_group_info = False

        msg = kwargs.get("message", {})
        if isinstance(msg, dict):
            msg_info = msg.get("message_info") or {}
            if isinstance(msg_info, dict):
                group_info = msg_info.get("group_info")
                if group_info is not None:
                    has_group_info = True
                    if isinstance(group_info, dict) and not group_id:
                        group_id = str(group_info.get("group_id", "") or "")
                user_info = msg_info.get("user_info") or {}
                if isinstance(user_info, dict) and not user_id:
                    user_id = str(user_info.get("user_id", "") or "")

        is_group = bool(group_id) or has_group_info
        return group_id, user_id, is_group

    def _is_chat_allowed(self, kwargs: dict) -> bool:
        """按群聊/私聊黑白名单判断当前会话是否允许发图。"""
        cf = self.config.chat_filter
        if not cf.enabled:
            return True
        group_id, user_id, is_group = self._extract_chat_context(kwargs)
        if is_group:
            return self._id_allowed_by_policy(group_id, cf.group_list_type, cf.group_list)
        return self._id_allowed_by_policy(user_id, cf.private_list_type, cf.private_list)

    @staticmethod
    def _id_allowed_by_policy(
        target_id: str,
        list_type: str,
        configured_ids: Any,
    ) -> bool:
        """whitelist=在名单内才放行；blacklist=在名单内则丢弃。"""
        if list_type == "whitelist":
            return target_id in configured_ids
        return target_id not in configured_ids

    def _is_at_mentioned(self, raw_message: str, is_group: bool, **kwargs) -> bool:
        at_mode = self.config.at_mode
        if not at_mode.enabled:
            return True
        if not is_group and not at_mode.require_at_private:
            return True
        if is_group and not at_mode.require_at_group:
            return True

        # 方法1：从 message 字典检查 MaiBot SDK 内置 is_at / is_mentioned 字段
        msg_dict = kwargs.get("message", {})
        if isinstance(msg_dict, dict):
            if msg_dict.get("is_at") or msg_dict.get("is_mentioned"):
                return True

        # 方法2：检查顶层 kwargs（兼容 Tool 调用路径，NapCat 直接传 is_at/is_mentioned）
        if kwargs.get("is_at") or kwargs.get("is_mentioned"):
            return True

        # 方法3：字符串匹配 @bot_name 或 CQ:at / <@
        matched_text = raw_message or kwargs.get("text", "") or ""
        bot_name = at_mode.bot_name
        if bot_name and (
            f"@{bot_name}" in matched_text or matched_text.strip().startswith(bot_name)
        ):
            return True
        if "[CQ:at" in matched_text or "<@" in matched_text:
            return True

        # 方法4：Tool/LLM 调用路径 — kwargs 中没有 message 字典也没有文本
        # 说明是 LLM 发起的工具调用，@ 检测已由 Command 路径或 LLM 自身处理过
        if not kwargs.get("message") and not matched_text:
            return True

        return False

    def _check_access(self, kwargs: dict) -> str | None:
        """返回 None 表示放行；返回字符串表示拦截（空串=静默，非空=回复该文案）。"""
        if not self.config.plugin.enabled:
            return "插件总开关已关闭"
        if not self._is_chat_allowed(kwargs):
            self.ctx.logger.info("[SetuPlugin] 消息未通过聊天名单过滤，跳过发图")
            return self.config.chat_filter.reject_message
        _, _, is_group = self._extract_chat_context(kwargs)
        raw = (kwargs.get("raw_message", "") or kwargs.get("text", "") or "").strip()
        if not self._is_at_mentioned(raw, is_group, **kwargs):
            return self.config.at_mode.reject_message
        return None

    # ── 分类判定 ───────────────────────────────────────────────────────

    def _pick_category(self, msg_text: str) -> str | None:
        """根据消息文本判断要发哪个分类：nsfw / sfw / None。

        nsfw 优先（色图语义更明确）；分类被关闭则不匹配该分类。
        """
        send = self.config.send
        if send.nsfw_allowed and any(kw in msg_text for kw in send.nsfw_keywords):
            return "nsfw"
        if send.sfw_allowed and any(kw in msg_text for kw in send.sfw_keywords):
            return "sfw"
        return None

    def _category_sort(self, category: str) -> str:
        return self.config.api.nsfw_sort if category == "nsfw" else self.config.api.sfw_sort

    def _category_label(self, category: str) -> str:
        return "色图" if category == "nsfw" else "无色图"

    # ── 色图范围过滤（在全局 nsfw_allowed 之上按群/私聊细分）─────────────

    def _nsfw_allowed_for_chat(self, kwargs: dict) -> bool:
        """色图是否允许在当前会话发送。

        nsfw_filter.enabled=False 时恒返回 True（交给全局 nsfw_allowed）。
        """
        nf = self.config.nsfw_filter
        if not nf.enabled:
            return True
        group_id, _user_id, is_group = self._extract_chat_context(kwargs)
        if is_group:
            return self._id_allowed_by_policy(group_id, nf.group_list_type, nf.group_list)
        return nf.private_allowed

    def _resolve_nsfw(self, kwargs: dict, category: str) -> tuple[str | None, str | None]:
        """对色图请求做范围过滤 + 降级。

        返回 (最终category, 拒绝文案)：
        - category 不变：放行
        - 降级为 "sfw"：本会话不允许色图，自动改发无色图
        - (None, reject)：拒绝不发图；reject 为空串表示静默
        """
        if category != "nsfw":
            return category, None
        if self._nsfw_allowed_for_chat(kwargs):
            return "nsfw", None
        # 色图被拦截
        nf = self.config.nsfw_filter
        if nf.fallback_to_sfw and self.config.send.sfw_allowed:
            return "sfw", None  # 降级为无色图
        return None, nf.reject_message

    # ── 去重缓存 ───────────────────────────────────────────────────────

    def _is_recently_sent(self, url: str) -> bool:
        return url in self._sent_url_set

    def _remember_sent(self, url: str) -> None:
        if url in self._sent_url_set:
            return
        self._sent_url_set.add(url)
        self._sent_url_order.append(url)
        self._trim_sent_cache()

    def _trim_sent_cache(self) -> None:
        while len(self._sent_url_order) > self._sent_max:
            old = self._sent_url_order.popleft()
            self._sent_url_set.discard(old)

    # ── API & 下载 ─────────────────────────────────────────────────────

    async def _fetch_image_urls(self, sort_key: str, num: int) -> list[str]:
        """调用 cnmiw API 获取一批随机图片 URL。"""
        n = max(1, min(int(num), 100))
        params = {"sort": sort_key, "type": "json", "num": str(n)}
        try:
            async with httpx.AsyncClient(timeout=self.config.api.request_timeout) as client:
                resp = await client.get(self.config.api.base_url, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            self.ctx.logger.warning("[SetuPlugin] API 请求失败: %s", e)
            return []
        pics = data.get("pic") if isinstance(data, dict) else None
        if not isinstance(pics, list):
            return []
        return [u for u in pics if isinstance(u, str) and u]

    async def _fetch_fresh_urls(self, sort_key: str, count: int) -> list[str]:
        """获取去重后的 URL 列表，最多 count 个。

        启用去重时最多重试 2 轮跳过近期已发的 URL；若去重后一张都没有则
        退化为不去重再取一次，保证可用性。
        """
        if not self.config.send.dedup_enabled:
            batch = await self._fetch_image_urls(sort_key, count)
            # 同一批内去重保序
            seen: set[str] = set()
            uniq: list[str] = []
            for u in batch:
                if u not in seen:
                    seen.add(u)
                    uniq.append(u)
            return uniq[:count]

        collected: list[str] = []
        max_rounds = 2
        for _ in range(max_rounds):
            need = count - len(collected)
            if need <= 0:
                break
            batch = await self._fetch_image_urls(sort_key, need)
            if not batch:
                break
            for u in batch:
                if u in collected or self._is_recently_sent(u):
                    continue
                collected.append(u)
            if len(batch) < need:
                break  # API 没给够，再请求也无意义

        if not collected:
            # 去重太严一张没拿到，退化为不去重
            batch = await self._fetch_image_urls(sort_key, count)
            seen = set()
            for u in batch:
                if u not in seen:
                    seen.add(u)
                    collected.append(u)
        return collected[:count]

    async def _download_image(self, url: str) -> bytes | None:
        """下载图片原始字节，带 Referer（兼容 sinaimg 直链与 CDN）。"""
        headers = {"Referer": IMAGE_REFERER, "User-Agent": IMAGE_UA}
        try:
            async with httpx.AsyncClient(
                headers=headers,
                timeout=self.config.api.download_timeout,
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.content
                return data if data else None
        except Exception as e:
            self.ctx.logger.warning("[SetuPlugin] 下载失败 %s: %s", url, e)
            return None

    # ── 发送 ───────────────────────────────────────────────────────────

    async def _send_images(self, stream_id: str, category: str) -> str:
        """按分类取图并发送，返回简短描述（给日志用）。"""
        count = max(1, int(self.config.send.count))
        sort_key = self._category_sort(category)
        label = self._category_label(category)

        urls = await self._fetch_fresh_urls(sort_key, count)
        if not urls:
            await self.ctx.send.text(f"{label}接口暂时拉不到图，稍后再试试吧～", stream_id)
            return f"{label}取图失败"

        sent = 0
        for url in urls[:count]:
            data = await self._download_image(url)
            if not data:
                continue
            try:
                b64 = base64.b64encode(data).decode()
                if await self.ctx.send.image(b64, stream_id):
                    sent += 1
                    self._remember_sent(url)
                    self.ctx.logger.info(
                        "[SetuPlugin] 已发 %s (%.1fKB) %s",
                        label, len(data) / 1024, url,
                    )
                    await asyncio.sleep(0.5)
            except Exception as e:
                self.ctx.logger.error("[SetuPlugin] 发送失败 %s: %s", url, e)

        if sent == 0:
            await self.ctx.send.text(f"{label}图片下载失败了，稍后再试～", stream_id)
            return f"{label}发送失败"
        return f"发了 {sent} 张{label}"

    # ── @Tool：发图 ────────────────────────────────────────────────────

    @Tool(
        "send_setu",
        brief_description="仅响应明确随机图片请求，发送一张普通二次元图片",
        description="仅用户明确请求随机图、随便来张图或普通美图时调用；指定角色但未要求随机时先澄清。不是搜索引擎或画图工具。一次交付后停止，禁止重复调用。",
        detailed_description="仅使用category=sfw，从普通图库随机取图；不能保证特定角色。nsfw已禁用。",
        parameters=[
            ToolParameterInfo(
                name="category",
                param_type=ToolParamType.STRING,
                description="图片分类：nsfw=色图，sfw=无色图。不确定或用户没明说时用 sfw。",
                required=False,
            ),
        ],
    )
    async def handle_send_setu_tool(self, **kwargs) -> dict[str, Any]:
        if time.time() - self._last_send_time < self.config.send.cooldown_sec:
            return {"success": True, "content": "刚刚已触发发图，冷却中跳过"}
        error = self._check_access(kwargs)
        if error is not None:
            return {"success": False, "content": error}
        category = self._normalize_category(kwargs.get("category"))
        # 色图范围过滤 + 降级
        final_cat, reject = self._resolve_nsfw(kwargs, category)
        if final_cat is None:
            return {"success": False, "content": reject or "本会话不允许色图"}
        allow = self.config.send.nsfw_allowed if final_cat == "nsfw" else self.config.send.sfw_allowed
        if not allow:
            return {"success": False, "content": f"{self._category_label(final_cat)}功能已关闭"}
        try:
            request = await current_random_request(self, kwargs)
        except Exception:
            request = None
        if request is None:
            return {"success": False, "error_code": "local_intent_rejected", "retryable": False,
                    "content": "当前真实消息不是新的随机图片请求，或该请求已经处理。指定角色需先澄清，画图交vertex_draw；不要重复调用，也不要说接口坏了。"}
        self._last_send_time = time.time()
        msg = await self._send_images(kwargs.get("stream_id", ""), final_cat)
        return {"success": True, "content": msg}

    @staticmethod
    def _normalize_category(value: Any) -> str:
        v = str(value or "").strip().lower()
        if v in ("nsfw", "r18", "色图", "涩图", "瑟图", "setu"):
            return "nsfw"
        return "sfw"

    # ── @Command：发图关键词 ───────────────────────────────────────────

    @Command(
        "setu_cmd",
        description="当用户消息包含涩图/色图/来点图等关键词时直接触发随机发图",
        pattern=ROUTE_PATTERN,
        aliases=["来点图"],
    )
    async def handle_send_setu_command(self, **kwargs) -> tuple[bool, str, int]:
        stream_id = kwargs.get("stream_id", "")
        msg_text = kwargs.get("text", "") or kwargs.get("raw_message", "") or ""

        if image_intent(msg_text) != "random":
            return False, "", 0
        category = self._pick_category(msg_text)
        if category is None:
            # 路由命中但 config 关键词没匹配上（或该分类已关），不处理，放行给后续流程
            return False, "", 0

        # 冷却（仅在确定要发图时计冷却）
        if time.time() - self._last_send_time < self.config.send.cooldown_sec:
            return False, "冷却中", 0

        error = self._check_access(kwargs)
        if error is not None:
            if error:
                await self.ctx.send.text(error, stream_id)
                return True, error, 2  # 已回复拦截文案，拦截避免 AI 重复回复
            return False, "", 0  # 静默拦截，放行给 AI 自然处理

        # 色图范围过滤 + 降级（无色图请求不受影响）
        final_cat, reject = self._resolve_nsfw(kwargs, category)
        if final_cat is None:
            if reject:
                await self.ctx.send.text(reject, stream_id)
                return True, reject, 2
            return False, "", 0  # 静默不发

        try:
            request = await current_random_request(self, kwargs)
        except Exception:
            request = None
        if request is None:
            return True, "当前请求已处理或不是随机图片请求", 2
        self._last_send_time = time.time()
        msg = await self._send_images(stream_id, final_cat)
        return True, msg, 2


def create_plugin() -> PixivCrawlerPlugin:
    return PixivCrawlerPlugin()
