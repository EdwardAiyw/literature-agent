import json
from pathlib import Path
import sqlite3
import sys

from fastapi.testclient import TestClient
import pytest

from literature_agent import api, launcher, obsidian, obsidian_service as service


@pytest.fixture
def configured(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    db = tmp_path / "source.db"
    connection = sqlite3.connect(db)
    connection.executescript("CREATE TABLE deliveries(id,run_id,subject,sent_at,subscription_id,kind,status); CREATE TABLE papers(id,run_id,payload); CREATE TABLE zotero_imports(paper_id,destination,payload,updated_at);")
    connection.execute("INSERT INTO deliveries VALUES ('d1','r1','Daily','2026-10-19T00:00:00+00:00','s1','digest','sent')")
    connection.execute("INSERT INTO papers VALUES ('p1','r1',?)", (json.dumps({"title": "Local paper", "doi": "10.1234/test"}),))
    connection.commit()
    connection.close()
    path = tmp_path / "integration" / "config.json"
    monkeypatch.setenv("LITERATURE_AGENT_OBSIDIAN_CONFIG", str(path))
    monkeypatch.setattr(service, "supported", lambda: True)
    monkeypatch.setattr(service, "discover_vaults", lambda: [])
    monkeypatch.setattr(service, "scheduler_status", lambda names: {"tasks": []})
    config = {"vault": str(vault), "folder": "Literature Agent", "mode": "local", "database": str(db), "subscription_id": "s1", "since": "2026-10-19T00:00:00+08:00"}
    return config, path


def test_product_api_saves_syncs_and_reuses_notes(configured, monkeypatch):
    config, path = configured
    before = Path(config["database"]).read_bytes()
    with TestClient(api.app) as client:
        assert client.get("/api/obsidian").json()["config"] is None
        assert client.put("/api/obsidian", json=config).status_code == 200
        saved = client.get("/api/obsidian").json()["config"]
        assert saved["mode"] == "local"
        response = client.post("/api/obsidian/sync")
        assert response.status_code == 200
        assert response.json()["unique_notes"] == 1
        assert client.post("/api/obsidian/sync").json()["unique_notes"] == 1
        assert client.get("/api/obsidian").json()["last_sync"]["status"] == "ok"
        called = []
        monkeypatch.setattr(service, "schedule", lambda data_dir, action: called.append(action))
        assert client.post("/api/obsidian/register").status_code == 200
        assert client.post("/api/obsidian/disable").status_code == 200
        assert called == ["register", "disable"]
        assert client.post("/api/obsidian/nonsense").status_code == 400
    assert Path(config["database"]).read_bytes() == before
    assert len(list((Path(config["vault"]) / "Literature Agent/Papers").glob("*.md"))) == 1
    assert path.is_file()


@pytest.mark.parametrize("change", [{"folder": "../outside"}, {"folder": "X|spoof"}, {"timezone": "Missing/Zone"}, {"since": "2026-10-19"}, {"mode": "ssh", "ssh_target": "-oProxyCommand=bad"}])
def test_product_rejects_invalid_config_without_replacing_saved(configured, change):
    config, path = configured
    with TestClient(api.app) as client:
        assert client.put("/api/obsidian", json=config).status_code == 200
        before = path.read_bytes()
        assert client.put("/api/obsidian", json={**config, **change}).status_code == 422
        assert path.read_bytes() == before


def test_server_does_not_expose_or_run_desktop_integration(configured, monkeypatch):
    monkeypatch.setattr(service, "supported", lambda: False)
    monkeypatch.setattr(service, "sync_now", lambda _: pytest.fail("Must not run desktop sync"))
    with TestClient(api.app) as client:
        assert client.get("/api/obsidian").json()["supported"] is False
        assert client.post("/api/obsidian/sync").status_code == 409


def test_sync_failure_is_reported_and_lock_is_released(configured):
    config, path = configured
    service.save(path.parent, service.ObsidianConfig(**config))
    broken = {**config, "database": str(path.parent / "missing.db")}
    path.write_text(json.dumps(broken), encoding="utf-8")
    with TestClient(api.app) as client:
        response = client.post("/api/obsidian/sync")
        assert response.status_code == 400
        assert "无法读取本机文献数据库" in response.json()["detail"]
    assert json.loads((path.parent / "last-sync.json").read_text())["status"] == "error"
    path.write_text(json.dumps(config), encoding="utf-8")
    assert obsidian.sync(path)["unique_notes"] == 1


def test_packaged_command_routes_to_exporter_without_starting_web_server(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "_configure_logging", lambda: None)
    monkeypatch.setattr(sys, "argv", ["LiteratureAgent.exe", "--sync-obsidian", "config.json"])
    received = []
    monkeypatch.setattr(obsidian, "main", lambda args: received.extend(args) or 0)
    assert launcher.main() == 0
    assert received == ["--config", "config.json"]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "LiteratureAgent.exe"))
    assert obsidian.snapshot_script() == tmp_path / "scripts/obsidian-snapshot.py"
