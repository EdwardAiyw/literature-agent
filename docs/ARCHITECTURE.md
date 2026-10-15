# Architecture

V2 separates orchestration (LangGraph), open-ended generation (OpenAI-compatible LLM), typed decisions (Jev), and deterministic execution. SQLite uses WAL; Alembic owns versioned schema upgrades; queued/running work is recovered by a bounded local worker after restart.

```mermaid
flowchart LR
  EXE[Windows launcher] --> API[FastAPI]
  UI[React GUI] --> API
  API --> DB[(SQLite)]
  API --> CFG[JSON settings]
  API --> CRED[Windows Credential Manager]
  API --> TASKS[Windows Task Scheduler]
  API --> G[LangGraph run]
  G --> P[Query planner]
  P --> R[Source retrieval]
  R --> D[Deduplicate]
  D --> C[Relevance screener]
  C --> S[Structured summarizer]
  S --> E{Evidence review enabled?}
  E -->|yes| V[Evidence reviewer]
  E -->|no| M[Result manifest]
  V --> M
  G --> A[Run events and artifacts]
  G --> J[Jev typed decisions]
  J --> DB
  M --> DB
  A --> DB
  DB --> UI
  API -->|explicit per-paper import| Z[Zotero Web API adapter]
  G -. future .-> F[OA PDF downloader]
```

The backend owns task state and run state. The GUI never calls data providers directly. Each graph node receives structured state and returns a structured state update. Provider adapters and the model adapter are replaceable interfaces.

The packaged launcher binds only to `127.0.0.1`, serves the built React application from the same process, checks for an existing healthy instance, and opens the browser. Non-secret settings live beside the selected data directory; secrets are stored per Windows user. Scheduler helpers launch the same packaged executable for login startup and due-subscription checks.

## State invariants

- Every paper has a stable canonical identifier.
- Every run records its current node, progress, status, timestamps, and errors.
- Every completed node writes a run event and one structured artifact.
- Every run uses a snapshot of the versioned prompt catalog available at startup.
- Model output is validated against a JSON shape before persistence.
- A failed source does not fail the entire run.
- Zotero export requires an explicit per-paper action. Review labels alone do not trigger export; ignored papers are blocked. DOI matches reuse existing items and preserve user-edited metadata. Import results are stored per paper and destination library/collection.
- DOI deduplication scans paginated top-level items and compares normalized DOI metadata; quick search is used only for DOI-less title candidates. A failed scan prevents creation. Creation tokens belong to one attempt; later retries scan again.
- Zotero import, data-directory replacement, and backup restoration hold the same nonblocking lock for their entire operation, including local result persistence or global database replacement. Conflicts return HTTP 409.
- The GUI invalidates and reloads destination-specific paper statuses on saved library/collection or configured-state changes, including completed runs. Task and destination generations reject stale responses. Collection keys take precedence over names.
- Settings APIs expose only configuration status, never saved secret values.
- A subscription cannot start a second active run or run twice in its configured local calendar day.
