from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from literature_agent import api, sources
from literature_agent.config import ConfigManager, MemorySecretStore, Settings
from literature_agent.db import Database


@pytest.fixture
def configured_app(tmp_path, monkeypatch):
    for variable in ("SERPAPI_API_KEY", "CORE_API_KEY"):
        monkeypatch.delenv(variable, raising=False)
    base = Settings(root=tmp_path, data_dir=tmp_path / "data")
    store = MemorySecretStore()
    manager = ConfigManager(base, store)
    database = Database(tmp_path / "product.db")
    monkeypatch.setattr(api, "config_manager", manager)
    monkeypatch.setattr(api, "settings", manager.get())
    monkeypatch.setattr(api, "database", database)
    sources._REQUEST_GATES.clear()
    monkeypatch.setattr(sources.time, "sleep", lambda _: None)
    with TestClient(api.app) as client:
        yield client, manager, store, database
    database.close()
    sources._REQUEST_GATES.clear()


def test_add_source_persists_configuration_without_exposing_credentials(configured_app):
    client, manager, store, _ = configured_app
    catalogue = {item["id"]: item for item in client.get("/api/sources").json()}
    assert catalogue["google_scholar"]["added"] is False
    assert catalogue["google_scholar"]["selectable"] is False
    missing = client.put("/api/sources/google_scholar", json={"enabled": True})
    assert missing.status_code == 422
    response = client.put("/api/sources/google_scholar", json={
        "api_key": "private-scholar-key", "enabled": True, "default_enabled": True, "daily_request_budget": 12,
    })
    assert response.status_code == 200
    assert response.json()["selectable"] is True
    assert response.json()["credential_configured"] is True
    assert response.json()["daily_request_budget"] == 12
    assert "private-scholar-key" not in response.text
    assert "private-scholar-key" not in client.get("/api/settings").text
    assert "private-scholar-key" not in manager.path.read_text(encoding="utf-8")
    restored = ConfigManager(manager.base, store).get()
    assert restored.serpapi_api_key == "private-scholar-key"
    assert sources.source_configuration(restored, "google_scholar")["default_enabled"] is True
    # An empty field preserves the stored key; clearing requires an explicit action.
    client.put("/api/sources/google_scholar", json={"api_key": "", "daily_request_budget": None})
    assert api.settings.serpapi_api_key == "private-scholar-key"
    assert sources.source_configuration(api.settings, "google_scholar")["daily_request_budget"] == 200


def test_task_and_subscription_defaults_follow_saved_source_preferences(configured_app):
    client, _, _, _ = configured_app
    client.put("/api/sources/arxiv", json={"enabled": False})
    client.put("/api/sources/google_scholar", json={"api_key": "key", "enabled": True, "default_enabled": True})
    task_response = client.post("/api/tasks", json={"name": "Configured defaults", "topic": "retrieval"})
    assert task_response.status_code == 200
    task = task_response.json()
    assert "arxiv" not in task["sources"]
    assert "google_scholar" in task["sources"]
    subscription = client.post("/api/subscriptions", json={
        "name": "Configured daily", "topic": "retrieval", "recipient": "reader@example.org", "schedule_time": "09:00", "target_count": 5,
    }).json()
    assert subscription["sources"] == task["sources"]
    assert client.post("/api/tasks", json={"name": "Disabled source", "topic": "topic", "sources": ["arxiv"]}).status_code == 422
    client.delete("/api/sources/google_scholar")
    assert client.get(f"/api/tasks/{task['id']}").json()["sources"] == task["sources"]
    assert "google_scholar" not in sources.default_source_ids(api.settings)
    client.put("/api/sources/google_scholar", json={"enabled": True})
    assert sources.source_configuration(api.settings, "google_scholar")["selectable"] is True
    client.put("/api/sources/google_scholar", json={"clear_api_key": True})
    state = sources.source_configuration(api.settings, "google_scholar")
    assert state["enabled"] is state["credential_configured"] is state["selectable"] is False


def test_disabled_sources_do_not_request_or_serve_a_previous_cache(configured_app):
    client, _, _, database = configured_app
    calls = []
    with httpx.Client(transport=httpx.MockTransport(lambda request: calls.append(request) or httpx.Response(200, json={"message": {"items": []}}))) as transport:
        sources.search_sources(["crossref"], ("topic",), 1, "", "", transport, api.settings, cache=database)
        client.put("/api/sources/crossref", json={"enabled": False})
        records, diagnostics = sources.search_sources(["crossref"], ("topic",), 1, "", "", transport, api.settings, cache=database)
    assert len(calls) == 1
    assert records == []
    assert diagnostics["crossref"]["status"] == "disabled"


def test_single_source_test_uses_fresh_requests_and_sanitizes_errors(configured_app, monkeypatch):
    client, manager, _, database = configured_app
    key = "secret-that-must-never-appear"
    client.put("/api/sources/google_scholar", json={"api_key": key, "enabled": True, "daily_request_budget": 2})
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json={"organic_results": [{"result_id": "a", "title": "A research paper"}]})
        return httpx.Response(401)
    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        monkeypatch.setattr(api, "build_sources", lambda _, settings: {"google_scholar": sources.GoogleScholarSource(transport, settings.serpapi_api_key)})
        first = client.post("/api/sources/google_scholar/test")
        assert first.json()["status"] == "ok"
        second = client.post("/api/sources/google_scholar/test")
    assert len(calls) == 2
    assert second.json()["status"] == "failed"
    assert second.json()["final_http_status"] == 401
    assert "HTTP 401" in second.json()["error"]
    assert key not in second.text
    assert key not in manager.path.read_text(encoding="utf-8")
    assert database.source_usage_total() == 2
    state = client.get("/api/sources").json()
    assert next(item for item in state if item["id"] == "google_scholar")["last_test"]["status"] == "failed"
    client.put("/api/sources/google_scholar", json={"api_key": "different-key"})
    assert sources.source_configuration(api.settings, "google_scholar")["last_test"] is None


