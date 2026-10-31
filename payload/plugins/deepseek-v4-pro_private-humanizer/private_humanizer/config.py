from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from maibot_sdk import Field, PluginConfigBase


# =============================================================================
# DEFAULT STRINGS
# =============================================================================

DEFAULT_FOLLOWUP_INTENT = (
    "这是私聊增强插件发起的主动续话检查。请回看刚才这一轮用户发言和你已经发出的回复，"
    "像真人私聊一样判断是否还需要自然补一句。只有在话题仍有余温、对方可能期待承接、"
    "或你刚才的回复留下了可继续的情绪/信息时才主动发一条很短的后续；"
    "如果要发，1-2句即可，先回应用户刚说的话再自然延伸，不要开启全新话题；"
    "如果刚才已经完整收束、对方明显不需要继续、或继续会显得打扰，就选择不发。"
    "不要编造未确认事实，不要解释插件，不要重复刚才的话，不要预设未来安排。"
)

# =============================================================================
# Runtime dataclasses (used by internal logic, loaded via load_config)
# =============================================================================

@dataclass(slots=True)
class PluginSection:
    enabled: bool = True
    private_only: bool = True
    target_platforms: list[str] = field(default_factory=lambda: ["qq"])
    target_user_ids: list[str] = field(default_factory=list)
    target_session_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TimeAwarenessSection:
    enabled: bool = True
    timezone: str = "Asia/Shanghai"
    holiday_region: str = "CN"
    custom_dates_enabled: bool = True
    custom_dates: list[dict[str, str]] = field(default_factory=list)


@dataclass(slots=True)
class ScheduleSection:
    enabled: bool = True
    generation_mode: str = "daily"
    refresh_hours: list[int] = field(default_factory=lambda: [7, 12, 18, 22])
    inject_into_planner: bool = True
    inject_into_replyer: bool = True
    allow_manual_override: bool = True
    manual_status: str = ""
    reference_only: bool = True
    allow_user_interrupt: bool = True
    manual_schedule: str = ""


@dataclass(slots=True)
class LifeEnvironmentSection:
    enabled: bool = True
    environment: str = ""
    auto_generate_when_empty: bool = True
    use_as_reference_only: bool = True


@dataclass(slots=True)
class ProfileSection:
    enabled: bool = True
    inject_into_private_prompt: bool = True
    require_evidence_for_preferences: bool = True


@dataclass(slots=True)
class GuardSection:
    fact_guard_enabled: bool = True
    anniversary_guard_enabled: bool = True
    style_guard_enabled: bool = True
    memory_guard_enabled: bool = True
    max_reply_chars_soft: int = 400
    max_reply_chars_hard: int = 800


@dataclass(slots=True)
class ProactiveFollowupSection:
    enabled: bool = True
    delay_seconds: int = 35
    cooldown_seconds: int = 180
    max_per_hour: int = 6
    min_reply_chars: int = 2
    intent: str = DEFAULT_FOLLOWUP_INTENT


@dataclass(slots=True)
class LoggingSection:
    enabled: bool = True
    log_level: str = "info"
    save_rewrite_pairs: bool = False


@dataclass(slots=True)
class TargetProfile:
    profile_id: str = ""
    platform: str = ""
    user_id: str = ""
    session_id: str = ""
    display_name: str = ""
    basic_info: str = ""
    preferences: str = ""
    important_dates: str = ""
    relationship_notes: str = ""

    def has_identity(self) -> bool:
        return bool(self.user_id or self.session_id)

    def verified_blocks(self) -> list[tuple[str, str]]:
        blocks = [
            ("基础信息", self.basic_info),
            ("偏好信息", self.preferences),
            ("重要日期", self.important_dates),
            ("关系说明", self.relationship_notes),
        ]
        return [(title, text.strip()) for title, text in blocks if text and text.strip()]


