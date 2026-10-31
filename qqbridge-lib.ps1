$ErrorActionPreference = 'Stop'

$script:PackageRoot = Split-Path -Parent $PSCommandPath
$script:StateDir = Join-Path $env:ProgramData 'QQBridge'
$script:StateFile = Join-Path $script:StateDir 'install-state.json'
$script:DistroName = 'Ubuntu'
$script:DockerDesktopPath = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
$script:DockerExePath = 'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
$script:AssumeYes = $false

function Write-QQLog {
    param([Parameter(Mandatory)][string]$Message)
    Write-Host "[QQBridge] $Message"
}

function Stop-QQBridge {
    param([Parameter(Mandatory)][string]$Message)
    throw $Message
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Restart-Elevated {
    param(
        [Parameter(Mandatory)][string]$EntryScript,
        [object[]]$Arguments = @()
    )
    $quoted = @()
    foreach ($value in $Arguments) {
        $quoted += '"' + ([string]$value).Replace('"', '\"') + '"'
    }
    $argumentLine = "-NoExit -NoProfile -ExecutionPolicy Bypass -File `"$EntryScript`" " + ($quoted -join ' ')
    Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList $argumentLine
    exit 0
}

function Assert-Windows11 {
    if (-not [Environment]::Is64BitOperatingSystem) {
        Stop-QQBridge 'QQBridge 仅支持 Windows 11 x64。'
    }
    $os = Get-CimInstance Win32_OperatingSystem
    $build = [int]($os.Version.Split('.')[2])
    if ($build -lt 22000) {
        Stop-QQBridge "检测到 $($os.Caption) build $build；需要 Windows 11 build 22000 或更高。"
    }
    Write-QQLog "Windows: $($os.Caption) build $build"
}

function Assert-Virtualization {
    $computer = Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue
    if ($computer -and $computer.HypervisorPresent) {
        Write-QQLog '硬件虚拟化：已启用'
        return
    }
    $cpu = Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cpu -and $cpu.VirtualizationFirmwareEnabled -eq $false -and $cpu.VMMonitorModeExtensions -eq $false) {
        Stop-QQBridge 'CPU 硬件虚拟化未启用。请在 BIOS/UEFI 中启用 Intel VT-x 或 AMD-V 后重试。'
    }
    Write-QQLog '硬件虚拟化：未确认，继续检查 WSL2 功能状态。'
}

function Read-State {
    if (-not (Test-Path -LiteralPath $script:StateFile)) {
        return $null
    }
    return Get-Content -LiteralPath $script:StateFile -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][AllowEmptyString()][string]$Content
    )
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($Path, $Content, $encoding)
}

function Write-State {
    param([Parameter(Mandatory)]$State)
    New-Item -ItemType Directory -Force -Path $script:StateDir | Out-Null
    $values = @{}
    if ($State -is [hashtable]) {
        foreach ($key in $State.Keys) { $values[$key] = $State[$key] }
    } else {
        foreach ($property in $State.PSObject.Properties) { $values[$property.Name] = $property.Value }
    }
    $values['updated_at'] = (Get-Date).ToUniversalTime().ToString('o')
    Write-Utf8NoBom -Path $script:StateFile -Content ($values | ConvertTo-Json -Depth 8)
}

function ConvertTo-WslPath {
    param([Parameter(Mandatory)][string]$Path)
    $resolved = [System.IO.Path]::GetFullPath($Path)
    if ($resolved -notmatch '^([A-Za-z]):\\(.*)$') {
        Stop-QQBridge "无法把路径转换为 WSL 路径: $Path"
    }
    $drive = $Matches[1].ToLowerInvariant()
    $rest = $Matches[2].Replace('\', '/')
    return "/mnt/$drive/$rest"
}

function Invoke-WslRaw {
    param(
        [Parameter(Mandatory)][string]$User,
        [Parameter(Mandatory)][string[]]$Arguments,
        [switch]$AllowFailure
    )
    $wslArgs = @('-d', $script:DistroName, '-u', $User, '--') + $Arguments
    $output = & wsl.exe @wslArgs 2>&1
    $code = $LASTEXITCODE
    if ($code -ne 0 -and -not $AllowFailure) {
        throw "WSL command failed ($code): $($output -join [Environment]::NewLine)"
    }
    return [pscustomobject]@{ ExitCode = $code; Output = @($output) }
}

function Invoke-WslBash {
    param(
        [Parameter(Mandatory)][string]$User,
        [Parameter(Mandatory)][string]$ScriptPath,
        [string[]]$ScriptArguments = @(),
        [switch]$AllowFailure
    )
    $arguments = @('bash', $ScriptPath) + $ScriptArguments
    $result = Invoke-WslRaw -User $User -Arguments $arguments -AllowFailure:$AllowFailure
    if ($result.Output.Count -gt 0) {
        $result.Output | ForEach-Object { Write-Host $_ }
    }
    return $result
}

function Get-WslDefaultUser {
    $result = Invoke-WslRaw -User 'root' -Arguments @('bash', '-lc', 'id -un') -AllowFailure
    if ($result.ExitCode -ne 0) {
        return $null
    }
    return (($result.Output | Select-Object -First 1) -as [string]).Trim()
}

function Test-WslFeature {
    param([Parameter(Mandatory)][string]$Name)
    $feature = Get-WindowsOptionalFeature -Online -FeatureName $Name -ErrorAction SilentlyContinue
    return $feature -and $feature.State -eq 'Enabled'
}

function Set-RebootPending {
    param([string]$Reason)
    Write-State @{
        phase = 'awaiting_reboot'
        reason = $Reason
        package_root = $script:PackageRoot
        distro = $script:DistroName
    }
    Write-Host ''
    Write-Host '需要重启 Windows 才能继续安装。脚本不会自动重启电脑。' -ForegroundColor Yellow
    Write-Host '重启后请以管理员身份重新运行同一个 install.ps1；安装状态已保存。'
    exit 3010
}

function Confirm-SystemChange {
    param([Parameter(Mandatory)][string]$Message)
    if ($script:AssumeYes) {
        Write-QQLog "$Message 已自动确认（-Yes）。"
        return
    }
    $answer = Read-Host "$Message [Y/n]"
    if ($answer -and $answer.Trim().ToLowerInvariant() -notin @('y', 'yes', '是')) {
        Stop-QQBridge '用户取消了安装。'
    }
}

function Ensure-WslUbuntu {
    $rebootRequired = $false
    foreach ($feature in @('Microsoft-Windows-Subsystem-Linux', 'VirtualMachinePlatform')) {
        if (-not (Test-WslFeature $feature)) {
            Confirm-SystemChange "需要启用 Windows 功能 $feature。是否继续？"
            Write-QQLog "启用 $feature"
            & dism.exe /online /enable-feature /featurename:$feature /all /norestart | Out-Host
            if ($LASTEXITCODE -eq 3010) {
                $rebootRequired = $true
            } elseif ($LASTEXITCODE -ne 0) {
                Stop-QQBridge "启用 $feature 失败，退出码 $LASTEXITCODE。"
            }
        }
    }
    if ($rebootRequired) {
        Set-RebootPending 'WSL Windows 功能已启用'
    }

    $list = & wsl.exe -l -q 2>$null
    # wsl.exe 在重定向时输出 UTF-16LE，PowerShell 5.1 会按控制台代码页解码，需去掉夹带的 NUL。
    $distros = @($list | ForEach-Object { ([string]$_ -replace "`0", '').Trim() } | Where-Object { $_ })
    if ($distros -notcontains $script:DistroName) {
        Confirm-SystemChange '需要安装 WSL2 Ubuntu 发行版。是否继续？'
        Write-QQLog '安装 Ubuntu（可能需要下载数分钟）'
        $output = @(& wsl.exe --install -d $script:DistroName --no-launch 2>&1 | ForEach-Object { ([string]$_ -replace "`0", '') })
        $code = $LASTEXITCODE
        $output | ForEach-Object { Write-Host $_ }
        if ($code -ne 0) {
            if (($output -join ' ') -match 'restart|重启|reboot') {
                Set-RebootPending 'WSL2/Ubuntu 安装完成但需要重启'
            }
            throw "安装 Ubuntu 失败，退出码 $code。"
        }
        if (($output -join ' ') -match 'restart|重启|reboot') {
            Set-RebootPending 'WSL2/Ubuntu 安装完成但需要重启'
        }
    }

    $setDefault = @(& wsl.exe --set-default-version 2 2>&1 | ForEach-Object { ([string]$_ -replace "`0", '') })
    if ($LASTEXITCODE -ne 0 -and (($setDefault -join ' ') -notmatch 'already|已经|2')) {
        Write-QQLog "无法显式设置 WSL 默认版本为 2：$($setDefault -join ' ')"
    }
    $versionOutput = @(& wsl.exe -l -v 2>&1 | ForEach-Object { ([string]$_ -replace "`0", '').Trim() })
    $ubuntuVersionLine = @($versionOutput | Where-Object { ([string]$_) -match "(^|\s)$([regex]::Escape($script:DistroName))(\s|$)" }) | Select-Object -First 1
    if ($ubuntuVersionLine -and ([string]$ubuntuVersionLine) -notmatch '\s2\s*$') {
        Write-QQLog "将 $($script:DistroName) 切换到 WSL2"
        & wsl.exe --set-version $script:DistroName 2 2>&1 | ForEach-Object { Write-Host $_ }
        if ($LASTEXITCODE -ne 0) {
            Stop-QQBridge 'Ubuntu 无法切换到 WSL2，请更新 WSL 并重试。'
        }
    }

    $probe = Invoke-WslRaw -User 'root' -Arguments @('bash', '-lc', 'true') -AllowFailure
    if ($probe.ExitCode -ne 0) {
        Write-QQLog '初始化 Ubuntu 实例'
        & wsl.exe --update 2>&1 | ForEach-Object { Write-Host $_ }
        $probe = Invoke-WslRaw -User 'root' -Arguments @('bash', '-lc', 'true') -AllowFailure
        if ($probe.ExitCode -ne 0) {
            Set-RebootPending 'Ubuntu 实例尚未完成初始化'
        }
    }
}

function Get-NormalizedLinuxUser {
    $name = $env:USERNAME.ToLowerInvariant() -replace '[^a-z0-9_-]', ''
    if (-not $name) {
        $name = 'qqbridge'
    }
    if ($name -match '^[0-9]') {
        $name = "qq$name"
    }
    return $name.Substring(0, [Math]::Min(31, $name.Length))
}

function Ensure-LinuxUser {
    $user = Get-NormalizedLinuxUser
    $safeUser = $user -replace '[^a-z0-9_-]', ''
    $script = @"
set -e
if ! id -u '$safeUser' >/dev/null 2>&1; then
  useradd -m -s /bin/bash '$safeUser'
fi
if getent group docker >/dev/null 2>&1; then
  usermod -aG docker '$safeUser'
fi
if [ ! -f /etc/wsl.conf ]; then
  printf '[user]\ndefault=$safeUser\n' > /etc/wsl.conf
fi
"@
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($script))
    $command = "echo $encoded | base64 -d | bash"
    $result = Invoke-WslRaw -User 'root' -Arguments @('bash', '-lc', $command)
    & wsl.exe --terminate $script:DistroName | Out-Null
    Start-Sleep -Seconds 2
    $homeResult = Invoke-WslRaw -User 'root' -Arguments @('bash', '-lc', "getent passwd '$safeUser' | cut -d: -f6")
    $home = (($homeResult.Output | Select-Object -First 1) -as [string]).Trim()
    if (-not $home) {
        Stop-QQBridge "无法读取 Linux 用户 $safeUser 的主目录。"
    }
    return [pscustomobject]@{ User = $safeUser; Home = $home }
}

