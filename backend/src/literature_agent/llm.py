from __future__ import annotations

import json
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


class ModelProvider:
    def __init__(self, base_url: str, api_key: str, model: str, client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.client = client or httpx.Client(timeout=45)

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model)

    def _complete_json(self, system: str, payload: dict) -> dict[str, Any]:
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
        result = self._complete_json(prompt, {"task": task})
        required = ("queries", "exclusions", "language_policy", "source_routing")
        missing = [key for key in required if key not in result]
        if missing or not isinstance(result["queries"], list):
            raise ValueError(f"Query plan missing fields: {', '.join(missing)}")
        return {
            "queries": [str(query).strip() for query in result["queries"] if str(query).strip()],
            "exclusions": [str(term).strip() for term in result["exclusions"] if str(term).strip()],
            "language_policy": str(result["language_policy"]),
            "source_routing": [str(source).strip() for source in result["source_routing"] if str(source).strip()],
            "engine": self.model,
        }

    def screen(self, record: dict, task: dict, prompt: str) -> dict[str, Any]:
        if not self.configured:
            return fallback_screen(record, task["topic"])
        result = self._complete_json(prompt, {"task": task, "paper": record})
        required = ("relevance_score", "priority", "relevance_reason", "recommended_action")
        missing = [key for key in required if key not in result]
        if missing:
            raise ValueError(f"Screening result missing fields: {', '.join(missing)}")
        score = min(1.0, max(0.0, float(result["relevance_score"])))
        priority = str(result["priority"]).upper()
        if priority not in {"P0", "P1", "P2"}:
            priority = "P0" if score >= 0.7 else "P1" if score >= 0.4 else "P2"
        return {
            "relevance_score": score,
            "priority": priority,
            "relevance_reason": str(result["relevance_reason"]),
            "recommended_action": str(result["recommended_action"]),
            "engine": self.model,
        }

    def summarize(self, record: dict, topic: str, prompt: str = "") -> dict[str, Any]:
        if not self.configured:
            return fallback(record, topic)
        system = prompt or "You are a cautious academic literature analyst. Return only valid JSON with the documented summary fields."
        result = self._complete_json(system, {"topic": topic, "paper": record})
        missing = [key for key in SUMMARY_KEYS if key not in result]
        if missing:
            raise ValueError(f"Model response missing keys: {', '.join(missing)}")
        result["engine"] = self.model
        return result

    def review_evidence(self, record: dict, summary: dict, prompt: str) -> dict[str, Any]:
        if not self.configured:
            return fallback_evidence_review(record, summary)
        result = self._complete_json(prompt, {"paper": record, "summary": summary})
        if "evidence_warnings" not in result or "confidence" not in result or not isinstance(result["evidence_warnings"], list):
            raise ValueError("Evidence review missing evidence_warnings or confidence")
        return {
            "evidence_warnings": [str(warning) for warning in result["evidence_warnings"]],
            "confidence": min(1.0, max(0.0, float(result["confidence"]))),
            "engine": self.model,
        }