@dataclass(slots=True)
class HumanizerConfig:
    plugin: PluginSection = field(default_factory=PluginSection)
    time_awareness: TimeAwarenessSection = field(default_factory=TimeAwarenessSection)
    schedule: ScheduleSection = field(default_factory=ScheduleSection)
    life_environment: LifeEnvironmentSection = field(default_factory=LifeEnvironmentSection)
    profile: ProfileSection = field(default_factory=ProfileSection)
    guard: GuardSection = field(default_factory=GuardSection)
    proactive_followup: ProactiveFollowupSection = field(default_factory=ProactiveFollowupSection)
    logging: LoggingSection = field(default_factory=LoggingSection)
    target_profiles: list[TargetProfile] = field(default_factory=list)


# =============================================================================
# WebUI PluginConfigBase models (mirror the dataclasses above)
# =============================================================================

class PluginSectionConfig(PluginConfigBase):
    __ui_label__ = "基础设置"
    __ui_icon__ = "settings"
    __ui_order__ = 0

    config_version: str = Field(default="1.6.1", title="配置版本", description="供 MaiBot WebUI 识别配置版本，普通用户不要修改。")
    enabled: bool = Field(default=True, title="启用插件", description="关闭后插件安装但不生效。")
    private_only: bool = Field(default=True, title="只在私聊生效", description="建议开启，避免影响群聊。")
    target_platforms: list[str] = Field(default_factory=lambda: ["qq"], title="生效平台", description="QQ / NapCat 私聊一般填写 qq。")
    target_user_ids: list[str] = Field(default_factory=list, title="目标用户 QQ 号", description="插件只会对这些用户的私聊生效。")
    target_session_ids: list[str] = Field(default_factory=list, title="目标会话 ID", description="通常留空；只有无法按 user_id 识别时再填写。")


class TimeAwarenessConfig(PluginConfigBase):
    __ui_label__ = "时间感知"
    __ui_icon__ = "calendar-clock"
    __ui_order__ = 1

    enabled: bool = Field(default=True, title="启用时间感知", description="让 MaiBot 知道当前日期、星期和时段。")
    timezone: str = Field(default="Asia/Shanghai", title="时区", description="中国大陆用户保持 Asia/Shanghai。")
    holiday_region: str = Field(default="CN", title="节假日地区", description="保留字段，默认 CN。")
    custom_dates_enabled: bool = Field(default=True, title="启用自定义日期", description="填写生日、相识日、纪念日等已确认日期时开启。")
    custom_dates: list[dict[str, str]] = Field(default_factory=list, title="自定义重要日期", description="格式为 name/date/description；不确定的日期请留空。")


class ScheduleConfig(PluginConfigBase):
    __ui_label__ = "日程参考"
    __ui_icon__ = "sun"
    __ui_order__ = 2

    enabled: bool = Field(default=True, title="启用日程参考", description="让 MaiBot 根据当前时段更像真的在生活，但日程不是事实。")
    generation_mode: str = Field(default="daily", title="生成模式", description="保留 daily 即可。")
    refresh_hours: list[int] = Field(default_factory=lambda: [7, 12, 18, 22], title="状态刷新小时", description="用于区分早晨、中午、傍晚、睡前。")
    inject_into_planner: bool = Field(default=True, title="注入 Planner", description="开启后向规划器注入私聊画像和约束，避免系统优先调用默认人设。")
    inject_into_replyer: bool = Field(default=True, title="注入 Replyer", description="建议开启，让最终回复遵守私聊增强约束。")
    allow_manual_override: bool = Field(default=True, title="允许手动今日状态", description="开启后 manual_status 非空时优先使用。")
    manual_status: str = Field(default="", title="手动今日状态", description="可留空。填写后作为今日状态参考，不是已发生事实。")
    reference_only: bool = Field(default=True, title="日程仅作参考", description="建议开启。日程只影响语气和行为候选。")
    allow_user_interrupt: bool = Field(default=True, title="允许用户打断日程", description="用户让 MaiBot 做其他事时，MaiBot 会优先判断并承接用户当前指示。")
    manual_schedule: str = Field(default="", title="手动日程参考", description="可留空。留空时插件按当前时段自动生成轻量日程；填写后作为固定日程参考。")


