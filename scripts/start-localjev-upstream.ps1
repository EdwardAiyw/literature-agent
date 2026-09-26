[CmdletBinding()]
param(
    [string]$RuntimeRoot = "D:\localjev-runtime",
    [string]$ModelPath = "",
    [switch]$Stop
)

$ErrorActionPreference = "Stop"
$serverScript = Join-Path $PSScriptRoot "localjev-upstream-server.mjs"
$pidFile = Join-Path $RuntimeRoot "upstream.pid"
$logFile = Join-Path $RuntimeRoot "logs\upstream.log"
$errorLogFile = Join-Path $RuntimeRoot "logs\upstream-error.log"

if ($Stop) {
    $processIds = @()
    if (Test-Path -LiteralPath $pidFile) {
        $processIds += [int](Get-Content -Raw -LiteralPath $pidFile)
    }
    $processIds += @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
    $processIds = @($processIds | Sort-Object -Unique)
    if ($processIds.Count -gt 0) {
        Stop-Process -Id $processIds -ErrorAction SilentlyContinue
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            if (-not (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)) {
                break
            }
            Start-Sleep -Milliseconds 200
        }
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped LocalJev upstream process(es): $($processIds -join ', ')."
    } else {
        Write-Host "LocalJev upstream is not running."
    }
    exit 0
}

$bun = Join-Path $env:USERPROFILE ".bun\bin\bun.exe"
if (-not $ModelPath) {
    $ModelPath = Join-Path $RuntimeRoot "models\qwen2.5-3b-instruct-q4_k_m.gguf"
}
$required = @(
    $bun,
    $serverScript,
    $ModelPath,
    (Join-Path $RuntimeRoot "node_modules\node-llama-cpp\dist\index.js"),
    (Join-Path $RuntimeRoot "node_modules\@node-llama-cpp\win-x64-vulkan\package.json")
)
foreach ($item in $required) {
    if (-not (Test-Path -LiteralPath $item)) {
        throw "Required LocalJev upstream file not found: $item"
    }
}

$listener = @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)
if ($listener.Count -gt 0) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2
    } catch {
        throw "Port 8000 is occupied by PID $($listener[0].OwningProcess), but it is not a healthy LocalJev upstream."
    }
    if ($health.status -eq "ok") {
        Write-Host "LocalJev upstream port 8000 is already listening (PID $($listener[0].OwningProcess))."
        exit 0
    }
    throw "Port 8000 is occupied by PID $($listener[0].OwningProcess), but it is not a healthy LocalJev upstream."
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $logFile) | Out-Null
$env:LOCALJEV_RUNTIME_ROOT = $RuntimeRoot
$env:LOCALJEV_MODEL_PATH = $ModelPath
$env:LOCALJEV_MODEL_NAME = "qwen2.5-3b-instruct-q4_k_m"
$vulkanBin = Join-Path $RuntimeRoot "node_modules\@node-llama-cpp\win-x64-vulkan\bins\win-x64-vulkan"
$env:PATH = "$vulkanBin;$env:PATH"
$process = Start-Process -FilePath $bun -ArgumentList $serverScript -WorkingDirectory $RuntimeRoot `
    -RedirectStandardOutput $logFile -RedirectStandardError $errorLogFile -WindowStyle Hidden -PassThru
Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ASCII

for ($attempt = 0; $attempt -lt 180; $attempt++) {
    Start-Sleep -Seconds 1
    if ($process.HasExited) {
        throw "LocalJev upstream exited during startup. Review $logFile and $errorLogFile"
    }
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2
        if ($health.status -eq "ok") {
            $listenerPid = Get-NetTCPConnection -LocalPort 8000 -State Listen |
                Select-Object -ExpandProperty OwningProcess -First 1
            Set-Content -LiteralPath $pidFile -Value $listenerPid -Encoding ASCII
            Write-Host "LocalJev upstream is running on http://127.0.0.1:8000 (PID $listenerPid)."
            exit 0
        }
    } catch {
        # Model loading can take over a minute on first launch.
    }
}

throw "LocalJev upstream did not become healthy. Review $logFile and $errorLogFile"
