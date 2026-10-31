# 多平台链接解析（MaiBot 移植版）

自动解析 QQ 群里的抖音、小红书、小黑盒链接，并把图文或视频发送回群聊。B 站链接建议继续使用独立的 Bilibili 插件，避免重复解析。

## 迁移来源

本插件是 MaiBot 适配版，解析核心迁移自 AstrBot 插件：

- 原项目：`Zhalslar/astrbot_plugin_parser`
- 原仓库：https://github.com/Zhalslar/astrbot_plugin_parser
- 原许可：MIT License

本移植版保留原解析核心，并将 AstrBot 的事件、发送与配置接口改为 MaiBot SDK / OneBot HTTP 发送方式。

## 功能

- 抖音短链、视频、图文解析
- 小红书短链、图文、视频解析
- 小黑盒帖子、游戏分享解析
- 图片优先使用群聊合并转发
- 视频使用 OneBot HTTP 直接发送
- 群白名单、去重冷却、媒体大小限制

## 命令

本插件没有显式命令。群里发送支持的平台链接后自动触发。

## 配置

主要配置位于 `config.toml`：

- `parser.enabled_platforms`：启用平台，默认 `douyin`、`xhs`、`xiaoheihe`
- `parser.group_whitelist`：允许自动解析的群号，公开版默认空列表表示所有群；生产环境建议填入目标群号
- `parser.block_ai_reply`：命中链接后是否阻止麦麦继续普通聊天
- `parser.max_images`：单条链接最多发送图片数
- `api.port`：OneBot HTTP API 端口，默认 `3000`
- `api.bot_uin`：发送合并转发节点时使用的 bot QQ，建议填写自己的机器人 QQ

## 依赖

依赖已在 `_manifest.json` 中声明，包括 `aiofiles`、`msgspec`、`yt-dlp`、`bilibili-api-python`。

## 许可与署名

本移植版遵循 MIT License。第三方来源与许可见 `THIRD_PARTY_NOTICES.md`。
