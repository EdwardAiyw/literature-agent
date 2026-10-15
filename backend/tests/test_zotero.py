import json
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient

from literature_agent import api
from literature_agent.config import ConfigManager, MemorySecretStore, Settings
from literature_agent.db import Database
from literature_agent.zotero import IMPORT_LOCK, ZoteroClient, ZoteroError, destination_for


def settings(tmp_path, **kwargs):
    return Settings(root=tmp_path, data_dir=tmp_path, zotero_library_id="123", zotero_api_key="never-print-this", **kwargs)


def test_import_doi_is_idempotent_and_keeps_existing_fields(tmp_path):
    items = []
    creations = []
    patches = []

    def handler(request):
        assert request.headers["Zotero-API-Key"] == "never-print-this"
        if request.url.path.endswith("/items/top"):
            # Real Zotero quick search misses DOI-only metadata, even with
            # qmode=everything. Only an unfiltered scan can find these items.
            assert "q" not in request.url.params
            assert "qmode" not in request.url.params
            return httpx.Response(200, json=items)
        if request.url.path.endswith("/collections"):
            return httpx.Response(200, json=[{"key": "COLL0001", "data": {"name": "Literature Agent"}}])
        if request.method == "POST":
            data = json.loads(request.content)[0]
            assert len(request.headers["Zotero-Write-Token"]) == 32
            creations.append(data)
            items.append({"key": "ITEM0001", "version": 4, "data": {**data, "title": "User edited title", "collections": ["OTHER001"]}})
            return httpx.Response(200, json={"successful": {"0": {"key": "ITEM0001"}}})
        if request.method == "PATCH":
            patches.append(json.loads(request.content))
            assert request.headers["If-Unmodified-Since-Version"] == "4"
            return httpx.Response(204)
        raise AssertionError(request.url)

    paper = {"title": "A study", "doi": "https://doi.org/10.1234/EXAMPLE", "authors": ["Jane Doe"], "source": "crossref", "abstract": "Evidence"}
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        zotero = ZoteroClient(settings(tmp_path), client)
        assert zotero.import_paper(paper)["status"] == "imported"
        assert zotero.import_paper({**paper, "id": "other-run"})["status"] == "existing"
    assert len(creations) == 1
    assert creations[0]["DOI"] == "10.1234/example"
    assert patches == [{"collections": ["OTHER001", "COLL0001"]}]
    assert items[0]["data"]["title"] == "User edited title"


