from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, time, timezone
from pathlib import Path
from dataclasses import replace
import os
import shutil
import subprocess
import sys
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import ConfigManager, SECRET_FIELDS, SETTING_FIELDS, Settings, save_bootstrap_data_dir
from . import __version__
from .db import Database
from .email import send_test_message
from .llm import ModelProvider
from .prompts import BUILTIN_PROMPTS
from .schemas import BackupRestoreRequest, DataDirectoryRequest, DecisionCallRead, DeliveryRead, PaperRead, PromptCreate, PromptRead, ReviewRequest, RunArtifactRead, RunEventRead, RunRead, SettingsTestRequest, SettingsUpdate, SubscriptionCreate, SubscriptionRead, SubscriptionUpdate, TaskBulkDelete, TaskCreate, TaskRead, TaskUpdate, TestSendRequest
from .sources import SOURCE_METADATA, build_sources
from .system_ops import run_scheduler_action, scheduler_status
from .worker import LocalRunWorker

config_manager = ConfigManager(Settings.from_env())
settings = config_manager.get()
database = Database(settings.db_path)
database.seed_builtin_prompts(BUILTIN_PROMPTS)
run_worker: LocalRunWorker | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global run_worker
    database.cleanup_test_tasks()
    run_worker = LocalRunWorker(lambda: settings, database)
    run_worker.recover()
    try:
        yield
    finally:
        run_worker.close()
        run_worker = None


app = FastAPI(title="Literature Agent", version=__version__, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174", "http://localhost:5175", "http://127.0.0.1:5175"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def protect_local_writes(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin", "")
        allowed = {f"http://127.0.0.1:{request.url.port or 80}", f"http://localhost:{request.url.port or 80}",
                   "http://127.0.0.1:5175", "http://localhost:5175"}
        if origin and origin not in allowed:
            return JSONResponse({"detail": "Cross-origin writes are not allowed"}, status_code=403)
    return await call_next(request)


def mount_frontend(target: FastAPI, directory: Path) -> bool:
    """Serve a built frontend when present without making it a backend-test dependency."""
    index = directory / "index.html"
    if not index.is_file():
        return False
    target.mount("/", StaticFiles(directory=directory, html=True), name="frontend")
    return True


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "live": settings.live, "database": database.health(), "worker": run_worker is not None, "jev_enabled": settings.jev_enabled, "jev_configured": bool(settings.jev_enabled and settings.jev_api_key)}


@app.post("/api/tasks", response_model=TaskRead)
def create_task(payload: TaskCreate):
    _validate_prompt_overrides(payload.prompt_overrides)
    return database.create_task(payload.model_dump())


@app.get("/api/tasks", response_model=list[TaskRead])
def list_tasks():
    return database.list_tasks()


@app.get("/api/tasks/{task_id}", response_model=TaskRead)
def get_task(task_id: str):
    task = database.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task


@app.patch("/api/tasks/{task_id}", response_model=TaskRead)
def update_task(task_id: str, patch: TaskUpdate):
    current = database.get_task(task_id)
    if not current:
        raise HTTPException(404, "Task not found")
    blockers = database.task_blockers(task_id)
    if blockers["subscribed"]:
        raise HTTPException(409, "Task is managed by a subscription; edit it from the subscriptions page")
    if blockers["active_runs"]:
        raise HTTPException(409, "Task cannot be edited while a run is queued, running, or paused")
    values = {**current, **patch.model_dump(exclude_none=True)}
    validated = TaskCreate.model_validate(values).model_dump()
    _validate_prompt_overrides(validated["prompt_overrides"])
    return database.update_task(task_id, validated)


