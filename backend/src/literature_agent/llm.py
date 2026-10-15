from __future__ import annotations

import json
import math
import re
from typing import Any

import httpx

SUMMARY_KEYS = (
    "research_problem",
    "method",
    "main_findings",
    "limitations",
    "relevance_reason",
    "research_use",
    "recommended_action",
    "confidence",
    "evidence_warnings",
)

QUERY_EXECUTION_REQUIREMENTS = (
    "Search APIs consume keyword queries, not a prose description. Use 2-8 keywords per query, "
    "focused on the task's central concept and at most one additional facet. Do not pack every task "
    "subtopic into each query. For bilingual search, start with a short English query for the central "
    "research topic and a Chinese query for that same topic; any remaining queries may cover an explicitly "
    "requested facet. For English-only or Chinese-only tasks use only the requested language. "
    "Preserve task scope; do not invent exclusions or extra requirements."
)


def fallback(record: dict, topic: str) -> dict[str, Any]:
    return {
        "research_problem": record.get("abstract") or "not stated in source",
        "method": "not stated in source",
        "main_findings": ["not stated in source"],
        "limitations": ["Verify against the full paper."],
        "relevance_reason": f"Matched the configured topic: {topic}",
        "research_use": "candidate for user review",
        "recommended_action": "read",
        "confidence": 0.35,
        "evidence_warnings": ["Abstract-only analysis or fallback summary"],
        "engine": "fallback",
    }


def fallback_query_plan(task: dict) -> dict[str, Any]:
    queries = [task.get("topic", ""), *task.get("research_questions", [])]
    return {
        "queries": list(dict.fromkeys(query.strip() for query in queries if query.strip())),
        "exclusions": [],
        "language_policy": task.get("language", "bilingual"),
        "source_routing": task.get("sources", ["fixture"]),
        "engine": "fallback",
    }


def fallback_screen(record: dict, topic: str) -> dict[str, Any]:
    text = f"{record.get('title', '')} {record.get('abstract', '')}".lower()
    tokens = [token for token in topic.lower().split() if token]
    score = 0.8 if any(token in text for token in tokens[:3]) else 0.35
    return {
        "relevance_score": score,
        "priority": "P0" if score >= 0.7 else "P1" if score >= 0.4 else "P2",
        "relevance_reason": f"Matched the configured topic: {topic}",
        "recommended_action": "read" if score >= 0.7 else "background",
        "engine": "fallback",
    }


def fallback_evidence_review(record: dict, summary: dict) -> dict[str, Any]:
    warnings = list(summary.get("evidence_warnings", []))
    if not record.get("abstract"):
        warnings.append("No abstract was available for evidence review")
    return {
        "evidence_warnings": list(dict.fromkeys(warnings)),
        "confidence": summary.get("confidence", 0.35),
        "engine": "fallback",
    }


def validate_query_plan(result: dict, task: dict) -> dict[str, Any]:
    required = ("queries", "exclusions", "language_policy", "source_routing")
    if not isinstance(result, dict) or any(key not in result for key in required):
        raise ValueError("Query plan must contain queries, exclusions, language_policy and source_routing")
    for key in ("queries", "exclusions", "source_routing"):
        if not isinstance(result[key], list) or any(not isinstance(value, str) for value in result[key]):
            raise ValueError(f"Query plan {key} must be an array of strings")
    queries = list(dict.fromkeys(query.strip() for query in result["queries"] if query.strip()))
    if not 1 <= len(queries) <= 4:
        raise ValueError("Query plan must contain 1-4 distinct nonempty queries")
    language = task.get("language", "bilingual")
    has_chinese = [bool(re.search(r"[\u3400-\u9fff]", query)) for query in queries]
    has_english = [not chinese and bool(re.search(r"[A-Za-z]", query)) for query, chinese in zip(queries, has_chinese)]
    if language == "bilingual" and not (any(has_chinese) and any(has_english)):
        raise ValueError("Bilingual search requires separate Chinese and English queries, including an English query without Chinese text")
    if language == "en" and not all(has_english):
        raise ValueError("English search requires English queries without Chinese text")
    if language == "zh" and not all(has_chinese):
        raise ValueError("Chinese search requires Chinese wording in every query")
    if any(len(query.split()) > 16 or len(query) > 160 for query in queries):
        raise ValueError("Search queries are too long; split the topic into short complementary keyword queries")
    if result["language_policy"] != language:
        raise ValueError("Query plan language_policy must match task.language")
    return {
        "queries": queries, "exclusions": [term.strip() for term in result["exclusions"] if term.strip()],
        "language_policy": language, "source_routing": list(task.get("sources", result["source_routing"])),
    }


