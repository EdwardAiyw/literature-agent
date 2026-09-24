[CmdletBinding()]
param(
    [string]$Version = "0.3.0"
)

$ErrorActionPreference = "Continue"
$resultFile = "C:\LiteratureAgentResults\AUTOMATED_RESULTS.md"
$confirmationFile = "C:\LiteratureAgentResults\MANUAL_CONFIRMATION.txt"
$installRoot = Join-Path $env:LOCALAPPDATA "Programs\Literature Agent"
$uninstaller = Join-Path $installRoot "unins000.exe"
$dataRoot = "C:\LiteratureAgentData"
$baseUrl = "http://127.0.0.1:8001"

function Add-Result([string]$name, [bool]$passed, [string]$detail) {
    $status = if ($passed) { "PASS" } else { "FAIL" }
    Add-Content -LiteralPath $resultFile -Encoding UTF8 -Value "| $name | $status | $detail |"
}

try {
    $tasks = @(Invoke-RestMethod -Uri "$baseUrl/api/tasks")
    $qualifyingRun = $null
    foreach ($task in $tasks) {
        $runs = @(Invoke-RestMethod -Uri "$baseUrl/api/tasks/$($task.id)/runs?limit=20")
        foreach ($run in $runs) {
            if ($run.status -ne "completed") { continue }
            $papers = @(Invoke-RestMethod -Uri "$baseUrl/api/runs/$($run.id)/papers")
            $sourceCount = @($papers | ForEach-Object source | Sort-Object -Unique).Count
            if ($papers.Count -ge 5 -and $sourceCount -ge 2) {
                $qualifyingRun = "$($run.id): $($papers.Count) papers, $sourceCount sources"
                break
            }
        }
        if ($qualifyingRun) { break }
    }
    Add-Result "Five papers from two sources" ([bool]$qualifyingRun) $(if ($qualifyingRun) { $qualifyingRun } else { "not found" })

    $scheduler = Invoke-RestMethod -Uri "$baseUrl/api/scheduler"
    Add-Result "Windows scheduled tasks" (@($scheduler.tasks).Count -eq 2) "$(@($scheduler.tasks).Count) tasks"

    $backup = Invoke-RestMethod -Uri "$baseUrl/api/backups" -Method Post -ContentType "application/json" -Body "{}"
    $backupExists = Test-Path -LiteralPath $backup.path
    Add-Result "Backup" $backupExists $(if ($backupExists) { Split-Path $backup.path -Leaf } else { "missing" })
    if ($backupExists) {
        $restoreBody = @{ path = $backup.path } | ConvertTo-Json
        $restore = Invoke-RestMethod -Uri "$baseUrl/api/backups/restore" -Method Post -ContentType "application/json" -Body $restoreBody
        Add-Result "Restore" ($restore.status -eq "restored") $restore.status
    }
} catch {
    Add-Result "Runtime final checks" $false $_.Exception.Message.Replace("|", "/")
}

$manual = Get-Content -LiteralPath $confirmationFile -Raw -ErrorAction SilentlyContinue
Add-Result "Manual confirmations completed" ($manual -and $manual -notmatch ": NO") "See MANUAL_CONFIRMATION.txt"

Get-Process LiteratureAgent -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
if (Test-Path -LiteralPath $uninstaller) {
    $uninstall = Start-Process -FilePath $uninstaller -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait -PassThru
    Start-Sleep -Seconds 2
    Add-Result "Uninstall" ($uninstall.ExitCode -eq 0 -and -not (Test-Path -LiteralPath (Join-Path $installRoot "LiteratureAgent.exe"))) "exit=$($uninstall.ExitCode)"
} else {
    Add-Result "Uninstall" $false "uninstaller missing"
}

$scheduled = @(Get-ScheduledTask -TaskName "Literature Agent *" -ErrorAction SilentlyContinue)
Add-Result "Scheduled tasks removed" ($scheduled.Count -eq 0) "$($scheduled.Count) remaining"
Add-Result "User data retained" (Test-Path -LiteralPath $dataRoot) $dataRoot
Add-Content -LiteralPath $resultFile -Encoding UTF8 -Value "`nFinalized: $(Get-Date -Format o)"
Start-Process -FilePath "notepad.exe" -ArgumentList $resultFile
