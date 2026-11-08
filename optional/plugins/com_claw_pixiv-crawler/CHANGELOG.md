# Pixiv-Crawler 更新日志

## v4.1.0 - 色图范围控制（按群聊细分）

**日期**: 2026-07-04
**版本**: v4.0.0 → v4.1.0
**状态**: ✅ 已完成本地语法校验

---

## ✨ 新增功能

### 色图范围控制 `[nsfw_filter]`

此前 `[send].nsfw_allowed` 是全局开关，所有群聊统一生效。实际使用中有些群可以色图、有些群绝不应出现色图。新增 `[nsfw_filter]` 段，在全局开关之上按群聊/私聊细分色图能否发送。

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enabled` | `false` | 是否启用色图范围控制 |
| `group_list_type` | `whitelist` | 色图群聊名单模式（whitelist/blacklist） |
| `group_list` | `[]` | 色图群聊名单 |
| `private_allowed` | `true` | 私聊是否允许色图 |
| `fallback_to_sfw` | `true` | 色图被拦截时降级发无色图 |
| `reject_message` | `""` | 不降级时的回复，留空静默 |

逻辑：
- 色图请求到达时，若 `nsfw_filter.enabled` 为真，群聊按 `group_list_type`/`group_list` 判定，私聊看 `private_allowed`
- 色图被拦截时：`fallback_to_sfw=true` 则自动改发一张无色图（降级），否则按 `reject_message` 回复或静默
- 无色图请求不受影响

配合现有 `[chat_filter]`（能不能发图）与 `[send].nsfw_allowed`（全局色图开关），可实现三档分组：不发图 / 仅无色图 / 可色图。

## 🛠 改动

- `config.py`：新增 `NsfwFilterSection`，`at_mode`/`send` 的 `__ui_order__` 顺延，`CONFIG_SCHEMA_VERSION` → 4.1.0
- `plugin.py`：新增 `_nsfw_allowed_for_chat` / `_resolve_nsfw`，在 Command 与 Tool 的访问控制之后、发送之前接入降级/拒绝逻辑
- `config.toml`：新增 `[nsfw_filter]` 默认段，`config_version` → 4.1.0
- `_manifest.json`：版本 → 4.1.0
- `README.md`：新增「色图范围」配置说明与三档分组示例

## 🐛 修复（发布前校验发现）

- `config.py`：`download_timeout` 的 validator 回退值由 20.0 改为 30.0，与字段默认值一致。原 `request_timeout`/`download_timeout` 共用一个 validator 统一回退 20.0，导致 `download_timeout`（默认 30.0）配了非法值时静默回退到 20.0。现已拆为两个独立 validator 各自回退到自身默认值。
- `config.py`：`PixivCrawlerConfig.__ui_label__` 补 `ClassVar[str]` 类型注解，与六个子 section 风格统一（无注解的类属性 pydantic v2 本就不当字段，仅风格问题）。

## ✅ 验证项

| 验证项 | 状态 |
|--------|------|
| config.py / plugin.py 语法校验 (py_compile) | ✅ |
| 色图范围过滤 + 降级逻辑（Command/Tool 两路径） | ✅ |
| 默认关闭不影响 v4.0 行为 | ✅ |
| 无色图请求不受 nsfw_filter 影响 | ✅ |

---

## v4.0.0 - 更换 cnmiw 随机图 API，大重构

**日期**: 2026-07-04
**版本**: v3.2.3 → v4.0.0
**状态**: ✅ 已完成本地语法校验

---

## 🔄 重构概述

从基于 Lolicon API 的「爬取-缓存-分类发图」模式，整体改为基于 cnmiw.com (MirlKoi API) 的「按需随机发图」模式。新 API 只能随机出图、不能按指定标签搜索，因此删除标签分类体系；同时按需求删除代理与图片压缩。

## ✨ 新增功能

### 1. 更换图片源为 cnmiw.com (MirlKoi API)

- 端点：`GET https://api.cnmiw.com/api.php?sort=<KEY>&type=json&num=<N>`，返回 `{"pic":[url,...]}`
- 色图用 `CDNsetu`，无色图用 `CDNcat`（CDN 链路免 Referer，更稳）
- 下载图片时统一带 `Referer: https://weibo.com/`，CDN 与直连两条链路都通

### 2. 群聊/私聊黑白名单（参考 napcat 适配器）

新增 `[chat_filter]` 配置段，可限制哪些群/私聊能发图：