class LifeEnvironmentConfig(PluginConfigBase):
    __ui_label__ = "虚拟生活环境"
    __ui_icon__ = "home"
    __ui_order__ = 3

    enabled: bool = Field(default=True, title="启用虚拟生活环境", description="为私聊注入生活环境参考。")
    environment: str = Field(default="", title="固定虚拟生活环境", description="可留空。留空时由主程序 LLM 根据人设自动生成；填写时作为固定环境参考。")
    auto_generate_when_empty: bool = Field(default=True, title="留空时自动生成", description="环境字段留空时，让主程序 LLM 生成一个稳定、低细节的生活环境参考。")
    use_as_reference_only: bool = Field(default=True, title="环境仅作参考", description="建议开启。环境只作为背景，不主动扩写成小说场景。")


class ProfileConfig(PluginConfigBase):
    __ui_label__ = "画像规则"
    __ui_icon__ = "user-round-check"
    __ui_order__ = 4

    enabled: bool = Field(default=True, title="启用画像", description="开启后注入下方私聊对象画像。")
    inject_into_private_prompt: bool = Field(default=True, title="画像写入私聊提示词", description="开启后 MaiBot 能看到 display_name、偏好、禁忌等。")
    require_evidence_for_preferences: bool = Field(default=True, title="偏好必须有证据", description="建议开启。未填写的偏好、日期、共同经历视为未知。")


class TargetProfileConfig(PluginConfigBase):
    __ui_label__ = "私聊对象画像"
    __ui_icon__ = "contact-round"
    __ui_order__ = 5

    profile_id: str = Field(default="target", title="画像编号", description="内部编号，用于区分多个私聊对象。")
    platform: str = Field(default="qq", title="平台", description="QQ 私聊填写 qq。")
    user_id: str = Field(default="", title="目标用户 QQ 号", description="应与 target_user_ids 中的值一致。")
    session_id: str = Field(default="", title="会话 ID", description="通常留空。")
    display_name: str = Field(default="", title="显示称呼", description="MaiBot 识别这个私聊对象时使用的称呼。")
    basic_info: str = Field(default="", title="基础信息", description="只写确定事实，不知道就留空或写未知。")
    preferences: str = Field(default="", title="偏好信息", description="只写确认过的聊天偏好、内容偏好和禁忌。")
    important_dates: str = Field(default="", title="重要日期", description="只有确认过才写；不确定就留空。")
    relationship_notes: str = Field(default="", title="关系说明和禁忌", description="写 MaiBot 应如何陪伴，以及不能编造什么。")


class GuardConfig(PluginConfigBase):
    __ui_label__ = "回复守卫"
    __ui_icon__ = "shield-check"
    __ui_order__ = 6

    fact_guard_enabled: bool = Field(default=True, title="事实守卫", description="防止无证据事实。")
    anniversary_guard_enabled: bool = Field(default=True, title="纪念日守卫", description="防止乱猜日期和相遇天数。")
    style_guard_enabled: bool = Field(default=True, title="风格守卫", description="减少过长、过度动作化和小说化回复。")
    memory_guard_enabled: bool = Field(default=True, title="记忆守卫", description="阻止模型自创个人事实进入表达学习。")
    max_reply_chars_soft: int = Field(default=400, title="软长度阈值", description="超过后更容易触发压缩。")
    max_reply_chars_hard: int = Field(default=800, title="硬长度上限", description="高风险长回复会被压缩到附近。")


class ProactiveFollowupConfig(PluginConfigBase):
    __ui_label__ = "主动续话"
    __ui_icon__ = "message-circle-plus"
    __ui_order__ = 7

    enabled: bool = Field(default=True, title="启用主动续话", description="MaiBot 回复后延迟检查是否自然补一句。")
    delay_seconds: int = Field(default=35, title="续话延迟秒数", description="建议 20-60 秒。")
    cooldown_seconds: int = Field(default=180, title="冷却秒数", description="同一会话两次主动续话的最短间隔。")
    max_per_hour: int = Field(default=6, title="每小时最多触发次数", description="0 表示不限制。")
    min_reply_chars: int = Field(default=2, title="最短回复长度", description="上一条回复短于该长度时不安排续话。")
    intent: str = Field(default=DEFAULT_FOLLOWUP_INTENT, title="续话判断意图", description="传给 Maisaka 主动任务的意图说明。")


