from __future__ import annotations

from typing import Any

from .constants import (
    CHAT_TYPE_SEARCH_ORDER,
    GROUP_HINTS,
    GROUP_ID_SEARCH_ORDER,
    GROUP_KEY_HINTS,
    GROUP_SESSION_PREFIXES,
    NESTED_CONTAINER_KEYS,
    PLATFORM_SEARCH_ORDER,
    PRIVATE_HINTS,
    PRIVATE_SESSION_PREFIXES,
    SESSION_SEARCH_ORDER,
    FIELD_SEARCH_ORDER,
)


def classify_session_id(session_id: str) -> str:
    """根据会话 ID 形态判断聊天类型：group / private / ""（未知）。

    MaiBot 的 stream/session id 自带类型前缀：
    - 群聊：qq_group_1049246517
    - 私聊：qq_private_3130274394
    """
    sid = str(session_id or "").strip().lower()
    if not sid:
        return ""
    if sid.startswith(GROUP_SESSION_PREFIXES) or "_group_" in sid:
        return "group"
    if sid.startswith(PRIVATE_SESSION_PREFIXES):
        return "private"
    # 兼容历史形态：qq_<纯数字> 视为私聊
    if sid.startswith("qq_") and sid[3:].isdigit():
        return "private"
    return ""


def chat_type_from_message(message: dict[str, Any]) -> str:
    """从 chat.receive 的序列化 SessionMessage 推导聊天类型。

    优先看 message_info.group_info 是否为空，其次看 session_id 形态。
    入站消息里没有 chat_type 字段，必须按群信息/会话 ID 推导。
    """
    if not isinstance(message, dict):
        return ""
    message_info = message.get("message_info") or {}
    if isinstance(message_info, dict) and message_info.get("group_info"):
        return "group"
    derived = classify_session_id(str(message.get("session_id", "") or ""))
    if derived:
        return derived
    # 无群信息且会话形态未知时，入站阶段按私聊处理（与主程序 is_group 判定一致）
    return "private"


def extract_chat_fields(kwargs: dict[str, Any]) -> dict[str, str]:
    candidates: list[dict[str, Any]] = [kwargs]
    for key in NESTED_CONTAINER_KEYS:
        value = kwargs.get(key)
        if isinstance(value, dict):
            candidates.append(value)

    messages = kwargs.get("messages")
    if isinstance(messages, list):
        for msg in messages:
            if isinstance(msg, dict):
                candidates.append(msg)

    def first(*names: str) -> str:
        for source in candidates:
            for name in names:
                value = source.get(name)
                if value is not None and str(value).strip():
                    return str(value).strip()
        return ""

    chat_type = first(*CHAT_TYPE_SEARCH_ORDER).lower()
    if not chat_type:
        session_id = first(*SESSION_SEARCH_ORDER)
        chat_type = classify_session_id(session_id)

    return {
        "platform": first(*PLATFORM_SEARCH_ORDER),
        "user_id": first(*FIELD_SEARCH_ORDER),
        "session_id": first(*SESSION_SEARCH_ORDER),
        "group_id": first(*GROUP_ID_SEARCH_ORDER),
        "chat_type": chat_type,
    }


def extract_last_user_message(messages: Any, limit: int = 500) -> str:
    """从模型消息列表里取最近一条 user 消息文本。

    after_response 等 hook 的 kwargs 里没有用户消息，回复守卫/主动续话
    需要依赖 before_model_request 阶段缓存下来的最近用户发言。
    兼容两类载荷：旧版 {"role": "user", "content": ...}，以及新版 MaiBot
    ContextItem 快照 {"item_type": "UserMessageItem", "parts": [...]}。
    """
    if not isinstance(messages, list):
        return ""

    def content_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    for key in ("text", "content", "content_text"):
                        value = item.get(key)
                        if isinstance(value, str) and value.strip():
                            parts.append(value)
                            break
            return "\n".join(parts)
        return ""

    def item_text(item: dict[str, Any]) -> str:
        texts: list[str] = []
        parts = item.get("parts")
        if isinstance(parts, list):
            for part in parts:
                if isinstance(part, dict) and str(part.get("type", "")).lower() == "text":
                    text = part.get("text")
                    if isinstance(text, str) and text.strip():
                        texts.append(text.strip())
        return "\n".join(texts)

    for item in reversed(messages):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").lower()
        item_type = str(item.get("item_type") or "")
        if role != "user" and item_type != "UserMessageItem":
            continue
        if item_type == "UserMessageItem":
            text = item_text(item)
        else:
            text = content_text(item.get("content") or item.get("content_text") or "")
        text = text.strip()
        if text:
            return text[:limit]
    return ""


def extract_message_text(messages: Any) -> str:
    """从消息列表提取全部纯文本，兼容旧版与新版两种载荷。

    旧版：{"role": ..., "content": ...} 字典列表；
    新版（MaiBot 1.2.x）：ContextItem 快照 {"item_type": ..., "parts": [...]}。
    用于匹配兜底等只需要“看文本”的场景。
    """

    if not isinstance(messages, list):
        return ""
    texts: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("item_type"):
            parts = message.get("parts")
            if not isinstance(parts, list):
                continue
            for part in parts:
                if isinstance(part, dict) and str(part.get("type", "")).lower() == "text":
                    text = part.get("text")
                    if isinstance(text, str) and text.strip():
                        texts.append(text.strip())
        else:
            content = message.get("content_text") or message.get("content") or ""
            if isinstance(content, str) and content.strip():
                texts.append(content.strip())
    return "\n".join(texts)


def has_group_id(fields: dict[str, str]) -> bool:
    return bool(fields.get("group_id", ""))


def has_group_keywords(text: str) -> bool:
    from .constants import GROUP_TEXT_SIGNALS
    return any(signal in text for signal in GROUP_TEXT_SIGNALS)


def classify_chat_type(fields: dict[str, str]) -> str:
    chat_type = fields.get("chat_type", "").lower()
    if chat_type in PRIVATE_HINTS:
        return "private"
    if chat_type in GROUP_HINTS:
        return "group"
    if has_group_id(fields):
        return "group"
    return ""


def is_definitely_private(fields: dict[str, str]) -> bool:
    chat_type = fields.get("chat_type", "").lower()
    if chat_type in PRIVATE_HINTS:
        return True
    if classify_session_id(fields.get("session_id", "")) == "private":
        return True
    return False


def is_definitely_group(fields: dict[str, str]) -> bool:
    chat_type = fields.get("chat_type", "").lower()
    if chat_type in GROUP_HINTS:
        return True
    if has_group_id(fields):
        return True
    if classify_session_id(fields.get("session_id", "")) == "group":
        return True
    return False