| 配置项 | 说明 |
|--------|------|
| `enabled` | 是否启用名单过滤 |
| `group_list_type` | `whitelist`/`blacklist` |
| `group_list` | 群号列表 |
| `private_list_type` | `whitelist`/`blacklist` |
| `private_list` | 用户 ID 列表 |
| `reject_message` | 未通过名单的回复，留空静默 |

逻辑参考 `napcat-adapter` 的 `NapCatChatFilter._is_id_allowed_by_list_policy`：whitelist=在名单内才放行，blacklist=在名单内则丢弃。

### 3. 色图/无色图双关键词桶

`[send]` 触发词拆成两组，命中哪组就发对应分类：

- `nsfw_keywords`（涩图/色图/瑟图/setu/r18…）→ 色图
- `sfw_keywords`（来点图/美图/二次元/看看腿…）→ 无色图

并新增 `nsfw_allowed` / `sfw_allowed` 总开关，可单独禁用色图。

### 4. 近期去重

内存中保留最近 N 条（默认 500）已发图片 URL，命中则自动重取，减少短时间内重复发同一张图。可开关、可配上限。

## 🗑 删除功能

- **代理**：`[proxy]` 段、`_proxy_url()`、所有 httpx `proxy=` 参数
- **图片压缩**：`_read_and_compress()`、PIL 依赖、渐进式 JPEG 重编码逻辑（改为原图 base64 直发）
- **标签/分类系统**：`tag_templates`/`tags`、分类目录、tag 解析与查询命令/Tool
- **本地缓存**：`images/` 目录读写、`sent_images.json` 持久化、总量清理
- **定时爬取**：`[schedule]` 段、爬取循环、自动补货、立刻爬取命令/Tool
- **Lolicon API**：`_fetch_batch`、`LOLICON_API`、`AGE_R18_MAP`
- **依赖 Pillow**：从 `_manifest.json` 移除

## ⚙️ 配置变更

### 版本号

- `_manifest.json`: `3.2.3` → `4.0.0`
- `CONFIG_SCHEMA_VERSION`: `3.2.3` → `4.0.0`
- `config.toml [plugin].config_version`: `3.2.3` → `4.0.0`

### 新配置结构

```
[plugin]        enabled, config_version
[api]           base_url, nsfw_sort, sfw_sort, request_timeout, download_timeout
[chat_filter]   enabled, group_list_type, group_list, private_list_type, private_list, reject_message
[at_mode]       enabled, require_at_group, require_at_private, bot_name, reject_message
[send]          nsfw_allowed, sfw_allowed, nsfw_keywords, sfw_keywords, count, cooldown_sec, dedup_enabled, dedup_max_size
```

### 不兼容说明

旧版 `[proxy]` `[schedule]` `[storage]` 段及 `[api]` 的 `tag_templates`/`tags`/`per_tag_count`/`age_rating`/`exclude_ai`/`image_size` 已删除，旧配置需替换为新版 `config.toml`。`images/` 目录与 `sent_images.json` 不再使用，可安全删除。

## 📁 文件变更

| 文件 | 变更 |
|------|------|
| `config.py` | 重写：新配置模型，去 proxy/schedule/storage/tag，加 chat_filter 与双关键词桶 |
| `plugin.py` | 重写：cnmiw 按需发图、原图直发不压缩、黑白名单、去重、Command+Tool |
| `config.toml` | 重写：新默认值 |
| `_manifest.json` | 版本升 4.0.0，描述更新，dependencies 去掉 Pillow |
| `README.md` | 重写：新功能与配置说明 |

## ✅ 验证项

| 验证项 | 状态 |
|--------|------|
| config.py / plugin.py 语法校验 (py_compile) | ✅ |
| Command 返回三元组 | ✅ |
| send.image 传 base64 原图 | ✅ |
| 黑白名单逻辑与 napcat 一致 | ✅ |
| kwargs 取 group_id/user_id 兼容 Command/Tool 路径 | ✅ |
| API 响应解析 `{"pic":[...]}` | ✅（实测） |
| CDN/直连链路下载均可用 | ✅（实测） |

---

## v3.2.3 - 命令冲突修复与动态补图

**日期**: 2026-06-12
**版本**: v3.2.2 → v3.2.3
**状态**: ✅ 已完成

---

## 🐛 修复

### 1. 修复命令太宽泛导致别的插件命令失败

