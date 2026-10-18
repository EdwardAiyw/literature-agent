# Product Requirements

## Product goal

Provide a local-first academic literature agent that automatically delivers a traceable daily digest of relevant papers without binding the user to one discipline.

## Primary workflow

1. Configure a daily subscription: topic, optional research questions, language policy, date range, target count, sources, recipient, and schedule.
2. The scheduled agent retrieves, deduplicates, excludes papers successfully delivered by that subscription, screens, ranks, and selects up to the configured target (task creation defaults to 10; subscription creation requires an explicit target). Fewer qualifying papers produce fewer results; empty results produce an explanatory notice.
3. The agent generates Chinese summaries and recommendation reasons, then sends an email digest containing metadata, DOI, and original links.
4. The user reviews the run, source diagnostics, results, and delivery status in the GUI.
5. The user explicitly imports selected papers into Zotero from the workbench or enables task-specific automatic import into an exact existing collection. The Web API connector deduplicates by DOI (exact title when DOI is absent) and reports per-paper results.

## Product boundaries

The first product release is single-user, local-first, and Windows-oriented. It does not bypass paywalls, scrape authenticated databases, attach PDFs to delivery emails, generate a complete thesis chapter, or make unsupported claims about a paper.

## Language policy

Tasks support Chinese, English, and bilingual retrieval. Original metadata remains unchanged. The default analysis language is Chinese.

## Delivery policy

New subscriptions advance the cutoff to the running day in their time zone unless a fixed cutoff is selected. Legacy subscriptions retain fixed-date behavior. Successful digest history is subscription-specific and survives ordinary run deletion.

The daily email contains titles, authors, sources, publication dates, DOI, original links, Chinese summaries, and recommendation reasons. It attaches a UTF-8 identifier TXT when reliable DOI/PMID/arXiv/ISBN/ADS metadata exists, selecting one identifier per paper and reporting missing IDs. It does not contain PDF attachments. Zotero can import these identifiers and use the user's own attachment-retrieval configuration when available.
