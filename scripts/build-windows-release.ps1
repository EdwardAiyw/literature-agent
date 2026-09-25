[CmdletBinding()]
param(
    [string]$Version = "0.3.0-rc.3",
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot "backend"
$frontendRoot = Join-Path $projectRoot "frontend"
$releaseRoot = Join-Path $projectRoot "release"
$python = Join-Path $backendRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Backend virtual environment not found. Create backend/.venv first."
}

Push-Location $frontendRoot
try {
    & npm ci
    if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." }
    & npm run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend production build failed." }
} finally { Pop-Location }

& $python -m pip install -e "$backendRoot[release]"
if ($LASTEXITCODE -ne 0) { throw "Release dependencies failed to install." }

New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
& $python -m PyInstaller --noconfirm --clean --distpath (Join-Path $releaseRoot "stage") --workpath (Join-Path $releaseRoot "build") (Join-Path $backendRoot "literature-agent.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

$packagedRoot = Join-Path $releaseRoot "stage\LiteratureAgent"
Copy-Item -LiteralPath $PSScriptRoot -Destination (Join-Path $packagedRoot "scripts") -Recurse -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "LICENSE") -Destination $packagedRoot -Force

if (-not $SkipInstaller) {
    $iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
    if (-not $iscc) {
        $iscc = @(
            (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
            (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
            (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
        ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    }
    if (-not $iscc) { throw "Inno Setup 6 is required to build the installer." }
    & $iscc "/DAppVersion=$Version" "/DProjectRoot=$projectRoot" (Join-Path $projectRoot "packaging\literature-agent.iss")
    if ($LASTEXITCODE -ne 0) { throw "Installer build failed." }

    $installer = Join-Path $releaseRoot "Literature-Agent-$Version-Windows-x64.exe"
    $checksum = Get-FileHash -LiteralPath $installer -Algorithm SHA256
    $checksumLine = "$($checksum.Hash.ToLowerInvariant())  $($checksum.Path | Split-Path -Leaf)`n"
    [System.IO.File]::WriteAllText(
        (Join-Path $releaseRoot "SHA256SUMS.txt"),
        $checksumLine,
        [System.Text.UTF8Encoding]::new($false)
    )
}

Write-Host "Windows release artifacts are in $releaseRoot"
