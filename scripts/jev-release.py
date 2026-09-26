from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND / "src"))

from literature_agent.config import Settings  # noqa: E402


LOCALJEV_DEFAULT_URL = "http://127.0.0.1:8080"
LOCALJEV_MODEL = "jev-latest"
LOCALJEV_MODEL_ALIASES = {"localjev-0.2", "localjev-latest", "jev-latest", "jev-preview"}


SHADOW_CASES = (
    {
        "name": "Jev Shadow - Agentic RAG benchmarks",
        "topic": "agentic RAG evaluation benchmarks",
        "research_questions": [
            "How are agentic RAG systems evaluated for retrieval quality, reasoning reliability, and end-to-end task performance?"
        ],
    },
    {
        "name": "Jev Shadow - Multi-agent scholarly search",
        "topic": "retrieval planning in multi-agent scholarly search",
        "research_questions": [
            "Which planning and coordination methods improve scholarly retrieval in multi-agent systems?"
        ],
    },
    {
        "name": "Jev Shadow - Evidence attribution",
        "topic": "hallucination and evidence attribution in RAG literature reviews",
        "research_questions": [
            "Which methods reduce hallucination and improve evidence attribution in RAG literature reviews?"
        ],
    },
)


def request_json(
    base_url: str,
    path: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 60,
) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        method=method,
        headers=request_headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed with HTTP {exc.code}: {body}") from exc


def update_env(values: dict[str, str]) -> None:
    env_path = BACKEND / ".env"
    if not env_path.exists():
        raise RuntimeError(f"Missing {env_path}")
    lines = env_path.read_text(encoding="utf-8").splitlines()
    remaining = dict(values)
    updated: list[str] = []
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in remaining:
                updated.append(f"{key}={remaining.pop(key)}")
                continue
        updated.append(line)
    updated.extend(f"{key}={value}" for key, value in remaining.items())
    env_path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def normalize_localjev_url(base_url: str) -> str:
    value = base_url.strip().rstrip("/")
    if value.endswith("/v1"):
        value = value[:-3]
    if not value.startswith(("http://", "https://")):
        raise RuntimeError("LocalJev base URL must start with http:// or https://")
    return value


def inspect_localjev(base_url: str, api_key: str = "", timeout: float = 10) -> dict[str, Any]:
    base_url = normalize_localjev_url(base_url)
    health = request_json(base_url, "/health", timeout=timeout)
    if not isinstance(health, dict) or health.get("status") != "ok":
        raise RuntimeError("LocalJev /health did not return status=ok")

    ready = request_json(base_url, "/ready", timeout=timeout)
    if not isinstance(ready, dict) or ready.get("status") != "ready":
        detail = ready.get("detail") if isinstance(ready, dict) else None
        raise RuntimeError(str(detail or "LocalJev upstream model is unavailable"))

    auth_headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
    response = request_json(base_url, "/v1/models", headers=auth_headers, timeout=timeout)
    models = response.get("models") if isinstance(response, dict) else None
    if not isinstance(models, list):
        raise RuntimeError("LocalJev /v1/models did not return a models array")
    names = {
        model.get("name")
        for model in models
        if isinstance(model, dict) and isinstance(model.get("name"), str)
    }
    if not names.intersection(LOCALJEV_MODEL_ALIASES):
        raise RuntimeError("LocalJev returned no supported Jev model")
    return {
        "base_url": base_url,
        "model": LOCALJEV_MODEL,
        "upstream_model": ready.get("upstream_model", ""),
        "available_models": sorted(names),
    }


def prepare(args: argparse.Namespace) -> int:
    settings = Settings.from_env(BACKEND)
    configured_url = settings.jev_base_url if settings.jev_provider.strip().lower() in {"local", "localjev"} else ""
    base_url = args.base_url or configured_url or LOCALJEV_DEFAULT_URL
    status = inspect_localjev(base_url, settings.jev_api_key)
    update_env(
        {
            "JEV_PROVIDER": "localjev",
            "JEV_BASE_URL": status["base_url"],
            "JEV_MODEL": LOCALJEV_MODEL,
            "JEV_TIMEOUT_SECONDS": "180",
            "JEV_MAX_INFLIGHT": "2",
            "JEV_ENABLED": "true",
            "JEV_SHADOW_MODE": "true",
        }
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))
    print("Prepared backend/.env for LocalJev Shadow. Restart Literature Agent before validation.")
    return 0


