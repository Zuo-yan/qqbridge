from maibot_sdk import MaiBotPlugin, PluginConfigBase, Field, HookHandler
from maibot_sdk.types import HookMode, HookOrder, ErrorPolicy
from typing import List
from copy import deepcopy
from datetime import datetime
from uuid import uuid4


class PluginSection(PluginConfigBase):
    """私聊必回复插件设置"""
    __ui_label__ = "基础设置"

    config_version: str = Field(
        default="2.5.2",
        description="配置文件版本号",
    )

    enabled: bool = Field(
        default=True,
        description="是否启用私聊必回复功能",
    )

    whitelist_users: str = Field(
        default="",
        description="白名单用户 ID：只有这些用户在私聊时才能直接跳过时机模型，多个 ID 用英文逗号分隔，留空表示对所有私聊用户生效",
        json_schema_extra={"placeholder": "例如: 123456,789012"},
    )


class AlwaysReplyPrivateConfig(PluginConfigBase):
    """私聊必回复插件完整配置"""

    plugin: PluginSection = Field(default_factory=PluginSection)


class AlwaysReplyPrivatePlugin(MaiBotPlugin):
    config_model = AlwaysReplyPrivateConfig

    def __init__(self):
        super().__init__()
        # 记录已处理的消息 ID，防止重复处理
        self._processed_message_ids: set[str] = set()
        # 记录需要强制 Planner 回复的私聊会话 ID
        self._private_sessions: set[str] = set()

    async def on_load(self) -> None:
        self.ctx.logger.info("私聊必回复插件已加载")

    async def on_unload(self) -> None:
        self.ctx.logger.info("私聊必回复插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        self.ctx.logger.info("私聊必回复插件配置已更新")

    def _is_private_chat(self, message: dict) -> bool:
        """判断消息是否为私聊"""
        if message.get("is_private") is True:
            return True

        chat_type = (
            message.get("chat_type")
            or message.get("scene")
            or message.get("detail_type")
            or ""
        )
        if chat_type in ("private", "direct"):
            return True

        add_config = {}
        if "message_info" in message:
            add_config = message.get("message_info", {}).get("additional_config") or {}
        elif "additional_config" in message:
            add_config = message.get("additional_config") or {}

        napcat_type = (
            add_config.get("napcat_message_type")
            or add_config.get("napcat_notice_type")
            or ""
        )
        if napcat_type == "private":
            return True

        if add_config.get("platform_io_target_user_id") is not None and not message.get("group_id"):
            return True

        return False

    def _extract_user_id(self, message: dict) -> str:
        """从消息中提取用户 ID"""
        user_id = message.get("user_id") or ""
        if user_id:
            return str(user_id)

        msg_info = message.get("message_info") or {}
        user_info = msg_info.get("user_info") or {}
        if user_info:
            uid = user_info.get("user_id") or user_info.get("id")
            if uid:
                return str(uid)

        return ""

    def _parse_id_list(self, raw_str: str) -> List[str]:
        """解析逗号分隔的 ID 列表"""
        if not raw_str:
            return []
        return [item.strip() for item in raw_str.split(",") if item.strip()]

    def _should_force_timing_continue(self, message: dict) -> bool:
        """判断是否应该强制跳过时机模型"""
        # 检查是否启用
        if not self.config.plugin.enabled:
            return False

        # 检查是否为私聊
        if not self._is_private_chat(message):
            self.ctx.logger.debug("非私聊消息，不强制跳过时机模型")
            return False

        # 检查白名单
        whitelist = self._parse_id_list(self.config.plugin.whitelist_users)
        if whitelist:
            user_id = self._extract_user_id(message)
            if not user_id:
                self.ctx.logger.debug("无法提取用户 ID，不强制跳过时机模型")
                return False

            if user_id not in whitelist:
                self.ctx.logger.debug(f"用户 {user_id} 不在白名单中，不强制跳过时机模型")
                return False

            self.ctx.logger.info(f"用户 {user_id} 在白名单中，将强制跳过时机模型")
        else:
            self.ctx.logger.info("白名单为空，所有私聊用户将强制跳过时机模型")

        return True

    @HookHandler(
        "chat.receive.after_process",
        name="force_timing_continue_in_private",
        description="私聊环境下强制跳过时机模型，直接进入 Planner",
        mode=HookMode.BLOCKING,
        order=HookOrder.LATE,
        error_policy=ErrorPolicy.SKIP,
    )
    async def force_timing_continue_in_private(self, **kwargs):
        """在私聊环境下通过设置 is_mentioned 标志来强制跳过时机模型"""
        message = kwargs.get("message", {})
        if not message:
            return {"action": "continue", "modified_kwargs": kwargs}

        # Keep this private-chat plugin from aborting unrelated group notices.
        if not self.config.plugin.enabled or not self._is_private_chat(message):
            return {"action": "continue", "modified_kwargs": kwargs}

        # 获取消息 ID
        message_id = str(message.get("message_id", ""))

        # 中止通知消息，防止其进入聊天流程、中断 Planner 或污染上下文
        if message.get("is_notify", False):
            self.ctx.logger.debug(f"中止 is_notify 通知消息: {message_id}")
            return {"action": "abort", "modified_kwargs": kwargs}

        # 中止 NapCat 的各种通知事件（通过 message_id 判断）
        if message_id and any(keyword in message_id for keyword in [
            "napcat-notice",
            "input_status",
            "notify",
            "-notice-",
        ]):
            self.ctx.logger.debug(f"中止 NapCat 通知事件: {message_id}")
            return {"action": "abort", "modified_kwargs": kwargs}

        # 如果已经设置了 is_mentioned 或 is_at，不需要重复设置
        if message.get("is_mentioned", False) or message.get("is_at", False):
            self.ctx.logger.debug(f"消息已有标志，跳过: {message_id}")
            return {"action": "continue", "modified_kwargs": kwargs}

        if not self._should_force_timing_continue(message):
            return {"action": "continue", "modified_kwargs": kwargs}

        # 检查消息是否已处理，防止重复处理
        if message_id and message_id in self._processed_message_ids:
            self.ctx.logger.debug(f"消息 {message_id} 已处理，跳过重复设置")
            return {"action": "continue", "modified_kwargs": kwargs}

        # 设置 is_mentioned 标志，让 runtime 的 _update_message_trigger_state 自动设置强制跳过
        # 同时注入数值型 is_mentioned 到 additional_config，使 reply_probability_boost >= 1.0
        # 这样可以绕过 mentioned_bot_reply 配置开关（默认 False），在默认配置下也能强制触发
        message["is_mentioned"] = True
        msg_info = message.setdefault("message_info", {})
        add_cfg = msg_info.setdefault("additional_config", {})
        add_cfg["is_mentioned"] = 1.0
        kwargs["message"] = message

        # 记录会话 ID，用于在 Planner 请求前注入强制回复指令
        session_id = str(message.get("session_id", ""))
        if session_id:
            self._private_sessions.add(session_id)
            # 限制集合大小，防止内存泄漏
            if len(self._private_sessions) > 1000:
                to_remove = list(self._private_sessions)[:500]
                for sid in to_remove:
                    self._private_sessions.discard(sid)

        # 记录已处理的消息 ID
        if message_id:
            self._processed_message_ids.add(message_id)
            # 限制集合大小，防止内存泄漏
            if len(self._processed_message_ids) > 1000:
                # 移除最旧的一半
                to_remove = list(self._processed_message_ids)[:500]
                for mid in to_remove:
                    self._processed_message_ids.discard(mid)

        user_id = self._extract_user_id(message)
        self.ctx.logger.info(
            f"✓ 私聊消息设置 is_mentioned 标志: user_id={user_id}, "
            f"message_id={message.get('message_id', 'unknown')}"
        )

        return {"action": "continue", "modified_kwargs": kwargs}

    @HookHandler(
        "maisaka.planner.before_request",
        name="force_reply_in_private_planner",
        description="私聊环境下在 Planner 请求前注入强制回复指令，降低 Planner 选择 wait 或不调用 reply 的概率",
        mode=HookMode.BLOCKING,
        order=HookOrder.LATE,
        error_policy=ErrorPolicy.SKIP,
    )
    async def force_reply_in_private_planner(self, **kwargs):
        """Inject once per received private turn, preserving the complete Hook payload."""
        if not self.config.plugin.enabled:
            return {"action": "continue", "modified_kwargs": kwargs}
        session_id = str(kwargs.get("session_id", ""))
        if not session_id or session_id not in self._private_sessions:
            return {"action": "continue", "modified_kwargs": kwargs}

        marker = "【私聊回复提示】"
        prompt = (
            "【私聊回复提示】对尚未处理的直接提问、问候或交流，应调用 reply 回应，"
            "不要仅查询记忆后沉默。用户明确要求停止联系、不回复，或本轮已经回复、"
            "已有表情回应、工具已接单并负责通知时，允许 stop，不强制追加文字。"
            "不要重复回复同一条消息，不要把系统通知当成新提问。"
        )
        raw_items = kwargs.get("items")
        if isinstance(raw_items, list):
            if kwargs.get("item_schema_version") != 1:
                return {"action": "continue", "modified_kwargs": kwargs}
            items = deepcopy(raw_items)
            systems = [item for item in items if isinstance(item, dict) and item.get("item_type") == "SystemMessageItem"]
            if any(not isinstance(item.get("parts"), list) for item in systems):
                return {"action": "continue", "modified_kwargs": kwargs}
            already_present = any(
                isinstance(part, dict) and part.get("type") == "text"
                and str(part.get("text", "")).startswith(marker)
                for item in systems for part in item["parts"]
            )
            if not already_present:
                if systems:
                    systems[0]["parts"].append({"type": "text", "text": prompt})
                else:
                    items.insert(0, {
                        "item_type": "SystemMessageItem",
                        "meta": {"item_id": uuid4().hex, "logical_turn_id": None,
                                 "timestamp": datetime.now().astimezone().isoformat()},
                        "parts": [{"type": "text", "text": prompt}],
                    })
            kwargs["items"] = items
        elif raw_items is not None:
            return {"action": "continue", "modified_kwargs": kwargs}
        elif isinstance(kwargs.get("messages"), list):
            messages = deepcopy(kwargs["messages"])
            if not any(isinstance(item, dict) and item.get("role") == "system"
                       and isinstance(item.get("content"), str) and item["content"].startswith(marker)
                       for item in messages):
                messages.append({"role": "system", "content": prompt})
            kwargs["messages"] = messages
        else:
            return {"action": "continue", "modified_kwargs": kwargs}

        # Invalid/unsupported payloads above retain the pending turn for a valid retry.
        self._private_sessions.discard(session_id)
        self.ctx.logger.info(f"✓ 私聊会话注入强制回复指令: session_id={session_id}")
        return {"action": "continue", "modified_kwargs": kwargs}


def create_plugin():
    return AlwaysReplyPrivatePlugin()
