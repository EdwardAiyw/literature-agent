# Zotero automatic import and identifier attachment validation

Implemented source: `647ed43`, validation-error fix: `b131145`. Production app image: `literature-agent:b131145`. Existing Windows RC5 release/tag/assets were not changed. LocalJev retains its prior image and Shadow configuration.

## Automated validation

- GitHub [CI 38997988386](https://github.com/EdwardAiyw/literature-agent/actions/runs/38997988386): all three jobs passed; backend **182 tests**, frontend production build, LocalJev typecheck/tests.
- Local backend baseline plus new regressions: 179 passed, followed by 10 focused Zotero job tests after adding three more cases and checking invalid merged targets return HTTP 422.
- Edge Playwright full suite: **30 passed**. After the final task-destination invalidation change, all three affected server/batch browser cases passed again; frontend production build passed.
- New coverage includes identifier validation (DOI/PMID/arXiv/ISBN/ADS), deduplication/missing identifiers/ignored records, UTF-8 MIME round trip, shared DOI indexing, pagination/full collection paths, preservation of existing metadata/memberships, concurrent enqueue idempotency, lost-response retry without duplicates, partial-progress recovery, completion/enqueue restart recovery, immutable destinations, library mismatch, SMTP failure independent of import, configuration preservation and TXT download.
- Browser fixtures remain isolated from live model/mail/Zotero writes. Preexisting workspace screenshots were restored from byte-identical backups and excluded from commits.

## Server update and real import acceptance

- No active retrieval run at cutover. Full backup of SQLite, settings, secrets and Compose environment retained on the server before update; only the app container was replaced.
- All **14 database table content hashes** matched after update and before enabling automatic imports. Settings, secret store and LocalJev environment hashes also matched.
- Read-only collection listing confirmed the exact user-selected existing **Daily Digest** collection. Enabled automatic import only for the existing approved daily task/subscription, retaining recipient, research settings, history, enabled state and **07:00 Asia/Hong_Kong** schedule.
- Backfilled only the approved Oct17 successful daily run containing 50 records. Result: **47 imported, 3 existing, 0 failed, 0 skipped**. Two DOI-less records exactly matched titles already imported in the batch, so these 50 result records map to **48 unique Zotero items**. A separate read-only paginated collection query confirmed every resulting item key belongs to Daily Digest.
- Existing run/paper/delivery/Prompt/decision history hashes remained unchanged. No retrieval was rerun and **no email was resent**. This validates actual Zotero writes/membership; desktop display still requires ordinary Zotero synchronization.
- Existing run export produced **48 real identifier lines**, with **2 records lacking reliable identifier metadata**. A digest rendered inside the deployed container included the matching TXT attachment without SMTP transmission. The next normal daily digest uses this attachment behavior; the already-received email is unchanged.
- Production webpage confirmed real TXT download, saved exact collection, enabled automatic import, preserved schedule and mobile layout without writes. Scheduler restored to its prior unpaused state after import verification.

## Limits and operations

The batch worker is intended for the existing single API process. A whole-library scan is required once per batch attempt for DOI metadata matching. External Zotero clients can still change or create items concurrently; version conflicts/uncertain responses end the attempt, and failure retry rebuilds the remote index. Provider 429 responses remain possible. Number recognition in Zotero depends on its own metadata services; missing IDs are reported rather than inferred from titles.

See [Zotero configuration, APIs and retry behavior](ZOTERO.md) and [server deployment/rollback](SERVER_DEPLOYMENT.md). Backups and exported user identifiers stay outside Git.
