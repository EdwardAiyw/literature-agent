# Roadmap

## Alpha

- Local FastAPI backend, SQLite, LangGraph workflow, fixture retrieval, React workbench, prompt catalog.
- Runtime Agent event timeline, node artifacts, Prompt snapshots, deterministic fallback, and optional evidence review.

## MVP / Beta

- Semantic Scholar/OpenAlex/Crossref/arXiv/PubMed adapters and parallel source diagnostics.
- OpenAI-compatible model provider.
- Subscription configuration, independent daily CLI, HTML/plain-text SMTP digest, and delivery history.
- GUI source/date controls and per-source diagnostics.
- Schedule-aware daily CLI and page-managed Windows Task Scheduler registration.
- Page-based onboarding, Windows Credential Manager, data directory selection, backup/restore, update checks, and runtime settings.
- PyInstaller application bundle, Inno Setup installer, and tag-triggered GitHub Release workflow.

- RC5 (2026-10-15): task-to-daily conversion, enforced relevance gates, validated query plans and source rate-limit/partial-result handling.

- Post-RC5 source: single-user Linux Docker runtime, internal scheduling, persistent file secrets, SSH web management and subscription editing; see [server deployment](SERVER_DEPLOYMENT.md).

## Post-Beta

- Released in RC4 (2026-10-15): explicit Zotero Web API citation import with paginated DOI metadata deduplication, per-destination status and database replacement locking.
- Future: optional automatic Zotero export policy after review.
- Durable run pause/resume/cancel and an in-product structured log viewer.
- Optional FAMOU evaluation workflow for labeled retrieval/ranking experiments.
- Authenticode signing and a stable release channel.
- Optional cloud backup.
