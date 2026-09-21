from fastapi.testclient import TestClient

from literature_agent.api import app


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
        papers = client.get(f"/api/runs/{run_id}/papers").json()
        assert len(papers) == 2


def test_prompt_catalog():
    with TestClient(app) as client:
        response = client.get("/api/prompts")
        assert response.status_code == 200
        assert any(item["id"] == "literature_summarizer.v1" for item in response.json())
