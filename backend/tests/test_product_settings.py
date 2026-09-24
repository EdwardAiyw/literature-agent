from fastapi.testclient import TestClient

from literature_agent import api
from literature_agent.config import ConfigManager, MemorySecretStore, Settings
from literature_agent.db import Database


def test_config_manager_separates_secrets_and_hot_updates(tmp_path):
    secrets = MemorySecretStore()
    manager = ConfigManager(Settings(root=tmp_path, data_dir=tmp_path / "data"), secrets)

    current = manager.update(
        {"live": True, "llm_base_url": "https://models.example/v1", "llm_model": "research-model"},
        {"llm_api_key": "secret-value"},
    )

    assert current.live is True
    assert current.llm_api_key == "secret-value"
    assert secrets.get("llm_api_key") == "secret-value"
    assert "secret-value" not in manager.path.read_text(encoding="utf-8")
    public = manager.public()
    assert public["secrets"]["llm_api_key"] is True
    assert "llm_api_key" not in public

    cleared = manager.update({}, {"llm_api_key": ""})
    assert cleared.llm_api_key == ""
    assert secrets.get("llm_api_key") == ""


def test_settings_api_never_returns_or_persists_secret(tmp_path, monkeypatch):
    manager = ConfigManager(Settings(root=tmp_path, data_dir=tmp_path / "data"), MemorySecretStore())
    monkeypatch.setattr(api, "config_manager", manager)
    monkeypatch.setattr(api, "settings", manager.get())

    with TestClient(api.app) as client:
        response = client.put("/api/settings/llm", json={
            "live": True,
            "llm_base_url": "https://models.example/v1",
            "llm_model": "research-model",
            "llm_api_key": "api-secret",
        })

    assert response.status_code == 200
    assert response.json()["license"] == "AGPL-3.0-only"
    assert response.json()["source_url"] == "https://github.com/EdwardAiyw/literature-agent"
    assert "api-secret" not in response.text
    assert "api-secret" not in manager.path.read_text(encoding="utf-8")
    assert api.settings.llm_api_key == "api-secret"


def test_settings_sections_reject_unrelated_fields(tmp_path, monkeypatch):
    manager = ConfigManager(Settings(root=tmp_path, data_dir=tmp_path / "data"), MemorySecretStore())
    monkeypatch.setattr(api, "config_manager", manager)
    monkeypatch.setattr(api, "settings", manager.get())

    with TestClient(api.app) as client:
        response = client.put("/api/settings/smtp", json={"llm_model": "wrong-section"})

    assert response.status_code == 422


def test_cross_origin_write_is_rejected():
    with TestClient(api.app) as client:
        response = client.post(
            "/api/tasks",
            headers={"Origin": "https://malicious.example"},
            json={"name": "Blocked", "topic": "blocked"},
        )
    assert response.status_code == 403


def test_second_run_for_same_task_is_rejected():
    with TestClient(api.app) as client:
        task = client.post("/api/tasks", json={"name": "Run lock", "topic": "locking"}).json()
        active = api.database.create_run(task["id"], total_steps=6)
        response = client.post(f"/api/tasks/{task['id']}/runs")
        assert response.status_code == 409
        api.database.update_run(active["id"], status="completed")
        client.delete(f"/api/tasks/{task['id']}")


def test_subscription_run_window_and_backup_integrity(tmp_path):
    database = Database(tmp_path / "agent.db")
    try:
        task = database.create_task({"name": "Daily", "topic": "RAG", "origin": "subscription"})
        first = database.create_run_if_idle(
            task["id"], 6, trigger_kind="subscription", subscription_id="subscription-1",
            not_before="2026-09-24T00:00:00+00:00",
        )
        assert first is not None
        database.update_run(first["id"], status="completed")
        assert database.create_run_if_idle(
            task["id"], 6, trigger_kind="subscription", subscription_id="subscription-1",
            not_before="2026-09-24T00:00:00+00:00",
        ) is None

        backup = database.backup(tmp_path / "backups" / "test.db")
        Database.validate_backup(backup)
    finally:
        database.close()
