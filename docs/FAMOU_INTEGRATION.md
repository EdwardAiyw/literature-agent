# FAMOU Integration

The project-local FAMOU skills are optional evaluation tools. They are not part of the normal literature retrieval graph and are not imported by the FastAPI runtime.

## Installed skills

- `skills/famou/famou-data-analysis`: analyze retrieval counts, deduplication rates, source failures, and human review labels.
- `skills/famou/famou-experiment-diagnosis`: inspect an evaluation run for stalled retrieval, invalid candidates, or ranking anomalies.
- `skills/famou/famou-experiment-manager`: manage an explicitly requested FAMOU hybrid experiment.
- `skills/famou/famou-result-visualization`: visualize optimization solutions when a future retrieval-weight experiment produces a solution that needs a separate HTML view.

## Runtime boundary

Normal tasks use the local LangGraph workflow and the configured academic source adapters. FAMOU is never called automatically, does not change source selection, and is not required for fixture or live retrieval.

Use FAMOU only for an explicit evaluation workflow, such as comparing query prompts, source weights, or ranking policies against a labeled benchmark. Keep its API configuration outside the normal application `.env` until that workflow is implemented.

```env
FAMOU_ENABLED=false
```

When enabled in a future evaluation command, the command must write a run manifest containing the task ID, source diagnostics, prompt versions, scoring contract, and output location. It must not mutate raw papers or the production ranking policy.

## Version and provenance

These skills were imported from `baidubce/skills` branch `develop`. Review the upstream license and changes before updating them. They are project-local copies so their instructions can be audited and pinned with the product source.
