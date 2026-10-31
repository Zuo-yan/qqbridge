# 让 Agent 部署 QQBridge

本指南面向接收仓库地址或 Release ZIP 的部署 Agent。先读 `AGENTS.md`。Windows 默认仅本机访问、登录 Windows 后启动 Docker Desktop，容器随引擎恢复；原生 Linux 默认仅本机访问。不要更换运行架构。

## 可以直接转发给 Agent 的指令

```text
请部署 https://github.com/Zuo-yan/qqbridge 。先阅读 AGENTS.md 和 AGENT-DEPLOY.md，检查当前系统与已有安装。
使用最新正式 Release 的 ZIP 和同名 SHA-256 文件，并核对校验值。不要覆盖已有实例。
Windows 保留 Docker Desktop + WSL2；默认仅本机访问、登录后自启。
你负责生成不含凭据的配置文件和执行安装；API Key 让我在本机隐藏输入窗口填写，不要向聊天索取、读取回显或记录 Key、Token、Cookie。
需要重启时保存进度并告诉我手动重启。下载或构建失败时保留实例，用续装入口重试，不要删除目录重装。
安装后引导我在本机凭据窗口取 Token、扫码、选择群白名单，再做基础检查和严格登录检查。
最终报告具体版本、访问地址、安装路径，以及 QQ 登录、白名单和实际聊天是否分别验证。尚未完成的步骤不能宣称成功。
```

## 1. 先检查，不要直接运行安装器

- Windows 11 **x64**：检查管理员提权、CPU 虚拟化、WSL2 Ubuntu、Docker Desktop Linux Engine；不支持 Windows ARM64。
- Linux **x86_64**：检查 Python 3.10+、sudo/root、rootful Docker Engine、Compose v2。
- 确认没有已有实例、同名容器或占用端口。Windows 状态位于 `C:\ProgramData\QQBridge\install-state.json`；Linux 位于 `/var/lib/qqbridge/install-state.json`。
- 已安装时使用配置或升级入口。状态为 `installing` 时使用续装入口。
- GitHub 的自动生成 Source code ZIP 与正式安装 ZIP 不同。优先使用 Release 中 `qqbridge-vX.Y.Z.zip` 和同名 `.zip.sha256`，不要下载 `latest/main` 后声称它是已发布版本。

## 2. Windows：Agent 准备配置，使用者只填 Key

复制 `deploy.example.json` 为仓库目录以外的本机文件（例如下载目录中的 `qqbridge-config.json`），填写：

- `llm_base_url`：使用者实际服务商地址，不要根据模型名猜测。
- `llm_model`：服务商实际模型标识，示例占位符必须替换。
- `llm_client_type`：通常为 `openai`（Chat Completions）；Responses 和 Gemini 需确认服务商支持。
- `owner_qq`：机器人管理员/接入者 QQ，不是 QQ 群的群主。填写后默认允许此 QQ 私聊；留空不授予该权限。
- `owner_name`：机器人对接入者的称呼，不影响权限。
- `bot_qq`：被扫码登录的机器人账号，可暂留空。
- `install_root`：WSL 内目录，默认 `~/qqbridge`，也可 `/srv/qqbridge`。这不是 Windows 安装盘选择，不能填 `D:\QQBridge` 或 `/mnt/d/...`。
- 三个端口必须互不相同、未被占用。其他字段用默认值。

配置文件**不允许包含 API Key、Cookie 或 Token**。朋友的私人配置不要写进仓库或安装包。

```powershell
# Agent 可执行；UAC 和本机 Key 窗口由使用者完成。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-local.ps1 -ConfigFile 'C:\Users\YOUR_USER\Downloads\qqbridge-config.json'
```

不提供配置文件则双击 `install.cmd` 按提示安装。`-Yes` 仅自动确认依赖安装，不能绕过 UAC 或代替扫码。无需永久修改系统执行策略。

重启提示退出码为 `3010`。不要自动重启；手动重启后用同一条命令继续。系统组件阶段不会保存 Key。

网络异常或构建失败后，状态为 `installing` 时：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-local.ps1 -Resume
```

续装只允许由安装器登记且配置已准备好的实例，保留原配置、Key 和数据。若初始化阶段失败、未达到可续装阶段，应停止并报告状态；不可自动删除或覆盖实例。

首次安装完成会自动打开本机凭据窗口和两个 WebUI。之后双击 `access.cmd` 可重新查看 WebUI Token。凭据仅显示在本机窗口，Agent 不应截图、读取 UI 文本或在工具输出中打印。

## 3. Linux

```bash
bash ./install-linux.sh
# 构建失败且已有安装状态时
bash ./install-linux.sh --resume
```

Linux 使用交互终端隐藏输入 Key，Agent 不能把 Key 放进命令行、聊天或答案报告。在 Agent 无法提供交互终端的环境，让使用者在本机运行安装入口，Agent 负责前置检查与后续验证。服务器上的 QQ 扫码仍由使用者完成。WebUI 推荐使用 SSH 端口转发，不建议把管理端口直接公开到互联网。

## 4. 安装完成不等于已经能聊天

1. 基础安装：容器启动、健康检查通过。
2. QQ 登录：使用者打开 NapCat、在本机复制 Token 登录并扫码。
3. 白名单：Windows `configure.ps1 -DiscoverGroups` 或双击 `configure.cmd`；Linux `configure-linux.sh --discover-groups`。只放行使用者指定的群/私聊。
4. 严格检查：Windows `verify.ps1 -RequireLogin`；Linux `verify-linux.sh --require-login`。
5. 在已允许的群或私聊里发一条消息，确认模型有实际回复，再报告完整接入成功。

基础验证在未扫码时会出现 OneBot WARN；严格检查将其视为失败。模型返回 401/403、模型名错误或余额不足不应通过重装解决，应修正服务商配置。验证脚本不自动发聊天消息，不自动产生模型请求费用。

## 5. 排错与交付

- 禁止 `cat .env`、`docker inspect` 全量环境导出、`docker compose config` 无差别回显，以及不筛选的 `docker logs`。这些输出可能包含 Key/Token。
- 读取非敏感状态与失败步骤，先修网络、Docker/WSL、端口和文件权限。Docker Desktop 运行中不要 `wsl --terminate Ubuntu`。
- 不要为了“重试”重新生成清单哈希、关闭完整性校验或覆盖 `instances/default`。
- 升级必须有同名 SHA-256 文件。保留升级前备份和失败目录，不要擅自清理聊天/登录数据。
- 最终交付：Release 版本与校验结果、实际实例版本、安装目录、两个 URL、启动方式、基础验证/QQ 登录/白名单/实际回复结果。Token 不写进报告。
