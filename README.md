# Literature Agent

Local-first Windows research literature agent. The product accepts a research topic, plans queries, retrieves records, deduplicates them, screens relevance, generates a structured research summary, and exposes the run in a desktop-ready GUI.

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

The MVP supports OpenAlex, Crossref, arXiv, and PubMed subscriptions, Chinese digest rendering, SMTP delivery records, and an independent daily CLI. Configure `LLM_API_KEY`, `LLM_MODEL`, `LITERATURE_AGENT_LIVE=true`, and the `SMTP_*` variables in `backend/.env` before running a subscription.

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
