# Gemini 联网搜索 1.1.0 — Vertex 适配

此目录是参考 `../reference/search_plugin.py`、`gemini_client.py`、`fetch_client.py`、`search_manifest.json` 制作的本地交付副本。保留插件 ID `local.gemini-web-search`、工厂 `create_plugin()` 及工具名 `gemini_search` / `gemini_fetch`。不应与旧插件同时注册这两个工具。本次未部署、未重启、未向模型发送真实请求。

## 默认配置

```toml
[plugin]
enabled = true
config_version = "1.1.0"

[provider]
backend = "vertex"
model_config_path = "/MaiMBot/config/model_config.toml"
model = "gemini-3.8-flash"
region = "global"
auth_mode = "api_key"
thinking_low = true
timeout_seconds = 90.0

[search]
default_sources = 6
max_sources = 10
max_output_tokens = 1800
max_output_chars = 12000
cache_ttl_seconds = 300
max_uses = 3  # 仅旧 Magpie 后端有效
```

以上为配置节选，未列字段沿用源码默认值。搜索模型、区域及思考配置与主模型独立。已有旧配置迁移时，应显式将 `provider.model` 从 `antigravity/...` 改为 Vertex 模型 ID；旧 Magpie 模型转到 `provider.magpie_model`。

每次真实搜索请求前只读 `model_config.toml` 中唯一的 `PrimaryProvider`，在进程内取得 `api_key` 和 `base_url`。不生成密钥副本，不将凭据写入插件配置、日志或测试记录。默认忽略 TOML 遗留的 `auth_type = "bearer"`：遵循现有 GeminiClient 的 `genai.Client(api_key=...)` 语义，发送 `x-goog-api-key`，不把 API key 当 OAuth token。旧默认鉴权 header / query 会被移除以防重复发送。

仅当明确将 PrimaryProvider 的 `api_key` 字段用作 OAuth access token 时，才可显式设 `provider.auth_mode = "oauth"`；插件不会自动获取、刷新或猜测 OAuth 凭据。

例如从当前区域 publisher base 派生搜索端点：

```text
https://asia-southeast1-aiplatform.googleapis.com/v1beta1/projects/<project>/locations/asia-southeast1/publishers/google
→ https://aiplatform.googleapis.com/v1beta1/projects/<project>/locations/global/publishers/google/models/gemini-3.8-flash:generateContent
```

保留原 project 和 API 版本，只为搜索替换 hostname/location。不会修改 TOML 或主模型区域。允许 Google 官方 Vertex HTTPS 主机；拒绝将主凭据发送至任意代理地址。也支持 Express 的 global root/publisher base。

主线程反馈该模型在 `asia-southeast1` 返回 404、在同 project/key 的 Global 成功并返回 grounding（约 6.14 秒）；这是主线程提供的结果，本副本没有复测收费接口。

## 请求与 grounding

运行时只需已有 `httpx`，直接发送 Vertex `generateContent` REST 请求：`tools=[{"googleSearch":{}}]`。默认 `generationConfig.thinkingConfig.thinkingLevel = "LOW"`。若搜索模型不接受思考参数，设 `provider.thinking_low = false` 可完全省略该字段；不会更改 Argon 的 LOW 配置。失败请求不会自动重试或自动切换后端，避免额外请求。

只从同一个 candidate 的 `groundingMetadata.groundingChunks[].web.uri` 接受 HTTP(S) 来源，去重并限制数量；保留 Google 返回的 grounding redirect URI，不从模型正文、citationMetadata 或原始搜索词补编链接，也不自动访问跳转链接。支持 REST camelCase 及 SDK `model_dump()` 的 snake_case。

只输出 `groundingSupports` 映射到保留来源的文本片段与引用。`content` 中的 `[1]` 是人类阅读编号；结构化 `citations[].source_indices` 是 `sources` 数组的 **0 起始索引**。缺少 segment text 时支持按 partIndex 和 UTF-8 字节偏移提取，跳过 thought parts。来源截断和去重后重新映射引用。

