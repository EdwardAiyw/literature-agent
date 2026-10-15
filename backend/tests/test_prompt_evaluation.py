import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def evaluation():
    path = Path(__file__).resolve().parents[2] / "scripts" / "evaluate-prompts.py"
    spec = importlib.util.spec_from_file_location("prompt_evaluation", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("score,priority", [(True, "P0"), (float("nan"), "P2"), (1.2, "P0"), (.8, "P2")])
def test_evaluation_detects_output_errors_hidden_by_production_coercion(evaluation, score, priority):
    raw = json.dumps({"relevance_score": score, "priority": priority, "relevance_reason": "source", "recommended_action": "read"})
    _, errors = evaluation.validate_output("relevance_screener", raw)
    assert errors


def test_evaluation_does_not_accept_empty_or_regressed_comparisons(evaluation):
    assert evaluation.automatic_checks([], 0)["v2_schema_all_valid"] is False
    assert evaluation.automatic_checks([], 0)["complete"] is False
    rows = [
        {"version": "v1", "role": "relevance_screener", "schema_valid": True, "usage": {}, "expected": "direct", "label_correct": True},
        {"version": "v2", "role": "relevance_screener", "schema_valid": True, "usage": {}, "expected": "direct", "label_correct": False},
    ]
    checks = evaluation.automatic_checks(rows, 2)
    assert checks["complete"] is True
    assert checks["clear_screening_not_worse"] is False
    assert checks["source_support_and_language"] == "manual_review_required"


def test_evaluation_stops_unreachable_provider_and_persists_failure_report(evaluation, tmp_path, monkeypatch):
    settings = SimpleNamespace(llm_api_key="fake", llm_model="fake")
    monkeypatch.setattr(evaluation.Settings, "from_env", lambda: None)
    monkeypatch.setattr(evaluation, "ConfigManager", lambda _: SimpleNamespace(get=lambda: settings))
    calls = []

    def fail(_settings, case, role, prompt):
        calls.append(case["id"])
        return {"case_id": case["id"], "role": role, "split": case["split"], "version": prompt["version"],
                "error": "ReadTimeout", "provider_failure": True, "schema_valid": False, "usage": {}, "expected": case["expected"]}

    monkeypatch.setattr(evaluation, "evaluate_job", fail)
    output = tmp_path / "report.json"
    monkeypatch.setattr(evaluation.sys, "argv", ["evaluate-prompts.py", "--split", "development", "--workers", "4", "--out", str(output)])
    assert evaluation.main() == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert len(calls) == 4 < report["planned_calls"]
    assert report["release_status"] == "blocked_provider_failures"
    assert report["automatic_checks"]["complete"] is False
    assert len(report["results"]) == 4
    assert "fake" not in json.dumps(report["results"])
