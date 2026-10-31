from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .time_utils import now_in_timezone


def write_audit(
    plugin_dir: Path,
    enabled: bool,
    record: dict[str, Any],
    timezone_name: str = "Asia/Shanghai",
) -> None:
    if not enabled:
        return
    log_dir = plugin_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    now = now_in_timezone(timezone_name)
    payload = {"time": now.strftime("%Y-%m-%d %H:%M:%S"), **record}
    path = log_dir / f"private-humanizer-{now:%Y-%m-%d}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
