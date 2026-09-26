[CmdletBinding()]
param(
    [string]$LocalJevRoot = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "localjev"),
    [switch]$Stop
)

$ErrorActionPreference = "Stop"
$bun = Join-Path $env:USERPROFILE ".bun\bin\bun.exe"
$pidFile = Join-Path $LocalJevRoot ".localjev.pid"
$logFile = Join-Path $LocalJevRoot "localjev.log"
$errorLogFile = Join-Path $LocalJevRoot "localjev-error.log"

if ($Stop) {
    $processIds = @()
    if (Test-Path -LiteralPath $pidFile) {
        $processIds += [int](Get-Content -Raw -LiteralPath $pidFile)
    }
    $processIds += @(Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
    $processIds = @($processIds | Sort-Object -Unique)
    if ($processIds.Count -gt 0) {
        Stop-Process -Id $processIds -ErrorAction SilentlyContinue
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            if (-not (Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue)) {
                break
            }
            Start-Sleep -Milliseconds 200
        }
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped LocalJev process(es): $($processIds -join ', ')."
    } else {
        Write-Host "LocalJev is not running."
    }
    exit 0
}

foreach ($required in @($bun, (Join-Path $LocalJevRoot "package.json"), (Join-Path $LocalJevRoot ".env"))) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required LocalJev file not found: $required"
    }
}

$listener = @(Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue)
if ($listener.Count -gt 0) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8080/health" -TimeoutSec 2
    } catch {
        throw "Port 8080 is occupied by PID $($listener[0].OwningProcess), but it is not a healthy LocalJev service."
    }
    if ($health.status -eq "ok") {
        Write-Host "LocalJev port 8080 is already listening (PID $($listener[0].OwningProcess))."
        exit 0
    }
    throw "Port 8080 is occupied by PID $($listener[0].OwningProcess), but it is not a healthy LocalJev service."
}

$process = Start-Process -FilePath $bun -ArgumentList "run", "start" -WorkingDirectory $LocalJevRoot `
    -RedirectStandardOutput $logFile -RedirectStandardError $errorLogFile -WindowStyle Hidden -PassThru
Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ASCII

for ($attempt = 0; $attempt -lt 20; $attempt++) {
    Start-Sleep -Milliseconds 250
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8080/health" -TimeoutSec 2
        if ($health.status -eq "ok") {
            $listenerPid = Get-NetTCPConnection -LocalPort 8080 -State Listen | Select-Object -ExpandProperty OwningProcess -First 1
            Set-Content -LiteralPath $pidFile -Value $listenerPid -Encoding ASCII
            Write-Host "LocalJev is running on http://127.0.0.1:8080 (PID $listenerPid)."
            exit 0
        }
    } catch {
        # Keep waiting until startup timeout.
    }
}

throw "LocalJev did not become healthy. Review $logFile and $errorLogFile"
