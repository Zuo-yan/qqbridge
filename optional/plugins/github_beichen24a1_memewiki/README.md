# MaiBot-MemeWiki

让麦麦认得群里的**梗和黑话**。MaiBot 版梗百科插件，移植自 AstrBot 插件
[astrbot_plugin_memewiki](https://github.com/in1t1a1/astrbot_plugin_memewiki)（MIT），
**内置词库沿用原项目**：6668 条词条，随插件分发，SQLite 毫秒级查询，不联网。

## 它解决什么问题

大模型对新梗、群内黑话、缩写经常**硬猜**，或者直接说「我不知道」。

这个插件做三件事：

1. **本地词库优先**：6668 条词条随插件分发，查词走 SQLite 精确匹配，亚毫秒级
2. **模型可自主查询**：注册 `search_meme_wiki` 工具，麦麦遇到没把握的词会自己去查，不用你教
3. **先会接，再解释**：词条按「怎么用 / 出处」组织，注入的内容让模型先照用法接一句，而不是上来科普

## 安装

放进 MaiBot 的 `plugins/` 目录（`_manifest.json` 与 `plugin.py` 必须在根层）：

```bash
cd MaiBot/plugins
git clone https://github.com/beichen24a1/MaiBot-MemeWiki.git
```

或在 WebUI「插件扩展 → 从 Git 安装」里粘贴仓库地址。装好后到「管理插件」启用。

无额外 Python 依赖（只用标准库 `sqlite3`）。

## 用法

### 1. 模型自主查梗（推荐）

插件注册了 `search_meme_wiki` 工具，**但 Planner 只读「行为风格」**。
要让麦麦真的想到去查，需要在 `bot_config.toml` 的 `[personality] behavior_style` 里加一句：

```text
遇到没有十足把握的网络新词、梗、缩写、黑话，先调用 search_meme_wiki 查，别硬猜也别编；
查到之后先照着用法接一句（像本来就会），只有对方明确问「这是什么梗」才解释出处，一两句就够。
```

> 写在「群聊提示词 / 私聊提示词」里不会影响 Planner，必须写进 `behavior_style`。

### 2. 命令查询

```
/梗 绝绝子
```

返回：

```
【梗】绝绝子
【标签】网络用语、文字梗、社交媒体、网络文化
【怎么用】"xx子"是一种将形容词或名词与"子"字结合的网络用语格式…
【出处】"绝绝子"这一说法源自网络流行语格式"xx子"…
```

## 匹配规则

- 先按**完整标题**精确命中
- 否则要求**消息里包含完整标题**（反过来「消息是标题前缀」不算），按标题长度取最长
  - 「你是什么」不会命中「你是什么冠军」
  - 「你说你是什么冠军」会命中
- 都没命中时返回明确提示，让模型说不知道而不是编

## 目录结构

```
MaiBot-MemeWiki/
  _manifest.json      插件清单（plugin_type=tool）
  plugin.py           Tool + /梗 命令 + 查询
  data/memes.db       内置词库（6668 条，约 16 MB，来自原项目）
```

## 与原作者版本的区别

| | AstrBot 版 | 本移植 |
| --- | --- | --- |
| 运行框架 | AstrBot | MaiBot（`@Tool` + `@Command`） |
| 词库 | 同（沿用 `memes.db`） | 同 |
| 模型自主查 | `search_meme_wiki` 工具 | `search_meme_wiki` 工具 |
| 命令 | `/梗`、`/黑话` | `/梗`（黑话管理暂未移植） |
| 联网兜底 | 回落 cnmeme.wiki / AstrBot 搜索 | **暂未移植**，只查本地 |
| 图片卡片 | 支持 | **暂未移植**，目前纯文字 |

当前版本聚焦「本地词库 + 模型自主查询」这条主链路；黑话自建、联网兜底、图片卡片还没搬，后续再做。

## 许可

MIT。词库与原始插件版权归原作者 [in1t1a1](https://github.com/in1t1a1) 所有，本仓库是派生移植，保留原版权声明。
