# 多平台链接解析 - 插件市场提交说明

## 推荐分类

- Utility Tools
- External Integration

## 推荐标签

- link-parser
- douyin
- xhs
- xiaoheihe
- astrbot-port

## 迁移来源

本插件是 MaiBot 移植版，解析核心迁移自 AstrBot 插件 `Zhalslar/astrbot_plugin_parser`。

- 原仓库：https://github.com/Zhalslar/astrbot_plugin_parser
- 原许可：MIT License
- 移植说明：保留原解析核心，将 AstrBot 消息事件、发送接口和配置读取改为 MaiBot SDK Hook 与 OneBot HTTP 发送。

## 上架备注

当前 `_manifest.json` 的 `urls.repository` 指向 MaiBot 移植版仓库；上游来源保留在 README 与 `THIRD_PARTY_NOTICES.md`。
