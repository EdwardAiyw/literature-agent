# Literature Agent

中文版本：[README.md](README.md)

Literature Agent is a self-hosted literature search and daily email assistant for Windows or a Linux server. Enter a research topic and it searches several public scholarly sources, removes duplicates, ranks relevance, and produces concise research briefs. You can also create a daily subscription that runs automatically and sends an HTML and plain-text digest to your inbox.

The application runs locally on your computer. It does not require a Literature Agent account, does not download or send PDFs, and does not bypass paywalls. Paper records include DOI and source links so that you can open and verify the original work.

> **Release status (October 15, 2026)**
>
> [`v0.3.0-rc.5`](https://github.com/EdwardAiyw/literature-agent/releases/tag/v0.3.0-rc.5) is published as a prerelease with task-to-daily conversion, relevance filtering and source rate-limit repairs, retaining default Prompt v2, Zotero and LocalJev. The 150 backend tests, 27 Edge regressions, frontend build, GitHub CI, Windows Release and packaged checks passed. The publicly downloaded installer matches its SHA-256 checksum. Full manual installer acceptance remains required before stable promotion.

> **Download and feedback**
>
> - [Download the Windows prerelease](https://github.com/EdwardAiyw/literature-agent/releases/tag/v0.3.0-rc.5)
> - [Email feedback](mailto:aiyuling.usm@gmail.com?subject=%5BLiterature%20Agent%20RC5%5D%20Feedback)
> - [Open a GitHub bug report](https://github.com/EdwardAiyw/literature-agent/issues/new?template=bug_report.yml)

For the original Chinese user guide, see [README.md](README.md).

Current source also supports opt-in task/subscription imports into exact Zotero collections, durable batch status/retry, and UTF-8 identifier TXT attachments in daily digests. One real DOI, PMID, arXiv ID, ISBN or ADS bibcode is selected per paper and deduplicated; missing IDs are reported. Existing runs offer downloads without resending mail. These source updates are not included in the existing RC5 Windows installer. See [Zotero operations](docs/ZOTERO.md).

Live runs automatically look up explicitly published journal JIF values on publisher websites and include the metric year and source link in the workbench, daily digests and new Zotero journal items. Coverage is partial; missing values stay unknown, preprints/conference papers are inapplicable, and lookup failures do not prevent mail. Existing JCR CSV imports remain available. Disable automatic lookup in Settings, or set its initial default with `JOURNAL_METRICS_AUTO=false`. See [journal metrics](docs/JOURNAL_METRICS.md).

## Contents

- [Changes in RC5](#changes-in-rc5)
- [What it does](#what-it-does)
- [Requirements](#requirements)
- [Install the Windows release](#install-the-windows-release)
- [First-time setup](#first-time-setup)
- [Run a literature search](#run-a-literature-search)
- [Create a daily subscription](#create-a-daily-subscription)
- [Runtime Prompts and task input](#runtime-prompts-and-task-input)
- [Understand results](#understand-results)
- [Zotero citation import](#zotero-citation-import)
- [Data, credentials, and privacy](#data-credentials-and-privacy)
- [Backup, restore, update, and uninstall](#backup-restore-update-and-uninstall)
- [Troubleshooting](#troubleshooting)
- [Run from source](#run-from-source)
- [Testing](#testing)
- [Contributing and security](#contributing-and-security)
- [License](#license)

## Changes in RC5

| Change | Result |
| --- | --- |
| Task-to-daily conversion | Reuse a current or historical task with its ID, research settings and history; add recipient, time and time zone |
| Relevance gate | Exclude scores below 0.40, ignore recommendations and unverified keyword fallbacks from live results |
| Search transparency | Inspect executed queries, date bounds and screening totals; validate bilingual query plans |
| Source resilience | Pace/retry Crossref and Semantic Scholar, respect cooldowns, preserve partial results and explain limits |
| Retained capabilities | Prompt v2 with v1/custom/task overrides, Zotero import, backups and optional Jev |

RC4 assets and tags remain available, but do not contain these conversion, relevance or rate-limit changes. Rerun searches after upgrading to apply the new rules; history is preserved.

## What it does

- Searches Semantic Scholar, OpenAlex, Crossref, arXiv, and PubMed.
- Supports Chinese, English, or bilingual queries.
- Restricts publication date ranges and target result counts.
- Plans searches, queries sources, normalizes and deduplicates records, filters for relevance, and writes research briefs.
- Optionally performs an evidence review that flags claims not supported by the available source material.
- Shows per-source success, cache, partial, rate-limit and failure states with result counts.
- Provides four generic default v2 Prompts with retained v1/custom versions and task overrides.
- Imports individual citations to Zotero with DOI/title deduplication and destination-specific status.
- Lets you mark papers for deep reading, saving, background, or ignoring.
- Converts existing tasks to daily subscriptions and sends HTML and plain-text digests.
- Keeps task history, run details, paper records, and delivery records locally.
- Provides browser controls for model, SMTP, source keys, Jev, request budgets, backups, and Windows scheduled tasks.

Generated summaries and relevance scores are screening aids, not a final assessment of paper quality. Open and verify the original paper before citing it.

## Requirements

### End users

- 64-bit Windows 10 or Windows 11.
- An OpenAI-compatible model service and API key.
- An SMTP-enabled mailbox and an SMTP authorization code or app password.
- An internet connection for searches, model calls, email delivery, and update checks.

Optional keys can improve service limits:

- Semantic Scholar API key.
- OpenAlex API key.
- PubMed API key and contact email.
- TypeSafe/Jev API key when testing the Jev decision layer.

API keys, SMTP authorization codes, and mailbox passwords are not the same as ordinary website passwords. Never put real credentials in screenshots, issues, chat messages, or commits.

### Developers

- Python 3.12 or newer.
- Node.js 20.19+ or 22.12+ (Node.js 22 is recommended for development).
- Windows Edge for browser regression tests.

## Server deployment

The source runtime also supports a single-user Linux Docker deployment. Daily searches and email continue while the desktop is off. Open the remote web UI through `scripts/open-server.ps1 -Target user@server` and edit subscription timing, time zone, topic, recipient, sources and enabled state, or run it manually. Model and mail settings remain editable in the web UI.

See the [server deployment and migration guide](docs/SERVER_DEPLOYMENT.md). The server checks schedules every 60 seconds; disable the old Windows daily task after migration to prevent duplicate delivery. Linux secrets are stored as permission-restricted plaintext files. The unauthenticated application binds to server loopback and is accessed through SSH.

This is post-RC5 source functionality; the existing RC5 installer is unchanged. Windows credential storage and 15-minute OS scheduling described below apply to desktop execution.

## Install the Windows release

1. Open the [`v0.3.0-rc.5` Release](https://github.com/EdwardAiyw/literature-agent/releases/tag/v0.3.0-rc.5).
2. Download both [Literature-Agent-0.3.0-rc.5-Windows-x64.exe](https://github.com/EdwardAiyw/literature-agent/releases/download/v0.3.0-rc.5/Literature-Agent-0.3.0-rc.5-Windows-x64.exe) and [SHA256SUMS.txt](https://github.com/EdwardAiyw/literature-agent/releases/download/v0.3.0-rc.5/SHA256SUMS.txt). Do not use GitHub's `Source code (zip)` as an installer.
3. In the download folder, open PowerShell and verify the installer:

   ```powershell
   Get-FileHash .\Literature-Agent-0.3.0-rc.5-Windows-x64.exe -Algorithm SHA256
   ```

   Compare the hash with the RC5 `SHA256SUMS.txt` from the same Release. If they differ, delete the downloaded file and download it again.

4. Run the installer. The prerelease is not commercially code-signed, so Windows SmartScreen may require **More info > Run anyway** after you have verified the checksum.
5. Start the application from the installer or the Windows Start menu. It opens a browser at <http://127.0.0.1:8001>.

The RC5 installer is 29,033,921 bytes. Its SHA-256 is:

```text
7e648d48a12397001a1b04aab39a4a58212e69293fb365ead5b2d4a269c6a0af
```

`127.0.0.1` means this computer. The local web interface is not exposed as a public website.

## First-time setup

The Settings page contains five setup areas. Complete them before using the Workspace or Daily Subscriptions pages.

### 1. Choose a data directory

Select a durable local folder such as `D:\LiteratureAgentData`. The directory stores the SQLite database, ordinary settings, logs, and backups.

- Do not use the installation folder, a temporary folder, a removable drive, or a shared network folder.
- Avoid syncing the live SQLite database with OneDrive, Nutstore, or similar tools while the application is running. Copy backup files instead.
- Do not change the data directory while a task is running.

### 2. Configure the model

Enter the OpenAI-compatible API URL, exact model identifier, and API key. For OpenAI, the URL is commonly `https://api.openai.com/v1`. Enable real searches and model calls, select **Test connection**, then **Save**.

The saved key is stored in Windows Credential Manager. A password field showing that a key is saved does not reveal the key; leaving it empty keeps the existing value.

### 3. Configure SMTP

Enter the SMTP host, port, account, authorization code or app password, sender, and test recipient. Common settings are:

| Provider | Host | Port | Encryption |
| --- | --- | --- | --- |
| 126 / QQ | `smtp.126.com` / `smtp.qq.com` | 465 | Direct SSL |
| Gmail | `smtp.gmail.com` | 465 | Direct SSL |
| Gmail / Microsoft 365 | `smtp.gmail.com` / `smtp.office365.com` | 587 | STARTTLS |

Port 465 normally uses direct SSL; port 587 normally uses STARTTLS. Select only the matching option. Enable SMTP in the mailbox provider first, generate an authorization code or app password, send a test email, and then save the settings.

### 4. Configure literature sources

Semantic Scholar, OpenAlex, Crossref, arXiv, and PubMed are available. Crossref and arXiv do not require a separate key in the current release. Test and save the source configuration. A temporary failure from one source does not necessarily fail a whole run; the run diagnostics show the status of each source.

### 5. Optional Jev decision layer

The server Compose stack includes a separate authenticated LocalJev cloud adapter (`http://localjev:8080`, alias `localjev-latest`). It uses the existing cloud model without loading a local model. The 2026-10-16 active-screening comparison failed quality and speed acceptance, so production retains Shadow mode and ordinary-model decisions. See the [measured results](docs/LOCALJEV_CLOUD_VALIDATION_2026-10-16.md).

Jev is disabled by default. Searches, filtering, summaries, and email delivery work without it. To experiment with the local Jev stack:

```powershell
.\scripts\start-jev-stack.ps1
.\scripts\start-jev-stack.ps1 -Stop
```

See [LocalJev integration](docs/LOCALJEV.md) and [Jev shadow testing](docs/V2_JEV.md) for installation and validation. Start with shadow mode so Jev decisions are recorded without changing the final selection. The automatic decision threshold must be greater than or equal to the manual-review threshold.

### 6. Register Windows tasks

The default daily request budget (`200`) and source cache (`24` hours) are suitable for most users. Select **Register scheduled tasks**. The application creates:

- `Literature Agent Local`, which starts the local service when the Windows user signs in.
- `Literature Agent Daily`, which checks for due subscriptions every 15 minutes.

The **Repair** action recreates missing tasks. **Disable** removes the tasks but keeps subscriptions and history.

## Run a literature search

Open **Workspace > Create research task** and enter:

- A recognizable task name.
- The research topic.
- Search language (Chinese, English, or both).
- Target paper count (start with `5`).
- Optional publication date range.
- One or more literature sources.
- Optional evidence review.

Leave the global prompt version unchanged on your first run. Select **Start**. The run proceeds through planning, source search, deduplication, relevance filtering, brief generation, optional evidence review, and result storage. Do not click Start repeatedly; only one active run is allowed for a task.

## Create a daily subscription

In the RC5 installer or source runtime, select **Convert to daily task** on the current-task card or the envelope action in workspace history. Review the inherited research configuration, enter the recipient, daily time and time zone, then save. Conversion retains the task ID, history, research questions, language/output settings, target count, sources, fixed date bounds, evidence review and Prompt overrides. Saving does not start a search or send mail. Converted tasks reopen their existing subscription; duplicate conversions are rejected. Deleting the subscription also deletes the original task/history and is blocked while a run is active. The dialog defaults to 08:00 and Asia/Hong_Kong; review them before saving.

On **Daily Subscriptions**, enter a name, topic, recipients, target count, local execution time, time zone, optional date range, and one or more sources. Common time zones include `Asia/Shanghai`, `Asia/Hong_Kong`, and `Asia/Kuala_Lumpur`.

Before relying on automation:

1. Send a subscription test email.
2. Confirm that `[Literature Agent] SMTP test` arrives, including in spam.
3. Run the subscription manually once.
4. Confirm that the research digest arrives and the delivery record is `sent`.
5. Confirm that both Windows scheduled tasks are registered.

The browser does not need to stay open, but the computer must be powered on, connected, and allowed to run the scheduled tasks. Checks occur every 15 minutes rather than exactly at the configured minute. A subscription runs at most once per calendar day in its configured time zone. A same-day one-off run before conversion does not consume that daily slot; active runs still prevent overlap.

## Runtime Prompts and task input

The four generic default v2 Prompts cover planning, relevance screening, summarization and evidence review. They use the current task's saved topic, research questions, language, dates and output requirements. When research questions are absent, screening follows the topic without inventing extra requirements. No fixed personal research topic is needed.

Keep the global default for the first run. Manage versions on the Runtime Prompt page or choose a task override under advanced settings. v1 and custom versions remain available. Runs retain Prompt snapshots and actual model paths; changing a default does not rewrite history. Jev receives the effective screening Prompt and task context while using independent decision questions, so inspect its routing audit when enabled. See the [Prompt system](docs/PROMPT_SYSTEM.md) and [v2 validation scope](docs/PROMPT_V2_VALIDATION.md).

## Understand results

- `Queued`: waiting for the local worker.
- `Running`: searching or processing.
- `Completed`: results are ready.
- `Failed`: the page includes the error and corrective action.

Source diagnostics show each provider's status and returned record count. One failed provider does not necessarily invalidate results from other providers. Relevance is an ordering aid, not a quality score. Papers without abstracts may have weaker screening signals, so inspect the original source.

RC5 excludes scores below 0.40, `ignore` recommendations and unverified keyword fallbacks. Scores of 0.40–0.69 may still represent background reading. Expand the executed search conditions to check queries/date bounds and inspect evaluated/rejected/selected counts. A date mentioned in topic text does not override the date fields. Existing results are preserved; the fix applies to new runs in both the RC5 installer and source runtime.

Workspace history can be searched, filtered, edited, or deleted. Deleting a task permanently deletes its run records and paper results.

## Data, credentials, and privacy

The selected data directory contains:

- `literature_agent_v2.db`: tasks, subscriptions, papers, runs, and deliveries.
- `settings.json`: non-secret settings.
- `logs/`: rotating logs retained for 14 days.
- `backups/`: manual and safety backups.

Model, SMTP, source, Zotero and Jev credentials are stored in the current Windows user's Credential Manager under names beginning with `LiteratureAgent/`. Credentials are not copied when a database is moved to another computer, and uninstalling does not automatically remove them or user data.

During a real run, query text and paper metadata are sent to the selected scholarly sources. The topic and paper metadata used for summarization are sent to the configured model provider. Email summaries are sent through the configured SMTP provider. Do not enter confidential information that should not be shared with those providers.

## Backup, restore, update, and uninstall

Use **Settings > Backup now** before upgrades or other maintenance. Keep the resulting `.db` file on a separate disk or trusted backup service.

To restore, stop active runs, choose **Restore backup**, and confirm. The application creates a `before-restore-*.db` safety copy. Restore replaces database content but does not replace Windows Credential Manager entries.

To update, finish active runs, back up and exit the running Literature Agent process, then download the matching installer and checksum file from the Release page, verify the checksum, and install over the existing version. The data directory, credentials, subscriptions, and history are preserved.

The in-app update check uses GitHub's stable-release endpoint and may not discover prereleases. Use the direct RC5 download link on this page.

Uninstall from **Windows Settings > Apps**. The program files and scheduled tasks are removed, while the data directory and credentials are retained by default. Delete those manually only after confirming that you no longer need them.

## Troubleshooting

### The page does not open

Restart Literature Agent from the Start menu, wait about ten seconds, and open <http://127.0.0.1:8001>. If port 8001 is occupied, close the other application using it and restart Literature Agent.

### Other pages redirect to Settings

Initial setup is incomplete. Check the five setup indicators, especially model saving, real-call enablement, SMTP completeness, and scheduled-task registration.

### Model connection fails

Check the full API URL (often ending in `/v1`), exact model name, key whitespace, account balance, and network access. Test again before saving.

### SMTP test fails

Use an SMTP authorization code or app password, not the mailbox login password. Match port 465 with direct SSL or port 587 with STARTTLS, keep sender and account consistent, and check spam.

### No papers are selected

Broaden the topic, remove a restrictive date range, choose multiple sources, and start with a small target count. The target is not a guarantee; papers must pass the relevance threshold.

### Crossref or Semantic Scholar returns 429

This is provider rate limiting. RC5 adds shared pacing, bounded retries and Retry-After cooldowns (at least 60 seconds after exhaustion), preserving earlier successful queries/pages. Only completed queries are cached, and every actual retry counts against the local budget. The workbench explains both current and historical HTTP 429 diagnostics; source connection checks show individual results.

Crossref uses the configured PubMed contact email or SMTP sender for mailto/User-Agent identification. Anonymous Semantic Scholar access can remain limited; save an API key under Settings > Literature sources and retry later. Raising the local daily budget cannot remove a provider limit. A read-only check on 2026-10-15 returned four Crossref records in two HTTP 200 requests, while four anonymous Semantic Scholar requests still returned HTTP 429. These repairs are included in RC5, but anonymous Semantic Scholar availability remains provider-controlled. Source updates require a backend restart after active runs finish; refreshing the browser is insufficient.

### The daily email is missing

Verify the test email and one manual run, inspect both scheduled tasks and repair them if needed, check the subscription time zone, and review **Daily Subscriptions > Delivery history**.

## Run from source

The following commands are for developers; end users should use the Windows installer.

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,release]"
.\.venv\Scripts\python.exe -m uvicorn literature_agent.api:app --host 127.0.0.1 --port 8001
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

The development frontend runs at <http://127.0.0.1:5175>; the backend runs at <http://127.0.0.1:8001>. The `.env` file is retained for source development and legacy migration only. The packaged application is configured from its Settings page.

## Zotero citation import

RC5 retains RC4's explicit per-paper Zotero import and deduplication repairs; the older RC3 installer does not include them. In Settings, enter a user/group Library ID, a read/write API key, and a collection name or existing Collection Key, then test and save the connection. Keys are stored in Windows Credential Manager.

DOI matching scans paginated top-level library items because Zotero quick search does not search DOI metadata. DOI-less papers use exact title matching. Existing items keep their metadata; only collection membership is added. Large libraries may take longer to check. Saved destination changes refresh statuses even for completed runs, and switching back restores that destination's records. Import and database replacement are mutually exclusive (HTTP 409 on conflict). Imports contain citation metadata only; the desktop client receives them through Zotero sync. See [Zotero configuration and troubleshooting](docs/ZOTERO.md).

## Testing

Local validation passed 150 backend tests, 27 Edge regressions and the frontend production build. [RC5 CI](https://github.com/EdwardAiyw/literature-agent/actions/runs/38748173439) and [Windows Release](https://github.com/EdwardAiyw/literature-agent/actions/runs/38748181058) passed, including the full backend/browser suites. An anonymous download matched both `SHA256SUMS.txt` and the GitHub asset digest. Packaged checks cover version, isolated database, Prompt v2 catalog, Zotero settings, frontend and task conversion without search or email side effects. Full manual install/upgrade, real Zotero sync, scheduling, restore and uninstall acceptance remain open. See the [public validation report](docs/VALIDATION_2026-10-15.md).

Run the backend tests, build the frontend, and execute browser regression tests:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm ci
npm run build
npm run test:e2e
```

Browser tests run sequentially against an isolated port (`8011`) and test data directory with real model/mail endpoints disabled. They do not modify the product database on port `8001`. Preserve existing screenshots and exclude generated results from commits.

Additional test and release documentation:

- [Product test and acceptance guide](TEST_GUIDE.md)
- [Windows release and maintenance](docs/WINDOWS_RELEASE.md)
- [Windows Sandbox installer acceptance](docs/INSTALLER_SANDBOX_TEST.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Local source release](docs/LOCAL_RELEASE.md)
- [LocalJev integration](docs/LOCALJEV.md)
- [Prompt system](docs/PROMPT_SYSTEM.md)
- [Changelog](CHANGELOG.md)

## Contributing and security

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Bug reports should include the application version, Windows and browser versions, reproduction steps, expected and actual results, and a relevant run ID. Remove API keys, SMTP credentials, personal data, and private paper content from logs and screenshots.

Do not disclose credentials or exploitable vulnerability details in public issues. Use GitHub's **Report a vulnerability** option in the Security tab when available, or contact the repository owner privately.

## License

Literature Agent is licensed under the [GNU Affero General Public License v3](LICENSE). It is provided as-is, without warranty.