class ModelProvider:
    def __init__(self, base_url: str, api_key: str, model: str, client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        # Keep the offline/fallback path truly network-independent. Constructing
        # httpx.Client eagerly can fail when a machine advertises an optional
        # SOCKS proxy, even though no model request will ever be made.
        self.client = client

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model)

    def _complete_json(self, system: str, payload: dict) -> dict[str, Any]:
        if self.client is None:
            self.client = httpx.Client(timeout=45)
        response = self.client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "temperature": 0.1,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            },
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()
        content = content.removeprefix("```json").removesuffix("```").strip()
        return json.loads(content)

    def plan_queries(self, task: dict, prompt: str) -> dict[str, Any]:
        if not self.configured:
            return fallback_query_plan(task)
        payload = {"task": task, "execution_requirements": QUERY_EXECUTION_REQUIREMENTS}
        validation_errors = []
        for attempt in range(2):
            result = self._complete_json(prompt, payload)
            try:
                plan = validate_query_plan(result, task)
            except ValueError as exc:
                validation_errors.append(str(exc))
                if attempt == 1:
                    raise ValueError(f"Invalid query plan after repair: {exc}") from exc
                payload = {
                    "task": task, "previous_plan": result, "validation_error": str(exc),
                    "execution_requirements": QUERY_EXECUTION_REQUIREMENTS,
                    "repair_instruction": "Return the same JSON schema. Correct the validation error using only the task scope. "
                    "Use short complementary keyword queries, each focused on a core concept and at most one facet; "
                    "do not concatenate the whole topic or add new concepts. For bilingual search include separate "
                    "Chinese and English queries. Keep technical acronyms where needed, but English queries must contain no Chinese wording.",
                }
                continue
            return {**plan, "engine": self.model, "repair_count": attempt, "validation_errors": validation_errors,
                    "execution_requirements": QUERY_EXECUTION_REQUIREMENTS}
        raise AssertionError("Query plan attempts exhausted")

    def screen(self, record: dict, task: dict, prompt: str) -> dict[str, Any]:
        if not self.configured:
            return fallback_screen(record, task["topic"])
        result = self._complete_json(prompt, {"task": task, "paper": record})
        required = ("relevance_score", "priority", "relevance_reason", "recommended_action")
        missing = [key for key in required if key not in result]
        if missing:
            raise ValueError(f"Screening result missing fields: {', '.join(missing)}")
        raw_score = result["relevance_score"]
        if isinstance(raw_score, bool) or not math.isfinite(float(raw_score)) or not 0 <= float(raw_score) <= 1:
            raise ValueError("Screening relevance_score must be a finite number between 0 and 1")
        score = float(raw_score)
        priority = "P0" if score >= 0.7 else "P1" if score >= 0.4 else "P2"
        action = str(result["recommended_action"])
        if action not in {"read", "save", "background", "ignore"}:
            raise ValueError("Screening recommended_action must be read, save, background or ignore")
        return {
            "relevance_score": score,
            "priority": priority,
            "relevance_reason": str(result["relevance_reason"]),
            "recommended_action": action,
            "engine": self.model,
        }

    def summarize(self, record: dict, topic: str, prompt: str = "", *, task: dict | None = None) -> dict[str, Any]:
        if not self.configured:
            return fallback(record, topic)
        system = prompt or "You are a cautious academic literature analyst. Return only valid JSON with the documented summary fields."
        payload = {"topic": topic, "paper": record}
        if task is not None:
            payload["task"] = task
        result = self._complete_json(system, payload)
        missing = [key for key in SUMMARY_KEYS if key not in result]
        if missing:
            raise ValueError(f"Model response missing keys: {', '.join(missing)}")
        result["engine"] = self.model
        return result

    def review_evidence(self, record: dict, summary: dict, prompt: str, *, task: dict | None = None) -> dict[str, Any]:
        if not self.configured:
            return fallback_evidence_review(record, summary)
        payload = {"paper": record, "summary": summary}
        if task is not None:
            payload["task"] = task
        result = self._complete_json(prompt, payload)
        if "evidence_warnings" not in result or "confidence" not in result or not isinstance(result["evidence_warnings"], list):
            raise ValueError("Evidence review missing evidence_warnings or confidence")
        return {
            "evidence_warnings": [str(warning) for warning in result["evidence_warnings"]],
            "confidence": min(1.0, max(0.0, float(result["confidence"]))),
            "engine": self.model,
        }
