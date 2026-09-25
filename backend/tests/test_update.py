import httpx
from fastapi.testclient import TestClient

from literature_agent.api import app


def test_private_release_is_not_reported_as_up_to_date(monkeypatch):
    def private_repo(*args, **kwargs):
        return httpx.Response(404, request=httpx.Request("GET", "https://api.github.com/"))

    monkeypatch.setattr("literature_agent.api.httpx.get", private_repo)
    with TestClient(app) as client:
        response = client.get("/api/update")
    assert response.status_code == 503
    assert "private" in response.json()["detail"].lower()


def test_public_release_reports_new_version(monkeypatch):
    def public_repo(*args, **kwargs):
        return httpx.Response(
            200,
            json={"tag_name": "v99.0.0", "html_url": "https://github.com/EdwardAiyw/literature-agent/releases/tag/v99.0.0"},
            request=httpx.Request("GET", "https://api.github.com/"),
        )

    monkeypatch.setattr("literature_agent.api.httpx.get", public_repo)
    with TestClient(app) as client:
        response = client.get("/api/update")
    assert response.status_code == 200
    assert response.json()["available"] is True
    assert response.json()["latest"] == "99.0.0"