@app.post("/api/tasks/bulk-delete")
def bulk_delete_tasks(payload: TaskBulkDelete):
    outcome = database.delete_tasks(payload.task_ids)
    if outcome["status"] == "missing":
        raise HTTPException(404, {"message": "One or more tasks were not found", "task_ids": outcome["task_ids"]})
    if outcome["status"] == "blocked":
        raise HTTPException(409, {"message": "Batch deletion was not performed", "subscribed": outcome["subscribed"], "active": outcome["active"]})
    return outcome


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str):
    outcome = database.delete_task(task_id)
    if outcome == "missing":
        raise HTTPException(404, "Task not found")
    if outcome == "subscribed":
        raise HTTPException(409, "Task is referenced by a subscription; delete the subscription first")
    if outcome == "active":
        raise HTTPException(409, "Task cannot be deleted while a run is queued, running, or paused")
    return {"status": "deleted", "task_id": task_id}


@app.get("/api/tasks/{task_id}/runs", response_model=list[RunRead])
def list_task_runs(task_id: str, limit: int = Query(default=20, ge=1, le=100)):
    if not database.get_task(task_id):
        raise HTTPException(404, "Task not found")
    return database.list_runs(task_id, limit)


@app.post("/api/tasks/{task_id}/runs", response_model=RunRead, status_code=202)
def start_run(task_id: str):
    task = database.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    total_steps = 7 if task.get("evidence_review") else 6
    run = database.create_run_if_idle(task_id, total_steps=total_steps)
    if not run:
        raise HTTPException(409, "This task already has an active run")
    if run_worker is None:
        raise HTTPException(503, "Run worker is not available")
    run_worker.submit_task(run["id"], task)
    return run


def _task_payload(payload: dict) -> dict:
    return {key: payload[key] for key in ("name", "topic", "research_questions", "language", "output_language", "date_from", "date_to", "target_count", "sources", "evidence_review", "prompt_overrides")} | {"origin": "subscription"}


def _validate_prompt_overrides(overrides: dict[str, str]) -> None:
    for role, prompt_id in overrides.items():
        prompt = database.get_prompt(prompt_id)
        if not prompt:
            raise HTTPException(422, f"Prompt not found: {prompt_id}")
        if prompt["role"] != role:
            raise HTTPException(422, f"Prompt {prompt_id} does not belong to role {role}")


@app.post("/api/subscriptions", response_model=SubscriptionRead, status_code=201)
def create_subscription(payload: SubscriptionCreate):
    values = payload.model_dump()
    _validate_prompt_overrides(values["prompt_overrides"])
    task = database.create_task(_task_payload(values))
    return database.create_subscription(task["id"], values)


@app.get("/api/subscriptions", response_model=list[SubscriptionRead])
def list_subscriptions():
    return database.list_subscriptions()


@app.get("/api/subscriptions/{subscription_id}", response_model=SubscriptionRead)
def get_subscription(subscription_id: str):
    subscription = database.get_subscription(subscription_id)
    if not subscription:
        raise HTTPException(404, "Subscription not found")
    return subscription


@app.patch("/api/subscriptions/{subscription_id}", response_model=SubscriptionRead)
def update_subscription(subscription_id: str, patch: SubscriptionUpdate):
    current = database.get_subscription(subscription_id)
    if not current:
        raise HTTPException(404, "Subscription not found")
    values = {**current, **{key: value for key, value in patch.model_dump().items() if value is not None}}
    values.pop("id", None)
    values.pop("task_id", None)
    values.pop("created_at", None)
    values.pop("updated_at", None)
    validated = SubscriptionCreate.model_validate(values).model_dump()
    _validate_prompt_overrides(validated["prompt_overrides"])
    updated = database.update_subscription(subscription_id, validated)
    database.update_task(current["task_id"], _task_payload(validated))
    return updated


@app.delete("/api/subscriptions/{subscription_id}")
def delete_subscription(subscription_id: str):
    if not database.delete_subscription(subscription_id):
        raise HTTPException(404, "Subscription not found")
    return {"status": "deleted", "subscription_id": subscription_id}


@app.get("/api/deliveries", response_model=list[DeliveryRead])
def list_deliveries(subscription_id: str | None = None, limit: int = Query(default=50, ge=1, le=100)):
    return database.list_deliveries(subscription_id, limit)


