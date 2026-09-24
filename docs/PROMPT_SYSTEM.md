# Prompt System

Built-in prompts are versioned by role and seeded into SQLite at startup. Each run reads the catalog once, so its node decisions can be traced to the prompt version used. Advanced users can clone a prompt into a custom version, edit it, activate it globally, or select a version for one task. Built-ins remain immutable in the product UI.

## Roles

- `query_planner.v1`: topic to search plan.
- `relevance_screener.v1`: paper and task to relevance decision.
- `literature_summarizer.v1`: paper to research decision summary.
- `evidence_reviewer.v1`: summary to evidence warnings.

## Runtime nodes

The graph executes `query_planner`, `retrieval`, `dedupe`, `relevance_screener`, and `literature_summarizer`. `evidence_reviewer` runs only when the task enables evidence review. Each node writes a user-readable event and a structured artifact to the run record.

## Output contract

```json
{
  "research_problem": "",
  "method": "",
  "main_findings": [],
  "limitations": [],
  "relevance_reason": "",
  "research_use": "",
  "recommended_action": "read|save|background|ignore",
  "confidence": 0.0,
  "evidence_warnings": []
}
```

The model must write `not stated in source` when the supplied title or abstract does not support a claim. Original title, authors, abstract, DOI, and URLs are never rewritten by the model.

When no model credentials are configured, deterministic fallback implementations satisfy the same output contracts. Fallback use is recorded through the `engine` field and does not silently claim model-generated evidence.
