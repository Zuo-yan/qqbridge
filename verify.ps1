[CmdletBinding()]
param(
    [string]$Instance = 'default',
    [switch]$RequireLogin
)

. (Join-Path $PSScriptRoot 'qqbridge-lib.ps1')

Assert-Windows11
$context = Get-QQBridgeContext
if ($Instance -notmatch '^[A-Za-z0-9_-]+$') {
    Stop-QQBridge 'Instance 名称无效。'
}

$release = "$($context.InstallRoot)/current"
$instancePath = "$($context.InstallRoot)/instances/$Instance"
$probe = Invoke-WslRaw -User 'root' -Arguments @('test', '-f', "$instancePath/.env") -AllowFailure
if ($probe.ExitCode -ne 0) {
    Stop-QQBridge "找不到实例 $Instance。"
}

Write-Host ''
Write-Host 'QQBridge 运行验证' -ForegroundColor Cyan
$verifyArguments = @('--install-root', $context.InstallRoot, '--instance', $Instance, '--target-user', $context.LinuxUser)
if ($RequireLogin) { $verifyArguments += '--require-login' }
$result = Invoke-WslBash -User 'root' -ScriptPath "$release/wsl/verify.sh" -ScriptArguments $verifyArguments -AllowFailure

$state = Read-State
if (-not $state.local_only) {
    $rules = @(Get-NetFirewallRule -DisplayName 'QQBridge*' -ErrorAction SilentlyContinue)
    if ($rules.Count -ge 2) {
        Write-Host 'PASS  专用网络防火墙规则'
    } else {
        Write-Host 'WARN  专用网络防火墙规则不完整'
    }
}

if ($result.ExitCode -ne 0) {
    Write-Host '验证失败；请查看上方 FAIL 项。' -ForegroundColor Red
    exit $result.ExitCode
}

if ($RequireLogin) {
    Write-Host '基础服务与 QQ 登录检查通过；请在已选群中发送消息完成最终验收。' -ForegroundColor Green
} else {
    Write-Host '基础服务检查通过；是否已登录 QQ 请查看上方 WARN。扫码后运行 verify.ps1 -RequireLogin。' -ForegroundColor Green
}
