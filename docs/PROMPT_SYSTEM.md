# Prompt System

Built-in prompts define how to process a task; users supply what to research through each task's inputs. No research topic is hard-coded. They are versioned by role and seeded into SQLite at startup. Each run resolves its catalog once and snapshots prompt IDs, versions and bodies. Advanced users can clone a prompt into a custom version, activate it globally, or select a version for one task. Built-in IDs and bodies are immutable, including during startup seeding.

**Release status (2026-10-15): v2 is the released default.** Initial requests timed out; after the endpoint recovered, frozen candidates passed real-model development/holdout comparison and source-by-source review. v1 remains available for rollback. See [validation results and limitations](PROMPT_V2_VALIDATION.md).

## Roles

- `query_planner.v1`: topic to search plan.
- `relevance_screener.v1`: paper and task to relevance decision.
- `literature_summarizer.v1`: paper to research decision summary.
- `evidence_reviewer.v1`: summary to evidence warnings.

The corresponding `.v2` defaults use the current task rather than a fixed discipline. Screening defines semantic-fit scoring (P0 >=0.70, P1 >=0.40, otherwise P2); missing abstracts signal uncertainty, not automatic irrelevance. Planning returns at most four complementary queries and invents no research questions or exclusions. Summaries distinguish proposed methods, observed results, associations and causal conclusions. Evidence review checks source support without inventing corrected facts. All roles treat instructions embedded in paper metadata or previous model outputs as data.

## Runtime nodes

The graph executes `query_planner`, `retrieval`, `dedupe`, `relevance_screener`, and `literature_summarizer`. `evidence_reviewer` runs only when the task enables evidence review. Each node writes a user-readable event and a structured artifact to the run record.

## Output contract

```json
{
  "research_problem": "",
  "method": "",
  "main_findings": [],
  "limitations": [],
  "relevance_reason": "",
  "research_use": "",
  "recommended_action": "read|save|background|ignore",
  "confidence": 0.0,
  "evidence_warnings": []
}
```

The model must write `not stated in source` when the supplied title or abstract does not support a claim. Original title, authors, abstract, DOI, and URLs are never rewritten by the model.

When no model credentials are configured, deterministic fallback implementations satisfy the same output contracts. Fallback use is recorded through the `engine` field and does not silently claim model-generated evidence.

## Complete workflow and task fields

Task form/API -> SQLite -> bounded local worker -> resolve task prompts -> query planning -> source retrieval -> deduplication -> relevance screening and selection -> summarization -> optional evidence review -> persistence/workbench. Subscriptions reuse the pipeline, followed by email. Zotero import is a separate explicit per-paper action. The local application can still call configured remote models and sources.

| Input | Actual execution | Limits |
|---|---|---|
| `topic` | Planner, screener and summarizer use the current task | No fixed discipline |
| `research_questions` | Planner and screener receive them; summarizer now does too | Optional; absent means topic-only analysis, not invented questions |
| `language` | Guides planner query language | No hard language filter in source adapters |
| `output_language` | Available to all four model roles | v2 specifies Chinese/English/bilingual explanations; keys, enums and missing-evidence marker remain unchanged; fallback is not newly localized |
| `date_from`, `date_to` | Source filtering; original bounds recorded in the planning artifact | Unknown dates can be retained and marked by existing adapters |
| `sources` | Executor uses user-selected sources | Nonempty task selection takes precedence over planner routing |
| `target_count` | Retrieval limits and final selection | Existing selection can retain low-score papers to fill the count |
| `evidence_review` | Controls whether evidence review runs | Disabled means no review node |
| `prompt_overrides` | Explicit role version takes precedence over global activation | Tasks pinned to v1 remain pinned after upgrade |

Planner queries are executed, deduplicated and capped at four. Its `exclusions` are recorded but not applied as hard search filters or forwarded to screening. Explicit scope in the task remains available to planning and screening. `language_policy` is planning metadata; `recommended_action=ignore` does not itself remove a record. Source diversity eligibility (0.55) is distinct from priority thresholds. This change does not add exclusion fields or change retrieval/ranking algorithms.

