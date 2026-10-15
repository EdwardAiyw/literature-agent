import httpx
import pytest

from literature_agent.llm import ModelProvider, fallback, validate_query_plan


def test_unconfigured_model_uses_explicit_fallback():
    result = ModelProvider("https://example.test/v1", "", "").summarize({"title": "Paper", "abstract": "Abstract"}, "topic")
    assert result["engine"] == "fallback"
    assert "not stated in source" in result["main_findings"]


def test_model_provider_parses_structured_response():
    class Transport(httpx.BaseTransport):
        def handle_request(self, request):
            payload = '{"research_problem":"问题","method":"方法","main_findings":["发现"],"limitations":["局限"],"relevance_reason":"相关","research_use":"精读","recommended_action":"read","confidence":0.9,"evidence_warnings":[]}'
            return httpx.Response(200, json={"choices": [{"message": {"content": payload}}]})

    client = httpx.Client(transport=Transport())
    result = ModelProvider("https://example.test/v1", "key", "model", client).summarize({"title": "Paper", "abstract": "Abstract"}, "topic")
    assert result["engine"] == "model"
    assert result["confidence"] == 0.9


def test_bilingual_plan_repairs_chinese_only_model_output_without_changing_task(monkeypatch):
    task = {"topic": "智能体检索增强生成", "language": "bilingual", "sources": ["arxiv"],
            "date_from": "2023-01-01", "date_to": "2026-10-15"}
    responses = iter([
        {"queries": ["智能体检索增强生成", "agentic RAG 多智能体"], "exclusions": [],
         "language_policy": "bilingual", "source_routing": ["arxiv"]},
        {"queries": ["智能体 检索增强生成", "agentic retrieval augmented generation"], "exclusions": [],
         "language_policy": "bilingual", "source_routing": ["arxiv", "invented-source"]},
    ])
    calls = []
    provider = ModelProvider("https://example.test/v1", "key", "model")
    monkeypatch.setattr(provider, "_complete_json", lambda system, payload: calls.append((system, payload)) or next(responses))
    result = provider.plan_queries(task, "saved prompt")
    assert len(calls) == 2
    assert calls[0][0] == calls[1][0] == "saved prompt"
    assert calls[1][1]["task"] == task
    assert result["queries"][-1] == "agentic retrieval augmented generation"
    assert result["source_routing"] == ["arxiv"]
    assert result["repair_count"] == 1
    assert len(result["validation_errors"]) == 1
    assert task["date_from"] == "2023-01-01"


@pytest.mark.parametrize("language,queries", [
    ("en", ["agentic retrieval evaluation"]),
    ("zh", ["智能体 RAG 评测"]),
    ("bilingual", ["水稻 耐旱", "rice drought tolerance"]),
])
def test_valid_query_languages_are_preserved(language, queries):
    plan = {"queries": queries, "language_policy": language, "exclusions": [], "source_routing": []}
    assert validate_query_plan(plan, {"language": language})["queries"] == queries


@pytest.mark.parametrize("queries", [[], [None], ["中英文混在一起 agentic RAG"], ["rice drought tolerance"],
                                      ["主题 " * 90, "topic"]])
def test_invalid_bilingual_plans_have_one_bounded_repair(monkeypatch, queries):
    provider = ModelProvider("https://example.test/v1", "key", "model")
    calls = []
    monkeypatch.setattr(provider, "_complete_json", lambda *_: calls.append(1) or {
        "queries": queries, "exclusions": [], "source_routing": [], "language_policy": "bilingual",
    })
    with pytest.raises(ValueError, match="after repair"):
        provider.plan_queries({"topic": "topic", "language": "bilingual"}, "prompt")
    assert len(calls) == 2


@pytest.mark.parametrize("score", [True, float("nan"), float("inf"), 1.2, -.1])
def test_invalid_screening_scores_are_not_promoted_to_relevant(monkeypatch, score):
    provider = ModelProvider("https://example.test/v1", "key", "model")
    monkeypatch.setattr(provider, "_complete_json", lambda *_: {
        "relevance_score": score, "priority": "P0", "relevance_reason": "reason", "recommended_action": "read",
    })
    with pytest.raises(ValueError, match="relevance_score"):
        provider.screen({}, {"topic": "topic"}, "prompt")
