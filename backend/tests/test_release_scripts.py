from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_production_subscription_allows_jev_to_be_disabled():
    script = (ROOT / "scripts" / "create-agentic-rag-subscription.ps1").read_text(encoding="utf-8")

    assert "Jev must be configured in Active mode" not in script
    assert "existing LLM/rule decision path" in script
    assert "-not $runtime.live" in script
    assert "-not $runtime.llm_configured" in script
    assert "-not $runtime.smtp_configured" in script
    assert 'Get-DotEnvValues -Path $envFile' in script
    assert '"LLM_API_KEY", "LLM_MODEL", "SMTP_HOST", "SMTP_FROM"' in script
    assert 'SMTP_PASSWORD' in script
    assert '$ValidateOnly' in script
    assert "No subscription or delivery was created" in script
    assert '[char]0x65E5' in script
    assert '[char]0x62A5' in script
    assert 'application/json; charset=utf-8' in script
    assert '$SubscriptionId' in script


def test_run_now_waits_for_successful_digest_delivery():
    script = (ROOT / "scripts" / "create-agentic-rag-subscription.ps1").read_text(encoding="utf-8")

    assert 'Invoke-RestMethod -Uri "$api/runs/$($run.id)"' in script
    assert 'Invoke-RestMethod -Uri "$api/deliveries?subscription_id=$($subscription.id)&limit=100"' in script
    assert '$delivery.status -eq "pending"' in script
    assert '$delivery.status -ne "sent"' in script
    assert "TimeoutSeconds" in script
    assert '$paperSources.Count -lt 2' in script
    assert 'evidence_reviewer' in script
    assert '$papersResponse | ForEach-Object' in script


def test_startup_registration_supports_packaged_and_source_runtime_without_env_file():
    script = (ROOT / "scripts" / "register-local-startup.ps1").read_text(encoding="utf-8")

    assert 'Join-Path $projectRoot "LiteratureAgent.exe"' in script
    assert 'Join-Path $PSScriptRoot "start-local.ps1"' in script
    assert 'backend\\.env' not in script
    assert 'New-ScheduledTaskAction -Execute $packagedApp' in script
