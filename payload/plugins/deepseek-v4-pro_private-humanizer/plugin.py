from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PLUGIN_DIR = Path(__file__).resolve().parent
PLUGIN_DIR_TEXT = str(PLUGIN_DIR)
if PLUGIN_DIR_TEXT not in sys.path:
    sys.path.insert(0, PLUGIN_DIR_TEXT)

from maibot_sdk import HookHandler, MaiBotPlugin
from maibot_sdk.types import ErrorPolicy, HookMode, HookOrder

from private_humanizer.audit import write_audit
from private_humanizer.config import (
    HumanizerConfig,
    PrivateHumanizerRuntimeConfig,
    load_config,
)
from private_humanizer.constants import PLANNER_MARKER, PROMPT_MARKER
from private_humanizer.context import (
    chat_type_from_message,
    extract_chat_fields,
    extract_last_user_message,
)
from private_humanizer.followup import FollowupManager
from private_humanizer.guards import guard_memory_items, guard_reply_text
from private_humanizer.matching import Matcher
from private_humanizer.prompting import (
    append_extra_prompt,
    build_humanizer_prompt,
    build_planner_prompt,
)
from private_humanizer.session import SessionTracker


class PrivateHumanizerPlugin(MaiBotPlugin):
    config_model = PrivateHumanizerRuntimeConfig

    def __init__(self) -> None:
        super().__init__()
        self._sessions = SessionTracker()
        self._matcher: Matcher | None = None
        self._followup: FollowupManager | None = None
        self._context_snapshots: dict[str, str] = {}

    # =========================================================================
    # Helpers
    # =========================================================================

    def _config(self) -> HumanizerConfig:
        return load_config(self._raw_config_data())

    def _raw_config_data(self) -> dict[str, Any]:
        if hasattr(self, "get_plugin_config_data"):
            try:
                data = self.get_plugin_config_data()
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        config = getattr(self, "config", None)
        if config is None:
            return {}
        if isinstance(config, dict):
            return config
        if hasattr(config, "model_dump"):
            return config.model_dump()
        if hasattr(config, "dict"):
            return config.dict()
        return self._object_to_dict(config)

    def _object_to_dict(self, value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, list):
            return [self._object_to_dict(item) for item in value]
        if isinstance(value, tuple):
            return [self._object_to_dict(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._object_to_dict(item) for key, item in value.items()}
        raw = getattr(value, "__dict__", {})
        return {
            key: self._object_to_dict(item)
            for key, item in raw.items()
            if not key.startswith("_")
        }

    def _matcher_ref(self) -> Matcher:
        if self._matcher is None:
            self._matcher = Matcher(self._config(), self._sessions, logger=self.ctx.logger)
        return self._matcher

    def _followup_ref(self) -> FollowupManager:
        if self._followup is None:
            self._followup = FollowupManager(self.ctx.maisaka.proactive.trigger)
        return self._followup

    def _audit(self, record: dict[str, Any], enabled: bool = True) -> None:
        config = self._config()
        write_audit(PLUGIN_DIR, enabled and config.logging.enabled, record, config.time_awareness.timezone)

    def _continue(self, modified_kwargs: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"action": "continue"}
        if modified_kwargs is not None:
            payload["modified_kwargs"] = modified_kwargs
        return payload

    @staticmethod
    def _merge_kwargs(kwargs: dict[str, Any], modified: dict[str, Any]) -> dict[str, Any]:
        """宿主用 modified_kwargs 整体替换 kwargs，而不是合并。

        返回时必须保留原始 kwargs 的全部键，否则 session_id / tool_definitions /
        reply_tool_args 等会在同 hook 的后续处理器（含其他插件）里丢失。
        """
        merged = dict(kwargs)
        merged.update(modified)
        return merged

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def on_load(self) -> None:
        config = self._config()
        self.ctx.logger.info(
            "Private Humanizer loaded: enabled=%s target_profiles=%d target_user_ids=%d",
            config.plugin.enabled,
            len(config.target_profiles),
            len(config.plugin.target_user_ids),
        )

    async def on_unload(self) -> None:
        self._followup_ref().clear()
        self.ctx.logger.info("Private Humanizer unloaded")

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        self._sessions.clear()
        self._followup_ref().clear()
        self._matcher = None
        self._context_snapshots.clear()
        self.ctx.logger.info("Private Humanizer config updated: scope=%s version=%s", scope, version)

    def _remember_context(self, session_id: str, messages: Any) -> None:
        if not session_id:
            return
        text = extract_last_user_message(messages)
        if text:
            self._context_snapshots[session_id] = text
        else:
            self._context_snapshots.pop(session_id, None)

    # =========================================================================
    # Session capture hooks (EARLY — run before other hooks consume kwargs)
    # =========================================================================

    def _is_target_user(self, user_id: str) -> bool:
        if not user_id:
            return False
        config = self._config()
        if user_id in config.plugin.target_user_ids:
            return True
        return any(profile.user_id == user_id for profile in config.target_profiles)

    @HookHandler(
        "chat.receive.after_process",
        name="private_humanizer_capture_receive",
        description="[1/3] Capture session_id and chat_type from incoming message.",
        mode=HookMode.BLOCKING,
        order=HookOrder.EARLY,
        error_policy=ErrorPolicy.SKIP,
    )
    async def capture_receive(self, message: Any = None, **kwargs: Any):
        if isinstance(message, dict):
            sid = str(message.get("session_id", "") or "")
            if not sid:
                mi = message.get("message_info", {}) or {}
                if isinstance(mi, dict):
                    ac = mi.get("additional_config", {}) or {}
                    if isinstance(ac, dict):
                        sid = str(ac.get("session_id", "") or ac.get("stream_id", "") or "")
            if sid:
                message_info = message.get("message_info", {}) or {}
                user_info = message_info.get("user_info", {}) or {}
                group_info = message_info.get("group_info", {}) or {}
                user_id = str(user_info.get("user_id", "") or "") if isinstance(user_info, dict) else ""
                group_id = str(group_info.get("group_id", "") or "") if isinstance(group_info, dict) else ""
                platform = str(message.get("platform", "") or "")
                chat_type = chat_type_from_message(message)

                if chat_type == "group":
                    # 群消息：清掉该会话的历史匹配缓存，防止曾经误判的缓存继续注入。
                    self._sessions.reject_group(sid)
                    self.ctx.logger.debug(
                        "captured group session=%s group_id=%s", sid, group_id or "(empty)",
                    )
                else:
                    self._sessions.capture(
                        sid,
                        chat_type="private",
                        platform=platform,
                        user_id=user_id,
                        group_id="",
                    )
                    if self._is_target_user(user_id):
                        self._sessions.confirm_target(
                            sid,
                            platform=platform,
                            user_id=user_id,
                        )
                        self.ctx.logger.info(
                            "confirmed target private session=%s user=%s", sid, user_id,
                        )
                    else:
                        self.ctx.logger.debug(
                            "captured private session=%s user=%s", sid, user_id or "(unknown)",
                        )
        return {"action": "continue"}

    @HookHandler(
        "maisaka.replyer.before_request",
        name="private_humanizer_capture_before_req",
        description="[2/3] Capture session_id from before_request kwargs.",
        mode=HookMode.BLOCKING,
        order=HookOrder.EARLY,
        error_policy=ErrorPolicy.SKIP,
    )
    async def capture_before_request(self, **kwargs):
        sid = str(kwargs.get("session_id", "") or kwargs.get("stream_id", "") or "")
        if sid:
            self._sessions.capture(sid)
        return {"action": "continue"}

    @HookHandler(
        "maisaka.replyer.before_model_request",
        name="private_humanizer_capture_before_model",
        description="[3/3] Capture session_id from before_model_request kwargs.",
        mode=HookMode.BLOCKING,
        order=HookOrder.EARLY,
        error_policy=ErrorPolicy.SKIP,
    )
    async def capture_before_model(self, **kwargs):
        sid = str(kwargs.get("session_id", "") or kwargs.get("stream_id", "") or "")
        if sid:
            self._sessions.capture(sid)
        return {"action": "continue"}

    # =========================================================================
    # Prompt injection — Planner
    # =========================================================================

    @HookHandler(
        "maisaka.planner.before_request",
        name="private_humanizer_planner_prompt",
        description="Inject compact profile into Planner messages.",
        mode=HookMode.BLOCKING,
        order=HookOrder.EARLY,
        error_policy=ErrorPolicy.SKIP,
    )
    async def inject_planner_prompt(self, **kwargs):
        config = self._config()
        if not config.schedule.inject_into_planner:
            return self._continue()

        fields = extract_chat_fields(kwargs)
        sid = fields.get("session_id", "")
        if not sid or not self._sessions.is_matched(sid):
            return self._continue()

        match_info = self._sessions.get_match_info(sid)
        if match_info.get("chat_type") == "group":
            return self._continue()

        match = self._matcher_ref().match(kwargs, config)
        if not match.matched:
            return self._continue()

        prompt = build_planner_prompt(config, match.profile)
        modified: dict[str, Any] = {}

        # v1.2.x+：宿主只认 ContextItem 快照（items 载荷），直接注入其中。
        raw_items = self._find_items(kwargs)
        items = self._inject_items(raw_items, prompt, PLANNER_MARKER) if raw_items is not None else None
        if items is not None:
            modified["items"] = items

        # 旧版宿主兼容：messages 路径。
        raw = self._find_messages(kwargs)
        messages = self._inject_prompt(match.profile, raw, prompt) if raw is not None else None
        if messages is not None:
            modified["messages"] = messages

        if not modified:
            return self._continue()
        self._audit({"stage": "planner_prompt", "chat_id": match.session_id, "user_id": match.user_id})
        return self._continue(self._merge_kwargs(kwargs, modified))

    # =========================================================================
    # Prompt injection — Replyer (tracking + model prompt)
    # =========================================================================

    @HookHandler(
        "maisaka.replyer.before_request",
        name="private_humanizer_replyer_prompt",
        description="Match and track private chat session before replyer builds request.",
        mode=HookMode.BLOCKING,
        order=HookOrder.NORMAL,
        error_policy=ErrorPolicy.SKIP,
    )
    async def inject_replyer_prompt(self, **kwargs):
        config = self._config()
        if not config.schedule.inject_into_replyer:
            return self._continue()

        match = self._matcher_ref().match(kwargs, config)
        if not match.matched:
            return self._continue()

        # v1.2.x+：before_request 是宿主唯一消费 extra_prompt 的位置
        # （会拼进“【额外回复要求】”并追加到请求），作为 items 注入的备份路径。
        modified: dict[str, Any] = {}
        extra = kwargs.get("extra_prompt", "")
        if isinstance(extra, str):
            prompt = build_humanizer_prompt(config, match.profile)
            modified["extra_prompt"] = append_extra_prompt({"extra_prompt": extra}, prompt)["extra_prompt"]

        self._audit({"stage": "replyer_prompt", "chat_id": match.session_id, "user_id": match.user_id})
        return self._continue(self._merge_kwargs(kwargs, modified))

    @HookHandler(
        "maisaka.replyer.before_model_request",
        name="private_humanizer_replyer_model_prompt",
        description="Inject private-chat constraints into final replyer model messages.",
        mode=HookMode.BLOCKING,
        order=HookOrder.NORMAL,
        error_policy=ErrorPolicy.SKIP,
    )
    async def inject_replyer_model_prompt(self, **kwargs):
        config = self._config()
        if not config.schedule.inject_into_replyer:
            return self._continue()

        match = self._matcher_ref().match(kwargs, config)
        if not match.matched:
            return self._continue()

        prompt = build_humanizer_prompt(config, match.profile)
        modified: dict[str, Any] = {}

        # v1.2.x+：宿主只认 items（ContextItem 快照），注入 system item 的 parts。
        raw_items = self._find_items(kwargs)
        items = self._inject_items(raw_items, prompt, PROMPT_MARKER) if raw_items is not None else None
        if items is not None:
            modified["items"] = items

        # 旧版宿主兼容：messages 路径。
        raw = self._find_messages(kwargs)
        messages = self._inject_prompt(match.profile, raw, prompt) if raw is not None else None
        if messages is not None:
            modified["messages"] = messages
            if isinstance(raw, list):
                raw.clear()
                raw.extend(messages)

        extra = kwargs.get("extra_prompt", "")
        if isinstance(extra, str):
            modified["extra_prompt"] = append_extra_prompt({"extra_prompt": extra}, prompt)["extra_prompt"]

        context_source = raw_items if raw_items is not None else raw
        self._remember_context(match.session_id, context_source)
        if not modified:
            return self._continue()

        self._audit({"stage": "replyer_model_prompt", "chat_id": match.session_id, "user_id": match.user_id})
        return self._continue(self._merge_kwargs(kwargs, modified))

    # =========================================================================
    # Reply guard
    # =========================================================================

    @HookHandler(
        "maisaka.replyer.after_response",
        name="private_humanizer_reply_guard",
        description="Rewrite unsupported facts, anniversary guesses, or over-novelistic replies.",
        mode=HookMode.BLOCKING,
        order=HookOrder.NORMAL,
        error_policy=ErrorPolicy.SKIP,
    )
    async def guard_reply(self, **kwargs):
        config = self._config()
        match = self._matcher_ref().match(kwargs, config)
        if not match.matched:
            return self._continue()

        path, text = self._find_reply_text(kwargs)
        if not text:
            return self._continue()

        context_text = self._collect_context_text(kwargs)
        if not context_text:
            context_text = self._context_snapshots.get(match.session_id, "")
        result = guard_reply_text(text, config, match.profile, context_text=context_text)
        final_text = result.text if result.changed else text

        self._followup_ref().schedule_if_needed(
            kwargs, config, match, final_text, context_text,
            audit_fn=lambda r: self._audit(r, enabled=config.logging.save_rewrite_pairs),
        )

        if result.changed:
            modified_kwargs: dict[str, Any] = {}
            target: dict[str, Any] = modified_kwargs
            for key in path[:-1]:
                target[key] = {}
                target = target[key]
            target[path[-1]] = result.text
            self._audit(
                {
                    "stage": "reply_guard",
                    "chat_id": match.session_id,
                    "user_id": match.user_id,
                    "risk_type": ",".join(result.risk_types),
                    "original_reply": text,
                    "rewritten_reply": result.text,
                    "evidence": result.evidence,
                },
                enabled=config.logging.save_rewrite_pairs,
            )
            return self._continue(self._merge_kwargs(kwargs, modified_kwargs))
        return self._continue()

    # =========================================================================
    # Memory guard
    # =========================================================================

    @HookHandler(
        "expression.learn.before_upsert",
        name="private_humanizer_memory_guard",
        description="Block suspicious self-created personal facts before upsert.",
        mode=HookMode.BLOCKING,
        order=HookOrder.EARLY,
        error_policy=ErrorPolicy.SKIP,
    )
    async def guard_expression_memory(self, **kwargs):
        config = self._config()
        match = self._matcher_ref().match(kwargs, config)
        if not match.matched or not config.guard.memory_guard_enabled:
            return self._continue()

        # 本版 MaiBot 的 expression.learn.before_upsert 载荷是
        # session_id / situation / style（字符串），不是 items/expressions 列表。
        situation = str(kwargs.get("situation", "") or "")
        style = str(kwargs.get("style", "") or "")
        blocked: list[str] = []
        if situation:
            _, blocked_situation = guard_memory_items(situation, config)
            blocked.extend(blocked_situation)
        if style:
            _, blocked_style = guard_memory_items(style, config)
            blocked.extend(blocked_style)
        if not blocked:
            return self._continue()

        self._audit({
            "stage": "memory_guard",
            "chat_id": match.session_id,
            "user_id": match.user_id,
            "risk_type": "unverified_memory",
            "blocked": blocked,
        })
        return {"action": "abort"}

    @HookHandler(
        "expression.learn.after_extract",
        name="private_humanizer_memory_extract_filter",
        description="Filter suspicious self-created facts from expression learning candidates.",
        mode=HookMode.BLOCKING,
        order=HookOrder.EARLY,
        error_policy=ErrorPolicy.SKIP,
    )
    async def filter_extracted_memory(self, **kwargs):
        config = self._config()
        if not config.guard.memory_guard_enabled:
            return self._continue()

        match = self._matcher_ref().match(kwargs, config)
        if not match.matched:
            return self._continue()

        expressions = kwargs.get("expressions")
        if not isinstance(expressions, list) or not expressions:
            return self._continue()

        kept: list[dict[str, Any]] = []
        blocked: list[str] = []
        for item in expressions:
            if not isinstance(item, dict):
                kept.append(item)
                continue
            situation = str(item.get("situation") or "")
            style = str(item.get("style") or "")
            _, situation_blocked = guard_memory_items(situation, config)
            _, style_blocked = guard_memory_items(style, config)
            if situation_blocked or style_blocked:
                blocked.append(situation or style)
                continue
            kept.append(item)

        if not blocked:
            return self._continue()

        self._audit({
            "stage": "memory_guard",
            "chat_id": match.session_id,
            "user_id": match.user_id,
            "risk_type": "unverified_memory",
            "blocked": blocked,
        })
        return self._continue(self._merge_kwargs(kwargs, {"expressions": kept}))

    # =========================================================================
    # Internal utilities
    # =========================================================================

    def _inject_prompt(self, profile: Any, messages: Any, prompt: str) -> list[dict[str, Any]] | None:
        if not isinstance(messages, list):
            return None
        updated: list[dict[str, Any]] = []
        inserted = False
        for item in messages:
            if not isinstance(item, dict):
                updated.append(item)
                continue
            message = dict(item)
            role = str(message.get("role") or "").lower()
            content = str(message.get("content") or message.get("content_text") or "")
            if role == "system" and not inserted:
                if PROMPT_MARKER not in content:
                    message["content"] = f"{content.rstrip()}\n\n{prompt}" if content.strip() else prompt
                    message["content_text"] = message["content"]
                inserted = True
            updated.append(message)
        if not inserted:
            updated.insert(0, {"role": "system", "content": prompt, "content_text": prompt})
        return updated

    @staticmethod
    def _find_items(kwargs: dict[str, Any]) -> list[Any] | None:
        """新版 MaiBot（≥1.2.x）的 ContextItem 快照载荷。"""

        value = kwargs.get("items")
        if isinstance(value, list):
            return value
        return None

    @staticmethod
    def _inject_items(items: Any, prompt: str, marker: str) -> list[dict[str, Any]] | None:
        """向 ContextItem 快照列表注入提示词（v1.2.x+ items 载荷）。

        新版载荷元素形如 {"item_type": "SystemMessageItem", "meta": {...}, "parts": [...]}，
        宿主通过 deserialize_prompt_items 恢复。优先把提示词追加到已有 system item 的
        parts（保持单条系统消息），没有 system item 时在头部插入新的 SystemMessageItem。
        marker 已存在时视为已注入，保持幂等。
        """

        if not isinstance(items, list):
            return None
        updated: list[dict[str, Any]] = []
        injected = False
        for item in items:
            if not injected and isinstance(item, dict) and item.get("item_type") == "SystemMessageItem":
                parts = item.get("parts")
                if isinstance(parts, list):
                    texts = [
                        str(part.get("text", ""))
                        for part in parts
                        if isinstance(part, dict) and str(part.get("type", "")).lower() == "text"
                    ]
                    if any(marker in text for text in texts):
                        injected = True
                    else:
                        item = dict(item)
                        item["parts"] = [*parts, {"type": "text", "text": prompt}]
                        injected = True
            updated.append(item)
        if not injected:
            updated.insert(
                0,
                {
                    "item_type": "SystemMessageItem",
                    "meta": {
                        "item_id": uuid.uuid4().hex,
                        "logical_turn_id": None,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                    "parts": [{"type": "text", "text": prompt}],
                },
            )
        return updated

    def _find_messages(self, kwargs: dict[str, Any]) -> list[Any] | None:
        for key in ("messages", "message_list", "conversation_messages", "chat_messages", "prompt_messages"):
            value = kwargs.get(key)
            if isinstance(value, list):
                return value
        for key, value in kwargs.items():
            if isinstance(value, list) and len(value) > 0:
                if any(isinstance(item, dict) and ("role" in item or "content" in item) for item in value):
                    return value
        return None

    def _find_reply_text(self, data: dict[str, Any]) -> tuple[list[Any], str]:
        direct_keys = ("response", "reply", "content", "text", "message", "result")
        for key in direct_keys:
            value = data.get(key)
            if isinstance(value, str):
                return [key], value
            if isinstance(value, dict):
                nested_path, nested_text = self._find_reply_text(value)
                if nested_text:
                    return [key, *nested_path], nested_text
        return [], ""

    def _collect_context_text(self, kwargs: dict[str, Any]) -> str:
        texts: list[str] = []

        def add_text(value: Any) -> None:
            if isinstance(value, str) and value.strip():
                texts.append(value.strip()[:240])

        def visit(value: Any, depth: int = 0) -> None:
            if value is None or depth > 3 or len(texts) >= 12:
                return
            if isinstance(value, str):
                add_text(value)
                return
            if isinstance(value, dict):
                for key in (
                    "processed_plain_text", "plain_text", "content", "content_text",
                    "text", "target_message_content", "last_user_message", "reply_reason",
                ):
                    add_text(value.get(key))
                for key in ("message", "target_message", "reply_message", "metadata", "reply_tool_args"):
                    if key in value:
                        visit(value[key], depth + 1)
                return
            if isinstance(value, (list, tuple)):
                for item in value[-8:]:
                    visit(item, depth + 1)

        for key in (
            "message", "target_message", "reply_message", "chat_history",
            "messages", "items", "metadata", "reply_tool_args", "reply_reason",
        ):
            visit(kwargs.get(key))
        return "\n".join(dict.fromkeys(texts))


def create_plugin():
    return PrivateHumanizerPlugin()
