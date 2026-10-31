from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .config import HumanizerConfig, TargetProfile
from .constants import GROUP_TEXT_SIGNALS
from .context import (
    classify_session_id,
    extract_chat_fields,
    extract_message_text,
    has_group_keywords,
    is_definitely_group,
    is_definitely_private,
)
from .session import SessionTracker


_logger = logging.getLogger("private_humanizer.matching")


@dataclass(slots=True)
class MatchResult:
    matched: bool
    profile: TargetProfile | None = None
    reason: str = ""
    platform: str = ""
    user_id: str = ""
    session_id: str = ""
    group_id: str = ""
    chat_type: str = ""


class Matcher:
    def __init__(self, config: HumanizerConfig, session_tracker: SessionTracker, logger: Any = None) -> None:
        self._config = config
        self._sessions = session_tracker
        self._logger = logger or _logger

    # =========================================================================
    # Public entry
    # =========================================================================

    def match(self, kwargs: dict[str, Any], config: HumanizerConfig | None = None) -> MatchResult:
        cfg = config or self._config

        if not cfg.plugin.enabled:
            return MatchResult(False, reason="plugin disabled")

        fields = extract_chat_fields(kwargs)
        session_id = fields.get("session_id", "")

        # 群聊硬拦截：无论缓存/提示词兜底是否命中，群会话一律不注入。
        # 这一步必须在任何缓存与提示词匹配之前执行，防止历史脏缓存再次泄露。
        if is_definitely_group(fields):
            if session_id:
                self._sessions.reject_group(session_id)
                self._logger.info("match hard-reject group session=%s", session_id)
            return MatchResult(False, reason="not private chat", **fields)

        result = self._match_by_fields(kwargs, cfg)
        if result.matched:
            self._sessions.confirm_target(
                result.session_id,
                platform=result.platform,
                user_id=result.user_id,
                chat_type=result.chat_type or "private",
            )
            self._logger.info("match_by_fields OK: %s (session=%s)", result.reason, result.session_id)
            return result

        if result.reason == "platform mismatch":
            self._logger.debug("match_by_fields early reject: %s", result.reason)
            return result

        result = self._match_by_session(kwargs, cfg)
        if result.matched:
            self._logger.info("match_by_session OK: session=%s", result.session_id)
            return result

        result = self._match_by_prompt(kwargs, cfg)
        if result.matched:
            self._logger.info("match_by_prompt OK: session=%s", result.session_id)
            self._sessions.confirm_target(
                result.session_id,
                platform=result.platform,
                user_id=result.user_id,
                chat_type="private",
            )
        else:
            self._logger.debug("no match (reason=%s)", result.reason)
        return result

    # =========================================================================
    # Strategy 1 — direct field matching
    # =========================================================================

    def _match_by_fields(self, kwargs: dict[str, Any], cfg: HumanizerConfig) -> MatchResult:
        fields = extract_chat_fields(kwargs)
        session_id = fields.get("session_id", "")

        if is_definitely_group(fields):
            return MatchResult(False, reason="not private chat", **fields)

        if not cfg.plugin.private_only:
            pass
        elif is_definitely_private(fields):
            pass
        else:
            cached = self._sessions.get_captured(session_id)
            if cached.get("chat_type") in ("group",):
                return MatchResult(False, reason="not private chat (cached group)", **fields)
            if cached.get("chat_type") in ("private",):
                pass
            else:
                user_id = fields.get("user_id", "")
                if user_id and user_id in cfg.plugin.target_user_ids:
                    if not fields.get("group_id"):
                        pass
                    else:
                        return MatchResult(False, reason="group_id present for target user", **fields)
                else:
                    return MatchResult(False, reason="not private chat (uncertain)", **fields)

        platform = fields["platform"]
        if cfg.plugin.target_platforms and platform and platform not in cfg.plugin.target_platforms:
            return MatchResult(False, reason="platform mismatch", **fields)

        for profile in cfg.target_profiles:
            if profile.platform:
                profile_platform_ok = not platform or profile.platform == platform
            else:
                profile_platform_ok = (
                    not cfg.plugin.target_platforms or not platform or platform in cfg.plugin.target_platforms
                )
            user_ok = bool(profile.user_id and profile.user_id == fields["user_id"])
            session_ok = bool(profile.session_id and profile.session_id == fields["session_id"])
            if profile_platform_ok and (user_ok or session_ok):
                return MatchResult(True, profile=profile, reason="profile matched", **fields)

        # 私聊会话 ID 自带目标 QQ：qq_private_3130274394。
        # 在 Replyer/Planner hook 里只有 session_id、没有 user_id 时也能准确识别。
        embedded_user_id = self._session_target_user_id(session_id)
        if embedded_user_id and embedded_user_id in cfg.plugin.target_user_ids:
            profile = next(
                (p for p in cfg.target_profiles if p.user_id == embedded_user_id),
                None,
            )
            if profile is None:
                profile = TargetProfile(profile_id=embedded_user_id, platform=platform, user_id=embedded_user_id)
            return MatchResult(
                True,
                profile=profile,
                reason="private session user matched",
                platform=platform or profile.platform,
                user_id=embedded_user_id,
                session_id=session_id,
                chat_type="private",
            )

        user_id = fields["user_id"]
        if user_id and user_id in cfg.plugin.target_user_ids:
            profile = TargetProfile(profile_id=user_id, platform=platform, user_id=user_id)
            return MatchResult(True, profile=profile, reason="user_id matched", **fields)

        session_id = fields["session_id"]
        if session_id and session_id in cfg.plugin.target_session_ids:
            profile = TargetProfile(profile_id=session_id, platform=platform, session_id=session_id)
            return MatchResult(True, profile=profile, reason="session_id matched", **fields)

        return MatchResult(False, reason="not target", **fields)

    # =========================================================================
    # Strategy 2 — confirmed / captured session matching
    # =========================================================================

    def _match_by_session(self, kwargs: dict[str, Any], cfg: HumanizerConfig) -> MatchResult:
        fields = extract_chat_fields(kwargs)
        session_id = fields.get("session_id", "")
        if not session_id:
            return MatchResult(False, reason="no session_id")

        if is_definitely_group(fields):
            self._sessions.reject_group(session_id)
            return MatchResult(False, reason="current message is group")

        cached = self._sessions.get_captured(session_id)
        if cached.get("chat_type") == "group":
            self._sessions.reject_group(session_id)
            return MatchResult(False, reason="cached group")

        if not self._sessions.is_matched(session_id):
            return MatchResult(False, reason="session not in matched cache")

        match_info = self._sessions.get_match_info(session_id)
        if match_info.get("chat_type") == "group":
            self._sessions.remove_matched(session_id)
            return MatchResult(False, reason="cached group")

        profile = self._resolve_profile(match_info, cfg)
        if profile is None:
            return MatchResult(False, reason="stale cache, no profile")

        return MatchResult(
            True,
            profile=profile,
            reason="cached matched session",
            platform=match_info.get("platform", "") or fields.get("platform", ""),
            user_id=match_info.get("user_id", "") or profile.user_id,
            session_id=session_id,
            chat_type=match_info.get("chat_type", "private"),
        )

    def _resolve_profile(self, match_info: dict[str, Any], cfg: HumanizerConfig) -> TargetProfile | None:
        cached_user_id = match_info.get("user_id", "")
        for profile in cfg.target_profiles:
            if cached_user_id and profile.user_id == cached_user_id:
                return profile
        if cfg.target_profiles:
            return cfg.target_profiles[0]
        if cached_user_id and cached_user_id in cfg.plugin.target_user_ids:
            return TargetProfile(
                profile_id=cached_user_id,
                platform=match_info.get("platform", ""),
                user_id=cached_user_id,
            )
        return None

    # =========================================================================
    # Strategy 3 — prompt text matching (last resort)
    # =========================================================================

    def _match_by_prompt(self, kwargs: dict[str, Any], cfg: HumanizerConfig) -> MatchResult:
        if not cfg.plugin.enabled:
            return MatchResult(False, reason="plugin disabled")

        fields = extract_chat_fields(kwargs)
        session_id = fields.get("session_id", "")

        # 提示词兜底只允许“明确私聊形态”的会话走：
        # 未知会话 ID（含空值）或群聊会话 ID 一律拒绝，避免群聊文本误匹配后缓存中毒。
        if is_definitely_group(fields):
            return MatchResult(False, reason="group session detected", **fields)
        if classify_session_id(session_id) != "private":
            self._logger.info(
                "prompt fallback rejected: session not private-shaped (session=%s)",
                session_id or "(empty)",
            )
            return MatchResult(False, reason="not private-shaped session", **fields)

        # 1.2.x 起 hook 载荷是 items（ContextItem 快照），旧版是 messages；
        # 先取 items，取不到再回退旧版 messages。
        messages = kwargs.get("items") or self._find_messages(kwargs)
        if not isinstance(messages, list):
            return MatchResult(False, reason="no prompt messages")

        text = extract_message_text(messages)
        if not text.strip():
            return MatchResult(False, reason="empty prompt messages")

        if cfg.plugin.private_only and has_group_keywords(text):
            return MatchResult(False, reason="group text signal detected")

        for profile in cfg.target_profiles:
            candidates = {
                profile.user_id.strip(),
                profile.display_name.strip(),
                profile.profile_id.strip(),
            }
            candidates.discard("")
            # 默认占位 profile_id（WebUI 新配置里常见）不参与文本匹配，避免误命中英文 "target"
            candidates.discard("target")
            if not candidates:
                continue
            for candidate in candidates:
                if len(candidate) < 2:
                    continue
                if candidate in text:
                    return MatchResult(
                        True,
                        profile=profile,
                        reason="prompt text matched",
                        platform=profile.platform,
                        user_id=profile.user_id,
                        session_id=session_id,
                        chat_type="private",
                    )
        return MatchResult(False, reason="not target")

    @staticmethod
    def _session_target_user_id(session_id: str) -> str:
        """从私聊形态会话 ID 中提取内嵌的 QQ 号。

        支持 qq_private_3130274394 / private_3130274394 / dm_3130274394 / qq_3130274394。
        """
        sid = str(session_id or "").strip().lower()
        if not sid:
            return ""
        for prefix in ("qq_private_", "private_", "dm_", "friend_", "qq_"):
            if sid.startswith(prefix):
                rest = sid[len(prefix):]
                if rest.isdigit():
                    return rest
        if sid.isdigit():
            return sid
        return ""

    @staticmethod
    def _find_messages(kwargs: dict[str, Any]) -> list[Any] | None:
        for key in ("messages", "message_list", "conversation_messages", "chat_messages", "prompt_messages"):
            value = kwargs.get(key)
            if isinstance(value, list):
                return value
        for key, value in kwargs.items():
            if isinstance(value, list) and len(value) > 0:
                if any(isinstance(item, dict) and ("role" in item or "content" in item) for item in value):
                    return value
        return None
