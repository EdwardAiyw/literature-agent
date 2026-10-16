# LocalJev cloud screening validation — 2026-10-16

## Decision

Cloud connectivity works, but active screening **did not pass** the quality and speed gate. Keep production in Shadow mode: ordinary model screening controls results. The active optimization is implemented and tested, but must not be promoted based on this evaluation.

## Reproducible comparison

Pinned LocalJev baseline: `3f23e36e1a3bff46c7e83e8e3781d3512bc82021`, MIT, with explicit JSON Object compatibility. Upstream: `deepseek-chat`; effective Prompt: `relevance_screener.v2`; auto threshold: 0.82. Both comparison arms used two workers. A new temporary SQLite database prevented application decision-cache hits; upstream prompt caching was not disabled. Ordinary calls ran first, so this is one sequential comparison, not a statistically controlled speed benchmark.

The 12 cases are the ten existing synthetic holdout cases plus the two development clinical cases. They cover paired topics, missing abstracts, population mismatch, Chinese and English, and metadata prompt injection. These are authored fixtures, not a real-paper retrieval benchmark. No prompts or thresholds were tuned after observing the results.

| Path | Correct labels | Valid outputs | Ordinary screening calls | Wall time |
| --- | --- | --- | --- | --- |
| Ordinary model | 12/12 | 12/12 | 12 | 7.96 s |
| Active Jev + ordinary fallback | 10/12 | 12/12 | 9 | 13.47 s |

Active mode falsely accepted the unrelated solar-cell/sleep and bicycle/protein-folding pairs with confidence 1.0. A threshold alone cannot detect this error. Lower ordinary-call count did not improve wall time. The acceptance requirements (>=90% agreement, no unrelated acceptance, 100% valid output, fewer ordinary calls and shorter wall time) were not met.

Full synthetic outputs are in [the JSON report](validation/localjev-cloud-2026-10-16.json). Reproduce with configured model/Jev settings:

```sh
python scripts/evaluate-jev-screening.py --output output/task-subscription/jev-evaluation.json
```

The command makes paid model requests, reads current settings, writes only its report and temporary decision database, and sends no email or Zotero writes. It exits nonzero when the gate fails. Revised decision rules require a fresh holdout before promotion.

## Verification

- 159 backend tests passed, including bounded concurrency, stable processing order, progress counts, active skip, shadow baseline, low-confidence/error fallback, audit skip markers and Prompt/task/deployment cache invalidation.
- Vendored LocalJev: typecheck and 20 tests passed, including JSON Object schema instructions, validation and one bounded repair.
- Production frontend build and five focused Edge browser checks passed.
- Isolated server authenticated model listing passed; unauthenticated model listing returned HTTP 403. Idle memory was about 10 MiB within the 128 MiB limit. The initial readiness check failed because the cloud catalog omitted the working legacy alias; canonical-model validation below resolved it.

The existing production run completed with 50 papers and its digest was accepted by SMTP at 08:09 Asia/Hong_Kong. This proves server acceptance, not inbox receipt. It used the ordinary model path captured before Jev was enabled. It was not interrupted, restarted or mailed again.

## Deployed server follow-up

- Runtime images: `literature-agent:9ab4b74` and `literature-localjev:9ab4b74`. The follow-up lockfile/documentation commit does not alter runtime source. RC5 Windows release tags/assets remain unchanged.
- Cloud `/models` listed `deepseek-flash` and `deepseek-v4-pro`; a real `deepseek-chat` completion resolved to `deepseek-flash`. Configured LocalJev with that canonical name while retaining the ordinary model's existing alias. `/api/jev/status` now reports `ready`, with the actual upstream model visible.
- Paused scheduling, verified no active runs, stopped the application and backed up SQLite plus settings, secrets and deployment configuration before replacement. All 14 database tables matched their pre-update content after deployment. Existing 07:00 Asia/Hong_Kong schedule and history were retained.
- Executed an isolated real-model workflow with the saved task and one real retrieved paper: completed with one paper, two `shadow_observed` decisions, ordinary-model screening/evidence results, no errors, and progress `1/1`. This called real planning, screening, summary and evidence models; retrieval was constrained to that supplied paper. It sent no mail and made no Zotero writes.
- Both containers were healthy, with zero OOMs and restarts. Added a dedicated project-owned 2 GiB swap file when existing swap was full; preserved the original swap. Docker boot startup is enabled.
- Restored daily scheduling and removed the temporary LocalJev staging container. Ordinary decisions remain authoritative. No duplicate production run or digest was created.
- Bun 1.3.5 initially rejected the inherited version-2 lockfile. The version-1 lockfile passed frozen installation, typecheck and all 20 tests in the actual pinned Linux Bun image.
