from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import HumanizerConfig

_logger = logging.getLogger("private_humanizer.time_utils")


WEEKDAYS_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


CN_FIXED_HOLIDAYS = {
    "01-01": "元旦",
    "02-14": "情人节",
    "03-08": "妇女节",
    "05-01": "劳动节",
    "06-01": "儿童节",
    "10-01": "国庆节",
    "12-24": "平安夜",
    "12-25": "圣诞节",
}


def now_in_timezone(timezone_name: str) -> datetime:
    try:
        return datetime.now(ZoneInfo(timezone_name))
    except Exception:
        _logger.warning(
            "ZoneInfo('%s') 不可用，回退到固定 UTC 偏移。注意：回退模式不处理夏令时。"
            " 请安装 tzdata 包或使用正确的 IANA 时区名。",
            timezone_name,
        )
        return datetime.now(tz=timezone_from_name(timezone_name))


_KNOWN_TZ_OFFSETS = {
    "Asia/Shanghai": 8, "Asia/Chongqing": 8, "Asia/Harbin": 8,     "Asia/Urumqi": 6,
    "Asia/Tokyo": 9, "Asia/Seoul": 9,
    "America/New_York": -5, "America/Chicago": -6, "America/Los_Angeles": -8,
    "Europe/London": 0, "Europe/Paris": 1, "Europe/Moscow": 3,
    "Australia/Sydney": 10,
    "CN": 8, "PRC": 8,
}

def timezone_from_name(name: str):
    name = str(name or "").strip()
    offset = _KNOWN_TZ_OFFSETS.get(name, 8)
    return timezone(timedelta(hours=offset), name=name or "Asia/Shanghai")


def period_name(hour: int) -> str:
    if 5 <= hour < 9:
        return "早晨"
    if 9 <= hour < 12:
        return "上午"
    if 12 <= hour < 14:
        return "中午/午休前后"
    if 14 <= hour < 18:
        return "下午"
    if 18 <= hour < 22:
        return "晚上"
    return "深夜/睡前"


def nearby_dates(config: HumanizerConfig, now: datetime) -> list[str]:
    items: list[str] = []
    today_key = now.strftime("%m-%d")
    tomorrow_key = (now + timedelta(days=1)).strftime("%m-%d")
    for key, name in CN_FIXED_HOLIDAYS.items():
        if key == today_key:
            items.append(f"今天是{name}")
        elif key == tomorrow_key:
            items.append(f"明天是{name}")

    if config.time_awareness.custom_dates_enabled:
        for item in config.time_awareness.custom_dates:
            name = str(item.get("name", "")).strip()
            date = str(item.get("date", "")).strip()
            desc = str(item.get("description", "")).strip()
            if not name or not date:
                continue
            suffix = f"：{desc}" if desc else ""
            normalized = date.replace("-", "").replace("/", "").replace(".", "")
            if normalized.endswith(today_key.replace("-", "")):
                items.append(f"今天是{name}{suffix}")
            elif normalized.endswith(tomorrow_key.replace("-", "")):
                items.append(f"明天是{name}{suffix}")
    return items


def build_time_summary(config: HumanizerConfig, now: datetime | None = None) -> str:
    now = now or now_in_timezone(config.time_awareness.timezone)
    parts = [
        f"当前时间：{now:%Y-%m-%d} {WEEKDAYS_CN[now.weekday()]}，{period_name(now.hour)}",
    ]
    nearby = nearby_dates(config, now)
    if nearby:
        parts.append("节日：" + "；".join(nearby))
    parts.append("可结合时段自然提及作息，不猜纪念日。")
    return "\n".join(parts)


def build_status_reference(config: HumanizerConfig, now: datetime | None = None) -> str:
    if config.schedule.manual_status and config.schedule.allow_manual_override:
        return config.schedule.manual_status.strip()

    now = now or now_in_timezone(config.time_awareness.timezone)
    status_map = {
        "早晨": "清晨，状态慢慢进入节奏",
        "上午": "上午，处理日常事务中",
        "中午": "午间，偏轻松",
        "下午": "下午，平稳陪伴中",
        "晚上": "晚上，节奏放慢",
    }
    period = period_name(now.hour)
    status = "深夜，更克制安稳"
    for key, val in status_map.items():
        if key in period:
            status = val
            break
    return f"状态：{status}"


def build_life_schedule_reference(config: HumanizerConfig, now: datetime | None = None) -> str:
    now = now or now_in_timezone(config.time_awareness.timezone)
    manual = config.schedule.manual_schedule.strip()
    if manual:
        return f"私聊日程参考：{manual}"

    hour = now.hour
    schedule_map = {
        (5, 8): "清晨，适合轻柔陪伴",
        (8, 11): "上午，处理日常中",
        (11, 14): "午间，可关心吃饭休息",
        (14, 17): "下午，陪伴式闲聊",
        (17, 20): "傍晚，节奏放松",
        (20, 23): "晚上，聊天和陪伴",
    }
    schedule_text = "深夜，克制安稳"
    for (lo, hi), text in schedule_map.items():
        if lo <= hour < hi:
            schedule_text = text
            break

    lines = [
        f"日程：{schedule_text}",
        "注意：仅作语气参考，不是事实。用户指示优先于日程。",
    ]
    return "\n".join(lines)
