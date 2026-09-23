# Jev V2 Integration

Jev is used as a typed System One decision plane, not as a replacement for the generative LLM.

| Mode | Behavior |
| --- | --- |
| Disabled | No Jev call; existing LLM/rule path remains unchanged. |
| Shadow | Jev calls are audited but do not change final output. |
| Active | High-confidence Jev output is used; low confidence or failure falls back. |

The `paper-screen.v1` contract scores topic fit, research-question fit, evidence completeness, study type and usefulness. The `evidence-check.v1` contract checks supported claims, warranted limitations and unsupported specificity.

Every call records requested/resolved model, schema version, state hash, typed answers, derived outcome, confidence, latency, input tokens, cache hit and fallback state. Inspect it through `GET /api/runs/{run_id}/decisions` or the GUI audit panel.

```env
TYPESAFE_API_KEY=
JEV_ENABLED=false
JEV_SHADOW_MODE=true
JEV_MODEL=jev-1.13.0
JEV_TIMEOUT_SECONDS=15
JEV_AUTO_THRESHOLD=0.82
JEV_REVIEW_THRESHOLD=0.55
JEV_CACHE_TTL_HOURS=168
```

Only task topic/questions, paper title/abstract and the structured summary are sent for decisions. PDF files, SMTP credentials and API keys are never placed in Jev state.
