# Jev V2 Shadow Test

Jev is a typed decision plane for relevance screening and evidence checks. Literature Agent uses LocalJev by default. Shadow mode records LocalJev's observations but leaves the existing LLM/rule decisions in control. Audit data is available in the workspace panel and through the API.

## Audit contract

`GET /api/runs/{run_id}/decisions` returns one row for each Jev decision attempt:

| Status | Meaning | `fallback_reason` |
| --- | --- | --- |
| `shadow_observed` | Jev returned a decision in Shadow mode; it did not control the result. | empty |
| `applied` | Active mode accepted a decision above the confidence threshold. | empty |
| `fallback` | Active mode used the existing decision path because Jev confidence was too low. | `low_confidence` |
| `failed` | The Jev request or decision failed. The existing path continues. | `jev_error` |

`fallback_used` means Jev was enabled in Active mode and the existing decision path took over. A Shadow observation is never counted as a fallback. Audit rows also include the requested/resolved model, schema version, state hash, answers, outcome, confidence, latency, input tokens, cache hit, and sanitized error text.

## Configure Shadow mode

Start LocalJev first by following [LocalJev 接入](LOCALJEV.md). For the installed product, open `设置 > LocalJev 决策层`, keep `影子模式` enabled, click `测试 LocalJev`, then enable Jev and save. An API key is optional unless the LocalJev service has configured `LOCALJEV_API_KEY`.

Source developers may instead copy `backend/.env.example` to `backend/.env` and keep these flags as shown:

```env
JEV_ENABLED=true
JEV_SHADOW_MODE=true
JEV_PROVIDER=localjev
JEV_BASE_URL=http://127.0.0.1:8080
JEV_MODEL=jev-latest
JEV_TIMEOUT_SECONDS=180
JEV_MAX_INFLIGHT=2
JEV_AUTO_THRESHOLD=0.82
```

For a real retrieval run, also set `LITERATURE_AGENT_LIVE=true`, `LLM_API_KEY`, and `LLM_MODEL`, plus any source API keys you have. The default database is the new `backend/data/literature_agent_v2.db`; the former `literature_agent.db` is not automatically opened or overwritten. Database startup runs Alembic migrations before opening the SQLite connection and aborts startup if migration fails.

Restart the backend after editing `.env`:

```powershell
cd backend
uvicorn literature_agent.api:app --reload --port 8001
```

Check configuration without exposing secrets:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/api/settings |
  Select-Object live, llm_configured, jev_enabled, jev_configured, jev_shadow_mode, jev_model
```

Expected: `live`, `llm_configured`, `jev_enabled`, and `jev_configured` are true; `jev_shadow_mode` is true.

## Run a small real test

Use one focused topic and target five papers. Create the task in the GUI or through the API, then start its run. Example API request:

```powershell
$task = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/api/tasks `
  -ContentType 'application/json' `
  -Body '{"name":"Jev Shadow validation","topic":"YOUR FOCUSED RESEARCH TOPIC","research_questions":["YOUR PRIMARY RESEARCH QUESTION"],"target_count":5,"sources":["semantic_scholar","openalex","crossref","arxiv","pubmed"]}'
$run = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8001/api/tasks/$($task.id)/runs"
$run.id
```

Wait until `GET /api/runs/{run_id}` reports `completed` or `failed`, then inspect the decision audit:

```powershell
$runId = 'PASTE_RUN_ID_HERE'
Invoke-RestMethod "http://127.0.0.1:8001/api/runs/$runId/decisions" |
  Select-Object stage, subject_id, mode, status, confidence, cached, fallback_used, fallback_reason, error |
  Format-Table -AutoSize
```

In a healthy Shadow run, successful calls have `mode=shadow`, `status=shadow_observed`, and `fallback_used=False`. Repeated inputs may have `cached=True`. Failures have `status=failed`, `fallback_reason=jev_error`; the run should continue on the existing LLM/rule path. Check the run events and papers as well, because an audit row alone does not prove the complete workflow succeeded.

Do not change `JEV_SHADOW_MODE` to false during this validation. Consider Active mode only after reviewing several successful runs, confidence distribution, cache behavior, errors, and final paper quality.
