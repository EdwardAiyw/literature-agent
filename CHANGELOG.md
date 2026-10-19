# Changelog

## Unreleased

- Sync complete email text and identifier attachments into Obsidian, with source diagnostics, deduplication statistics and shared JIF provenance in paper notes; label reconstructed historical messages explicitly.
- Persist rendered mail/attachment/paper snapshots before SMTP for successful-delivery export and protect hand-edited TXT assets with stored hashes.

- Make Obsidian a built-in desktop Settings feature with vault discovery, saved local/server connections, sync-now, independent task controls, status and open-index actions; reject desktop actions on the server.
- Support packaged `--sync-obsidian CONFIG`, automatic source/EXE task selection and task removal on uninstall; preserve the existing explicit-config CLI and destination-specific note mappings. Published RC6 binaries remain unchanged.

- Add source-only Obsidian sync for successful server digests via read-only SSH snapshots, linked daily/paper Markdown notes, identity reuse and preserved personal annotations.
- Add an independent Windows login/15-minute sync task, catch-up after offline periods and local status reporting. Published RC6 assets are unchanged.

- Correct the Sandbox finalizer to validate the actual restore success response and safety backup, and check scheduled task names explicitly. Published RC6 installer assets remain unchanged.
- Record 26 passing Sandbox lifecycle checks, the data-preserving desktop upgrade, and real installed-binary retrieval with loopback SMTP receipt.

## 0.3.0-rc.6 - 2026-10-18

- Merge cross-source paper identities and exclude each subscription's successful delivery history before model screening. Backfill durable `digest_history` snapshots independently of run deletion; do not consume papers for failed/test/no-send mail.
- Add running-day/fixed subscription cutoffs and restart-safe configuration snapshots; preserve legacy fixed-date behavior. Show history exclusion statistics and explain empty digests without reusing delivered papers.
- Rewrite Chinese/English READMEs around runtime choices, daily selection and source quickstart; retain detailed Windows steps in a separate user guide.

- Automatically enrich selected papers with DOI journal metadata and explicitly published publisher JIF/year/source before digest creation and automatic Zotero import. Add bounded public HTTPS lookup, shared caches, a settings toggle and run diagnostics; preserve delivery on lookup failure and user-imported metrics on same-year conflicts. Validate three real Frontiers journals; other publishers may block access or lack supported formats. Retain atomic JCR CSV imports, existing Zotero metadata and identifier-only TXT. No model-estimated factors or substitute citation metrics.

- Add task/subscription-specific opt-in Zotero import into exact existing collections, read-only collection selection, durable destination snapshots, batch progress/retry and restart recovery independent of retrieval/mail.
- Share one remote DOI index per batch attempt, preserve existing metadata/collections, verify target membership and block deletion/database replacement while import work is pending.
- Attach UTF-8 Zotero identifier TXT files to daily digests, preserving actual DOI/PMID/arXiv/ISBN/ADS identifiers with one preferred identifier per paper, deduplication and missing-ID notices; offer downloads for existing runs without resending mail.

- Vendor pinned MIT LocalJev with JSON Object cloud compatibility, internal authenticated Compose service, bounded resources and reproducible screening evaluation.
- Pass effective task/Prompt context to Jev; version cache by deployment; bound screening workers and record intermediate counts and skipped ordinary calls. Active high-confidence screening skips duplicate model requests; Shadow retains ordinary decisions.
- Record the failed real DeepSeek active-screening gate; retain production Shadow mode. Confirm the first server digest was accepted by SMTP without repeating the completed run.

- Add opt-in Linux server mode with a persistent, permission-restricted secret store and a 60-second scheduler using the existing bounded worker and per-day database guard.
- Add a loopback-only Docker deployment, SSH web access helper and Windows-to-server migration/operations guide.
- Edit existing daily subscriptions from the webpage, including schedule and enabled state, while preserving hidden research settings, Prompt overrides and history.
- Display server-specific settings/scheduler status and reject online server database replacement or Windows scheduler actions.

