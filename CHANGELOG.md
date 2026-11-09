# 更新记录

## 1.3.8

- 模型路由与延迟优化：将主要回复 (`replyer`) 与视觉 (`vlm`) 任务首选模型调整为 Gemini 3.8 Flash (`vertex_flash`)，配合 Visible Grace 流式保底机制，消除原先回退等待的 6s 延迟并大幅提升首字生成与交互响应速度。
- 动态好感度与群友印象静默感知：启用 `com_0-hz_impression-card` 轻量级后台自刷新机制 (`light_refresh`)，关闭公屏加减分广播通知（`notify.enabled = false`），人设接入后台静默印象维护与好感度动态调整。
- 语音情感参数拓展与傲娇声线对齐：扩展 `xuqian13_tts_voice_plugin` 豆包后端情感映射表，新增「傲娇」、「撒娇」、「别扭」、「调侃」等多重声线模式并支持自定义提示词；人设与 Action 规范深度联动，根据聊天语境自适应匹配语音情感。

## 1.3.7

- 人设性格与攻击性深度优化：建立「主人/熟人/生人/挑衅/求助」五层因人而异的态度机制，严禁千人一面或无差别贴吧开喷；收敛日常无端粗口与攻击性。
- 傲娇受挫与软化退让机制：增加核心情绪保护逻辑——当察觉对方动真格、真的生气、不耐烦或情绪受委屈时，严禁硬刚、反问或火上浇油，不卑微道歉，而是语气迅速软化、嘴硬借坡下驴并主动给出下台阶。

## 1.3.6

- 语音合成与富媒体超时优化：NapCat OneBot `baseTimeout` 与 `sendMsg` 默认发送等待超时放宽至 30s（原 10s），彻底解决长语音及富媒体上传耗时超过 10s 导致误报超时失败的假死问题。
- 静默错误处理：将 `xuqian13_tts_voice_plugin` 的 `send_error_messages` 默认设为 `false`，屏蔽向群聊公屏推送 `语音合成失败: 语音发送失败` 等系统级扰民提示。

## 1.3.5

- 主动私聊与虚拟锚点修复：修复主动私聊虚拟锚点解析、群消息回填污染及前置异常预留锁释放。

## 1.3.3

- 帕累托最优加固：释放 `host_bridge.py` 与 `vertex_responses_gateway.py` (v1.2.0) 在网络 I/O 期间的全局锁，支持并发请求、将 `MAX_TOKENS` 映射为 `incomplete` 终态并提升最大输出上限至 32768。
- 规划器回退加速：将 `planner` 设为 `deepseek_flash -> vertex_flash` 顺序回退，并在 `utils_model.py` (v1.3.0) 为 `planner` 的主模型 `deepseek_flash` 配置 20s 单次尝试超时上限。
- 路由与通知修复：修复 `chat.open_session` 唯一账号解析（`session_route.py`）与插件虚拟通知引用跳过逻辑（`reply.py`）。
- 插件与元数据同步：同步 `chartyr_maiwork` v0.16.8、对齐 `maibot-community_mai-life` v1.23.8 版本常量、放宽 `com_0-hz_impression-card` v0.3.7 SDK 版本上限至 `2.99.99`。

## 1.3.1

- 同步线上最终回复、视觉、规划方向、表情和媒体任务路由补丁；镜像直接复制最终源文件，不重复执行一次性修改脚本。
- 更新已有插件的修复源码；补充生活、表情选择、后台文件任务、媒体交付等可选源码与运行依赖说明，不自动启用额外插件。
- 收录 Codex SDK/Vertex 后台运行器、历史核对补发及 NapCat 发送证据/临时私聊目标修复；移除默认载荷中的旧 maibot-moepix。
- 保留安装器的凭据模板；不包含线上配置、私人关系、人设实例、表情库、聊天记录或登录数据。

## 1.3.0

- Linux 新增 `--config-file`、`--non-interactive` 和 `QQBRIDGE_*` 环境配置；无人值守模式缺少必需项时直接失败，凭据只从环境接收。
- HTTP/HTTPS/SOCKS5 代理从安装配置写入实例环境并透传到 MaiBot；保留内部通信的 NO_PROXY，镜像补充 SOCKS 依赖。
- 实例目录支持 Compose override，安装、配置、验证、升级和回滚共用；核心发布文件仍严格校验。
- 安装、升级和回滚优先拉取 GHCR 版本镜像，拉取失败回退本地构建；新增 Release 镜像发布和 CI 构建检查。
- 新增 `access-linux.sh` 本机终端凭据查看和按实际端口生成的 SSH 转发命令。

## 1.2.0

面向“把仓库交给朋友的 Agent 部署”的流程改进。

- Windows 新增 `install-local.ps1 -ConfigFile`：Agent 准备无凭据 JSON，使用者只在本机隐藏窗口填 Key；不再自动读取剪贴板。
- 默认仅本机访问、登录 Windows 后自启；显式 `-Lan` / `-DisableAutoStart` 可调整。保留现有实例偏好。
- `access.cmd` 独立本机窗口查看两个 WebUI Token，不向 Agent 终端或安装报告输出；不显示内部 OneBot Token。
- Windows/Linux 增加安全续装：先保存安装上下文；达到配置就绪后，下载/构建失败可保留配置重试。
- WSL 命令使用独立 stdout/stderr 与明确参数转义，兼容 PowerShell 5.1；构建进度实时输出。
- 选择群白名单时不再重填模型；修改配置后显式重建容器，让挂载配置重新加载。
- 升级在停容器后备份，备份失败尝试恢复旧服务；回滚保留原实例，失败发布目录隔离后支持同版本重试。
- Linux 所有权使用实际主组；配置原子写入；启动后再次收紧凭据权限。
- 严格验证 QQ 登录、预期插件目录和私密配置权限；基础安装与实际聊天验收分别报告。
- 新增 `AGENT-DEPLOY.md`、配置模板、Windows/共享恢复回归测试、CI 与只打包受版本管理文件的构包工具。

验证范围：Windows PowerShell 5.1 + 本机 WSL 参数/流处理；模拟 Docker 的隔离安装/续装/升级/回滚测试；Compose 配置、镜像构建和包完整性检查。未完成另一台干净电脑完整从零安装、UAC/凭据窗口手工操作、QQ 扫码和群聊回复验收。Linux LAN 的 Docker 转发来源限制未验证，推荐 localhost + SSH 转发。

## 1.1.2

首次本机安装过程修复：PowerShell 自动变量冲突、原生 stderr 中止、Docker Desktop WSL 集成中断、模型与 QQ 输入提示、实时构建输出、WebUI 打开与目录选择。后续审查发现自动剪贴板、凭据终端显示和失败重试仍需完善，由 1.2.0 替代这些流程。