function Get-DockerExe {
    if (Test-Path -LiteralPath $script:DockerExePath) {
        return $script:DockerExePath
    }
    $command = Get-Command docker.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    return $null
}

function Set-DockerWslIntegration {
    $settingsPath = Join-Path $env:APPDATA 'Docker\settings-store.json'
    $settingsDir = Split-Path -Parent $settingsPath
    New-Item -ItemType Directory -Force -Path $settingsDir | Out-Null
    $alreadyIntegrated = $false
    if (Test-Path -LiteralPath $settingsPath) {
        $backup = "$settingsPath.qqbridge-$((Get-Date).ToString('yyyyMMddHHmmss')).bak"
        Copy-Item -LiteralPath $settingsPath -Destination $backup -Force
        $settings = Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $integrated = @($settings.IntegratedWslDistros | Where-Object { $_ } | ForEach-Object { [string]$_ })
        $alreadyIntegrated = ($settings.EnableIntegrationWithDefaultWslDistro -eq $true) -and ($integrated -contains $script:DistroName) -and ($settings.UseWindowsContainers -eq $false)
    } else {
        $settings = [pscustomobject]@{}
        $integrated = @()
        $alreadyIntegrated = $false
    }
    if ($integrated -notcontains $script:DistroName) {
        $integrated += $script:DistroName
    }
    $settings | Add-Member -NotePropertyName EnableIntegrationWithDefaultWslDistro -NotePropertyValue $true -Force
    $settings | Add-Member -NotePropertyName IntegratedWslDistros -NotePropertyValue @($integrated) -Force
    $settings | Add-Member -NotePropertyName UseWindowsContainers -NotePropertyValue $false -Force
    Write-Utf8NoBom -Path $settingsPath -Content ($settings | ConvertTo-Json -Depth 30)
    if (-not $alreadyIntegrated -and (Get-Process -Name 'Docker Desktop' -ErrorAction SilentlyContinue)) {
        Confirm-SystemChange '需要重启 Docker Desktop 以应用 Ubuntu WSL Integration。是否继续？'
        Get-Process -Name 'Docker Desktop','com.docker.backend','com.docker.build','com.docker.cli' -ErrorAction SilentlyContinue |
            Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 5
    }
}

