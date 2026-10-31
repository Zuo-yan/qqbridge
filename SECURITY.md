# QQBridge 安全说明

## 凭据

运行时凭据只保存在实例目录，不进入 Git 仓库、ZIP 或安装报告：

- `instances/default/.env`：主模型、搜索、OneBot 和 WebUI token。
- `instances/default/config/model_config.toml`：主模型 API Key。
- `instances/default/plugins/*/config.toml`：可选插件凭据和 Cookie。
- `instances/default/napcat/config/*.json`：NapCat token 和登录后的账号配置。

这些文件由安装器创建，权限为 `600`，并归属于指定运行用户。它们不是额外加密存储；主机磁盘加密和账户安全仍由使用者负责。

## 网络

Windows：

- 默认 MaiBot `18001`、NapCat `6099`、OneBot `3001` 都只绑定 `127.0.0.1`。只有显式 `-Lan` 才开放 WebUI 到局域网。
- 局域网模式只创建 Windows“专用网络”和 `LocalSubnet` 入站规则。
- `-LocalOnly` 将 WebUI 绑定到 `127.0.0.1`，并删除 QQBridge 防火墙规则。

Linux：

- 默认 MaiBot `18001`、NapCat `6099` 只绑定 `127.0.0.1`。
- `--lan` 只绑定一个自动检测或显式指定的 LAN IPv4 地址，不会绑定 `0.0.0.0`。
- LAN 模式尝试添加 UFW/firewalld 规则，但 Docker 转发可能绕过宿主机输入链，不能据此保证只允许指定 CIDR。推荐仅本机绑定配合 SSH 端口转发；不要将 WebUI 发布到公网。
- OneBot `3001` 始终只绑定 `127.0.0.1`。

自动生成的 token 至少 32 字节随机值。Windows 通过独立本机 `access.cmd` 窗口展示两个 WebUI Token；内部 OneBot Token 不显示。Agent 不应读取窗口内容或截图。API Key 通过本机隐藏对话框输入，不自动读取剪贴板。不要在聊天、日志或命令回显中输出凭据。

## 访问控制

全新实例默认阻断所有群聊。安装时显式填写的机器人管理员 QQ 会加入私聊白名单；留空则所有私聊被阻断。其他群和私聊 QQ 只在白名单流程中显式放行。

## 安装权限

- Windows 安装器要求管理员权限，以便配置 WSL2、Docker Desktop、文件系统和专用网络防火墙。
- 原生 Linux 入口要求 root 权限，以便写 `/var/lib/qqbridge`、设置实例所有权和限制 `.env` 权限。
- Linux 使用 rootful Docker Engine；不支持 rootless Docker。
- Docker 缺失时，安装器会明确询问是否执行 Docker 官方 `https://get.docker.com` 安装脚本。

## 发布包边界

发布包不包含：

- QQ 登录凭据、`ntqq` 数据、TOTP、扫码会话。
- 聊天记录、`MaiBot.db`、记忆数据、生成图片、缓存和日志。
- Codex 登录数据、浏览器登录态、真实 Cookie 或个人群号。
- 现有 `.env` 或任何真实 API Key。

不要用 `strings` 或日志命令输出整个 `.env`。发布前应运行包完整性、敏感字符串和缓存检查。

## 责任边界

QQBridge 只面向私人或可信小范围使用。QQ 平台规则、NapCat 上游行为、插件第三方服务条款、Docker Desktop 商业许可和模型服务商条款由使用者自行确认。
