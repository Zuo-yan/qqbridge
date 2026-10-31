[CmdletBinding()]
param(
    [string]$BackupId
)

. (Join-Path $PSScriptRoot 'qqbridge-lib.ps1')

if (-not (Test-IsAdministrator)) {
    $arguments = @()
    if ($BackupId) { $arguments += @('-BackupId', $BackupId) }
    Restart-Elevated -EntryScript $PSCommandPath -Arguments $arguments
}

Assert-Windows11
$context = Get-QQBridgeContext
Ensure-DockerDesktop

$arguments = @(
    '--install-root', $context.InstallRoot,
    '--target-user', $context.LinuxUser
)
if ($BackupId) {
    if ($BackupId -notmatch '^[0-9TZ-]+$') {
        Stop-QQBridge 'BackupId 格式无效。'
    }
    $arguments += @('--backup-id', $BackupId)
}

$result = Invoke-WslBash `
    -User 'root' `
    -ScriptPath "$($context.InstallRoot)/current/wsl/rollback.sh" `
    -ScriptArguments $arguments `
    -AllowFailure
if ($result.ExitCode -ne 0) {
    Stop-QQBridge '回滚失败，请检查上方日志。'
}

$versionResult = Invoke-WslRaw -User 'root' -Arguments @('cat', "$($context.InstallRoot)/current/VERSION")
$version = (($versionResult.Output | Select-Object -First 1) -as [string]).Trim()
$state = Read-State
$state.package_version = $version
Write-State $state
Write-Host "回滚完成，当前版本 $version。" -ForegroundColor Green
