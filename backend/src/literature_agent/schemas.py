from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .sources import SUPPORTED_SOURCES


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    topic: str = Field(min_length=1, max_length=1000)
    research_questions: list[str] = Field(default_factory=list)
    language: Literal["zh", "en", "bilingual"] = "bilingual"
    output_language: Literal["zh", "en", "bilingual"] = "zh"
    date_from: str = Field(default="", pattern=r"^$|^\d{4}-\d{2}-\d{2}$")
    date_to: str = Field(default="", pattern=r"^$|^\d{4}-\d{2}-\d{2}$")
    target_count: int = Field(default=10, ge=1, le=100)
    sources: list[str] = Field(default_factory=lambda: ["openalex", "crossref", "arxiv", "pubmed"])
    evidence_review: bool = False

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, sources: list[str]) -> list[str]:
        invalid = sorted(set(sources) - set(SUPPORTED_SOURCES))
        if invalid:
            raise ValueError(f"Unsupported source(s): {', '.join(invalid)}")
        return list(dict.fromkeys(sources))

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be before or equal to date_to")
        return self


DEFAULT_SOURCES = ["openalex", "crossref", "arxiv", "pubmed"]


class SubscriptionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    topic: str = Field(min_length=1, max_length=1000)
    research_questions: list[str] = Field(default_factory=list)
    language: Literal["zh", "en", "bilingual"] = "bilingual"
    output_language: Literal["zh", "en", "bilingual"] = "zh"
    date_from: str = Field(default="", pattern=r"^$|^\d{4}-\d{2}-\d{2}$")
    date_to: str = Field(default="", pattern=r"^$|^\d{4}-\d{2}-\d{2}$")
    target_count: int = Field(ge=1, le=100)
    sources: list[str] = Field(default_factory=lambda: list(DEFAULT_SOURCES))
    recipient: str = Field(min_length=3, max_length=320)
    schedule_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: str = Field(default="Asia/Hong_Kong", min_length=1, max_length=80)
    evidence_review: bool = False
    enabled: bool = True

    @field_validator("sources")
    @classmethod
    def validate_subscription_sources(cls, sources: list[str]) -> list[str]:
        invalid = sorted(set(sources) - set(SUPPORTED_SOURCES))
        if invalid:
            raise ValueError(f"Unsupported source(s): {', '.join(invalid)}")
        if not sources:
            raise ValueError("At least one source is required")
        return list(dict.fromkeys(sources))

    @field_validator("recipient")
    @classmethod
    def validate_recipient(cls, recipient: str) -> str:
        value = recipient.strip()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("recipient must be an email address")
        return value

    @model_validator(mode="after")
    def validate_subscription_dates(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be before or equal to date_to")
        return self


class SubscriptionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    topic: str | None = Field(default=None, min_length=1, max_length=1000)
    research_questions: list[str] | None = None
    language: Literal["zh", "en", "bilingual"] | None = None
    output_language: Literal["zh", "en", "bilingual"] | None = None
    date_from: str | None = Field(default=None, pattern=r"^$|^\d{4}-\d{2}-\d{2}$")
    date_to: str | None = Field(default=None, pattern=r"^$|^\d{4}-\d{2}-\d{2}$")
    target_count: int | None = Field(default=None, ge=1, le=100)
    sources: list[str] | None = None
    recipient: str | None = Field(default=None, min_length=3, max_length=320)
    schedule_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: str | None = Field(default=None, min_length=1, max_length=80)
    evidence_review: bool | None = None
    enabled: bool | None = None

    @field_validator("sources")
    @classmethod
    def validate_update_sources(cls, sources: list[str] | None) -> list[str] | None:
        if sources is None:
            return None
        invalid = sorted(set(sources) - set(SUPPORTED_SOURCES))
        if invalid:
            raise ValueError(f"Unsupported source(s): {', '.join(invalid)}")
        if not sources:
            raise ValueError("At least one source is required")
        return list(dict.fromkeys(sources))


class SubscriptionRead(SubscriptionCreate):
    id: str
    task_id: str
    created_at: datetime
    updated_at: datetime


class DeliveryRead(BaseModel):
    id: str
    subscription_id: str
    run_id: str | None = None
    kind: Literal["digest", "test"]
    status: Literal["pending", "sent", "failed"]
    recipient: str
    subject: str
    error: str = ""
    created_at: datetime
    sent_at: datetime | None = None


class TestSendRequest(BaseModel):
    recipient: str | None = Field(default=None, min_length=3, max_length=320)


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
    progress: int = 0
    total_steps: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RunEventRead(BaseModel):
    id: int
    run_id: str
    node: str
    status: str
    message: str
    artifact_type: str = ""
    created_at: datetime


class RunArtifactRead(BaseModel):
    run_id: str
    node: str
    payload: dict = Field(default_factory=dict)
    created_at: datetime


class PromptRead(BaseModel):
    id: str
    role: str
    version: str
    body: str
    builtin: bool


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
