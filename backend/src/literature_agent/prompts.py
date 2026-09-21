from __future__ import annotations

BUILTIN_PROMPTS = [
    {
        "id": "query_planner.v1",
        "role": "query_planner",
        "version": "v1",
        "builtin": True,
        "body": "Convert the user's topic into precise academic search queries, synonyms, exclusions, language policy, and source routing. Never add a research claim not present in the topic.",
    },
    {
        "id": "relevance_screener.v1",
        "role": "relevance_screener",
        "version": "v1",
        "builtin": True,
        "body": "Assess whether a paper directly serves the task topic. Return a score, a short evidence-based reason, and read/save/background/ignore action.",
    },
    {
        "id": "literature_summarizer.v1",
        "role": "literature_summarizer",
        "version": "v1",
        "builtin": True,
        "body": "Summarize only the supplied title and abstract. Return problem, method, findings, limitations, research use, confidence, and evidence warnings. Use 'not stated in source' when needed.",
    },
    {
        "id": "evidence_reviewer.v1",
        "role": "evidence_reviewer",
        "version": "v1",
        "builtin": True,
        "body": "Check each summary claim against the supplied paper evidence. Flag unsupported, over-specific, or temporally ambiguous claims.",
    },
]