class LoggingConfig(PluginConfigBase):
    __ui_label__ = "日志审计"
    __ui_icon__ = "file-clock"
    __ui_order__ = 8

    enabled: bool = Field(default=True, title="启用日志", description="记录插件拦截、改写和主动续话行为。")
    log_level: str = Field(default="info", title="日志等级", description="普通用户保持 info。")
    save_rewrite_pairs: bool = Field(default=False, title="保存改写前后文本", description="默认关闭以保护隐私；排查问题时可临时打开。")


class PrivateHumanizerRuntimeConfig(PluginConfigBase):
    __ui_label__ = "私聊拟人化增强"
    __ui_icon__ = "shield-check"
    __ui_order__ = -1

    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig, description="Basic plugin settings.")
    time_awareness: TimeAwarenessConfig = Field(default_factory=TimeAwarenessConfig, description="Date and time awareness.")
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig, description="Soft daily schedule reference.")
    life_environment: LifeEnvironmentConfig = Field(default_factory=LifeEnvironmentConfig, description="Virtual living environment reference.")
    profile: ProfileConfig = Field(default_factory=ProfileConfig, description="Profile injection settings.")
    target_profiles: list[TargetProfileConfig] = Field(default_factory=lambda: [TargetProfileConfig()], description="Private chat target profiles.")
    guard: GuardConfig = Field(default_factory=GuardConfig, description="Reply and memory guards.")
    proactive_followup: ProactiveFollowupConfig = Field(default_factory=ProactiveFollowupConfig, description="Proactive follow-up settings.")
    logging: LoggingConfig = Field(default_factory=LoggingConfig, description="Audit log settings.")


# =============================================================================
# Config loader
# =============================================================================


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _str_list(value: Any) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def _int_list(value: Any, default: list[int]) -> list[int]:
    result: list[int] = []
    for item in _as_list(value):
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result or default


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "y"}:
        return True
    if normalized in {"0", "false", "no", "off", "n"}:
        return False
    return default


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    return value if isinstance(value, dict) else {}


