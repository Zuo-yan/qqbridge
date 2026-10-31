[CmdletBinding()]
param([string]$ConfigFile, [switch]$Resume)
. (Join-Path $PSScriptRoot 'qqbridge-lib.ps1')
if ($ConfigFile) { $ConfigFile = (Resolve-Path -LiteralPath $ConfigFile).Path }
if (-not (Test-IsAdministrator)) {
    $forward = @()
    if ($ConfigFile) { $forward += @('-ConfigFile', $ConfigFile) }
    if ($Resume) { $forward += '-Resume' }
    Restart-Elevated -EntryScript $PSCommandPath -Arguments $forward
}
try {
    $params = @{ Yes = $true }
    if ($ConfigFile) { $params.ConfigFile = $ConfigFile }
    $saved = Read-State
    if ($Resume -or ($saved -and $saved.phase -eq 'installing')) { $params.Resume = $true }
    & (Join-Path $PSScriptRoot 'install.ps1') @params
    Write-Host '下一步：扫码、选择白名单，再执行严格验证。'
} catch {
    Write-Host '安装未完成。请保留实例并查看错误；只有配置准备完成的中断安装可用 install.ps1 -Resume。' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Yellow
    Write-Host 'Agent 可读取 install-state.json 的非敏感状态；不要导出 .env 或原始容器日志。'
    exit 1
}
