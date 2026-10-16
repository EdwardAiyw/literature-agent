import pytest
from threading import Barrier, Lock

from literature_agent import graph as graph_module
from literature_agent import runner as runner_module
from literature_agent.config import Settings
from literature_agent.db import Database
from literature_agent.graph import select_diverse_records
from literature_agent.llm import ModelProvider, fallback_query_plan
from literature_agent.prompts import BUILTIN_PROMPTS
from literature_agent.runner import execute_run
from literature_agent.schemas import TaskCreate


def paper(title: str, source: str, score: float) -> dict:
    return {"title": title, "source": source, "relevance_score": score}


def test_selection_includes_a_second_qualified_source():
    records = [
        paper("A1", "crossref", 0.95),
        paper("A2", "crossref", 0.94),
        paper("A3", "crossref", 0.93),
        paper("A4", "crossref", 0.92),
        paper("A5", "crossref", 0.91),
        paper("B1", "arxiv", 0.80),
    ]
    selected, diagnostic = select_diverse_records(records, 5)
    assert len(selected) == 5
    assert {item["source"] for item in selected} == {"crossref", "arxiv"}
    assert diagnostic["diversity_required"] is True
    assert diagnostic["diversity_satisfied"] is True
    assert diagnostic["selected_source_counts"] == {"crossref": 4, "arxiv": 1}


def test_selection_does_not_force_a_low_relevance_source():
    records = [paper("A1", "crossref", 0.95), paper("A2", "crossref", 0.90), paper("B1", "arxiv", 0.54)]
    selected, diagnostic = select_diverse_records(records, 2)
    assert [item["title"] for item in selected] == ["A1", "A2"]
    assert diagnostic["diversity_required"] is False
    assert "Fewer than two sources" in diagnostic["diversity_reason"]


def test_selection_does_not_fill_requested_count_with_unrelated_papers():
    records = [paper("Relevant RAG method", "arxiv", .85),
               paper("Generative ontology", "openalex", .05),
               paper("Philosophical fiction", "openalex", .03),
               paper("Literary commentary", "openalex", .02)]
    selected, diagnostic = select_diverse_records(records, 50)
    assert [item["title"] for item in selected] == ["Relevant RAG method"]
    assert diagnostic["evaluated_count"] == 4
    assert diagnostic["qualified_count"] == diagnostic["selected_count"] == 1
    assert diagnostic["rejected_count"] == 3
    assert {item["reason"] for item in diagnostic["rejected"]} == {"below_relevance_threshold"}


def test_selection_accepts_background_boundary_but_respects_ignore():
    records = [paper("Background", "arxiv", .4), paper("Peripheral", "openalex", .399),
               {**paper("Explicitly ignored", "crossref", .9), "screening": {"recommended_action": "ignore"}}]
    selected, diagnostic = select_diverse_records(records, 10)
    assert [item["title"] for item in selected] == ["Background"]
    assert diagnostic["rejected_count"] == 2


@pytest.mark.parametrize("score,action", [(.05, "ignore"), (.85, "read")])
def test_live_graph_rejects_irrelevant_or_unverified_candidates_before_summarizing(tmp_path, monkeypatch, score, action):
    database = Database(tmp_path / "relevance.db")
    database.seed_builtin_prompts(BUILTIN_PROMPTS)
    task = database.create_task(TaskCreate(name="Regression", topic="agentic retrieval", target_count=50,
                                         sources=["openalex"]).model_dump())
    run = database.create_run(task["id"], total_steps=6)
    monkeypatch.setattr(ModelProvider, "plan_queries", lambda *_: fallback_query_plan(task))
    monkeypatch.setattr(graph_module, "search_sources", lambda *_args, **_kwargs: (
        [{"title": "Generative ontology", "source": "openalex", "source_id": "W1", "abstract": "A philosophical essay."}],
        {"openalex": {"status": "ok", "count": 1, "error": ""}},
    ))
    monkeypatch.setattr(ModelProvider, "screen", lambda *_: {
        "relevance_score": score, "priority": "P2", "recommended_action": action,
        "relevance_reason": "Not research on the task.", "engine": "test-model" if score < .4 else "fallback",
    })
    def unexpected_summary(*_args, **_kwargs):
        pytest.fail("Rejected candidates must not consume summary requests")
    monkeypatch.setattr(ModelProvider, "summarize", unexpected_summary)
    result = execute_run(Settings(root=tmp_path, live=True), database, run["id"], task)
    assert result["status"] == "completed"
    assert result["paper_count"] == 0
    assert database.list_papers(run["id"]) == []
    screening = database.get_run_artifact(run["id"], "relevance_screener")["payload"]
    assert screening["evaluated_count"] == screening["rejected_count"] == 1
    assert screening["selected_count"] == 0
    database.close()


