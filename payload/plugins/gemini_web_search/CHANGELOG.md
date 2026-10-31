# 1.0.3

- 增加 MaiBot Runner 要求的 `create_plugin()` 工厂函数。

# 1.0.2

- 将插件目录加入模块搜索路径，修复 Runner 无法导入同目录客户端模块的问题。

# 1.0.1

- 补齐 MaiBot 清单校验要求的 `author.url` 和 `urls.repository`。

# 1.0.0

- 新增 `gemini_search`，通过 Magpie 的 Anthropic Messages 接口调用 Gemini Google Search grounding。
- 只有取得实际 `web_search_tool_result` 来源时才返回成功。
- 新增 `gemini_fetch`，带 DNS、私网地址、重定向、大小和内容类型限制。
