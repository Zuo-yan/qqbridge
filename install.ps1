[CmdletBinding()]
param(
    [string]$InstallRoot = '~/qqbridge',
    [switch]$LocalOnly = $true,
    [switch]$Lan,
    [switch]$DisableAutoStart,
    [switch]$Yes,
    [switch]$NoBrowser,
    [string]$ConfigFile,
    [switch]$Resume
)

. (Join-Path $PSScriptRoot 'qqbridge-lib.ps1')
$script:AssumeYes = [bool]$Yes

if ($ConfigFile) { $ConfigFile = (Resolve-Path -LiteralPath $ConfigFile).Path }
if (-not (Test-IsAdministrator)) {
    $arguments = @()
    foreach ($name in @('InstallRoot', 'ConfigFile')) {
        if ($PSBoundParameters.ContainsKey($name)) { $arguments += @("-$name", (Get-Variable $name -ValueOnly)) }
    }
    foreach ($name in @('Lan', 'DisableAutoStart', 'Yes', 'NoBrowser', 'Resume')) {
        if (Get-Variable $name -ValueOnly) { $arguments += "-$name" }
    }
    Restart-Elevated -EntryScript $PSCommandPath -Arguments $arguments
}

Assert-Windows11
Assert-Virtualization
Test-PackageIntegrity -Root $script:PackageRoot
$packageVersion = (Get-Content -LiteralPath (Join-Path $script:PackageRoot 'VERSION') -Raw -Encoding UTF8).Trim()
$state = Read-State
$settings = @{}
if ($ConfigFile) {
    $configObject = Get-Content -LiteralPath $ConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $allowed = @('install_root', 'llm_base_url', 'llm_model', 'llm_client_type', 'owner_qq', 'owner_name', 'bot_qq', 'maibot_port', 'napcat_port', 'onebot_port')
    foreach ($property in $configObject.PSObject.Properties) {
        if ($property.Name -notin $allowed) { Stop-QQBridge "配置文件含不支持的字段 $($property.Name)。API Key 必须在本机安全窗口填写。" }
        $settings[$property.Name] = $property.Value
    }
    foreach ($required in @('llm_base_url', 'llm_model', 'llm_client_type')) {
        if (-not $settings[$required]) { Stop-QQBridge "配置文件缺少 $required。请由 Agent 补齐非敏感配置。" }
    }
    if ($settings.install_root -and -not $PSBoundParameters.ContainsKey('InstallRoot')) { $InstallRoot = [string]$settings.install_root }
}