def test_empty_live_retrieval_never_creates_fixture_papers(tmp_path, monkeypatch):
    database = Database(tmp_path / "empty.db")
    database.seed_builtin_prompts(BUILTIN_PROMPTS)
    task = database.create_task(TaskCreate(name="Empty", topic="agentic retrieval", sources=["crossref"]).model_dump())
    run = database.create_run(task["id"], total_steps=6)
    monkeypatch.setattr(ModelProvider, "plan_queries", lambda *_: fallback_query_plan(task))
    monkeypatch.setattr(graph_module, "search_sources", lambda *_args, **_kwargs: (
        [], {"crossref": {"status": "failed", "count": 0, "error": "HTTP 429"}},
    ))
    result = execute_run(Settings(root=tmp_path, live=True), database, run["id"], task)
    assert result["status"] == "completed"
    assert database.list_papers(run["id"]) == []
    retrieval = database.get_run_artifact(run["id"], "retrieval")["payload"]
    assert retrieval["source_mode"] == "live"
    assert "fixture" not in retrieval["sources"]
    database.close()


def test_invalid_live_plan_fails_before_retrieving(tmp_path, monkeypatch):
    database = Database(tmp_path / "invalid-plan.db")
    database.seed_builtin_prompts(BUILTIN_PROMPTS)
    task = database.create_task(TaskCreate(name="Invalid plan", topic="agentic retrieval").model_dump())
    run = database.create_run(task["id"], total_steps=6)
    def invalid_plan(*_):
        raise ValueError("Bilingual search requires separate Chinese and English queries")
    monkeypatch.setattr(ModelProvider, "plan_queries", invalid_plan)
    monkeypatch.setattr(graph_module, "search_sources", lambda *_args, **_kwargs: pytest.fail("Invalid plans must not be searched"))
    result = execute_run(Settings(root=tmp_path, live=True), database, run["id"], task)
    assert result["status"] == "failed"
    assert "Bilingual" in result["error"]
    assert database.get_run_artifact(run["id"], "retrieval") is None
    database.close()


@pytest.mark.parametrize("shadow", [False, True])
def test_relevance_gate_uses_final_jev_routing(tmp_path, monkeypatch, shadow):
    database = Database(tmp_path / "jev-relevance.db")
    database.seed_builtin_prompts(BUILTIN_PROMPTS)
    task = database.create_task(TaskCreate(name="Jev relevance", topic="agentic retrieval", sources=["openalex"]).model_dump())
    run = database.create_run(task["id"], total_steps=6)
    class FakeDecisions:
        configured = True
        provider = "test-jev"
        probability_kind = "self_reported"
        def __init__(self, *_):
            self.mode = "shadow" if shadow else "active"
        def screen_paper(self, *_):
            return {"relevance_score": .05, "priority": "P2", "recommended_action": "ignore",
                    "relevance_reason": "Unrelated", "engine": "test-jev", "route": "auto_apply",
                    "auto_eligible": True, "decision_confidence": .95}
    monkeypatch.setattr(graph_module, "JevDecisionProvider", FakeDecisions)
    monkeypatch.setattr(ModelProvider, "plan_queries", lambda *_: fallback_query_plan(task))
    monkeypatch.setattr(graph_module, "search_sources", lambda *_args, **_kwargs: (
        [{"title": "A candidate", "source": "openalex", "source_id": "W1", "abstract": "An abstract."}],
        {"openalex": {"status": "ok", "count": 1, "error": ""}},
    ))
    monkeypatch.setattr(ModelProvider, "screen", lambda *_: {
        "relevance_score": .85, "priority": "P0", "recommended_action": "read",
        "relevance_reason": "Relevant", "engine": "baseline",
    })
    result = execute_run(Settings(root=tmp_path, live=True, jev_shadow_mode=shadow), database, run["id"], task)
    assert result["status"] == "completed"
    assert result["paper_count"] == int(shadow)
    if shadow:
        assert database.list_papers(run["id"])[0]["screening"]["engine"] == "baseline"
    database.close()