**问题**: 发图 Command 使用 `pattern=r".+"` 宽匹配，会吞掉其他插件注册的命令（如 `help`、`status` 等），导致这些命令无法正常响应。

**修复**: 将发图 Command 的匹配模式从 `.+"` 改为仅在消息包含 `trigger_keywords` 时才注册匹配，避免与 MaiBot 其他插件的命令冲突。

---

## ✨ 新增功能

### 2. 动态补图：图片低于 3 张自动爬到上限

当用户请求发图或触发自动补图逻辑时，如果当前未发送图片库存低于 3 张，插件会自动触发爬取，将库存补充到配置上限。

行为说明：

- 检测时机：发图前、定时检查
- 触发阈值：未发送图片 < 3 张
- 补充目标：补到 `max_total_images` 配置上限
- 指定分类时：只补该分类
- 未指定分类时：按 `tag_templates` 全量补充

用户配置中新增参数：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `auto_refill_min` | `3` | 动态补图阈值，低于此数量自动爬取 |

---

## 📁 文件变更

| 文件 | 变更 |
|------|------|
| `plugin.py` | 修复 Command 宽匹配冲突、新增动态补图逻辑 |
| `config.py` | schema 版本升级到 3.2.3，新增 `auto_refill_min` 配置项 |
| `_manifest.json` | 插件版本升级到 3.2.3 |
| `config.toml` | 新增 `auto_refill_min` 默认配置 |

---

# Pixiv-Crawler 更新日志

## v3.2.2 - NapCat 发图稳定性修复与发布清理

**日期**: 2026-06-05
**版本**: v3.2.1 → v3.2.2
**状态**: ✅ 已完成本地语法校验

---

## ✨ 用户侧变更

- 优化静态图片发送链路：发送前统一重编码，降低 NapCat 发图超时概率
- GIF 保持原样发送，避免把动图错误转成静态图
- 默认发布包已清理本地图片库、发送记录和运行缓存，适合直接上传 GitHub

## 🛠 开发侧变更

- `plugin.py`：静态图统一重编码为更稳的 JPEG 发送
- `plugin.py`：最大边长下调到 1280，目标大小收紧到约 300KB
- `plugin.py`：新增更详细的发送日志，包含原图大小、重编码后大小、最终质量
- `config.py` / `_manifest.json` / `config.toml`：版本统一提升到 3.2.2

---

# Pixiv-Crawler 更新日志

## v3.2.0 - 分类发图与发送稳定性优化

**日期**: 2026-05-29
**版本**: v3.0.0 → v3.2.0
**状态**: ✅ 已完成本地验证

---

## ✨ 新增功能

### 1. 支持按图片分类 / tag 发图

现在可以按 `images/<tag>/` 目录作为图片分类，定向发送某一类图片。

示例：

- `看看萝莉`
- `涩图 萝莉`
- `标签: 萝莉`
- `分类：猫耳`

处理逻辑：

1. 优先解析显式语法：`tag: xxx` / `标签: xxx` / `分类: xxx`
2. 如果没有显式语法，则从现有目录名中匹配消息里的分类名
3. 多个分类同时命中时，优先选择更长、更具体的分类名
4. 如果分类不存在，会返回当前可用分类列表

### 2. 新增图片分类状态查询

新增命令和 Tool，用于查看当前图片仓库里的分类库存。

触发词：

- `图片分类`
- `分类列表`
- `tag列表`
- `标签列表`
- `有哪些tag`
- `有哪些标签`
- `查看分类`
- `查看标签`

返回示例：

```text
📁 当前图片分类：
- 萝莉: 20 张，未发送 17 张，已发送 3 张
- 猫耳: 12 张，未发送 12 张，已发送 0 张
```

新增 Tool：

- `pixiv_tag_status`：查看所有分类的总数、未发送数、已发送数

### 3. Tool 发图支持 `tag` 参数

`send_setu` Tool 新增可选参数：

| 参数 | 类型 | 说明 |
|------|------|------|
| `tag` | string | 指定图片分类，例如 `萝莉`、`猫耳`、`风景` |

LLM 路径现在也可以在理解用户意图后定向发送指定分类图片。

---

## 🚀 优化

### 1. 空分类自动补货更精准

当指定分类没有未发送图片时，如果开启 `auto_crawl_when_empty`：

- 指定了分类：只爬取该分类
- 未指定分类：保持原逻辑，执行全量模板爬取

