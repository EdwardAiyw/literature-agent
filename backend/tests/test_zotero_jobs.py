import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from literature_agent import api, runner, zotero_jobs
from literature_agent.config import Settings
from literature_agent.db import Database
from literature_agent.schemas import TaskCreate
from literature_agent.worker import LocalRunWorker
from literature_agent.zotero import IMPORT_LOCK, ZoteroClient, destination_for


@pytest.fixture
def setup(tmp_path):
    settings = Settings(root=tmp_path, data_dir=tmp_path, zotero_library_id="123", zotero_api_key="secret", zotero_collection_key="TARGET01")
    db = Database(tmp_path / "agent.db")
    task = db.create_task(TaskCreate(name="Study", topic="RAG", zotero_auto_import=True, zotero_collection_key="TARGET01").model_dump())
    run = db.create_run(task["id"], 6)
    db.update_run(run["id"], status="completed")
    for i in range(3):
        db.add_paper(run["id"], f"paper{i}", {"title": f"Study {i}", "doi": "10.1234/same" if i < 2 else "", "authors": [], "abstract": "", "published_date": "", "source": "crossref"})
    papers = db.list_papers(run["id"])
    db.review_paper(papers[2]["id"], "ignore")
    yield settings, db, task, run, papers
    db.close()


def transport(monkeypatch, lose_response=False):
    items, requests = {}, []
    lost = False
    real_client = httpx.Client
    def handler(request):
        nonlocal lost
        requests.append((request.method, request.url.path))
        path = request.url.path
        if path.endswith("/collections/TARGET01"):
            return httpx.Response(200, json={"key": "TARGET01"})
        if path.endswith("/items/top"):
            return httpx.Response(200, json=list(items.values()))
        if request.method == "POST":
            data = json.loads(request.content)[0]
            key = "ITEM0001"
            items[key] = {"key": key, "version": 1, "data": data}
            if lose_response and not lost:
                lost = True
                raise httpx.ReadTimeout("lost", request=request)
            return httpx.Response(200, json={"successful": {"0": items[key]}})
        if request.method == "GET" and "/items/" in path:
            return httpx.Response(200, json=items[path.rsplit("/", 1)[-1]])
        raise AssertionError(str(request.url))
    monkeypatch.setattr(zotero_jobs.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    return items, requests


def test_batch_shared_index_exact_membership_and_idempotent_enqueue(setup, monkeypatch):
    settings, db, task, run, papers = setup
    items, requests = transport(monkeypatch)
    dest = destination_for(settings)
    with ThreadPoolExecutor(4) as pool:
        batches = list(pool.map(lambda _: db.reserve_zotero_batch(run["id"], dest), range(8)))
    assert len({b["id"] for b in batches}) == 1
    assert len(db.list_zotero_batches()) == 1
    assert db.task_blockers(task["id"])["active_runs"] == [run["id"]]
    result = zotero_jobs.process_batch(settings, db, run["id"], batches[0]["id"])
    assert result["counts"] == {"imported": 1, "existing": 1, "failed": 0, "skipped": 1, "pending": 0}
    assert len([r for r in requests if r[0] == "POST"]) == 1
    assert len([r for r in requests if r[1].endswith("/items/top")]) == 1
    assert items["ITEM0001"]["data"]["collections"] == ["TARGET01"]
    assert db.get_run(run["id"])["status"] == "completed"
    assert db.list_deliveries() == []
    assert not db.task_blockers(task["id"])["active_runs"]


def test_lost_response_retry_rechecks_remote_without_duplicate_or_mail(setup, monkeypatch):
    settings, db, _, run, _ = setup
    items, requests = transport(monkeypatch, lose_response=True)
    batch = db.reserve_zotero_batch(run["id"], destination_for(settings))
    failed = zotero_jobs.process_batch(settings, db, run["id"], batch["id"])
    assert failed["status"] == "failed"
    assert len(items) == 1
    retry = db.reserve_zotero_batch(run["id"], batch["destination"], retry=True)
    result = zotero_jobs.process_batch(settings, db, run["id"], retry["id"])
    assert result["status"] == "completed"
    assert result["counts"]["existing"] == 2
    assert len([r for r in requests if r[0] == "POST"]) == 1
    assert db.list_deliveries() == []


def test_destination_snapshot_and_library_mismatch(setup, monkeypatch):
    settings, db, _, run, _ = setup
    _, requests = transport(monkeypatch)
    batch = db.reserve_zotero_batch(run["id"], destination_for(settings))
    changed = replace(settings, zotero_collection_key="OTHER001")
    assert zotero_jobs.process_batch(changed, db, run["id"], batch["id"])["status"] == "completed"
    assert all("OTHER001" not in path for _, path in requests)
    other = db.reserve_zotero_batch(run["id"], destination_for(changed))
    assert zotero_jobs.process_batch(replace(settings, zotero_library_id="456"), db, run["id"], other["id"])["status"] == "failed"
    assert not any("/456/" in path for _, path in requests)


def test_restart_recovers_post_completion_gap_and_pending_batch(setup, monkeypatch):
    settings, db, task, run, _ = setup
    transport(monkeypatch)
    zotero_jobs.remember_target(settings, db, run["id"], task)
    worker = LocalRunWorker(settings, db)
    try:
        assert worker.recover() == 1
    finally:
        worker.close()
    assert db.list_zotero_batches()[0]["status"] == "completed"
    second = db.reserve_zotero_batch(run["id"], destination_for(replace(settings, zotero_collection_key="OTHER001")))
    db.save_run_artifact(run["id"], second["id"], {**second, "status": "running"})
    monkeypatch.setattr("literature_agent.worker.process_batch", lambda *args: None)
    worker = LocalRunWorker(settings, db)
    try:
        assert worker.recover() == 1
    finally:
        worker.close()


def test_email_failure_does_not_block_import(setup, monkeypatch):
    settings, db, task, run, _ = setup
    transport(monkeypatch)
    settings = replace(settings, live=True, llm_api_key="key", llm_model="model")
    sub = db.create_subscription(task["id"], {**task, "recipient": "reader@example.org", "timezone": "Asia/Hong_Kong"})
    def execute(*args, **kwargs):
        zotero_jobs.remember_target(settings, db, run["id"], task)
        return db.get_run(run["id"])
    monkeypatch.setattr(runner, "execute_run", execute)
    def fail(*args): raise RuntimeError("SMTP failed")
    monkeypatch.setattr(runner, "send_message", fail)
    result = runner.run_subscription(settings, db, sub, run_id=run["id"])
    assert result["status"] == "completed"
    assert result["delivery"]["status"] == "failed"
    assert db.list_zotero_batches()[0]["status"] == "completed"


def test_api_target_preservation_download_and_pending_maintenance(setup, monkeypatch):
    settings, db, task, run, papers = setup
    monkeypatch.setattr(api, "settings", settings)
    monkeypatch.setattr(api, "database", db)
    monkeypatch.setattr(api, "run_worker", None)
    monkeypatch.setattr(ZoteroClient, "_collection", lambda _: "TARGET01")
    # No lifespan: this test inspects a queued batch before worker execution.
    with TestClient(api.app) as client:
        assert client.patch(f"/api/tasks/{task['id']}", json={"zotero_collection_key": ""}).status_code == 422
        subscription = client.post(f"/api/tasks/{task['id']}/subscription", json={"recipient": "reader@example.org", "schedule_time": "07:00"}).json()
        assert subscription["zotero_collection_key"] == "TARGET01"
        assert subscription["zotero_auto_import"] is True
        assert client.patch(f"/api/subscriptions/{subscription['id']}", json={"zotero_collection_key": ""}).status_code == 422
        content = client.get(f"/api/runs/{run['id']}/zotero-identifiers")
        assert content.text == "10.1234/same\n"
        assert content.headers["X-Missing-Identifier-Count"] == "0"
        db.save_zotero_import(papers[0]["id"], destination_for(settings), {"status": "existing", "error": ""})
        assert client.get(f"/api/runs/{run['id']}/papers").json()[0]["zotero"]["status"] == "existing"
        db.reserve_zotero_batch(run["id"], destination_for(settings))
        assert db.has_pending_zotero_batches()
        assert client.delete(f"/api/subscriptions/{subscription['id']}").status_code == 409
        with IMPORT_LOCK:
            assert client.post(f"/api/runs/{run['id']}/zotero-batches").status_code == 409


def test_enabled_import_requires_exact_key():
    assert TaskCreate(name="A", topic="B").zotero_auto_import is False
    with pytest.raises(ValidationError):
        TaskCreate(name="A", topic="B", zotero_auto_import=True)


def test_collection_listing_is_read_only_paginated_and_disambiguates_paths(tmp_path):
    starts = []
    def handler(request):
        assert request.method == "GET"
        start = int(request.url.params["start"])
        starts.append(start)
        rows = [{"key": "PARENT01", "data": {"name": "Research"}}] + [
            {"key": f"KEY{i:05d}", "data": {"name": "Daily Digest", "parentCollection": "PARENT01"}} for i in range(99)
        ] if start == 0 else [{"key": "OTHER001", "data": {"name": "Daily Digest"}}]
        return httpx.Response(200, json=rows, headers={"Total-Results": "101"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = ZoteroClient(Settings(root=tmp_path, zotero_library_id="123", zotero_api_key="secret"), client).list_collections()
    assert starts == [0, 100]
    assert {row["path"] for row in result} == {"Research", "Research / Daily Digest", "Daily Digest"}


def test_retry_preserves_successes_and_restart_resumes_only_pending(setup, monkeypatch):
    settings, db, _, run, papers = setup
    transport(monkeypatch)
    batch = db.reserve_zotero_batch(run["id"], destination_for(settings))
    # Simulate a shutdown after the first per-paper checkpoint.
    batch["results"][papers[0]["id"]] = {"status": "imported", "item_key": "PRIOR001", "error": ""}
    batch["status"] = "running"
    db.save_run_artifact(run["id"], batch["id"], batch)
    result = zotero_jobs.process_batch(settings, db, run["id"], batch["id"])
    assert result["results"][papers[0]["id"]]["item_key"] == "PRIOR001"
    assert result["counts"]["imported"] == 2
    assert result["counts"]["skipped"] == 1


def test_batch_existing_item_preserves_metadata_and_other_memberships(tmp_path):
    item = {"key": "EXIST001", "version": 3, "data": {"DOI": "10.1234/same", "title": "User title", "abstractNote": "User notes", "collections": ["OTHER001"]}}
    patches = []
    def handler(request):
        if request.url.path.endswith("/items/top"):
            return httpx.Response(200, json=[item])
        if request.method == "PATCH":
            assert request.headers["If-Unmodified-Since-Version"] == "3"
            patch = json.loads(request.content)
            patches.append(patch)
            item["data"].update(patch)
            item["version"] += 1
            return httpx.Response(204)
        assert request.method == "GET"
        return httpx.Response(200, json=item)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        zotero = ZoteroClient(Settings(root=tmp_path, zotero_library_id="123", zotero_api_key="secret", zotero_collection_key="TARGET01"), client)
        zotero.prepare_batch()
        assert zotero.import_paper({"title": "Provider title", "doi": "10.1234/same"})["status"] == "existing"
    assert patches == [{"collections": ["OTHER001", "TARGET01"]}]
    assert item["data"]["title"] == "User title"
    assert item["data"]["abstractNote"] == "User notes"
