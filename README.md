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
