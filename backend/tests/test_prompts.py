import json
from pathlib import Path

import httpx
import pytest

from literature_agent import graph as graph_module
from literature_agent import prompts as prompt_module
from literature_agent.config import Settings
from literature_agent.db import Database
from literature_agent.llm import ModelProvider, fallback
from literature_agent.prompts import BUILTIN_PROMPTS, V1_PROMPTS, V2_PROMPTS
from literature_agent.schemas import TaskCreate


def release_catalog(version):
    values = V1_PROMPTS + (V2_PROMPTS if version == "v2" else [])
    return [{**prompt, "default": prompt["version"] == version} for prompt in values]


@pytest.fixture
def database(tmp_path):
    instance = Database(tmp_path / "prompts.db")
    yield instance
    instance.close()


def test_release_upgrade_preserves_overrides_custom_versions_and_snapshot(database, monkeypatch):
    database.seed_builtin_prompts(release_catalog("v1"))
    old = database.get_prompt("query_planner.v1")
    snapshot = {"id": old["id"], "body": old["body"], "version": old["version"]}
    database.save_run_artifact("historic-run", "query_planner", {"prompt_snapshot": snapshot})
    custom = database.create_prompt_override("relevance_screener", "User instructions", "relevance_screener.v1")
    database.seed_builtin_prompts(release_catalog("v2"))

    resolved = {prompt["role"]: prompt for prompt in database.resolve_prompts({})}
    assert resolved["query_planner"]["id"] == "query_planner.v2"
    assert resolved["relevance_screener"]["id"] == custom["id"]
    assert database.get_prompt("query_planner.v1") == {**old, "active": False}
    pinned = database.resolve_prompts({"prompt_overrides": {"query_planner": "query_planner.v1"}})
    assert pinned[0]["id"] == "query_planner.v1"
    assert database.get_run_artifact("historic-run", "query_planner")["payload"]["prompt_snapshot"] == snapshot

    monkeypatch.setattr(prompt_module, "DEFAULT_PROMPT_VERSION", "v2")
    database.delete_prompt_override(custom["id"])
    assert database.get_prompt("relevance_screener.v2")["active"] is True


def test_fresh_defaults_and_explicit_rollback_survive_restart(database):
    catalog = release_catalog("v2")
    database.seed_builtin_prompts(catalog)
    assert all(prompt["version"] == "v2" for prompt in database.resolve_prompts({}))
    database.activate_prompt("query_planner.v1")
    database.seed_builtin_prompts(catalog)
    assert database.resolve_prompts({})[0]["id"] == "query_planner.v1"
    # Published IDs are immutable even if a later catalog accidentally edits them.
    changed = [{**prompt, "body": "accidental overwrite"} for prompt in catalog]
    database.seed_builtin_prompts(changed)
    assert database.get_prompt("query_planner.v1")["body"] == V1_PROMPTS[0]["body"]


def test_released_catalog_seeds_v2_and_keeps_v1(database):
    database.seed_builtin_prompts(BUILTIN_PROMPTS)
    assert len(database.list_prompts()) == 8
    assert all(prompt["version"] == "v2" for prompt in database.resolve_prompts({}))
    assert {prompt["id"] for prompt in database.list_prompts() if prompt["version"] == "v1"} == {
        prompt["id"] for prompt in V1_PROMPTS
    }


def test_seeding_is_atomic_on_bad_catalog(database):
    broken = [{**V1_PROMPTS[0]}, {"id": "broken", "role": "query_planner"}]
    with pytest.raises(KeyError):
        database.seed_builtin_prompts(broken)
    assert database.list_prompts() == []


def test_model_messages_preserve_context_and_legacy_call_signatures():
    calls = []
    task = TaskCreate(name="test", topic="Different task", research_questions=["Does it work?"], output_language="en").model_dump()
    paper = {"title": "Paper", "abstract": "An observational association."}
    summary = {key: value for key, value in fallback(paper, task["topic"]).items() if key != "engine"}

    def respond(request):
        payload = json.loads(request.content)
        calls.append(payload)
        result = {"evidence_warnings": [], "confidence": .7} if payload["messages"][0]["content"] == "review" else summary
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(result)}}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        provider = ModelProvider("https://example.test/v1", "key", "model", client)
        provider.summarize(paper, task["topic"], "summary", task=task)
        provider.review_evidence(paper, summary, "review", task=task)
        provider.summarize(paper, "legacy", "summary")
        provider.review_evidence(paper, summary, "review")
    for call in calls[:2]:
        assert call["temperature"] == .1
        assert call["messages"][0]["role"] == "system"
        assert json.loads(call["messages"][1]["content"])["task"] == task
    assert "task" not in json.loads(calls[2]["messages"][1]["content"])
    assert "task" not in json.loads(calls[3]["messages"][1]["content"])
    assert paper == {"title": "Paper", "abstract": "An observational association."}


