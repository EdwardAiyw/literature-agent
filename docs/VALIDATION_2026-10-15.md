# Source validation — 2026-10-15

This report covers the relevance, source rate-limit and task-to-daily subscription changes packaged in RC5. The published `v0.3.0-rc.4` tag and installer do not contain them. Raw local logs, database snapshots and generated test results are excluded from Git under the contribution policy.

## Final automated validation

| Check | Result |
| --- | --- |
| Full backend suite | 150 passed |
| Edge Playwright regressions | 27 passed |
| Frontend production build | Passed |
| Git whitespace check | Passed |

Backend tests used an isolated data directory. Browser tests ran sequentially against their shared isolated database, with model, Jev and SMTP endpoints disabled. Desktop/mobile conversion screenshots were inspected; three preexisting modified screenshots were preserved byte-for-byte.

Coverage includes relevance thresholds and final ordinary/Jev routing, rejection auditing, empty live retrieval, query-plan language/shape validation, request pacing and retry budgets, partial-result caching, rate-limit diagnostics, and subscription conversion. Conversion checks cover retained task settings/history, invalid schedules, duplicate and stale requests, cross-connection races, rollback, daily due checks, active-run deletion protection, reload persistence, cancellation and error retry.

## Read-only live checks

- Replaying seven historical candidates scored 0.02–0.05 selected none under the new relevance gate.
- A limited OpenAlex/DeepSeek probe retrieved ten candidates and screened eight: five were rejected, one was directly relevant and two were background references. This does not establish full five-source retrieval quality.
- At approximately 12:00 UTC, Crossref returned four records from two HTTP 200 requests. Anonymous Semantic Scholar exhausted four attempts with HTTP 429; no API key was configured. The new handling reports this limit accurately and respects cooldowns; it cannot remove the provider's limit.

These probes did not change saved tasks or send email/Zotero writes. Fixed-case Prompt validation remains documented separately in [Prompt v2 validation](PROMPT_V2_VALIDATION.md).

## Local deployment verification

After active runs finished, the local source service on port 8001 was backed up and restarted at 13:00 UTC (21:00 Asia/Hong_Kong). The conversion endpoint and updated frontend were confirmed loaded. All database table hashes and persisted settings hashes matched the pre-restart snapshots. No production task was converted or emailed during verification.

Installer acceptance and full live retrieval quality checks remain open; see the [test guide](../TEST_GUIDE.md) and [current state](CURRENT_STATE.md).
