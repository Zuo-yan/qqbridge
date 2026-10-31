[CmdletBinding()]
param(
    [string]$Instance = 'default',
    [switch]$Advanced,
    [switch]$DiscoverGroups
)

. (Join-Path $PSScriptRoot 'qqbridge-lib.ps1')

if (-not (Test-IsAdministrator)) {
    $arguments = @('-Instance', $Instance)
    if ($Advanced) { $arguments += '-Advanced' }
    if ($DiscoverGroups) { $arguments += '-DiscoverGroups' }
    Restart-Elevated -EntryScript $PSCommandPath -Arguments $arguments
}

Assert-Windows11
$context = Get-QQBridgeContext
if ($Instance -notmatch '^[A-Za-z0-9_-]+$') {
    Stop-QQBridge 'Instance 名称无效。'
}
$instancePath = "$($context.InstallRoot)/instances/$Instance"
$probe = Invoke-WslRaw -User 'root' -Arguments @('test', '-f', "$instancePath/.env") -AllowFailure
if ($probe.ExitCode -ne 0) {
    Stop-QQBridge "找不到实例 $Instance。"
}

$currentBase = Get-InstanceEnvValue -Context $context -Key 'LLM_BASE_URL'
$currentModel = Get-InstanceEnvValue -Context $context -Key 'LLM_MODEL'
$currentClient = Get-InstanceEnvValue -Context $context -Key 'LLM_CLIENT_TYPE'
$currentOwner = Get-InstanceEnvValue -Context $context -Key 'OWNER_QQ'
$currentBot = Get-InstanceEnvValue -Context $context -Key 'BOT_QQ'
$currentMaiPort = [int](Get-InstanceEnvValue -Context $context -Key 'MAIBOT_PORT')
$currentNapPort = [int](Get-InstanceEnvValue -Context $context -Key 'NAPCAT_PORT')
$currentOnePort = [int](Get-InstanceEnvValue -Context $context -Key 'ONEBOT_PORT')
$currentBind = Get-InstanceEnvValue -Context $context -Key 'MAIBOT_BIND'
$answers = @{}

Write-Host ''
Write-Host '基础配置（直接回车表示保留）' -ForegroundColor Cyan
Write-Host "当前模型: $currentModel @ $currentBase ($currentClient)"
$base = (Read-Host '新的 Base URL').Trim()
if ($base) { $answers.llm_base_url = $base }
$model = (Read-Host '新的模型标识').Trim()
if ($model) { $answers.llm_model = $model }
Write-Host '客户端类型：1) openai  2) openai_responses  3) gemini  空) 保留'
$clientChoice = (Read-Host '选择').Trim()
switch ($clientChoice) {
    '1' { $answers.llm_client_type = 'openai' }
    '2' { $answers.llm_client_type = 'openai_responses' }
    '3' { $answers.llm_client_type = 'gemini' }
}
$secureKey = Read-Host '新的 API Key（回车保留，输入不回显）' -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $newKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}
if ($newKey) { $answers.llm_api_key = $newKey }
$newKey = $null

Write-Host "当前群主 QQ: $(if($currentOwner){$currentOwner}else{'(未设置)'})"
$owner = (Read-Host '新的群主 QQ（输入 - 可清空）').Trim()
if ($owner -eq '-') {
    $answers.owner_qq = ''
} elseif ($owner) {
    if ($owner -notmatch '^\d{5,12}$') { Stop-QQBridge 'QQ 号格式无效。' }
    $answers.owner_qq = $owner
}
$ownerName = (Read-Host '新的群主称呼').Trim()
if ($ownerName) { $answers.owner_name = $ownerName }
Write-Host "当前机器人 QQ: $(if($currentBot){$currentBot}else{'(未设置)'})"
$bot = (Read-Host '新的机器人 QQ（输入 - 可清空）').Trim()
if ($bot -eq '-') {
    $answers.bot_qq = ''
} elseif ($bot) {
    if ($bot -notmatch '^\d{5,12}$') { Stop-QQBridge 'QQ 号格式无效。' }
    $answers.bot_qq = $bot
}

