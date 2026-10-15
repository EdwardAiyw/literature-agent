# Literature Agent

中文版本：[README.md](README.md)

Literature Agent is a self-hosted literature search and daily email assistant for Windows. Enter a research topic and it searches several public scholarly sources, removes duplicates, ranks relevance, and produces concise research briefs. You can also create a daily subscription that runs automatically and sends an HTML and plain-text digest to your inbox.

The application runs locally on your computer. It does not require a Literature Agent account, does not download or send PDFs, and does not bypass paywalls. Paper records include DOI and source links so that you can open and verify the original work.

> **RC4 candidate status (October 15, 2026)**
>
> `v0.3.0-rc.4` includes generic default Prompt v2, Zotero integration, DOI metadata deduplication, database replacement locking, and destination-status refresh. Local validation passed 105 backend tests, 18 Edge regressions, and the frontend build. GitHub Windows Release generates the installer and `SHA256SUMS.txt`; verify that the workflow succeeded and assets are present before downloading. RC4 remains a prerelease pending manual installer acceptance.

> **Download and feedback**
>
> - [Download the Windows prerelease](https://github.com/EdwardAiyw/literature-agent/releases/tag/v0.3.0-rc.4)
> - [Email feedback](mailto:aiyuling.usm@gmail.com?subject=%5BLiterature%20Agent%20RC4%5D%20Feedback)
> - [Open a GitHub bug report](https://github.com/EdwardAiyw/literature-agent/issues/new?template=bug_report.yml)

For the original Chinese user guide, see [README.md](README.md).

## Contents

- [What it does](#what-it-does)
- [Requirements](#requirements)
- [Install the Windows release](#install-the-windows-release)
- [First-time setup](#first-time-setup)
- [Run a literature search](#run-a-literature-search)
- [Create a daily subscription](#create-a-daily-subscription)
- [Understand results](#understand-results)
- [Data, credentials, and privacy](#data-credentials-and-privacy)
- [Backup, restore, update, and uninstall](#backup-restore-update-and-uninstall)
- [Troubleshooting](#troubleshooting)
- [Run from source](#run-from-source)
- [Testing](#testing)
- [Contributing and security](#contributing-and-security)
- [License](#license)

## What it does

- Searches Semantic Scholar, OpenAlex, Crossref, arXiv, and PubMed.
- Supports Chinese, English, or bilingual queries.
- Restricts publication date ranges and target result counts.
- Plans searches, queries sources, normalizes and deduplicates records, filters for relevance, and writes research briefs.
- Optionally performs an evidence review that flags claims not supported by the available source material.
- Shows per-source success, failure, and result counts.
- Lets you mark papers for deep reading, saving, background, or ignoring.
- Sends daily HTML and plain-text email digests.
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

## Install the Windows release

1. Open the [`v0.3.0-rc.4` Release](https://github.com/EdwardAiyw/literature-agent/releases/tag/v0.3.0-rc.4).
2. Download both `Literature-Agent-0.3.0-rc.4-Windows-x64.exe` and `SHA256SUMS.txt`. Do not use GitHub's `Source code (zip)` as an installer.
3. In the download folder, open PowerShell and verify the installer:

   ```powershell
   Get-FileHash .\Literature-Agent-0.3.0-rc.4-Windows-x64.exe -Algorithm SHA256
   ```

   Compare the hash with the RC4 `SHA256SUMS.txt` from the same Release. If they differ, delete the downloaded file and download it again.

4. Run the installer. The prerelease is not commercially code-signed, so Windows SmartScreen may require **More info > Run anyway** after you have verified the checksum.
5. Start the application from the installer or the Windows Start menu. It opens a browser at <http://127.0.0.1:8001>.

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

On **Daily Subscriptions**, enter a name, topic, recipients, target count, local execution time, time zone, optional date range, and one or more sources. Common time zones include `Asia/Shanghai`, `Asia/Hong_Kong`, and `Asia/Kuala_Lumpur`.

Before relying on automation:

1. Send a subscription test email.
2. Confirm that `[Literature Agent] SMTP test` arrives, including in spam.
3. Run the subscription manually once.
4. Confirm that the research digest arrives and the delivery record is `sent`.
5. Confirm that both Windows scheduled tasks are registered.

The browser does not need to stay open, but the computer must be powered on, connected, and allowed to run the scheduled tasks. Checks occur every 15 minutes rather than exactly at the configured minute. A subscription runs at most once per calendar day in its configured time zone.

## Understand results

- `Queued`: waiting for the local worker.
- `Running`: searching or processing.
- `Completed`: results are ready.
- `Failed`: the page includes the error and corrective action.

Source diagnostics show each provider's status and returned record count. One failed provider does not necessarily invalidate results from other providers. Relevance is an ordering aid, not a quality score. Papers without abstracts may have weaker screening signals, so inspect the original source.

Workspace history can be searched, filtered, edited, or deleted. Deleting a task permanently deletes its run records and paper results.

## Data, credentials, and privacy

The selected data directory contains:

- `literature_agent_v2.db`: tasks, subscriptions, papers, runs, and deliveries.
- `settings.json`: non-secret settings.
- `logs/`: rotating logs retained for 14 days.
- `backups/`: manual and safety backups.

Model, SMTP, and source credentials are stored in the current Windows user's Credential Manager under names beginning with `LiteratureAgent/`. Credentials are not copied when a database is moved to another computer, and uninstalling does not automatically remove them or user data.

During a real run, query text and paper metadata are sent to the selected scholarly sources. The topic and paper metadata used for summarization are sent to the configured model provider. Email summaries are sent through the configured SMTP provider. Do not enter confidential information that should not be shared with those providers.

## Backup, restore, update, and uninstall

Use **Settings > Backup now** before upgrades or other maintenance. Keep the resulting `.db` file on a separate disk or trusted backup service.

To restore, stop active runs, choose **Restore backup**, and confirm. The application creates a `before-restore-*.db` safety copy. Restore replaces database content but does not replace Windows Credential Manager entries.

To update, back up first, download the matching installer and checksum file from the Release page, verify the checksum, and install over the existing version. The data directory, credentials, subscriptions, and history are preserved.

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

### Semantic Scholar returns 429

This is provider rate limiting. Retry later, add a Semantic Scholar key, or rely on the other sources while the service backs off.

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

RC4 source and installer include explicit per-paper citation import from the workbench; the older RC3 installer does not include it. In Settings, enter a user/group Library ID, a read/write API key, and a collection name or existing Collection Key, then test and save the connection. Keys are stored in Windows Credential Manager.

DOI matching scans paginated top-level library items because Zotero quick search does not search DOI metadata. DOI-less papers use exact title matching. Existing items keep their metadata; only collection membership is added. Large libraries may take longer to check. Saved destination changes refresh statuses even for completed runs, and switching back restores that destination's records. Import and database replacement are mutually exclusive (HTTP 409 on conflict). Imports contain citation metadata only; the desktop client receives them through Zotero sync. See [Zotero configuration and troubleshooting](docs/ZOTERO.md).

## Testing

Run the backend tests, build the frontend, and execute browser regression tests:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm ci
npm run build
npm run test:e2e
```

Browser tests use an isolated port (`8011`) and test data directory. They do not modify the product database running on port `8001`.

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
