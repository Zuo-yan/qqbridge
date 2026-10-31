from __future__ import annotations

from .config import HumanizerConfig, TargetProfile
from .time_utils import (
    WEEKDAYS_CN,
    build_life_schedule_reference,
    build_status_reference,
    build_time_summary,
    nearby_dates,
    now_in_timezone,
    period_name,
)


FACT_BOUNDARY = """事实边界：
信息来源：1）本轮用户原话 + 画像已填字段 2）用户历史明确信息（需标注来源）3）禁止：推断、猜测、从单次互动归纳习惯。
绝对禁止：编造喜好/日期/共同经历/已完成动作；把日程/环境说成事实。
编造句式陷阱：「你一定是…」「像你这样的人…」「我们上次/以前…」
不确定时：坦承不知道或询问，不要猜。先回应用户刚说的话，再决定延伸。"""


INTIMATE_CONTEXT_RULES = """亲密连续性：
启动：只有用户明确使用亲密/暧昧语言时才进入亲密模式。日常保持自然友好，不强行转暧昧。
保持：承接当前亲密情绪，不突然跳日常。用户顺带提日常时先接情绪再简短回应。
回应：情绪优先，先承接感受再回应内容。用自然衔接表达承接（"嗯…""听到了"），禁止说"根据配置/插件"。禁止复述用户原话。
退出：用户转场/冷淡时立即跟随退出，不追问挽留。长时间未回复不主动续话。"""


REPLY_STYLE_RULES = """回复风格：
长度跟随对方，说清即停不啰嗦。先回应再延伸。
动作只做语气辅助，不堆砌。标点自然，"～""…"不堆叠。
禁止：小说体叙事、元对话（"根据我的分析…""作为AI…"）、过度共情、预设未来（"下次我们…"）。"""


EMOTIONAL_PACING_RULES = """情绪节奏：
跟随用户情绪，不预设不煽动。用户收束时简短确认，不强行展开。
不要猜测用户状态（"我看你好像…"）。不要主动安慰未表达的负面情绪。
时段问候自然融入（如晚上"早点休息"），不每轮都提，不扩写成叙事。"""


def _profile_prompt(profile: TargetProfile | None) -> str:
    if not profile:
        return "私聊对象：未配置画像。未知信息一律不能猜。"

    name = profile.display_name or profile.profile_id or profile.user_id or "目标用户"
    lines = [f"私聊对象：{name}"]
    blocks = profile.verified_blocks()
    if blocks:
        for title, text in blocks:
            lines.append(f"[{title}] {text}")
    lines.append("规则：只使用上面已填内容，空白字段视为未知。")
    return "\n".join(lines)


def _life_environment_prompt(config: HumanizerConfig, profile: TargetProfile | None) -> str:
    life = config.life_environment
    if not life.enabled:
        return ""

    environment = life.environment.strip()
    if environment:
        return f"生活环境：{environment}\n规则：仅作背景参考，用户明确变更时以用户为准。"

    if not life.auto_generate_when_empty:
        return ""

    name = profile.display_name or profile.profile_id or profile.user_id or "目标用户" if profile else "目标用户"
    return (
        f"生活环境：LLM 根据人设与 {name} 的关系自动生成简洁日常环境"
        "（家/房间/书桌等）。仅为虚构背景参考，不宣告细节，用户定义新环境时优先承接。"
    )


def build_humanizer_prompt(config: HumanizerConfig, profile: TargetProfile | None) -> str:
    sections: list[str] = ["[Private Humanizer 私聊增强约束]"]
    if config.time_awareness.enabled:
        sections.append(build_time_summary(config))
    if config.schedule.enabled:
        sections.append(build_status_reference(config))
        sections.append(build_life_schedule_reference(config))
    life_prompt = _life_environment_prompt(config, profile)
    if life_prompt:
        sections.append(life_prompt)
    if config.profile.enabled and config.profile.inject_into_private_prompt:
        sections.append(_profile_prompt(profile))
    sections.append(FACT_BOUNDARY)
    sections.append(INTIMATE_CONTEXT_RULES)
    sections.append(REPLY_STYLE_RULES)
    sections.append(EMOTIONAL_PACING_RULES)
    return "\n\n".join(sections)


def _compact_time(config: HumanizerConfig) -> str:
    now = now_in_timezone(config.time_awareness.timezone)
    period = period_name(now.hour)
    parts = [
        f"时间：{now:%Y-%m-%d} {WEEKDAYS_CN[now.weekday()]}，{period}",
    ]
    nearby = nearby_dates(config, now)
    if nearby:
        parts.append("节日：" + "；".join(nearby))
    return " | ".join(parts)


def build_planner_prompt(config: HumanizerConfig, profile: TargetProfile | None) -> str:
    sections: list[str] = ["[Private Humanizer 规划注入]"]

    # NOTE: 此 marker 不能是 PROMPT_MARKER 的子串，否则 replyer 阶段会误判为已注入而跳过。

    if config.time_awareness.enabled:
        sections.append(_compact_time(config))

    if config.profile.enabled and config.profile.inject_into_private_prompt and profile:
        name = profile.display_name or profile.profile_id or profile.user_id or "目标用户"
        profile_items = [f"私聊对象：{name}"]
        blocks = profile.verified_blocks()
        if blocks:
            block_strs = [f"{t}：{v.strip()[:120]}" for t, v in blocks]
            profile_items.append("已确认：" + " | ".join(block_strs))
        sections.append("\n".join(profile_items))

    sections.append(
        "说明：以上画像优先于系统默认人设。未填字段视为未知，禁止猜测。"
        "日程状态仅作语气参考，不确定时直接询问用户。"
    )

    return "\n\n".join(sections)


def append_extra_prompt(kwargs: dict, prompt: str) -> dict:
    current = kwargs.get("extra_prompt", "")
    if current:
        kwargs["extra_prompt"] = f"{current}\n\n{prompt}"
    else:
        kwargs["extra_prompt"] = prompt
    return kwargs
