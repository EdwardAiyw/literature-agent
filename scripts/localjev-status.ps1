[CmdletBinding()]
param(
    [string]$BaseUrl = "http://127.0.0.1:8080",
    [string]$UpstreamUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"

try {
    $upstreamHealth = Invoke-RestMethod -Uri "$UpstreamUrl/health" -TimeoutSec 5
    $upstreamModels = Invoke-RestMethod -Uri "$UpstreamUrl/v1/models" -TimeoutSec 5
    $health = Invoke-RestMethod -Uri "$BaseUrl/health" -TimeoutSec 5
    try {
        $ready = Invoke-RestMethod -Uri "$BaseUrl/ready" -TimeoutSec 10
    } catch {
        if ($_.ErrorDetails.Message) {
            $ready = $_.ErrorDetails.Message | ConvertFrom-Json
        } else {
            $ready = [pscustomobject]@{ status = "unavailable"; detail = $_.Exception.Message }
        }
    }
    $models = Invoke-RestMethod -Uri "$BaseUrl/v1/models" -TimeoutSec 5
    [pscustomobject]@{
        upstream_url = $UpstreamUrl
        upstream_health = $upstreamHealth.status
        upstream_models = ($upstreamModels.data.id -join ", ")
        base_url = $BaseUrl
        health = $health.status
        ready = $ready.status
        upstream_model = $ready.upstream_model
        detail = $ready.detail
        models = ($models.models.name -join ", ")
    } | Format-List
} catch {
    Write-Error "LocalJev chain status check failed: $($_.Exception.Message)"
}
