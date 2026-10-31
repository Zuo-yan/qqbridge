from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from .config import HumanizerConfig
from .constants import FOLLOWUP_LOG_WINDOW_SECONDS, INTIMATE_FOLLOWUP_INTENT
from .context import extract_chat_fields
from .guards import is_intimate_context
from .matching import MatchResult

_logger = logging.getLogger("private_humanizer.followup")


class FollowupManager:
    def __init__(self, trigger_fn: Callable[..., Any]) -> None:
        self._trigger = trigger_fn
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._history: dict[str, list[float]] = {}

    def clear(self) -> None:
        for task in list(self._tasks.values()):
            if not task.done():
                task.cancel()
        self._tasks.clear()
        self._history.clear()

    def cancel_session(self, session_id: str) -> None:
        task = self._tasks.pop(session_id, None)
        if task is not None and not task.done():
            task.cancel()

    # ------------------------------------------------------------------
    # Schedule
    # ------------------------------------------------------------------

    def schedule_if_needed(
        self,
        kwargs: dict[str, Any],
        config: HumanizerConfig,
        match: MatchResult,
        response_text: str,
        context_text: str = "",
        audit_fn: Callable[..., None] | None = None,
    ) -> bool:
        followup = config.proactive_followup
        if not followup.enabled:
            return False

        session_id = str(match.session_id or extract_chat_fields(kwargs).get("session_id") or "").strip()
        if not session_id:
            return False

        if len((response_text or "").strip()) < followup.min_reply_chars:
            return False

        if int(kwargs.get("retry_count") or 0) > 0:
            return False

        existing = self._tasks.get(session_id)
        if existing is not None and not existing.done():
            return False

        now = time.time()
        recent = [
            stamp
            for stamp in self._history.get(session_id, [])
            if now - stamp < FOLLOWUP_LOG_WINDOW_SECONDS
        ]
        self._history[session_id] = recent

        if followup.max_per_hour and len(recent) >= followup.max_per_hour:
            if audit_fn:
                audit_fn({
                    "stage": "followup_skipped",
                    "chat_id": session_id,
                    "user_id": match.user_id,
                    "reason": "hourly limit reached",
                    "limit": followup.max_per_hour,
                })
            return False

        if recent and now - recent[-1] < followup.cooldown_seconds:
            return False

        intimate = is_intimate_context(context_text, response_text)
        self._tasks[session_id] = asyncio.create_task(
            self._delayed_trigger(session_id, config, match.user_id, response_text, intimate, audit_fn),
        )
        return True

    async def _delayed_trigger(
        self,
        session_id: str,
        config: HumanizerConfig,
        user_id: str,
        response_text: str,
        intimate_context: bool = False,
        audit_fn: Callable[..., None] | None = None,
    ) -> None:
        try:
            await asyncio.sleep(config.proactive_followup.delay_seconds)
            intent = INTIMATE_FOLLOWUP_INTENT if intimate_context else config.proactive_followup.intent
            result = await self._trigger(
                stream_id=session_id,
                intent=intent,
                reason="private_humanizer_followup",
                metadata={
                    "source": "private_humanizer",
                    "last_reply_preview": (response_text or "").strip()[:120],
                    "intimate_context": intimate_context,
                },
            )
            success = bool(isinstance(result, dict) and result.get("success"))
            if success:
                self._history.setdefault(session_id, []).append(time.time())
            if audit_fn:
                audit_fn({
                    "stage": "followup_triggered" if success else "followup_failed",
                    "chat_id": session_id,
                    "user_id": user_id,
                    "result": result,
                })
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if audit_fn:
                audit_fn({
                    "stage": "followup_failed",
                    "chat_id": session_id,
                    "user_id": user_id,
                    "error": str(exc),
                })
        finally:
            self._tasks.pop(session_id, None)