function Start-DockerDesktop {
    if (-not (Test-Path -LiteralPath $script:DockerDesktopPath)) {
        Stop-QQBridge "找不到 Docker Desktop: $script:DockerDesktopPath"
    }
    $process = Get-Process -Name 'Docker Desktop' -ErrorAction SilentlyContinue
    if (-not $process) {
        Write-QQLog '启动 Docker Desktop；如出现登录、许可或 WSL 提示，请在窗口中完成。'
        Start-Process -FilePath $script:DockerDesktopPath
    }
}

function Ensure-LinuxDockerGroup {
    $safeUser = ([string]$script:LinuxUser) -replace '[^a-z0-9_-]', ''
    if (-not $safeUser) {
        return
    }
    $check = Invoke-WslRaw -User 'root' -Arguments @(
        'bash', '-lc',
        "id -nG '$safeUser' 2>/dev/null | tr ' ' '\n' | grep -qx docker"
    ) -AllowFailure
    if ($check.ExitCode -eq 0) {
        return
    }
    $groupExists = Invoke-WslRaw -User 'root' -Arguments @(
        'bash', '-lc',
        "getent group docker >/dev/null 2>&1"
    ) -AllowFailure
    if ($groupExists.ExitCode -ne 0) {
        return
    }
    Write-QQLog "将 WSL 用户 $safeUser 加入 docker 组"
    Invoke-WslRaw -User 'root' -Arguments @(
        'usermod', '-aG', 'docker', $safeUser
    ) | Out-Null
    & wsl.exe --terminate $script:DistroName | Out-Null
    Start-Sleep -Seconds 2
}

