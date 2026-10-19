# Current State

## Obsidian source integration (2026-10-19)

- Added a separate SSH/read-only SQLite → Markdown exporter and Windows login/15-minute scheduling helper; no server or installed RC6 binary upgrade is required. The immutable RC6 installer does not contain these helpers.
- User-selected RAG_Agent vault received the October 19 successful 10-paper digest, daily index and existing Zotero links. The independent scheduled task executed successfully with result 0; repeated export reused all 10 notes. Personal annotations outside managed blocks are preserved. See [configuration, validation and limits](OBSIDIAN.md).

## RC6 synchronized release and deployment (2026-10-18)

- Version `0.3.0-rc.6` uses immutable tag `v0.3.0-rc.6`, commit `ebda008d2efec3aae5413343a7328adba1e52202`. Windows packaging includes the daily history/date, automatic Zotero and JIF features previously available only in source. See [release and validation](RELEASE_RC6.md).
- Linux image `literature-agent:rc6-ebda008` is deployed and healthy with a running, error-free 60-second scheduler. Upgrade preserved all 17 table hashes and configuration hashes. Backup: `/opt/literature-agent/backups/rc6-20261018T012736Z`; previous image retained for rollback. Final isolated image passed 245 backend tests.
- Existing subscription remains enabled at 07:00 Asia/Hong_Kong, target at most 10 papers, running-day cutoff and original Zotero target. LocalJev remains Shadow. This upgrade did not retrieve, email or import papers again. Windows and Linux deploy separately; their data does not synchronize.
- Windows Release passed 245 backend tests, 32 Edge cases, frontend build and packaged runtime checks. The publicly re-downloaded installer is 29,146,628 bytes; its SHA-256 matches the checksum file and GitHub asset digest.
- RC6 passed 26 Sandbox lifecycle checks, an actual 0.3.0-to-RC6 desktop upgrade with all 17 tables/settings preserved, and an installed-binary live run yielding five papers from three sources with loopback SMTP receipt. It remains a prerelease pending clean-system onboarding, natural trigger execution and external inbox receipt. See [installer validation](INSTALLER_RC6_VALIDATION_2026-10-18.md). Historical RC5 assets and dated validation results remain unchanged.

## Daily digest duplicate repair (2026-10-18)

- Shared source workflow now merges cross-source paper identities and excludes each subscription's successful delivery history before model screening. SMTP failures/no-send do not consume papers; independent subscriptions and manual tasks retain their own behavior.
- `date_to_mode` adds running-day/fixed cutoff selection, preserving legacy fixed dates and storing restart-safe execution snapshots. Migration `20261018_0006` backfills durable delivery snapshots. See [behavior, limits and validation](DAILY_DEDUPLICATION.md).
- The initial repair used server image `literature-agent:digest-0aaced276934`, later superseded by RC6 above. The approved existing subscription now tracks through the running day at 07:00 Asia/Hong_Kong. All 15 preexisting business tables and configuration hashes were preserved before the explicit subscription update; 3 historical digests/150 papers were backfilled. The deployment itself did not send mail. A subsequent authorized replacement run on 2026-10-18 selected 10 papers, SMTP accepted its digest at 08:47 Asia/Hong_Kong, and all 10 Zotero imports completed. The existing subscription now targets at most 10 papers daily at 07:00; this is a per-subscription setting. Windows RC5 assets remain unchanged.
- Windows and final Linux image: 245 backend tests passed on each. Frontend build and 9 affected Edge cases passed. Real-data isolated replay reduced the Oct18 selected list from 50 records to 44 identities and excluded 35 previously delivered identities, leaving 9 unseen; this does not predict future retrieval yield.

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

## Zotero task automation and identifier attachments (2026-10-17)

- Source defaults to public publisher JIF lookup after selected-paper persistence and before completion/mail/Zotero. DOI metadata and ISSN journal identity are verified; success/missing/failure are cached, with a 60-second deadline and two concurrent requests. Optional JCR CSV imports remain; no model guesses or substitute metrics. `20261017_0005` adds `journal_metric_lookups` beside `journal_metrics`; historical papers are not automatically enriched. Three real Frontiers journals passed; an isolated copy of the current 50 records produced 48 inapplicable/2 insufficient-metadata records and no JIF. See [configuration and limits](JOURNAL_METRICS.md).
- Automatic JIF server image `5e2defc` deployed after backup and real public lookups from the server. All 14 prior business-table hashes/settings/secrets/LocalJev environment preserved; new lookup cache starts empty and populates on subsequent live runs. CI passed 235 backend tests/build/LocalJev checks; 15 affected Edge cases and read-only production UI/mobile checks passed. Existing 07:00 Asia/Hong_Kong schedule, automatic Zotero target and Shadow retained; scheduler resumed, no mail, retrieval or Zotero writes during deployment. See [validation/deployment details](JOURNAL_METRICS.md).

