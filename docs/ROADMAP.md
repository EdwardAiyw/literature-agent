# Roadmap

## Alpha

- Local FastAPI backend, SQLite, LangGraph workflow, fixture retrieval, React workbench, prompt catalog.
- Runtime Agent event timeline, node artifacts, Prompt snapshots, deterministic fallback, and optional evidence review.

## MVP / Beta

- Page-managed source connections: nine open adapters plus optional Google Scholar (SerpApi) and CORE; configure credentials, enable/default selections, per-source budgets and connection tests in Settings. See [coverage and limits](SOURCES.md).
- OpenAI-compatible model provider.
- Subscription configuration, independent daily CLI, HTML/plain-text SMTP digest, and delivery history.
- GUI source/date controls and per-source diagnostics.
- Schedule-aware daily CLI and page-managed Windows Task Scheduler registration.
- Page-based onboarding, Windows Credential Manager, data directory selection, backup/restore, update checks, and runtime settings.
- PyInstaller application bundle, Inno Setup installer, and tag-triggered GitHub Release workflow.

- RC5 (2026-10-15): task-to-daily conversion, enforced relevance gates, validated query plans and source rate-limit/partial-result handling.

- RC6 (2026-10-18): single-user Linux Docker runtime, internal scheduling, persistent file secrets, SSH web management and subscription editing; see [server deployment](SERVER_DEPLOYMENT.md).

- RC6 (2026-10-18): durable delivery-history filtering, cross-source identities, dynamic subscription cutoffs and restart-safe snapshots; see [daily selection](DAILY_DEDUPLICATION.md).

- RC6 (2026-10-18): publisher JIF lookup with year/source and optional JCR CSV imports; Windows packaging and separate Linux deployment.

- RC7 (2026-11-01): configurable source connections, 11 adapters including optional Google Scholar/CORE, and packaged Obsidian settings with complete email archives. See [release and validation](RELEASE_RC7.md).

## Post-Beta

- Released in RC4 (2026-10-15): explicit Zotero Web API citation import with paginated DOI metadata deduplication, per-destination status and database replacement locking.
- Released in RC6 (initial source rollout 2026-10-17): opt-in task/subscription Zotero export into exact collections, durable batch recovery/retry, and daily identifier TXT attachments. PDF download/upload remains future work.
- Durable run pause/resume/cancel and an in-product structured log viewer.
- Optional FAMOU evaluation workflow for labeled retrieval/ranking experiments.
- Authenticode signing and a stable release channel.
- Optional cloud backup.
