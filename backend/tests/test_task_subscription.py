from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
import sqlite3
from threading import Barrier

from fastapi.testclient import TestClient
import pytest

from literature_agent import api
from literature_agent.daily import due_subscriptions
from literature_agent.db import Database
from literature_agent.prompts import BUILTIN_PROMPTS
from literature_agent.schemas import SubscriptionCreate, TaskCreate


SCHEDULE = {"recipient": "reader@example.org", "schedule_time": "08:00", "timezone": "Asia/Hong_Kong"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    database = Database(tmp_path / "conversion.db")
    database.seed_builtin_prompts(BUILTIN_PROMPTS)
    monkeypatch.setattr(api, "database", database)
    with TestClient(api.app) as client:
        yield client
    database.close()


def make_task(client):
    prompt = api.database.create_prompt_override("relevance_screener", "Use task-specific evidence only.")
    return client.post("/api/tasks", json={
        "name": "Research to daily", "topic": "Agentic RAG",
        "research_questions": ["How are retrieval tools selected?", "How is evidence checked?"],
        "language": "en", "output_language": "bilingual", "target_count": 17,
        "sources": ["openalex", "crossref"], "date_from": "2023-01-01", "date_to": "2026-10-15",
        "evidence_review": True, "prompt_overrides": {"relevance_screener": prompt["id"]},
    }).json()


def test_conversion_preserves_config_prompts_identity_and_history_without_execution(client):
    task = make_task(client)
    database = api.database
    run = database.create_run(task["id"], total_steps=7)
    database.update_run(run["id"], status="completed", progress=7)
    database.add_paper(run["id"], "doi:kept", {"title": "Kept result", "relevance_score": 0.9})
    database.add_run_event(run["id"], "complete", "completed", "Keep this event")
    database.save_run_artifact(run["id"], "query_planner", {"prompt_snapshot": {"version": "original"}})
    history = (database.get_run(run["id"]), database.list_papers(run["id"]), database.list_run_events(run["id"]), database.list_run_artifacts(run["id"]))
    prompts = database.list_prompts()

    response = client.post(f"/api/tasks/{task['id']}/subscription", json=SCHEDULE)
    assert response.status_code == 201
    subscription = response.json()
    assert subscription["task_id"] == task["id"]
    for key in TaskCreate.model_fields:
        if key != "origin":
            assert subscription[key] == task[key]
    assert {key: subscription[key] for key in SCHEDULE} == SCHEDULE
    assert subscription["enabled"] is True
    promoted = client.get(f"/api/tasks/{task['id']}").json()
    assert promoted["origin"] == "subscription"
    assert promoted["created_at"] == task["created_at"]
    assert len(database.list_tasks()) == len(database.list_subscriptions()) == 1
    assert history == (database.get_run(run["id"]), database.list_papers(run["id"]), database.list_run_events(run["id"]), database.list_run_artifacts(run["id"]))
    assert database.list_prompts() == prompts
    assert database.list_deliveries() == []
    assert len(database.list_runs(task["id"])) == 1


@pytest.mark.parametrize("schedule", [
    {}, {**SCHEDULE, "recipient": "invalid"}, {**SCHEDULE, "schedule_time": "25:00"},
    {**SCHEDULE, "timezone": "Mars/Olympus"}, {**SCHEDULE, "topic": "Cannot override research here"},
])
def test_conversion_rejects_invalid_schedule_without_writes(client, schedule):
    task = make_task(client)
    assert client.post(f"/api/tasks/{task['id']}/subscription", json=schedule).status_code == 422
    assert api.database.get_task(task["id"])["origin"] == "user"
    assert api.database.list_subscriptions() == []


def test_missing_and_duplicate_conversions_do_not_create_extra_tasks(client):
    assert client.post("/api/tasks/missing/subscription", json=SCHEDULE).status_code == 404
    task = make_task(client)
    created = client.post(f"/api/tasks/{task['id']}/subscription", json=SCHEDULE).json()
    duplicate = client.post(f"/api/tasks/{task['id']}/subscription", json={**SCHEDULE, "schedule_time": "09:00"})
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["subscription_id"] == created["id"]
    assert len(api.database.list_subscriptions()) == len(api.database.list_tasks()) == 1
    assert api.database.get_subscription(created["id"])["schedule_time"] == "08:00"


def test_conversion_during_running_task_keeps_run_and_blocks_deletion(client):
    task = make_task(client)
    run = api.database.create_run(task["id"], total_steps=7)
    api.database.update_run(run["id"], status="running", progress=3)
    response = client.post(f"/api/tasks/{task['id']}/subscription", json=SCHEDULE)
    assert response.status_code == 201
    subscription = response.json()
    assert api.database.get_run(run["id"])["status"] == "running"
    assert client.delete(f"/api/subscriptions/{subscription['id']}").status_code == 409
    assert api.database.get_run(run["id"])["progress"] == 3
    api.database.update_run(run["id"], status="completed")
    assert client.delete(f"/api/subscriptions/{subscription['id']}").status_code == 200


def test_manual_run_today_does_not_suppress_converted_daily_schedule(client):
    task = make_task(client)
    run = api.database.create_run(task["id"], total_steps=7)
    api.database.update_run(run["id"], status="completed", started_at="2026-10-15T00:10:00+00:00")
    subscription = client.post(f"/api/tasks/{task['id']}/subscription", json=SCHEDULE).json()
    now = datetime(2026, 10, 15, 1, 0, tzinfo=timezone.utc)
    assert due_subscriptions(api.database, [subscription], now) == [subscription]
    daily = api.database.create_run(task["id"], 7, trigger_kind="subscription", subscription_id=subscription["id"])
    api.database.update_run(daily["id"], status="completed", started_at="2026-10-15T00:30:00+00:00")
    assert due_subscriptions(api.database, [subscription], now) == []
    assert due_subscriptions(api.database, [subscription], datetime(2026, 10, 16, 1, 0, tzinfo=timezone.utc)) == [subscription]


def test_converted_subscription_queues_through_existing_worker_without_replaying_history(client, monkeypatch):
    task = make_task(client)
    manual = api.database.create_run(task["id"], total_steps=7)
    api.database.update_run(manual["id"], status="completed")
    subscription = client.post(f"/api/tasks/{task['id']}/subscription", json=SCHEDULE).json()
    submitted = []
    monkeypatch.setattr(api, "settings", replace(api.settings, live=True, llm_api_key="test-only", llm_model="test-only"))
    monkeypatch.setattr(api.run_worker, "submit_subscription", lambda run_id, value: submitted.append((run_id, value)))
    response = client.post(f"/api/subscriptions/{subscription['id']}/runs")
    assert response.status_code == 202
    run = response.json()
    assert run["task_id"] == task["id"]
    assert run["trigger_kind"] == "subscription"
    assert run["total_steps"] == 7
    assert submitted == [(run["id"], api.database.get_subscription(subscription["id"]))]
    assert client.post(f"/api/subscriptions/{subscription['id']}/runs").status_code == 409
    api.database.update_run(run["id"], status="completed")


def test_cross_connection_conversion_is_atomic_and_rejects_duplicates(tmp_path):
    path = tmp_path / "concurrent.db"
    first, second = Database(path), Database(path)
    task = first.create_task(TaskCreate(name="Atomic", topic="retrieval").model_dump())
    payload = SubscriptionCreate.model_validate({**task, **SCHEDULE}).model_dump()
    barrier = Barrier(2)
    def convert(database):
        barrier.wait(timeout=5)
        return database.subscribe_task(task["id"], task, payload)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(convert, [first, second]))
        assert sorted(item["status"] for item in results) == ["created", "subscribed"]
        assert len(first.list_tasks()) == len(first.list_subscriptions()) == 1
    finally:
        first.close()
        second.close()


def test_stale_conversion_and_failed_transaction_leave_task_unchanged(client):
    task = make_task(client)
    database = api.database
    payload = SubscriptionCreate.model_validate({**task, **SCHEDULE}).model_dump()
    updated = database.update_task(task["id"], {**TaskCreate.model_validate(task).model_dump(), "topic": "Changed"})
    assert database.subscribe_task(task["id"], task, payload)["status"] == "changed"
    assert database.list_subscriptions() == []
    database.connection.execute("CREATE TRIGGER reject_promotion BEFORE UPDATE ON tasks BEGIN SELECT RAISE(ABORT, 'promotion blocked'); END")
    database.connection.commit()
    with pytest.raises(sqlite3.IntegrityError, match="promotion blocked"):
        database.subscribe_task(task["id"], updated, SubscriptionCreate.model_validate({**updated, **SCHEDULE}).model_dump())
    assert database.get_task(task["id"]) == updated
    assert database.list_subscriptions() == []
    database.connection.execute("DROP TRIGGER reject_promotion")
    database.connection.commit()
    assert client.post(f"/api/tasks/{task['id']}/subscription", json=SCHEDULE).status_code == 201
