from __future__ import annotations

PROMPT_MARKER = "[Private Humanizer 私聊增强约束]"
PLANNER_MARKER = "[Private Humanizer 规划注入]"

FOLLOWUP_LOG_WINDOW_SECONDS = 3600

INTIMATE_FOLLOWUP_INTENT = (
    "这是私聊增强插件发起的主动续话检查。最近上下文已经由用户明确开启亲密/暧昧话题；"
    "请只判断是否需要像真实私聊一样自然补一句很短的话。"
    "如果要发，承接刚才的亲密情绪和关系感，可以更主动一点，1-2句话即可，每句不超过30字；"
    "先承接感受再回应内容，不要突然转去吃饭、天气、工作或日程等无关话题；"
    "不要机械复述刚才的话，不要解释插件，不要编造未确认事实。"
    "如果刚才已经自然收束、对方明显转场、或自你上条回复后对方没有新的回应，就不要发。"
)

PRIVATE_HINTS = frozenset({"private", "friend", "direct", "dm", "单聊", "私聊", "person"})
GROUP_HINTS = frozenset({"group", "guild", "channel", "群聊", "群"})

GROUP_KEY_HINTS = frozenset({"group_id", "guild_id", "channel_id"})
GROUP_TEXT_SIGNALS = ("group_id=", "qq_group_", "群聊", "频道", "guild_id", "channel_id")

# 会话 ID 形态识别：MaiBot 的 stream/session id 直接编码聊天类型。
# 群聊形如 qq_group_1049246517，私聊形如 qq_private_3130274394。
GROUP_SESSION_PREFIXES = ("qq_group_", "group_", "guild_", "channel_")
PRIVATE_SESSION_PREFIXES = ("qq_private_", "private_", "dm_", "friend_")

FIELD_SEARCH_ORDER = (
    "user_id", "sender_id", "from_user_id", "person_id", "target_user_id",
)
SESSION_SEARCH_ORDER = (
    "session_id", "chat_id", "stream_id", "conversation_id",
)
PLATFORM_SEARCH_ORDER = (
    "platform", "adapter", "platform_name",
)
CHAT_TYPE_SEARCH_ORDER = (
    "chat_type", "message_type", "conversation_type",
)
GROUP_ID_SEARCH_ORDER = (
    "group_id", "guild_id", "channel_id",
)

NESTED_CONTAINER_KEYS = (
    "message", "target_message", "chat_info", "session", "metadata", "event", "reply_tool_args",
)