- Source runtime adds opt-in exact-collection task/subscription imports, destination snapshots, shared batch DOI indexes, durable per-paper progress and failure retry without retrieval/mail. Worker restart resumes unfinished batches.
- Daily digests attach UTF-8 identifier TXT when reliable IDs exist; the workbench exports the same identifiers for existing runs. No invented identifiers or PDF attachments.
- Defaults remain off; task conversion preserves settings. Global credentials stay shared. Existing Windows RC5 assets remain immutable. See [Zotero configuration and APIs](ZOTERO.md).
- Initial Zotero rollout used server image `b131145`; approved daily task targets Daily Digest. Oct17 backfill processed 50 records (47 new, 3 existing, 0 failed), confirmed 48 unique remote items in the target collection. No retrieval/mail repeated; 07:00 Asia/Hong_Kong and LocalJev Shadow retained. That rollout passed 182 backend tests and 30 Edge cases. See [validation](ZOTERO_VALIDATION_2026-10-17.md).

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

## RC5 relevance repair (2026-10-15)

- Formal local testing exposed a result-selection defect: seven unrelated candidates scored 0.02-0.05 still entered results because selection only ranked and filled the target count.
- Source now gates final ordinary/Jev decisions at relevance >=0.40, respects `ignore`, excludes keyword fallback screening from live results, and records rejected candidates/counts. Empty live retrieval no longer creates fixtures.
- Query planning adds recorded runtime execution requirements and one bounded repair for invalid language/shape/length; published Prompt bodies, explicit selections and historical snapshots stay intact. arXiv no longer replaces unsupported Chinese-only queries with generic `literature` searches.
- Workbench exposes executed queries/date bounds and screening totals. Empty digests explain that no qualifying papers were found.
- Historical replay excludes all seven low-score results. A separate OpenAlex/DeepSeek probe, using the intended 2023-01-01 to 2026-10-15 date range, screened eight of ten retrieved candidates: five ignored, one directly relevant and two background references. It did not alter the saved subscription or send mail/Zotero writes; this limited probe is not full five-source quality acceptance.
- Initial relevance validation passed 129 backend tests, the frontend build and 20 Edge regressions, including two new relevance cases; final combined validation passed 150 backend tests and 27 Edge regressions. RC5 packages these changes; the immutable RC4 installer and tag do not include them. See the [public validation report](VALIDATION_2026-10-15.md).

## RC5 source rate-limit repair (2026-10-15)

- Crossref now identifies the client with the configured PubMed contact email or SMTP sender. Crossref/Semantic Scholar share process-local per-provider/key pacing, bounded retries and Retry-After cooldowns; exhausted sources cool down for at least 60 seconds. This cannot guarantee anonymous API availability.
- Later query/page failures retain previous records. Completed queries are cached independently, incomplete aggregate searches are not cached as complete, and every actual request/retry reserves budget. Diagnostics retain attempt/retry/cooldown counts.
- Workbench labels HTTP 429 as rate-limited, including historical diagnostics without rewriting history; partially retrieved records stay available. Settings source checks report individual failures/limits instead of falsely marking them successful.
- Read-only integration check at 2026-10-15 12:00 UTC: Crossref returned 4 records from two HTTP 200 requests; anonymous Semantic Scholar exhausted four attempts with HTTP 429. No user task, email or Zotero write was initiated. See the [public validation report](VALIDATION_2026-10-15.md).
- Validation: 138 backend tests, production frontend build and 24 Edge regressions passed; the final source diagnostic adjustment also passed all four focused browser cases. Three preexisting modified screenshots were restored byte-for-byte after regression.
- Deployed to the local source service on port 8001 at 2026-10-15 13:00 UTC after the manual run finished. The idle restart also loaded task conversion below; database table hashes and persisted settings were unchanged. The RC5 release packages these repairs; the published RC4 installer/tag remain unchanged.

## RC5 task-to-daily conversion (2026-10-15)

- Current-task card and history row expose conversion to an existing daily-subscription workflow. The dialog reviews inherited research settings and fixed date bounds, accepts recipient/time/timezone, and supports required-field validation, pending state, cancellation and error retry on desktop/mobile.
- `POST /api/tasks/{task_id}/subscription` atomically attaches one subscription to the same task ID and changes ownership. Topic/questions, language/output, count, sources, dates, evidence review, explicit Prompt overrides and historical runs/results stay intact. Duplicate/stale conversions are rejected; saving does not run retrieval, send mail or register Windows tasks.
- Same-day manual runs no longer suppress the subscription's due check; active runs still prevent overlap. Subscription deletion is rejected while its associated task is queued/running/paused. Normal deletion retains its explicit task/history cascade semantics.
- Validation: 150 backend tests, production frontend build and 27 Edge regressions passed. Browser fixtures disable model/mail endpoints and run sequentially against their shared isolated database. Three preexisting screenshots were restored exactly.
- Local service 8001 was backed up and restarted at 2026-10-15 13:00 UTC; new API/frontend are loaded, and all database table hashes/settings hashes match the pre-restart snapshot. No production task was converted or emailed during verification. See the [public validation report](VALIDATION_2026-10-15.md).