## 0.3.0-rc.5 - 2026-10-15

- Convert an existing task to a daily subscription from the current task or history, preserving identity, research settings, Prompt overrides and run history; guard duplicate/stale requests atomically.
- Keep same-day manual runs from suppressing a newly converted subscription's daily schedule, and reject subscription deletion while its task is active.
- Add desktop/mobile conversion regressions and isolate browser fixture runs from real model/mail endpoints.
- Enforce relevance >=0.40 and respect `ignore` after final ordinary/Jev routing; exclude unverified keyword fallbacks from live results instead of filling target counts with unrelated papers.
- Validate multilingual query plans and repair invalid plans once; record concise-query execution requirements without modifying published Prompt bodies.
- Keep empty live searches empty and skip unsupported Chinese-only arXiv queries instead of substituting generic results.
- Show executed queries, date bounds and screening counts; explain empty digests without recommending rejected papers.
- Add Crossref contact identification and shared per-provider pacing, bounded HTTP 429 retries and Retry-After cooldowns for Crossref/Semantic Scholar.
- Preserve completed queries and earlier pages after later source failures; cache only completed queries, and account for each actual retry against the request budget.
- Explain source rate limits and partial results in the workbench/settings checks, including legacy HTTP 429 diagnostics. Anonymous Semantic Scholar availability remains provider-controlled.

## 0.3.0-rc.4 - 2026-10-15

- Bundle the LocalJev decision layer and controls added after RC3, and gate Windows publishing on packaged runtime, Prompt catalog, Zotero settings and frontend smoke checks.
- Add Zotero user/group library settings, secure API key storage, read-only permission tests, and validated legacy configuration migration.
- Add explicit per-paper citation import, DOI/title deduplication, collection membership, persistent import status and retry in the workbench.
- Back up and migrate existing databases to preserve destination-specific Zotero import results.
- Fix Zotero DOI-only metadata deduplication with a paginated library scan, and use attempt-scoped creation tokens so deletion and re-import do not reuse a consumed token.
- Hold the import lock throughout data-directory changes and backup restoration to prevent saving remote import results into a replaced database.
- Refresh completed-run Zotero statuses after destination changes and reject late responses from the old destination.
- Release generic default Prompt v2 with retained v1/custom/task versions and fixed-case validation; see `docs/PROMPT_V2_VALIDATION.md`.

## 0.3.0-rc.3 - 2026-09-25

- Make Windows scheduler status checks degrade cleanly on timeout and keep Jev decision audit ordering deterministic.
- Prevent startup deadlocks when a recovered run completes before its callback is registered.
- Report private GitHub Releases as unavailable instead of incorrectly claiming the app is current.
- Run the frontend build and Edge Playwright regression before publishing Windows Release assets.
- Add external Beta feedback templates, security guidance, and RC3 version identification.

## 0.3.0-rc.2 - 2026-09-24

- 增加页面化首次配置、LLM、SMTP、来源、Jev 和运行参数设置。
- 使用 Windows Credential Manager 保存 API Key 和 SMTP 密码。
- 增加设置热更新、连接测试、数据目录选择、备份恢复和日志轮转。
- 增加 Windows 计划任务页面管理和重复运行保护。
- 增加 PyInstaller、Inno Setup 与 GitHub Releases 自动构建流程。
- 保留现有 `.env`、SQLite 数据库和无 Jev 运行路径的兼容性。
- 串行保护共享 SQLite 连接，修复并发初始化中的虚假 404 和 500。
- 增加首次加载、轮询和任务切换的请求取消与过期响应保护。
- 修复 390px 移动端和 768px 平板端的导航、表单与任务列表横向溢出。
- 增加 100 组双初始化并发回归和 Edge Playwright 响应式回归。
- 增加 Windows Sandbox 安装、备份恢复和卸载验收工具。