def load_config(raw: dict[str, Any] | None) -> HumanizerConfig:
    data = raw or {}
    plugin = _section(data, "plugin")
    time_awareness = _section(data, "time_awareness")
    schedule = _section(data, "schedule")
    life_environment = _section(data, "life_environment")
    profile = _section(data, "profile")
    guard = _section(data, "guard")
    proactive_followup = _section(data, "proactive_followup")
    logging = _section(data, "logging")

    profiles: list[TargetProfile] = []
    for item in _as_list(data.get("target_profiles")):
        if not isinstance(item, dict):
            continue
        target = TargetProfile(
            profile_id=str(item.get("profile_id", "")).strip(),
            platform=str(item.get("platform", "")).strip(),
            user_id=str(item.get("user_id", "")).strip(),
            session_id=str(item.get("session_id", "")).strip(),
            display_name=str(item.get("display_name", "")).strip(),
            basic_info=str(item.get("basic_info", "")).strip(),
            preferences=str(item.get("preferences", "")).strip(),
            important_dates=str(item.get("important_dates", "")).strip(),
            relationship_notes=str(item.get("relationship_notes", "")).strip(),
        )
        if target.has_identity():
            profiles.append(target)

    config = HumanizerConfig(
        plugin=PluginSection(
            enabled=_safe_bool(plugin.get("enabled", True)),
            private_only=_safe_bool(plugin.get("private_only", True)),
            target_platforms=_str_list(plugin.get("target_platforms", ["qq"])),
            target_user_ids=_str_list(plugin.get("target_user_ids", [])),
            target_session_ids=_str_list(plugin.get("target_session_ids", [])),
        ),
        time_awareness=TimeAwarenessSection(
            enabled=_safe_bool(time_awareness.get("enabled", True)),
            timezone=str(time_awareness.get("timezone", "Asia/Shanghai")).strip() or "Asia/Shanghai",
            holiday_region=str(time_awareness.get("holiday_region", "CN")).strip() or "CN",
            custom_dates_enabled=_safe_bool(time_awareness.get("custom_dates_enabled", True)),
            custom_dates=[
                item for item in _as_list(time_awareness.get("custom_dates", [])) if isinstance(item, dict)
            ],
        ),
        schedule=ScheduleSection(
            enabled=_safe_bool(schedule.get("enabled", True)),
            generation_mode=str(schedule.get("generation_mode", "daily")).strip() or "daily",
            refresh_hours=_int_list(schedule.get("refresh_hours", [7, 12, 18, 22]), [7, 12, 18, 22]),
            inject_into_planner=_safe_bool(schedule.get("inject_into_planner", True)),
            inject_into_replyer=_safe_bool(schedule.get("inject_into_replyer", True)),
            allow_manual_override=_safe_bool(schedule.get("allow_manual_override", True)),
            manual_status=str(schedule.get("manual_status", "")).strip(),
            reference_only=_safe_bool(schedule.get("reference_only", True)),
            allow_user_interrupt=_safe_bool(schedule.get("allow_user_interrupt", True)),
            manual_schedule=str(schedule.get("manual_schedule", "")).strip(),
        ),
        life_environment=LifeEnvironmentSection(
            enabled=_safe_bool(life_environment.get("enabled", True)),
            environment=str(life_environment.get("environment", "")).strip(),
            auto_generate_when_empty=_safe_bool(life_environment.get("auto_generate_when_empty", True)),
            use_as_reference_only=_safe_bool(life_environment.get("use_as_reference_only", True)),
        ),
        profile=ProfileSection(
            enabled=_safe_bool(profile.get("enabled", True)),
            inject_into_private_prompt=_safe_bool(profile.get("inject_into_private_prompt", True)),
            require_evidence_for_preferences=_safe_bool(profile.get("require_evidence_for_preferences", True)),
        ),
        guard=GuardSection(
            fact_guard_enabled=_safe_bool(guard.get("fact_guard_enabled", True)),
            anniversary_guard_enabled=_safe_bool(guard.get("anniversary_guard_enabled", True)),
            style_guard_enabled=_safe_bool(guard.get("style_guard_enabled", True)),
            memory_guard_enabled=_safe_bool(guard.get("memory_guard_enabled", True)),
            max_reply_chars_soft=_safe_int(guard.get("max_reply_chars_soft", 400), 400),
            max_reply_chars_hard=_safe_int(guard.get("max_reply_chars_hard", 800), 800),
        ),
        proactive_followup=ProactiveFollowupSection(
            enabled=_safe_bool(proactive_followup.get("enabled", True)),
            delay_seconds=max(1, _safe_int(proactive_followup.get("delay_seconds", 35), 35)),
            cooldown_seconds=max(0, _safe_int(proactive_followup.get("cooldown_seconds", 180), 180)),
            max_per_hour=max(0, _safe_int(proactive_followup.get("max_per_hour", 6), 6)),
            min_reply_chars=max(0, _safe_int(proactive_followup.get("min_reply_chars", 2), 2)),
            intent=str(proactive_followup.get("intent", DEFAULT_FOLLOWUP_INTENT)).strip()
            or DEFAULT_FOLLOWUP_INTENT,
        ),
        logging=LoggingSection(
            enabled=_safe_bool(logging.get("enabled", True)),
            log_level=str(logging.get("log_level", "info")).strip() or "info",
            save_rewrite_pairs=_safe_bool(logging.get("save_rewrite_pairs", False)),
        ),
        target_profiles=profiles,
    )

    if config.guard.max_reply_chars_soft > config.guard.max_reply_chars_hard:
        config.guard.max_reply_chars_soft = config.guard.max_reply_chars_hard

    return config
