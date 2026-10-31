# 麦麦私聊拟人化增强

> 基于 Fucarlosm/private-humanizer（原项目已删库）深度修改与优化而来。
>
> 原始作者：[Fucarlosm](https://github.com/Fucarlosm) · 原始许可：MIT

---

## 免责声明

1. **本插件仅供学习、研究和个人娱乐用途。** 不得用于任何违法、违规或侵犯他人权益的场景，包括但不限于骚扰、欺诈、冒充他人、传播违法信息等。
2. 插件通过向 MaiBot 的 LLM 请求注入提示词约束来影响回复风格，**不保证在所有 LLM 模型上生效**。不同模型的指令遵循能力差异较大：部分模型可能完全忽略约束、部分模型可能过度遵守导致回复僵硬、部分模型可能只遵守一部分规则。模型也可能在未被守卫拦截的情况下产生不符合约束的回复。
3. 插件内置的"事实守卫"和"记忆守卫"均为**基于正则表达式和关键词的规则级检查**，无法做到 100% 精确——既可能漏过编造内容（漏报），也可能拦截合理的正常回复（误报）。守卫对 LLM 已经生成的文本只能做事后检测和替换，**无法阻止模型在生成阶段的方向**。请根据实际体验调整 `[guard]` 下的开关，必要时关闭特定守卫。
4. **亲密上下文连续性守卫**依赖 `INTIMATE_TERMS` 硬编码关键词列表（`guards.py`）判断上下文是否处于亲密状态。该列表仅覆盖明确的性暗示词汇，**无法识别所有亲密、暧昧或情感升温的表达方式**，存在漏检可能。如果使用场景对亲密话题跳转无要求，可关闭 `style_guard_enabled`。
5. 主动续话功能会在 MaiBot 回复后延迟触发低优先级主动任务。**如果目标用户对"机器人主动说话"敏感，请在 `[proactive_followup]` 中关闭 `enabled`。** 主动续话由 Maisaka 引擎最终决定是否发送，插件无法保证每次触发都会实际发出消息，也无法保证发出的内容完全符合预期。
6. **插件注入的提示词包含当前时间、虚拟日程、虚拟生活环境和自生成的生活状态**——这些内容均为根据时段自动生成的虚构参考信息，**不是 MaiBot 的真实状态，也不是插件作者的生活事实**。它们仅用于让回复带有时间感和生活气息，请勿将其误解为真实信息。配置中的 `manual_status` 和 `manual_schedule` 字段同理。
7. 插件写入的审计日志默认不包含私聊原文（`save_rewrite_pairs = false`）。**如需排查问题临时开启，排查结束后务必关回 `false`**，保护目标用户隐私。日志文件位于插件目录下的 `logs/` 文件夹，以 `private-humanizer-YYYY-MM-DD.jsonl` 格式保存，**不会自动清理，也不会自动轮转**，请定期检查和删除过期日志。
8. 配置文件中的 `custom_dates` 字段支持填写生日、纪念日等个人日期，这些信息会直接出现在注入 LLM 的提示词中，**每次该目标的私聊触发时都会携带**。请勿填写他人未经授权的隐私信息；不确定的日期请留空。
9. **提示词注入会增加每次 LLM 请求的 token 消耗**。完整约束块（时间、状态、日程、环境、画像、事实边界、亲密规则、风格规则、情绪规则）总计约 1500-3000 个中文字符，加上 `extra_prompt` 备份与 `items`/`messages` 两条注入路径同时生效，实际 token 开销取决于所用模型的 tokenizer。如果对 token 成本敏感，可关闭不用的功能段（如 `life_environment.enabled`、`schedule.enabled`）来减小提示词体积。
10. 本插件**必须配置至少一个 `target_user_ids` 或 `[[target_profiles]].user_id` 才能生效**。默认 `config.toml` 中这两个字段均为空，插件不会匹配任何用户，不会产生任何效果，也不会消耗 token。
11. 配置 `inject_into_planner = true` 时，提示词会注入到 Planner 阶段，Payload 较 replyer 注入更小（精简版），但仍会略微增加 token 消耗。如不需要可在 `[schedule]` 中关闭。
12. **记忆守卫拦截 `expression.learn.after_extract`（候选过滤）与 `expression.learn.before_upsert`（写入前中止）两条 Hook 路径**，不拦截 MaiBot 其他记忆写入路径（如手动添加、数据库直接写入等）。如果 MaiBot 启用了其他记忆插件或自定义记忆逻辑，本插件的记忆守卫可能无法覆盖。
13. 本插件只读取自身目录下的 `config.toml`，不修改 MaiBot 主配置文件、数据库或系统文件。插件运行时会读取配置并在内存中维护匹配缓存和续话历史，卸载或配置更新时自动清理。
14. 使用者应自行评估功能对聊天体验的影响，**作者不对因使用本插件产生的任何后果承担责任**，包括但不限于：回复质量下降、误拦截关键信息、亲密场景话题跳转未被阻止、主动续话造成打扰、token 成本增加、日志文件占用磁盘空间等。

---

## 📌 版本兼容性

- **兼容版本**：MaiBot **1.0.0 ~ 1.99.99**（当前插件版本 v1.6.1）。
- **两代 Hook 载荷自动适配**：MaiBot 1.2.0 起把 `before_request` / `before_model_request` 的消息载荷从 `messages`（`role/content` 字典）重构为 `items`（ContextItem 快照）。插件 v1.6.1 同时支持两种载荷——1.2.x 走 `items` 注入（追加到 system item 的 parts），1.0.x / 1.1.x 走 `messages` 注入；并在 `maisaka.replyer.before_request` 写入 `extra_prompt` 备份（该位置在所有 1.x 版本都会被宿主消费，拼入「【额外回复要求】」）。
- **kwargs 替换语义**：MaiBot 核心 `hook_dispatcher` 用 `dict(...)` **整体替换** kwargs 而非合并，多插件共用同一 Hook 点时后注册的插件可能拿不到 `session_id` 等关键参数。插件所有注入/改写返回都**合并保留原始 kwargs 全键**，并内置三级 session_id 捕获机制（消息接收 → before_request → before_model_request）和 `extract_chat_fields` 额外搜索路径，在 kwargs 被替换后仍可恢复会话 ID。
- **群聊硬拦截**：会话 ID 形态识别 + receive 阶段确认/去毒，详见 [CHANGELOG.md](CHANGELOG.md)。

---

## 优化改动（相对原版）

以下为本次深度优化涉及的改动点，沿用原始架构但做了大量调整：

| 类别 | 改动内容 |
|------|----------|
| **隐私安全** | `save_rewrite_pairs` 默认关闭；新增 `.gitignore` 排除日志与备份目录 |
| **提示词重构** | 取消按场景分级的硬性字数上限，改为自然长度策略；消除 FACT_BOUNDARY/INTIMATE/EMOTIONAL 段落间的内部矛盾；重构编造陷阱为清晰的"句式 → 实质"对照；合并重复规则减少冗余 |
| **守卫阈值** | `max_reply_chars_soft` 80→400，`max_reply_chars_hard` 160→800，仅在极端小说化时介入 |
| **守卫逻辑** | 移除单字场景词（"躺/蜷/蹭"）及日常高频词（"沙发/窗外/灯光/香气"）减少误匹配；INTIMATE_TERMS 从 8 个扩展到 12 个覆盖轻度亲密场景；证据验证引入 18 个 stop words；记忆守卫不再检查 dict key |
| **匹配策略** | profile 未指定平台时继承全局 `target_platforms` 约束，防止跨平台误匹配；prompt 文本匹配增加最短候选名过滤 |
| **时间工具** | 去掉 `build_status_reference` 和日程参考中"简短/少写/不制造"等限制性语言；`Asia/Urumqi` 时区偏移修正为 UTC+6 |
| **配置修复** | `config.toml` 重置为代码默认值；`cooldown_seconds` 默认统一为 180 秒 |
| **确定性** | `_intimate_bridge_fallback` 用 `hashlib.sha256` 取代 `hash() ^ id()`，确保同输入可重现 |
| **测试适配** | `test_memory_guard_handles_dict_items` 适配 dict key 不再检查的逻辑 |

## 功能概述

本插件**只读取自身目录下的 `config.toml`**，不依赖 MaiBot 主配置。核心能力：

- **私聊匹配**：仅对 `target_user_ids` 或 `target_profiles` 中配置的目标私聊生效，不影响群聊和其他联系人。
- **时间与日程注入**：在回复阶段告知 LLM 当前日期、星期、时段、近期节假日和轻量日程参考，让回复带有真实的时间感。
- **私聊对象画像**：将你填写的基础信息、偏好、重要日期和关系说明注入私聊提示词，LLM 只能使用已确认的内容。
- **回复风格约束**：引导 LLM 自然调整回复长度（而非硬性字数限制），限制动作描写密度、禁止小说体叙事和预设未来，仅在极端情况下由守卫介入压缩。
- **事实边界守卫**：检查 LLM 回复中的无证据事实、纪念日猜测、过度动作描写，触发后改写为坦承不知道的回复。
- **记忆守卫**：在"表达学习"写入前拦截疑似模型自创的个人事实（如"用户最喜欢桃子汽水"），避免污染长期记忆。
- **主动续话**：回复发出后延迟检查是否需要自然补一句短消息（支持亲密场景的专属续话策略），内置冷却和每小时上限。

---

## 安装

1. 将整个 `private-humanizer` 文件夹放入 MaiBot 的 `plugins/` 目录。
2. **修改 `config.toml`**——这是必须步骤：
   - 在 `[plugin]` 中填写 `target_user_ids`（如 `["123456789"]`）。
   - 在 `[[target_profiles]]` 中至少填写 `user_id` 和 `display_name`。
3. 重启 MaiBot，或在 WebUI 中重新加载插件。

> 默认 `config.toml` 已将 `target_user_ids` 设为空数组 `[]`，插件不会匹配任何用户。未配置前无任何效果。

---

## 最小配置示例

```toml
[plugin]
enabled = true
target_user_ids = ["123456789"]

[[target_profiles]]
profile_id = "target"
platform = "qq"
user_id = "123456789"
display_name = "目标私聊对象"
basic_info = "称呼偏好：目标私聊对象\n所在地区：未知\n作息：未知\n"
preferences = "聊天偏好：自然、有回应感\n"
important_dates = ""
relationship_notes = "不要编造未确认的偏好、礼物、纪念日或共同经历。"
```

**重要：** 未填写的画像字段会被视为"未知"。插件会要求 LLM 保持"不确定/询问/基于当前对话回应"，而不是猜测。

---

## 配置项详解

### `[plugin]` — 基础设置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `config_version` | str | `"1.6.1"` | 配置版本号，由插件管理，请勿手动修改 |
| `enabled` | bool | `true` | 插件开关 |
| `private_only` | bool | `true` | 仅私聊生效，建议保持开启 |
| `target_platforms` | list | `["qq"]` | 生效平台，QQ 填写 `"qq"` |
| `target_user_ids` | list | `[]` | **必填**，目标 QQ 号列表 |
| `target_session_ids` | list | `[]` | 通常留空；无法按 user_id 识别时使用 |

### `[time_awareness]` — 时间感知

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `true` | 注入日期、星期、时段信息 |
| `timezone` | str | `"Asia/Shanghai"` | 时区 |
| `holiday_region` | str | `"CN"` | 节假日地区标识，保留字段 |
| `custom_dates_enabled` | bool | `true` | 是否启用下方的自定义重要日期 |
| `custom_dates` | list | `[]` | 自定义重要日期，格式 `{name, date, description}`，不确定的请留空 |

### `[schedule]` — 日程参考

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `true` | 启用日程参考 |
| `generation_mode` | str | `"daily"` | 生成模式，保持 `daily` 即可 |
| `refresh_hours` | list | `[7, 12, 18, 22]` | 状态刷新小时，用于区分时段 |
| `inject_into_replyer` | bool | `true` | 注入 Replyer 阶段（推荐） |
| `inject_into_planner` | bool | `true` | 注入 Planner 阶段（精简版画像+约束） |
| `manual_status` | str | `""` | 手动今日状态，非空时覆盖自动生成 |
| `manual_schedule` | str | `""` | 手动日程参考，非空时覆盖自动生成 |
| `reference_only` | bool | `true` | 日程仅作语气参考，不是事实 |
| `allow_user_interrupt` | bool | `true` | 用户可打断日程引导 |

### `[life_environment]` — 虚拟生活环境

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `true` | 注入虚拟生活环境 |
| `environment` | str | `""` | 固定环境描述，留空由 LLM 自动生成 |
| `auto_generate_when_empty` | bool | `true` | 环境为空时自动生成 |
| `use_as_reference_only` | bool | `true` | 仅作背景参考，不主动扩写 |

### `[profile]` — 画像规则

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `true` | 注入私聊画像 |
| `inject_into_private_prompt` | bool | `true` | 写入私聊提示词 |
| `require_evidence_for_preferences` | bool | `true` | 偏好必须有证据（空白字段视为未知） |

### `[[target_profiles]]` — 私聊对象画像

| 字段 | 类型 | 说明 |
|------|------|------|
| `profile_id` | str | 内部标识，默认 `"target"` |
| `platform` | str | 平台，QQ 填 `"qq"` |
| `user_id` | str | **必填**，目标 QQ 号 |
| `display_name` | str | LLM 识别该对象使用的称呼 |
| `basic_info` | str | 只写确定事实，不知道写"未知" |
| `preferences` | str | 只写确认过的偏好 |
| `important_dates` | str | 只有确认过的日期才填 |
| `relationship_notes` | str | 关系说明与禁忌事项 |

### `[guard]` — 回复守卫

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `fact_guard_enabled` | bool | `true` | 拦截无证据事实 |
| `anniversary_guard_enabled` | bool | `true` | 拦截纪念日/日期猜测 |
| `style_guard_enabled` | bool | `true` | 拦截过长/小说化回复 |
| `memory_guard_enabled` | bool | `true` | 拦截可疑记忆写入 |
| `max_reply_chars_soft` | int | `400` | 软上限，场景词≥3 且超过此长度触发压缩 |
| `max_reply_chars_hard` | int | `800` | 硬上限，触发后强制截断在附近 |

### `[proactive_followup]` — 主动续话

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `true` | 开启主动续话 |
| `delay_seconds` | int | `35` | 延迟秒数（20-60 推荐） |
| `cooldown_seconds` | int | `180` | 同会话最小间隔 |
| `max_per_hour` | int | `6` | 每小时最多触发次数，`0` 不限 |
| `min_reply_chars` | int | `2` | 上条回复短于此不触发 |
| `intent` | str | （默认续话意图） | 传给 Maisaka 主动任务的意图说明；亲密场景自动切换为更严格的亲密续话意图 |

### `[logging]` — 日志审计

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `true` | 记录拦截/改写/续话行为 |
| `log_level` | str | `"info"` | 日志等级 |
| `save_rewrite_pairs` | bool | `false` | **隐私敏感**，建议永远保持 `false` |

---

## Hook 注册清单

插件在 MaiBot 中注册了以下 Hook（均在 `plugin.py` 中定义）：

| Hook 点 | 方法 | 时机 | 行为 |
|---------|------|------|------|
| `chat.receive.after_process` | `capture_receive` | 消息接收后（EARLY） | [1/3] 捕获 session_id，按 `message_info` 确认目标私聊 / 群聊去毒 |
| `maisaka.replyer.before_request` | `capture_before_request` | 回复请求前（EARLY） | [2/3] 捕获 session_id |
| `maisaka.replyer.before_model_request` | `capture_before_model` | 模型调用前（EARLY） | [3/3] 捕获 session_id |
| `maisaka.planner.before_request` | `inject_planner_prompt` | 规划器请求前（EARLY） | 注入精简版私聊画像和约束（1.2.x `items` / 旧版 `messages`） |
| `maisaka.replyer.before_request` | `inject_replyer_prompt` | 回复请求前（NORMAL） | 匹配和跟踪私聊会话 + 写入 `extra_prompt` 备份 |
| `maisaka.replyer.before_model_request` | `inject_replyer_model_prompt` | 模型调用前（NORMAL） | 注入完整私聊增强约束（1.2.x `items` / 旧版 `messages`） |
| `maisaka.replyer.after_response` | `guard_reply` | 回复生成后（NORMAL） | 规则守卫 + 调度主动续话 |
| `expression.learn.after_extract` | `filter_extracted_memory` | 表达候选解析后（EARLY） | 过滤包含可疑个人事实的表达候选 |
| `expression.learn.before_upsert` | `guard_expression_memory` | 表达学习写入前（EARLY） | 拦截 situation/style 中的可疑个人事实并中止写入 |

所有 Hook 均为 `BLOCKING` 模式，出错策略为 `SKIP`（出错时不阻塞主流程）。

---

## 主动续话工作原理

1. 每次守卫检查通过后，`FollowupManager.schedule_if_needed` 判断是否满足条件：
   - 开启且满足最短回复长度
   - 无重试（`retry_count == 0`）
   - 没有该会话的进行中续话任务
   - 未触及每小时上限和冷却
2. 满足条件时创建异步 Task，延迟 `delay_seconds` 秒后执行。
3. 延迟期间检测上下文（含 before_model_request 阶段缓存的最近用户发言快照）是否为亲密场景，选择普通续话意图或亲密续话意图。
4. 调用 `ctx.maisaka.proactive.trigger()`，由 Maisaka 自行判断是否真正发送。
5. 发送成功后记录时间戳到冷却历史。

**亲密续话**：上下文中检测到 `INTIMATE_TERMS`（`guards.py` 中定义）时，使用 `INTIMATE_FOLLOWUP_INTENT` 替代默认意图，包含更严格的亲密连续性约束。

---

## 匹配策略

插件采用“群聊硬拦截 + 确认缓存优先 + 兜底受限”的匹配策略：

| 优先级 | 策略 | 说明 |
|--------|------|------|
| 0 | 群聊硬拦截 | `qq_group_*` / `group_*` 等群形态会话 ID、显式 `group_id` 或 `chat_type=group` 直接拒绝，并清除该会话的历史匹配缓存（去毒） |
| 1 | 标准字段匹配 | `user_id` / `session_id` / `platform` 与目标配置匹配；私聊形态会话 ID 内嵌目标 QQ（如 `qq_private_3130274394`）时无需 user_id 也可直接命中 |
| 2 | 确认缓存匹配 | receive 阶段已确认的目标私聊会话，后续只有 session_id 的 hook 直接命中 |
| 3 | Prompt 文本兜底 | **仅限明确私聊形态会话**；扫描 messages 中是否出现画像的 `display_name` / `user_id`（占位 `profile_id="target"` 除外） |

匹配时还会检查：
- **会话 ID 形态**：`qq_group_*` / `group_*` 判定为群，`qq_private_*` / `private_*` / `dm_*` 判定为私聊；这是模型请求阶段（只有 session_id）最可靠的判定依据。
- **receive 阶段确认**：入站消息按 `message_info.group_info` 区分群/私聊；目标用户私聊写入确认缓存，群消息清除匹配缓存。
- **群聊过滤**：`private_only = true` 时拒绝 group/guild/channel 及含 `group_id` 的消息。
- **平台过滤**：`target_platforms` 非空时拒绝不在列表中的平台。
- **Prompt 群信号检测**：提示词兜底前扫描文本中的群聊特征关键词，作为会话 ID 之外的二次防线。

---

## 提示词注入机制

每次触发时会构造一个约束块（`[Private Humanizer 私聊增强约束]`），按顺序包含：

1. 当前时间（日期、星期、时段、近期节假日）
2. 今日状态（自动生成的时段状态）
3. 日程参考（当前时段行为候选 + 使用规则）
4. 生活环境（固定或自动生成的假设）
5. 目标画像（确认字段列表）
6. 事实边界（信息来源分级 + 禁止项 + 不确定处理）
7. 亲密连续性（启动/保持/回应/退出规则）
8. 回复风格（长度/内容/动作/禁止模式）
9. 情绪节奏（跟随/预设/收束/时间感知）

在 Replyer 阶段通过 `before_model_request` 注入：MaiBot 1.2.x 为 `items`（ContextItem 快照，追加到 system item 的 parts），1.0.x / 1.1.x 为 `messages`（`role/content` 字典）；同时通过 `before_request` 的 `extra_prompt` 备份路径确保兼容性（宿主会拼入「【额外回复要求】」）。两条路径均按 marker 幂等去重，不会重复注入。
Planner 阶段注入精简版（时间 + 画像 + 关键约束），同样自动适配 `items` / `messages` 两种载荷，详见 `build_planner_prompt`。

---

## 审计日志

日志文件位于 `logs/private-humanizer-YYYY-MM-DD.jsonl`，每行一条 JSON 记录。包含字段：

```json
{
  "time": "2026-06-28 14:30:00",
  "stage": "replyer_prompt | replyer_model_prompt | reply_guard | memory_guard | followup_triggered | followup_failed | followup_skipped",
  "chat_id": "...",
  "user_id": "...",
  "risk_type": "unsupported_fact,anniversary_guess,novelistic_style,intimate_topic_shift,unverified_memory"
}
```

当 `save_rewrite_pairs = true` 时，`reply_guard` 记录会额外包含 `original_reply` 和 `rewritten_reply` 字段——**仅限排查时临时开启**。

---

## 常见问题

### 插件已启用，但没有任何效果？

检查 `config.toml`：
- `target_user_ids` 和 `[[target_profiles]].user_id` 是否填写了目标 QQ 号？
- `plugin.enabled` 是否为 `true`？
- `schedule.inject_into_replyer` 是否为 `true`？

### 守卫把正常的回复拦截了怎么办？

- 先在 `[logging]` 中临时设置 `save_rewrite_pairs = true`，观察日志中的 `risk_type` 和 `original_reply`。
- 根据被拦截的类型，关闭 `[guard]` 中对应的守卫开关（`fact_guard_enabled` / `anniversary_guard_enabled` / `style_guard_enabled`）。
- 排查完毕后改回 `save_rewrite_pairs = false`。

### 回复被守卫压缩了怎么办？

- 当前风格守卫阈值较宽松（`max_reply_chars_soft = 400`，`max_reply_chars_hard = 800`），只在极端小说化时触发。
- 如果仍然触发，检查是否回复中堆砌了大量场景描写词汇（`SCENE_WORDS`）。可适当减少动作和环境描写。
- 上述阈值和新默认值参见 `[guard]` 配置段。

### 主动续话太频繁/太打扰？

- 增大 `cooldown_seconds`（如 600-900）。
- 减小 `max_per_hour`（如 1-2）。
- 或直接关闭 `proactive_followup.enabled`。

### 想对另一个私聊对象也生效？

在 `[[target_profiles]]` 中追加一个新条目，填写不同的 `profile_id` 和 `user_id`：

```toml
[[target_profiles]]
profile_id = "target2"
platform = "qq"
user_id = "987654321"
display_name = "另一个对象"
# ... 画像字段
```

同时在 `target_user_ids` 中追加：

```toml
target_user_ids = ["123456789", "987654321"]
```

### 某些模型不遵守提示词约束怎么办？

不同 LLM 的指令遵循能力差异显著。如果发现约束经常被忽略：
- 检查模型的 system prompt 优先级机制（部分模型对"最终消息中的 system 角色文本"响应更好）。
- 尝试使用指令遵循能力更强的模型。
- 插件在 `before_model_request` 阶段同时通过 `items`（1.2.x）/ `messages`（旧版）直接注入，并在 `before_request` 阶段写入 `extra_prompt` 备份，以最大化兼容性。

---

## 离线测试

在插件根目录运行：

```bash
python -m unittest discover -s tests
```

当前覆盖：配置加载（含字符串布尔解析）、私聊匹配（含群聊硬拦截 / 缓存去毒 / 会话 ID 形态识别）、守卫逻辑（事实/纪念日/风格/记忆/亲密话题转移）、上下文快照与提示词构建、1.2.x `items` 载荷注入与 ContextItem 快照解析。

---

## 更新日志

完整版本历史见 [CHANGELOG.md](CHANGELOG.md)。
