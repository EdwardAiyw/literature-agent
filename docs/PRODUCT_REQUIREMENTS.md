# Product Requirements

## Product goal

Provide a local-first academic literature agent that automatically delivers a traceable daily digest of relevant papers without binding the user to one discipline.

## Primary workflow

1. Configure a daily subscription: topic, optional research questions, language policy, date range, target count, sources, recipient, and schedule.
2. The scheduled agent retrieves, deduplicates, screens, ranks, and selects 10-20 papers.
3. The agent generates Chinese summaries and recommendation reasons, then sends an email digest containing metadata, DOI, and original links.
4. The user reviews the run, source diagnostics, results, and delivery status in the GUI.
5. The user imports selected papers into Zotero by DOI. A future Zotero connector may automate this step.

## Product boundaries

The first product release is single-user, local-first, and Windows-oriented. It does not bypass paywalls, scrape authenticated databases, attach PDFs to delivery emails, generate a complete thesis chapter, or make unsupported claims about a paper.

## Language policy

Tasks support Chinese, English, and bilingual retrieval. Original metadata remains unchanged. The default analysis language is Chinese.

## Delivery policy

The daily email contains titles, authors, sources, publication dates, DOI, original links, Chinese summaries, and recommendation reasons. It does not contain PDF attachments. Zotero is expected to import citations by DOI and use the user's own attachment-retrieval configuration when available.
