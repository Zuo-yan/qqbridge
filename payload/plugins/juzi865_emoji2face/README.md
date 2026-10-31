# Emoji 转 QQ 表情

让麦麦发消息时，把 Unicode emoji（😊😂👍）自动替换成 QQ 原生小黄脸表情。

## 效果

| 原本发送 | 实际渲染 |
|---|---|
| `今天天气真好啊 😊` | 今天天气真好啊 ![微笑](https://img.gtimg.com/open/app/faces/0.png) |
| `笑死我了 😂` | 笑死我了 ![破涕为笑](https://img.gtimg.com/open/app/faces/14.png) |
| `给你点赞 👍` | 给你点赞 ![强](https://img.gtimg.com/open/app/faces/76.png) |

QQ 原生表情在手机和 PC 端都显示为统一的小黄脸，比 Unicode emoji 在不同设备上形状各异更自然。

> ⚠️ **适用范围说明**  
> 本插件仅处理 **标准 Unicode emoji**（😊😂👍 等通用字符）到 **QQ 内置小黄脸（face 类型）** 的转换。  
> **不支持** QQ 原创表情（如菜汪）、魔法表情（mface）、大表情（bface）等腾讯私有表情类型。
> 如需发送上述表情请使用其他插件或手动构造消息段。

## 原理

1. 通过 `send_service.before_send` 钩子拦截每一条出站消息
2. 扫描文本段中的 Unicode emoji character
3. 用内置映射表查到对应的 QQ face ID
4. 把 emoji 拆成独立的 `face` 消息段注入消息体
5. SnowLuma adapter 展开后以 OneBot `{"type":"face","data":{"id":"14"}}` 格式发送到 QQ

## 前置要求

SnowLuma adapter 需要增加一段 6 行的代码，让 `_convert_outbound_segments()` 能识别 emoji2face 注入的 `dict` 包裹消息段。

### 修改 SnowLuma adapter

打开 `modules/MaiBot/plugins/snowluma-adapter/plugin.py`，找到 `_convert_outbound_segments()` 方法。在最后一个 `continue` 之后、`跳过无法转换的出站消息段` 的日志行**之前**，插入以下代码：

```python
            if item_type == "dict" and isinstance(item_data, Mapping):
                wrapped_type = str(item_data.get("type") or "").strip()
                wrapped_data = item_data.get("data")
                if wrapped_type in {"face", "mface", "bface"}:
                    segments.append({"type": wrapped_type, "data": wrapped_data if isinstance(wrapped_data, dict) else {}})
                    continue
```

参考位置（GitHub commit 锚点参考）：

```
plugin.py 第 2375 行附近
```

从 `self.ctx.logger.debug(f"SnowLuma 跳过无法转换的出站消息段..."）` 这行往前数的最后一个 `continue` 之后插入。完整上下文参见仓库中的 [plugin.py](../../snowluma-adapter/plugin.py)。

修改后保存即可，无需重启 MaiBot——执行 `/pm plugin reload snowluma-adapter` 热重载适配器。

> ⚠️ **关于 adapter 兼容性**  
> 上述修改针对 SnowLuma adapter 当前版本的 `_convert_outbound_segments()` 实现。如果 SnowLuma adapter 后续更新，
> 该补丁可能被覆盖或失效，需要重新检查并应用。建议在更新 SnowLuma adapter 后主动验证 emoji 转换是否正常工作。

## 安装

将 `emoji2face/` 目录放入 `modules/MaiBot/plugins/` 后执行插件重载：

```
/pm plugin reload emoji2face
```

确认日志出现：

```
[runner:emoji2face] 插件已加载
```

## 配置

`config.toml`：

```toml
[plugin]
enabled = true

[convert]
mode = "auto"
max_emoji_per_message = 5
```

| 参数 | 默认值 | 说明 |
|---|---|---|
| `enabled` | `true` | 总开关 |
| `mode` | `"auto"` | `auto` = 仅转映射表中有的 emoji；`all` = 尝试转换所有；`off` = 关闭 |
| `max_emoji_per_message` | `5` | 单条消息最多转换的 emoji 数量，防止刷屏 |

修改配置后执行 `/pm plugin reload emoji2face` 热重载生效。

## 映射表覆盖范围

当前内置 127 条映射，覆盖常见类别：

- 😀😊😍😘 等积极表情 → 微笑、色、亲亲等
- 😂🤣😆 等大笑表情 → 呲牙、惊讶
- 😢😭😤😠 等负面表情 → 大哭、发怒等
- 👍👏👊🙏 等手势 → 鼓掌、敲打等
- ❤️💔💋 等符号 → 爱心、心碎等
- 🍉🍺☕ 等食物 → 西瓜、啤酒等
- 🐷🐱🐶 等动物 → 猪头、可爱等
- 🌹💐 等植物 → 玫瑰
- ⚽🏀 等运动 → 足球、篮球等
- ⚡💣💩 等物品 → 闪电、炸弹、便便等

没有对应 QQ 表情的 emoji（如 🦄🛸）不会被转换，保持原样发送。

## 常见问题

**Q: 为什么发了表情但 QQ 显示为方框/空白？**
A: 确认 SnowLuma adapter 已按要求修改代码并重载。检查 MaiBot 日志是否有 `跳过无法转换的出站消息段: type=dict`——如有说明 adapter 修改未生效。

**Q: 不想转换某些表情怎么办？**
A: 当前不支持白名单过滤。如需跳过，可将 `mode` 设为 `"off"` 临时关闭。

**Q: 支持 QQ 原创表情（菜汪）和魔法表情吗？**
A: 不支持。本插件的映射表只覆盖标准 Unicode emoji → QQ 内置小黄脸 ID。``mface``/``bface`` 等类型没有公开的 ID 文档，且每个原创表情的 emotion_id 是腾讯私有的，无法事先枚举。如果你有已知的原创表情 ID，可在其他插件中直接构造 OneBot 段 `{"type":"mface","data":{"emotion_id":"xxx"}}` 发送——SnowLuma adapter 已经在本文的修改中支持了 mface/bface 透传。

**Q: 会影响其他插件发送的消息吗？**
A: 不影响。钩子对所有出站消息统一处理，其他插件无需改动。

**Q: QQ face ID 和 emoji 的对应关系不准怎么办？**
A: 映射表在 `plugin.py` 中的 `_EMOJI_TO_FACE` 字典里，可自行增删改条目后重载插件生效。

## 许可证

MIT
