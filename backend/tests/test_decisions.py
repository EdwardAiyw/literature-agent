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
                        jev_api_key="test")
    provider = JevDecisionProvider(settings, database, client_factory=lambda: BrokenClient([]))
    with pytest.raises(TimeoutError):
        provider.screen_paper("run-failed", {"canonical_id": "paper-1", "title": "Paper"}, {"topic": "topic"})
    audit = database.list_decision_calls("run-failed")[0]
    assert audit["status"] == "failed"
    assert audit["fallback_reason"] == "jev_error"
    assert audit["fallback_used"] is (not shadow_mode)
    assert "TimeoutError" in audit["error"]
    database.close()
