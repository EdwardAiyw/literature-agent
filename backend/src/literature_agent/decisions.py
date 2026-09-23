from __future__ import annotations

import hashlib
import json
import statistics
import time
from contextlib import AbstractContextManager
from typing import Any, Callable

from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

from .config import Settings
from .db import Database

SCREEN_SCHEMA_VERSION = "paper-screen.v1"
EVIDENCE_SCHEMA_VERSION = "evidence-check.v1"


def _stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_stable(value).encode()).hexdigest()


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def _certainty(probability: float) -> float:
    return _clamp(abs(float(probability) - 0.5) * 2)


class JevDecisionProvider:
    """Versioned TypeSafe System One decisions with cache, confidence gates and audit."""

    def __init__(self, settings: Settings, database: Database,
                 client_factory: Callable[[], AbstractContextManager[Any]] | None = None) -> None:
        self.settings = settings
        self.database = database
        self.client_factory = client_factory or self._default_client

    @property
    def configured(self) -> bool:
        return bool(self.settings.jev_enabled and self.settings.jev_api_key and self.settings.jev_model)

    @property
    def mode(self) -> str:
        return "shadow" if self.settings.jev_shadow_mode else "active"

    def _default_client(self) -> TypeSafeClient:
        return TypeSafeClient(api_key=self.settings.jev_api_key, model=self.settings.jev_model,
                              timeout=self.settings.jev_timeout_seconds)

    def _request(self, state: dict, questions: dict, schema_version: str) -> dict:
        state_hash = _hash(state)
        question_payload = {key: question.model_dump(mode="json", exclude_none=True) for key, question in questions.items()}
        cache_key = _hash({"model": self.settings.jev_model, "schema": schema_version,
                           "state": state, "questions": question_payload})
        cached = self.database.get_decision_cache(cache_key)
        if cached:
            return {**cached, "state_hash": state_hash, "cached": True, "latency_ms": 0.0}
        started = time.perf_counter()
        with self.client_factory() as client:
            response = client.system_one(state=state, questions=questions, model=self.settings.jev_model)
        payload = {
            "requested_model": self.settings.jev_model,
            "resolved_model": response.model,
            "answers": {key: answer.model_dump(mode="json") for key, answer in response.answers.items()},
            "input_tokens": int(response.usage.input_tokens or 0),
        }
        self.database.save_decision_cache(cache_key, response.model, schema_version, payload,
                                          self.settings.jev_cache_ttl_hours)
        return {**payload, "state_hash": state_hash, "cached": False,
                "latency_ms": (time.perf_counter() - started) * 1000}

    def _audit(self, run_id: str, stage: str, subject_id: str, schema: str,
               envelope: dict, outcome: dict, status: str = "completed", error: str = "") -> None:
        self.database.add_decision_call({
            "run_id": run_id, "stage": stage, "subject_id": subject_id, "mode": self.mode,
            "status": status, "requested_model": self.settings.jev_model,
            "resolved_model": envelope.get("resolved_model", ""), "schema_version": schema,
            "state_hash": envelope.get("state_hash", ""), "answers": envelope.get("answers", {}),
            "outcome": outcome, "confidence": outcome.get("decision_confidence", 0),
            "latency_ms": envelope.get("latency_ms", 0), "input_tokens": envelope.get("input_tokens", 0),
            "cached": envelope.get("cached", False),
            "fallback_used": self.mode == "active" and not outcome.get("auto_eligible", False), "error": error,
        })

    def screen_paper(self, run_id: str, record: dict, task: dict) -> dict:
        subject = str(record.get("canonical_id") or record.get("source_id") or _hash(record.get("title", "")))
        state = {"task": {"topic": task.get("topic", ""), "research_questions": task.get("research_questions", [])},
                 "paper": {key: record.get(key, "") for key in ("title", "abstract", "published_date", "source", "venue")}}
        questions = {
            "topic_fit": Score(instructions="How directly does the paper address the task topic?",
                               criteria=["Unrelated", "Peripheral", "Directly relevant", "Central evidence"]),
            "question_fit": Score(instructions="How well can it answer a task research question?",
                                  criteria=["Cannot help", "Weak context", "Useful evidence", "Direct answer"]),
            "evidence": Score(instructions="How much usable evidence is in the title and abstract?",
                              criteria=["Insufficient", "Broad only", "Method or findings", "Substantially complete"]),
            "study_type": Choice(instructions="Primary study type?", criteria={
                "empirical": "Experiment or observed data", "review": "Synthesis of prior work",
                "method": "Method, system or algorithm", "dataset": "Dataset or benchmark",
                "opinion": "Commentary or position", "other": "No clear listed type"}),
            "directly_useful": Noul(instructions="Would a careful researcher keep this paper for the task?"),
        }
        try:
            envelope = self._request(state, questions, SCREEN_SCHEMA_VERSION)
            a = envelope["answers"]
            topic, question, evidence = (_clamp(float(a[key]["score"]) / 3)
                                         for key in ("topic_fit", "question_fit", "evidence"))
            useful = _clamp(a["directly_useful"]["noul"])
            relevance = _clamp(.5 * topic + .25 * question + .15 * evidence + .1 * useful)
            confidence = _clamp(statistics.fmean([a["topic_fit"]["confidence"], a["question_fit"]["confidence"],
                                                   a["evidence"]["confidence"], a["study_type"]["confidence"],
                                                   _certainty(useful)]))
            outcome = {"relevance_score": relevance, "priority": "P0" if relevance >= .8 else "P1" if relevance >= .55 else "P2",
                       "relevance_reason": f"Jev composite: topic {topic:.2f}, question {question:.2f}, evidence {evidence:.2f}.",
                       "recommended_action": "save" if relevance >= .85 else "read" if relevance >= .65 else "background" if relevance >= .4 else "ignore",
                       "study_type": a["study_type"]["choice"], "decision_confidence": confidence,
                       "auto_eligible": confidence >= self.settings.jev_auto_threshold, "engine": envelope["resolved_model"]}
            self._audit(run_id, "relevance_screener", subject, SCREEN_SCHEMA_VERSION, envelope, outcome)
            return outcome
        except Exception as exc:
            outcome = {"auto_eligible": False, "decision_confidence": 0.0}
            self._audit(run_id, "relevance_screener", subject, SCREEN_SCHEMA_VERSION,
                        {"state_hash": _hash(state)}, outcome, "failed", f"{type(exc).__name__}: {exc}")
            raise

    def review_evidence(self, run_id: str, record: dict, summary: dict) -> dict:
        subject = str(record.get("canonical_id") or record.get("source_id") or _hash(record.get("title", "")))
        state = {"paper": {"title": record.get("title", ""), "abstract": record.get("abstract", "")},
                 "summary": {key: summary.get(key, [] if key in {"main_findings", "limitations"} else "")
                             for key in ("research_problem", "method", "main_findings", "limitations")}}
        questions = {
            "claims_supported": Noul(instructions="Are summary claims supported by the abstract?"),
            "limitations_warranted": Noul(instructions="Are limitations cautious and warranted?"),
            "unsupported_specificity": Noul(instructions="Does the summary add unsupported specifics or numbers?"),
        }
        try:
            envelope = self._request(state, questions, EVIDENCE_SCHEMA_VERSION)
            a = envelope["answers"]
            supported, warranted, unsupported = (float(a[key]["noul"]) for key in questions)
            confidence = _clamp(statistics.fmean(map(_certainty, (supported, warranted, unsupported))))
            warnings = []
            if supported < .7: warnings.append("Jev found claims that may exceed the abstract.")
            if warranted < .7: warnings.append("Jev found limitations that may not be evidence-bounded.")
            if unsupported > .3: warnings.append("Jev detected potentially unsupported specificity.")
            outcome = {"evidence_warnings": warnings, "confidence": _clamp(statistics.fmean([supported, warranted, 1 - unsupported])),
                       "decision_confidence": confidence, "auto_eligible": confidence >= self.settings.jev_auto_threshold,
                       "engine": envelope["resolved_model"]}
            self._audit(run_id, "evidence_reviewer", subject, EVIDENCE_SCHEMA_VERSION, envelope, outcome)
            return outcome
        except Exception as exc:
            outcome = {"auto_eligible": False, "decision_confidence": 0.0}
            self._audit(run_id, "evidence_reviewer", subject, EVIDENCE_SCHEMA_VERSION,
                        {"state_hash": _hash(state)}, outcome, "failed", f"{type(exc).__name__}: {exc}")
            raise
