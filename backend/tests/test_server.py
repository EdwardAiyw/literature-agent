import os
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from literature_agent import api
from literature_agent.config import ConfigManager, FileSecretStore, Settings
from literature_agent.db import Database
from literature_agent.scheduler import DailyScheduler


def test_server_secrets_survive_new_config_instances_and_clear(tmp_path, monkeypatch):
    base = Settings(root=tmp_path, data_dir=tmp_path / "data", llm_api_key="old-env-secret")
    store = FileSecretStore(base.data_dir / "secrets.json")
    first = ConfigManager(base, store)
    first.update({"llm_model": "model"}, {"llm_api_key": "server-secret", "smtp_password": "mail-secret"})
    second = ConfigManager(base, FileSecretStore(store.path))
    assert second.get().llm_api_key == "server-secret"
    assert second.get().smtp_password == "mail-secret"
    assert "server-secret" not in second.path.read_text()
    if os.name != "nt":
        assert store.path.stat().st_mode & 0o777 == 0o600
    second.update({}, {"llm_api_key": ""})
    assert ConfigManager(base, FileSecretStore(store.path)).get().llm_api_key == ""


class RecordingWorker:
    def __init__(self):
        self.submitted = []

    def submit_subscription(self, run_id, subscription):
        self.submitted.append((run_id, subscription["id"]))


def scheduled(tmp_path):
    db = Database(tmp_path / "server.db")
    task = db.create_task({"name": "Daily", "topic": "RAG", "evidence_review": True})
    sub = db.create_subscription(task["id"], {"name": "Daily", "topic": "RAG", "recipient": "reader@example.org",
        "schedule_time": "08:00", "timezone": "Asia/Hong_Kong", "target_count": 5, "sources": ["openalex"], "enabled": True})
    settings = Settings(root=tmp_path, live=True, llm_api_key="test", llm_model="test", smtp_host="smtp.example.org", smtp_from="sender@example.org")
    worker = RecordingWorker()
    return db, task, sub, worker, DailyScheduler(lambda: settings, db, worker)


def test_server_scheduler_catches_up_and_respects_day_and_manual_runs(tmp_path):
    db, task, sub, worker, scheduler = scheduled(tmp_path)
    try:
        manual = db.create_run(task["id"], 6)
        db.update_run(manual["id"], status="completed", started_at="2026-10-15T00:01:00+00:00")
        assert scheduler.tick(datetime(2026, 10, 14, 23, 59, tzinfo=timezone.utc)) == 0
        assert scheduler.tick(datetime(2026, 10, 15, 2, tzinfo=timezone.utc)) == 1
        run_id = worker.submitted[0][0]
        db.update_run(run_id, status="completed", started_at="2026-10-15T02:00:00+00:00")
        assert scheduler.tick(datetime(2026, 10, 15, 3, tzinfo=timezone.utc)) == 0
        assert scheduler.tick(datetime(2026, 10, 16, 0, tzinfo=timezone.utc)) == 1
    finally:
        db.close()


def test_server_scheduler_active_runs_and_disabled_subscriptions_are_not_started(tmp_path):
    db, task, sub, worker, scheduler = scheduled(tmp_path)
    try:
        active = db.create_run(task["id"], 6)
        assert scheduler.tick(datetime(2026, 10, 15, 1, tzinfo=timezone.utc)) == 0
        db.update_run(active["id"], status="completed")
        db.update_subscription(sub["id"], {**sub, "enabled": False})
        assert scheduler.tick(datetime(2026, 10, 15, 1, tzinfo=timezone.utc)) == 0
        assert worker.submitted == []
    finally:
        db.close()


def test_competing_server_schedulers_queue_once(tmp_path):
    db, task, sub, worker, scheduler = scheduled(tmp_path)
    other = Database(db.path)
    second = DailyScheduler(scheduler.settings, other, worker)
    try:
        instant = datetime(2026, 10, 15, 1, tzinfo=timezone.utc)
        assert scheduler.tick(instant) == 1
        assert second.tick(instant) == 0
        assert len(worker.submitted) == 1
    finally:
        other.close()
        db.close()


def test_server_scheduler_pause_and_missing_model_do_not_create_runs(tmp_path, monkeypatch):
    db, task, sub, worker, scheduler = scheduled(tmp_path)
    try:
        monkeypatch.setenv("LITERATURE_AGENT_SCHEDULER_PAUSED", "true")
        assert scheduler.tick(datetime(2026, 10, 15, 1, tzinfo=timezone.utc)) == 0
        monkeypatch.delenv("LITERATURE_AGENT_SCHEDULER_PAUSED")
        scheduler.settings = lambda: Settings(root=tmp_path)
        assert scheduler.tick(datetime(2026, 10, 15, 1, tzinfo=timezone.utc)) == 0
        assert db.list_runs(task["id"]) == []
    finally:
        db.close()


def test_server_lifespan_stops_scheduler_and_guards_database_replacement(tmp_path, monkeypatch):
    monkeypatch.setenv("LITERATURE_AGENT_SERVER", "true")
    db = Database(tmp_path / "api.db")
    monkeypatch.setattr(api, "database", db)
    with TestClient(api.app) as client:
        assert client.get("/api/settings").json()["server_mode"] is True
        assert client.get("/api/scheduler").json()["running"] is True
        assert client.get("/api/onboarding").json()["steps"]["scheduler"] is True
        assert client.post("/api/scheduler/register").status_code == 409
        assert client.put("/api/system/data-directory", json={"path": str(tmp_path)}).status_code == 409
        assert client.post("/api/backups/restore", json={"path": str(tmp_path / "backup.db")}).status_code == 409
        # The SSH tunnel uses its own Host port; same-origin writes must still work.
        response = client.post("/api/tasks", headers={"Host": "127.0.0.1:18001", "Origin": "http://127.0.0.1:18001"}, json={"name": "Tunnel", "topic": "RAG"})
        assert response.status_code == 200
    assert api.daily_scheduler is None
    db.close()