function Wait-DockerEngine {
    param([int]$TimeoutSeconds = 600)
    $started = Get-Date
    while (((Get-Date) - $started).TotalSeconds -lt $TimeoutSeconds) {
        $docker = Get-DockerExe
        if ($docker) {
            $output = & $docker info --format '{{.OSType}}' 2>$null
            if ($LASTEXITCODE -eq 0 -and (($output -join '').Trim().ToLowerInvariant() -eq 'linux')) {
                $wslProbe = Invoke-WslRaw -User $script:LinuxUser -Arguments @('docker', 'info', '--format', '{{.OSType}}') -AllowFailure
                if ($wslProbe.ExitCode -eq 0 -and (($wslProbe.Output -join '').Trim().ToLowerInvariant() -eq 'linux')) {
                    return
                }
                # Docker Desktop 启动后才创建 docker 组；在等待期间持续尝试把用户加入该组。
                Ensure-LinuxDockerGroup
            }
        }
        Start-Sleep -Seconds 5
    }
    Stop-QQBridge 'Docker Desktop Linux Engine 或 WSL 集成在等待时间内未就绪。请在 Docker Desktop 中完成登录/许可，并启用 Ubuntu WSL Integration 后重试。'
}

function Ensure-DockerDesktop {
    if (-not (Test-Path -LiteralPath $script:DockerDesktopPath)) {
        Confirm-SystemChange '需要安装 Docker Desktop。是否继续？'
        $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
        if (-not $winget) {
            Stop-QQBridge '未找到 winget，请先安装 App Installer，或手动安装 Docker Desktop。'
        }
        Write-QQLog '通过 winget 安装 Docker Desktop'
        & winget.exe install --id Docker.DockerDesktop -e --silent --accept-source-agreements --accept-package-agreements
        $wingetCode = $LASTEXITCODE
        if ($wingetCode -eq 3010) {
            Set-RebootPending 'Docker Desktop 安装完成但需要重启'
        }
        if ($wingetCode -ne 0) {
            Stop-QQBridge "Docker Desktop 安装失败，winget 退出码 $wingetCode。"
        }
    }

    Set-DockerWslIntegration
    Start-DockerDesktop
    Ensure-LinuxDockerGroup
    Wait-DockerEngine -TimeoutSeconds 600
    Write-QQLog 'Docker Desktop Linux Engine 已就绪，Ubuntu WSL Integration 可用。'
}

