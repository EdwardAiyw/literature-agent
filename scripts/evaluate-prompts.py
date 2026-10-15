"""Fixed-input prompt comparison. Calls only the configured model, never the app DB.

Run development first, freeze candidates, then run holdout. A successful CLI run
does not release prompts: inspect source support and language in the saved outputs.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from literature_agent.config import ConfigManager, Settings  # noqa: E402
from literature_agent.llm import ModelProvider, SUMMARY_KEYS  # noqa: E402
from literature_agent.prompts import V1_PROMPTS, V2_PROMPTS  # noqa: E402

ROLES = ("query_planner", "relevance_screener", "literature_summarizer", "evidence_reviewer")
FIELDS = {
    "query_planner": {"queries", "exclusions", "language_policy", "source_routing"},
    "relevance_screener": {"relevance_score", "priority", "relevance_reason", "recommended_action"},
    "literature_summarizer": set(SUMMARY_KEYS),
    "evidence_reviewer": {"evidence_warnings", "confidence"},
}


def valid_number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1


def strings(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def validate_output(role: str, raw: str) -> tuple[dict, list[str]]:
    """Check raw output before production coercions/clamping can hide defects."""
    try:
        result = json.loads(raw)
    except (ValueError, TypeError):
        return {}, ["not a JSON object without markdown"]
    if not isinstance(result, dict) or set(result) != FIELDS[role]:
        return {}, ["incorrect object fields"]
    errors = []
    arrays = {
        "query_planner": ("queries", "exclusions", "source_routing"),
        "literature_summarizer": ("main_findings", "limitations", "evidence_warnings"),
        "evidence_reviewer": ("evidence_warnings",),
    }.get(role, ())
    for field in arrays:
        if not strings(result[field]):
            errors.append(f"{field}: expected array of strings")
    for field in ("confidence", "relevance_score"):
        if field in result and not valid_number(result[field]):
            errors.append(f"{field}: expected finite number in [0,1]")
    if "recommended_action" in result and result["recommended_action"] not in ("read", "save", "background", "ignore"):
        errors.append("invalid recommended_action")
    if role == "relevance_screener":
        if not isinstance(result["relevance_reason"], str):
            errors.append("relevance_reason: expected string")
        score = result["relevance_score"]
        expected_priority = "P0" if valid_number(score) and score >= .7 else "P1" if valid_number(score) and score >= .4 else "P2"
        if result["priority"] != expected_priority:
            errors.append("priority does not match existing score thresholds")
    if role == "literature_summarizer":
        for field in ("research_problem", "method", "relevance_reason", "research_use"):
            if not isinstance(result[field], str):
                errors.append(f"{field}: expected string")
    if role == "query_planner":
        if not strings(result["queries"]) or not 1 <= len(result["queries"]) <= 4 or any(not item.strip() for item in result["queries"]):
            errors.append("queries: expected 1-4 nonempty strings")
        if result["language_policy"] not in ("zh", "en", "bilingual"):
            errors.append("invalid language_policy")
    return result, errors


def task_for(case: dict) -> dict:
    return {
        "name": case["id"], "target_count": 5, "date_from": "", "date_to": "",
        "sources": ["semantic_scholar", "openalex", "crossref", "arxiv", "pubmed"],
        "evidence_review": True, "prompt_overrides": {}, **case["task"],
    }


def review_summary(case: dict) -> dict:
    return {
        "research_problem": "not stated in source", "method": "not stated in source",
        "main_findings": [case["review"]["claim"]], "limitations": ["not stated in source"],
        "relevance_reason": "candidate for this task", "research_use": "verify against the full paper",
        "recommended_action": "background", "confidence": .95, "evidence_warnings": [],
    }


def jobs_for(cases: list[dict]) -> list[tuple[dict, str, dict]]:
    jobs = []
    for case in cases:
        roles = ["relevance_screener"]
        roles += ["query_planner"] if case.get("plan") else []
        roles += ["literature_summarizer"] if case.get("summarize") else []
        roles += ["evidence_reviewer"] if case.get("review") else []
        for role in roles:
            for catalog in (V1_PROMPTS, V2_PROMPTS):
                jobs.append((case, role, next(prompt for prompt in catalog if prompt["role"] == role)))
    return jobs


def evaluate_job(settings: Settings, case: dict, role: str, prompt: dict) -> dict:
    task = task_for(case)
    paper = case["paper"]
    row = {"case_id": case["id"], "split": case["split"], "role": role,
           "version": prompt["version"], "prompt_id": prompt["id"], "raw_output": "", "usage": {}}
    if role == "relevance_screener":
        row["expected"] = case["expected"]

    def capture(response: httpx.Response) -> None:
        response.read()
        if response.status_code == 200:
            body = response.json()
            row["raw_output"] = body.get("choices", [{}])[0].get("message", {}).get("content", "")
            row["usage"] = body.get("usage", {})

    started = time.perf_counter()
    try:
        with httpx.Client(timeout=45, event_hooks={"response": [capture]}) as client:
            provider = ModelProvider(settings.llm_base_url, settings.llm_api_key, settings.llm_model, client)
            if role == "query_planner":
                output = provider.plan_queries(task, prompt["body"])
            elif role == "relevance_screener":
                output = provider.screen(paper, task, prompt["body"])
            elif role == "literature_summarizer":
                output = provider.summarize(paper, task["topic"], prompt["body"], task=task)
            else:
                output = provider.review_evidence(paper, review_summary(case), prompt["body"], task=task)
            row["output"] = output
            row["engine"] = output["engine"]
    except Exception as exc:
        # Do not save provider bodies/headers/URLs which may contain credentials.
        row["error"] = type(exc).__name__
        row["provider_failure"] = isinstance(exc, (httpx.RequestError, httpx.HTTPStatusError))
        if isinstance(exc, httpx.HTTPStatusError):
            row["http_status"] = exc.response.status_code
    row["latency_ms"] = round((time.perf_counter() - started) * 1000)
    raw, errors = validate_output(role, row["raw_output"])
    row["validation_errors"] = errors
    row["schema_valid"] = not errors and "error" not in row
    if role == "relevance_screener" and raw and valid_number(raw.get("relevance_score")):
        score = raw["relevance_score"]
        label = "direct" if score >= .7 else "borderline" if score >= .4 else "unrelated"
        row.update(expected=case["expected"], predicted=label, label_correct=label == case["expected"])
    if role == "query_planner" and raw:
        row["task_constraints_match"] = (
            raw["language_policy"] == task["language"] and raw["source_routing"] == task["sources"]
            and raw["exclusions"] == []
        )
    if role == "evidence_reviewer" and raw:
        row["planted_claim_flagged"] = bool(raw["evidence_warnings"]) and valid_number(raw["confidence"]) and raw["confidence"] < .95
        row["manual_review_required"] = "Confirm warnings identify the planted claim, not just a generic source caveat."
    if role == "literature_summarizer" and raw:
        claim_text = json.dumps({key: raw[key] for key in ("research_problem", "method", "main_findings", "limitations")}, ensure_ascii=False)
        source = paper["title"] + " " + paper["abstract"]
        row["new_numeric_tokens"] = sorted(set(re.findall(r"\d+(?:\.\d+)?", claim_text)) - set(re.findall(r"\d+(?:\.\d+)?", source)))
        row["manual_review_required"] = "Audit every research claim against source; check language, missing evidence, negation and causal qualifiers. Numeric tokens are only a heuristic."
    return row


def summarize(rows: list[dict]) -> dict:
    summary = {}
    for version in ("v1", "v2"):
        values = [row for row in rows if row["version"] == version]
        screens = [row for row in values if row["role"] == "relevance_screener"]
        clear = [row for row in screens if row.get("expected") in ("direct", "unrelated")]
        summary[version] = {
            "calls": len(values), "errors": sum("error" in row for row in values),
            "schema_valid": sum(row["schema_valid"] for row in values),
            "screen_correct": sum(row.get("label_correct", False) for row in screens), "screen_total": len(screens),
            "clear_screen_correct": sum(row.get("label_correct", False) for row in clear),
            "clear_screen_total": len(clear),
            "planted_flag_checks_pass": sum(row.get("planted_claim_flagged", False) for row in values),
            "planner_constraints_pass": sum(row.get("task_constraints_match", False) for row in values),
            "total_tokens": sum(row["usage"].get("total_tokens", 0) for row in values),
        }
    return summary


def automatic_checks(rows: list[dict], planned_calls: int) -> dict:
    stats = summarize(rows)
    candidate = [row for row in rows if row["version"] == "v2"]
    return {
        "complete": planned_calls > 0 and len(rows) == planned_calls,
        "v2_schema_all_valid": bool(candidate) and all(row["schema_valid"] for row in candidate),
        "clear_screening_not_worse": (
            stats["v2"]["clear_screen_total"] > 0
            and stats["v2"]["clear_screen_total"] == stats["v1"]["clear_screen_total"]
            and stats["v2"]["clear_screen_correct"] >= stats["v1"]["clear_screen_correct"]
        ),
        "source_support_and_language": "manual_review_required",
        "baseline_defect_fixed": "manual_review_required",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("development", "holdout"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    args = parser.parse_args()
    fixture = ROOT / "backend" / "tests" / "fixtures" / "prompt_cases.json"
    content = fixture.read_bytes()
    cases = [case for case in json.loads(content)["cases"] if case["split"] == args.split]
    settings = ConfigManager(Settings.from_env()).get()
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(), "split": args.split,
        "model": settings.llm_model, "temperature": .1, "dataset_sha256": hashlib.sha256(content).hexdigest(),
        "cases": cases, "prompts": V1_PROMPTS + V2_PROMPTS,
        "limitations": "Synthetic cases; one sample per version, input and role. No live retrieval, no Jev calls, no production DB changes. Human source/language review required. Does not demonstrate real-world recall or repeatability.",
        "release_status": "pending_manual_review", "results": [],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)

    def save_report() -> None:
        report["summary"] = summarize(report["results"])
        report["automatic_checks"] = automatic_checks(report["results"], report.get("planned_calls", 0))
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    save_report()
    if not settings.llm_api_key or not settings.llm_model:
        report["release_status"] = "blocked_no_model"
    else:
        jobs = jobs_for(cases)
        report["planned_calls"] = len(jobs)
        report["release_status"] = "running"
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            # Bound failed-provider spend; do not queue an entire corpus against an
            # unreachable service. Persist each result so interruptions are reviewable.
            for start in range(0, len(jobs), args.workers):
                futures = [pool.submit(evaluate_job, settings, *job) for job in jobs[start:start + args.workers]]
                for future in as_completed(futures):
                    row = future.result()
                    report["results"].append(row)
                    save_report()
                    print(f"{row['case_id']} {row['role']} {row['version']}: {'ok' if row['schema_valid'] else 'FAIL'}", flush=True)
                if sum(row.get("provider_failure", False) for row in report["results"]) >= 3:
                    report["release_status"] = "blocked_provider_failures"
                    break
        if report["release_status"] == "running":
            report["release_status"] = "pending_manual_review"
        report["results"].sort(key=lambda row: (row["case_id"], row["role"], row["version"]))
    report["summary"] = summarize(report["results"])
    if not report["release_status"].startswith("blocked") and any(not row["schema_valid"] for row in report["results"] if row["version"] == "v2"):
        report["release_status"] = "blocked_output_or_provider_failure"
    if report["release_status"] == "pending_manual_review":
        checks = automatic_checks(report["results"], report["planned_calls"])
        if not all(checks[key] for key in ("complete", "v2_schema_all_valid", "clear_screening_not_worse")):
            report["release_status"] = "blocked_quality_checks"
    save_report()
    print(json.dumps({"report": str(args.out), "status": report["release_status"], "summary": report["summary"]}, ensure_ascii=False))
    return 1 if report["release_status"].startswith("blocked") else 0


if __name__ == "__main__":
    raise SystemExit(main())
