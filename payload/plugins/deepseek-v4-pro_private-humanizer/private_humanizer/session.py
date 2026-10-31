from __future__ import annotations

from typing import Any


class SessionTracker:
    def __init__(self) -> None:
        self._matched: dict[str, dict[str, Any]] = {}
        self._captured: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Capture (from receive hook, before matching)
    # ------------------------------------------------------------------

    def capture(self, session_id: str, **fields: Any) -> None:
        if not session_id:
            return
        entry = self._captured.get(session_id)
        if entry is None:
            self._captured[session_id] = dict(fields)
        else:
            entry.update({k: v for k, v in fields.items() if v})

    def confirm_target(self, session_id: str, **fields: Any) -> None:
        """将某个会话确认为目标用户私聊。

        只在 chat.receive 阶段拿到可靠 user_id 与群信息后调用。
        确认后的会话可被 Planner/Replyer 等只有 session_id 的 hook 直接命中。
        """
        if not session_id:
            return
        entry = self._matched.get(session_id)
        if entry is None:
            self._matched[session_id] = {"chat_type": "private"}
            entry = self._matched[session_id]
        entry.update({"chat_type": "private"})
        for key in ("platform", "user_id", "profile_id", "group_id"):
            value = fields.get(key)
            if value:
                entry[key] = value
        captured = self._captured.get(session_id)
        if captured is None:
            self._captured[session_id] = {}
            captured = self._captured[session_id]
        captured.update({"chat_type": "private"})
        for key in ("platform", "user_id", "group_id"):
            value = fields.get(key)
            if value:
                captured[key] = value

    def reject_group(self, session_id: str) -> None:
        """把会话标记/降级为群聊并清掉历史匹配缓存（去毒）。

        防止曾经被误判为私聊的群会话继续命中注入逻辑。
        """
        if not session_id:
            return
        self._matched.pop(session_id, None)
        captured = self._captured.get(session_id)
        if captured is None:
            self._captured[session_id] = {}
            captured = self._captured[session_id]
        captured["chat_type"] = "group"

    def get_captured(self, session_id: str) -> dict[str, Any]:
        return self._captured.get(session_id, {})

    def captured_session_ids(self) -> set[str]:
        return set(self._captured.keys())

    # ------------------------------------------------------------------
    # Match tracking
    # ------------------------------------------------------------------

    def mark_matched(self, session_id: str, **fields: Any) -> None:
        if not session_id:
            return
        entry = self._matched.get(session_id)
        if entry is None:
            self._matched[session_id] = dict(fields)
        else:
            entry.update({k: v for k, v in fields.items() if v})

    def is_matched(self, session_id: str) -> bool:
        return session_id in self._matched

    def get_match_info(self, session_id: str) -> dict[str, Any]:
        return self._matched.get(session_id, {})

    def matched_session_ids(self) -> set[str]:
        return set(self._matched.keys())

    def remove_matched(self, session_id: str) -> None:
        self._matched.pop(session_id, None)

    # ------------------------------------------------------------------
    # Bulk
    # ------------------------------------------------------------------

    def clear(self) -> None:
        self._matched.clear()
        self._captured.clear()
