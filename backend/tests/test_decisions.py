from typesafe_sdk import SystemOneResponse
from literature_agent.config import Settings
from literature_agent.db import Database
from literature_agent.decisions import JevDecisionProvider
import pytest


class FakeClient:
    def __init__(self, calls): self.calls = calls
    def __enter__(self): return self
    def __exit__(self, *_): return None
    def system_one(self, **kwargs):
        self.calls.append(kwargs)
        return SystemOneResponse.model_validate({"model": "jev-1.13.0", "usage": {"input_tokens": 10}, "answers": {
            "topic_fit": {"type": "score", "score": 2.8, "confidence": .94, "legend": {0:"n",1:"l",2:"u",3:"c"}, "probabilities": {0:0,1:.02,2:.16,3:.82}},
            "question_fit": {"type": "score", "score": 2.6, "confidence": .9, "legend": {0:"n",1:"l",2:"u",3:"c"}, "probabilities": {0:0,1:.05,2:.3,3:.65}},
            "evidence": {"type": "score", "score": 2.2, "confidence": .86, "legend": {0:"n",1:"l",2:"u",3:"c"}, "probabilities": {0:0,1:.1,2:.6,3:.3}},
            "study_type": {"type": "choice", "choice": "method", "confidence": .93,
                           "probabilities": {"empirical":.03,"review":.01,"method":.92,"dataset":.02,"opinion":.01,"other":.01}},
            "directly_useful": {"type": "noul", "noul": .94}}})


def test_jev_screening_is_cached_and_audited(tmp_path):
    database = Database(tmp_path / "jev.db"); calls = []
    settings = Settings(root=tmp_path, db_path=tmp_path / "jev.db", jev_enabled=True,
                        jev_provider="typesafe_cloud", jev_base_url="",
                        jev_shadow_mode=False, jev_api_key="test", jev_auto_threshold=.8)
    provider = JevDecisionProvider(settings, database, client_factory=lambda: FakeClient(calls))
    record = {"canonical_id":"paper-1", "title":"Agentic retrieval", "abstract":"We evaluate an agent.", "source":"semantic_scholar"}
    task = {"topic":"agentic retrieval", "research_questions":["Does it improve recall?"]}
    assert provider.screen_paper("run-1", record, task)["auto_eligible"] is True
    provider.screen_paper("run-1", record, task)
    audit = database.list_decision_calls("run-1")
    assert len(calls) == 1 and len(audit) == 2 and audit[1]["cached"] is True
    assert audit[0]["status"] == "applied"
    database.close()


def test_decision_audit_order_follows_insertion_when_timestamps_match(tmp_path):
    database = Database(tmp_path / "audit-order.db")
    base = {
        "run_id": "run-order",
        "stage": "relevance_screener",
        "subject_id": "paper-1",
        "mode": "active",
        "status": "applied",
        "requested_model": "jev-1.13.0",
        "schema_version": "paper-screen.v1",
        "created_at": "2026-09-25T00:00:00+00:00",
    }
    database.add_decision_call({**base, "id": "z-first", "cached": False})
    database.add_decision_call({**base, "id": "a-second", "cached": True})

    audit = database.list_decision_calls("run-order")

    assert [item["id"] for item in audit] == ["z-first", "a-second"]
    assert audit[1]["cached"] is True
    database.close()


def test_shadow_decision_is_observed_without_counting_as_fallback(tmp_path):
    path = tmp_path / "shadow.db"
    database = Database(path)
    settings = Settings(root=tmp_path, db_path=path, jev_enabled=True, jev_shadow_mode=True,
                        jev_provider="typesafe_cloud", jev_base_url="",
                        jev_api_key="test", jev_auto_threshold=.8)
    provider = JevDecisionProvider(settings, database, client_factory=lambda: FakeClient([]))
    provider.screen_paper("run-shadow", {"canonical_id": "paper-1", "title": "Paper"}, {"topic": "topic"})
    audit = database.list_decision_calls("run-shadow")[0]
    assert audit["status"] == "shadow_observed"
    assert audit["fallback_used"] is False
    assert audit["fallback_reason"] == ""
    database.close()


def test_active_low_confidence_is_audited_as_fallback(tmp_path):
    path = tmp_path / "low-confidence.db"
    database = Database(path)
    settings = Settings(root=tmp_path, db_path=path, jev_enabled=True, jev_shadow_mode=False,
                        jev_provider="typesafe_cloud", jev_base_url="",
                        jev_api_key="test", jev_auto_threshold=1.0)
    provider = JevDecisionProvider(settings, database, client_factory=lambda: FakeClient([]))
    provider.screen_paper("run-low", {"canonical_id": "paper-1", "title": "Paper"}, {"topic": "topic"})
    audit = database.list_decision_calls("run-low")[0]
    assert audit["status"] == "fallback"
    assert audit["fallback_used"] is True
    assert audit["fallback_reason"] == "low_confidence"
    database.close()


@pytest.mark.parametrize("shadow_mode", [True, False])
def test_jev_failure_is_audited_without_claiming_application(tmp_path, shadow_mode):
    class BrokenClient(FakeClient):
        def system_one(self, **kwargs):
            raise TimeoutError("provider timeout")

    path = tmp_path / f"failure-{shadow_mode}.db"
    database = Database(path)
    settings = Settings(root=tmp_path, db_path=path, jev_enabled=True, jev_shadow_mode=shadow_mode,
                        jev_provider="typesafe_cloud", jev_base_url="", jev_api_key="test")
    provider = JevDecisionProvider(settings, database, client_factory=lambda: BrokenClient([]))
    with pytest.raises(TimeoutError):
        provider.screen_paper("run-failed", {"canonical_id": "paper-1", "title": "Paper"}, {"topic": "topic"})
    audit = database.list_decision_calls("run-failed")[0]
    assert audit["status"] == "failed"
    assert audit["fallback_reason"] == "jev_error"
    assert audit["fallback_used"] is (not shadow_mode)
    assert "TimeoutError" in audit["error"]
    database.close()


