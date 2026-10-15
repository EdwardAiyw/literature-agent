[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-zA-Z0-9][a-zA-Z0-9_.@-]*$')]
    [string]$Target,
    [ValidateRange(1, 65535)][int]$SshPort = 22,
    [ValidateRange(1, 65535)][int]$LocalPort = 18001,
    [ValidateRange(1, 65535)][int]$RemotePort = 18081,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$url = "http://127.0.0.1:$LocalPort"
function Test-ServerConnection {
    try {
        $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 2
        $settings = Invoke-RestMethod "$url/api/settings" -TimeoutSec 2
        return ($health.status -eq 'ok' -and $settings.server_mode -eq $true)
    } catch { return $false }
}

if (-not (Test-ServerConnection)) {
    if (Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $LocalPort is occupied by another service. Choose another -LocalPort."
    }
    $ssh = (Get-Command ssh.exe -ErrorAction Stop).Source
    $tunnel = Start-Process -FilePath $ssh -WindowStyle Hidden -PassThru -ArgumentList @(
        '-N', '-T', '-p', $SshPort, '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'ConnectTimeout=8', '-o', 'ExitOnForwardFailure=yes',
        '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=3',
        '-L', "127.0.0.1:${LocalPort}:127.0.0.1:${RemotePort}", $Target
    )
    $connected = $false
    for ($attempt = 0; $attempt -lt 15; $attempt++) {
        if (Test-ServerConnection) { $connected = $true; break }
        if ($tunnel.HasExited) { break }
        Start-Sleep -Seconds 1
    }
    if (-not $connected) {
        if (-not $tunnel.HasExited) { Stop-Process -Id $tunnel.Id }
        throw 'Server connection failed. Check SSH key access, the trusted host key and server health.'
    }
}
Write-Host "Literature Agent server: $url"
if (-not $NoBrowser) { Start-Process $url }
