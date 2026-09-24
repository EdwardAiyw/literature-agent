[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[^@\s]+@[^@\s]+\.[^@\s]+$')]
    [string]$Recipient,
    [string]$BaseUrl = "http://127.0.0.1:8001",
    [string]$SubscriptionId = "",
    [ValidateRange(60, 7200)]
    [int]$TimeoutSeconds = 1800,
    [switch]$ValidateOnly,
    [switch]$TestSend,
    [switch]$RunNow
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot "backend\.env"

function Get-DotEnvValues {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Persistent backend configuration is missing: $Path"
    }
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) { continue }
        $key, $value = $trimmed.Split("=", 2)
        $values[$key.Trim()] = $value.Trim().Trim('"').Trim("'")
    }
    return $values
}

$persistent = Get-DotEnvValues -Path $envFile
$requiredPersistent = @("LLM_API_KEY", "LLM_MODEL", "SMTP_HOST", "SMTP_FROM")
$missingPersistent = @($requiredPersistent | Where-Object { -not $persistent.ContainsKey($_) -or -not $persistent[$_] })
$persistentLive = [string]$persistent["LITERATURE_AGENT_LIVE"]
if ($persistentLive.ToLowerInvariant() -notin @("1", "true", "yes")) {
    $missingPersistent += "LITERATURE_AGENT_LIVE=true"
}
if ($persistent["SMTP_USERNAME"] -and -not $persistent["SMTP_PASSWORD"]) {
    $missingPersistent += "SMTP_PASSWORD"
}
if ($missingPersistent.Count -gt 0) {
    throw "Complete backend/.env before production release. Missing or disabled: $($missingPersistent -join ', ')"
}

$api = $BaseUrl.TrimEnd('/') + "/api"
$runtime = Invoke-RestMethod -Uri "$api/settings"
if (-not $runtime.live -or -not $runtime.llm_configured -or -not $runtime.smtp_configured) {
    throw "Live retrieval, LLM, and SMTP must be configured before creating the production subscription."
}
if ($runtime.jev_enabled -and $runtime.jev_configured) {
    $jevMode = if ($runtime.jev_shadow_mode) { "Shadow" } else { "Active" }
    Write-Host "Jev is configured in $jevMode mode."
} else {
    Write-Host "Jev is disabled or unconfigured; the subscription will use the existing LLM/rule decision path."
}
if ($ValidateOnly) {
    Write-Host "Production configuration is ready. No subscription or delivery was created."
    return
}

$subscriptionName = "Agentic RAG " + [string][char]0x65E5 + [string][char]0x62A5
$payload = @{
    name = $subscriptionName
    topic = "agentic retrieval augmented generation evaluation"
    research_questions = @("How are agentic RAG systems evaluated for retrieval quality, reasoning reliability, and end-to-end task performance?")
    language = "bilingual"
    output_language = "zh"
    date_from = ""
    date_to = ""
    target_count = 5
    sources = @("semantic_scholar", "openalex", "crossref", "arxiv", "pubmed")
    recipient = $Recipient
    schedule_time = "08:00"
    timezone = "Asia/Hong_Kong"
    evidence_review = $true
    prompt_overrides = @{}
    enabled = $true
}

$existing = if ($SubscriptionId) {
    Invoke-RestMethod -Uri "$api/subscriptions/$SubscriptionId"
} else {
    @(Invoke-RestMethod -Uri "$api/subscriptions") |
        Where-Object { $_.name -eq $payload.name -or $_.name -eq "Agentic RAG ???" } |
        Select-Object -First 1
}
$body = $payload | ConvertTo-Json -Depth 5
$bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($body)
if ($null -eq $existing) {
    $subscription = Invoke-RestMethod -Method Post -Uri "$api/subscriptions" -ContentType "application/json; charset=utf-8" -Body $bodyBytes
    Write-Host "Created subscription: $($subscription.id)"
} else {
    $subscription = Invoke-RestMethod -Method Patch -Uri "$api/subscriptions/$($existing.id)" -ContentType "application/json; charset=utf-8" -Body $bodyBytes
    Write-Host "Updated subscription: $($subscription.id)"
}

if ($TestSend) {
    $delivery = Invoke-RestMethod -Method Post -Uri "$api/subscriptions/$($subscription.id)/test-send" -ContentType "application/json" -Body "{}"
    if ($delivery.status -ne "sent") { throw "SMTP test failed: $($delivery.error)" }
    Write-Host "SMTP test sent to $Recipient"
}

if ($RunNow) {
    $run = Invoke-RestMethod -Method Post -Uri "$api/subscriptions/$($subscription.id)/runs"
    Write-Host "Started production subscription run: $($run.id)"

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Seconds 2
        $run = Invoke-RestMethod -Uri "$api/runs/$($run.id)"
        Write-Host "Run status: $($run.status) ($($run.progress)/$($run.total_steps))"
    } while ($run.status -in @("queued", "running", "paused") -and [DateTime]::UtcNow -lt $deadline)

    if ($run.status -in @("queued", "running", "paused")) {
        throw "Production run $($run.id) did not finish within $TimeoutSeconds seconds."
    }
    if ($run.status -ne "completed") {
        throw "Production run $($run.id) ended with status '$($run.status)': $($run.error)"
    }

    $papersResponse = Invoke-RestMethod -Uri "$api/runs/$($run.id)/papers"
    $papers = @($papersResponse | ForEach-Object { $_ })
    $paperSources = @($papers | Select-Object -ExpandProperty source -Unique)
    if ($papers.Count -ne $payload.target_count) {
        throw "Production run returned $($papers.Count) paper(s); expected $($payload.target_count)."
    }
    if ($paperSources.Count -lt 2) {
        throw "Production run did not meet source diversity: $($paperSources -join ', ')"
    }
    $artifactsResponse = Invoke-RestMethod -Uri "$api/runs/$($run.id)/artifacts"
    $artifacts = @($artifactsResponse | ForEach-Object { $_ })
    $reviewArtifact = $artifacts | Where-Object { $_.node -eq "evidence_reviewer" } | Select-Object -First 1
    if ($null -eq $reviewArtifact -or $reviewArtifact.payload.reviewed_count -ne $payload.target_count) {
        throw "Evidence review did not complete for all $($payload.target_count) papers."
    }
    Write-Host "Validated $($papers.Count) papers across $($paperSources.Count) sources: $($paperSources -join ', ')"

    do {
        $deliveries = @(Invoke-RestMethod -Uri "$api/deliveries?subscription_id=$($subscription.id)&limit=100")
        $delivery = $deliveries | Where-Object { $_.run_id -eq $run.id } | Select-Object -First 1
        if ($null -eq $delivery -or $delivery.status -eq "pending") { Start-Sleep -Seconds 2 }
    } while (($null -eq $delivery -or $delivery.status -eq "pending") -and [DateTime]::UtcNow -lt $deadline)

    if ($null -eq $delivery) {
        throw "Production run $($run.id) completed, but no delivery record was created."
    }
    if ($delivery.status -eq "pending") {
        throw "Production delivery did not finish within $TimeoutSeconds seconds."
    }
    if ($delivery.status -ne "sent") {
        throw "Production delivery failed with status '$($delivery.status)': $($delivery.error)"
    }
    Write-Host "Production digest sent to $Recipient."
}

$subscription