$changePorts = Read-Host '是否修改端口？[y/N]'
if ($changePorts -and $changePorts.Trim().ToLowerInvariant() -in @('y', 'yes', '是')) {
    $maiPortText = Read-Host "MaiBot 端口 [$currentMaiPort]"
    $napPortText = Read-Host "NapCat 端口 [$currentNapPort]"
    $onePortText = Read-Host "OneBot 本机端口 [$currentOnePort]"
    $newMai = if ($maiPortText) { [int]$maiPortText } else { $currentMaiPort }
    $newNap = if ($napPortText) { [int]$napPortText } else { $currentNapPort }
    $newOne = if ($onePortText) { [int]$onePortText } else { $currentOnePort }
    foreach ($pair in @(
        @{ Name = 'MaiBot'; New = $newMai; Old = $currentMaiPort },
        @{ Name = 'NapCat'; New = $newNap; Old = $currentNapPort },
        @{ Name = 'OneBot'; New = $newOne; Old = $currentOnePort }
    )) {
        if ($pair.New -lt 1024 -or $pair.New -gt 65535) {
            Stop-QQBridge "$($pair.Name) 端口超出范围。"
        }
        if ($pair.New -ne $pair.Old -and -not (Test-TcpPortAvailable -Port $pair.New)) {
            Stop-QQBridge "$($pair.Name) 端口 $($pair.New) 已被占用。"
        }
    }
    $answers.maibot_port = $newMai
    $answers.napcat_port = $newNap
    $answers.onebot_port = $newOne
}

if ($Advanced) {
    Write-Host ''
    Write-Host '高级外部服务（直接回车表示跳过/保留）' -ForegroundColor Cyan
    $searchBase = (Read-Host '搜索服务 Base URL').Trim()
    $searchModel = (Read-Host '搜索服务模型').Trim()
    $secureSearch = Read-Host '搜索服务 API Key（不回显）' -AsSecureString
    $searchBstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureSearch)
    try {
        $searchKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($searchBstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($searchBstr)
    }
    if ($searchBase -or $searchModel -or $searchKey) {
        if (-not ($searchBase -and $searchModel -and $searchKey)) {
            Stop-QQBridge '启用搜索插件时，Base URL、模型和 API Key 必须同时填写。'
        }
        $answers.search_base_url = $searchBase
        $answers.search_model = $searchModel
        $answers.search_api_key = $searchKey
    }
    $searchKey = $null

    $secureTts = Read-Host '小米 MiMo TTS API Key（留空跳过，输入不回显）' -AsSecureString
    $ttsBstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureTts)
    try {
        $ttsKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ttsBstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ttsBstr)
    }
    if ($ttsKey) {
        $answers.tts_api_key = $ttsKey
        $ttsUrl = (Read-Host 'TTS API URL [https://api.xiaomimimo.com/v1/chat/completions]').Trim()
        if ($ttsUrl) { $answers.tts_api_url = $ttsUrl }
        $ttsModel = (Read-Host 'TTS 模型 [mimo-v2.5-tts]').Trim()
        if ($ttsModel) { $answers.tts_model = $ttsModel }
        $ttsVoice = (Read-Host '默认音色 [冰糖]').Trim()
        if ($ttsVoice) { $answers.tts_voice = $ttsVoice }
    }
    $ttsKey = $null
    $codexPath = (Read-Host 'Codex CLI 容器内绝对路径（留空跳过）').Trim()
    if ($codexPath) { $answers.codex_path = $codexPath }
    $proxy = (Read-Host '链接解析代理，例如 http://172.17.0.1:7890（留空跳过）').Trim()
    if ($proxy) { $answers.http_proxy = $proxy }
    foreach ($item in @(
        @{ Prompt = '知乎 Cookie'; Key = 'zhihu_cookie' },
        @{ Prompt = 'YouTube Cookie'; Key = 'youtube_cookie' },
        @{ Prompt = 'Pixiv Cookie'; Key = 'pixiv_cookie' },
        @{ Prompt = '抖音 Cookie'; Key = 'douyin_cookie' },
        @{ Prompt = '小红书 Cookie'; Key = 'xhs_cookie' },
        @{ Prompt = 'Bilibili Cookie'; Key = 'bilibili_cookie' },
        @{ Prompt = '萌娘百科 Cookie'; Key = 'moegirl_cookie' }
    )) {
        $value = (Read-Host "$($item.Prompt)（留空跳过）").Trim()
        if ($value) { $answers[$item.Key] = $value }
    }
}