function Test-TcpPortAvailable {
    param([Parameter(Mandatory)][int]$Port)
    $listeners = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    return -not $listeners
}

function Read-Port {
    param(
        [Parameter(Mandatory)][string]$Label,
        [Parameter(Mandatory)][int]$Default
    )
    while ($true) {
        $text = Read-Host "$Label [$Default]"
        if (-not $text) {
            $value = $Default
        } elseif (-not [int]::TryParse($text, [ref]$value) -or $value -lt 1024 -or $value -gt 65535) {
            Write-Host '端口必须是 1024-65535 之间的整数。' -ForegroundColor Yellow
            continue
        }
        if (-not (Test-TcpPortAvailable -Port $value)) {
            $change = Read-Host "端口 $value 已被占用。是否输入其他端口？[Y/n]"
            if (-not $change -or $change.Trim().ToLowerInvariant() -in @('y', 'yes', '是')) {
                continue
            }
            Stop-QQBridge "端口 $value 冲突，安装已停止。"
        }
        return $value
    }
}

function Save-SecureAnswers {
    param([Parameter(Mandatory)][hashtable]$Answers)
    $path = [System.IO.Path]::GetTempFileName()
    Write-Utf8NoBom -Path $path -Content ($Answers | ConvertTo-Json -Depth 10)
    & icacls.exe $path /inheritance:r /grant:r "$($env:USERDOMAIN)\$($env:USERNAME):(R,W,D)" | Out-Null
    return $path
}

