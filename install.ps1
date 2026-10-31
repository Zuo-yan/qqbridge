[CmdletBinding()]
param(
    [string]$InstallRoot = '~/qqbridge',
    [switch]$LocalOnly,
    [switch]$DisableAutoStart,
    [switch]$Yes,
    [switch]$NoBrowser
)

. (Join-Path $PSScriptRoot 'qqbridge-lib.ps1')
$script:AssumeYes = [bool]$Yes

if (-not (Test-IsAdministrator)) {
    $arguments = @()
    # 只在用户显式传入时转发，避免提权后误判为“已指定目录”而跳过交互选择。
    if ($PSBoundParameters.ContainsKey('InstallRoot')) { $arguments += @('-InstallRoot', $InstallRoot) }
    if ($LocalOnly) { $arguments += '-LocalOnly' }
    if ($DisableAutoStart) { $arguments += '-DisableAutoStart' }
    if ($Yes) { $arguments += '-Yes' }
    if ($NoBrowser) { $arguments += '-NoBrowser' }
    Restart-Elevated -EntryScript $PSCommandPath -Arguments $arguments
}

Assert-Windows11
Assert-Virtualization
Test-PackageIntegrity -Root $script:PackageRoot

if ($InstallRoot -notmatch '^(~|/)') {
    Stop-QQBridge 'InstallRoot 必须是 WSL 绝对路径或以 ~/ 开头。'
}

$state = Read-State
if ($state -and $state.phase -eq 'awaiting_reboot') {
    Write-QQLog '检测到重启后续装状态，继续执行安装流程。'
}

Ensure-WslUbuntu
$linux = Ensure-LinuxUser
$script:LinuxUser = $linux.User
if (-not $PSBoundParameters.ContainsKey('InstallRoot')) {
    while ($true) {
        $chosenRoot = ConvertTo-CleanText (Read-Host "安装目录 [$InstallRoot]（直接回车使用默认，或输入 ~/xxx / 绝对路径）")
        if (-not $chosenRoot) { break }
        if ($chosenRoot -match '^(~|/)') {
            $InstallRoot = $chosenRoot
            break
        }
        Write-Host '安装目录必须以 ~/ 或 / 开头，请重新输入。' -ForegroundColor Yellow
    }
}
$expandedRoot = if ($InstallRoot -eq '~') { $linux.Home } elseif ($InstallRoot.StartsWith('~/')) { "$($linux.Home)/$($InstallRoot.Substring(2))" } else { $InstallRoot }

$existing = Invoke-WslRaw -User 'root' -Arguments @(
    'bash', '-lc',
    "test -e '$expandedRoot/current' || test -L '$expandedRoot/current' || test -f '$expandedRoot/instances/default/config/bot_config.toml'"
) -AllowFailure
if ($existing.ExitCode -eq 0) {
    Stop-QQBridge "已存在实例 $expandedRoot。请使用 configure.ps1；升级请使用 upgrade.ps1。"
}

Ensure-DockerDesktop

Write-Host ''
Write-Host '配置主聊天模型' -ForegroundColor Cyan
while ($true) {
    $baseUrl = ConvertTo-CleanText (Read-Host 'OpenAI 兼容 Base URL（必填，例如 https://api.deepseek.com/v1）')
    if (-not $baseUrl) {
        Write-Host 'Base URL 不能为空，请填写你的模型服务地址。' -ForegroundColor Yellow
        continue
    }
    if ($baseUrl -match '^https?://') { break }
    if ($baseUrl -match '^sk-') {
        Write-Host '这看起来是 API Key，不是 Base URL。Base URL 应以 http:// 或 https:// 开头。' -ForegroundColor Yellow
    } else {
        Write-Host 'Base URL 必须以 http:// 或 https:// 开头，请重新输入。' -ForegroundColor Yellow
    }
}
$model = ''
while (-not $model) {
    $model = ConvertTo-CleanText (Read-Host '模型标识（例如 gpt-4.1-mini / deepseek-chat）')
    if (-not $model) { Write-Host '模型标识不能为空，请重新输入。' -ForegroundColor Yellow }
}

