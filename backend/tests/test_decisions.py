from typesafe_sdk import SystemOneResponse
from literature_agent.config import Settings
from literature_agent.db import Database
from literature_agent.decisions import JevDecisionProvider


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
    database.close()
