---
name: estimate-du-units
description: Estimate annual UiPath Document Understanding AI Unit or Platform Unit consumption from customer automation descriptions, especially messy natural-language descriptions involving scanned documents, forms, OCR, classification, extraction, indexing, manual queues, batches, faxes, PDFs, or document routing. Use when Codex needs to decide whether DU applies, infer documents and page volume, source or annualize workload counts, calculate low/base/high consumption, explain assumptions, or produce a planning estimate for a UiPath customer.
---

# Estimate DU Units

## Operating Rules

- Treat licensing and metering as time-sensitive. For customer-facing estimates, verify current UiPath docs and licensing pages before finalizing.
- Prefer official UiPath sources for metering, customer operational data for volume, and official/regulatory sources only when customer data is unavailable.
- Keep AI Units and Platform Units separate. Do not convert between them unless the current licensing source provides the rate.
- State whether the result is a planning estimate, not a quote.
- If DU applicability is unclear, provide a conditional estimate and the smallest set of clarifying questions.

## Workflow

1. Normalize the customer wording.
   - Extract action verbs: read, classify, extract, index, route, validate, assign, click.
   - Extract document cues: scanned, PDF, image, fax, form number, attachment, batch, manual indexing, OCR.
   - Extract systems: scanner, mailbox, repository, case system, Orchestrator, queue, target app.
   - Rewrite as: "This appears to [process action] [document type] from [source] and [write/route/assign] [output] in [target]."

2. Decide whether Document Understanding applies.
   - Count DU only when pages are digitized, classified, extracted, or otherwise processed by DU/IXP.
   - Estimate zero DU units when the bot only uses structured data, APIs, existing metadata, or clicks a value after humans/upstream systems already identified the document.
   - Mark "unclear" when the description says manual indexing, scan, batch, or form number but does not say whether the bot reads the image.

3. Build a document inventory.
   - For each document type, capture source, page count, page-count evidence, attachments, cover sheets, blank pages, split packets, retries, rejects, duplicate scans, and reprocessing.
   - Count pages processed, not cases, batches, or work items.
   - Use low/base/high page counts when packets can vary.

4. Establish annual volume.
   - Source priority: customer production logs, source-system reports, repository counts, official/regulatory workload data, SME estimate, scenario band.
   - Annualize partial data transparently: 90-day count x 365 / 90, monthly average x 12, weekly average x 52, daily average x business days.
   - Keep national/public form volume separate from the customer's actual volume.

5. Select metering.
   - Verify modern vs classic vs mixed DU, package/API path, and whether Generative Validation or standalone classic activities are used.
   - Current public defaults to verify: modern DU is page-based at 1 AI Unit per processed page; UiPath licensing has listed IXP Document Understanding at 0.2 Platform Units per page.
   - If Generative Validation, classic extractors/classifiers, or mixed projects are present, check current official docs and add the incremental consumption explicitly.

6. Calculate and sanity-check.
   - Base formula: `annual_units = annual_transactions x average_pages_per_transaction x units_per_page`.
   - For multiple documents: sum each document type separately.
   - Use `scripts/du_estimate.py` for repeatable arithmetic when helpful.
   - Round planning estimates sensibly after showing the exact base calculation.

7. Present the estimate.
   - Lead with the number and formula.
   - Include the applicability call, low/base/high band, assumptions, confidence, and source links.
   - List only the clarifying questions that would materially change the estimate.

## Confidence

- High: current metering verified, page count known from samples or form source, annual volume from customer production data.
- Medium: metering and page count known, but volume is public, annualized, or SME-estimated.
- Low: unclear DU path, unknown document packet shape, no reliable volume, or potential mixed/classic/generative add-ons.

## Robustness Checks

Before finalizing, check:

- The automation really sends pages to DU, not just structured metadata.
- The page count includes cover sheets, attachments, blanks, and split/retry behavior when applicable.
- Annual volume is customer-specific unless clearly labeled as public or proxy volume.
- The calculation uses pages processed by DU, not business transactions completed.
- The estimate names the metering model and date/source used.
- AI Unit and Platform Unit outputs are not merged into one number.

## References

- Read `references/du-estimation-guide.md` for the full worksheet, source hierarchy, response template, decision rules, and worked SSA CMS-1763 example.
- Use `scripts/du_estimate.py` to calculate low/base/high scenario tables.
