# 更新日志

本项目遵循语义化版本（SemVer）。重要变更都会记录在本文件中。

## v1.6.1 (2026-08-28)

### 修复：MaiBot 1.2.x 提示词注入完全失效

- **适配新版 Hook 载荷 `items`**：MaiBot 1.2.x 把 `maisaka.planner.before_request` /
  `maisaka.replyer.before_model_request` 的载荷从 `messages`（`role/content` 字典列表）
  改为 `items`（`serialize_prompt_items` 输出的 ContextItem 快照），且宿主只认返回的
  `items`。旧版 `_find_messages` 无法识别新结构，注入静默失效（audit 仍记录成功，
  实际请求里没有提示词）。现在把提示词追加到已有 `SystemMessageItem` 的 `parts`
  （无 system item 时头部插入新 `SystemMessageItem`），幂等去重，并保留旧版
  `messages` / `extra_prompt` 兼容路径。
- **激活 `extra_prompt` 备份路径**：`maisaka.replyer.before_request` 是 1.2.x 中唯一
  会消费 `extra_prompt` 的位置（拼入「【额外回复要求】」），插件现于此阶段写入完整
  私聊增强约束，与 `items` 注入形成双保险。
- **上下文快照兼容**：`extract_last_user_message` 现可解析新版 `UserMessageItem`
  快照，回复守卫/主动续话依赖的最近用户发言不再因载荷结构变化被清空。
- **匹配兜底兼容**：prompt 文本匹配现可读取新版 `items` 载荷（新增
  `extract_message_text`，兼容旧版 `messages`），1.2.x 下最后一层兜底不再失效；
  群聊硬拦截（会话 ID 形态）逻辑不变。
- **版本号统一**：`_manifest.json` / `config.toml` / `config.py` 的 `config_version`
  同步升至 `1.6.1`，首次加载时会触发一次宿主配置合并迁移（仅补默认键，保留用户已有配置）。

## v1.6.0 (2026-08-09)

### 安全：彻底修复提示词泄露到群聊

- **会话 ID 形态识别**：MaiBot 的 stream/session id 自带类型前缀（`qq_group_*` / `qq_private_*`）。新增 `classify_session_id`，在所有 hook 上自动推导 chat_type，作为群/私聊的权威判据。
- **群聊硬拦截**：匹配链路最前面先判群，缓存与提示词兜底之前即拒绝；历史脏缓存（群会话被误标记为私聊）会被主动清除（去毒），杜绝“中毒一次、持续泄露”。
- **receive 阶段确认/去毒**：`chat.receive.after_process` 按 `message_info.group_info` 区分群/私聊；目标用户私聊写入确认缓存，群消息清除该会话的匹配缓存。
- **提示词兜底收紧**：`_match_by_prompt` 只允许明确私聊形态（`qq_private_*` / `private_*` / `dm_*` 等）的会话走；空 session_id、未知形态、群形态一律拒绝，杜绝群聊文本误匹配后缓存中毒。
- **删除全局兜底状态**：移除跨会话复用的 `_last_captured_session_id`，防止群消息污染后续私聊判断。

### 修复：目标私聊无法识别（收太紧）

- **捕获逻辑适配真实载荷**：入站消息序列化没有 `chat_type` 字段，原捕获逻辑永远无法确认私聊，导致匹配全被拒绝。改为从 `message_info.group_info` + `user_info.user_id` 推导并确认目标会话。
- **私聊形态会话 ID 直接命中**：Replyer/Planner hook 只有 `session_id=qq_private_<目标QQ>` 时也能识别目标，不再依赖缓存。

### 修复：其他问题

- **modified_kwargs 全键保真**：MaiBot 宿主用返回值**整体替换** kwargs 而非合并。所有注入/改写点改为保留原始 kwargs 全键，避免同 hook 的后续处理器（含其他插件）丢失 `session_id` / `tool_definitions` / `reply_tool_args`。
- **记忆守卫复活**：`expression.learn.before_upsert` 的真实载荷是 `session_id/situation/style`（字符串），原检查的 `items/candidates/expressions/records/data` 键不存在，守卫从未生效。现按 situation/style 拦截并中止写入；新增 `expression.learn.after_extract` 候选过滤；补充“用户喜欢/用户习惯/用户偏好”等模型自创事实句式。
- **配置布尔解析修复**：字符串形式的 `"false"` 不再被 Python `bool()` 误解析为 `True`。
- **亲密词表防误伤**：修改部分内容。
- **上下文快照**：before_model_request 阶段缓存每个目标会话的最近用户发言，回复守卫与主动续话的亲密检测不再因 after_response 无用户文本而失效；配置更新时自动清空。
- **profile_id 占位符**：默认 `"target"` 不再参与提示词文本匹配，避免误命中英文 target。

### 文档

- 新增独立 `CHANGELOG.md`，README 中的版本历史章节迁移至此。
- 更新 README 匹配策略、Hook 注册清单，以及排错文档，与 v1.6.0 实际行为一致。

