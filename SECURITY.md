# QQBridge 安全说明

## 凭据

运行时凭据只保存在 WSL 实例目录，不进入 Git 仓库、ZIP 或安装报告：

- `instances/default/.env`：主模型、搜索、OneBot 和 WebUI token。
- `instances/default/config/model_config.toml`：主模型 API Key。
- `instances/default/plugins/*/config.toml`：可选插件凭据和 Cookie。
- `instances/default/napcat/config/*.json`：NapCat token 和登录后的账号配置。

这些文件在安装时由 root 创建并 chown 给运行用户，权限设置为 `600`。它们不是额外加密存储；主机磁盘加密、Windows 账户安全和 WSL 访问控制仍由使用者负责。

## 网络

- 默认 MaiBot `18001`、NapCat `6099` 绑定 `0.0.0.0`，OneBot `3001` 只绑定 `127.0.0.1`。
- 局域网模式只创建 Windows“专用网络”和 `LocalSubnet` 入站规则，公共网络不创建规则。
- `-LocalOnly` 将所有对外 WebUI 绑定到 `127.0.0.1`，并删除 QQBridge 防火墙规则。
- 自动生成的 token 至少 32 字节随机值。

## 访问控制

全新实例的 `adapter_policy.toml` 默认阻断所有群聊和私聊。只有 `configure.ps1 -DiscoverGroups` 选择的群和明确填写的私聊 QQ 才会被允许。

## 发布包边界

发布包不包含：

- QQ 登录凭据、`ntqq` 数据、TOTP、扫码会话。
- 聊天记录、`MaiBot.db`、记忆数据、生成图片、缓存和日志。
- Codex 登录数据、浏览器登录态、真实 Cookie 或个人群号。

如果需要在发布前再次扫描，使用仓库根目录的静态检查步骤；不要用 `strings` 输出整个 `.env`。

## 责任边界

QQBridge 只面向私人或可信小范围使用。QQ 平台规则、NapCat 上游行为、插件第三方服务条款、Docker Desktop 商业许可和模型服务商条款由使用者自行确认。
