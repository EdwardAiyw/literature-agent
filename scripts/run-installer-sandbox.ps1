[CmdletBinding()]
param(
    [string]$Version = "0.3.0"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $projectRoot "release"
$installer = Join-Path $releaseRoot "Literature-Agent-$Version-Windows-x64.exe"
$checksum = Join-Path $releaseRoot "SHA256SUMS.txt"
$sandboxExecutable = Join-Path $env:WINDIR "System32\WindowsSandbox.exe"

if (-not (Test-Path -LiteralPath $installer)) { throw "Installer not found: $installer" }
if (-not (Test-Path -LiteralPath $checksum)) { throw "Checksum file not found: $checksum" }
if (-not (Test-Path -LiteralPath $sandboxExecutable)) {
    throw "Windows Sandbox is unavailable. Enable Containers-DisposableClientVM and restart Windows first."
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$resultRoot = Join-Path $projectRoot "test-results\installer-sandbox-$stamp"
New-Item -ItemType Directory -Path $resultRoot -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot "docs\INSTALLER_SANDBOX_TEST.md") -Destination (Join-Path $resultRoot "CHECKLIST.md")
Set-Content -LiteralPath (Join-Path $resultRoot "MANUAL_CONFIRMATION.txt") -Encoding UTF8 -Value @(
    "SMTP test email received: NO"
    "Five-paper digest received: NO"
    "Final five papers use at least two sources: NO"
    "Onboarding completed in the page: NO"
    "Notes:"
)

function Escape-Xml([string]$value) {
    return [System.Security.SecurityElement]::Escape($value)
}

$configuration = @"
<Configuration>
  <VGpu>Disable</VGpu>
  <Networking>Enable</Networking>
  <ClipboardRedirection>Enable</ClipboardRedirection>
  <MemoryInMB>4096</MemoryInMB>
  <MappedFolders>
    <MappedFolder>
      <HostFolder>$(Escape-Xml $releaseRoot)</HostFolder>
      <SandboxFolder>C:\LiteratureAgentRelease</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>$(Escape-Xml $PSScriptRoot)</HostFolder>
      <SandboxFolder>C:\LiteratureAgentScripts</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>$(Escape-Xml $resultRoot)</HostFolder>
      <SandboxFolder>C:\LiteratureAgentResults</SandboxFolder>
      <ReadOnly>false</ReadOnly>
    </MappedFolder>
  </MappedFolders>
  <LogonCommand>
    <Command>powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\LiteratureAgentScripts\installer-sandbox-bootstrap.ps1 -Version $(Escape-Xml $Version)</Command>
  </LogonCommand>
</Configuration>
"@

$wsbPath = Join-Path $resultRoot "Literature-Agent-$Version.wsb"
[System.IO.File]::WriteAllText($wsbPath, $configuration, [System.Text.UTF8Encoding]::new($false))
Write-Host "Sandbox results: $resultRoot"
Write-Host "Close Windows Sandbox only after running the finalizer described in CHECKLIST.md."
Start-Process -FilePath $sandboxExecutable -ArgumentList "`"$wsbPath`""
