from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from literature_agent import api
from literature_agent.db import Database
from literature_agent.prompts import BUILTIN_PROMPTS
from literature_agent.schemas import SubscriptionCreate, TaskCreate


def test_strict_mode_double_initialization_is_safe_during_writes(tmp_path, monkeypatch):
    isolated = Database(tmp_path / "concurrency.db")
    isolated.seed_builtin_prompts(BUILTIN_PROMPTS)
    task = isolated.create_task(
        TaskCreate(name="Concurrent regression", topic="SQLite shared connection", target_count=1).model_dump()
    )
    subscription_payload = SubscriptionCreate(
        name="Concurrent subscription",
        topic="SQLite shared connection",
        target_count=1,
        recipient="reader@example.org",
        schedule_time="08:00",
        sources=["openalex"],
    ).model_dump()
    subscription_task = isolated.create_task(
        TaskCreate(
            name=subscription_payload["name"],
            topic=subscription_payload["topic"],
            target_count=1,
            sources=["openalex"],
            origin="subscription",
        ).model_dump()
    )
    subscription = isolated.create_subscription(subscription_task["id"], subscription_payload)
    run = isolated.create_run(task["id"], total_steps=7)
    isolated.update_run(run["id"], status="completed", current_node="complete", progress=7, paper_count=1)
    isolated.add_run_event(run["id"], "complete", "completed", "Saved results")
    isolated.save_run_artifact(run["id"], "retrieval", {"sources": {"openalex": {"status": "success", "count": 1}}})
    isolated.add_paper(
        run["id"],
        "doi:concurrency-regression",
        {
            "title": "Concurrent SQLite regression",
            "authors": ["Test Author"],
            "abstract": "Regression fixture.",
            "published_date": "2026-09-24",
            "source": "openalex",
            "doi": "10.0000/concurrency",
            "official_url": "https://example.org/paper",
            "relevance_score": 1.0,
        },
    )
    isolated.create_delivery(
        subscription["id"], run["id"], "digest", subscription["recipient"], "Concurrent digest", "sent"
    )
    monkeypatch.setattr(api, "database", isolated)
    monkeypatch.setattr(api, "scheduler_status", lambda: {"supported": True, "tasks": []})

    paths = (
        "/api/tasks",
        "/api/subscriptions",
        "/api/deliveries",
        "/api/prompts",
        "/api/settings",
        "/api/onboarding",
        f"/api/tasks/{task['id']}/runs?limit=1",
        f"/api/runs/{run['id']}",
        f"/api/runs/{run['id']}/events",
        f"/api/runs/{run['id']}/artifacts",
        f"/api/runs/{run['id']}/papers",
    )

    def bootstrap(client: TestClient) -> list[tuple[str, int]]:
        return [(path, client.get(path).status_code) for path in paths]

    def write_while_reading() -> None:
        for progress in range(200):
            isolated.update_run(run["id"], progress=progress % 8)
            isolated.save_run_artifact(run["id"], "writer", {"progress": progress})

    try:
        with TestClient(api.app) as client, ThreadPoolExecutor(max_workers=24) as pool:
            writer = pool.submit(write_while_reading)
            # React StrictMode mounts twice: 100 cycles therefore produce 200 full bootstraps.
            futures = [pool.submit(bootstrap, client) for _ in range(200)]
            failures = [result for future in futures for result in future.result() if result[1] != 200]
            writer.result()
        assert failures == []
    finally:
        isolated.close()
