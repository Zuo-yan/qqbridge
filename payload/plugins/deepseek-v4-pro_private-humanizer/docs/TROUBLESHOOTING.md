# 排错说明

## 升级 MaiBot 到 1.2.x 后提示词注入失效

原因：MaiBot 1.2.0 起（2026-08-05 重构）把 `maisaka.planner.before_request` /
`maisaka.replyer.before_model_request` 的载荷从 `messages`（`role/content` 字典列表）
改成了 `items`（ContextItem 快照），且宿主只认返回的 `items`。旧版插件只识别
`messages`，注入会静默失效——插件 audit 日志仍会记录 `replyer_model_prompt`，
但实际发出去的模型请求里没有任何提示词。

处理：

1. 确认插件已升级到 **v1.6.1**（检查 `_manifest.json` 的 `version`）。
2. 在 WebUI 重载插件或重启 MaiBot。
3. 私聊触发一次后，打开 MaiBot 的 `logs/maisaka_prompt/replyer/qq_private_*/` 下最新
   的请求 JSON，搜索 `[Private Humanizer 私聊增强约束]`。**只查插件自己的 audit 日志
   不可靠**（旧版也会记录成功）。

插件 v1.6.1 同时支持两代载荷：1.2.x 走 `items`（追加到 system item 的 parts），
1.0.x / 1.1.x 走 `messages`，并在 `before_request` 写入 `extra_prompt` 备份。

## `No module named 'private_humanizer'`

原因：MaiBot 用绝对路径加载 `plugin.py`，Python 没有自动把插件根目录加入模块搜索路径。

处理：确认 `plugin.py` 开头有如下逻辑：

```python
PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))
```

并确认安装目录里存在：

```text
private-humanizer/
  plugin.py
  private_humanizer/
    __init__.py
```

## 插件加载了但没有效果

优先检查：

1. `config.toml` 中 `[plugin].enabled` 是否为 `true`。
2. `target_user_ids` 是否填写了真实私聊用户 ID。
3. `target_platforms` 是否和适配器平台字段一致，例如 `qq`。
4. 当前消息是否来自私聊。群聊会被跳过。
5. 如果适配器没有传 `user_id`，可以尝试填写 `target_session_ids` 或在画像里填写 `session_id`。

## 群聊不再触发（泄露修复说明）

自 v1.6.0 起，插件按以下三层规则判断，群聊提示词注入已被硬拦截：

1. 会话 ID 形态：`qq_group_*` / `group_*` 等群形态会话 ID 在任何 hook 上都会直接拒绝，即使历史缓存曾被误标记为私聊也会被清掉（去毒）。
2. receive 阶段确认：入站消息按 `message_info.group_info` 判断群/私聊；目标用户私聊会写入确认缓存，群消息会主动清除匹配缓存。
3. 提示词文本兜底只允许明确私聊形态（`qq_private_*` 等）的会话走；空 session_id、未知形态一律拒绝，避免文本误匹配。

如果仍出现群聊注入，请确认：

- 插件目录已更新到修复版（检查 `private_humanizer/matching.py` 是否存在）。
- 修改配置后在 WebUI 重载插件或重启 MaiBot（`on_config_update` 会清空旧缓存）。
- 群聊会话 ID 是否被适配器改写成了非标准形态（此时可临时把目标限制为 `target_session_ids`）。

## 中文显示乱码

插件文件使用 UTF-8 保存。如果 PowerShell 中 `Get-Content` 显示乱码，通常是终端代码页问题，不代表插件文件损坏。

可以用支持 UTF-8 的编辑器打开，或在 PowerShell 中执行：

```powershell
chcp 65001
```

## 修改配置后没有变化

重启 MaiBot 或在 WebUI 中重载插件。插件实现了 `on_config_update`，但实际是否热更新取决于当前 MaiBot 插件运行时版本。