---

## v1.5.0 (2026-07-16)

**Planner 群聊泄漏修复 + 匹配稳定性增强（3 项）**

- **修复 Planner 提示词泄漏到群聊**：Planner kwargs 天然缺少 `chat_type`/`group_id`，导致 `_is_private` 默认回退为私聊、user_id 匹配穿透到群聊。改为依赖 `_matched_sessions` 缓存——只有被 Replyer 阶段确认过的私聊 session 才注入 Planner 提示词，群聊 session 永远不会进入缓存，彻底阻断泄漏。
- **修复 `extract_chat_fields` 误判消息 `type` 为聊天类型**：`"scope"` 和 `"type"` 从 chat_type 搜索键中移除（过于通用，消息中的 `type: "text"` 导致 `_is_private` 错误拒绝私聊，使整个插件失效）。
- **阶段提示词隔离**：`_inject_prompt_into_messages` 注入新提示词时不再清除已存在的其他阶段 Marker（Planner 与 Replyer 提示词共存，各自 Marker 不同，互不覆盖）。

## v1.4.0 (2026-07-10)

**Planner 注入 + 回复器提示词全面精简（6 项）**

- **新增 Planner 阶段注入**：注册 `maisaka.planner.before_request` Hook，在规划器阶段注入精简版私聊画像和关键约束，避免系统优先调用默认人设而忽略插件配置。
- **修复 Marker 碰撞**：Planner 与 Replyer 使用不同的 Prompt Marker，防止 Planner 注入后 Replyer 误判为已注入而跳过。
- **精简 Planner 提示词**：时间、画像、约束信息压缩为 3-5 行紧凑格式，降低 token 开销。
- **回复器提示词全面精简**：`FACT_BOUNDARY` 从 25 行缩至 5 行，`INTIMATE_CONTEXT_RULES` 从 16 行缩至 6 行，`REPLY_STYLE_RULES` 从 15 行缩至 4 行，`EMOTIONAL_PACING_RULES` 从 16 行缩至 4 行。
- **时间工具输出压缩**：`build_time_summary` 缩至 2-3 行，`build_status_reference` 缩为单行，`build_life_schedule_reference` 缩至 2 行并合并说明规则。
- **画像和环境注入精简**：`_profile_prompt` 移除冗余说明行，`_life_environment_prompt` 自动生成模式从 5 行缩至 1 行。

## v1.3.0 (2026-07-03)

**MaiBot 1.0.10 兼容性修复与注入机制重构（5 项）**

- **注入路径重构**：移除 `inject_replyer_prompt` 的 `extra_prompt` 注入，改为仅做会话匹配跟踪；`inject_replyer_model_prompt` 作为唯一注入点，同时尝试 `modified_kwargs` 返回和原地修改消息列表两种方式，确保在 MaiBot 1.0.10 的 kwargs 传递机制下约束文本仍能到达模型。
- **新增 `_find_messages()` 方法**：多 key 命名兜底（`messages` / `message_list` / `conversation_messages` 等）+ 全 kwargs 内容检测，兼容 MaiBot 未来可能的 kwargs key 变更。
- **Hook 顺序调整**：全部回复阶段 Hook 从 `LATE` 改为 `NORMAL`，适配 MaiBot 1.0.10 的 Hook 调度时序变化。
- **依赖移除**：`append_extra_prompt` 不再被注入流程依赖（保留函数供外部调用），消除 `extra_prompt` 注入路径不可靠带来的失效风险。
- 修复 MaiBot ≥1.0.10 因 Hook 返回 `modified_kwargs` 中的 `messages` 修改未传递到实际模型请求的问题。

## v1.2.0 (2026-07-03)

**兼容性修复与 session_id 捕获增强（6 项）**

- 新增三级 session_id 捕获机制：`chat.receive.after_process` → `maisaka.replyer.before_request` → `maisaka.replyer.before_model_request`，逐级兜底。
- `extract_chat_fields` 增加 `messages` 列表搜索路径。
- `_match` 方法新增缓存 session 降级匹配，当 kwargs 提取不到 session_id 时，使用捕获的 session_id 查询 `_matched_sessions` 缓存。
- 修复 MaiBot ≥1.0.8 因 `hook_dispatcher` kwargs 替换逻辑导致多插件共存时私聊匹配失败的问题。

## v1.1.0 (2026-07-01)

**初始深度优化版**

- 基于 Fucarlosm/private-humanizer 深度修改。
- 提示词全面重写，配置重置为安全默认值。
- 新增时间感知、日程参考、虚拟生活环境、画像注入、回复守卫、记忆守卫、主动续话等功能。
- 修复 `_match()` / `_match_from_prompt_messages()` / `_schedule_followup_if_needed()` 中 session_id 获取不一致的问题；`_match()` 复用已提取的 `user_id`/`session_id` 字段，消除重复的 `extract_chat_fields` 调用。
