[CmdletBinding()]
param(
    [string]$InstallRoot = '~/qqbridge',
    [switch]$LocalOnly,
    [switch]$DisableAutoStart
)

. (Join-Path $PSScriptRoot 'qqbridge-lib.ps1')

if (-not (Test-IsAdministrator)) {
    $arguments = @('-InstallRoot', $InstallRoot)
    if ($LocalOnly) { $arguments += '-LocalOnly' }
    if ($DisableAutoStart) { $arguments += '-DisableAutoStart' }
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
$baseUrl = Read-Host 'OpenAI 兼容 Base URL [https://api.openai.com/v1]'
if (-not $baseUrl) { $baseUrl = 'https://api.openai.com/v1' }
$model = Read-Host '模型标识（例如 gpt-4.1-mini / deepseek-chat）'
if (-not $model) { Stop-QQBridge '模型标识不能为空。' }
$secureKey = Read-Host 'API Key（输入不会回显）' -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}
if (-not $apiKey) { Stop-QQBridge 'API Key 不能为空。' }

Write-Host '客户端类型：1) openai  2) openai_responses  3) gemini'
$clientChoice = Read-Host '选择 [1]'
switch ($clientChoice) {
    '2' { $clientType = 'openai_responses' }
    '3' { $clientType = 'gemini' }
    default { $clientType = 'openai' }
}

$ownerQq = (Read-Host '管理员/群主 QQ（可留空，人设管理命令将不可用）').Trim()
if ($ownerQq -and $ownerQq -notmatch '^\d{5,12}$') {
    Stop-QQBridge 'QQ 号格式无效。'
}
$ownerName = (Read-Host '群主称呼 [群主]').Trim()
if (-not $ownerName) { $ownerName = '群主' }
$botQq = (Read-Host '机器人 QQ（登录后再填可留空）').Trim()
if ($botQq -and $botQq -notmatch '^\d{5,12}$') {
    Stop-QQBridge '机器人 QQ 格式无效。'
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
            '--napcat-gid', $gid
        )
} finally {
    Remove-Item -LiteralPath $answerFile -Force -ErrorAction SilentlyContinue
}

$localOnlyValue = [bool]$LocalOnly.IsPresent
$disableAutostartValue = [bool]$DisableAutoStart.IsPresent
Update-QQBridgeFirewall -LocalOnly:$localOnlyValue -MaiBotPort $maiPort -NapCatPort $napPort
Set-DockerAutostart -Disable:$disableAutostartValue

Write-State @{
    phase = 'installed'
    package_version = '1.0.0'
    distro = $script:DistroName
    linux_user = $linux.User
    linux_home = $linux.Home
    install_root = $expandedRoot
    local_only = $LocalOnly.IsPresent
    maibot_port = $maiPort
    napcat_port = $napPort
    onebot_port = $onePort
}

Write-Host ''
Write-Host 'QQBridge 安装完成。' -ForegroundColor Green
Write-Host "NapCat WebUI: http://localhost:$napPort"
Write-Host "MaiBot WebUI: http://localhost:$maiPort"
Write-Host '下一步：在 NapCat WebUI 扫码登录，然后运行 configure.ps1 -DiscoverGroups 设置群白名单。'
