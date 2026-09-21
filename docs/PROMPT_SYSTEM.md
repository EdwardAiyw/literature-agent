# Prompt System

Built-in prompts are versioned by role. Advanced users may clone and edit a prompt; built-ins remain immutable.

## Roles

- `query_planner.v1`: topic to search plan.
- `relevance_screener.v1`: paper and task to relevance decision.
- `literature_summarizer.v1`: paper to research decision summary.
- `evidence_reviewer.v1`: summary to evidence warnings.

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
