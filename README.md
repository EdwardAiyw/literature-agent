# Literature Agent V2

Local-first Windows research literature agent. The product accepts a research topic, plans queries, retrieves records, deduplicates them, screens relevance, generates a structured research summary, and exposes the run in a desktop-ready GUI.

V2 adds a TypeSafe AI Jev System One decision plane for typed relevance screening and evidence checks. Jev runs behind feature flags, defaults to shadow mode, records confidence/model/latency/cache/fallback audit data, and falls back to the existing LLM or deterministic path when confidence is insufficient.

This is a new product repository. The legacy `literature-digest` repository remains an independent reference implementation.

## Development

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn literature_agent.api:app --reload --port 8001
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5175`. The checked-in development defaults use API port `8001` and GUI port `5175`; copy `frontend/.env.example` to `frontend/.env` only when you need to override the API URL.

The default backend uses deterministic fixture records so the GUI can be evaluated without API keys. Set `LITERATURE_AGENT_LIVE=true` and configure provider keys to enable live retrieval.

## MVP daily subscriptions

V2 supports Semantic Scholar, OpenAlex, Crossref, arXiv, and PubMed subscriptions, Chinese digest rendering, SMTP delivery records, source caching and a global daily request budget. Configure `LLM_API_KEY`, `LLM_MODEL`, `LITERATURE_AGENT_LIVE=true`, and the `SMTP_*` variables in `backend/.env` before running a subscription.

Start Jev in shadow mode:

```env
TYPESAFE_API_KEY=your-key
JEV_ENABLED=true
JEV_SHADOW_MODE=true
JEV_MODEL=jev-1.13.0
```

After validating audit results, set `JEV_SHADOW_MODE=false` to allow high-confidence Jev decisions to take effect. See [`docs/V2_JEV.md`](docs/V2_JEV.md).

Create or manage subscriptions in the GUI, then run one manually with:

```powershell
cd backend
.\.venv\Scripts\python.exe -m literature_agent.daily --run-subscription <subscription-id>
```

Use `--run-enabled` for all enabled subscriptions or `--no-send` to validate retrieval without SMTP delivery. Windows Task Scheduler can invoke the same CLI after the first manual delivery is verified.

For normal scheduled operation, register the included Windows task once from PowerShell:

```powershell
.\scripts\register-windows-task.ps1
```

The task calls `--run-due` every 15 minutes. Each enabled subscription runs only after its configured local time and at most once per local calendar day. Remove the task with `-Unregister`.

Completed CLI and scheduled runs remain available in the GUI: choose the corresponding item under “最近任务” to reopen its events, source diagnostics, and selected papers.
