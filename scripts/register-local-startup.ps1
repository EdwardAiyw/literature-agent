[CmdletBinding()]
param(
    [string]$TaskName = "Literature Agent Local",
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
$launcher = Join-Path $PSScriptRoot "start-local.ps1"
$packagedApp = Join-Path $projectRoot "LiteratureAgent.exe"
$frontendIndex = Join-Path $projectRoot "frontend\dist\index.html"

if (-not (Test-Path -LiteralPath $packagedApp) -and -not (Test-Path -LiteralPath $launcher)) {
    throw "Local launcher not found: $launcher"
}
if (-not (Test-Path -LiteralPath $packagedApp) -and -not (Test-Path -LiteralPath $frontendIndex)) {
    throw "Frontend production build is missing. Run scripts\start-local.ps1 -BuildFrontend before registration."
}

if (Test-Path -LiteralPath $packagedApp) {
    $action = New-ScheduledTaskAction -Execute $packagedApp -Argument "--no-browser" -WorkingDirectory $projectRoot
} else {
    $powerShell = (Get-Command powershell.exe).Source
    $arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$launcher`""
    $action = New-ScheduledTaskAction -Execute $powerShell -Argument $arguments -WorkingDirectory $projectRoot
}
$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Starts the local Literature Agent GUI and API when the current user signs in." `
    -Force | Out-Null

Write-Host "Registered '$TaskName' for $userId logon."