$apiKey = ''
while (-not $apiKey) {
    $secureKey = Read-Host 'API Key（输入不回显；若 Ctrl+V 粘贴无效，可先复制到剪贴板后直接回车）' -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    try {
        $apiKey = ConvertTo-CleanText ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr))
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    if (-not $apiKey) {
        $clipboardText = Get-Clipboard -Raw -ErrorAction SilentlyContinue
        $apiKey = ConvertTo-CleanText $clipboardText
    }
    if ($apiKey -match '^https?://') {
        Write-Host '这看起来是 URL，不是 API Key。' -ForegroundColor Yellow
        $apiKey = ''
    }
    if (-not $apiKey) {
        Write-Host '未读取到有效 API Key，请重试（可先复制到剪贴板后直接回车）。' -ForegroundColor Yellow
    }
}

$clientType = ''
while (-not $clientType) {
    Write-Host '客户端类型：1) openai（大多数兼容服务，含 DeepSeek）  2) openai_responses（仅 OpenAI Responses API）  3) gemini'
    $clientChoice = (Read-Host '选择 [1]').Trim()
    switch ($clientChoice) {
        '' { $clientType = 'openai' }
        '1' { $clientType = 'openai' }
        '2' { $clientType = 'openai_responses' }
        '3' { $clientType = 'gemini' }
        default { Write-Host '请输入 1、2 或 3。' -ForegroundColor Yellow }
    }
}

while ($true) {
    $ownerQq = ConvertTo-CleanText (Read-Host '管理员/机器人主人 QQ（即接入者本人，可留空）')
    if (-not $ownerQq) { break }
    if ($ownerQq -match '^\d{5,12}$') { break }
    Write-Host 'QQ 号格式无效，请输入 5-12 位数字。' -ForegroundColor Yellow
}
$ownerName = ConvertTo-CleanText (Read-Host '管理员称呼（机器人怎么称呼你，例如你的昵称）[群主]')
if (-not $ownerName) { $ownerName = '群主' }
while ($true) {
    $botQq = ConvertTo-CleanText (Read-Host '机器人 QQ（登录后再填可留空）')
    if (-not $botQq) { break }
    if ($botQq -match '^\d{5,12}$') { break }
    Write-Host 'QQ 号格式无效，请输入 5-12 位数字。' -ForegroundColor Yellow
}

$maiPort = Read-Port -Label 'MaiBot WebUI 端口' -Default 18001
$napPort = Read-Port -Label 'NapCat WebUI 端口' -Default 6099
$onePort = Read-Port -Label 'OneBot 本机端口' -Default 3001
$bind = if ($LocalOnly) { '127.0.0.1' } else { '0.0.0.0' }

$uidResult = Invoke-WslRaw -User 'root' -Arguments @('id', '-u', $linux.User)
$gidResult = Invoke-WslRaw -User 'root' -Arguments @('id', '-g', $linux.User)
$uid = (($uidResult.Output | Select-Object -First 1) -as [string]).Trim()
$gid = (($gidResult.Output | Select-Object -First 1) -as [string]).Trim()

$answers = @{
    llm_base_url = $baseUrl
    llm_api_key = $apiKey
    llm_model = $model
    llm_client_type = $clientType
    owner_qq = $ownerQq
    owner_name = $ownerName
    bot_qq = $botQq
    maibot_port = $maiPort
    napcat_port = $napPort
    onebot_port = $onePort
    maibot_bind = $bind
    napcat_bind = $bind
    timezone = 'Asia/Shanghai'
    restart_policy = if ($DisableAutoStart) { 'no' } else { 'unless-stopped' }
    allowed_groups = @()
    allowed_users = @($ownerQq | Where-Object { $_ })
}
$apiKey = $null

