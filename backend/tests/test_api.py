from fastapi.testclient import TestClient

from literature_agent.api import app, database


def test_create_task_and_run():
    with TestClient(app) as client:
        task = client.post("/api/tasks", json={"name": "RAG test", "topic": "agentic retrieval", "target_count": 2}).json()
        assert task["topic"] == "agentic retrieval"
        run = client.post(f"/api/tasks/{task['id']}/runs")
        assert run.status_code == 202
        run_id = run.json()["id"]
        import time
        for _ in range(20):
            current = client.get(f"/api/runs/{run_id}").json()
            if current["status"] == "completed":
                break
            time.sleep(0.05)
        assert current["status"] == "completed"
        assert current["started_at"]
        assert current["progress"] == 6
        task_runs = client.get(f"/api/tasks/{task['id']}/runs?limit=1")
        assert task_runs.status_code == 200
        assert task_runs.json()[0]["id"] == run_id
        papers = client.get(f"/api/runs/{run_id}/papers").json()
        assert len(papers) == 2
        events = client.get(f"/api/runs/{run_id}/events").json()
        assert [event["node"] for event in events if event["status"] == "completed"] == [
            "query_planner", "retrieval", "dedupe", "relevance_screener", "literature_summarizer", "complete"
        ]
        artifacts = client.get(f"/api/runs/{run_id}/artifacts").json()
        assert any(artifact["node"] == "result_manifest" for artifact in artifacts)
        contract = next(artifact["payload"] for artifact in artifacts if artifact["node"] == "query_planner")
        assert contract["prompt_snapshot"]["query_planner"]["version"] == "v1"


def test_evidence_review_adds_runtime_node():
    with TestClient(app) as client:
        task = client.post("/api/tasks", json={"name": "Evidence test", "topic": "evidence review", "target_count": 2, "evidence_review": True}).json()
        run = client.post(f"/api/tasks/{task['id']}/runs").json()
        import time
        for _ in range(20):
            current = client.get(f"/api/runs/{run['id']}").json()
            if current["status"] == "completed":
                break
            time.sleep(0.05)
        assert current["total_steps"] == 7
        assert any(event["node"] == "evidence_reviewer" for event in client.get(f"/api/runs/{run['id']}/events").json())


def test_delete_task_cascades_owned_run_data_and_protects_subscriptions():
    with TestClient(app) as client:
        task = client.post("/api/tasks", json={"name": "Delete task", "topic": "cleanup", "target_count": 2}).json()
        run = database.create_run(task["id"], total_steps=6)
        database.add_paper(run["id"], "doi:task-delete", {"title": "Delete task paper", "relevance_score": 0.2})
        database.add_run_event(run["id"], "retrieval", "completed", "Delete task event")
        database.save_run_artifact(run["id"], "retrieval", {"sources": {}})
        database.update_run(run["id"], status="completed", finished_at="2026-09-22T00:00:00+00:00")

        deleted = client.delete(f"/api/tasks/{task['id']}")
        assert deleted.status_code == 200
        assert deleted.json() == {"status": "deleted", "task_id": task["id"]}
        assert client.get(f"/api/tasks/{task['id']}").status_code == 404
        assert database.get_run(run["id"]) is None
        assert database.list_papers(run["id"]) == []
        assert database.list_run_events(run["id"]) == []
        assert database.list_run_artifacts(run["id"]) == []
        assert client.delete(f"/api/tasks/{task['id']}").status_code == 404

        subscription = client.post("/api/subscriptions", json={
            "name": "Protected task",
            "topic": "cleanup",
            "target_count": 2,
            "recipient": "researcher@example.org",
            "schedule_time": "08:00",
            "sources": ["openalex"],
        }).json()
        blocked = client.delete(f"/api/tasks/{subscription['task_id']}")
        assert blocked.status_code == 409
        assert client.get(f"/api/tasks/{subscription['task_id']}").status_code == 200


def test_task_update_and_bulk_delete_guards():
    with TestClient(app) as client:
        first = client.post("/api/tasks", json={"name": "Editable", "topic": "old topic", "target_count": 2}).json()
        updated = client.patch(f"/api/tasks/{first['id']}", json={"name": "Edited", "topic": "new topic", "target_count": 4})
        assert updated.status_code == 200
        assert updated.json()["name"] == "Edited"
        assert updated.json()["topic"] == "new topic"

        active_run = database.create_run(first["id"], total_steps=6)
        blocked_update = client.patch(f"/api/tasks/{first['id']}", json={"name": "Blocked"})
        assert blocked_update.status_code == 409
        blocked_delete = client.delete(f"/api/tasks/{first['id']}")
        assert blocked_delete.status_code == 409
        database.update_run(active_run["id"], status="completed", finished_at="2026-09-22T00:00:00+00:00")

        second = client.post("/api/tasks", json={"name": "Second", "topic": "second", "target_count": 2}).json()
        subscription = client.post("/api/subscriptions", json={
            "name": "Protected",
            "topic": "protected",
            "target_count": 2,
            "recipient": "researcher@example.org",
            "schedule_time": "08:00",
            "sources": ["openalex"],
        }).json()
        blocked_batch = client.post("/api/tasks/bulk-delete", json={"task_ids": [second["id"], subscription["task_id"]]})
        assert blocked_batch.status_code == 409
        assert client.get(f"/api/tasks/{second['id']}").status_code == 200
        assert client.get(f"/api/tasks/{subscription['task_id']}").status_code == 200

        deleted = client.post("/api/tasks/bulk-delete", json={"task_ids": [first["id"], second["id"]]})
        assert deleted.status_code == 200
        assert deleted.json()["task_ids"] == [first["id"], second["id"]]
        assert client.get(f"/api/tasks/{first['id']}").status_code == 404
        assert client.get(f"/api/tasks/{second['id']}").status_code == 404
        assert client.post("/api/tasks/bulk-delete", json={"task_ids": [first["id"], first["id"]]}).status_code == 422


