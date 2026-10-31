from maibot_sdk import Field, PluginConfigBase


class PluginSection(PluginConfigBase):
    enabled: bool = Field(default=True, description="是否启用 emoji 转换")
    config_version: str = Field(default="1.0.0", description="配置版本号")


class ConvertSection(PluginConfigBase):
    mode: str = Field(
        default="auto",
        description='转换模式: auto=仅转换已知映射的 emoji, all=尝试转换所有 emoji, off=关闭',
    )
    max_emoji_per_message: int = Field(
        default=5, ge=1, le=20, description="单条消息最多转换的 emoji 数量",
    )


class Emoji2FaceConfig(PluginConfigBase):
    plugin: PluginSection = Field(default_factory=PluginSection)
    convert: ConvertSection = Field(default_factory=ConvertSection)