$answerFile = Save-SecureAnswers -Answers $answers
try {
    $wslPackage = ConvertTo-WslPath $script:PackageRoot
    $wslAnswers = ConvertTo-WslPath $answerFile
    $scriptPath = "$wslPackage/wsl/install.sh"
    Write-QQLog '开始写入 WSL ext4、构建定制镜像并启动容器。'
    $result = Invoke-WslBash `
        -User 'root' `
        -ScriptPath $scriptPath `
        -ScriptArguments @(
            '--package', $wslPackage,
            '--install-root', $expandedRoot,
            '--answers', $wslAnswers,
            '--target-user', $linux.User,
            '--napcat-uid', $uid,
            '--napcat-gid', $gid,
            '--platform', 'wsl'
        )
} finally {
    Remove-Item -LiteralPath $answerFile -Force -ErrorAction SilentlyContinue
}

$localOnlyValue = [bool]$LocalOnly.IsPresent
$disableAutostartValue = [bool]$DisableAutoStart.IsPresent
Update-QQBridgeFirewall -LocalOnly:$localOnlyValue -MaiBotPort $maiPort -NapCatPort $napPort
Set-DockerAutostart -Disable:$disableAutostartValue

$packageVersion = (Get-Content -LiteralPath (Join-Path $script:PackageRoot 'VERSION') -Raw -Encoding UTF8).Trim()
Write-State @{
    phase = 'installed'
    package_version = $packageVersion
    distro = $script:DistroName
    linux_user = $linux.User
    linux_home = $linux.Home
    install_root = $expandedRoot
    local_only = $LocalOnly.IsPresent
    maibot_port = $maiPort
    napcat_port = $napPort
    onebot_port = $onePort
}

$context = [pscustomobject]@{
    InstallRoot = $expandedRoot
    LinuxUser = $linux.User
    Distro = $script:DistroName
    DockerDesktop = $script:DockerDesktopPath
}
$webuiToken = ''
$onebotToken = ''
try { $webuiToken = Get-InstanceEnvValue -Context $context -Key 'WEBUI_TOKEN' } catch { }
try { $onebotToken = Get-InstanceEnvValue -Context $context -Key 'ONEBOT_TOKEN' } catch { }
$maiToken = ''
for ($i = 0; $i -lt 10 -and -not $maiToken; $i++) {
    $maiJson = Invoke-WslRaw -User 'root' -Arguments @('cat', "$expandedRoot/instances/default/data/webui.json") -AllowFailure
    if ($maiJson.ExitCode -eq 0 -and $maiJson.Output.Count -gt 0) {
        try { $maiToken = [string](($maiJson.Output -join "`n") | ConvertFrom-Json).access_token } catch { $maiToken = '' }
    }
    if (-not $maiToken) { Start-Sleep -Seconds 2 }
}

Write-Host ''
Write-Host 'QQBridge 安装完成。' -ForegroundColor Green
Write-Host 'WebUI 登录 Token（仅在本窗口显示，不写入安装日志）：' -ForegroundColor Cyan
# 直接写控制台：会显示在窗口里，但不会进入 Start-Transcript 日志。
[Console]::WriteLine("NapCat WebUI  http://localhost:$napPort")
[Console]::WriteLine("  Token: $webuiToken")
[Console]::WriteLine("MaiBot WebUI  http://localhost:$maiPort")
[Console]::WriteLine("  Token: $maiToken")
[Console]::WriteLine("OneBot Token (internal): $onebotToken")
Write-Host '下一步：在 NapCat WebUI 扫码登录，然后运行 configure.ps1 -DiscoverGroups 设置群白名单。'

if (-not $NoBrowser) {
    try { Start-Process "http://localhost:$napPort" } catch { }
    try { Start-Process "http://localhost:$maiPort" } catch { }
}
