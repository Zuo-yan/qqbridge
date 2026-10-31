# QQBridge 一键部署包

版本：`1.2.0`

这是一个可同时部署到 **Windows 11 x64** 和 **原生 Linux x86_64** 的私人 QQ 聊天机器人部署包，组合 MaiBot、NapCat、17 个插件、14 个运行时补丁、当前“哈基米”人设、表情包和提示图片。

Windows 使用 Docker Desktop + WSL2 Ubuntu；原生 Linux 使用 Docker Engine + Compose v2。两种平台共用同一套配置、插件、人设、镜像、数据目录、升级和回滚逻辑。

旧“大飞鱼”人设保存在 `payload/personas/legacy-dafeiyu.md`，只作为前任角色资料；默认启用的是“哈基米”人设。

## 交给朋友的 Agent

先让 Agent 阅读 [AGENT-DEPLOY.md](AGENT-DEPLOY.md)，其中有可直接转发的部署指令、无密钥配置模板和验收步骤。

Windows 推荐由 Agent 填写 `deploy.example.json` 的本机副本，再执行 `install-local.ps1 -ConfigFile <本机JSON>`。使用者只需确认 UAC、在本机隐藏窗口填写 Key、扫码和选择群。不要把 Key 发到聊天。默认仅本机访问，登录 Windows 后自启；已有实例的设置不会自动改变。

## 入口

| 操作 | Windows 11 | 原生 Linux |
|---|---|---|
| 安装 | 双击 `install.cmd` 或 `.\install.ps1` | `bash ./install-linux.sh` |
| 配置 | 双击 `configure.cmd` 或 `.\configure.ps1` | `bash ./configure-linux.sh` |
| 验证 | 双击 `verify.cmd` 或 `.\verify.ps1` | `bash ./verify-linux.sh` |
| 升级 | `.\upgrade.ps1 -Package <ZIP>` | `bash ./upgrade-linux.sh --package <ZIP>` |
| 回滚 | `.\rollback.ps1` | `bash ./rollback-linux.sh` |

## Windows 11 一键安装（推荐）

1. 把 ZIP 解压到任意本地目录，不要在压缩包内直接运行。
2. 双击 `install.cmd`，在 UAC 提示中点“是”。
3. 按窗口提示选择安装目录（直接回车使用默认 `~/qqbridge`，也可输入 `~/xxx` 或绝对路径）、填写模型和 QQ 信息；如果提示需要重启，重启后再次双击 `install.cmd`。
4. 安装完成自动打开两个页面，并弹出独立的本机凭据窗口显示 WebUI Token；之后双击 `access.cmd` 可重新查看。Token 不打印到 Agent 的终端输出。
5. 在 NapCat WebUI 扫码登录后，双击 `configure.cmd` 选择允许的群，再双击 `verify.cmd` 检查。

安装和配置入口会在需要时请求 UAC 提权；这些 `.cmd` 仅对当前进程绕过执行策略，不需要永久修改 `Set-ExecutionPolicy`。`verify.cmd` 执行扫码后的严格检查。所有 `.ps1` 均以 UTF-8 BOM 保存，兼容中文 Windows PowerShell 5.1。

## Windows 11 安装

要求 Windows 11 x64。右键打开“终端”或 PowerShell，以管理员身份进入本目录：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

默认安装到 WSL 用户主目录的 `~/qqbridge`。常用参数：

```powershell
.\install.ps1 -InstallRoot '~/qqbridge'
.\install.ps1 -Lan                       # 仅明确需要时开放局域网
.\install.ps1 -DisableAutoStart          # 手动启动
.\install-local.ps1 -ConfigFile 'C:\path\qqbridge-config.json' # Agent 入口
.\install-local.ps1 -Resume              # 失败后保留配置续装
```

- 默认仅本机：MaiBot/NapCat 绑定 `127.0.0.1`，不创建局域网规则。`-LocalOnly` 保留兼容；只有 `-Lan` 才开放局域网。
- 默认登录 Windows 后启动 Docker Desktop；容器用 `unless-stopped` 恢复。这不是未登录时的系统服务，也不会唤醒关机/休眠电脑。
- `-DisableAutoStart`：不创建 Docker Desktop 登录自启动任务，并关闭容器自动重启。
- 安装器不会自动重启电脑。WSL 功能需要重启时会保存状态并退出；重启后重新执行同一命令。

