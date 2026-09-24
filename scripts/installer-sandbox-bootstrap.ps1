[CmdletBinding()]
param(
    [string]$Version = "0.3.0"
)

$ErrorActionPreference = "Stop"
$resultFile = "C:\LiteratureAgentResults\AUTOMATED_RESULTS.md"
$installer = "C:\LiteratureAgentRelease\Literature-Agent-$Version-Windows-x64.exe"
$checksumFile = "C:\LiteratureAgentRelease\SHA256SUMS.txt"
$installRoot = Join-Path $env:LOCALAPPDATA "Programs\Literature Agent"
$app = Join-Path $installRoot "LiteratureAgent.exe"
$dataRoot = "C:\LiteratureAgentData"
$bootstrap = "C:\LiteratureAgentBootstrap.json"
$baseUrl = "http://127.0.0.1:8001"

function Add-Result([string]$name, [bool]$passed, [string]$detail) {
    $status = if ($passed) { "PASS" } else { "FAIL" }
    Add-Content -LiteralPath $resultFile -Encoding UTF8 -Value "| $name | $status | $detail |"
}

Set-Content -LiteralPath $resultFile -Encoding UTF8 -Value @(
    "# Literature Agent $Version Windows Sandbox Results"
    ""
    "Started: $(Get-Date -Format o)"
    ""
    "| Check | Result | Detail |"
    "| --- | --- | --- |"
)

try {
    $expected = ((Get-Content -LiteralPath $checksumFile -Raw).Trim() -split "\s+")[0]
    $actual = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
    Add-Result "SHA-256" ($actual -eq $expected.ToLowerInvariant()) $actual

    $process = Start-Process -FilePath $installer -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-" -Wait -PassThru
    Add-Result "Install" ($process.ExitCode -eq 0 -and (Test-Path -LiteralPath $app)) "exit=$($process.ExitCode)"

    $env:LITERATURE_AGENT_DATA_DIR = $dataRoot
    $env:LITERATURE_AGENT_BOOTSTRAP = $bootstrap
    Start-Process -FilePath $app -ArgumentList "--port", "8001", "--no-browser" | Out-Null
    $healthy = $false
    for ($attempt = 0; $attempt -lt 120; $attempt++) {
        try {
            $health = Invoke-RestMethod -Uri "$baseUrl/api/health" -TimeoutSec 2
            if ($health.status -eq "ok") { $healthy = $true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    Add-Result "First launch" $healthy "health=$($health.status); data=$dataRoot"

    if ($healthy) {
        $duplicate = Start-Process -FilePath $app -ArgumentList "--port", "8001", "--no-browser" -Wait -PassThru
        Add-Result "Duplicate launch" ($duplicate.ExitCode -eq 0) "exit=$($duplicate.ExitCode)"
        $page = Invoke-WebRequest -Uri $baseUrl -UseBasicParsing
        Add-Result "Bundled frontend" ($page.StatusCode -eq 200 -and $page.Content -match '<div id="root">') "HTTP $($page.StatusCode)"
    }
} catch {
    Add-Result "Bootstrap exception" $false $_.Exception.Message.Replace("|", "/")
}

Add-Content -LiteralPath $resultFile -Encoding UTF8 -Value "`nBootstrap finished: $(Get-Date -Format o)"
$desktop = [Environment]::GetFolderPath("Desktop")
$finalizer = Join-Path $desktop "Finish Literature Agent Test.cmd"
[System.IO.File]::WriteAllText(
    $finalizer,
    "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\LiteratureAgentScripts\installer-sandbox-finalize.ps1 -Version $Version`r`npause`r`n",
    [System.Text.Encoding]::ASCII
)
Start-Process -FilePath "notepad.exe" -ArgumentList "C:\LiteratureAgentResults\CHECKLIST.md"
Start-Process -FilePath "msedge.exe" -ArgumentList $baseUrl
