# Architecture

```mermaid
flowchart LR
  UI[React GUI] --> API[FastAPI]
  API --> DB[(SQLite)]
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
  M --> DB
  A --> DB
  DB --> UI
  G -. future .-> Z[Zotero adapter]
  G -. future .-> F[OA PDF downloader]
```

The backend owns task state and run state. The GUI never calls data providers directly. Each graph node receives structured state and returns a structured state update. Provider adapters and the model adapter are replaceable interfaces.

## State invariants

- Every paper has a stable canonical identifier.
- Every run records its current node, progress, status, timestamps, and errors.
- Every completed node writes a run event and one structured artifact.
- Every run uses a snapshot of the versioned prompt catalog available at startup.
- Model output is validated against a JSON shape before persistence.
- A failed source does not fail the entire run.
- A paper is not exported to Zotero until a user review or explicit auto-save policy allows it.