if ($DiscoverGroups) {
    Write-Host ''
    Write-Host '正在从 NapCat/OneBot 读取群列表；请确认机器人 QQ 已扫码登录。' -ForegroundColor Cyan
    $onebotScript = "$($context.InstallRoot)/current/wsl/onebot.py"
    $result = Invoke-WslRaw -User 'root' -Arguments @(
        'python3', $onebotScript,
        '--instance', $instancePath,
        '--action', 'get_group_list'
    ) -AllowFailure
    if ($result.ExitCode -ne 0) {
        $result.Output | ForEach-Object { Write-Host $_ }
        Stop-QQBridge '读取群列表失败。请先在 NapCat WebUI 完成 QQ 登录。'
    }
    $json = ($result.Output -join "`n").Trim()
    $groups = @($json | ConvertFrom-Json)
    if ($groups.Count -eq 0) {
        Stop-QQBridge '机器人当前没有可用群列表。'
    }
    for ($i = 0; $i -lt $groups.Count; $i++) {
        Write-Host ("{0,3}. {1}  ({2})" -f ($i + 1), $groups[$i].group_name, $groups[$i].group_id)
    }
    $selection = Read-Host '输入允许的群序号，逗号分隔，或 all'
    $selected = @()
    if ($selection.Trim().ToLowerInvariant() -eq 'all') {
        $selected = @($groups | ForEach-Object { [string]$_.group_id })
    } else {
        foreach ($part in $selection.Split(',')) {
            $index = 0
            if (-not [int]::TryParse($part.Trim(), [ref]$index) -or $index -lt 1 -or $index -gt $groups.Count) {
                Stop-QQBridge "群序号无效: $part"
            }
            $selected += [string]$groups[$index - 1].group_id
        }
    }
    $privatePrompt = if ($currentOwner) { "允许私聊的 QQ（逗号分隔）[$currentOwner]" } else { '允许私聊的 QQ（逗号分隔，可留空）' }
    $privateText = (Read-Host $privatePrompt).Trim()
    if (-not $privateText) {
        $privateText = $currentOwner
    }
    $privateUsers = @($privateText.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    foreach ($qq in $privateUsers) {
        if ($qq -notmatch '^\d{5,12}$') { Stop-QQBridge "QQ 号无效: $qq" }
    }
    $answers.allowed_groups = @($selected | Select-Object -Unique)
    $answers.allowed_users = @($privateUsers | Select-Object -Unique)
}

if ($answers.Count -eq 0) {
    Write-QQLog '没有需要修改的配置。'
    exit 0
}

$answerFile = Save-SecureAnswers -Answers $answers
try {
    $package = "$($context.InstallRoot)/current"
    $scriptPath = "$package/wsl/configure.sh"
    $answerPath = ConvertTo-WslPath $answerFile
    Invoke-WslBash `
        -User 'root' `
        -ScriptPath $scriptPath `
        -ScriptArguments @(
            '--package', $package,
            '--install-root', $context.InstallRoot,
            '--answers', $answerPath,
            '--target-user', $context.LinuxUser,
            '--instance', $Instance
        ) | Out-Null
} finally {
    Remove-Item -LiteralPath $answerFile -Force -ErrorAction SilentlyContinue
}

$finalMai = if ($answers.ContainsKey('maibot_port')) { [int]$answers.maibot_port } else { $currentMaiPort }
$finalNap = if ($answers.ContainsKey('napcat_port')) { [int]$answers.napcat_port } else { $currentNapPort }
$finalOne = if ($answers.ContainsKey('onebot_port')) { [int]$answers.onebot_port } else { $currentOnePort }
$localOnly = $currentBind -in @('127.0.0.1', 'localhost')
Update-QQBridgeFirewall -LocalOnly:$localOnly -MaiBotPort $finalMai -NapCatPort $finalNap
$state = Read-State
if ($state) {
    $state.maibot_port = $finalMai
    $state.napcat_port = $finalNap
    $state.onebot_port = $finalOne
    Write-State $state
}

Write-Host ''
Write-Host '配置已应用。' -ForegroundColor Green
Write-Host "NapCat WebUI: http://localhost:$finalNap"
Write-Host "MaiBot WebUI: http://localhost:$finalMai"
