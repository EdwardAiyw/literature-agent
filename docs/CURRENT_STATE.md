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

## Verified RC3 release state (2026-09-25)

- `v0.3.0-rc.3` is published as a public GitHub prerelease from commit `9614050`.
- Backend: 51 tests pass locally and in GitHub Actions, including immediate-completion recovery deadlock coverage and 100 StrictMode-style double-initialization cycles with concurrent database writes.
- Frontend: production build and five Edge Playwright regressions pass locally and on the Windows Release runner; coverage includes ten cold loads, three viewports, all navigation entries, overflow, controls, and rapid task switching.
- Release asset: `Literature-Agent-0.3.0-rc.3-Windows-x64.exe`, 28,611,752 bytes, SHA-256 `5cfc8b45a68346b6ce5e51282d510d71ae0889b11760f79b05d00aaf2a5b51fc`.
- Live source and delivery UAT in the source runtime confirmed five final papers from at least two sources, SMTP test mail, manual digest, and scheduled digest.
- Earlier candidate installers passed the automated Sandbox bootstrap checks. RC3 still requires install/update, real delivery, scheduling, backup/restore, and uninstall acceptance before stable promotion.

## Zotero source-runtime integration (updated 2026-10-15)

- Explicit per-paper Web API import for user/group libraries, DOI/title deduplication, target collection membership, persisted status and retry.
- DOI-only metadata matches use paginated top-level library scanning; failed scans prevent creation. Deletion/re-import uses a fresh creation token. Existing user metadata is preserved.
- Import and database replacement share a lock through local persistence/replacement. Saved destination changes refresh completed-run statuses and invalidate late responses from the previous target.
- Settings and read-only connection test, Windows Credential Manager API key storage, and a validated legacy configuration migration script.
- Web library writes appear in the desktop client after Zotero sync; no local Zotero database edits or PDF transfer.
- Included in RC4 source and installer builds; the old RC3 installer does not include it.

## Default Prompt source-runtime state (2026-10-15)

- Four generic v2 defaults are released; v1, custom versions, task overrides, and explicit rollback are retained.
- Fixed-case model quality results and the earlier 91-test acceptance baseline are recorded in [Prompt v2 validation](PROMPT_V2_VALIDATION.md). Zotero repair regression results are recorded in [Zotero integration](ZOTERO.md).

## RC4 candidate (2026-10-15)

- Version: `0.3.0-rc.4`; combines the Zotero source integration/repairs, Prompt v2 release and LocalJev changes made after RC3.
- Local validation: 105 backend tests, frontend production build and 18 Edge regressions passed. GitHub CI and Windows Release validate the pushed source before publishing the installer and checksum.
- Installer upgrade, real Zotero permissions/sync and full Windows acceptance remain prerequisites for stable promotion.

## Not yet implemented

- Durable pause/resume/cancel behavior across service restarts.
- Open-access PDF downloader.
- Authenticode signing for the Windows installer.
- Multi-user accounts and cloud synchronization.
