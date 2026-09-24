[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ResultPath
)

$ErrorActionPreference = "Stop"
try {
    $result = Enable-WindowsOptionalFeature -Online -FeatureName Containers-DisposableClientVM -All -NoRestart
    $lines = @(
        "FeatureName=Containers-DisposableClientVM"
        "State=$($result.State)"
        "RestartNeeded=$($result.RestartNeeded)"
        "Completed=$(Get-Date -Format o)"
    )
    [System.IO.File]::WriteAllLines($ResultPath, $lines, [System.Text.UTF8Encoding]::new($false))
    exit 0
} catch {
    [System.IO.File]::WriteAllText($ResultPath, "Error=$($_.Exception.Message)", [System.Text.UTF8Encoding]::new($false))
    exit 1
}