def wait_for_run(base_url: str, run_id: str, timeout_seconds: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        run = request_json(base_url, f"/api/runs/{run_id}")
        if run["status"] in {"completed", "failed", "cancelled"}:
            return run
        time.sleep(2)
    raise RuntimeError(f"Run {run_id} did not finish within {timeout_seconds} seconds")


def execute_case(base_url: str, case: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    task = request_json(
        base_url,
        "/api/tasks",
        "POST",
        {
            **case,
            "target_count": 5,
            "sources": ["semantic_scholar", "openalex", "crossref", "arxiv", "pubmed"],
            "language": "bilingual",
            "output_language": "zh",
            "evidence_review": True,
            "origin": "test",
        },
    )
    run = request_json(base_url, f"/api/tasks/{task['id']}/runs", "POST")
    completed = wait_for_run(base_url, run["id"], timeout_seconds)
    decisions = request_json(base_url, f"/api/runs/{run['id']}/decisions")
    papers = request_json(base_url, f"/api/runs/{run['id']}/papers")
    artifacts = request_json(base_url, f"/api/runs/{run['id']}/artifacts")
    retrieval = next((item["payload"] for item in artifacts if item["node"] == "retrieval"), {})
    automatic_pass = (
        completed["status"] == "completed"
        and len(papers) >= 5
        and bool(decisions)
        and retrieval.get("source_mode") != "fixture_fallback"
        and all(
            item["mode"] == "shadow"
            and item["status"] == "shadow_observed"
            and not item["fallback_used"]
            and not item["error"]
            for item in decisions
        )
    )
    return {
        "task_id": task["id"],
        "run_id": run["id"],
        "name": case["name"],
        "status": completed["status"],
        "paper_count": len(papers),
        "papers": [
            {
                "title": paper.get("title", ""),
                "source": paper.get("source", ""),
                "relevance_score": paper.get("relevance_score", 0),
                "official_url": paper.get("official_url", ""),
            }
            for paper in papers[:5]
        ],
        "decision_count": len(decisions),
        "decision_statuses": sorted({item["status"] for item in decisions}),
        "source_mode": retrieval.get("source_mode", ""),
        "automatic_pass": automatic_pass,
    }


def write_report(prefix: str, payload: dict[str, Any]) -> Path:
    log_dir = BACKEND / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = log_dir / f"{prefix}-{timestamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def validate_runtime(settings: dict[str, Any], expected_shadow: bool) -> None:
    required = {
        "live": True,
        "llm_configured": True,
        "jev_enabled": True,
        "jev_configured": True,
        "jev_shadow_mode": expected_shadow,
    }
    mismatches = {key: (settings.get(key), value) for key, value in required.items() if settings.get(key) != value}
    if mismatches:
        raise RuntimeError(f"Runtime settings do not match the release gate: {mismatches}")


def shadow(args: argparse.Namespace) -> int:
    validate_runtime(request_json(args.base_url, "/api/settings"), expected_shadow=True)
    cases = [execute_case(args.base_url, case, args.timeout_seconds) for case in SHADOW_CASES]
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "shadow",
        "automatic_pass": len(cases) == 3 and all(case["automatic_pass"] for case in cases),
        "manual_review_required": "Confirm at least four of the five papers in every case are directly relevant and evidence-bounded.",
        "cases": cases,
    }
    path = write_report("jev-shadow", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Report: {path}")
    return 0 if report["automatic_pass"] else 1


def activate(args: argparse.Namespace) -> int:
    if not args.approve_relevance:
        raise RuntimeError("Activation requires --approve-relevance after reviewing all 15 papers")
    report_path = Path(args.report).resolve()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("mode") != "shadow" or not report.get("automatic_pass") or len(report.get("cases", [])) != 3:
        raise RuntimeError("The supplied report did not pass the three-run Shadow gate")
    update_env({"JEV_ENABLED": "true", "JEV_SHADOW_MODE": "false"})
    print("Jev Active is configured in backend/.env. Restart the local service, then run the canary command.")
    return 0


def canary(args: argparse.Namespace) -> int:
    validate_runtime(request_json(args.base_url, "/api/settings"), expected_shadow=False)
    result = execute_case(args.base_url, SHADOW_CASES[0] | {"name": "Jev Active canary"}, args.timeout_seconds)
    decisions = request_json(args.base_url, f"/api/runs/{result['run_id']}/decisions")
    active_pass = result["status"] == "completed" and not any(item["status"] == "failed" for item in decisions) and any(
        item["status"] == "applied" for item in decisions
    )
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "mode": "active", "automatic_pass": active_pass, "case": result}
    path = write_report("jev-active-canary", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Report: {path}")
    return 0 if active_pass else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare and validate the Jev local release gate")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare", help="verify LocalJev readiness and enable Shadow")
    prepare_parser.add_argument("--base-url", help=f"LocalJev URL (default: {LOCALJEV_DEFAULT_URL})")
    prepare_parser.set_defaults(handler=prepare)

    shadow_parser = subparsers.add_parser("shadow", help="run the three-case Shadow validation")
    shadow_parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    shadow_parser.add_argument("--timeout-seconds", type=int, default=900)
    shadow_parser.set_defaults(handler=shadow)

    activate_parser = subparsers.add_parser("activate", help="switch .env to Active after manual relevance review")
    activate_parser.add_argument("--report", required=True)
    activate_parser.add_argument("--approve-relevance", action="store_true")
    activate_parser.set_defaults(handler=activate)

    canary_parser = subparsers.add_parser("canary", help="verify Active mode applies at least one decision")
    canary_parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    canary_parser.add_argument("--timeout-seconds", type=int, default=900)
    canary_parser.set_defaults(handler=canary)

    args = parser.parse_args()
    try:
        return args.handler(args)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