def test_localjev_normalizes_probabilities_and_routes_to_review(tmp_path, monkeypatch):
    path = tmp_path / "localjev.db"
    database = Database(path)
    settings = Settings(root=tmp_path, db_path=path, jev_enabled=True, jev_shadow_mode=False,
                        jev_provider="localjev", jev_base_url="http://127.0.0.1:8080/v1",
                        jev_auto_threshold=.95, jev_review_threshold=.5)
    provider = JevDecisionProvider(settings, database)
    payload = {
        "model": "local-model",
        "usage": {"input_tokens": 7},
        "answers": {
            "topic_fit": {"score": 2.7, "confidence": .8, "probabilities": {"0": 0, "1": .1, "2": .3, "3": .6}},
            "question_fit": {"score": 2.5, "confidence": .8, "probabilities": {"0": 0, "1": .1, "2": .4, "3": .5}},
            "evidence": {"score": 2.4, "confidence": .8, "probabilities": {"0": 0, "1": .1, "2": .5, "3": .4}},
            "study_type": {"choice": "method", "confidence": .8, "probabilities": {"empirical": .1, "review": .1, "method": .5, "dataset": .1, "opinion": .1, "other": .1}},
            "directly_useful": {"noul": .9},
        },
    }
    monkeypatch.setattr(provider, "_http_system_one", lambda *_: payload)

    result = provider.screen_paper("run-local", {"canonical_id": "paper-1", "title": "Paper"}, {"topic": "topic"})
    audit = database.list_decision_calls("run-local")[0]

    assert result["route"] == "needs_review"
    assert audit["provider"] == "localjev"
    assert audit["probability_kind"] == "self_reported"
    assert audit["routing"] == "needs_review"
    assert sum(audit["probabilities"]["topic_fit"].values()) == pytest.approx(1)
    assert provider.base_url == "http://127.0.0.1:8080"
    database.close()


def test_custom_provider_requires_base_url(tmp_path):
    settings = Settings(root=tmp_path, db_path=tmp_path / "custom.db", jev_enabled=True,
                        jev_provider="custom", jev_base_url="")
    database = Database(settings.db_path)
    assert JevDecisionProvider(settings, database).configured is False
    database.close()


def test_http_provider_retries_invalid_answer_shape_and_audits_validation_error(tmp_path, monkeypatch):
    path = tmp_path / "invalid-answer.db"
    database = Database(path)
    settings = Settings(root=tmp_path, db_path=path, jev_enabled=True, jev_shadow_mode=False,
                        jev_provider="localjev", jev_base_url="http://127.0.0.1:8000")
    provider = JevDecisionProvider(settings, database)
    calls = []
    invalid = {"answers": {"topic_fit": {"score": 4.5, "confidence": .8},
                           "question_fit": {"score": 2, "confidence": .8},
                           "evidence": {"score": 2, "confidence": .8},
                           "study_type": {"choice": "method", "confidence": .8},
                           "directly_useful": {"noul": .9}}}
    monkeypatch.setattr(provider, "_http_system_one", lambda *_: calls.append(1) or invalid)

    with pytest.raises(ValueError, match="invalid score"):
        provider.screen_paper("run-invalid", {"canonical_id": "paper-1", "title": "Paper"}, {"topic": "topic"})

    audit = database.list_decision_calls("run-invalid")[0]
    assert len(calls) == 2
    assert audit["attempt_count"] == 2
    assert "invalid score" in audit["validation_error"]
    database.close()


def test_localjev_connection_status_checks_health_ready_and_models(tmp_path, monkeypatch):
    path = tmp_path / "localjev-status.db"
    database = Database(path)
    settings = Settings(root=tmp_path, db_path=path, jev_enabled=True,
                        jev_provider="localjev", jev_base_url="http://127.0.0.1:8080",
                        jev_model="jev-latest")
    provider = JevDecisionProvider(settings, database)
    calls = []
    responses = {
        "/health": {"status": "ok"},
        "/ready": {"status": "ready", "upstream_model": "diffusiongemma-26B-A4B-it-4bit"},
        "/v1/models": {"models": [{"name": "localjev-latest"}, {"name": "localjev-0.2"}]},
    }
    monkeypatch.setattr(provider, "_get_json", lambda path, **kwargs: calls.append((path, kwargs)) or responses[path])

    status = provider.connection_status()

    assert status["status"] == "ready"
    assert status["service"] == "LocalJev"
    assert status["upstream_model"] == "diffusiongemma-26B-A4B-it-4bit"
    assert [path for path, _ in calls] == ["/health", "/ready", "/v1/models"]
    assert calls[-1][1]["authenticated"] is True
    database.close()


def test_localjev_connection_status_reports_unavailable_upstream(tmp_path, monkeypatch):
    path = tmp_path / "localjev-unavailable.db"
    database = Database(path)
    settings = Settings(root=tmp_path, db_path=path, jev_enabled=True,
                        jev_provider="localjev", jev_base_url="http://127.0.0.1:8080")
    provider = JevDecisionProvider(settings, database)
    monkeypatch.setattr(provider, "_get_json", lambda path, **_: {"status": "ok"} if path == "/health" else {"status": "unavailable", "detail": "upstream model is not loaded"})

    status = provider.connection_status()

    assert status["status"] == "unavailable"
    assert "upstream model is not loaded" in status["detail"]
    database.close()