@app.post("/api/subscriptions/{subscription_id}/runs", response_model=RunRead, status_code=202)
def run_subscription_now(subscription_id: str):
    subscription = database.get_subscription(subscription_id)
    if not subscription:
        raise HTTPException(404, "Subscription not found")
    task = database.get_task(subscription["task_id"])
    if not task:
        raise HTTPException(404, "Subscription task not found")
    if not settings.live or not settings.llm_api_key or not settings.llm_model:
        raise HTTPException(409, "Configure LITERATURE_AGENT_LIVE, LLM_API_KEY, and LLM_MODEL before a subscription run")
    total_steps = 7 if task.get("evidence_review") else 6
    local_now = datetime.now(timezone.utc).astimezone(ZoneInfo(subscription["timezone"]))
    local_day_start = datetime.combine(local_now.date(), time.min, tzinfo=local_now.tzinfo).astimezone(timezone.utc).isoformat()
    run = database.create_run_if_idle(task["id"], total_steps=total_steps, trigger_kind="subscription", subscription_id=subscription_id, not_before=local_day_start)
    if not run:
        raise HTTPException(409, "This subscription is already active or has run today")
    if run_worker is None:
        raise HTTPException(503, "Run worker is not available")
    run_worker.submit_subscription(run["id"], subscription)
    return run


@app.post("/api/subscriptions/{subscription_id}/test-send", response_model=DeliveryRead, status_code=202)
def test_send(subscription_id: str, payload: TestSendRequest | None = None):
    subscription = database.get_subscription(subscription_id)
    if not subscription:
        raise HTTPException(404, "Subscription not found")
    recipient = (payload.recipient if payload else None) or subscription["recipient"]
    subject = "[Literature Agent] SMTP test"
    delivery = database.create_delivery(subscription_id, None, "test", recipient, subject)
    try:
        send_test_message(settings, recipient)
    except Exception as exc:
        return database.update_delivery(delivery["id"], status="failed", error=f"{type(exc).__name__}: {exc}")
    return database.update_delivery(delivery["id"], status="sent", sent_at=datetime.now(timezone.utc).isoformat())


@app.get("/api/runs/{run_id}", response_model=RunRead)
def get_run(run_id: str):
    run = database.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@app.get("/api/runs/{run_id}/events", response_model=list[RunEventRead])
def list_run_events(run_id: str):
    if not database.get_run(run_id):
        raise HTTPException(404, "Run not found")
    return database.list_run_events(run_id)


@app.get("/api/runs/{run_id}/artifacts", response_model=list[RunArtifactRead])
def list_run_artifacts(run_id: str):
    if not database.get_run(run_id):
        raise HTTPException(404, "Run not found")
    return database.list_run_artifacts(run_id)


@app.get("/api/runs/{run_id}/papers", response_model=list[PaperRead])
def list_papers(run_id: str):
    if not database.get_run(run_id):
        raise HTTPException(404, "Run not found")
    return database.list_papers(run_id)


@app.get("/api/runs/{run_id}/decisions", response_model=list[DecisionCallRead])
def list_run_decisions(run_id: str):
    if not database.get_run(run_id):
        raise HTTPException(404, "Run not found")
    return database.list_decision_calls(run_id)


@app.post("/api/papers/{paper_id}/review")
def review_paper(paper_id: str, payload: ReviewRequest):
    if not database.review_paper(paper_id, payload.review):
        raise HTTPException(404, "Paper not found")
    return {"status": "ok", "review": payload.review}


@app.get("/api/prompts", response_model=list[PromptRead])
def list_prompts():
    return database.list_prompts()


@app.post("/api/prompts", response_model=PromptRead, status_code=201)
def create_prompt(payload: PromptCreate):
    if payload.parent_id:
        parent = database.get_prompt(payload.parent_id)
        if not parent or parent["role"] != payload.role:
            raise HTTPException(422, "parent_id must reference a prompt from the same role")
    return database.create_prompt_override(payload.role, payload.body, payload.parent_id)


@app.post("/api/prompts/{prompt_id}/activate", response_model=PromptRead)
def activate_prompt(prompt_id: str):
    prompt = database.get_prompt(prompt_id)
    if not prompt:
        raise HTTPException(404, "Prompt not found")
    return database.activate_prompt(prompt_id)


