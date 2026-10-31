# QQBridge Windows 11 一键部署包

版本：`1.0.0`

这是一个面向 Windows 11 x64 的私人 QQ 聊天机器人部署包，组合 MaiBot、NapCat、17 个插件、14 个运行时补丁、当前“哈基米”人设、表情包和提示图片。安装目标是 Docker Desktop + WSL2 Linux containers，运行文件位于 WSL ext4 的 `~/qqbridge`。

旧“大肥鱼”人设保存在 `payload/personas/legacy-dafeiyu.md`，只作为前任角色资料；默认启用的是“哈基米”人设。

## 快速安装

1. 右键打开“终端”或 PowerShell，以管理员身份进入本目录。
2. 执行：

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
- `-DisableAutoStart`：不创建 Docker Desktop 登录自启动任务。
- 安装器不会自动重启电脑。WSL 功能需要重启时会保存状态并退出；重启后重新执行同一命令。

安装器会检查 Windows 11、管理员权限、虚拟化、WSL2、Ubuntu、Docker Desktop 和 Linux Engine。缺少组件时会在确认后通过 `winget`/DISM/`wsl --install` 安装。

首次安装会询问：

- OpenAI 兼容主模型的 Base URL、模型标识、API Key 和客户端类型。
- 群主 QQ、群主称呼和可选的机器人 QQ。
- MaiBot、NapCat、OneBot 端口。

API Key、OneBot token 和 NapCat WebUI token 不会写进安装包；运行时 `.env` 权限为 `600`。

## 安装后三步

1. 打开 NapCat WebUI：`http://localhost:6099`，用自动生成的 WebUI token 登录并扫码登录 QQ。
2. 运行群发现和访问控制：

```powershell
.\configure.ps1 -DiscoverGroups
```

3. 运行验证：

```powershell
.\verify.ps1
```

默认访问策略是群聊和私聊全部阻断。NapCat 扫码成功后再运行 `configure.ps1 -DiscoverGroups` 选择允许的群；私聊只加入明确填写的 QQ。

## 配置

基础配置：

```powershell
.\configure.ps1
```

高级外部服务：

```powershell
.\configure.ps1 -Advanced
```

高级配置按需填写搜索、TTS、Codex Draw、代理和 Cookie。缺失必要凭据的插件默认停用，并记录在实例的 `plugin-report.json`。

所有运行配置位于：

```text
~/qqbridge/instances/default/
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

默认端口：

| 服务 | Windows/WSL 端口 | 容器端口 | 默认绑定 |
|---|---:|---:|---|
| MaiBot WebUI | 18001 | 8001 | 局域网 |
| NapCat WebUI | 6099 | 6099 | 局域网 |
| OneBot WebSocket | 3001 | 3001 | 仅 `127.0.0.1` |

局域网模式会创建仅限 Windows“专用网络”和 `LocalSubnet` 的 TCP 入站规则，公共网络不放行。NapCat 和 OneBot 使用每次安装生成的独立强 token。

## 升级和回滚

```powershell
.\upgrade.ps1 -Package 'C:\path\to\qqbridge-windows-vX.Y.Z.zip'
.\rollback.ps1
.\rollback.ps1 -BackupId '20261031T120000Z'
```

升级包必须与同名 `.sha256` 文件一起提供；`upgrade.ps1` 会先校验 ZIP，再停止当前容器并执行升级。

升级前会备份配置、插件、人设和持久数据；只保留最近 3 份备份。升级失败会尝试自动回滚。版本目录、`current` 软链接和 `instances/default` 持久目录分离，升级不会把用户配置直接覆盖成包内模板。

备份位置：

```text
~/qqbridge/backups/<UTC时间>/
├── instance.tar.gz
└── metadata.env
```

## 安全边界

- 安装包不包含 QQ 登录数据、聊天记录、长期记忆、生成图片、Codex 登录数据或现有 `.env`。
- 不迁移原机器人 QQ 账号登录状态；新主机必须由使用者扫码。
- `.env`、模型配置和 NapCat 配置在 WSL 中设置为 `600`。
- 默认阻断所有群聊和私聊，必须显式发现群并设置白名单。
- 公共网络防火墙规则不会创建。
- Docker Desktop 商业使用许可由使用者自行确认。

更完整的安全说明见 `SECURITY.md`。

## 插件

包内包含 17 个插件目录：

`Color2333_maibot-multi-platform-parser`、`MaiBot-SnowLuma-Adapter`、`TAIY2020_smart_poke_plugin`、`codex-draw`、`com_maibot_link-parser`、`deepseek-v4-pro_private-humanizer`、`gemini_web_search`、`github_erhan111119_mai-repost-shit`、`hajimi-file-download`、`juzi865_emoji2face`、`maibot-community_mai-repeater`、`maibot-moepix`、`mizuku003_tieba-share`、`persona-manager`、`token_usage_report`、`xuqian13_tts_voice_plugin`、`xxxxx7258_moegirl-wiki-plugin`。

上游仓库、来源提交、打包树哈希和许可证文件名见 `plugin-metadata.json` 与 `THIRD_PARTY_NOTICES.md`。

## 常用运维

```powershell
# 查看验证报告
.\verify.ps1

# 进入实例后查看日志
wsl -d Ubuntu -- bash -lc 'cd ~/qqbridge && docker compose --env-file instances/default/.env -f current/compose.yaml logs --tail=100'
```

如果 Docker Desktop 登录后未启动容器，先打开 Docker Desktop，等待 Linux Engine 就绪；容器使用 `restart: unless-stopped`。

## 已知限制

- 仅支持 Windows 11 x64，不支持 Windows 10、ARM64 或 Windows containers。
- QQ 登录、验证码和扫码必须由使用者完成。
- 搜索、TTS、绘图和部分平台 Cookie 依赖外部服务，安装包不携带任何真实凭据。
- 插件和基础镜像采用手动版本升级，不在后台自动拉取。
