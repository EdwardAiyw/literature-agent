[CmdletBinding()]
param(
    [string]$TaskName = "Literature Agent Daily",
    [ValidateRange(5, 1440)]
    [int]$IntervalMinutes = 15,
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"

if ($Unregister) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -ne $existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed scheduled task: $TaskName"
    } else {
        Write-Host "Scheduled task does not exist: $TaskName"
    }
    return
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot "backend"
$python = Join-Path $backendRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Backend virtual environment not found at $python. Create it and install the project first."
}

$action = New-ScheduledTaskAction `
    -Execute $python `
    -Argument "-m literature_agent.daily --run-due" `
    -WorkingDirectory $backendRoot
$firstRun = (Get-Date).AddMinutes(1)
$trigger = New-ScheduledTaskTrigger `
    -Once `
    -At $firstRun `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Runs due Literature Agent subscriptions in each subscription's configured timezone." `
    -Force | Out-Null

Write-Host "Registered '$TaskName'. It checks due subscriptions every $IntervalMinutes minute(s)."
