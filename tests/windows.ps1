[CmdletBinding()]
param([string]$Repo, [switch]$WithWsl)
if (-not $Repo) { $Repo = Split-Path -Parent $PSScriptRoot }
$ErrorActionPreference = 'Stop'
. (Join-Path $Repo 'qqbridge-lib.ps1')
function Check($Condition, $Name) { if (-not $Condition) { throw "FAIL $Name" }; Write-Host "PASS $Name" }
foreach ($file in Get-ChildItem $Repo -Filter *.ps1) {
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$null, [ref]$errors)
    Check ($errors.Count -eq 0) "parse $($file.Name)"
    $bytes = [IO.File]::ReadAllBytes($file.FullName)
    Check ($bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191) "BOM $($file.Name)"
}
foreach ($valid in @('~/qqbridge', '/srv/qqbridge')) { Assert-InstallRoot $valid }
foreach ($invalid in @('/', '~', '~/../etc', '/mnt/d/qq', '/etc/foo', "/srv/a'b", 'D:\QQ')) {
    $rejected = $false
    try { Assert-InstallRoot $invalid } catch { $rejected = $true }
    Check $rejected "reject root $invalid"
}
Check (Test-ModelBaseUrl 'https://api.deepseek.com/v1') 'valid model URL'
foreach ($invalid in @('sk-dummy', 'https://', 'https://user:pass@example.org/v1', 'https://example.org/v1?key=dummy')) {
    Check (-not (Test-ModelBaseUrl $invalid)) 'reject invalid model URL'
}
$p = Save-SecureAnswers @{ llm_api_key = 'dummy-test-value' }
try {
    Check (([IO.File]::ReadAllBytes($p))[0] -eq 123) 'answers no BOM'
    $acl = Get-Acl $p
    Check $acl.AreAccessRulesProtected 'answers ACL inheritance disabled'
    Check ($acl.Access.Count -eq 1) 'answers ACL single principal'
} finally { Remove-Item $p -Force }
if ($WithWsl) {
    $code = 'import json,sys; print(json.dumps(sys.argv[1:],ensure_ascii=False)); print("progress",file=sys.stderr)'
    $result = Invoke-WslRaw -User 'root' -Arguments @('python3', '-c', $code, 'with space', 'say "hello"', '中文', 'dollar$literal')
    Check ($result.ExitCode -eq 0) 'native stdout exit'
    $decoded = ($result.Output -join "`n") | ConvertFrom-Json
    Check ($decoded.Count -eq 4 -and $decoded[0] -eq 'with space' -and $decoded[1] -eq 'say "hello"' -and $decoded[2] -eq '中文' -and $decoded[3] -eq 'dollar$literal') 'native exact argv and Unicode'
    Check ($result.StdErr -eq 'progress') 'native stderr isolated'
    $result = Invoke-WslRaw -User 'root' -Arguments @('bash', '-c', 'echo progress >&2; exit 7') -AllowFailure
    Check ($result.ExitCode -eq 7) 'native failure exit preserved'
    Check ($ErrorActionPreference -eq 'Stop') 'error preference preserved'
    $result = Invoke-WslRaw -User 'root' -Arguments @('true')
    Check ($result.Output.Count -eq 0 -and $result.StdErr -eq '') 'empty streams'
}
# Installer flow uses dummy credentials and isolated filesystem fixtures only.
$fixture = Join-Path ([IO.Path]::GetTempPath()) ('qqbridge-windows-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $fixture | Out-Null
Copy-Item (Join-Path $Repo 'install.ps1') (Join-Path $fixture 'install.ps1')
[IO.File]::WriteAllText((Join-Path $fixture 'VERSION'), '1.2.0')
$mock = @'
$script:PackageRoot = $PSScriptRoot
$script:DistroName = 'Ubuntu'
$script:DockerDesktopPath = 'dummy'
function Test-IsAdministrator { $true }
function Assert-Windows11 {}
function Assert-Virtualization {}
function Test-PackageIntegrity {}
function Read-State { $global:TestState }
function Ensure-WslUbuntu {}
function Ensure-LinuxUser { [pscustomobject]@{ User='fixture'; Home='/home/fixture' } }
function Ensure-DockerDesktop {}
function Invoke-WslRaw { param($User,$Arguments,[switch]$AllowFailure)
 if ($Arguments[0] -eq 'test') { return [pscustomobject]@{ExitCode=1;Output=@()} }
 return [pscustomobject]@{ExitCode=0;Output=@('1000')}
}
function Test-TcpPortAvailable { $true }
function Read-LocalSecret { $global:SecretPrompts++; return 'dummy-test-value' }
function Save-SecureAnswers { param($Answers) $global:SavedAnswers=$Answers.Clone(); [IO.Path]::GetTempFileName() }
function Write-State { param($State) $global:TestState=$State }
function ConvertTo-WslPath { '/fixture-package' }
function Invoke-WslBash { param($User,$ScriptPath,$ScriptArguments)
 $global:ShellArguments=$ScriptArguments
 if ($global:SimulateFailure) { throw 'fixture deployment failed' }
 [pscustomobject]@{ExitCode=0;Output=@()}
}
function Update-QQBridgeFirewall { param($LocalOnly,$MaiBotPort,$NapCatPort) $global:FirewallLocal=$LocalOnly }
function Set-DockerAutostart { param([switch]$Disable) $global:AutostartDisabled=[bool]$Disable }
function Write-QQLog { param($Message) Write-Host $Message }
function Start-Process {}
function Read-Host { throw 'Unexpected nonsecret prompt in configured deployment' }
'@
[IO.File]::WriteAllText((Join-Path $fixture 'qqbridge-lib.ps1'), $mock, (New-Object Text.UTF8Encoding($true)))
$config = Join-Path $fixture 'config.json'
[IO.File]::WriteAllText($config, '{"llm_base_url":"https://api.deepseek.com/v1","llm_model":"dummy-model","llm_client_type":"openai"}')
$global:TestState = $null
$global:SecretPrompts = 0
$global:SimulateFailure = $true
$failed = $false
try { & (Join-Path $fixture 'install.ps1') -ConfigFile $config -Yes -NoBrowser } catch { $failed = $true }
Check $failed 'interrupted install reported'
Check ($global:TestState.phase -eq 'installing') 'context saved before deployment'
Check ($global:SavedAnswers.maibot_bind -eq '127.0.0.1' -and $global:SavedAnswers.restart_policy -eq 'unless-stopped') 'friend defaults local and autostart'
Check ($global:SecretPrompts -eq 1) 'only local secret prompt'
$global:SimulateFailure = $false
& (Join-Path $fixture 'install.ps1') -Resume -NoBrowser
Check ($global:TestState.phase -eq 'installed') 'resume completes state'
Check ($global:ShellArguments -contains '--resume') 'resume flag forwarded'
Check ($global:SecretPrompts -eq 1) 'resume does not collect secret again'
Check ($global:FirewallLocal -and -not $global:AutostartDisabled) 'resume preserves preferences'
$blocked = $false
try { & (Join-Path $fixture 'install.ps1') -ConfigFile $config } catch { $blocked = $true }
Check $blocked 'existing installed instance protected'
Write-Host "ALL WINDOWS CHECKS PASSED; isolated fixture retained at $fixture"
