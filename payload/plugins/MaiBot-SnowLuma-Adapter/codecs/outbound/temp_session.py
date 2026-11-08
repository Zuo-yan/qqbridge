"""Choose a shared group for QQ temporary private sessions."""
from __future__ import annotations

from typing import Any, Mapping


PRIVATE_ACTIONS = {"send_private_msg", "send_private_forward_msg"}


def choose_temp_group(user_id: str, friend_ids: set[str], groups: list[Mapping[str, Any]]) -> str:
    """Return the shared group used to open a temporary session.

    Friends keep the normal private channel. A non-friend uses the shared group
    with the most members; equal sizes use the larger group id.
    """

    target = str(user_id or "").strip()
    if not target or target in {str(item).strip() for item in friend_ids}:
        return ""
    best_key: tuple[int, str] | None = None
    best_group = ""
    for group in groups:
        group_id = str(group.get("group_id") or "").strip()
        members = {str(item).strip() for item in group.get("members") or [] if str(item).strip()}
        if not group_id or target not in members:
            continue
        try:
            member_count = int(group.get("member_count") or 0)
        except (TypeError, ValueError):
            member_count = 0
        if member_count <= 0:
            member_count = len(members)
        key = (member_count, group_id)
        if best_key is None or key > best_key:
            best_key = key
            best_group = group_id
    return best_group


def with_temp_group(action_name: str, params: Mapping[str, Any], group_id: str) -> dict[str, Any]:
    """Attach a temporary-session source group without turning the send into a group message."""

    updated = dict(params)
    source = str(group_id or "").strip()
    if action_name not in PRIVATE_ACTIONS or not source or str(updated.get("group_id") or "").strip():
        return updated
    updated["group_id"] = source
    return updated
