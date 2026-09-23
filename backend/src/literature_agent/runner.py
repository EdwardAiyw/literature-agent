from __future__ import annotations

from datetime import datetime, timezone

from .config import Settings
from .db import Database
from .email import render_digest, send_message
from .graph import build_graph


def execute_run(settings: Settings, database: Database, run_id: str, task: dict) -> dict:
    current = database.get_run(run_id) or {}
    started_at = current.get("started_at") or datetime.now(timezone.utc).isoformat()
    database.update_run(run_id, status="running", current_node="query_planner", started_at=started_at)
    try:
        graph = build_graph(settings, database, database.list_prompts())
        graph.invoke({"task": task, "run_id": run_id, "errors": []})
    except Exception as exc:
        database.update_run(run_id, status="failed", current_node="failed", error=f"{type(exc).__name__}: {exc}", finished_at=datetime.now(timezone.utc).isoformat())
    return database.get_run(run_id) or {}


def run_subscription(settings: Settings, database: Database, subscription: dict, send_email: bool = True, run_id: str | None = None) -> dict:
    if not settings.live:
        raise RuntimeError("LITERATURE_AGENT_LIVE=true is required for subscription runs")
    if not settings.llm_api_key or not settings.llm_model:
        raise RuntimeError("LLM_API_KEY and LLM_MODEL must be configured for subscription runs")
    task = database.get_task(subscription["task_id"])
    if not task:
        raise RuntimeError(f"Task {subscription['task_id']} not found for subscription")
    total_steps = 7 if task.get("evidence_review") else 6
    run = database.get_run(run_id) if run_id else database.create_run(
        subscription["task_id"], total_steps=total_steps, trigger_kind="subscription", subscription_id=subscription["id"]
    )
    if not run:
        raise RuntimeError(f"Run {run_id} not found")
    result = execute_run(settings, database, run["id"], task)
    if not send_email:
        return result

    papers = database.list_papers(run["id"])
    retrieval = database.get_run_artifact(run["id"], "retrieval") or {}
    diagnostics = retrieval.get("payload", {}).get("sources", {})
    message = render_digest(subscription, papers, diagnostics)
    delivery = database.create_delivery(subscription["id"], run["id"], "digest", subscription["recipient"], message.subject)
    if result.get("status") != "completed":
        database.update_delivery(delivery["id"], status="failed", error=result.get("error", "Run failed"))
        return {**result, "delivery": database.get_delivery(delivery["id"])}
    try:
        send_message(settings, subscription["recipient"], message)
    except Exception as exc:
        database.update_delivery(delivery["id"], status="failed", error=f"{type(exc).__name__}: {exc}")
    else:
        database.update_delivery(delivery["id"], status="sent", sent_at=datetime.now(timezone.utc).isoformat())
    return {**(database.get_run(run["id"]) or result), "delivery": database.get_delivery(delivery["id"])}
