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
uvicorn literature_agent.api:app --reload --port 8000
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

The default backend uses deterministic fixture records so the GUI can be evaluated without API keys. Set `LITERATURE_AGENT_LIVE=true` and configure provider keys to enable live retrieval.

## MVP daily subscriptions

The MVP supports OpenAlex, Crossref, arXiv, and PubMed subscriptions, Chinese digest rendering, SMTP delivery records, and an independent daily CLI. Configure `LLM_API_KEY`, `LLM_MODEL`, `LITERATURE_AGENT_LIVE=true`, and the `SMTP_*` variables in `backend/.env` before running a subscription.

Create or manage subscriptions in the GUI, then run one manually with:

```powershell
cd backend
.\.venv\Scripts\python.exe -m literature_agent.daily --run-subscription <subscription-id>
```

Use `--run-enabled` for all enabled subscriptions or `--no-send` to validate retrieval without SMTP delivery. Windows Task Scheduler can invoke the same CLI after the first manual delivery is verified.
