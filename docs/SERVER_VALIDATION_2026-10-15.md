# Server runtime validation — 2026-10-15

Backend/source validation baseline: `5219ee3d09546c0e50ecf2d40a83a18e180df9db`. Deployed runtime: `fe0d79d289d6a832b1b8ace8b6bd53a1a9780db8`, which additionally identifies remote execution in the navigation and connection label. Its frontend build, both focused server browser cases and actual remote desktop/mobile checks passed. [Runtime CI](https://github.com/EdwardAiyw/literature-agent/actions/runs/38756705343) passed. The immutable RC5 Windows installer is unchanged.

## Automated checks

- Windows backend: 156 tests passed against isolated data.
- Frontend: TypeScript and production Vite build passed; all 29 Edge regressions passed, including server settings and subscription editing that retains hidden research configuration.
- Ubuntu 22.04 Docker / Python 3.12: all 156 backend tests passed in an isolated temporary container. Only the existing LangGraph pending-deprecation warning remains.
- [GitHub CI](https://github.com/EdwardAiyw/literature-agent/actions/runs/38754211915) passed for the source commit.
- Original three modified regression screenshots were restored byte-for-byte and excluded from the commit.

## Deployed staging checks

- Built `literature-agent:5219ee3` and the follow-up `literature-agent:fe0d79d` from a SHA-256 verified source archive and locally compiled frontend; no credentials or production database entered the build context.
- Nonroot container started with a read-only root filesystem, bounded resources and loopback-only host publishing. Health checks, SQLite migrations and the internal scheduler initialized successfully.
- Verified SSH tunnel access, same-origin settings writes and settings/secret persistence across a container restart.
- Verified data directory mode 700 and settings/secret files mode 600.
- An actual request from the server to the configured model returned the expected connection-test JSON. SMTP TLS connection, authentication and NOOP succeeded; no test email was sent.
- Actual remote webpage checks passed for editing a subscription and preserving its task/configuration, desktop/mobile layout, schedule and enabled-state updates, and server scheduler/settings status. Fixtures were deleted after verification; daily dispatch remained paused.

## Production cutover — 2026-10-16 (Asia/Hong_Kong)

- The user explicitly requested interruption of the active desktop retrieval, migration and a fresh server execution. Created a verified pre-interruption SQLite backup, stopped the desktop API and recorded the interrupted run as cancelled with a migration event; prior history remains intact.
- Used the SQLite backup API for the final snapshot. All 14 table counts and content hashes matched the server copy before and after startup, preserving one task, one subscription, two historical runs and eight Prompts.
- Migrated effective model, mail, source and Zotero settings and credentials over SSH. Data and secret permissions remained restricted; credential values were not committed or logged.
- Enabled production server scheduling at 2026-10-15 23:47 UTC. The existing enabled 07:00 Asia/Hong_Kong subscription was already due and started one fresh run automatically. Query planning completed and retrieval began; no duplicate manual launch was issued.
- Disabled both desktop Daily and Local scheduled tasks and left the old local data intact. Server is now the source of truth; the old desktop service remains stopped.
- Confirmed healthy container, no OOM/restart, the active new run on the real webpage, one migrated subscription, retained schedule, web editing entry and internal scheduler status. Opened the local SSH browser entry; the desktop server shortcut remains available.

## Acceptance boundary

Migration integrity and startup/execution initiation are verified. The newly started production search and its final email are not yet verified as completed. Prior staging SMTP checks used TLS authentication and NOOP without sending mail; final digest delivery should be checked in the webpage's delivery history. Migration and operations are described in [SERVER_DEPLOYMENT.md](SERVER_DEPLOYMENT.md).