def test_no_doi_title_match_and_collection_creation(tmp_path):
    writes = []
    def handler(request):
        if request.url.path.endswith("/items/top"):
            assert request.url.params["q"] == "A study"
            return httpx.Response(200, json=[{"key": "ITEM0002", "version": 1, "data": {"title": "  A STUDY  ", "collections": []}}])
        if request.method == "GET":
            return httpx.Response(200, json=[])
        writes.append((request.method, json.loads(request.content)))
        return httpx.Response(204) if request.method == "PATCH" else httpx.Response(200, json={"successful": {"0": {"key": "COLL0002"}}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = ZoteroClient(settings(tmp_path), client).import_paper({"title": "A study"})
    assert result["status"] == "existing"
    assert writes == [("POST", [{"name": "Literature Agent"}]), ("PATCH", {"collections": ["COLL0002"]})]


def test_existing_doi_beyond_first_page_is_reused(tmp_path):
    starts = []
    def handler(request):
        assert request.method == "GET"
        if request.url.path.endswith("/items/top"):
            assert "q" not in request.url.params
            start = int(request.url.params["start"])
            starts.append(start)
            rows = [{"key": "OTHER001", "data": {"DOI": "10.1234/unrelated"}}] * 100 if start == 0 else [
                {"key": "ITEM0003", "version": 3, "data": {"DOI": "10.1234/match", "collections": ["COLL0003"]}}]
            return httpx.Response(200, json=rows, headers={"Total-Results": "101"})
        return httpx.Response(200, json={"key": "COLL0003"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = ZoteroClient(settings(tmp_path, zotero_collection_key="COLL0003"), client).import_paper({"title": "Study", "doi": "10.1234/match"})
    assert starts == [0, 100]
    assert result["item_key"] == "ITEM0003"
    assert result["status"] == "existing"


def test_doi_scan_requires_exact_metadata_and_ignores_non_citations(tmp_path):
    writes = []
    def handler(request):
        if request.url.path.endswith("/items/top"):
            assert "q" not in request.url.params
            return httpx.Response(200, json=[
                {"key": "NOTE0001", "data": {"DOI": "10.1234/match", "itemType": "note"}},
                {"key": "FILE0001", "data": {"DOI": "10.1234/match", "itemType": "attachment"}},
                {"key": "DEAD0001", "data": {"DOI": "10.1234/match", "deleted": 1}},
                {"key": "OTHER001", "data": {"DOI": "10.1234/match-extra", "title": "Study"}},
                {"key": "OTHER002", "data": {"title": "Study", "abstractNote": "10.1234/match"}},
            ])
        if request.method == "GET":
            return httpx.Response(200, json={"key": "COLL0001"})
        writes.append(request.method)
        return httpx.Response(200, json={"successful": {"0": {"key": "NEW00001"}}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = ZoteroClient(settings(tmp_path, zotero_collection_key="COLL0001"), client).import_paper({"title": "Study", "doi": "doi: 10.1234/MATCH"})
    assert result["status"] == "imported"
    assert writes == ["POST"]


@pytest.mark.parametrize("invalid_json", [False, True])
def test_incomplete_doi_scan_never_creates_item_or_collection(tmp_path, invalid_json):
    def handler(request):
        assert request.method == "GET"
        assert request.url.path.endswith("/items/top")
        if request.url.params["start"] == "0":
            return httpx.Response(200, json=[{"data": {"DOI": "10.1234/other"}}] * 100)
        return httpx.Response(200, text="not json") if invalid_json else httpx.Response(500)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ZoteroError):
            ZoteroClient(settings(tmp_path), client).import_paper({"title": "Study", "doi": "10.1234/match"})


@pytest.mark.parametrize("lost_response", [False, True])
def test_reimport_after_deletion_or_lost_response(tmp_path, lost_response):
    items, tokens = [], []
    def handler(request):
        if request.url.path.endswith("/items/top"):
            assert "q" not in request.url.params
            return httpx.Response(200, json=items)
        if request.method == "GET":
            return httpx.Response(200, json={"key": "COLL0001"})
        assert request.method == "POST"
        token = request.headers["Zotero-Write-Token"]
        # Zotero rejects a reused write token with 412.
        if token in tokens:
            return httpx.Response(412)
        tokens.append(token)
        items.append({"key": "ITEM0001", "version": 1, "data": json.loads(request.content)[0]})
        if lost_response and len(tokens) == 1:
            raise httpx.ReadTimeout("response lost after commit", request=request)
        return httpx.Response(200, json={"successful": {"0": {"key": "ITEM0001"}}})
    paper = {"title": "Study", "doi": "https://doi.org/10.1234%2FMATCH"}
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        zotero = ZoteroClient(settings(tmp_path, zotero_collection_key="COLL0001"), client)
        if lost_response:
            with pytest.raises(ZoteroError, match="网络"):
                zotero.import_paper(paper)
        else:
            assert zotero.import_paper(paper)["status"] == "imported"
            items.clear()  # The user deletes the item in Zotero.
        result = zotero.import_paper(paper)
    assert result["status"] == ("existing" if lost_response else "imported")
    assert len(tokens) == (1 if lost_response else 2)
    assert len(set(tokens)) == len(tokens)


def test_http_200_with_failed_item_is_not_reported_as_success(tmp_path):
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"key": "COLL0004"} if "/collections/" in request.url.path else [])
        return httpx.Response(200, json={"successful": {}, "failed": {"0": {"message": "invalid field"}}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ZoteroError, match="未确认写入成功"):
            ZoteroClient(settings(tmp_path, zotero_collection_key="COLL0004"), client).import_paper({"title": "Study"})


@pytest.mark.parametrize("library_type,library_id,access,allowed", [
    ("user", "123", {"user": {"library": True, "write": True}}, True),
    ("user", "456", {"user": {"library": True, "write": True}}, False),
    ("user", "123", {"user": {"library": True}}, False),
    ("group", "456", {"groups": {"456": {"library": True, "write": True}}}, True),
    ("group", "456", {"groups": {"all": {"library": True, "write": True}}}, True),
])
def test_connection_is_read_only_and_checks_target_permissions(tmp_path, library_type, library_id, access, allowed):
    def handler(request):
        assert request.method == "GET"
        return httpx.Response(200, json={"userID": 123, "access": access} if request.url.path == "/keys/current" else [])
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        zotero = ZoteroClient(replace(settings(tmp_path), zotero_library_type=library_type, zotero_library_id=library_id), client)
        if allowed:
            assert zotero.check_connection()["writable"]
        else:
            with pytest.raises(ZoteroError, match="权限"):
                zotero.check_connection()


@pytest.mark.parametrize("code", [403, 429, 500])
def test_provider_errors_do_not_expose_key_or_response(tmp_path, code):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(code, text="never-print-this"))) as client:
        with pytest.raises(ZoteroError) as exc:
            ZoteroClient(settings(tmp_path), client).check_connection()
        assert "never-print-this" not in str(exc.value)


def test_api_persists_failure_retry_and_destination_scoped_results(tmp_path, monkeypatch):
    db = Database(tmp_path / "agent.db")
    task = db.create_task({"name": "Study", "topic": "RAG"})
    run = db.create_run(task["id"], total_steps=6)
    db.update_run(run["id"], status="completed")
    db.add_paper(run["id"], "doi:study", {"title": "Study", "authors": [], "abstract": "", "published_date": "", "source": "crossref"})
    paper = db.list_papers(run["id"])[0]
    monkeypatch.setattr(api, "database", db)
    monkeypatch.setattr(api, "settings", settings(tmp_path))
    def fail(self, paper):
        raise ZoteroError("Permission denied")
    monkeypatch.setattr(ZoteroClient, "import_paper", fail)
    with TestClient(api.app) as client:
        path = f"/api/papers/{paper['id']}/zotero"
        result = client.post(path).json()
        assert result["status"] == "failed"
        assert client.get(f"/api/runs/{run['id']}/papers").json()[0]["zotero"]["error"] == "Permission denied"
        monkeypatch.setattr(ZoteroClient, "import_paper", lambda self, paper: {"status": "imported", "item_key": "ITEM0001", "error": ""})
        assert client.post(path).json()["status"] == "imported"
        monkeypatch.setattr(api, "settings", replace(api.settings, zotero_library_id="456"))
        assert client.get(f"/api/runs/{run['id']}/papers").json()[0]["zotero"] is None
        db.review_paper(paper["id"], "ignore")
        assert client.post(path).status_code == 409
        assert client.post("/api/papers/missing/zotero").status_code == 404
        IMPORT_LOCK.acquire()
        try:
            assert client.post(path).status_code == 409
        finally:
            IMPORT_LOCK.release()
        assert client.delete(f"/api/tasks/{task['id']}").status_code == 200
        assert db.get_zotero_import(paper["id"], destination_for(settings(tmp_path))) is None
    db.close()


def test_zotero_settings_hide_key_and_validate_fields(tmp_path, monkeypatch):
    manager = ConfigManager(Settings(root=tmp_path, data_dir=tmp_path), MemorySecretStore())
    monkeypatch.setattr(api, "settings", manager.get())
    monkeypatch.setattr(api, "config_manager", manager)
    with TestClient(api.app) as client:
        response = client.put("/api/settings/zotero", json={"zotero_library_id": "123", "zotero_api_key": "never-print-this"})
        assert response.json()["zotero_configured"]
        assert "never-print-this" not in response.text
        assert "never-print-this" not in manager.path.read_text()
        assert client.put("/api/settings/zotero", json={"zotero_collection_key": "../invalid"}).status_code == 422
        assert client.put("/api/settings/zotero", json={"llm_model": "invalid"}).status_code == 422
        monkeypatch.setattr(ZoteroClient, "check_connection", lambda self: {"writable": True})
        assert client.post("/api/settings/zotero/test", json={}).json()["diagnostics"]["writable"]
        assert not client.delete("/api/settings/secrets/zotero_api_key").json()["zotero_configured"]


@pytest.fixture
def isolated_import_runtime(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    manager = ConfigManager(settings(data_dir), MemorySecretStore())
    db = Database(manager.get().db_path)
    task = db.create_task({"name": "Lock test", "topic": "RAG"})
    run = db.create_run(task["id"], total_steps=6)
    db.update_run(run["id"], status="completed")
    db.add_paper(run["id"], "doi:lock", {"title": "Study", "doi": "10.1234/lock", "authors": [], "source": "crossref"})
    paper = db.list_papers(run["id"])[0]
    monkeypatch.setattr(api, "config_manager", manager)
    monkeypatch.setattr(api, "settings", manager.get())
    monkeypatch.setattr(api, "database", db)
    monkeypatch.setattr(api, "run_worker", None)
    monkeypatch.setattr(api, "save_bootstrap_data_dir", lambda target: None)
    # Replacement databases intentionally lack the original paper.
    target = tmp_path / "replacement"
    replacement = Database(target / "literature_agent_v2.db")
    replacement.close()
    with TestClient(api.app) as client:
        yield client, db, paper, target
    api.database.close()
    db.close()


def replace_database(client, operation, target):
    if operation == "directory":
        return client.put("/api/system/data-directory", json={"path": str(target)})
    return client.post("/api/backups/restore", json={"path": str(target / "literature_agent_v2.db")})


@pytest.mark.parametrize("operation", ["directory", "restore"])
def test_import_reserves_database_until_local_result_is_saved(isolated_import_runtime, monkeypatch, operation):
    client, db, paper, target = isolated_import_runtime
    entered, release = Event(), Event()
    def import_remote(self, paper):
        entered.set()
        assert release.wait(5)
        return {"status": "imported", "item_key": "ITEM0001", "error": ""}
    monkeypatch.setattr(ZoteroClient, "import_paper", import_remote)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.post, f"/api/papers/{paper['id']}/zotero")
        try:
            assert entered.wait(5)
            assert replace_database(client, operation, target).status_code == 409
            assert api.database is db
        finally:
            release.set()
        assert future.result(timeout=5).status_code == 200
    assert db.get_zotero_import(paper["id"], destination_for(api.settings))["status"] == "imported"
    assert not IMPORT_LOCK.locked()


@pytest.mark.parametrize("operation", ["directory", "restore"])
@pytest.mark.parametrize("pause_at", ["list_recoverable_runs", "close"])
def test_replacement_reserves_lock_before_checks_and_through_close(isolated_import_runtime, monkeypatch, operation, pause_at):
    client, db, paper, target = isolated_import_runtime
    entered, release = Event(), Event()
    original = getattr(db, pause_at)
    def paused(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)
    monkeypatch.setattr(db, pause_at, paused)
    writes = []
    monkeypatch.setattr(ZoteroClient, "import_paper", lambda self, paper: writes.append(paper))
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(replace_database, client, operation, target)
        try:
            assert entered.wait(5)
            assert client.post(f"/api/papers/{paper['id']}/zotero").status_code == 409
            assert writes == []
        finally:
            release.set()
        assert future.result(timeout=5).status_code == 200
    assert api.database is not db
    assert api.database.get_paper(paper["id"]) is None
    assert not IMPORT_LOCK.locked()


@pytest.mark.parametrize("operation", ["directory", "restore"])
def test_replacement_releases_lock_on_validation_error(isolated_import_runtime, monkeypatch, operation, tmp_path):
    client, db, paper, _ = isolated_import_runtime
    invalid = tmp_path / "not-a-directory"
    invalid.write_text("invalid", encoding="utf-8")
    assert replace_database(client, operation, invalid).status_code == 400
    assert api.database is db
    assert not IMPORT_LOCK.locked()
    monkeypatch.setattr(ZoteroClient, "import_paper", lambda self, paper: {"status": "existing", "item_key": "ITEM0001", "error": ""})
    assert client.post(f"/api/papers/{paper['id']}/zotero").status_code == 200


def test_directory_noop_releases_lock(isolated_import_runtime):
    client, _, _, _ = isolated_import_runtime
    response = client.put("/api/system/data-directory", json={"path": str(api.settings.data_dir)})
    assert response.status_code == 200
    assert not IMPORT_LOCK.locked()
