"""麦麦!来点二次元图片! — 插件配置模型。

基于 cnmiw.com (MirlKoi API) 的随机二次元图片插件配置。
WebUI 配置表单依赖此模块生成多语言界面。
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Literal, Optional

from maibot_sdk import Field, PluginConfigBase
from pydantic import field_validator

# ═══════════════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════════════

CONFIG_SCHEMA_VERSION = "4.1.0"


# ═══════════════════════════════════════════════════════════════════════
# i18n 辅助
# ═══════════════════════════════════════════════════════════════════════

def _schema_i18n(
    *,
    label_en: str,
    label_ja: str,
    hint_en: Optional[str] = None,
    hint_ja: Optional[str] = None,
    placeholder_en: Optional[str] = None,
    placeholder_ja: Optional[str] = None,
) -> Dict[str, Dict[str, str]]:
    """构造 WebUI 配置项多语言说明，外层 label/hint 保留中文字段。"""
    i18n: Dict[str, Dict[str, str]] = {
        "en_US": {"label": label_en},
        "ja_JP": {"label": label_ja},
    }
    if hint_en is not None:
        i18n["en_US"]["hint"] = hint_en
    if hint_ja is not None:
        i18n["ja_JP"]["hint"] = hint_ja
    if placeholder_en is not None:
        i18n["en_US"]["placeholder"] = placeholder_en
    if placeholder_ja is not None:
        i18n["ja_JP"]["placeholder"] = placeholder_ja
    return i18n


# ═══════════════════════════════════════════════════════════════════════
# 规范化辅助
# ═══════════════════════════════════════════════════════════════════════

def _normalize_string(value: Any) -> str:
    """规范化字符串配置值，去首尾空白；None 返回空串。"""
    return "" if value is None else str(value).strip()


def _normalize_string_list(value: Any) -> List[str]:
    """规范化字符串列表：去空白、去重、保序。非列表返回空列表。"""
    if not isinstance(value, list):
        return []
    normalized: List[str] = []
    seen: set[str] = set()
    for item in value:
        text = _normalize_string(item)
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _normalize_positive_float(value: Any, default: float) -> float:
    """规范化正浮点数；非法回退默认值。"""
    if isinstance(value, (int, float)) and float(value) > 0:
        return float(value)
    if isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError:
            return default
        if parsed > 0:
            return parsed
    return default


# ═══════════════════════════════════════════════════════════════════════
# 配置模型
# ═══════════════════════════════════════════════════════════════════════


class PluginSection(PluginConfigBase):
    """插件基础设置"""
    __ui_label__: ClassVar[str] = "插件总开关"
    __ui_order__: ClassVar[int] = 0

    config_version: str = Field(
        default=CONFIG_SCHEMA_VERSION,
        description="配置 schema 版本，请勿手动修改。",
        json_schema_extra={
            "disabled": True,
            "hidden": True,
            "label": "配置版本",
            "i18n": _schema_i18n(label_en="Config version", label_ja="設定バージョン"),
            "order": 99,
        },
    )
    enabled: bool = Field(
        default=True,
        description="总开关。关闭后插件完全停止工作，不会发图。",
        json_schema_extra={
            "label": "启用插件",
            "hint": "关闭后插件完全停止工作，不会发图。",
            "i18n": _schema_i18n(
                label_en="Enable plugin",
                label_ja="プラグインを有効化",
                hint_en="Master switch. When OFF, the plugin stops entirely — no image sending.",
                hint_ja="マスタースイッチ。OFFにすると画像送信も完全に停止します。",
            ),
            "order": 0,
        },
    )

    @field_validator("config_version", mode="before")
    @classmethod
    def _normalize_config_version(cls, value: Any) -> str:
        return _normalize_string(value) or CONFIG_SCHEMA_VERSION


class ApiSection(PluginConfigBase):
    """图片来源设置（cnmiw.com / MirlKoi API）"""
    __ui_label__: ClassVar[str] = "图片来源"
    __ui_order__: ClassVar[int] = 1

    base_url: str = Field(
        default="https://api.cnmiw.com/api.php",
        description="随机图片 API 地址。",
        json_schema_extra={
            "label": "API 地址",
            "hint": "cnmiw.com (MirlKoi API) 随机图片接口，一般无需修改。",
            "i18n": _schema_i18n(
                label_en="API URL",
                label_ja="API URL",
                hint_en="cnmiw.com (MirlKoi API) random image endpoint. Usually no need to change.",
                hint_ja="cnmiw.com (MirlKoi API) ランダム画像エンドポイント。通常変更不要。",
            ),
            "order": 0,
        },
    )
    nsfw_sort: str = Field(
        default="CDNsetu",
        description="色图分类的 sort 参数。CDN 开头免 Referer 更稳，直连需 Referer。",
        json_schema_extra={
            "label": "色图分类(sort)",
            "hint": "色图用哪个分类。推荐 CDNsetu（免Referer，稳）。也可用 setu(直连快但需Referer)。",
            "i18n": _schema_i18n(
                label_en="NSFW sort key",
                label_ja="NSFW sortキー",
                hint_en="CDNsetu = CDN reverse proxy (no Referer, stable). setu = direct (faster, needs Referer).",
                hint_ja="CDNsetu=CDN経由(Referer不要・安定)。setu=直接(高速・Referer必要)。",
            ),
            "order": 1,
        },
    )
    sfw_sort: str = Field(
        default="CDNcat",
        description="无色图分类的 sort 参数。CDN 开头免 Referer 更稳。",
        json_schema_extra={
            "label": "无色图分类(sort)",
            "hint": "无色图用哪个分类。推荐 CDNcat（免Referer，稳）。也可用 cat(直连快但需Referer)。",
            "i18n": _schema_i18n(
                label_en="SFW sort key",
                label_ja="SFW sortキー",
                hint_en="CDNcat = CDN reverse proxy (no Referer, stable). cat = direct (faster, needs Referer).",
                hint_ja="CDNcat=CDN経由(Referer不要・安定)。cat=直接(高速・Referer必要)。",
            ),
            "order": 2,
        },
    )
    request_timeout: float = Field(
        default=20.0,
        description="调用 API 获取图片地址的超时时间（秒）。",
        json_schema_extra={
            "label": "API 超时(秒)",
            "hint": "请求图片接口的超时时间，单位秒。",
            "i18n": _schema_i18n(
                label_en="API timeout (sec)",
                label_ja="APIタイムアウト(秒)",
                hint_en="Timeout for requesting the image API, in seconds.",
                hint_ja="画像APIリクエストのタイムアウト(秒)。",
            ),
            "order": 3,
            "step": 1,
        },
    )
    download_timeout: float = Field(
        default=30.0,
        description="下载单张图片的超时时间（秒）。",
        json_schema_extra={
            "label": "下载超时(秒)",
            "hint": "下载单张图片的超时时间，单位秒。",
            "i18n": _schema_i18n(
                label_en="Download timeout (sec)",
                label_ja="ダウンロードタイムアウト(秒)",
                hint_en="Timeout for downloading a single image, in seconds.",
                hint_ja="1枚の画像ダウンロードのタイムアウト(秒)。",
            ),
            "order": 4,
            "step": 1,
        },
    )

    @field_validator("base_url", "nsfw_sort", "sfw_sort", mode="before")
    @classmethod
    def _normalize_text(cls, value: Any) -> str:
        return _normalize_string(value)

    @field_validator("request_timeout", mode="before")
    @classmethod
    def _normalize_request_timeout(cls, value: Any) -> float:
        return _normalize_positive_float(value, 20.0)

    @field_validator("download_timeout", mode="before")
    @classmethod
    def _normalize_download_timeout(cls, value: Any) -> float:
        # 回退值与字段默认值 30.0 保持一致（避免非法配置静默回退到 20.0）
        return _normalize_positive_float(value, 30.0)


class ChatFilterSection(PluginConfigBase):
    """聊天名单过滤（参考 napcat 适配器的黑白名单）"""
    __ui_label__: ClassVar[str] = "聊天名单"
    __ui_order__: ClassVar[int] = 2

    enabled: bool = Field(
        default=False,
        description="开启后按下方名单限制哪些群聊/私聊能发图。",
        json_schema_extra={
            "label": "启用聊天名单",
            "hint": "关闭=所有群和私聊都能发图。开启后按下方群聊/私聊名单过滤。",
            "i18n": _schema_i18n(
                label_en="Enable chat list filter",
                label_ja="チャットリストを有効化",
                hint_en="OFF = all groups/private chats can receive images. ON = filter by the lists below.",
                hint_ja="OFF=全グループ/個人チャットで画像送信可。ON=下のリストでフィルター。",
            ),
            "order": 0,
        },
    )
    group_list_type: Literal["whitelist", "blacklist"] = Field(
        default="blacklist",
        description="群聊名单模式。",
        json_schema_extra={
            "label": "群聊名单模式",
            "hint": "whitelist=只有名单内的群能发图；blacklist=名单内的群不发图。",
            "i18n": _schema_i18n(
                label_en="Group list mode",
                label_ja="グループリストモード",
                hint_en="whitelist = only listed groups can receive images; blacklist = listed groups are blocked.",
                hint_ja="whitelist=リスト内のグループのみ送信可。blacklist=リスト内のグループは送信不可。",
            ),
            "order": 1,
        },
    )
    group_list: List[str] = Field(
        default_factory=list,
        description="群聊名单中的群号列表。",
        json_schema_extra={
            "label": "群聊名单",
            "hint": "群号会自动转字符串并去重。whitelist 模式只填允许发图的群；blacklist 模式填禁止发图的群。",
            "i18n": _schema_i18n(
                label_en="Group list",
                label_ja="グループリスト",
                hint_en="Group IDs are normalized to strings and deduplicated.",
                hint_ja="グループIDは文字列に正規化・重複排除されます。",
                placeholder_en="Enter group ID",
                placeholder_ja="グループIDを入力",
            ),
            "placeholder": "请输入群号",
            "order": 2,
        },
    )
    private_list_type: Literal["whitelist", "blacklist"] = Field(
        default="blacklist",
        description="私聊名单模式。",
        json_schema_extra={
            "label": "私聊名单模式",
            "hint": "whitelist=只有名单内的用户私聊能发图；blacklist=名单内的用户私聊不发图。",
            "i18n": _schema_i18n(
                label_en="Private list mode",
                label_ja="個人チャットリストモード",
                hint_en="whitelist = only listed users can receive images; blacklist = listed users are blocked.",
                hint_ja="whitelist=リスト内のユーザーのみ送信可。blacklist=リスト内のユーザーは送信不可。",
            ),
            "order": 3,
        },
    )
    private_list: List[str] = Field(
        default_factory=list,
        description="私聊名单中的用户 ID 列表。",
        json_schema_extra={
            "label": "私聊名单",
            "hint": "用户 ID 会自动转字符串并去重。",
            "i18n": _schema_i18n(
                label_en="Private list",
                label_ja="個人チャットリスト",
                hint_en="User IDs are normalized to strings and deduplicated.",
                hint_ja="ユーザーIDは文字列に正規化・重複排除されます。",
                placeholder_en="Enter user ID",
                placeholder_ja="ユーザーIDを入力",
            ),
            "placeholder": "请输入用户 ID",
            "order": 4,
        },
    )
    reject_message: str = Field(
        default="",
        description="未通过名单时的提示语。留空则静默不发图。",
        json_schema_extra={
            "label": "未通过名单时的回复",
            "hint": "当前群/私聊不在允许范围时的提示语。留空=静默不发图（不回复）。",
            "i18n": _schema_i18n(
                label_en="Reply when not allowed",
                label_ja="許可外の返信",
                hint_en="Reply when the chat isn't allowed. Empty = silently skip.",
                hint_ja="許可されていないチャットの返信。空欄=サイレント。",
                placeholder_en="Leave empty = silent",
                placeholder_ja="空欄=サイレント",
            ),
            "placeholder": "留空 = 静默不发图",
            "order": 5,
        },
    )

    @field_validator("group_list_type", "private_list_type", mode="before")
    @classmethod
    def _normalize_list_type(cls, value: Any) -> Literal["whitelist", "blacklist"]:
        normalized = _normalize_string(value).lower()
        if normalized == "whitelist":
            return "whitelist"
        if normalized == "blacklist":
            return "blacklist"
        return "blacklist"

    @field_validator("group_list", "private_list", mode="before")
    @classmethod
    def _normalize_id_lists(cls, value: Any) -> List[str]:
        return _normalize_string_list(value)


class NsfwFilterSection(PluginConfigBase):
    """色图范围控制（在全局 nsfw_allowed 之上，按群聊/私聊细分色图是否允许）"""
    __ui_label__: ClassVar[str] = "色图范围"
    __ui_order__: ClassVar[int] = 3

    enabled: bool = Field(
        default=False,
        description="开启后按下方名单限制哪些群聊/私聊能发色图；关闭则色图只受全局「允许色图」控制。",
        json_schema_extra={
            "label": "启用色图范围",
            "hint": "关闭=色图能否发送只看「发图设置·允许色图」。开启后，色图还要通过下方群聊/私聊名单。",
            "i18n": _schema_i18n(
                label_en="Enable NSFW scope",
                label_ja="NSFWスコープを有効化",
                hint_en="OFF = NSFW follows the global 'Allow NSFW' toggle. ON = NSFW must also pass the lists below.",
                hint_ja="OFF=NSFWは全体設定に従う。ON=NSFWは下のリストも通過する必要あり。",
            ),
            "order": 0,
        },
    )
    group_list_type: Literal["whitelist", "blacklist"] = Field(
        default="whitelist",
        description="色图群聊名单模式。",
        json_schema_extra={
            "label": "色图群聊模式",
            "hint": "whitelist=只有名单内的群能发色图（默认，保守）；blacklist=名单内的群不能发色图，其它群可以。",
            "i18n": _schema_i18n(
                label_en="NSFW group list mode",
                label_ja="NSFWグループリストモード",
                hint_en="whitelist = only listed groups can send NSFW (default, safe). blacklist = listed groups are blocked from NSFW.",
                hint_ja="whitelist=リスト内グループのみNSFW可(既定・安全)。blacklist=リスト内グループはNSFW不可。",
            ),
            "order": 1,
        },
    )
    group_list: List[str] = Field(
        default_factory=list,
        description="色图群聊名单中的群号列表。",
        json_schema_extra={
            "label": "色图群聊名单",
            "hint": "群号自动转字符串并去重。whitelist 模式填允许发色图的群；blacklist 模式填禁止发色图的群。",
            "i18n": _schema_i18n(
                label_en="NSFW group list",
                label_ja="NSFWグループリスト",
                hint_en="Group IDs normalized to strings and deduplicated.",
                hint_ja="グループIDは文字列に正規化・重複排除。",
                placeholder_en="Enter group ID",
                placeholder_ja="グループIDを入力",
            ),
            "placeholder": "请输入群号",
            "order": 2,
        },
    )
    private_allowed: bool = Field(
        default=True,
        description="私聊是否允许发色图（群聊不受此项影响，按上面的群聊名单走）。",
        json_schema_extra={
            "label": "私聊允许色图",
            "hint": "私聊场合通常较私密，默认允许色图。关闭则私聊也不能发色图（仍可发无色图）。",
            "i18n": _schema_i18n(
                label_en="Allow NSFW in private chats",
                label_ja="個人チャットでNSFWを許可",
                hint_en="Private chats are usually more private, default ON. OFF blocks NSFW in private chats (SFW still allowed).",
                hint_ja="個人チャットは通常プライベート、既定ON。OFFだと個人チャットでもNSFW不可(SFWは可)。",
            ),
            "order": 3,
        },
    )
    fallback_to_sfw: bool = Field(
        default=True,
        description="色图被拦截时是否自动降级为发无色图。",
        json_schema_extra={
            "label": "拦截时降级发无色图",
            "hint": "开启=本群不允许色图时，自动改发一张无色图（仍满足看图需求）。关闭=按下方回复语处理，不发图。",
            "i18n": _schema_i18n(
                label_en="Fallback to SFW when blocked",
                label_ja="ブロック時にSFWへフォールバック",
                hint_en="ON = send an SFW image instead when NSFW is blocked. OFF = handle by the reply text below, no image.",
                hint_ja="ON=NSFWブロック時にSFW画像を代わりに送信。OFF=下の返信テキストで処理、画像なし。",
            ),
            "order": 4,
        },
    )
    reject_message: str = Field(
        default="",
        description="色图被拦截且不降级时的回复语。留空则静默不发图。",
        json_schema_extra={
            "label": "色图被拦截时的回复",
            "hint": "仅在「拦截时降级发无色图」关闭时生效。留空=静默不发图。如：本群不允许色图哦~",
            "i18n": _schema_i18n(
                label_en="Reply when NSFW blocked",
                label_ja="NSFWブロック時の返信",
                hint_en="Only used when 'Fallback to SFW' is OFF. Empty = silently skip.",
                hint_ja="「SFWフォールバック」OFF時のみ有効。空欄=サイレント。",
                placeholder_en="Leave empty = silent",
                placeholder_ja="空欄=サイレント",
            ),
            "placeholder": "留空 = 静默不发图",
            "order": 5,
        },
    )

    @field_validator("group_list_type", mode="before")
    @classmethod
    def _normalize_list_type(cls, value: Any) -> Literal["whitelist", "blacklist"]:
        normalized = _normalize_string(value).lower()
        if normalized == "whitelist":
            return "whitelist"
        if normalized == "blacklist":
            return "blacklist"
        return "whitelist"

    @field_validator("group_list", mode="before")
    @classmethod
    def _normalize_id_list(cls, value: Any) -> List[str]:
        return _normalize_string_list(value)


class AtModeSection(PluginConfigBase):
    """触发条件"""
    __ui_label__: ClassVar[str] = "触发条件"
    __ui_order__: ClassVar[int] = 4

    enabled: bool = Field(
        default=True,
        description="开启后只有 @机器人 的消息才会触发发图，防止误触发。",
        json_schema_extra={
            "label": "需要 @ 才触发",
            "hint": "开启后群聊中必须 @机器人 才会发图。关闭则任何含关键词的消息都会触发。",
            "i18n": _schema_i18n(
                label_en="Require @-mention to trigger",
                label_ja="@メンションが必要",
                hint_en="When ON, only @-mentioned messages trigger image sending. When OFF, any message with keywords triggers.",
                hint_ja="ONにすると@メンションされたメッセージのみ画像送信をトリガー。OFFだとキーワード含む全メッセージが対象。",
            ),
            "order": 0,
        },
    )
    require_at_group: bool = Field(
        default=True,
        description="群聊中是否需要 @ 机器人才触发。",
        json_schema_extra={
            "label": "群聊需要 @",
            "hint": "群聊场景下是否需要 @ 机器人才触发发图。",
            "i18n": _schema_i18n(
                label_en="Require @ in group chats",
                label_ja="グループチャットで@必須",
                hint_en="Whether group chat messages must @-mention the bot to trigger.",
                hint_ja="グループチャットでボットへの@メンションが必要かどうか。",
            ),
            "order": 1,
        },
    )
    require_at_private: bool = Field(
        default=False,
        description="私聊中是否也需要 @ 才触发。通常关闭即可。",
        json_schema_extra={
            "label": "私聊也需要 @",
            "hint": "私聊场景通常不需要 @，直接发关键词即可触发。",
            "i18n": _schema_i18n(
                label_en="Require @ in private chats",
                label_ja="プライベートチャットで@必須",
                hint_en="Usually OFF for private chats — just type the keyword directly.",
                hint_ja="通常プライベートチャットではOFF。キーワードを直接入力するだけ。",
            ),
            "order": 2,
        },
    )
    bot_name: str = Field(
        default="麦麦",
        description="机器人在群里的昵称，用于检测 @ 提及。",
        json_schema_extra={
            "label": "机器人昵称",
            "hint": "用于检测消息中是否 @了机器人。需要和机器人在群里的昵称一致。",
            "i18n": _schema_i18n(
                label_en="Bot nickname",
                label_ja="ボットのニックネーム",
                hint_en="Used to detect @-mentions in messages. Must match the bot's nickname in the group.",
                hint_ja="メッセージ内の@メンション検出に使用。グループでのボットのニックネームと一致させてください。",
            ),
            "order": 3,
        },
    )
    reject_message: str = Field(
        default="",
        description="未 @ 时的拦截提示语。留空则静默忽略不回复。",
        json_schema_extra={
            "label": "未 @ 时的回复",
            "hint": "当消息未 @ 机器人时回复的提示语。留空 = 静默忽略，不回复任何内容。",
            "i18n": _schema_i18n(
                label_en="Reply when not @-mentioned",
                label_ja="@未メンション時の返信",
                hint_en="Reply text when the message doesn't @-mention the bot. Leave empty = silently ignore.",
                hint_ja="@メンションされていない場合の返信テキスト。空欄 = 無視して返信なし。",
                placeholder_en="Leave empty = silent ignore",
                placeholder_ja="空欄 = サイレント無視",
            ),
            "placeholder": "留空 = 静默忽略",
            "order": 4,
        },
    )


class SendSection(PluginConfigBase):
    """发图设置"""
    __ui_label__: ClassVar[str] = "发图设置"
    __ui_order__: ClassVar[int] = 5

    nsfw_allowed: bool = Field(
        default=True,
        description="是否允许发送色图（NSFW）。",
        json_schema_extra={
            "label": "允许色图",
            "hint": "关闭后所有色图关键词都不会发图（无色图不受影响）。",
            "i18n": _schema_i18n(
                label_en="Allow NSFW",
                label_ja="NSFWを許可",
                hint_en="When OFF, NSFW keywords won't trigger images (SFW unaffected).",
                hint_ja="OFFにするとNSFWキーワードで画像送信なし(SFWは影響なし)。",
            ),
            "order": 0,
        },
    )
    sfw_allowed: bool = Field(
        default=True,
        description="是否允许发送无色图（SFW）。",
        json_schema_extra={
            "label": "允许无色图",
            "hint": "关闭后所有无色图关键词都不会发图（色图不受影响）。",
            "i18n": _schema_i18n(
                label_en="Allow SFW",
                label_ja="SFWを許可",
                hint_en="When OFF, SFW keywords won't trigger images (NSFW unaffected).",
                hint_ja="OFFにするとSFWキーワードで画像送信なし(NSFWは影響なし)。",
            ),
            "order": 1,
        },
    )
    nsfw_keywords: List[str] = Field(
        default=["涩图", "色图", "瑟图", "来点涩图", "来点色图", "setu", "r18"],
        description="触发色图的关键词列表。消息含任意一个即发色图。",
        json_schema_extra={
            "label": "色图触发词",
            "hint": "消息含任意一个即触发色图（前提：允许色图已开）。每行一个。",
            "i18n": _schema_i18n(
                label_en="NSFW trigger keywords",
                label_ja="NSFWトリガーキーワード",
                hint_en="Any message containing one of these triggers an NSFW image (if NSFW allowed). One per line.",
                hint_ja="いずれかを含むメッセージでNSFW画像を送信(NSFW許可時)。1行1つ。",
                placeholder_en="涩图, 色图, setu",
                placeholder_ja="涩图, 色图, setu",
            ),
            "placeholder": "涩图, 色图, 瑟图, setu",
            "order": 2,
        },
    )
    sfw_keywords: List[str] = Field(
        default=["来点图", "来张图", "看看腿", "来点腿", "来点二次元图片", "来点二次元图", "美图", "无色图"],
        description="触发无色图的关键词列表。消息含任意一个即发无色图。",
        json_schema_extra={
            "label": "无色图触发词",
            "hint": "消息含任意一个即触发无色图（前提：允许无色图已开）。每行一个。",
            "i18n": _schema_i18n(
                label_en="SFW trigger keywords",
                label_ja="SFWトリガーキーワード",
                hint_en="Any message containing one of these triggers an SFW image (if SFW allowed). One per line.",
                hint_ja="いずれかを含むメッセージでSFW画像を送信(SFW許可時)。1行1つ。",
                placeholder_en="来点图, 美图, 二次元",
                placeholder_ja="来点图, 美图, 二次元",
            ),
            "placeholder": "来点图, 美图, 二次元",
            "order": 3,
        },
    )
    count: int = Field(
        default=1,
        description="每次触发发送几张图片。1~100。",
        json_schema_extra={
            "label": "每次发几张",
            "hint": "每次触发发图时发送几张。API 单次最多取 100 张，建议 1~3 张。",
            "i18n": _schema_i18n(
                label_en="Images per trigger",
                label_ja="トリガーあたりの送信枚数",
                hint_en="How many images to send each time. API max 100 per call. Recommended 1-3.",
                hint_ja="トリガーごとの送信枚数。APIは最大100枚/回。推奨1-3。",
            ),
            "order": 4,
        },
    )
    cooldown_sec: float = Field(
        default=10.0,
        description="两次发图之间的最小间隔（秒），防刷屏。",
        json_schema_extra={
            "label": "冷却时间(秒)",
            "hint": "两次发图之间的最小间隔，单位秒，防止刷屏。",
            "i18n": _schema_i18n(
                label_en="Cooldown (sec)",
                label_ja="クールダウン(秒)",
                hint_en="Minimum interval between triggers, in seconds.",
                hint_ja="トリガー間の最小間隔(秒)。",
            ),
            "order": 5,
            "step": 1,
        },
    )
    dedup_enabled: bool = Field(
        default=True,
        description="是否启用近期去重（避免短时间内重复发同一张图）。",
        json_schema_extra={
            "label": "启用近期去重",
            "hint": "开启后记住最近发过的图片地址，命中则自动重取，减少重复发图。",
            "i18n": _schema_i18n(
                label_en="Enable recent dedup",
                label_ja="最近の重複除外",
                hint_en="Remember recently sent image URLs and re-fetch on match to reduce duplicates.",
                hint_ja="最近送信した画像URLを記憶し、重複時は再取得して重複を減らします。",
            ),
            "order": 6,
        },
    )
    dedup_max_size: int = Field(
        default=500,
        description="去重缓存最多记住多少条记录。",
        json_schema_extra={
            "label": "去重缓存上限",
            "hint": "近期去重缓存的最大条数，超出后自动丢弃最旧的。",
            "i18n": _schema_i18n(
                label_en="Dedup cache size",
                label_ja="重複除外キャッシュ上限",
                hint_en="Max entries in the recent-dedup cache. Oldest dropped when exceeded.",
                hint_ja="最近の重複除外キャッシュの最大件数。超過時は最古のものを破棄。",
            ),
            "order": 7,
            "step": 1,
        },
    )

    @field_validator("nsfw_keywords", "sfw_keywords", mode="before")
    @classmethod
    def _normalize_keywords(cls, value: Any) -> List[str]:
        return _normalize_string_list(value)

    @field_validator("count", mode="before")
    @classmethod
    def _normalize_count(cls, value: Any) -> int:
        try:
            n = int(value)
        except (TypeError, ValueError):
            return 1
        return max(1, min(n, 100))

    @field_validator("cooldown_sec", mode="before")
    @classmethod
    def _normalize_cooldown(cls, value: Any) -> float:
        return _normalize_positive_float(value, 10.0)

    @field_validator("dedup_max_size", mode="before")
    @classmethod
    def _normalize_dedup_size(cls, value: Any) -> int:
        try:
            n = int(value)
        except (TypeError, ValueError):
            return 500
        return max(1, n)


class PixivCrawlerConfig(PluginConfigBase):
    """插件完整配置"""
    __ui_label__: ClassVar[str] = "全部配置"

    plugin: PluginSection = Field(default_factory=PluginSection)
    api: ApiSection = Field(default_factory=ApiSection)
    chat_filter: ChatFilterSection = Field(default_factory=ChatFilterSection)
    nsfw_filter: NsfwFilterSection = Field(default_factory=NsfwFilterSection)
    at_mode: AtModeSection = Field(default_factory=AtModeSection)
    send: SendSection = Field(default_factory=SendSection)


PixivCrawlerConfig.model_rebuild()