@app.delete("/api/prompts/{prompt_id}")
def delete_prompt(prompt_id: str):
    prompt = database.get_prompt(prompt_id)
    if not prompt:
        raise HTTPException(404, "Prompt not found")
    if prompt["builtin"]:
        raise HTTPException(409, "Built-in prompts cannot be deleted")
    database.delete_prompt_override(prompt_id)
    return {"status": "deleted", "prompt_id": prompt_id}


SETTING_SECTIONS = {
    "llm": {"live", "llm_base_url", "llm_model", "llm_api_key"},
    "smtp": {"smtp_host", "smtp_port", "smtp_username", "smtp_password", "smtp_from", "smtp_starttls", "smtp_ssl"},
    "sources": {"openalex_api_key", "semantic_scholar_api_key", "pubmed_api_key", "pubmed_email"},
    "jev": {"jev_enabled", "jev_shadow_mode", "jev_api_key", "jev_model", "jev_timeout_seconds", "jev_auto_threshold", "jev_review_threshold"},
    "runtime": {"source_cache_ttl_hours", "source_daily_request_budget"},
}


def _public_settings() -> dict:
    return {
        "version": __version__,
        "license": "AGPL-3.0-only",
        "source_url": "https://github.com/EdwardAiyw/literature-agent",
        "live": settings.live,
        "data_dir": str(settings.data_dir),
        "llm_base_url": settings.llm_base_url,
        "llm_model": settings.llm_model,
        "llm_configured": bool(settings.llm_api_key and settings.llm_model),
        "smtp_host": settings.smtp_host,
        "smtp_port": settings.smtp_port,
        "smtp_username": settings.smtp_username,
        "smtp_from": settings.smtp_from,
        "smtp_starttls": settings.smtp_starttls,
        "smtp_ssl": settings.smtp_ssl,
        "smtp_configured": bool(settings.smtp_host and settings.smtp_from),
        "openalex_configured": bool(settings.openalex_api_key),
        "semantic_scholar_configured": bool(settings.semantic_scholar_api_key),
        "pubmed_configured": bool(settings.pubmed_api_key),
        "pubmed_email": settings.pubmed_email,
        "jev_enabled": settings.jev_enabled,
        "jev_configured": bool(settings.jev_enabled and settings.jev_api_key),
        "jev_shadow_mode": settings.jev_shadow_mode,
        "jev_model": settings.jev_model,
        "jev_timeout_seconds": settings.jev_timeout_seconds,
        "jev_auto_threshold": settings.jev_auto_threshold,
        "jev_review_threshold": settings.jev_review_threshold,
        "source_cache_ttl_hours": settings.source_cache_ttl_hours,
        "source_daily_request_budget": settings.source_daily_request_budget,
        "source_usage": database.source_usage_snapshot(),
        "famou_enabled": settings.famou_enabled,
        "sources": [{"id": name, **metadata} for name, metadata in SOURCE_METADATA.items()],
        "runtime_nodes": ["query_planner", "retrieval", "dedupe", "relevance_screener", "literature_summarizer", "evidence_reviewer"],
    }


@app.get("/api/settings")
def get_settings():
    return _public_settings()


def _section_values(section: str, payload: SettingsUpdate) -> tuple[dict, dict]:
    allowed = SETTING_SECTIONS.get(section)
    if not allowed:
        raise HTTPException(404, "Unknown settings section")
    supplied = payload.model_dump(exclude_none=True)
    invalid = set(supplied) - allowed
    if invalid:
        raise HTTPException(422, f"Setting(s) do not belong to {section}: {', '.join(sorted(invalid))}")
    secrets = {key: supplied.pop(key) for key in list(supplied) if key in SECRET_FIELDS}
    return supplied, secrets