if ($Resume) {
    if (-not $state -or $state.phase -ne 'installing') { Stop-QQBridge '没有可续装的安装状态。已有正式实例请使用 configure.ps1 或 upgrade.ps1。' }
    if ($state.package_version -ne $packageVersion) { Stop-QQBridge '请使用与中断安装相同版本的安装包续装。' }
    $script:DistroName = [string]$state.distro
    $script:LinuxUser = [string]$state.linux_user
    $expandedRoot = [string]$state.install_root
    $linux = [pscustomobject]@{ User = $script:LinuxUser; Home = [string]$state.linux_home }
    $maiPort = [int]$state.maibot_port
    $napPort = [int]$state.napcat_port
    $onePort = [int]$state.onebot_port
    $localOnlyValue = [bool]$state.local_only
    $disableAutostartValue = [bool]$state.disable_autostart
    Assert-InstallRoot $expandedRoot
    Ensure-DockerDesktop
    Write-QQLog '继续部署已保存的实例；保留配置、凭据和登录数据。'
    Invoke-WslBash -User 'root' -ScriptPath "$(ConvertTo-WslPath $script:PackageRoot)/wsl/install.sh" -ScriptArguments @(
        '--package', (ConvertTo-WslPath $script:PackageRoot), '--install-root', $expandedRoot,
        '--target-user', $linux.User, '--platform', 'wsl', '--resume'
    ) | Out-Null
} else {
    if ($state -and $state.phase -eq 'installing') { Stop-QQBridge '检测到中断的安装。请运行 install.ps1 -Resume；不要删除实例或重新填写 Key。' }
    if ($state -and $state.phase -eq 'installed') { Stop-QQBridge '已存在正式实例。请使用 configure.ps1 修改配置，或 upgrade.ps1 升级。' }
    Ensure-WslUbuntu
    $linux = Ensure-LinuxUser
    $script:LinuxUser = $linux.User
    if (-not $ConfigFile -and -not $PSBoundParameters.ContainsKey('InstallRoot')) {
        while ($true) {
            $chosenRoot = ConvertTo-CleanText (Read-Host "WSL 内安装目录 [$InstallRoot]（回车默认，例如 ~/qqbridge；不能填写 D:\ 路径）")
            if (-not $chosenRoot) { break }
            try { Assert-InstallRoot $chosenRoot; $InstallRoot = $chosenRoot; break } catch { Write-Host $_.Exception.Message -ForegroundColor Yellow }
        }
    }
    Assert-InstallRoot $InstallRoot
    $expandedRoot = if ($InstallRoot.StartsWith('~/')) { "$($linux.Home)/$($InstallRoot.Substring(2))" } else { $InstallRoot }
    foreach ($path in @("$expandedRoot/current", "$expandedRoot/instances/default")) {
        $existing = Invoke-WslRaw -User 'root' -Arguments @('test', '-e', $path) -AllowFailure
        if ($existing.ExitCode -eq 0) { Stop-QQBridge '目标已包含实例或安装残留，已停止以保护数据。请按部署指南恢复，不要覆盖或删除。' }
    }
    Ensure-DockerDesktop
    Write-Host ''
    Write-Host '配置主聊天模型（API Key 只在稍后本机窗口填写）' -ForegroundColor Cyan
    $baseUrl = [string]$settings.llm_base_url
    while (-not (Test-ModelBaseUrl $baseUrl)) {
        if ($ConfigFile) { Stop-QQBridge 'llm_base_url 必须是有效的 HTTP(S) 服务地址，不能包含 Key 或用户凭据。' }
        $baseUrl = ConvertTo-CleanText (Read-Host '模型服务 Base URL（必填，例如 https://api.deepseek.com/v1）')
        if (-not (Test-ModelBaseUrl $baseUrl)) { Write-Host '请输入有效的 HTTP(S) 服务地址；API Key 请在稍后的本机窗口输入。' -ForegroundColor Yellow }
    }
    $model = [string]$settings.llm_model
    while (-not $model) { $model = ConvertTo-CleanText (Read-Host '模型标识（必填，以服务商提供的名称为准）') }
    $clientType = [string]$settings.llm_client_type
    if ($clientType -and $clientType -notin @('openai', 'openai_responses', 'gemini')) { Stop-QQBridge 'llm_client_type 无效。' }
    while (-not $clientType) {
        $choice = (Read-Host '协议：1) Chat Completions（默认，含 DeepSeek） 2) Responses 3) Gemini [1]').Trim()
        switch ($choice) {
            '' { $clientType = 'openai' }
            '1' { $clientType = 'openai' }
            '2' { $clientType = 'openai_responses' }
            '3' { $clientType = 'gemini' }
            default { Write-Host '请输入 1、2 或 3。' -ForegroundColor Yellow }
        }
    }
    if (([uri]$baseUrl).Host -eq 'api.deepseek.com' -and $clientType -ne 'openai') {
        Stop-QQBridge 'DeepSeek 官方接口需要 openai（Chat Completions）；请修改配置后重试。'
    }
    $ownerQq = [string]$settings.owner_qq
    $botQq = [string]$settings.bot_qq
    if (-not $ConfigFile) {
        $ownerQq = Read-QqNumber '机器人管理员 QQ（接入者本人；填写后允许此 QQ 私聊，留空不启用）'
        $botQq = Read-QqNumber '机器人账号 QQ（用于扫码登录的账号，未知可留空）'
    }
    foreach ($qq in @($ownerQq, $botQq)) { if ($qq -and $qq -notmatch '^[0-9]{5,12}$') { Stop-QQBridge 'QQ 号应为 5-12 位数字。' } }
    $ownerName = [string]$settings.owner_name
    if (-not $ConfigFile) { $ownerName = ConvertTo-CleanText (Read-Host '接入者昵称（机器人对你的称呼）[接入者]') }
    if (-not $ownerName) { $ownerName = '接入者' }
    foreach ($text in @($baseUrl, $model, $ownerName)) {
        if ($text -match '[\x00-\x1f\x7f"\\]') { Stop-QQBridge '模型配置或昵称包含不支持的引号、反斜杠或控制字符，请修正后重试。' }
    }
    if ($model -eq 'replace-with-your-provider-model-id') { Stop-QQBridge '请先将示例模型占位符替换为服务商实际模型标识。' }
    $ports = @{}
    foreach ($entry in @(@('maibot_port', 18001), @('napcat_port', 6099), @('onebot_port', 3001))) {
        $name = [string]$entry[0]
        if ($ConfigFile) {
            $port = [int]$entry[1]
            if ($settings.ContainsKey($name)) { $port = [int]$settings[$name] }
            if ($port -lt 1024 -or $port -gt 65535 -or -not (Test-TcpPortAvailable $port)) { Stop-QQBridge "$name 无效或已被占用。" }
        } else { $port = Read-Port -Label $name -Default ([int]$entry[1]) }
        if ($ports.Values -contains $port) { Stop-QQBridge '三个服务必须使用不同端口，请重新配置。' }
        $ports[$name] = $port
    }
    $maiPort = $ports.maibot_port
    $napPort = $ports.napcat_port
    $onePort = $ports.onebot_port
    $localOnlyValue = -not [bool]$Lan
    $disableAutostartValue = [bool]$DisableAutoStart
    $bind = if ($localOnlyValue) { '127.0.0.1' } else { '0.0.0.0' }
    $uid = ((Invoke-WslRaw -User 'root' -Arguments @('id', '-u', $linux.User)).Output -join '').Trim()
    $gid = ((Invoke-WslRaw -User 'root' -Arguments @('id', '-g', $linux.User)).Output -join '').Trim()
    Write-Host "部署到 $expandedRoot；模型 $model；协议 $clientType；仅本机=$localOnlyValue；登录后自启=$(-not $disableAutostartValue)"
    $apiKey = Read-LocalSecret -Title 'QQBridge 模型 API Key' -Prompt '请在本机输入或粘贴模型 API Key。Key 不会回传给 Agent 或写入安装日志。'
    $answers = @{
        llm_base_url = $baseUrl; llm_api_key = $apiKey; llm_model = $model; llm_client_type = $clientType
        owner_qq = $ownerQq; owner_name = $ownerName; bot_qq = $botQq
        maibot_port = $maiPort; napcat_port = $napPort; onebot_port = $onePort
        maibot_bind = $bind; napcat_bind = $bind; timezone = 'Asia/Shanghai'
        restart_policy = if ($disableAutostartValue) { 'no' } else { 'unless-stopped' }
        allowed_groups = @(); allowed_users = @($ownerQq | Where-Object { $_ })
    }
    $answerFile = Save-SecureAnswers -Answers $answers
    $apiKey = $null
    Write-State @{
        phase = 'installing'; package_version = $packageVersion; distro = $script:DistroName
        linux_user = $linux.User; linux_home = $linux.Home; install_root = $expandedRoot
        local_only = $localOnlyValue; disable_autostart = $disableAutostartValue
        maibot_port = $maiPort; napcat_port = $napPort; onebot_port = $onePort
    }
    try {
        $wslPackage = ConvertTo-WslPath $script:PackageRoot
        Invoke-WslBash -User 'root' -ScriptPath "$wslPackage/wsl/install.sh" -ScriptArguments @(
            '--package', $wslPackage, '--install-root', $expandedRoot, '--answers', (ConvertTo-WslPath $answerFile),
            '--target-user', $linux.User, '--napcat-uid', $uid, '--napcat-gid', $gid, '--platform', 'wsl'
        ) | Out-Null
    } finally {
        Remove-Item -LiteralPath $answerFile -Force -ErrorAction SilentlyContinue
        $answers.Clear()
    }
}

Update-QQBridgeFirewall -LocalOnly:$localOnlyValue -MaiBotPort $maiPort -NapCatPort $napPort
Set-DockerAutostart -Disable:$disableAutostartValue
Write-State @{
    phase = 'installed'; package_version = $packageVersion; distro = $script:DistroName
    linux_user = $linux.User; linux_home = $linux.Home; install_root = $expandedRoot
    local_only = $localOnlyValue; disable_autostart = $disableAutostartValue
    maibot_port = $maiPort; napcat_port = $napPort; onebot_port = $onePort
}
Write-Host '基础安装完成；QQ 登录和群白名单仍需完成。' -ForegroundColor Green
Write-Host "NapCat: http://localhost:$napPort   MaiBot: http://localhost:$maiPort"
Write-Host '登录 Token 将只在本机凭据窗口中显示；重新查看请双击 access.cmd。'
Start-Process powershell.exe -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f (Join-Path $PSScriptRoot 'access.ps1'))
if (-not $NoBrowser) {
    Start-Process "http://localhost:$napPort"
    Start-Process "http://localhost:$maiPort"
}
Write-Host '扫码后运行 configure.ps1 -DiscoverGroups，再运行 verify.ps1 -RequireLogin 验证接入。'
