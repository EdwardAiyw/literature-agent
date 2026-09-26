import argparse
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def load_jev_release():
    path = ROOT / "scripts" / "jev-release.py"
    spec = importlib.util.spec_from_file_location("jev_release", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_localjev_prepare_checks_readiness_and_writes_shadow_config(monkeypatch):
    release = load_jev_release()
    calls = []
    written = {}

    class FakeSettings:
        jev_provider = "localjev"
        jev_base_url = "http://127.0.0.1:8080/v1"
        jev_api_key = "local-secret"

        @classmethod
        def from_env(cls, _root):
            return cls()

    responses = {
        "/health": {"status": "ok"},
        "/ready": {"status": "ready", "upstream_model": "diffusiongemma-test"},
        "/v1/models": {"models": [{"name": "localjev-latest"}, {"name": "localjev-0.2"}]},
    }

    def fake_request(base_url, path, **kwargs):
        calls.append((base_url, path, kwargs))
        return responses[path]

    monkeypatch.setattr(release, "Settings", FakeSettings)
    monkeypatch.setattr(release, "request_json", fake_request)
    monkeypatch.setattr(release, "update_env", written.update)

    assert release.prepare(argparse.Namespace(base_url=None)) == 0
    assert [call[1] for call in calls] == ["/health", "/ready", "/v1/models"]
    assert all(call[0] == "http://127.0.0.1:8080" for call in calls)
    assert calls[-1][2]["headers"] == {"Authorization": "Bearer local-secret"}
    assert written == {
        "JEV_PROVIDER": "localjev",
        "JEV_BASE_URL": "http://127.0.0.1:8080",
        "JEV_MODEL": "jev-latest",
        "JEV_TIMEOUT_SECONDS": "180",
        "JEV_MAX_INFLIGHT": "2",
        "JEV_ENABLED": "true",
        "JEV_SHADOW_MODE": "true",
    }


def test_localjev_prepare_rejects_unavailable_upstream(monkeypatch):
    release = load_jev_release()
    written = {}

    def fake_request(_base_url, path, **_kwargs):
        if path == "/health":
            return {"status": "ok"}
        return {"status": "unavailable", "detail": "upstream is offline"}

    monkeypatch.setattr(release, "request_json", fake_request)
    monkeypatch.setattr(release, "update_env", written.update)

    with pytest.raises(RuntimeError, match="upstream is offline"):
        release.inspect_localjev("http://127.0.0.1:8080")
    assert written == {}


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
