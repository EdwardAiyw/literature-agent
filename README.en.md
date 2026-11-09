# Literature Agent

Turn a research topic into a traceable daily literature digest.

[中文](README.md) · [Windows download](https://github.com/EdwardAiyw/literature-agent/releases/tag/v0.3.0-rc.7) · [Server deployment](docs/SERVER_DEPLOYMENT.md) · [Issues](https://github.com/EdwardAiyw/literature-agent/issues)

Literature Agent is an open-source assistant for individual researchers. It searches scholarly sources, merges duplicate records, screens relevance, generates research briefs, and records results and email deliveries. Current source can pause a subscription after a healthy search yields no new papers and synthesize its entire successful digest history. Run it on a Windows computer or your own Linux server. The UI and linked operational guides are primarily in Chinese.

## Choose a runtime

**2026-11-09 update: pause subscriptions after healthy zero-paper runs, send a separate pause notice, then deliver a complete historical literature synthesis.** This is on `main` and deployed to the current Linux server. The published Windows installer remains RC7.

| Runtime | Audience | Features and updates |
| --- | --- | --- |
| [Windows RC7 installer](https://github.com/EdwardAiyw/literature-agent/releases/tag/v0.3.0-rc.7) | Test users wanting an installer | Eleven source connections, Obsidian, complete digest archives, delivery deduplication, Zotero and JIF; excludes automatic pause and historical synthesis |
| Current `main` source | Developers and users needing newer features | All capabilities described here; rebuild the frontend and restart after updating |
| [Linux Docker deployment](docs/SERVER_DEPLOYMENT.md) | Users needing unattended daily operation | Build and switch images from a chosen commit, manage through SSH; the current server has this update, while other deployments require separate upgrades |

RC7 remains a prerelease. This update is **Unreleased**: no new Windows installer has been published and historical tags have not moved. See the [RC7 release record](docs/RELEASE_RC7.md) for packaged features and validation, and the [deployment record](docs/SERVER_DEPLOYMENT.md) for the current server's commit, image and backups. Updating GitHub does not upgrade installed applications or other servers.

## Capabilities

- Manage literature connections in Settings: add, configure, test, enable or remove sources, with saved credentials, default selections and per-source request limits. Nine open sources plus optional Google Scholar (via SerpApi) and CORE are supported. See [source coverage and limits](docs/SOURCES.md).
- Plan queries, screen relevance, generate structured summaries, and optionally review claims against supplied evidence. Preserve executed queries, Prompt snapshots, and source diagnostics.
- Schedule HTML/plain-text digests in each subscription's time zone, with DOI and original links.
- Merge current-search duplicates and exclude papers already successfully emailed by that subscription, including older papers not yet delivered.
- Pause a subscription after a healthy zero-paper search and send separate pause and historical-summary emails. Source/model failures do not trigger automatic pause. Available in current source and upgraded servers.
- Synthesize all successful digests for that subscription into cited themes, methods, findings, relationships/disagreements and next steps, with a complete paper appendix and Markdown report. Download reports, retry failures and resume subscriptions from the UI. Available in current source and upgraded servers.
- Import citations individually or automatically into an exact Zotero collection, with durable progress/retry and identifier TXT attachments.
- Connect Obsidian from Settings: discover vaults, save a local/server source, sync now, manage automatic sync, inspect status, and open linked daily/paper notes while preserving annotations. This [built-in RC7 feature](docs/OBSIDIAN.md) supports Windows scheduling and offline catch-up.
- Archive complete digest text, source diagnostics, deduplication counts, JIF provenance and identifier TXT attachments into the vault. New sends retain the original render snapshot; older reconstructed digests are labeled explicitly.
- Look up verifiable publisher JIF values with year/source, or import JCR CSV data. Lookup failure does not block delivery.
- Manage models, SMTP, sources, backups, subscriptions, and versioned Prompts from the UI; optionally inspect LocalJev decisions.

Supported sources are Semantic Scholar, OpenAlex, Crossref, arXiv, PubMed, DOAJ, DataCite, HAL, Europe PMC, and the separately keyed Google Scholar (SerpApi) and CORE connections. See [source configuration, access and coverage](docs/SOURCES.md).

Scores, briefs and historical synthesis use saved metadata, abstracts and summaries. Verify the original paper before citing it. The application does not download or email PDFs or bypass paywalls.

## Get started

### Windows installer

1. Download `Literature-Agent-0.3.0-rc.7-Windows-x64.exe` and `SHA256SUMS.txt` from the [RC7 release](https://github.com/EdwardAiyw/literature-agent/releases/tag/v0.3.0-rc.7), then verify the checksum.
2. Install and launch; open <http://127.0.0.1:8001>. Python and Node.js are not required for the installer.
3. In Settings, select a data directory and configure/test your OpenAI-compatible model, SMTP mailbox, and sources.
4. Register Windows scheduled tasks, finish onboarding, and run a small search.
5. Create a daily subscription or convert an existing task. Test SMTP, then verify one real digest.

You need a model API key and, for email, SMTP credentials or an app password. Provider fees are separate from this project. See the [Windows user guide](docs/WINDOWS_USER_GUIDE.md) for setup, updates, and troubleshooting.

### Linux server

Follow the [deployment guide](docs/SERVER_DEPLOYMENT.md) to build images and configure a persistent volume. The server checks due subscriptions every 60 seconds and continues while your computer is off. Compose publishes only host loopback port `18081`.

Configure SSH keys and trust the verified host key first. From a Windows checkout, connect to an existing deployment with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/open-server.ps1 -Target user@server
```

The helper opens <http://127.0.0.1:18001>. The server is single-user and has no application login: keep loopback binding and use SSH forwarding. Disable desktop scheduling after migration to avoid duplicate dispatch.

## How daily selection works

For a subscription configured for `07:00`, `Asia/Hong_Kong`, and **10 papers**:

1. Search the saved topic, sources, and start date. The running-day policy advances the cutoff each day; a fixed cutoff is also available.
2. Merge current candidates, then remove papers previously delivered successfully by this subscription.
3. Screen remaining candidates, summarize, and optionally review evidence; select at most 10, as configured for this subscription.
4. When papers qualify, send the digest and persist delivery identities after SMTP success, then process the optional Zotero import batch.
5. Current source and upgraded servers enter the pause-and-summary flow below when retrieval and processing are healthy but yield zero papers. Source/model failures preserve the subscription and expose diagnostics.

The target is an **upper bound**. Send fewer when fewer qualify; do not recycle delivered papers to fill the quota. Ten is only an example. The RC7 installer retains its original empty-result notice; automatic pause and historical synthesis require current source or an upgraded server.

- Identity matching uses normalized DOI, PMID, versionless arXiv/source IDs, and conservative title/author matching. Incomplete metadata can still prevent a match.
- History is subscription-specific. Changing recipients does not reset it; separate subscriptions can deliver the same paper. One-off tasks only deduplicate their current search.
- SMTP tests, failed deliveries, and `--no-send` do not consume papers.
- New subscriptions default to the running-day cutoff; legacy subscriptions retain fixed-date behavior until changed.
- Regular dispatch and manual subscription runs share a local-calendar-day guard, with active-run exclusion. SMTP success confirms acceptance by the mail server, not inbox receipt.

See [deduplication, date policy, migration, and delivery limits](docs/DAILY_DEDUPLICATION.md).

## Automatic pause and complete historical synthesis

Automatic closure requires a completed live subscription run, successful or cached diagnostics for every selected source, no source or model-processing errors, and **zero final papers**. Failed, partial, rate-limited, disabled, unconfigured or missing source diagnostics do not qualify. One-off tasks, fixture data, SMTP tests and `--no-send` do not trigger it. Only the affected subscription pauses; this does not establish that the entire field has no new research.

The flow is:

1. **Pause future dispatch.** Save the paused state and the historical evidence snapshot used for this report. The scheduler skips that subscription.
2. **Send a separate pause notice.** Explain the reason, time, historical digest/paper counts and how to resume. Stop recurring empty digests.
3. **Send the historical synthesis.** Read every successful formal digest for this subscription, deduplicate, analyze in batches and merge the results. The UI's 50/100-record history limits do not truncate this corpus. Failed/test/notice/summary emails neither enter the literature corpus nor consume delivery identities.

The report covers themes, methods, findings, relationships and disagreements, limitations in this collection, and proposed next steps. Numbered citations such as `[P0001]` connect the synthesis to a complete per-paper appendix containing available original abstracts, saved briefs, evidence warnings, metadata and original links. Reconstructed older records and missing evidence are labeled. Attachments include `literature-history-report.md` and, when reliable identifiers exist, `zotero-identifiers.txt`.

| Action in Daily Subscriptions | Result |
| --- | --- |
| Inspect pause status | View the reason, time, historical paper count and notice/report status |
| Download the complete report | Available after generation, even if summary email delivery failed |
| Retry notice and summary | Continue failed work using saved batches/report, skip emails already recorded as successful, and avoid new retrieval or Zotero imports |
| After the report completes or fails, edit and enable daily execution | Resume scheduling while preserving delivery history; adjust topic, dates or sources first if needed |

Pause takes effect immediately. Notice or report failure does not re-enable the subscription. Restart recovery resumes interrupted queued/running reports; explicitly failed jobs require a retry. Active reports block conflicting new runs and deletion for that task. Invalid JSON, sections, reference IDs or output length receive at most one model repair; persistent errors preserve checkpoints and mark the report failed.

The report uses saved abstracts and briefs; **paper full texts have not been read**. Valid citation IDs do not independently verify scientific claims. An explicit user request can pause and summarize an existing latest completed zero-paper run through `POST /api/subscriptions/{id}/closure/start`, retaining source warnings without repeating retrieval. See [conditions, APIs, errors and recovery](docs/SUBSCRIPTION_CLOSURE.md).

## Data and limitations

| Data | Storage |
| --- | --- |
| Tasks, papers, runs, deliveries, identity history | `literature_agent_v2.db` in the selected directory; SQLite WAL with Alembic migrations |
| Pause state, evidence snapshots, synthesis checkpoints and reports | Subscription/run artifacts in the same database; deleting a subscription removes its history and report, so download them first |
| Non-secret settings | `settings.json` in the same directory |
| Windows secrets | Current user's Windows Credential Manager |
| Linux server secrets | Permission-restricted plaintext `secrets.json`; protect the volume and backups |

Queries go to selected sources; paper metadata, abstracts and synthesis materials go to the configured model; digests, notices and reports go through your SMTP provider. Database backups do not include all settings or credentials. Back up configuration separately, avoid live cloud synchronization of SQLite, and use a consistent backup rather than copying a database without its WAL. Desktop and server databases do not synchronize.

Providers can throttle or fail; diagnostics distinguish cached, partial, rate-limited, and failed results. Publisher JIF coverage is incomplete, and preprints/conference papers are usually inapplicable. No model-estimated JIF or substitute citation metric is used. LocalJev is optional and disabled by default; the validated server configuration remains Shadow after active screening failed its quality gate.

Historical synthesis adds model calls and larger emails; costs and message-size limits depend on your providers. Retries skip successfully recorded emails, but a crash after SMTP acceptance and before local recording can still cause duplicate delivery. Strict exactly-once delivery is not guaranteed.

## Run from source

Requires **Python 3.12+, Node.js 22, and npm**. Windows PowerShell:

```powershell
git clone https://github.com/EdwardAiyw/literature-agent.git
cd literature-agent
python -m venv backend/.venv
./backend/.venv/Scripts/python.exe -m pip install -e "./backend[dev]"
cd frontend
npm ci
npm run build
cd ..
./backend/.venv/Scripts/python.exe -m literature_agent.launcher --port 8001
```

Open <http://127.0.0.1:8001> and configure/enable live retrieval, the model and SMTP in Settings. A fresh unconfigured source runtime defaults to offline operation; saved settings remain effective. `.env` remains a development/migration fallback; do not commit secrets. Before updating an existing source deployment, back up data and configuration, run `git pull`, install dependencies and rebuild the frontend as above, then restart. Use the deployment guide for Linux image upgrades.

For frontend development, run the backend and Vite in separate terminals:

```powershell
# Terminal one, starting from repository root
cd backend
./.venv/Scripts/python.exe -m uvicorn literature_agent.api:app --host 127.0.0.1 --port 8001
```

```powershell
# Terminal two, starting from repository root
cd frontend
npm run dev
```

Vite serves <http://127.0.0.1:5175> and proxies `/api` to port `8001`. See the [operations manual](docs/V2_OPERATIONS_MANUAL.md) for configuration and API debugging.

## Validation and development

Validation as of **2026-11-09**:

| Scope | Result and limits |
| --- | --- |
| Current backend source | **328 passed**, covering pause conditions, historical coverage, transaction rollback, checkpoints, model repair, email retries and APIs |
| Final current server image | Isolated **327 passed, 1 Windows-only test skipped**; deployment preserved all 17 tables and settings/secrets, with healthy worker and scheduler |
| Frontend and GitHub CI | Production build and **1 added Edge mobile interaction test** passed; feature/fix commits passed backend, frontend and LocalJev CI |
| Live historical synthesis | 26 successful digests and 322 records merged into **235 paper identities**, no missing historical records; 235 appendix entries and both attachments verified, notice and summary accepted by SMTP, inbox arrival unverified |
| Published Windows RC7 | Historical release baseline: **299 backend tests, 36 full Edge regressions** and packaging checks; this installer excludes the new closure feature |

See [closure validation](docs/SUBSCRIPTION_CLOSURE.md), [server deployment](docs/SERVER_DEPLOYMENT.md) and the [RC7 release record](docs/RELEASE_RC7.md). Automated tests mock the model and SMTP. Live report validation does not independently verify every scientific claim or guarantee other providers' availability. RC7 clean-system onboarding, natural scheduling and external inbox receipt require separate [acceptance checks](TEST_GUIDE.md).

Use an isolated test data directory and bootstrap configuration instead of production settings; see the [test setup](TEST_GUIDE.md#18-开发者自动化测试附录):

```powershell
cd backend
./.venv/Scripts/python.exe -m pytest -q
cd ../frontend
npm run build
npm run test:e2e
```

Browser tests require Windows Edge and `backend/.venv`; they use isolated port `8011` and test data with real model/mail calls disabled. Exclude test output, secrets, and personal databases from commits.

## Repository layout

| Path | Contents |
| --- | --- |
| `backend/src/literature_agent/` | FastAPI, workflow, sources, scheduling, email, historical synthesis and database access |
| `backend/alembic/`, `backend/tests/` | SQLite migrations and backend tests |
| `frontend/` | React / TypeScript / Vite UI and Playwright interaction tests |
| `deploy/` | Linux Docker / Compose and optional LocalJev service |
| `scripts/`, `packaging/` | SSH access, scheduled tasks, acceptance and Windows packaging helpers |
| `docs/` | Features, APIs, operations, releases and validation records |

## Documentation

| Topic | Documents |
| --- | --- |
| Setup and troubleshooting | [Windows guide](docs/WINDOWS_USER_GUIDE.md) · [Server deployment and rollback](docs/SERVER_DEPLOYMENT.md) |
| Sources and daily selection | [Eleven source connections](docs/SOURCES.md) · [History and cutoff rules](docs/DAILY_DEDUPLICATION.md) |
| Automatic pause and synthesis | [Conditions, emails, complete reports, retry and resume](docs/SUBSCRIPTION_CLOSURE.md) |
| Zotero and JIF | [Imports and attachments](docs/ZOTERO.md) · [Journal metrics](docs/JOURNAL_METRICS.md) |
| Obsidian | [Vault connection, automatic sync and troubleshooting](docs/OBSIDIAN.md) |
| Prompts and LocalJev | [Prompt system](docs/PROMPT_SYSTEM.md) · [LocalJev](docs/LOCALJEV.md) · [Cloud quality gate](docs/LOCALJEV_CLOUD_VALIDATION_2026-10-16.md) |
| Development and operations | [Architecture](docs/ARCHITECTURE.md) · [Operations](docs/V2_OPERATIONS_MANUAL.md) · [Windows release](docs/WINDOWS_RELEASE.md) |
| Progress and validation | [Current state](docs/CURRENT_STATE.md) · [Roadmap](docs/ROADMAP.md) · [Changelog](CHANGELOG.md) · [Acceptance tests](TEST_GUIDE.md) |

## Feedback and license

Report bugs through [GitHub Issues](https://github.com/EdwardAiyw/literature-agent/issues/new?template=bug_report.yml) or [email](mailto:aiyuling.usm@gmail.com). Include version, reproduction steps, run ID, and redacted screenshots. Follow the [security policy](SECURITY.md) for vulnerabilities and [contribution guide](CONTRIBUTING.md) for code changes.

Licensed under [GNU AGPL-3.0](LICENSE), provided as-is without warranty.
