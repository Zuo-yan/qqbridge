[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Package
)

. (Join-Path $PSScriptRoot 'qqbridge-lib.ps1')

if (-not (Test-IsAdministrator)) {
    Restart-Elevated -EntryScript $PSCommandPath -Arguments @('-Package', $Package)
}

Assert-Windows11
$context = Get-QQBridgeContext
$zipPath = (Resolve-Path -LiteralPath $Package).Path
if ([IO.Path]::GetExtension($zipPath) -ne '.zip') {
    Stop-QQBridge '升级包必须是 ZIP 文件。'
}

$shaCandidates = @("$zipPath.sha256", [IO.Path]::ChangeExtension($zipPath, '.sha256'))
$shaVerified = $false
foreach ($shaFile in $shaCandidates) {
    if (Test-Path -LiteralPath $shaFile) {
        $expected = ((Get-Content -LiteralPath $shaFile -Raw -Encoding UTF8).Trim() -split '\s+')[0].ToLowerInvariant()
        if ($expected -notmatch '^[0-9a-f]{64}$') {
            Stop-QQBridge "SHA-256 文件格式无效: $shaFile"
        }
        $actual = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $expected) {
            Stop-QQBridge 'ZIP 的 SHA-256 校验失败。'
        }
        Write-QQLog 'ZIP SHA-256 校验通过。'
        $shaVerified = $true
        break
    }
}
if (-not $shaVerified) {
    Stop-QQBridge '升级包缺少同名 .sha256 校验文件，拒绝继续。'
}

$temp = Join-Path ([IO.Path]::GetTempPath()) "qqbridge-upgrade-$([guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path $temp | Out-Null
try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($zipPath)
    try {
        foreach ($entry in $archive.Entries) {
            $destination = [IO.Path]::GetFullPath((Join-Path $temp $entry.FullName))
            $tempPrefix = $temp.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
            if ($destination -ne $temp -and -not $destination.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase)) {
                Stop-QQBridge "ZIP 包含不安全路径: $($entry.FullName)"
            }
        }
    } finally {
        $archive.Dispose()
    }
    Expand-Archive -LiteralPath $zipPath -DestinationPath $temp -Force

    $packageRoot = if (Test-Path -LiteralPath (Join-Path $temp 'manifest.json')) {
        $temp
    } else {
        $children = @(Get-ChildItem -LiteralPath $temp -Directory)
        if ($children.Count -eq 1 -and (Test-Path -LiteralPath (Join-Path $children[0].FullName 'manifest.json'))) {
            $children[0].FullName
        } else {
            Stop-QQBridge '无法识别 ZIP 中的安装包根目录。'
        }
    }

    Test-PackageIntegrity -Root $packageRoot
    $newVersion = (Get-Content -LiteralPath (Join-Path $packageRoot 'VERSION') -Raw -Encoding UTF8).Trim()
    $currentResult = Invoke-WslRaw -User 'root' -Arguments @('cat', "$($context.InstallRoot)/current/VERSION")
    $currentVersion = (($currentResult.Output | Select-Object -First 1) -as [string]).Trim()
    try {
        if ([version]$newVersion -le [version]$currentVersion) {
            Stop-QQBridge "升级包版本 $newVersion 必须高于当前版本 $currentVersion。"
        }
    } catch {
        Stop-QQBridge "版本号格式无效: $newVersion / $currentVersion"
    }

    Ensure-DockerDesktop
    $wslPackage = ConvertTo-WslPath $packageRoot
    $result = Invoke-WslBash `
        -User 'root' `
        -ScriptPath "$wslPackage/wsl/upgrade.sh" `
        -ScriptArguments @(
            '--package', $wslPackage,
            '--install-root', $context.InstallRoot,
            '--target-user', $context.LinuxUser
        )
    if ($result.ExitCode -ne 0) {
        Stop-QQBridge '升级失败；脚本已尝试自动回滚。'
    }

    $state = Read-State
    $state.package_version = $newVersion
    Write-State $state
    Write-Host "升级完成：$currentVersion -> $newVersion" -ForegroundColor Green
} finally {
    if (Test-Path -LiteralPath $temp) {
        Remove-Item -LiteralPath $temp -Recurse -Force
    }
}