def test_prompt_catalog():
    with TestClient(app) as client:
        response = client.get("/api/prompts")
        assert response.status_code == 200
        assert any(item["id"] == "literature_summarizer.v1" for item in response.json())


def test_prompt_override_lifecycle_and_task_snapshot():
    with TestClient(app) as client:
        builtin = next(item for item in client.get("/api/prompts").json() if item["id"] == "query_planner.v1")
        created = client.post("/api/prompts", json={"role": "query_planner", "parent_id": builtin["id"], "body": "Custom planner instructions."})
        assert created.status_code == 201
        override = created.json()
        assert override["builtin"] is False
        assert override["active"] is True

        prompts = client.get("/api/prompts").json()
        assert next(item for item in prompts if item["id"] == override["id"])["active"] is True
        assert next(item for item in prompts if item["id"] == builtin["id"])["active"] is False

        task = client.post("/api/tasks", json={
            "name": "Prompt override test",
            "topic": "runtime prompts",
            "target_count": 2,
            "prompt_overrides": {"query_planner": override["id"]},
        })
        assert task.status_code == 200
        run = client.post(f"/api/tasks/{task.json()['id']}/runs")
        assert run.status_code == 202
        import time
        for _ in range(20):
            current = client.get(f"/api/runs/{run.json()['id']}").json()
            if current["status"] == "completed":
                break
            time.sleep(0.05)
        contract = next(item["payload"] for item in client.get(f"/api/runs/{run.json()['id']}/artifacts").json() if item["node"] == "query_planner")
        assert contract["prompt_snapshot"]["query_planner"]["id"] == override["id"]
        assert contract["prompt_snapshot"]["query_planner"]["body"] == "Custom planner instructions."

        assert client.post(f"/api/prompts/{builtin['id']}/activate").status_code == 200
        assert client.delete(f"/api/prompts/{override['id']}").status_code == 200
        assert client.delete(f"/api/prompts/{builtin['id']}").status_code == 409


def test_task_source_validation_and_settings_catalog():
    with TestClient(app) as client:
        invalid = client.post("/api/tasks", json={"name": "Invalid source", "topic": "topic", "sources": ["cnki"]})
        assert invalid.status_code == 422
        settings = client.get("/api/settings").json()
        assert {source["id"] for source in settings["sources"]} >= {"openalex", "crossref", "arxiv", "pubmed"}


def test_subscription_crud_and_delivery_history():
    with TestClient(app) as client:
        payload = {
            "name": "Daily RAG",
            "topic": "agentic retrieval",
            "target_count": 10,
            "recipient": "researcher@example.org",
            "schedule_time": "08:00",
            "sources": ["openalex", "pubmed"],
        }
        created = client.post("/api/subscriptions", json=payload)
        assert created.status_code == 201
        subscription = created.json()
        assert subscription["sources"] == ["openalex", "pubmed"]
        assert subscription["task_id"]
        updated = client.patch(f"/api/subscriptions/{subscription['id']}", json={"target_count": 12, "enabled": False})
        assert updated.status_code == 200
        assert updated.json()["target_count"] == 12
        assert updated.json()["enabled"] is False
        task = client.get(f"/api/tasks/{subscription['task_id']}").json()
        assert task["target_count"] == 12
        assert task["sources"] == ["openalex", "pubmed"]
        assert client.get("/api/deliveries").status_code == 200

        run = database.create_run(subscription["task_id"], total_steps=6)
        database.add_paper(run["id"], "doi:delete-smoke", {"title": "Delete smoke", "relevance_score": 0.1})
        database.add_run_event(run["id"], "retrieval", "completed", "Delete smoke event")
        database.save_run_artifact(run["id"], "retrieval", {"sources": {}})
        database.create_delivery(subscription["id"], run["id"], "digest", subscription["recipient"], "Delete smoke")

        deleted = client.delete(f"/api/subscriptions/{subscription['id']}")
        assert deleted.status_code == 200
        assert deleted.json() == {"status": "deleted", "subscription_id": subscription["id"]}
        assert client.get(f"/api/subscriptions/{subscription['id']}").status_code == 404
        assert client.get(f"/api/tasks/{subscription['task_id']}").status_code == 404
        assert database.get_run(run["id"]) is None
        assert database.list_papers(run["id"]) == []
        assert database.list_run_events(run["id"]) == []
        assert database.list_run_artifacts(run["id"]) == []
        assert database.list_deliveries(subscription["id"]) == []
        assert client.delete(f"/api/subscriptions/{subscription['id']}").status_code == 404


def test_subscription_requires_schedule_recipient_and_source():
    with TestClient(app) as client:
        response = client.post("/api/subscriptions", json={"name": "Incomplete", "topic": "topic", "target_count": 10})
        assert response.status_code == 422


def test_subscription_rejects_invalid_calendar_values():
    with TestClient(app) as client:
        base = {
            "name": "Invalid schedule",
            "topic": "topic",
            "target_count": 10,
            "recipient": "researcher@example.org",
            "schedule_time": "08:00",
            "sources": ["openalex"],
        }
        assert client.post("/api/subscriptions", json={**base, "date_from": "2026-02-30"}).status_code == 422
        assert client.post("/api/subscriptions", json={**base, "timezone": "Mars/Olympus"}).status_code == 422
        assert client.post("/api/subscriptions", json={**base, "recipient": "not-an-email"}).status_code == 422