@pytest.mark.parametrize("mode,route,expected_engine", [
    ("off", "auto_apply", "baseline"),
    ("shadow", "auto_apply", "baseline"),
    ("active", "auto_apply", "jev-test"),
    ("active", "needs_review", "baseline"),
])
def test_graph_context_and_actual_jev_routing(database, tmp_path, monkeypatch, mode, route, expected_engine):
    catalog = release_catalog("v2")
    database.seed_builtin_prompts(catalog)
    task = TaskCreate(name="context", topic="A user-supplied topic", research_questions=["A user question?"],
                      output_language="en", evidence_review=True, target_count=1, sources=["fixture"]).model_dump()
    task = database.create_task(task)
    run = database.create_run(task["id"], total_steps=7)
    captured = {}
    bodies = {prompt["body"]: prompt["role"] for prompt in V2_PROMPTS}

    def complete(_self, system, payload):
        role = bodies[system]
        captured[role] = payload
        if role == "query_planner":
            return {"queries": ["用户提供的主题", task["topic"]], "exclusions": [], "language_policy": "bilingual", "source_routing": ["fixture"]}
        if role == "relevance_screener":
            return {"relevance_score": .8, "priority": "P0", "relevance_reason": "baseline reason", "recommended_action": "read"}
        if role == "literature_summarizer":
            return {key: value for key, value in fallback(payload["paper"], task["topic"]).items() if key != "engine"}
        return {"evidence_warnings": ["baseline warning"], "confidence": .3}

    class FakeDecisions:
        configured = mode != "off"
        provider = "fake"
        probability_kind = "self_reported"

        def __init__(self, *_):
            self.mode = mode

        def screen_paper(self, *_):
            return {"relevance_score": .95, "priority": "P0", "relevance_reason": "jev reason", "recommended_action": "save",
                    "decision_confidence": .95, "auto_eligible": True, "route": route, "engine": "jev-test"}

        def review_evidence(self, *_):
            return {"evidence_warnings": ["jev warning"], "confidence": .2, "decision_confidence": .95,
                    "auto_eligible": True, "route": route, "engine": "jev-test"}

    monkeypatch.setattr(ModelProvider, "_complete_json", complete)
    monkeypatch.setattr(graph_module, "JevDecisionProvider", FakeDecisions)
    settings = Settings(root=tmp_path, llm_model="baseline", llm_api_key="test", jev_shadow_mode=mode != "active")
    graph_module.build_graph(settings, database, database.resolve_prompts(task)).invoke({"task": task, "run_id": run["id"], "errors": []})
    assert database.get_run(run["id"])["status"] == "completed"
    assert database.get_run_artifact(run["id"], "result_manifest")["payload"]["errors"] == []
    assert set(captured) == {prompt["role"] for prompt in V2_PROMPTS}
    for payload in captured.values():
        assert payload["task"] == task
    paper = database.list_papers(run["id"])[0]
    assert paper["screening"]["engine"] == expected_engine
    assert paper["summary"]["engine"] == "baseline"
    assert paper["summary"]["evidence_review_engine"] == expected_engine
    assert paper["summary"]["relevance_reason"] == paper["screening"]["relevance_reason"]
    snapshot = database.get_run_artifact(run["id"], "query_planner")["payload"]["prompt_snapshot"]
    assert all(prompt["version"] == "v2" for prompt in snapshot.values())


def test_fixed_cases_keep_paired_papers_inside_one_split():
    cases = json.loads((Path(__file__).parent / "fixtures" / "prompt_cases.json").read_text(encoding="utf-8"))["cases"]
    assert len(cases) >= 20
    assert len({case["id"] for case in cases}) == len(cases)
    development = {(case["paper"]["title"], case["paper"]["abstract"]) for case in cases if case["split"] == "development"}
    holdout = {(case["paper"]["title"], case["paper"]["abstract"]) for case in cases if case["split"] == "holdout"}
    assert development.isdisjoint(holdout)
    assert all(case["provenance"] == "synthetic" for case in cases)
