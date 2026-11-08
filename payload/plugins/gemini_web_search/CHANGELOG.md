# Changelog

## 1.1.0 — 2026-11-04

- 从参考 1.0.3 插件复制适配；保留插件 ID、gemini_search、gemini_fetch 及原有 Magpie 可选后端。
- 默认 Vertex gemini-3.8-flash、Global、LOW；仅搜索支持独立区域/模型及省略思考参数。
- 请求前只读当前 PrimaryProvider，以 x-goog-api-key 使用 API key，忽略遗留 bearer；OAuth 需显式配置。
- 从 PrimaryProvider 派生搜索端点，不更改主模型配置或区域。
- 严格解析 grounding sources 和逐句 citations，缺来源拒绝声称完成搜索。
- 增加公开关键词显式确认，丢弃 ori_question，加入本地隐私检查及响应脱敏。
- 保留 5 分钟 LRU 缓存和安全页面抓取，修复默认来源数上限及错误详情泄露。
- 新模块名使用 vertex_search_client / vertex_search_privacy，避免共享 runner 通用模块名冲突。
- 添加离线 mock、SDK 请求序列化及配置/安全回归测试；无远端部署、重启或收费调用。