缺少可核验 grounding 来源时返回 `success=false`，不会显示“已搜索”。有真实来源而没有逐句 grounding support 时，仅返回来源及“缺少可映射逐句引文”的说明，不使用模型记忆摘要。

Vertex GoogleSearch 没有本实现可用的 `max_uses` 硬上限；单次工具调用发送一个模型请求，限制输入关键词长度、输出来源数和 token 数。模型内部可能产生多个实际搜索词；不能把 Magpie 的 `max_uses` 当作 Vertex 计费查询硬限制。

## 显式调用与隐私

```json
{"query":"Gemini release notes", "public_query":true, "count":6}
```

`gemini_search` 仍由 Planner 按问题需要显式调用，无消息监听器、自动搜索钩子或普通闲聊搜索注入。工具描述明确要求先提炼公开关键词。新增必填工具参数 `public_query`；方法默认 false，遗漏或非布尔 true 均拒绝请求，便于旧调用方安全失败。

`ori_question` 仅保留接口兼容，始终丢弃；不读取或发送聊天历史、记忆、群上下文或其他 kwargs。关键词限定 1–256 字符，本地拒绝常见凭据、邮箱、长号码、私人聊天标记和链接。当前加载的凭据也不得出现在关键词中。检查属于防误传措施，不能判断所有自由文本的公开性；调用方仍须先移除非公开内容，不能仅把 `public_query` 一律设 true。

成功结果只存进程内 LRU，默认 TTL 300 秒、容量 128。失败不缓存，配置更新会清缓存，cache key 不含原始问题。`count` 与默认来源数均受 `max_sources` 约束。错误不回显响应正文、完整请求、URL、header 或原始异常；成功结果中的已知凭据也会脱敏。

## URL 读取与旧后端

`gemini_fetch(url=...)` 继续直接使用原插件 `SafePageFetcher`，无需调用搜索模型。保留 DNS 公网地址检查、每次重定向检查、大小/类型/次数限制、脚本样式过滤；补充凭据 URL 拒绝及安全错误处理。它不带 PrimaryProvider 的任何鉴权 header 或聊天上下文。抓取实现沿用原插件的校验后请求流程，未新增浏览器执行或 cookie 支持。

`provider.backend = "magpie"` 可显式切回旧 Anthropic `/messages` 后端，继续使用原 `base_url`、`api_key` 字段及独立 `magpie_model`。Magpie 密钥默认留空，此目录没有复制任何真实密钥。默认 Vertex，绝不隐式回退。新模块使用 `vertex_search_client` / `vertex_search_privacy` 独立名称，避免共享 runner 中通用 `vertex_client` / `privacy` 模块缓存冲突；旧 `gemini_client` / `fetch_client` 名称按要求保留。

## 离线测试

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

本地隔离 `.venv` 已安装测试依赖；运行时依赖见 `requirements.txt`，测试专用依赖见 `requirements-test.txt`，完整本地环境版本见 `requirements-test-lock.txt`。测试用假凭据和本目录内临时 TOML，MockTransport 拦截模型/页面请求，禁止 socket connect；不读取远端真实凭据。

结果：**27 项通过**，详见 `test-results.txt`。覆盖当前遗留 bearer 配置仍用 x-goog-api-key、默认 Global 派生与区域可配、OAuth 显式选择、凭据轮换、LOW/omit、真实 google-genai 1.73.1 SDK 的 mock 请求序列化、grounding/citations/redirect URI、UTF-8 偏移、缺 grounding 拒绝、来源限额、缓存到期、错误/成功脱敏、隐私拦截、安全抓取、Magpie 可选和通用模块名冲突。

SDK 1.73.1 的 mock 请求中嵌套 thinking config 序列化为 `thinking_level`，测试按 SDK 类型语义校验 LOW；本插件 REST 明确使用 `thinkingLevel`。MaiBot 工具装饰器/配置测试使用基于远端 SDK 2 只读签名的 double，尚未进行真实 MaiBot runner / QQ 集成测试。

Google 官方接口参考：[Google Search grounding](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/grounding/grounding-with-google-search)、[Vertex endpoint 形状](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/start/express-mode/vertex-ai-express-mode-api-reference)。
