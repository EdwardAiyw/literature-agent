from __future__ import annotations

BUILTIN_PROMPTS = [
    {
        "id": "query_planner.v1",
        "role": "query_planner",
        "version": "v1",
        "builtin": True,
        "body": "Convert the user's topic into a cautious academic search plan. Return only JSON with queries, exclusions, language_policy, and source_routing. Preserve the user's scope and do not introduce research claims.",
    },
    {
        "id": "relevance_screener.v1",
        "role": "relevance_screener",
        "version": "v1",
        "builtin": True,
        "body": "Assess whether the supplied title and abstract directly serve the task topic. Return only JSON with relevance_score, priority, relevance_reason, and recommended_action. Ground every reason in the supplied paper metadata.",
    },
    {
        "id": "literature_summarizer.v1",
        "role": "literature_summarizer",
        "version": "v1",
        "builtin": True,
        "body": "Summarize only the supplied title and abstract. Return only one JSON object with exactly these keys: research_problem (string), method (string), main_findings (array of strings), limitations (array of strings), relevance_reason (string), research_use (string), recommended_action (string), confidence (number from 0 to 1), and evidence_warnings (array of strings). Use 'not stated in source' when needed. Do not add markdown, nesting, or extra keys.",
    },
    {
        "id": "evidence_reviewer.v1",
        "role": "evidence_reviewer",
        "version": "v1",
        "builtin": True,
        "body": "Check the supplied summary against the supplied title and abstract. Return only JSON with evidence_warnings and confidence. Flag unsupported, over-specific, or temporally ambiguous claims without inventing evidence.",
    },
]


def prompt_for(catalog: list[dict], role: str) -> dict:
    for prompt in catalog:
        if prompt["role"] == role:
            return prompt
    raise KeyError(f"Missing built-in prompt for role: {role}")