def test_subscription_digest_does_not_recommend_rejected_papers(tmp_path, monkeypatch):
    database = Database(tmp_path / "digest-relevance.db")
    database.seed_builtin_prompts(BUILTIN_PROMPTS)
    task = database.create_task(TaskCreate(name="Digest relevance", topic="agentic retrieval", sources=["openalex"]).model_dump())
    subscription = database.create_subscription(task["id"], {
        "name": "Digest relevance", "topic": task["topic"], "recipient": "researcher@example.org",
        "schedule_time": "08:00", "timezone": "Asia/Hong_Kong", "target_count": 10,
        "sources": ["openalex"], "enabled": True,
    })
    monkeypatch.setattr(ModelProvider, "plan_queries", lambda *_: fallback_query_plan(task))
    monkeypatch.setattr(graph_module, "search_sources", lambda *_args, **_kwargs: (
        [{"title": "Unrelated fiction", "source": "openalex", "source_id": "W1", "abstract": "A novel."}],
        {"openalex": {"status": "ok", "count": 1, "error": ""}},
    ))
    monkeypatch.setattr(ModelProvider, "screen", lambda *_: {
        "relevance_score": .02, "priority": "P2", "recommended_action": "ignore",
        "relevance_reason": "Not related", "engine": "test-model",
    })
    messages = []
    monkeypatch.setattr(runner_module, "send_message", lambda _settings, _recipient, message: messages.append(message))
    result = runner_module.run_subscription(Settings(root=tmp_path, live=True, llm_api_key="fake", llm_model="fake"),
                                            database, subscription)
    assert result["paper_count"] == 0
    assert result["delivery"]["status"] == "sent"
    assert len(messages) == 1
    assert "Unrelated fiction" not in messages[0].text + messages[0].html
    assert "没有找到符合相关性要求" in messages[0].text
    assert "没有找到符合相关性要求" in messages[0].html
    database.close()


@pytest.mark.parametrize("shadow", [False, True])
def test_screening_bounds_workers_skips_only_active_auto_and_reports_progress(tmp_path, monkeypatch, shadow):
    database = Database(tmp_path / "bounded.db")
    database.seed_builtin_prompts(BUILTIN_PROMPTS)
    task = database.create_task(TaskCreate(name="Bounded", topic="Topic", sources=["fixture"],
                                          target_count=24, evidence_review=False).model_dump())
    run = database.create_run(task["id"], total_steps=6)
    records = [{"title": f"Paper {i}", "source": "fixture", "source_id": str(i)} for i in range(24)]
    monkeypatch.setattr(graph_module, "fixture_records", lambda _: records)
    barrier, lock = Barrier(2), Lock()
    counters = {"inflight": 0, "peak": 0, "baseline": 0}
    saved_titles = []
    add_paper = database.add_paper
    def save_paper(run_id, canonical_id, record):
        saved_titles.append(record["title"])
        return add_paper(run_id, canonical_id, record)
    monkeypatch.setattr(database, "add_paper", save_paper)
    class Decisions:
        configured = True
        provider = "test"
        probability_kind = "self_reported"
        mode = "shadow" if shadow else "active"
        def __init__(self, *_): pass
        def screen_paper(self, _run, record, actual_task, prompt):
            assert actual_task == task and prompt
            with lock:
                counters["inflight"] += 1
                counters["peak"] = max(counters["peak"], counters["inflight"])
            try:
                i = int(record["source_id"])
                if i < 2: barrier.wait(timeout=5)
                database.add_decision_call({"run_id": _run, "stage": "relevance_screener",
                    "subject_id": record["canonical_id"], "mode": self.mode, "status": "applied",
                    "requested_model": "test", "schema_version": "test"})
                if i % 3 == 2: raise TimeoutError("Jev unavailable")
                return {"relevance_score": .6, "priority": "P1", "recommended_action": "background",
                        "relevance_reason": "Task fit", "engine": "jev-test", "decision_confidence": .95 if i % 3 == 0 else .6,
                        "auto_eligible": i % 3 == 0, "route": "auto_apply" if i % 3 == 0 else "needs_review"}
            finally:
                with lock: counters["inflight"] -= 1
    monkeypatch.setattr(graph_module, "JevDecisionProvider", Decisions)
    def baseline(*_):
        with lock: counters["baseline"] += 1
        return {"relevance_score": .6, "priority": "P1", "recommended_action": "background",
                "relevance_reason": "Ordinary task fit", "engine": "ordinary"}
    monkeypatch.setattr(ModelProvider, "screen", baseline)
    result = execute_run(Settings(root=tmp_path, jev_shadow_mode=shadow, jev_max_inflight=2), database, run["id"], task)
    assert result["status"] == "completed", result
    assert counters["peak"] == 2, result
    assert counters["baseline"] == (24 if shadow else 16)
    assert saved_titles == [p["title"] for p in records]
    progress = database.get_run_artifact(run["id"], "screening_progress")["payload"]
    assert progress == {"processed": 24, "total": 24, "auto_applied": 0 if shadow else 8,
                        "baseline_calls": 24 if shadow else 16, "fallback_count": 0 if shadow else 16}
    audit = database.latest_decision_call(run["id"], "relevance_screener", "fixture:0")
    assert audit["baseline_outcome"] == (baseline() if shadow else {"skipped": True, "reason": "jev_auto_apply"})
    assert audit["fallback_used"] is False
    failure = database.latest_decision_call(run["id"], "relevance_screener", "fixture:2")
    assert failure["fallback_reason"] == "jev_error"
    database.close()
