from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .db import Database
from .graph import build_graph
from .prompts import BUILTIN_PROMPTS
from .schemas import PaperRead, ReviewRequest, RunRead, TaskCreate, TaskRead

settings = Settings.from_env()
database = Database(settings.db_path)


def execute_run(run_id: str, task: dict) -> None:
    try:
        graph = build_graph(settings, database)
        graph.invoke({"task": task, "run_id": run_id, "errors": []})
    except Exception as exc:
        database.update_run(run_id, status="failed", current_node="failed", error=f"{type(exc).__name__}: {exc}")


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    database.close()


app = FastAPI(title="Literature Agent", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "live": settings.live}


@app.post("/api/tasks", response_model=TaskRead)
def create_task(payload: TaskCreate):
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


@app.post("/api/tasks/{task_id}/runs", response_model=RunRead, status_code=202)
def start_run(task_id: str, background: BackgroundTasks):
    task = database.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    run = database.create_run(task_id)
    background.add_task(execute_run, run["id"], task)
    return run


@app.get("/api/runs/{run_id}", response_model=RunRead)
def get_run(run_id: str):
    run = database.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


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


@app.get("/api/prompts")
def list_prompts():
    return BUILTIN_PROMPTS


@app.get("/api/settings")
def get_settings():
    return {"live": settings.live, "llm_configured": bool(settings.llm_api_key and settings.llm_model), "sources": ["fixture", "openalex"]}
