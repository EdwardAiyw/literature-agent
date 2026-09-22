from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .db import Database
from .email import send_test_message
from .prompts import BUILTIN_PROMPTS
from .runner import execute_run, run_subscription
from .schemas import DeliveryRead, PaperRead, PromptCreate, PromptRead, ReviewRequest, RunArtifactRead, RunEventRead, RunRead, SubscriptionCreate, SubscriptionRead, SubscriptionUpdate, TaskBulkDelete, TaskCreate, TaskRead, TaskUpdate, TestSendRequest
from .sources import SOURCE_METADATA

settings = Settings.from_env()
database = Database(settings.db_path)
database.seed_builtin_prompts(BUILTIN_PROMPTS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.cleanup_test_tasks()
    yield


app = FastAPI(title="Literature Agent", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174", "http://localhost:5175", "http://127.0.0.1:5175"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "live": settings.live}


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
def start_run(task_id: str, background: BackgroundTasks):
    task = database.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    total_steps = 7 if task.get("evidence_review") else 6
    run = database.create_run(task_id, total_steps=total_steps)
    background.add_task(execute_run, settings, database, run["id"], task)
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
def run_subscription_now(subscription_id: str, background: BackgroundTasks):
    subscription = database.get_subscription(subscription_id)
    if not subscription:
        raise HTTPException(404, "Subscription not found")
    task = database.get_task(subscription["task_id"])
    if not task:
        raise HTTPException(404, "Subscription task not found")
    if not settings.live or not settings.llm_api_key or not settings.llm_model:
        raise HTTPException(409, "Configure LITERATURE_AGENT_LIVE, LLM_API_KEY, and LLM_MODEL before a subscription run")
    total_steps = 7 if task.get("evidence_review") else 6
    run = database.create_run(task["id"], total_steps=total_steps)
    background.add_task(run_subscription, settings, database, subscription, True, run["id"])
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


@app.get("/api/settings")
def get_settings():
    return {
        "live": settings.live,
        "llm_configured": bool(settings.llm_api_key and settings.llm_model),
        "smtp_configured": bool(settings.smtp_host and settings.smtp_from),
        "famou_enabled": settings.famou_enabled,
        "sources": [{"id": name, **metadata} for name, metadata in SOURCE_METADATA.items()],
        "runtime_nodes": ["query_planner", "retrieval", "dedupe", "relevance_screener", "literature_summarizer", "evidence_reviewer"],
    }
