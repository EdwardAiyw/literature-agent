# Current State

## Legacy implementation

The existing `literature-digest` project is an independent script-oriented system. It currently provides:

- OpenAlex, Crossref, Semantic Scholar, and arXiv source adapters.
- Persistent paper records, deduplication, relevance scoring, and daily Markdown/JSON/HTML reports.
- OpenAI-compatible summary generation with a deterministic fallback.
- SMTP delivery through GitHub Actions.
- Local open-access PDF download and Zotero Web API import.
- Windows Task Scheduler scripts for local synchronization.

Its current limitations are a command-line workflow, no reusable task model, no resumable Agent graph, no GUI, limited prompt management, and no product-level settings or observability.

## Product decision

`literature-agent` is a new product repository. It is not a direct rewrite inside the legacy repository. The product is a general single-user academic literature agent: each task has its own topic, language policy, date range, source selection, and output policy.

## Implemented MVP slice

- FastAPI backend with SQLite task/run/paper storage.
- LangGraph-compatible retrieval workflow with planning, retrieval, screening, and summarization nodes.
- Deterministic fixture mode for offline development.
- React/TypeScript result workbench.
- Versioned built-in prompt catalog.
- Runtime Agent stages for query planning, retrieval, deduplication, relevance screening, summarization, and optional evidence review.
- Persisted run events, node artifacts, progress, result manifests, and Prompt version snapshots.
- Optional project-local FAMOU evaluation skills, isolated from normal retrieval.
- API contracts for task creation, run control, paper review, prompts, and settings.
- Subscription CRUD with required recipient, schedule, target count, source and date policy.
- Independent daily CLI, SMTP HTML/plain-text digest rendering, delivery history, and GUI status views.
- Schedule-aware `--run-due` execution plus a Windows Task Scheduler registration script.
- Historical task runs can be reopened in the GUI after CLI or scheduled execution.
- Live adapters for Semantic Scholar, OpenAlex, Crossref, arXiv, and PubMed, including partial-failure diagnostics, caching, request budgets, and source-specific retry behavior.
- Page-based onboarding and hot-updated settings for model, SMTP, sources, Jev, runtime limits, data location, backup, restore, scheduler, and update checks.
- Windows Credential Manager storage for model, SMTP, source, and Jev secrets; setting APIs never return saved secret values.
- PyInstaller directory packaging, a locally verified Inno Setup installer, and a tag-triggered GitHub Release workflow.
- Configurable data directory, database validation, migration-time backups, daily log rotation, and local-origin write protection.
- Serialized access to the shared SQLite connection, plus abortable frontend bootstrap, polling, and task selection to prevent stale or false error states.
- Responsive workbench coverage at 390 x 844, 768 x 1024, and 1440 x 1000, including all four product views.
- Windows Sandbox launch, bootstrap, manual-check, finalization, backup/restore, and uninstall acceptance scripts.

## Verified release-candidate state

- Backend: 45 tests pass, including 100 StrictMode-style double-initialization cycles with concurrent database writes.
- Frontend: production build passes; five Edge Playwright regressions cover ten cold loads, three viewports, all navigation entries, overflow, controls, and rapid task switching.
- Packaged executable: starts with an isolated data directory on a non-default port, returns a healthy API response, and serves the bundled frontend.
- Live source and delivery UAT: five final papers from at least two sources, SMTP test mail, manual digest, and scheduled digest were confirmed.
- Remaining release gate: restart Windows after enabling Sandbox, then complete the isolated installer checklist before promoting the candidate to a stable release.

## Not yet implemented

- Durable pause/resume/cancel behavior across service restarts.
- Zotero Web API connector.
- Open-access PDF downloader.
- Authenticode signing for the Windows installer.
- Multi-user accounts and cloud synchronization.
