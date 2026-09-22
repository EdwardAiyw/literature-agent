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

## Not yet migrated

- Production source adapters are now implemented for OpenAlex, Crossref, arXiv, and PubMed; live credentials and provider-rate testing remain.
- Durable pause/resume/cancel behavior across service restarts.
- Zotero Web API connector.
- Open-access PDF downloader.
- Windows Tauri packaging.
- Secure Windows Credential Manager storage.
- Multi-user accounts and cloud synchronization.