安装器检查 Windows 11、管理员权限、硬件虚拟化、WSL2、Ubuntu、Docker Desktop 和 Linux Engine。缺少组件时会在确认后通过 `winget`、DISM 或 `wsl --install` 安装。

## 原生 Linux 安装

要求 Linux x86_64、Python 3.10+、`systemd`、`sudo`、Docker Engine 和 Docker Compose v2。默认按 rootful Docker 管理；已测试目标为常见 Ubuntu/Debian 系发行版。

```bash
unzip qqbridge-v1.2.0.zip
cd qqbridge-v1.2.0
bash ./install-linux.sh
```

安装器会：

1. 先验证 `manifest.json` 中全部文件的 SHA-256。
2. 检查 Docker Engine、Compose v2 和 Python。
3. Docker 缺失时询问是否使用 Docker 官方 `get.docker.com` 脚本安装。
4. 将目标用户加入 `docker` 组并验证访问权限。
5. 默认将 WebUI 绑定到 `127.0.0.1`，安装到目标用户的 `~/qqbridge`。

Linux 常用参数：

```bash
bash ./install-linux.sh --install-root /srv/qqbridge
bash ./install-linux.sh --target-user qqbot
bash ./install-linux.sh --lan
bash ./install-linux.sh --lan --lan-bind-ip 192.168.1.20
bash ./install-linux.sh --lan --lan-cidr 192.168.1.0/24
bash ./install-linux.sh --disable-autostart
```

- Windows 和 Linux 默认均仅本机访问。
- `--lan` 只绑定一个自动检测或显式指定的局域网 IPv4 地址，不会绑定 `0.0.0.0`。
- Linux LAN 模式会尝试添加 UFW/firewalld 规则，但 Docker 发布端口可能绕过宿主机输入规则；这不是已验证的来源网段隔离。推荐默认 localhost + SSH 转发；不要直接发布到公网。
- `--disable-autostart` 将容器重启策略设为 `no`，不会关闭整台主机上的 Docker 服务。
- Linux 安装状态保存在 `/var/lib/qqbridge/install-state.json`，权限为 `600`。

## 首次配置

两个平台首次安装都会询问：

- OpenAI 兼容主模型的 Base URL、模型标识、API Key 和客户端类型。
- 管理员/“群主” QQ、称呼和可选的机器人 QQ。这里的“群主”指**机器人主人（接入者本人）**，不是 QQ 群群主；它用于人设管理命令和私聊白名单。留空会失去人设管理命令，且私聊默认全部阻断。
- MaiBot、NapCat、OneBot 端口与时区。

API Key、OneBot token 和 NapCat WebUI token 不会写进安装包；运行时 `.env` 权限为 `600`。token 在每台主机首次安装时重新生成。

安装后三步：

1. Windows 双击 `access.cmd` 在本机查看 NapCat/MaiBot Token，再登录并扫码；Linux 由使用者在本机查看凭据。不要在 Agent 输出、截图或日志中传播 token。
2. 扫码后设置群白名单：

```powershell
# Windows
.\configure.ps1 -DiscoverGroups
```

```bash
# Linux
bash ./configure-linux.sh --discover-groups
```

3. 运行完整验证：

```powershell
.\verify.ps1 -RequireLogin
```

```bash
bash ./verify-linux.sh --require-login
```

群聊默认全部阻断；私聊默认只允许安装时显式填写的机器人管理员 QQ（若留空则全部阻断）。之后通过白名单选择其他允许的群/私聊。基础检查不要求 QQ 已登录；严格登录检查通过后，还需要在已允许的群里确认实际回复。

## 配置

Windows：

```powershell
.\configure.ps1
.\configure.ps1 -Advanced
```

Linux：

```bash
bash ./configure-linux.sh
bash ./configure-linux.sh --advanced
```

高级配置按需填写搜索、TTS、Codex Draw、代理和 Cookie。缺失必要凭据的插件默认停用，并记录在实例的 `plugin-report.json`。

运行目录：

```text
~/qqbridge/                       # Linux 默认；Windows 位于 WSL 用户主目录
├── releases/1.2.0/
├── current -> releases/1.2.0/
├── backups/
└── instances/default/
    ├── .env
    ├── config/
    ├── plugins/
    ├── data/
    ├── personas/
    ├── napcat/
    ├── logs/
    └── depends-data/
```

## 端口和局域网

