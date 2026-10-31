[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'qqbridge-lib.ps1')
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
try {
    $context = Get-QQBridgeContext
    $state = Read-State
    $napToken = Get-InstanceEnvValue -Context $context -Key 'WEBUI_TOKEN'
    $result = Invoke-WslRaw -User 'root' -Arguments @('cat', "$($context.InstallRoot)/instances/default/data/webui.json")
    $maiToken = [string](($result.Output -join "`n" | ConvertFrom-Json).access_token)
    if (-not $napToken -or -not $maiToken) { throw '凭据尚未就绪，请启动容器后重试。' }
    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'QQBridge 本机登录凭据（请勿截图外传）'
    $form.Size = New-Object System.Drawing.Size(720, 270)
    $form.StartPosition = 'CenterScreen'
    $form.FormBorderStyle = 'FixedDialog'
    $form.MaximizeBox = $false
    $index = 0
    foreach ($entry in @(@('NapCat', [int]$state.napcat_port, $napToken), @('MaiBot', [int]$state.maibot_port, $maiToken))) {
        $y = 18 + $index * 85
        $label = New-Object System.Windows.Forms.Label
        $label.Text = "$($entry[0])  http://localhost:$($entry[1])"
        $label.SetBounds(16, $y, 660, 24)
        $box = New-Object System.Windows.Forms.TextBox
        $box.Text = [string]$entry[2]
        $box.ReadOnly = $true
        $box.SetBounds(16, ($y + 27), 660, 26)
        $form.Controls.AddRange(@($label, $box))
        $index++
    }
    $note = New-Object System.Windows.Forms.Label
    $note.Text = '点击 Token 后 Ctrl+A / Ctrl+C 复制；NapCat 登录后扫码。仅在本机显示，不打印到终端。'
    $note.SetBounds(16, 194, 670, 36)
    $form.Controls.Add($note)
    [void]$form.ShowDialog()
} catch {
    [void][System.Windows.Forms.MessageBox]::Show('无法读取本机登录凭据。请确认 WSL、容器已启动，且安装状态存在。', 'QQBridge')
    exit 1
} finally {
    if ($form) { $form.Dispose() }
    $napToken = $null
    $maiToken = $null
}