The backend supports research questions and output language. The current task creation UI does not expose questions and sends Chinese output; editing exposes both. Subscription creation also sends fixed language defaults. This change does not expand these forms.

## Model interfaces and actual output provenance

`ModelProvider.summarize(..., *, task=None)` and `review_evidence(..., *, task=None)` accept optional task context. Old positional calls remain valid. Graph calls now supply it to both, while planner/screener already receive task input. Model choice, temperature (0.1), timeout (45 seconds) and production parsing are unchanged.

The graph replaces summary `relevance_reason` and `recommended_action` with the actual screening result. Review warnings are merged and final confidence cannot exceed summary confidence. Original metadata is not rewritten. Unknown research fields use `not stated in source`; v2 requests an array containing this marker for unknown findings/limitations. Source-access caveats are warnings, not invented author-reported limitations.

Jev uses independent typed questions in `decisions.py`, not these prompt bodies. Shadow mode observes Jev while preserving the ordinary-model result; active mode can apply an eligible Jev result. Inspect `screening.engine`, `summary.engine`, `summary.evidence_review_engine`, decision audit baseline/final outcomes and routing. A v2 prompt snapshot does not establish that every final decision used v2. Jev algorithms/questions remain unchanged. Offline graph tests verify off/shadow/active-auto/active-review routes, not real Jev quality.

Unconfigured/failed models use explicit `engine=fallback`; empty live retrieval can use `fixture_fallback`. Neither counts as evidence of prompt quality or real retrieval success.

## Release and rollback

`DEFAULT_PROMPT_VERSION` in `prompts.py` is the explicit release gate. It is now `v2` after recorded acceptance, registering both versions:

- Fresh databases select v2 for all roles.
- Existing databases upgrade an active built-in v1 only when that role's v2 is first inserted. Custom defaults, explicit task overrides and historical snapshots are retained.
- Explicitly activating v1 after upgrade survives restart. Deleting an active custom version restores the released built-in default.
- Seeding is atomic and insert-only. First insertion is the one-time upgrade marker; no schema migration is required.

For future versions, do not manually pre-seed unreleased rows into production: that consumes the first-insertion marker. Candidate evaluation uses no app database. Creating a custom version through the existing API immediately activates it, so evaluation deliberately does not use that API.

## Fixed-input comparison and acceptance

`backend/tests/fixtures/prompt_cases.json` contains 20 pre-labelled **synthetic** task-paper cases, 10 development / 10 holdout. Reused papers and paired topics stay within a split. Coverage includes multiple disciplines, no questions, missing abstracts, language variants, negative findings, homonyms and embedded instructions; evidence cases contain deliberately unsupported claims. This is a small regression aid, not a real-paper retrieval benchmark or statistical guarantee.

From the repository root:

```powershell
backend/.venv/Scripts/python.exe scripts/evaluate-prompts.py --split development --workers 4 --out output/prompt-v2/development.json
# Freeze candidates after development review, then run the independent holdout:
backend/.venv/Scripts/python.exe scripts/evaluate-prompts.py --split holdout --workers 4 --out output/prompt-v2/holdout.json
```

The script reuses configured model settings without changing the app database. Both versions use the same current call path, one sample per input/role/version. Reports contain exact prompt text, fixture hash, inputs, raw content, parsed outputs, actual engine, token usage and timing, never credentials. Raw validation runs before production coercion/clamping can hide defects. Results are saved as they arrive; three provider errors stop subsequent batches. An incomplete/fallback/unreachable run cannot pass.

Acceptance requires all v2 raw outputs to satisfy their JSON contracts, clear relevant/unrelated decisions not to regress, no new major unsupported claims on holdout, and at least one observed baseline defect fixed. Manually audit source support and requested language for each summary and verify that evidence warnings identify the planted claim. Nonempty warnings or numeric-token heuristics alone do not prove correctness. Record the review in the validation report before releasing; the script never automatically releases candidates. If holdout results guide revisions, replace the holdout before acceptance.

Point tests at an isolated data directory/database before pytest: existing API tests initialize a database at import time.
