# Literature Agent

Turn a research topic into a traceable daily literature digest.

[中文](README.md) · [Windows download](https://github.com/EdwardAiyw/literature-agent/releases/tag/v0.3.0-rc.6) · [Server deployment](docs/SERVER_DEPLOYMENT.md) · [Issues](https://github.com/EdwardAiyw/literature-agent/issues)

Literature Agent is an open-source assistant for individual researchers. It searches scholarly sources, merges duplicate records, screens relevance, generates research briefs, and records results and email deliveries. Run it on a Windows computer or your own Linux server. The UI and linked operational guides are primarily in Chinese.

## Choose a runtime

**As of October 18, 2026, the RC6 Windows installer, matching source, and upgraded server include delivery-history filtering, dynamic publication cutoffs, automatic Zotero collection imports, and publisher JIF lookup.**

| Runtime | Audience | Available features |
| --- | --- | --- |
| [Windows RC6 installer](https://github.com/EdwardAiyw/literature-agent/releases/tag/v0.3.0-rc.6) | Test users wanting an installer | Delivery-history filtering, dynamic cutoffs, automatic Zotero collection imports, publisher JIF, and the existing workbench and Prompt v2 |
| Current `main` source | Developers and users needing newer features | All implemented capabilities below |
| [Linux Docker deployment](docs/SERVER_DEPLOYMENT.md) | Users needing unattended daily operation | Self-built source image, web access through SSH |

RC6 remains a prerelease. All 26 Sandbox lifecycle checks passed, the existing Windows installation was upgraded with data preserved, and the installed binary completed a real five-paper search. Clean-system onboarding, natural schedule triggers, and external inbox receipt still require manual acceptance; see the [installer validation](docs/INSTALLER_RC6_VALIDATION_2026-10-18.md). Windows and Linux share the versioned source but require separate installation or deployment. Updating GitHub does not upgrade installed applications. Historical RC5 tags and assets remain unchanged.

## Capabilities

- Search Semantic Scholar, OpenAlex, Crossref, arXiv, and PubMed with language and publication-date controls.
- Plan queries, screen relevance, generate structured summaries, and optionally review claims against supplied evidence. Preserve executed queries, Prompt snapshots, and source diagnostics.
- Schedule HTML/plain-text digests in each subscription's time zone, with DOI and original links.
- Merge current-search duplicates and exclude papers already successfully emailed by that subscription, including older papers not yet delivered.
- Import citations individually or automatically into an exact Zotero collection, with durable progress/retry and identifier TXT attachments.
- Connect Obsidian from Settings: discover vaults, save a local/server source, sync now, manage automatic sync, inspect status, and open linked daily/paper notes while preserving annotations. This [built-in feature on `main`](docs/OBSIDIAN.md) supports Windows scheduling and offline catch-up; the published RC6 installer does not include this entry yet.
- Archive complete digest text, source diagnostics, deduplication counts, JIF provenance and identifier TXT attachments into the vault. New sends retain the original render snapshot; older reconstructed digests are labeled explicitly.
- Look up verifiable publisher JIF values with year/source, or import JCR CSV data. Lookup failure does not block delivery.
- Manage models, SMTP, sources, backups, subscriptions, and versioned Prompts from the UI; optionally inspect LocalJev decisions.

Scores and summaries support reading decisions. Verify the original paper before citing it. The application does not download or email PDFs or bypass paywalls.

## Get started

### Windows installer

1. Download `Literature-Agent-0.3.0-rc.6-Windows-x64.exe` and `SHA256SUMS.txt` from the [RC6 release](https://github.com/EdwardAiyw/literature-agent/releases/tag/v0.3.0-rc.6), then verify the checksum.
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
3. Screen remaining candidates, summarize, and optionally review evidence; select at most 10.
4. Send the digest and persist delivery identities after SMTP success, then process the optional Zotero import batch.

The target is an **upper bound**. Send fewer when fewer qualify, and an explanatory notice when none qualify. Do not recycle old papers to fill the quota. Ten is a configurable subscription target, not a global limit.

- Identity matching uses normalized DOI, PMID, versionless arXiv/source IDs, and conservative title/author matching. Incomplete metadata can still prevent a match.
- History is subscription-specific. Changing recipients does not reset it; separate subscriptions can deliver the same paper. One-off tasks only deduplicate their current search.
- SMTP tests, failed deliveries, and `--no-send` do not consume papers.
- New subscriptions default to the running-day cutoff; legacy subscriptions retain fixed-date behavior until changed.
- Regular dispatch and manual subscription runs share a local-calendar-day guard, with active-run exclusion. SMTP success confirms acceptance by the mail server, not inbox receipt.

See [deduplication, date policy, migration, and delivery limits](docs/DAILY_DEDUPLICATION.md).

## Data and limitations

| Data | Storage |
| --- | --- |
| Tasks, papers, runs, deliveries, identity history | `literature_agent_v2.db` in the selected directory; SQLite WAL with Alembic migrations |
| Non-secret settings | `settings.json` in the same directory |
| Windows secrets | Current user's Windows Credential Manager |
| Linux server secrets | Permission-restricted plaintext `secrets.json`; protect the volume and backups |

Queries and paper metadata go to selected sources and the configured model; digests go through your SMTP provider. Database backups do not include all settings or credentials. Back up configuration separately, avoid live cloud synchronization of SQLite, and use a consistent backup rather than copying a database without its WAL. Desktop and server databases do not synchronize.

Providers can throttle or fail; diagnostics distinguish cached, partial, rate-limited, and failed results. Publisher JIF coverage is incomplete, and preprints/conference papers are usually inapplicable. No model-estimated JIF or substitute citation metric is used. LocalJev is optional and disabled by default; the validated server configuration remains Shadow after active screening failed its quality gate.

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

Open <http://127.0.0.1:8001> and configure real calls in Settings. Source defaults to offline operation. `.env` remains a development/migration fallback; do not commit secrets.

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

The RC6 release passed **245 backend tests on Windows and Linux**, the frontend build, **32 full Edge regressions**, and packaged runtime checks. A public installer re-download matched the checksum file and GitHub asset digest; see the [RC6 release record](docs/RELEASE_RC6.md). A real replacement digest selected 10 papers with no overlap under the current identity rules; SMTP accepted it and all 10 Zotero imports completed. This validates that run, not universal source availability or future quotas. See the [validation record](docs/DAILY_DEDUPLICATION.md).

```powershell
cd backend
./.venv/Scripts/python.exe -m pytest -q
cd ../frontend
npm run build
npm run test:e2e
```

Browser tests require Windows Edge and `backend/.venv`; they use isolated port `8011` and test data with real model/mail calls disabled. Exclude test output, secrets, and personal databases from commits.

## Documentation

- [Windows setup and troubleshooting](docs/WINDOWS_USER_GUIDE.md) · [Server deployment and rollback](docs/SERVER_DEPLOYMENT.md)
- [Daily history and cutoff rules](docs/DAILY_DEDUPLICATION.md) · [Zotero imports](docs/ZOTERO.md) · [Journal metrics](docs/JOURNAL_METRICS.md)
- [Prompt system](docs/PROMPT_SYSTEM.md) · [LocalJev](docs/LOCALJEV.md) · [Cloud quality gate](docs/LOCALJEV_CLOUD_VALIDATION_2026-10-16.md)
- [Architecture](docs/ARCHITECTURE.md) · [Operations](docs/V2_OPERATIONS_MANUAL.md) · [Current state](docs/CURRENT_STATE.md)
- [Changelog](CHANGELOG.md) · [Acceptance tests](TEST_GUIDE.md) · [Windows release](docs/WINDOWS_RELEASE.md)

Report bugs through [GitHub Issues](https://github.com/EdwardAiyw/literature-agent/issues/new?template=bug_report.yml) or [email](mailto:aiyuling.usm@gmail.com). Include version, reproduction steps, run ID, and redacted screenshots. Follow the [security policy](SECURITY.md) for vulnerabilities and [contribution guide](CONTRIBUTING.md) for code changes.

Licensed under [GNU AGPL-3.0](LICENSE), provided as-is without warranty.
