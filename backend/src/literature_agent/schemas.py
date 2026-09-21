from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    topic: str = Field(min_length=1, max_length=1000)
    research_questions: list[str] = Field(default_factory=list)
    language: Literal["zh", "en", "bilingual"] = "bilingual"
    output_language: Literal["zh", "en", "bilingual"] = "zh"
    date_from: str = ""
    date_to: str = ""
    target_count: int = Field(default=10, ge=1, le=100)
    sources: list[str] = Field(default_factory=lambda: ["fixture"])
    evidence_review: bool = False


class TaskRead(TaskCreate):
    id: str
    created_at: datetime
    updated_at: datetime


class RunRead(BaseModel):
    id: str
    task_id: str
    status: Literal["queued", "running", "paused", "completed", "failed", "cancelled"]
    current_node: str = ""
    paper_count: int = 0
    error: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None


class PaperRead(BaseModel):
    id: str
    run_id: str
    title: str
    authors: list[str]
    abstract: str
    published_date: str
    source: str
    doi: str = ""
    official_url: str = ""
    open_access_url: str = ""
    relevance_score: float = 0.0
    priority: str = "P2"
    language: str = "unknown"
    summary: dict = Field(default_factory=dict)
    review: str = "unreviewed"


class ReviewRequest(BaseModel):
    review: Literal["unreviewed", "read", "save", "background", "ignore"]
