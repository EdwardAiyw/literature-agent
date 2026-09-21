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


class ModelProvider:
    def __init__(self, base_url: str, api_key: str, model: str, client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.client = client or httpx.Client(timeout=45)

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model)

    def summarize(self, record: dict, topic: str) -> dict[str, Any]:
        if not self.configured:
            return fallback(record, topic)
        system = """You are a cautious academic literature analyst. Return only valid JSON with these keys: research_problem, method, main_findings, limitations, relevance_reason, research_use, recommended_action, confidence, evidence_warnings. Use Chinese for analysis. Preserve technical names. Use 'not stated in source' when the title and abstract do not support a claim. Never invent findings."""
        user = json.dumps({"topic": topic, "paper": record}, ensure_ascii=False)
        response = self.client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "temperature": 0.1, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()
        content = content.removeprefix("```json").removesuffix("```").strip()
        result = json.loads(content)
        missing = [key for key in SUMMARY_KEYS if key not in result]
        if missing:
            raise ValueError(f"Model response missing keys: {', '.join(missing)}")
        result["engine"] = self.model
        return result