## Verified RC5 prerelease (2026-10-15)

- Published [`v0.3.0-rc.5`](https://github.com/EdwardAiyw/literature-agent/releases/tag/v0.3.0-rc.5) from immutable source commit `7c68797`, packaging all RC5 changes above and retaining RC4 capabilities.
- [GitHub CI](https://github.com/EdwardAiyw/literature-agent/actions/runs/38748173439) and [Windows Release](https://github.com/EdwardAiyw/literature-agent/actions/runs/38748181058) passed. The clean Windows runner passed 150 backend tests, the frontend production build and 27 Edge regressions.
- Packaged runtime checks passed for version, isolated database, eight built-in Prompts/four active v2 defaults, Zotero settings, frontend and conversion retaining task settings without creating runs or deliveries.
- Installer: 29,033,921 bytes; anonymous re-download SHA-256 `7e648d48a12397001a1b04aab39a4a58212e69293fb365ead5b2d4a269c6a0af` matches both `SHA256SUMS.txt` and GitHub's asset digest. RC4/RC3 assets and tags remain unchanged.
- Full manual installer/upgrade, real Zotero permissions/sync, scheduler, restore and uninstall acceptance remain prerequisites for stable promotion. Anonymous Semantic Scholar remained rate-limited in the independent live probe.

## Verified RC4 prerelease (2026-10-15)

- Version: `0.3.0-rc.4`; combines the Zotero source integration/repairs, Prompt v2 release and LocalJev changes made after RC3.
- Local validation, GitHub CI and Windows Release passed: 105 backend tests, frontend production build and 18 Edge regressions. Packaged runtime health/version, isolated database path, eight built-in prompts/four v2 defaults, Zotero settings and frontend checks passed.
- Source tag `v0.3.0-rc.4` points to `9b46771`; the corrected release workflow on `main` rebuilt that immutable tag successfully ([run 38716729435](https://github.com/EdwardAiyw/literature-agent/actions/runs/38716729435)).
- Published installer: 29,018,832 bytes; re-downloaded SHA-256 `52efebc8eca12ba262ee7a770ce6976155d3a92694268d6874203f06ada8845f` matches the published checksum file.
- Installer upgrade, real Zotero permissions/sync and full Windows acceptance remain prerequisites for stable promotion.

## Post-RC5 server runtime

- Source supports single-user Linux Docker operation, persistent file secrets, internal daily dispatch and SSH-only web management. Desktop scheduling and credential storage remain unchanged.
- Web subscription editing includes timing and enabled state, retains research settings and history, and supports manual server execution.
- Deployment, migration, environment variables, data ownership and rollback are documented in [SERVER_DEPLOYMENT.md](SERVER_DEPLOYMENT.md). These changes are not in the immutable RC5 Windows installer; RC6 source includes this runtime, deployed separately on Linux.
- Validation: 156 tests passed on Windows and in the Ubuntu runtime container, 29 Edge regressions passed, and GitHub CI passed. Staging verified restart persistence, model/SMTP connectivity without mail, and actual remote desktop/mobile subscription editing. See [server validation](SERVER_VALIDATION_2026-10-15.md).
- Production cutover completed on 2026-10-16 (Asia/Hong_Kong): all 14 tables verified, desktop active run cancelled at user request, both desktop scheduled tasks disabled, server scheduling enabled and one fresh due subscription run started. The first server search completed with 50 papers; SMTP accepted its digest at 08:09 Asia/Hong_Kong. Inbox receipt is unverified. Server is the authoritative task/configuration store.

## LocalJev cloud screening

- Pinned lightweight LocalJev adapter supports authenticated internal Compose access to the existing DeepSeek cloud model. Effective screening Prompt/task and deployment identity participate in decisions/cache.
- Bounded screening concurrency, progress counts and explicit ordinary-call skip audit are implemented; active high-confidence skips duplicate screening, low-confidence/error falls back.
- Real 12-case comparison failed: ordinary 12/12 at 7.96 s, active 10/12 at 13.47 s, including two unrelated acceptances. Keep production Shadow mode; do not claim active screening acceptance. [Results](LOCALJEV_CLOUD_VALIDATION_2026-10-16.md).
- Server runtime `9ab4b74` is deployed in Shadow mode; internal LocalJev reports ready using canonical `deepseek-flash` (the existing ordinary `deepseek-chat` alias resolves to it). Real isolated workflow completed with one paper and two Shadow decisions; all 14 production tables matched the backup and daily scheduling resumed.
- Verification: 159 backend tests, 20 LocalJev tests/typecheck on pinned Linux Bun 1.3.5, frontend build and five focused Edge checks passed.

## Not yet implemented

- Durable pause/resume/cancel behavior across service restarts.
- Open-access PDF downloader.
- Authenticode signing for the Windows installer.
- Multi-user accounts and cloud synchronization.
