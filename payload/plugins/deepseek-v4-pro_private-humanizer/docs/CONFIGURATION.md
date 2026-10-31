# 配置说明

> 本文档适用于 v1.6.1。

所有配置都在 `config.toml` 中完成。插件不会读取 MaiBot 主程序的 `bot_config.toml`，因此每个使用者都需要在本插件配置里填写自己的目标私聊和画像。

## `[plugin]`

```toml
[plugin]
enabled = true
private_only = true
target_platforms = ["qq"]
target_user_ids = ["123456789"]
target_session_ids = []
```

- `enabled`：总开关。
- `private_only`：建议保持 `true`，开启后群聊不会触发插件。
- `target_platforms`：允许的平台。常见值是 `qq`。
- `target_user_ids`：目标私聊用户 ID 白名单。
- `target_session_ids`：可选。某些适配器更容易拿到 session_id，可以在这里补充。

## `[[target_profiles]]`

```toml
[[target_profiles]]
profile_id = "target"
platform = "qq"
user_id = "123456789"
session_id = ""
display_name = "目标私聊对象"
basic_info = ""
preferences = ""
important_dates = ""
relationship_notes = ""
```

画像是可信事实来源。只要写在这里，插件会把它作为“已确认信息”注入；没写的内容会被视为未知。

建议写法：

- 使用短句，不要写成大段小说设定。
- 只写确定事实。
- 不确定的内容留空。
- 日期最好写清楚年份或说明是否每年重复。

## `[time_awareness]`

控制真实日期和时段注入：

```toml
[time_awareness]
enabled = true
timezone = "Asia/Shanghai"
holiday_region = "CN"
custom_dates_enabled = true
```

`custom_dates` 可以写自定义重要日期：

```toml
[[time_awareness.custom_dates]]
name = "相识日"
date = "2025-06-18"
description = "用户明确确认过的相识日"
```

## `[schedule]`

控制“今日状态参考”：

```toml
[schedule]
enabled = true
generation_mode = "daily"
inject_into_planner = false
inject_into_replyer = true
allow_manual_override = true
manual_status = ""
```

当前版本是规则生成的轻量状态，不调用额外 LLM。`manual_status` 填写后会优先使用，例如：

```toml
manual_status = "今天状态比较安静，适合简短陪伴和轻松聊天，不主动编造具体行程。"
```

## `[guard]`

控制回复与记忆守卫：

```toml
[guard]
fact_guard_enabled = true
anniversary_guard_enabled = true
style_guard_enabled = true
memory_guard_enabled = true
max_reply_chars_soft = 400
max_reply_chars_hard = 800
```

- `fact_guard_enabled`：阻止“你最爱”“我记得你”“我给你准备了”等无证据事实。
- `anniversary_guard_enabled`：阻止纪念日乱猜。
- `style_guard_enabled`：压缩过长、过度动作化、过度场景化回复。
- `memory_guard_enabled`：阻止疑似自创事实进入表达学习。

## `[logging]`

```toml
[logging]
enabled = true
log_level = "info"
save_rewrite_pairs = false
```

`save_rewrite_pairs = true` 时会保存原回复和改写结果，便于调试。默认关闭以保护隐私，排查问题时可临时开启，排查结束后务必关回 `false`。
