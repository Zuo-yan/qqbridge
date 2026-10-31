# QQBridge 一键部署包

版本：`1.1.0`

这是一个可同时部署到 **Windows 11 x64** 和 **原生 Linux x86_64** 的私人 QQ 聊天机器人部署包，组合 MaiBot、NapCat、17 个插件、14 个运行时补丁、当前“哈基米”人设、表情包和提示图片。

Windows 使用 Docker Desktop + WSL2 Ubuntu；原生 Linux 使用 Docker Engine + Compose v2。两种平台共用同一套配置、插件、人设、镜像、数据目录、升级和回滚逻辑。

旧“大飞鱼”人设保存在 `payload/personas/legacy-dafeiyu.md`，只作为前任角色资料；默认启用的是“哈基米”人设。

## 入口

| 操作 | Windows 11 | 原生 Linux |
|---|---|---|
| 安装 | `.\install.ps1` | `bash ./install-linux.sh` |
| 配置 | `.\configure.ps1` | `bash ./configure-linux.sh` |
| 验证 | `.\verify.ps1` | `bash ./verify-linux.sh` |
| 升级 | `.\upgrade.ps1 -Package <ZIP>` | `bash ./upgrade-linux.sh --package <ZIP>` |
| 回滚 | `.\rollback.ps1` | `bash ./rollback-linux.sh` |

## Windows 11 安装

要求 Windows 11 x64。右键打开“终端”或 PowerShell，以管理员身份进入本目录：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

默认安装到 WSL 用户主目录的 `~/qqbridge`。常用参数：

```powershell
.\install.ps1 -InstallRoot '~/qqbridge'
.\install.ps1 -LocalOnly
.\install.ps1 -DisableAutoStart
```

- `-LocalOnly`：MaiBot/NapCat 只绑定 `127.0.0.1`，不创建局域网防火墙规则。
- `-DisableAutoStart`：不创建 Docker Desktop 登录自启动任务，并关闭容器自动重启。
- 安装器不会自动重启电脑。WSL 功能需要重启时会保存状态并退出；重启后重新执行同一命令。

安装器检查 Windows 11、管理员权限、硬件虚拟化、WSL2、Ubuntu、Docker Desktop 和 Linux Engine。缺少组件时会在确认后通过 `winget`、DISM 或 `wsl --install` 安装。

## 原生 Linux 安装

要求 Linux x86_64、Python 3.10+、`systemd`、`sudo`、Docker Engine 和 Docker Compose v2。默认按 rootful Docker 管理；已测试目标为常见 Ubuntu/Debian 系发行版。

```bash
unzip qqbridge-v1.1.0.zip
cd qqbridge-v1.1.0
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

- Linux 默认是仅本机模式，比 Windows 默认更保守。
- `--lan` 只绑定一个自动检测或显式指定的局域网 IPv4 地址，不会绑定 `0.0.0.0`。
- 检测到活动 UFW 或 firewalld 时，会添加仅允许指定局域网 CIDR 访问 WebUI 端口的规则；未检测到防火墙时会给出明确警告。
- `--disable-autostart` 将容器重启策略设为 `no`，不会关闭整台主机上的 Docker 服务。
- Linux 安装状态保存在 `/var/lib/qqbridge/install-state.json`，权限为 `600`。

## 首次配置

两个平台首次安装都会询问：

- OpenAI 兼容主模型的 Base URL、模型标识、API Key 和客户端类型。
- 群主 QQ、群主称呼和可选的机器人 QQ。
- MaiBot、NapCat、OneBot 端口与时区。

API Key、OneBot token 和 NapCat WebUI token 不会写进安装包；运行时 `.env` 权限为 `600`。token 在每台主机首次安装时重新生成。

安装后三步：

1. 打开 NapCat WebUI，用 `.env` 中的 `WEBUI_TOKEN` 登录并扫码。不要通过截图、聊天或日志传播 token。
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
.\verify.ps1
```

```bash
bash ./verify-linux.sh
```

默认访问策略是群聊和私聊全部阻断，只有显式选择的群和私聊 QQ 才会放行。

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
├── releases/1.1.0/
├── current -> releases/1.1.0/
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
| MaiBot WebUI | `0.0.0.0:18001` | `127.0.0.1:18001` | 8001 |
| NapCat WebUI | `0.0.0.0:6099` | `127.0.0.1:6099` | 6099 |
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
- 默认阻断所有群聊和私聊，必须显式发现群并设置白名单。
- Windows 不创建公共网络防火墙规则；Linux LAN 模式不会绑定全部网卡。
- Windows Docker Desktop 商业许可与 Docker Engine 的生产环境配置由使用者自行确认。

完整说明见 `SECURITY.md`。

## 插件

包内包含 17 个插件目录：

`Color2333_maibot-multi-platform-parser`、`MaiBot-SnowLuma-Adapter`、`TAIY2020_smart_poke_plugin`、`codex-draw`、`com_maibot-link-parser`、`deepseek-v4-pro_private-humanizer`、`gemini_web_search`、`github_erhan111119_mai-repost-shit`、`hajimi-file-download`、`juzi865_emoji2face`、`maibot-community_mai-repeater`、`maibot-moepix`、`mizuku003_tieba-share`、`persona-manager`、`token_usage_report`、`xuqian13_tts_voice_plugin`、`xxxxx7258_moegirl-wiki-plugin`。

上游仓库、来源提交、打包树哈希和许可证文件名见 `plugin-metadata.json` 与 `THIRD_PARTY_NOTICES.md`。

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