@pytest.mark.parametrize("payload", [
    {"daily_request_budget": 0}, {"daily_request_budget": -1}, {"daily_request_budget": 100001},
    {"unknown_field": True}, {"api_key": "not-supported"}, {"email": "not-an-email"},
])
def test_source_settings_validate_inputs(configured_app, payload):
    client, _, _, _ = configured_app
    assert client.put("/api/sources/doaj", json=payload).status_code == 422
    assert client.put("/api/sources/not-a-source", json={}).status_code == 404


def test_no_default_sources_gives_actionable_creation_error(configured_app):
    client, _, _, _ = configured_app
    for name in sources.DEFAULT_SOURCES:
        assert client.put(f"/api/sources/{name}", json={"default_enabled": False}).status_code == 200
    response = client.post("/api/tasks", json={"name": "No defaults", "topic": "topic"})
    assert response.status_code == 422
    assert "来源" in response.json()["detail"]


def test_scholar_pagination_preserves_partial_results_and_never_treats_snippets_as_abstracts(tmp_path, monkeypatch):
    sources._REQUEST_GATES.clear()
    monkeypatch.setattr(sources.time, "sleep", lambda _: None)
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url.params["as_ylo"] == "2025"
        if request.url.params["start"] != "0":
            return httpx.Response(429, headers={"Retry-After": "120"})
        return httpx.Response(200, json={"organic_results": [{
            "result_id": str(i), "title": f"Paper {i}", "snippet": "A short search excerpt.",
            "publication_info": {"summary": "A Author - Journal, 2025 - example.org", "authors": [{"name": "A Author"}]},
        } for i in range(20)], "serpapi_pagination": {"next": "https://serpapi.com/search.json?start=20"}})
    settings = Settings(root=tmp_path, serpapi_api_key="key", source_configs={"google_scholar": {"added": True, "enabled": True}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        records, diagnostics = sources.search_sources(["google_scholar"], ("topic",), 21, "2025-06-01", "2025-12-31", transport, settings)
    assert len(records) == 20
    assert records[0]["abstract"] == ""
    assert records[0]["search_snippet"] == "A short search excerpt."
    assert records[0]["published_date"] == "2025" and records[0]["date_unknown"] is True
    assert diagnostics["google_scholar"]["status"] == "partial"
    assert len(calls) == 2
    sources._REQUEST_GATES.clear()


def test_core_uses_bearer_auth_and_normalizes_metadata(tmp_path):
    def handler(request):
        assert request.headers["Authorization"] == "Bearer core-key"
        assert "yearPublished" in request.url.params["q"]
        return httpx.Response(200, json={"results": [{"id": 42, "doi": "10.1234/CORE", "title": "CORE paper",
            "abstract": "Full abstract", "authors": [{"name": "A Author"}], "yearPublished": 2025,
            "downloadUrl": "https://repository.example/paper.pdf", "language": {"code": "en"}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        paper = sources.CORESource(transport, "core-key").search(("topic",), 1, "2025-01-01", "2025-12-31")[0]
    assert paper["doi"] == "10.1234/core"
    assert paper["authors"] == ["A Author"]
    assert paper["language"] == "en"
    assert paper["abstract"] == "Full abstract"


def test_source_config_save_retries_transient_windows_file_locks(tmp_path, monkeypatch):
    import literature_agent.config as config
    if config.os.name != "nt":
        pytest.skip("Windows file sharing behavior")
    manager = ConfigManager(Settings(root=tmp_path, data_dir=tmp_path), MemorySecretStore())
    original_replace = Path.replace
    attempts = []
    def briefly_locked(path, target):
        attempts.append(path)
        if len(attempts) < 3:
            raise PermissionError("temporary file sharing lock")
        return original_replace(path, target)
    monkeypatch.setattr(Path, "replace", briefly_locked)
    monkeypatch.setattr(config.time, "sleep", lambda _: None)
    manager.update({"source_configs": {"crossref": {"enabled": False}}})
    assert len(attempts) == 3
    assert manager.get().source_configs["crossref"]["enabled"] is False


def test_source_request_logs_never_include_query_string_credentials(caplog, monkeypatch):
    import logging
    # Alembic disables existing loggers during API initialization. Exercise the
    # request logger explicitly so an empty capture cannot pass this check.
    monkeypatch.setattr(logging.getLogger("httpx"), "disabled", False)
    key = "scholar-private-log-key"
    with caplog.at_level(logging.INFO, logger="httpx"):
        with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"organic_results": []}))) as transport:
            sources.GoogleScholarSource(transport, key).search(("research",), 1, "", "")
    assert "serpapi.com" in caplog.text
    assert key not in caplog.text
    assert "[redacted]" in caplog.text
