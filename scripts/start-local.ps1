[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8001,
    [switch]$BuildFrontend
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot "backend"
$frontendRoot = Join-Path $projectRoot "frontend"
$python = Join-Path $backendRoot ".venv\Scripts\python.exe"
$alembic = Join-Path $backendRoot ".venv\Scripts\alembic.exe"
$frontendIndex = Join-Path $frontendRoot "dist\index.html"
$logRoot = Join-Path $backendRoot "logs"

foreach ($required in @($python, $alembic)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required local runtime file not found: $required"
    }
}

if ($BuildFrontend) {
    Push-Location $frontendRoot
    try {
        & npm run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend production build failed." }
    } finally {
        Pop-Location
    }
}

if (-not (Test-Path -LiteralPath $frontendIndex)) {
    throw "Frontend production build is missing. Run scripts\start-local.ps1 -BuildFrontend once."
}

$listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
if ($listeners.Count -gt 0) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 3
        if ($health.status -eq "ok") {
            Write-Host "Literature Agent is already healthy on port $Port."
            exit 0
        }
    } catch {
        # The listener is not this application; fail below with its owning PID.
    }
    $owners = ($listeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
    throw "Port $Port is already occupied by process(es): $owners"
}

Push-Location $backendRoot
try {
    & $alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "Database migration failed." }

    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $logFile = Join-Path $logRoot ("local-{0}.log" -f (Get-Date -Format "yyyyMMdd"))
    "[$(Get-Date -Format o)] Starting Literature Agent on http://127.0.0.1:$Port" | Add-Content -Encoding UTF8 $logFile
    # Windows PowerShell promotes native stderr (including harmless startup
    # warnings) to a terminating error under ErrorActionPreference=Stop.
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $python -m uvicorn literature_agent.api:app --host 127.0.0.1 --port $Port *>> $logFile
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    exit $exitCode
} finally {
    Pop-Location
}
