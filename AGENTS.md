# QQBridge Agent Contract

本目录供后续 Agent 在 Windows 11 或原生 Linux 上安装、配置、验证或升级 QQBridge 时使用。

## 平台选择

- Windows 11 x64：优先双击 `install.cmd`、`configure.cmd`、`verify.cmd`（自动提权并绕过执行策略）；也可使用 `install.ps1`、`configure.ps1`、`verify.ps1`、`upgrade.ps1`、`rollback.ps1`。
- `install.ps1 -Yes` 会跳过系统变更确认，供 `install.cmd` 一键安装使用；手动安装时建议不加。
- 原生 Linux x86_64：使用 `install-linux.sh`、`configure-linux.sh`、`verify-linux.sh`、`upgrade-linux.sh`、`rollback-linux.sh`。
- 不要从 Windows 执行 Linux 入口，也不要在 Linux 上尝试 PowerShell 入口。

## 必须遵守

- 需要向用户提问或让用户选择时，优先使用当前 Agent 可用的交互式选择工具；不要假定朋友使用 Codex 或 Claude。密钥使用本机隐藏输入窗口，不通过聊天收集。
- 不得读取后在聊天、日志、报告或命令回显中输出 `.env`、API Key、Cookie、OneBot token、NapCat token、QQ 密码或 TOTP。
- 不得覆盖已有 `instances/default`。首次安装使用对应平台的安装入口；已有实例使用配置或升级入口。
- Linux 安装、配置、升级和回滚需要 root 权限；脚本会通过 `sudo` 提示提权。不要绕过其文件所有权和 `600` 权限设置。
- 升级或回滚前必须确认备份已创建；失败时停止继续操作并运行对应平台的回滚入口。
- 安装后必须运行对应平台的验证入口，检查容器健康、OneBot 连接、文件权限和插件清单。
- 不得自动重启 Windows 或 Linux 主机。需要重启时保存状态并明确告知用户手动重启。
- 不得把 QQ 登录数据、聊天记录、长期记忆、生成图片、Codex 登录数据或真实凭据加入发布包。
- Windows 默认不得开放公共网络；局域网规则必须仅限 `Private` 和 `LocalSubnet`。
- Linux 默认只允许本机访问。只有用户明确选择 `--lan` 时才开放局域网，并优先绑定单一 LAN IP、配置 UFW/firewalld 来源网段限制。
- 修改默认端口后必须同步更新防火墙规则和用户可见 URL。
- 发布前必须运行静态敏感信息扫描、PowerShell/Bash/Python 语法检查、Compose 配置检查和镜像构建检查。
- 不得在升级 ZIP 未通过同名 SHA-256 校验时继续。

## Agent 自动化入口（先读 AGENT-DEPLOY.md）

- Windows 推荐 `install-local.ps1 -ConfigFile <本机非敏感JSON>`。Agent 准备 Base URL、模型、协议、QQ、端口和 WSL 目录；API Key 由使用者在本机隐藏输入窗口填写。不要在非交互工具里调用 Read-Host 然后反复重试。
- Windows 默认仅本机访问、登录后自启。仅明确要求局域网访问时加 `-Lan`；仅明确要求手动启动时加 `-DisableAutoStart`。不要改变已有实例偏好。
- 默认安装目录是 WSL 内的 `~/qqbridge`，自定义目录也是 Linux 路径；不能直接填 Windows 盘符。
- 中断后 Windows 用 `install-local.ps1 -Resume`，Linux 用 `install-linux.sh --resume`。只有安装器记录且达到 ready_to_start 或 complete 的配置才能续装；不要通过改名目录/删除数据来自动重装。
- Token 只由使用者在本机 `access.cmd` 凭据窗口查看复制；不要把窗口内容读取、截图或带回对话。不要打印内部 OneBot token。
- `configure.ps1 -DiscoverGroups` 只管理白名单，不要求重填模型。扫码后必须运行 `verify.ps1 -RequireLogin` / `verify-linux.sh --require-login`；基础安装成功与 QQ 接入成功分开报告。
- 不得执行全量 `.env`、容器环境、Compose 展开配置或未经脱敏的容器日志输出。不要为排错重新生成发布清单哈希。
- 已有版本未包含新入口时，优先下载并校验新 Release，再按升级流程处理，不覆盖旧实例。

## 推荐顺序

1. 阅读 `README.md`、`SECURITY.md`、`manifest.json`，确认目标平台。
2. Windows：确认 Windows 11 x64、管理员权限、WSL2 Ubuntu 和 Docker Desktop Linux Engine。
3. Linux：确认 Linux x86_64、Python 3.10+、rootful Docker Engine、Compose v2 和 `sudo`。
4. 运行对应平台的安装入口。
5. 引导用户在 NapCat WebUI 扫码登录，且不要索取或输出 token。
6. 运行 `configure.ps1 -DiscoverGroups` 或 `configure-linux.sh --discover-groups`。
7. 运行对应平台的验证入口。
8. 升级时只使用同时提供同名 `.sha256` 的官方 ZIP。
