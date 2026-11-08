# 麦麦!来点二次元图片!

[MaiBot](https://github.com/MaiM-with-u/MaiBot) 随机二次元图片插件，基于 [cnmiw.com (MirlKoi API)](https://api.cnmiw.com/)。**无需 Pixiv 账号，无需 Token，按需直取随机图，开箱即用。**

> v4.0 起已从 Lolicon 爬取缓存模式改为 cnmiw 随机图按需直发模式。旧版的代理、压缩、标签分类、定时爬取、本地缓存均已移除。

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| 🔞 色图 / 无色图 | 两个关键词桶分别触发 NSFW / SFW 随机图，可单独开关 |
| 🎲 按需随机 | 每次触发直连 API 取随机图，不预爬不缓存 |
| 🖼️ 原图直发 | 不压缩、不重编码，base64 直发，保留画质 |
| 📋 群聊/私聊黑白名单 | 参考 napcat 适配器，可配置哪些群/私聊能发图 |
| 🔞 色图范围控制 | 在全局开关之上，按群聊白/黑名单细分色图能否发；可降级发无色图 |
| 🎯 @触发 | 群聊 @机器人 + 关键词才发图，防误触 |
| ❄️ 冷却防刷 | 两次发图最小间隔，防刷屏 |
| 🔁 近期去重 | 记住最近发过的图，命中自动重取，减少重复 |

## 🚀 快速开始

### 1. 安装

将插件文件夹放到 MaiBot 的 `plugins/` 目录下：

```
MaiBot/
└── plugins/
    └── com_claw_pixiv-crawler/
        ├── plugin.py
        ├── config.py
        ├── config.toml
        ├── _manifest.json
        └── README.md
```

依赖：`httpx`（不再需要 Pillow）。

### 2. 配置

启动 MaiBot 后在 WebUI 中配置，或直接编辑 `config.toml`：

```toml
[plugin]
enabled = true

[api]
nsfw_sort = "CDNsetu"   # 色图分类，CDN 免 Referer 更稳
sfw_sort = "CDNcat"     # 无色图分类

[chat_filter]
enabled = false          # 开启后按名单过滤
group_list_type = "blacklist"
group_list = []

[at_mode]
bot_name = "麦麦"

[send]
nsfw_keywords = ["涩图", "色图", "setu", "r18"]
sfw_keywords = ["来点图", "美图", "二次元"]
count = 1
```

### 3. 使用

```
# 群聊需 @（默认）
@麦麦 涩图        → 随机色图
@麦麦 来点图      → 随机无色图
@麦麦 美图        → 随机无色图

# 私聊直接发（默认无需 @）
涩图
来点二次元图
```

## ⚙️ 配置详解

### 图片来源 `[api]`

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `base_url` | `https://api.cnmiw.com/api.php` | API 地址，一般不改 |
| `nsfw_sort` | `CDNsetu` | 色图分类 sort。`CDNsetu`=CDN免Referer稳；`setu`=直连快但需Referer |
| `sfw_sort` | `CDNcat` | 无色图分类 sort。`CDNcat`/`cat` 同上 |
| `request_timeout` | `20.0` | 调 API 取地址的超时(秒) |
| `download_timeout` | `30.0` | 下载单图超时(秒) |

> 下载图片时插件会自动带 `Referer: https://weibo.com/`，所以 `CDNsetu`/`CDNcat` 和 `setu`/`cat` 两种链路都能用。CDN 链路更稳，推荐默认。

> 进阶可把 sort 改成其它分类：`top`(精选) `pc`(横屏) `mp`(竖屏) `random`/`iw233`(全部)，对应 `CDNtop` 等也有 CDN 变体。

### 聊天名单 `[chat_filter]`（参考 napcat 适配器）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enabled` | `false` | 关闭=所有群/私聊都能发图 |
| `group_list_type` | `blacklist` | `whitelist`=只有名单内群能发；`blacklist`=名单内群禁发 |
| `group_list` | `[]` | 群号列表 |
| `private_list_type` | `blacklist` | 私聊名单模式 |
| `private_list` | `[]` | 用户 ID 列表 |
| `reject_message` | `""` | 未通过名单的回复；留空=静默不发图 |

### 色图范围 `[nsfw_filter]`

在全局「允许色图」之上，按群聊/私聊细分色图能否发送。配合 `[chat_filter]` 和 `[send]` 可实现三档分组：不发图 / 仅无色图 / 可色图。

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enabled` | `false` | 关闭=色图只看全局「允许色图」；开启后色图还要过下方名单 |
| `group_list_type` | `whitelist` | `whitelist`=只有名单内群能发色图（保守）；`blacklist`=名单内群禁色图 |
| `group_list` | `[]` | 色图群聊名单，群号列表 |
| `private_allowed` | `true` | 私聊是否允许色图（群聊不受此项影响） |
| `fallback_to_sfw` | `true` | 色图被拦截时自动改发无色图；关闭则按 `reject_message` 处理 |
| `reject_message` | `""` | 色图被拦截且不降级时的回复；留空=静默不发图 |

**三档分组示例**：
- 某群完全不发图 → `[chat_filter]` 黑名单加入该群
- 某群只发无色图 → `[nsfw_filter]` 白名单模式，不加该群（或 blacklist 加入该群）
- 某群可发色图 → `[nsfw_filter]` 白名单模式，加入该群

### 触发条件 `[at_mode]`

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enabled` | `true` | 是否需要 @ 才触发 |
| `require_at_group` | `true` | 群聊是否需要 @ |
| `require_at_private` | `false` | 私聊是否需要 @（通常关闭） |
| `bot_name` | `麦麦` | 机器人昵称，用于检测 @ |
| `reject_message` | `""` | 未 @ 时的回复；留空=静默 |

### 发图设置 `[send]`

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `nsfw_allowed` | `true` | 是否允许色图 |
| `sfw_allowed` | `true` | 是否允许无色图 |
| `nsfw_keywords` | `["涩图","色图",...]` | 色图触发词 |
| `sfw_keywords` | `["来点图","美图",...]` | 无色图触发词 |
| `count` | `1` | 每次发几张(1~100) |
| `cooldown_sec` | `10.0` | 冷却秒数 |
| `dedup_enabled` | `true` | 是否启用近期去重 |
| `dedup_max_size` | `500` | 去重缓存条数上限 |

## 🔧 API 说明

- **端点**: `GET https://api.cnmiw.com/api.php?sort=<KEY>&type=json&num=<N>`
- **返回**: `{"pic": ["url1", "url2", ...]}`，N 最大 100
- **CDN 链路** (`CDNsetu`/`CDNcat` 等): 返回 `setu.iw233.top` 图片，免 Referer
- **直连链路** (`setu`/`cat` 等): 返回 `sinaimg.cn` 图片，需 `Referer: https://weibo.com/`（插件已自动带）
- 无需鉴权

## 📋 从旧版迁移（v3.x → v4.0）

v4.0 是大版本重构，配置结构不兼容旧版：

1. 替换 `plugin.py` / `config.py` / `config.toml` / `_manifest.json` 为新版
2. 旧配置段 `[proxy]` `[schedule]` `[storage]` 和 `[api]` 里的 `tag_templates`/`tags`/`per_tag_count`/`age_rating`/`exclude_ai`/`image_size` 已删除
3. 新增 `[chat_filter]` 段，`[send]` 拆成 `nsfw_keywords`/`sfw_keywords` 双桶
4. 旧的 `images/` 目录、`sent_images.json` 不再使用，可安全删除
5. 不再依赖 Pillow

## 📄 License

MIT
