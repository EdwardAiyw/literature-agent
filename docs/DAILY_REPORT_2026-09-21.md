# Literature Agent Daily Report - 2026-09-21

## Today's conclusion

The product is aligned around one primary outcome: a local-first agent that delivers a daily bilingual literature digest. It is not merely a literature-search workbench, and FAMOU is not part of the daily runtime.

The required daily loop is:

1. Read the user's subscription topics and preferences.
2. Search supported Chinese and English literature sources on schedule.
3. Deduplicate, screen, rank, and select 10-20 papers.
4. Generate Chinese summaries and concise recommendation reasons.
5. Send one daily email containing the digest, DOI, and original links.
6. Record the complete result and delivery status locally.
7. Let Zotero import papers by DOI; the agent must not send or manage PDF email attachments.

## Confirmed decisions

- Platform: single-user, local-first, Windows-oriented desktop product.
- Languages: bilingual retrieval; Chinese is the default UI and analysis language.
- Daily volume: 10-20 ranked papers per digest, configurable by the user.
- Sources: OpenAlex, Crossref, arXiv, and PubMed are the current real-source baseline. Chinese academic sources will be added only through legal, supported access methods.
- Email: deliver the daily summary with title, authors, source, publication date, DOI, original link, Chinese summary, and recommendation reason.
- PDF policy: no PDF attachments in email. The digest exposes DOI and links so Zotero can import the citation and retrieve attachments through the user's configured Zotero workflow when available.
- Zotero: DOI-based import is the first integration priority. Direct open-access PDF download can be a later enhancement, not a prerequisite for daily email delivery.
- LLM: optional OpenAI-compatible provider configuration with deterministic fallback. The model and whether separate Chinese/English models are needed remain open decisions.
- FAMOU: development-only evaluation support for prompts, source weighting, ranking, and retrieval quality. It must not run automatically in the daily delivery workflow.

## Delivered in the current codebase

- FastAPI backend, SQLite persistence, React/TypeScript workbench, and LangGraph-oriented retrieval flow.
- Agent nodes for query planning, retrieval, deduplication, relevance screening, literature summarization, optional evidence review, and completion.
- Persisted run events, node artifacts, progress, result manifests, and prompt-version snapshots.
- API support for run events, artifacts, prompt catalog, and settings inspection.
- Source adapters for OpenAlex, Crossref, arXiv, and PubMed, with concurrent retrieval and per-source diagnostics.
- Deterministic fixture mode and tests for source retrieval, including partial source failures.
- Project-local FAMOU skills and documentation, isolated from the runtime agent.

## Verified status

- Backend test suite passed after the real-source adapter work: 8 tests passed.
- Frontend production build passed before the current unfinished source-selection UI work.
- The GUI still creates runs with the fixture source hard-coded. Source selection, date fields, and source diagnostics display remain to be completed and re-verified.
- The running backend may be stale because it was previously started without reload; restart it after backend changes before manual testing.

## Next implementation priority

1. Complete and verify source/date selection in the GUI, then display per-source diagnostics from run artifacts.
2. Add persistent daily subscriptions: topics, language policy, sources, target count, schedule, recipient, and enabled state.
3. Add an independently runnable daily CLI job for Windows Task Scheduler. The scheduler must not depend on the GUI or FastAPI background tasks.
4. Build the daily HTML and plain-text email digest with DOI and original links only.
5. Add SMTP settings, secret-safe configuration, delivery history, retryable failure records, and a manual test-send action.
6. Implement Zotero DOI-based import and report per-paper import results.

## Explicitly deferred

- PDF email attachments and automatic attachment extraction from the mailbox.
- Direct open-access PDF download as a required daily-delivery step.
- Selection of a production LLM provider or a two-model Chinese/English design.
- Automatic FAMOU execution or a FAMOU product UI.
- Tauri packaging, Windows Credential Manager integration, and advanced pause/resume/cancel recovery.

## Definition of success for the next milestone

At the configured time, a Windows scheduled task can execute the agent without the GUI open; retrieve and rank literature from real sources; email a traceable daily digest of 10-20 papers with Chinese summaries, DOI, and links; persist the delivery result; and make the same digest viewable in the GUI.
