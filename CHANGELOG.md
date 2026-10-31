# 更新记录

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
