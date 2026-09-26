[CmdletBinding()]
param([switch]$Stop)

$ErrorActionPreference = "Stop"

if ($Stop) {
    & (Join-Path $PSScriptRoot "start-localjev.ps1") -Stop
    & (Join-Path $PSScriptRoot "start-localjev-upstream.ps1") -Stop
    exit 0
}

& (Join-Path $PSScriptRoot "start-localjev-upstream.ps1")
& (Join-Path $PSScriptRoot "start-localjev.ps1")
& (Join-Path $PSScriptRoot "localjev-status.ps1")