function Update-QQBridgeFirewall {
    param(
        [bool]$LocalOnly,
        [int]$MaiBotPort,
        [int]$NapCatPort
    )
    Get-NetFirewallRule -DisplayName 'QQBridge*' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    if ($LocalOnly) {
        Write-QQLog '本机模式：未创建局域网入站规则。'
        return
    }
    New-NetFirewallRule `
        -DisplayName 'QQBridge MaiBot LAN' `
        -Direction Inbound -Action Allow -Protocol TCP -LocalPort $MaiBotPort `
        -Profile Private -RemoteAddress LocalSubnet | Out-Null
    New-NetFirewallRule `
        -DisplayName 'QQBridge NapCat LAN' `
        -Direction Inbound -Action Allow -Protocol TCP -LocalPort $NapCatPort `
        -Profile Private -RemoteAddress LocalSubnet | Out-Null
    Write-QQLog '已创建仅限专用网络和本地子网的防火墙规则。'
}

function Set-DockerAutostart {
    param([switch]$Disable)
    $taskName = 'QQBridge Docker Desktop'
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($Disable) {
        if ($existing) {
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        }
        Write-QQLog '已关闭 QQBridge 的 Docker Desktop 登录自启动任务。'
        return
    }
    if (-not (Test-Path -LiteralPath $script:DockerDesktopPath)) {
        Stop-QQBridge '无法创建自启动任务：Docker Desktop 路径不存在。'
    }
    $action = New-ScheduledTaskAction -Execute $script:DockerDesktopPath
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-QQLog '已创建 Docker Desktop 登录自启动任务。'
}

function Get-QQBridgeContext {
    $state = Read-State
    if (-not $state -or -not $state.install_root -or -not $state.linux_user) {
        Stop-QQBridge '未找到 QQBridge 安装状态。请先运行 install.ps1。'
    }
    return [pscustomobject]@{
        InstallRoot = [string]$state.install_root
        LinuxUser = [string]$state.linux_user
        Distro = if ($state.distro) { [string]$state.distro } else { $script:DistroName }
        DockerDesktop = $script:DockerDesktopPath
    }
}

function Get-InstanceEnvValue {
    param(
        [Parameter(Mandatory)][pscustomobject]$Context,
        [Parameter(Mandatory)][string]$Key
    )
    $instance = "$($Context.InstallRoot)/instances/default"
    $tool = "$($Context.InstallRoot)/current/wsl/env_tool.py"
    $result = Invoke-WslRaw -User 'root' -Arguments @('python3', $tool, '--instance', $instance, '--get', $Key)
    return (($result.Output | Select-Object -First 1) -as [string]).Trim()
}

function Test-PackageIntegrity {
    param([Parameter(Mandatory)][string]$Root)
    $manifestPath = Join-Path $Root 'manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath)) {
        Stop-QQBridge '安装包缺少 manifest.json，拒绝继续。'
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($property in $manifest.files.PSObject.Properties) {
        $relative = $property.Name.Replace('/', [IO.Path]::DirectorySeparatorChar)
        $path = Join-Path $Root $relative
        if (-not (Test-Path -LiteralPath $path)) {
            Stop-QQBridge "安装包文件缺失: $($property.Name)"
        }
        $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        $expected = [string]$property.Value.sha256
        if ($actual -ne $expected) {
            Stop-QQBridge "安装包文件校验失败: $($property.Name)"
        }
    }
    $fileCount = @($manifest.files.PSObject.Properties).Count
    Write-QQLog "安装包完整性校验通过（$fileCount 个文件）。"
}
