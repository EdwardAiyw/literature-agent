"""Paid real-model screening comparison; isolated SQLite, no email or Zotero writes."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from literature_agent.config import ConfigManager, Settings  # noqa: E402
from literature_agent.db import Database  # noqa: E402
from literature_agent.decisions import JevDecisionProvider  # noqa: E402
from literature_agent.llm import ModelProvider  # noqa: E402
from literature_agent.prompts import V2_PROMPTS  # noqa: E402


def compare(settings: Settings, cases: list[dict], workers: int = 2) -> dict:
    prompt = next(p["body"] for p in V2_PROMPTS if p["role"] == "relevance_screener")
    with TemporaryDirectory(prefix="jev-screening-") as directory:
        database = Database(Path(directory) / "validation.db")
        decisions = JevDecisionProvider(replace(settings, jev_shadow_mode=False,
            jev_auto_threshold=max(.82, settings.jev_auto_threshold)), database)
        if not decisions.configured or not settings.llm_api_key or not settings.llm_model:
            database.close()
            raise ValueError("Configure both ordinary model and Jev before evaluation")

        def evaluate(case: dict, active: bool) -> dict:
            started = time.perf_counter()
            decision, baseline, output, error, jev_error, correct = None, False, {}, "", "", False
            try:
                if active:
                    try:
                        decision = decisions.screen_paper("validation", {"canonical_id": case["id"],
                            **case["paper"]}, case["task"], prompt)
                    except Exception as exc:
                        jev_error = type(exc).__name__
                if decision and decision.get("auto_eligible") and decision.get("route") == "auto_apply":
                    output = decision
                else:
                    baseline = True
                    model = ModelProvider(settings.llm_base_url, settings.llm_api_key, settings.llm_model)
                    try:
                        output = model.screen(case["paper"], case["task"], prompt)
                    finally:
                        if model.client:
                            model.client.close()
                score, action = output["relevance_score"], output["recommended_action"]
                correct = (score >= .65 and action != "ignore") if case["expected"] == "direct" else (
                    score < .4 or action == "ignore") if case["expected"] == "unrelated" else (
                    score <= .7 and action != "save")
            except Exception as exc:
                # Do not serialize authenticated URLs, headers or upstream bodies.
                error = type(exc).__name__
            return {"id": case["id"], "expected": case["expected"], "correct": correct,
                    "result": output, "jev": decision, "baseline": baseline, "error": error, "jev_error": jev_error,
                    "seconds": round(time.perf_counter() - started, 3)}

        report = {"cases": len(cases), "workers": workers, "cache": "fresh isolated database",
                  "model": settings.llm_model, "prompt": "relevance_screener.v2"}
        try:
            for mode in ("baseline", "active"):
                started = time.perf_counter()
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    rows = list(pool.map(lambda case: evaluate(case, mode == "active"), cases))
                report[mode] = {"seconds": time.perf_counter() - started, "rows": rows,
                    "correct": sum(r["correct"] for r in rows), "valid": sum(not r["error"] for r in rows),
                    "baseline_calls": sum(r["baseline"] for r in rows)}
            active, baseline = report["active"], report["baseline"]
            report["passed"] = (active["correct"] / len(cases) >= .9 and active["valid"] == baseline["valid"] == len(cases)
                and active["baseline_calls"] < len(cases) and active["seconds"] < baseline["seconds"]
                and all(r["correct"] for r in active["rows"] if r["expected"] == "unrelated"))
            return report
        finally:
            database.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", type=Path, default=ROOT / "backend/tests/fixtures/prompt_cases.json")
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))["cases"]
    selected = [c for c in cases if c["split"] == "holdout"] + cases[:2]
    settings = ConfigManager(Settings.from_env(ROOT)).get()
    report = compare(settings, selected)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "cases": report["cases"], "output": str(args.output)}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
