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

## Acceptance boundary

Staging checks do not claim end-to-end daily delivery or retrieval quality. Final database cutover must wait for active desktop work to finish or an explicit interruption decision, then use a consistent SQLite backup with table-content verification. The old Windows daily task must remain disabled after cutover to prevent duplicate delivery. Migration and operations are described in [SERVER_DEPLOYMENT.md](SERVER_DEPLOYMENT.md).
