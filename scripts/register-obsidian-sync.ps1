[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Config,
    [string]$TaskName = 'Literature Agent Obsidian Sync',
    [ValidateRange(5,1440)][int]$IntervalMinutes = 15,
    [switch]$Unregister
)
$ErrorActionPreference = 'Stop'
if ($Unregister) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    return
}
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot 'backend\.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "Create backend/.venv and install backend first." }
$configPath = (Resolve-Path -LiteralPath $Config).Path
$action = New-ScheduledTaskAction -Execute $python -Argument "-m literature_agent.obsidian --config `"$configPath`"" -WorkingDirectory (Join-Path $projectRoot 'backend')
$repeat = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) -RepetitionDuration (New-TimeSpan -Days 3650)
$login = New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($repeat, $login) -Principal $principal -Settings $settings -Description 'Read sent digests over SSH into an Obsidian vault; does not run searches or send mail.' -Force | Out-Null
Write-Host "Registered '$TaskName': at login and every $IntervalMinutes minutes while logged in."
