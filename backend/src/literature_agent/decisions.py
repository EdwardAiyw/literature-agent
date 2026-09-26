from __future__ import annotations

import hashlib
import json
import math
import statistics
import time
from contextlib import AbstractContextManager
from typing import Any, Callable

import httpx

from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

from .config import Settings
from .db import Database

SCREEN_SCHEMA_VERSION = "paper-screen.v2"
EVIDENCE_SCHEMA_VERSION = "evidence-check.v2"
LOCALJEV_DEFAULT_URL = "http://127.0.0.1:8080"
LOCALJEV_MODEL_ALIASES = {"localjev-0.2", "localjev-latest", "jev-latest", "jev-preview"}


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
        if not self.settings.jev_enabled or not self.settings.jev_model:
            return False
        if self.provider == "typesafe_cloud":
            return bool(self.settings.jev_api_key or self.settings.jev_base_url)
        return self.provider in {"kev", "localjev", "custom"} and bool(self.settings.jev_base_url)

    @property
    def mode(self) -> str:
        return "shadow" if self.settings.jev_shadow_mode else "active"

    def _default_client(self) -> TypeSafeClient:
        return TypeSafeClient(api_key=self.settings.jev_api_key, model=self.settings.jev_model,
                              timeout=self.settings.jev_timeout_seconds,
                              base_url=self.settings.jev_base_url or None)

    @property
    def provider(self) -> str:
        value = self.settings.jev_provider.strip().lower()
        return {"typesafe": "typesafe_cloud", "local": "localjev"}.get(value, value or "typesafe_cloud")

    @property
    def probability_kind(self) -> str:
        return {"typesafe_cloud": "native", "kev": "calibrated", "localjev": "self_reported"}.get(self.provider, "unknown")

    @property
    def base_url(self) -> str:
        value = (self.settings.jev_base_url or "").rstrip("/")
        if value.endswith("/v1"):
            value = value[:-3]
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("Jev base URL must start with http:// or https://")
        return value

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.jev_api_key}"} if self.settings.jev_api_key else {}

    def _get_json(self, path: str, *, authenticated: bool = False, timeout: float = 5.0) -> dict:
        if not self.base_url:
            raise ValueError("JEV_BASE_URL is required for this Jev provider")
        headers = self._headers() if authenticated else {}
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(f"{self.base_url}{path}", headers=headers)
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise ValueError(f"Jev {path} response must be an object")
        return data

    def connection_status(self) -> dict:
        result = {
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.settings.jev_model,
            "configured": self.configured,
            "status": "disabled" if not self.settings.jev_enabled else "configured",
            "probability_kind": self.probability_kind,
        }
        if self.provider != "localjev":
            return result
        if not self.base_url:
            return {**result, "status": "unavailable", "detail": "LocalJev base URL is required"}
        try:
            health = self._get_json("/health")
            if health.get("status") != "ok":
                raise RuntimeError("LocalJev health check did not return status=ok")
            ready = self._get_json("/ready")
            if ready.get("status") != "ready":
                raise RuntimeError(str(ready.get("detail") or "LocalJev upstream model is unavailable"))
            models = self._get_json("/v1/models", authenticated=True)
            names = {item.get("name") for item in models.get("models", []) if isinstance(item, dict)}
            accepted = names | LOCALJEV_MODEL_ALIASES
            if self.settings.jev_model not in accepted:
                raise RuntimeError(f"LocalJev does not accept model {self.settings.jev_model!r}")
            return {**result, "status": "ready", "service": "LocalJev",
                    "upstream_model": ready.get("upstream_model", ""),
                    "available_models": sorted(name for name in names if name)}
        except Exception as exc:
            return {**result, "status": "unavailable", "service": "LocalJev",
                    "detail": f"{type(exc).__name__}: {exc}"}

    def _question_payload(self, questions: dict) -> dict:
        return {key: question.model_dump(mode="json", exclude_none=True) for key, question in questions.items()}

    def _http_system_one(self, state: dict, questions: dict) -> dict:
        if not self.base_url:
            raise ValueError("JEV_BASE_URL is required for HTTP Jev providers")
        payload = {"state": state, "questions": self._question_payload(questions), "model": self.settings.jev_model}
        with httpx.Client(timeout=self.settings.jev_timeout_seconds, follow_redirects=True) as client:
            response = client.post(f"{self.base_url}/v1/systemone", json=payload, headers=self._headers())
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
            raise ValueError("Jev response must contain an answers object")
        return data

    def _validate_answers(self, answers: dict, questions: dict) -> None:
        missing = sorted(set(questions) - set(answers))
        if missing:
            raise ValueError(f"Jev response missing answers: {', '.join(missing)}")
        extra = sorted(set(answers) - set(questions))
        if extra:
            raise ValueError(f"Jev response contains unexpected answers: {', '.join(extra)}")
        for key, question in questions.items():
            answer = answers[key]
            if not isinstance(answer, dict):
                raise ValueError(f"Jev answer {key} is not an object")
            question_type = question.model_dump(mode="json").get("type")
            if question_type == "score":
                if not isinstance(answer.get("score"), (int, float)) or not 0 <= float(answer["score"]) <= len(question.criteria) - 1:
                    raise ValueError(f"Jev answer {key} has an invalid score")
                if not isinstance(answer.get("confidence"), (int, float)) or not 0 <= float(answer["confidence"]) <= 1:
                    raise ValueError(f"Jev answer {key} has an invalid confidence")
            elif question_type == "choice":
                if answer.get("choice") not in question.criteria:
                    raise ValueError(f"Jev answer {key} has an invalid choice")
                if not isinstance(answer.get("confidence"), (int, float)) or not 0 <= float(answer["confidence"]) <= 1:
                    raise ValueError(f"Jev answer {key} has an invalid confidence")
            elif question_type == "noul":
                if not isinstance(answer.get("noul"), (int, float)) or not 0 <= float(answer["noul"]) <= 1:
                    raise ValueError(f"Jev answer {key} has an invalid noul value")
            probabilities = answer.get("probabilities")
            if question_type in {"score", "choice"} and not isinstance(probabilities, dict):
                raise ValueError(f"Jev answer {key} is missing probabilities")
            if isinstance(probabilities, dict) and probabilities:
                try:
                    values = {str(label): float(probability) for label, probability in probabilities.items()}
                except (TypeError, ValueError):
                    raise ValueError(f"Jev answer {key} has invalid probabilities") from None
                if not all(math.isfinite(value) and 0 <= value <= 1 for value in values.values()):
                    raise ValueError(f"Jev answer {key} has invalid probabilities")
                expected = ({str(index) for index in range(len(question.criteria))}
                            if question_type == "score" else set(question.criteria) if question_type == "choice" else set())
                if expected and set(values) != expected:
                    raise ValueError(f"Jev answer {key} probabilities do not match its criteria")
                total = sum(values.values())
                if total <= 0 or abs(total - 1) >= 0.02:
                    raise ValueError(f"Jev answer {key} has invalid probabilities")
                answer["probabilities"] = {label: value / total for label, value in values.items()}
                if question_type == "choice" and values[str(answer["choice"])] < max(values.values()) - 1e-6:
                    raise ValueError(f"Jev answer {key} choice does not match its highest probability")

    def _response_payload(self, response: Any, questions: dict, attempt_count: int = 1) -> dict:
        if isinstance(response, dict):
            model = response.get("model") or self.settings.jev_model
            answers = response.get("answers") or {}
            usage = response.get("usage") or {}
        else:
            model = response.model
            answers = {key: answer.model_dump(mode="json") for key, answer in response.answers.items()}
            usage = response.usage.model_dump(mode="json") if hasattr(response.usage, "model_dump") else response.usage
        self._validate_answers(answers, questions)
        probabilities = {key: answer.get("probabilities", {}) for key, answer in answers.items() if answer.get("probabilities")}
        return {"requested_model": self.settings.jev_model, "resolved_model": model,
                "answers": answers, "probabilities": probabilities,
                "input_tokens": int((usage or {}).get("input_tokens", 0)), "attempt_count": attempt_count,
                "provider": self.provider, "probability_kind": self.probability_kind}

    def _request(self, state: dict, questions: dict, schema_version: str) -> dict:
        state_hash = _hash(state)
        question_payload = self._question_payload(questions)
        cache_key = _hash({"provider": self.provider, "base_url": self.settings.jev_base_url,
                           "model": self.settings.jev_model, "schema": schema_version,
                           "state": state, "questions": question_payload})
        cached = self.database.get_decision_cache(cache_key)
        if cached:
            return {**cached, "state_hash": state_hash, "cached": True, "latency_ms": 0.0}
        started = time.perf_counter()
        attempts = 0
        last_error: Exception | None = None
        while attempts < 2:
            attempts += 1
            try:
                if self.provider == "typesafe_cloud":
                    with self.client_factory() as client:
                        response = client.system_one(state=state, questions=questions, model=self.settings.jev_model)
                else:
                    response = self._http_system_one(state, questions)
                payload = self._response_payload(response, questions, attempts)
                break
            except Exception as exc:
                last_error = exc
                if attempts >= 2:
                    raise
        else:
            raise last_error or RuntimeError("Jev request failed")
        self.database.save_decision_cache(cache_key, payload.get("resolved_model", self.settings.jev_model), schema_version, payload,
                                          self.settings.jev_cache_ttl_hours)
        return {**payload, "state_hash": state_hash, "cached": False,
                "latency_ms": (time.perf_counter() - started) * 1000}

    def _audit(self, run_id: str, stage: str, subject_id: str, schema: str,
               envelope: dict, outcome: dict, status: str | None = None, error: str = "") -> dict:
        failed = bool(error)
        confidence = float(outcome.get("decision_confidence", 0))
        if self.mode == "shadow":
            routing = "shadow_only"
        elif failed:
            routing = "fallback"
        elif confidence >= self.settings.jev_auto_threshold:
            routing = "auto_apply"
        elif confidence >= self.settings.jev_review_threshold:
            routing = "needs_review"
        else:
            routing = "fallback"
        fallback_used = self.mode == "active" and routing != "auto_apply"
        if failed:
            audit_status = "failed"
            fallback_reason = "jev_error"
        elif self.mode == "shadow":
            audit_status = "shadow_observed"
            fallback_reason = ""
        elif routing in {"needs_review", "fallback"}:
            audit_status = "fallback"
            fallback_reason = "low_confidence"
        else:
            audit_status = "applied"
            fallback_reason = ""
        return self.database.add_decision_call({
            "run_id": run_id, "stage": stage, "subject_id": subject_id, "mode": self.mode,
            "status": status or audit_status, "requested_model": self.settings.jev_model,
            "resolved_model": envelope.get("resolved_model", ""), "schema_version": schema,
            "state_hash": envelope.get("state_hash", ""), "answers": envelope.get("answers", {}),
            "outcome": outcome, "confidence": outcome.get("decision_confidence", 0),
            "latency_ms": envelope.get("latency_ms", 0), "input_tokens": envelope.get("input_tokens", 0),
            "cached": envelope.get("cached", False),
            "fallback_used": fallback_used, "fallback_reason": fallback_reason, "error": error,
            "provider": envelope.get("provider", self.provider), "probability_kind": envelope.get("probability_kind", self.probability_kind),
            "routing": routing, "probabilities": envelope.get("probabilities", {}),
            "attempt_count": envelope.get("attempt_count", 1), "validation_error": envelope.get("validation_error", ""),
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
                       "auto_eligible": confidence >= self.settings.jev_auto_threshold, "route": self._route(confidence), "engine": envelope["resolved_model"]}
            self._audit(run_id, "relevance_screener", subject, SCREEN_SCHEMA_VERSION, envelope, outcome)
            return outcome
        except Exception as exc:
            outcome = {"auto_eligible": False, "decision_confidence": 0.0}
            self._audit(run_id, "relevance_screener", subject, SCREEN_SCHEMA_VERSION,
                        {"state_hash": _hash(state), "attempt_count": 2,
                         "validation_error": str(exc) if isinstance(exc, ValueError) else ""},
                        outcome, "failed", f"{type(exc).__name__}: {exc}")
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
                       "route": self._route(confidence),
                       "engine": envelope["resolved_model"]}
            self._audit(run_id, "evidence_reviewer", subject, EVIDENCE_SCHEMA_VERSION, envelope, outcome)
            return outcome
        except Exception as exc:
            outcome = {"auto_eligible": False, "decision_confidence": 0.0}
            self._audit(run_id, "evidence_reviewer", subject, EVIDENCE_SCHEMA_VERSION,
                        {"state_hash": _hash(state), "attempt_count": 2,
                         "validation_error": str(exc) if isinstance(exc, ValueError) else ""},
                        outcome, "failed", f"{type(exc).__name__}: {exc}")
            raise

    def _route(self, confidence: float) -> str:
        if self.mode == "shadow":
            return "shadow_only"
        if confidence >= self.settings.jev_auto_threshold:
            return "auto_apply"
        if confidence >= self.settings.jev_review_threshold:
            return "needs_review"
        return "fallback"