@app.put("/api/settings/{section}")
def update_settings(section: str, payload: SettingsUpdate):
    global settings
    values, secrets = _section_values(section, payload)
    candidate = replace(settings, **values, **{key: value for key, value in secrets.items() if value})
    if candidate.smtp_ssl and candidate.smtp_starttls:
        raise HTTPException(422, "SMTP SSL and STARTTLS cannot both be enabled")
    if candidate.jev_auto_threshold < candidate.jev_review_threshold:
        raise HTTPException(422, "Jev auto threshold must be greater than or equal to review threshold")
    try:
        settings = config_manager.update(values, secrets)
    except (OSError, ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return _public_settings()


@app.delete("/api/settings/secrets/{secret_name}")
def clear_setting_secret(secret_name: str):
    global settings
    if secret_name not in SECRET_FIELDS:
        raise HTTPException(404, "Unknown secret")
    try:
        settings = config_manager.update({}, {secret_name: ""})
    except (OSError, ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return _public_settings()


@app.post("/api/settings/{section}/test")
def test_settings(section: str, payload: SettingsTestRequest):
    values, secrets = _section_values(section, SettingsUpdate.model_validate(payload.model_dump(exclude={"recipient"})))
    candidate_values = {**values, **{key: value for key, value in secrets.items() if value != ""}}
    candidate = replace(settings, **candidate_values)
    try:
        if section == "llm":
            if not candidate.llm_api_key or not candidate.llm_model:
                raise ValueError("API Key and model are required")
            result = ModelProvider(candidate.llm_base_url, candidate.llm_api_key, candidate.llm_model)._complete_json(
                "Return only this JSON object: {\"status\":\"ok\"}", {"test": "Literature Agent connection"}
            )
            if result.get("status") != "ok":
                raise ValueError("The model returned an unexpected response")
        elif section == "smtp":
            recipient = payload.recipient or candidate.smtp_from
            if not recipient:
                raise ValueError("A test recipient or sender address is required")
            send_test_message(candidate, recipient)
        elif section == "sources":
            diagnostics = {}
            with httpx.Client(timeout=20, follow_redirects=True) as client:
                for name, source in build_sources(client, candidate).items():
                    try:
                        records = source.search(("retrieval augmented generation",), 1, "", "")
                        diagnostics[name] = {"ok": True, "count": len(records)}
                    except Exception as exc:
                        diagnostics[name] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            if not any(item["ok"] for item in diagnostics.values()):
                raise RuntimeError("All literature source checks failed")
            return {"status": "ok", "section": section, "diagnostics": diagnostics}
        elif section == "jev":
            if candidate.jev_enabled and not candidate.jev_api_key:
                raise ValueError("Jev API Key is required when Jev is enabled")
        elif section != "runtime":
            raise HTTPException(404, "Unknown settings section")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"{type(exc).__name__}: {exc}") from exc
    return {"status": "ok", "section": section}


@app.get("/api/onboarding")
def onboarding_status():
    schedule = scheduler_status()
    tasks = {item.get("name") for item in schedule.get("tasks", [])}
    steps = {
        "data": settings.data_dir.exists() and database.health()["writable"],
        "llm": bool(settings.live and settings.llm_api_key and settings.llm_model),
        "smtp": bool(settings.smtp_host and settings.smtp_from),
        "sources": True,
        "scheduler": set(schedule.get("tasks") and ("Literature Agent Local", "Literature Agent Daily") or ()).issubset(tasks),
    }
    return {"complete": all(steps.values()), "steps": steps, "data_dir": str(settings.data_dir)}


@app.post("/api/system/select-data-directory")
def select_data_directory():
    if os.name != "nt":
        raise HTTPException(400, "The native directory picker is only available on Windows")
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(title="选择 Literature Agent 数据目录", initialdir=str(settings.data_dir))
        root.destroy()
    except Exception as exc:
        raise HTTPException(400, f"Could not open directory picker: {exc}") from exc
    return {"path": selected}


@app.post("/api/system/select-backup")
def select_backup_file():
    if os.name != "nt":
        raise HTTPException(400, "The native file picker is only available on Windows")
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askopenfilename(
            title="选择 Literature Agent 备份",
            initialdir=str(settings.data_dir / "backups"),
            filetypes=[("SQLite backup", "*.db"), ("All files", "*.*")],
        )
        root.destroy()
    except Exception as exc:
        raise HTTPException(400, f"Could not open backup picker: {exc}") from exc
    return {"path": selected}


@app.put("/api/system/data-directory")
def change_data_directory(payload: DataDirectoryRequest):
    global config_manager, settings, database, run_worker
    target = Path(payload.path).expanduser().resolve()
    if target == settings.data_dir.resolve():
        return {"status": "ok", "path": str(target)}
    if database.list_recoverable_runs():
        raise HTTPException(409, "Cannot move data while a run is active")
    try:
        target.mkdir(parents=True, exist_ok=True)
        probe = target / ".literature-agent-write-test"
        probe.write_text("ok", encoding="ascii")
        probe.unlink()
        target_db = target / "literature_agent_v2.db"
        if target_db.exists():
            Database.validate_backup(target_db)
        else:
            database.backup(target_db)
        old_values = {key: getattr(settings, key) for key in SETTING_FIELDS}
        base = replace(settings, data_dir=target, db_path=target_db)
        new_manager = ConfigManager(base, config_manager.secret_store)
        new_manager.update(old_values)
        new_settings = new_manager.get()
        new_database = Database(new_settings.db_path)
        new_database.seed_builtin_prompts(BUILTIN_PROMPTS)
        if run_worker:
            run_worker.close()
        database.close()
        save_bootstrap_data_dir(target)
        config_manager, settings, database = new_manager, new_settings, new_database
        run_worker = LocalRunWorker(lambda: settings, database)
    except Exception as exc:
        raise HTTPException(400, f"Could not use the selected data directory: {exc}") from exc
    return {"status": "ok", "path": str(target)}


@app.get("/api/scheduler")
def get_scheduler_status():
    return scheduler_status()


@app.get("/api/update")
def check_update():
    try:
        response = httpx.get("https://api.github.com/repos/EdwardAiyw/literature-agent/releases/latest", timeout=10,
                             headers={"Accept": "application/vnd.github+json", "User-Agent": "Literature-Agent"})
        if response.status_code == 404:
            raise HTTPException(503, "GitHub Release is unavailable. This repository may be private; check with the distributor for updates.")
        response.raise_for_status()
        release = response.json()
        latest = str(release.get("tag_name", "")).lstrip("v")
        return {"current": __version__, "available": bool(latest and latest != __version__),
                "latest": latest, "url": release.get("html_url", "")}
    except Exception as exc:
        raise HTTPException(503, f"Could not check GitHub Releases: {type(exc).__name__}: {exc}") from exc


@app.post("/api/scheduler/{action}")
def manage_scheduler(action: str):
    try:
        runtime_root = Path(sys.executable).parent if getattr(sys, "frozen", False) else settings.root.parent
        return run_scheduler_action(runtime_root, action)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/backups")
def create_backup():
    target = settings.data_dir / "backups" / f"literature-agent-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
    database.backup(target)
    return {"status": "ok", "path": str(target)}


@app.post("/api/backups/restore")
def restore_backup(payload: BackupRestoreRequest):
    global database, run_worker
    source = Path(payload.path).expanduser().resolve()
    try:
        Database.validate_backup(source)
    except (OSError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    if database.list_recoverable_runs():
        raise HTTPException(409, "Cannot restore while a run is active")
    safety = settings.data_dir / "backups" / f"before-restore-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
    database.backup(safety)
    if run_worker:
        run_worker.close()
    database.close()
    shutil.copy2(source, settings.db_path)
    database = Database(settings.db_path)
    database.seed_builtin_prompts(BUILTIN_PROMPTS)
    run_worker = LocalRunWorker(lambda: settings, database)
    return {"status": "ok", "safety_backup": str(safety)}


# Keep this mount last so /api routes always win. The backend remains testable in
# clean checkouts where the ignored frontend/dist directory has not been built.
mount_frontend(app, settings.root.parent / "frontend" / "dist")
