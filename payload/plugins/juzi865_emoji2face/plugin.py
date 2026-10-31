from __future__ import annotations

from maibot_sdk import MaiBotPlugin

from .config import Emoji2FaceConfig


class Emoji2FacePlugin(MaiBotPlugin):
    config_model = Emoji2FaceConfig

    async def on_load(self) -> None:
        self.ctx.logger.info(
            "emoji2face 已加载（功能由 SnowLuma adapter 原生提供，"
            "本插件仅用于配置管理）",
        )

    async def on_unload(self) -> None:
        self.ctx.logger.info("emoji2face 插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        self.ctx.logger.info("emoji2face 配置已更新: %s", version)


def create_plugin() -> Emoji2FacePlugin:
    return Emoji2FacePlugin()