这样可以避免用户只想要某个分类时触发全量爬取，减少无关下载和等待时间。

### 2. Command 触发改为宽匹配 + 内部动态过滤

发图命令 `setu_cmd` 改为 `pattern=r".+"`，关键词仍由 `config.toml` 的 `send.trigger_keywords` 控制。

收益：

- 修改 `trigger_keywords` 后不需要改代码里的正则
- 支持新增触发词，例如 `看看腿`、`看看脸`
- 配合内部过滤，仍能避免无关消息真正触发发图

同时，分类查询命令会在发图关键词过滤前优先分流，避免被宽匹配 Command 吞掉。

### 3. 发送模式明确为 base64 压缩发送

状态显示中的发送模式已改为：

```text
发送模式: base64压缩发送
```

说明：当前 MaiBot SDK / NapCat 链路中，`send.image + base64` 是最可靠的图片发送方式；不再在更新日志中宣传 URL 直发。

### 4. 图片压缩阈值下调，降低 NapCat 发图超时概率

压缩策略调整：

| 项目 | v3.0.0 | v3.2.0 |
|------|--------|--------|
| 触发压缩阈值 | 12MB | 500KB |
| 最大边长 | 2048px | 1600px |
| 目标大小 | 固定质量 85 | 尽量压到 400KB 内 |
| 质量策略 | 单次保存 | 85 → 75 → 60 → 45 → 30 渐进式压缩 |

效果：

- 降低 VPS / NapCat 上传大图导致 `sendMsg` 超时的概率
- 通过 PIL 重编码规避个别 JPEG 内容触发的发送异常
- 日志从 MB 粒度改为 KB 粒度，更方便观察压缩效果

---

## 🐛 修复

### 1. 修复分类查询被宽匹配发图命令抢先吞掉的问题

由于发图 Command 使用宽匹配，独立的分类查询 Command 可能无法优先命中。现已在主发图 Command 内部最前面处理分类查询关键词，保证查询命令稳定可用。

### 2. 修复指定分类库存统计不准确的问题

以下方法新增 `tag` 参数，支持按分类统计：

- `_list_all_images(tag=None)`
- `_collect_unsent_images(tag=None)`
- `_count_all_images(tag=None)`
- `_count_unsent_images(tag=None)`

现在全局库存和指定分类库存会分别计算，不再混淆。

### 3. 改善不存在分类的用户提示

当用户请求不存在的分类时，会返回：

```text
没有找到「xxx」分类。当前可用分类：...
```

避免静默失败或误以为仓库为空。

---

## ⚙️ 配置变更

### 版本号

- `_manifest.json`: `3.0.0` → `3.2.0`
- `CONFIG_SCHEMA_VERSION`: `3.0.0` → `3.2.0`
- `config.toml [plugin].config_version`: `3.0.0` → `3.2.0`

### 默认配置调整

当前本地配置调整为：

```toml
[api]
tag_templates = ["萝莉"]
exclude_ai = true

[at_mode]
bot_name = "星宫"

[send]
trigger_keywords = [
    "涩图",
    "看看腿",
    "看看脸",
]
count = 3
```

---

## 📁 文件变更

| 文件 | 变更 |
|------|------|
| `plugin.py` | 分类发图、分类状态查询、Tool tag 参数、压缩策略优化 |
| `config.py` | schema 版本升级到 3.2.0 |
| `config.toml` | 默认标签、AI 排除、bot 名、触发词更新 |
| `_manifest.json` | 插件版本升级到 3.2.0 |
| `.gitignore` | 新增本地忽略规则 |

---

## ✅ 验证项

| 验证项 | 状态 |
|--------|------|
| 插件版本号更新 | ✅ |
| 分类目录扫描 | ✅ |
| 指定分类未发送图片收集 | ✅ |
| 不存在分类提示 | ✅ |
| 分类状态文本生成 | ✅ |
| Tool `tag` 参数注册 | ✅ |
| 图片压缩策略更新 | ✅ |
| 状态显示发送模式修正 | ✅ |

---

## ⚠️ 兼容性说明

- 仍然使用 `images/<tag>/` 目录结构，无需迁移图片文件。
- `sent_images.json` 的已发送记录格式保持兼容。
- 旧的全局随机发图行为保留；不指定分类时仍从全仓库随机挑图。
- `send.image + base64` 仍是当前可靠发送路径；不依赖 URL 直发能力。
