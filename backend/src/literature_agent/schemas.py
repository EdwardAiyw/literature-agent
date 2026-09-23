from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator

from .sources import SUPPORTED_SOURCES


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _clean_required(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("value must not be blank")
    return value


def _clean_questions(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _validate_date(value: str) -> str:
    if value:
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("date must be a valid ISO date") from exc
    return value


def _validate_email(value: str) -> str:
    value = value.strip()
    if not EMAIL_PATTERN.fullmatch(value):
        raise ValueError("recipient must be an email address")
    return value


def _validate_timezone(value: str) -> str:
    value = value.strip()
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("timezone must be a valid IANA timezone") from exc
    return value


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    topic: str = Field(min_length=1, max_length=1000)
    research_questions: list[str] = Field(default_factory=list)
    language: Literal["zh", "en", "bilingual"] = "bilingual"
    output_language: Literal["zh", "en", "bilingual"] = "zh"
    date_from: str = Field(default="", pattern=r"^$|^\d{4}-\d{2}-\d{2}$")
    date_to: str = Field(default="", pattern=r"^$|^\d{4}-\d{2}-\d{2}$")
    target_count: int = Field(default=10, ge=1, le=100)
    sources: list[str] = Field(default_factory=lambda: ["semantic_scholar", "openalex", "crossref", "arxiv", "pubmed"])
    evidence_review: bool = False
    prompt_overrides: dict[str, str] = Field(default_factory=dict)
    origin: Literal["user", "test", "subscription"] = "user"

    @field_validator("name", "topic")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _clean_required(value)

    @field_validator("research_questions")
    @classmethod
    def validate_questions(cls, values: list[str]) -> list[str]:
        return _clean_questions(values)

    @field_validator("date_from", "date_to")
    @classmethod
    def validate_dates(cls, value: str) -> str:
        return _validate_date(value)

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, sources: list[str]) -> list[str]:
        invalid = sorted(set(sources) - set(SUPPORTED_SOURCES))
        if invalid:
            raise ValueError(f"Unsupported source(s): {', '.join(invalid)}")
        if not sources:
            raise ValueError("At least one source is required")
        return list(dict.fromkeys(sources))

    @field_validator("prompt_overrides")
    @classmethod
    def validate_task_prompt_overrides(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_prompt_overrides(value)

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be before or equal to date_to")
        return self


class TaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    topic: str | None = Field(default=None, min_length=1, max_length=1000)
    research_questions: list[str] | None = None
    language: Literal["zh", "en", "bilingual"] | None = None
    output_language: Literal["zh", "en", "bilingual"] | None = None
    date_from: str | None = Field(default=None, pattern=r"^$|^\d{4}-\d{2}-\d{2}$")
    date_to: str | None = Field(default=None, pattern=r"^$|^\d{4}-\d{2}-\d{2}$")
    target_count: int | None = Field(default=None, ge=1, le=100)
    sources: list[str] | None = None
    evidence_review: bool | None = None
    prompt_overrides: dict[str, str] | None = None

    @field_validator("name", "topic")
    @classmethod
    def validate_required_text(cls, value: str | None) -> str | None:
        return _clean_required(value) if value is not None else None

    @field_validator("research_questions")
    @classmethod
    def validate_questions(cls, values: list[str] | None) -> list[str] | None:
        return _clean_questions(values) if values is not None else None

    @field_validator("date_from", "date_to")
    @classmethod
    def validate_dates(cls, value: str | None) -> str | None:
        return _validate_date(value) if value is not None else None

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, sources: list[str] | None) -> list[str] | None:
        if sources is None:
            return None
        invalid = sorted(set(sources) - set(SUPPORTED_SOURCES))
        if invalid:
            raise ValueError(f"Unsupported source(s): {', '.join(invalid)}")
        if not sources:
            raise ValueError("At least one source is required")
        return list(dict.fromkeys(sources))

    @field_validator("prompt_overrides")
    @classmethod
    def validate_prompt_overrides(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        return _validate_prompt_overrides(value) if value is not None else None

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be before or equal to date_to")
        return self


class TaskBulkDelete(BaseModel):
    task_ids: list[str] = Field(min_length=1, max_length=100)

    @field_validator("task_ids")
    @classmethod
    def validate_task_ids(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("task_ids must contain non-empty ids")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("task_ids must not contain duplicates")
        return cleaned


DEFAULT_SOURCES = ["semantic_scholar", "openalex", "crossref", "arxiv", "pubmed"]
PROMPT_ROLES = ("query_planner", "relevance_screener", "literature_summarizer", "evidence_reviewer")


def _validate_prompt_overrides(value: dict[str, str]) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("prompt_overrides must be an object")
    invalid = sorted(set(value) - set(PROMPT_ROLES))
    if invalid:
        raise ValueError(f"Unsupported prompt role(s): {', '.join(invalid)}")
    cleaned: dict[str, str] = {}
    for role, prompt_id in value.items():
        if not isinstance(prompt_id, str) or not prompt_id.strip():
            raise ValueError(f"Prompt override for {role} must be a non-empty prompt id")
        cleaned[role] = prompt_id.strip()
    return cleaned


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
    prompt_overrides: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("name", "topic")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _clean_required(value)

    @field_validator("research_questions")
    @classmethod
    def validate_questions(cls, values: list[str]) -> list[str]:
        return _clean_questions(values)

    @field_validator("date_from", "date_to")
    @classmethod
    def validate_dates(cls, value: str) -> str:
        return _validate_date(value)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        return _validate_timezone(value)

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
        return _validate_email(recipient)

    @model_validator(mode="after")
    def validate_subscription_dates(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be before or equal to date_to")
        return self

    @field_validator("prompt_overrides")
    @classmethod
    def validate_prompt_override_map(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_prompt_overrides(value)


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
    prompt_overrides: dict[str, str] | None = None
    enabled: bool | None = None

    @field_validator("name", "topic")
    @classmethod
    def validate_required_text(cls, value: str | None) -> str | None:
        return _clean_required(value) if value is not None else None

    @field_validator("research_questions")
    @classmethod
    def validate_questions(cls, values: list[str] | None) -> list[str] | None:
        return _clean_questions(values) if values is not None else None

    @field_validator("date_from", "date_to")
    @classmethod
    def validate_dates(cls, value: str | None) -> str | None:
        return _validate_date(value) if value is not None else None

    @field_validator("recipient")
    @classmethod
    def validate_recipient(cls, value: str | None) -> str | None:
        return _validate_email(value) if value is not None else None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        return _validate_timezone(value) if value is not None else None

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

    @field_validator("prompt_overrides")
    @classmethod
    def validate_update_prompt_overrides(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        return _validate_prompt_overrides(value) if value is not None else None


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

    @field_validator("recipient")
    @classmethod
    def validate_recipient(cls, value: str | None) -> str | None:
        return _validate_email(value) if value is not None else None


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
    trigger_kind: Literal["manual", "subscription"] = "manual"
    subscription_id: str | None = None
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


class DecisionCallRead(BaseModel):
    id: str
    run_id: str
    stage: str
    subject_id: str = ""
    mode: Literal["shadow", "active"]
    status: str
    requested_model: str
    resolved_model: str = ""
    schema_version: str
    state_hash: str
    answers: dict = Field(default_factory=dict)
    outcome: dict = Field(default_factory=dict)
    confidence: float = 0.0
    latency_ms: float = 0.0
    input_tokens: int = 0
    cached: bool = False
    fallback_used: bool = False
    error: str = ""
    created_at: datetime


class PromptRead(BaseModel):
    id: str
    role: str
    version: str
    body: str
    builtin: bool
    active: bool = False
    parent_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PromptCreate(BaseModel):
    role: Literal["query_planner", "relevance_screener", "literature_summarizer", "evidence_reviewer"]
    body: str = Field(min_length=1, max_length=20000)
    parent_id: str | None = None

    @field_validator("body")
    @classmethod
    def validate_body(cls, value: str) -> str:
        return _clean_required(value)


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