| 服务 | Windows 默认 | Linux 默认 | 容器端口 |
|---|---|---|---:|
| MaiBot WebUI | `127.0.0.1:18001` | `127.0.0.1:18001` | 8001 |
| NapCat WebUI | `127.0.0.1:6099` | `127.0.0.1:6099` | 6099 |
| OneBot WebSocket | `127.0.0.1:3001` | `127.0.0.1:3001` | 3001 |

Windows 局域网模式只创建“专用网络”和 `LocalSubnet` 入站规则，公共网络不放行。Linux `--lan` 使用单一 LAN IP 绑定，并尽可能配置 UFW/firewalld 来源网段规则。OneBot 在两端默认都只绑定本机。

## 升级和回滚

升级包必须和目标端同名 `.sha256` 文件一起提供：

```powershell
# Windows
.\upgrade.ps1 -Package 'C:\path\to\qqbridge-v1.2.0.zip'
.\rollback.ps1
```

```bash
# Linux
bash ./upgrade-linux.sh --package ~/downloads/qqbridge-v1.2.0.zip
bash ./rollback-linux.sh
bash ./rollback-linux.sh --backup-id 20261031T120000Z
```

升级前会备份配置、插件、人设和持久数据，只保留最近 3 份。升级失败会尝试自动回滚。版本目录、`current` 软链接和 `instances/default` 持久目录分离，升级不会把用户配置覆盖成包内模板。

备份格式：

```text
~/qqbridge/backups/<UTC时间>/
├── instance.tar.gz
└── metadata.env
```

## 安全边界

- 安装包不包含 QQ 登录数据、聊天记录、长期记忆、生成图片、Codex 登录数据或现有 `.env`。
- 不迁移机器人 QQ 登录状态；新主机必须由使用者扫码。
- `.env`、模型配置和 NapCat 配置权限设置为 `600`。
- 默认阻断所有群聊；私聊仅放行安装时填写的管理员 QQ，其他访问需显式设置白名单。
- Windows 不创建公共网络防火墙规则；Linux LAN 模式不会绑定全部网卡。
- Windows Docker Desktop 商业许可与 Docker Engine 的生产环境配置由使用者自行确认。

完整说明见 `SECURITY.md`。

## 插件

包内包含 17 个插件目录：

`Color2333_maibot-multi-platform-parser`、`MaiBot-SnowLuma-Adapter`、`TAIY2020_smart_poke_plugin`、`codex-draw`、`com_maibot-link-parser`、`deepseek-v4-pro_private-humanizer`、`gemini_web_search`、`github_erhan111119_mai-repost-shit`、`hajimi-file-download`、`juzi865_emoji2face`、`maibot-community_mai-repeater`、`maibot-moepix`、`mizuku003_tieba-share`、`persona-manager`、`token_usage_report`、`xuqian13_tts_voice_plugin`、`xxxxx7258_moegirl-wiki-plugin`。

上游仓库、来源提交、打包树哈希和许可证文件名见 `plugin-metadata.json` 与 `THIRD_PARTY_NOTICES.md`。

## 发布验证

维护者先将新增源码加入 git 索引，然后使用 `python -I tools/release.py --root <仓库> --refresh-manifest` 更新清单；审核清单改动后，去掉该选项再次校验。`--output <新的空目录>` 只打包受版本管理的文件并生成 ZIP + SHA-256，拒绝运行时文件与常见凭据模式。不要把私人部署配置放入 git 索引。

发布前还必须完成 PowerShell/Bash/Python 语法、Windows 回归、隔离部署恢复测试、Compose 配置与镜像构建检查。源码检查不等于全新机器实测；没有完成的系统/扫码测试需在发布说明中注明。

## 常用运维

```bash
# Linux 查看日志
cd ~/qqbridge
docker compose --env-file instances/default/.env -f current/compose.yaml logs --tail=100
```

```powershell
# Windows/WSL 查看日志
wsl -d Ubuntu -- bash -lc 'cd ~/qqbridge && docker compose --env-file instances/default/.env -f current/compose.yaml logs --tail=100'
```

容器默认使用 `restart: unless-stopped`；如果 Docker 服务或 Docker Desktop 未启动，容器不会自行拉起重启守护进程。

## 已知限制

- Windows 只支持 Windows 11 x64；Linux 只支持 x86_64。
- 不支持 Windows 10、ARM64、Windows containers 或 Docker rootless 模式。
- QQ 登录、验证码和扫码必须由使用者完成。
- 搜索、TTS、绘图和部分平台 Cookie 依赖外部服务，安装包不携带任何真实凭据。
- 插件和基础镜像采用手动版本升级，不在后台自动拉取。
