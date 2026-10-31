# Gemini 联网搜索 1.0.3

这是当前 MaiBot 部署使用的原生插件，提供两个工具：

- `gemini_search`：通过 Magpie 调用 `antigravity/gemini-3.8-flash` 的 Google Search grounding。
- `gemini_fetch`：安全读取公开网页正文，拒绝本机、私网和保留地址。

`gemini_search` 只有在响应中实际出现 `web_search_tool_result` 且至少取得一个来源时才返回成功，防止模型把旧记忆冒充为联网结果。

部署后应同时：

1. 移除旧的 `deepseek_web_search` 插件目录。
2. 将 `model_config.toml` 的 `model_task_config.web_search.model_list` 设为空，避免重复联网工具。
3. 把人设中的 `deepseek_search` / `deepseek_fetch` 改成 `gemini_search` / `gemini_fetch`。

插件配置里的 `provider.api_key` 是 Magpie gateway key，部署时从现有模型配置复制，不写入仓库模板。
