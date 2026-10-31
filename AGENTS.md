# QQBridge Agent Contract

本目录供后续 Agent 安装、配置、验证或升级 QQBridge 时使用。

## 必须遵守

- 需要向用户提问或让用户选择时，使用 Codex 的交互式对话框，不要用长篇文字自行代替选择。
- 不得读取后在聊天、日志、报告或命令回显中输出 `.env`、API Key、Cookie、OneBot token、NapCat token、QQ 密码或 TOTP。
- 不得覆盖已有 `instances/default`。首次安装使用 `install.ps1`；已有实例使用 `configure.ps1` 或 `upgrade.ps1`。
- 升级或回滚前必须确认备份已创建；失败时停止继续操作并执行 `rollback.ps1`。
- 安装后必须运行 `verify.ps1`，检查容器健康、OneBot 连接、文件权限和插件清单。
- 不得自动重启 Windows。需要重启时保存状态并明确告知用户手动重启。
- 不得把 QQ 登录数据、聊天记录、长期记忆、生成图片、Codex 登录数据或真实凭据加入发布包。
- 默认不得开放公共网络防火墙；局域网规则必须仅限 `Private` 和 `LocalSubnet`。
- 修改默认端口后必须同步更新防火墙规则和用户可见 URL。
- 发布前必须运行静态敏感信息扫描、PowerShell/Bash/Python 语法检查、Compose 配置检查和镜像构建检查。

## 推荐顺序

1. 阅读 `README.md`、`SECURITY.md`、`manifest.json`。
2. 确认 Windows 11 x64、管理员权限、WSL2 Ubuntu 和 Docker Desktop Linux Engine。
3. 运行 `install.ps1`。
4. 引导用户扫码登录 NapCat。
5. 运行 `configure.ps1 -DiscoverGroups`。
6. 运行 `verify.ps1`。
7. 需要升级时使用带 SHA-256 的 ZIP 和 `upgrade.ps1`。
