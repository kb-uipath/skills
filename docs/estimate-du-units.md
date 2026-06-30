# estimate-du-units

## Purpose

Estimate annual UiPath Document Understanding AI Unit or Platform Unit consumption from customer
automation descriptions, especially messy natural-language descriptions involving scanned documents,
forms, OCR, classification, extraction, indexing, manual queues, batches, faxes, PDFs, or document
routing.

## When to use

Estimate annual UiPath Document Understanding AI Unit or Platform Unit consumption from customer
automation descriptions, especially messy natural-language descriptions involving scanned documents,
forms, OCR, classification, extraction, indexing, manual queues, batches, faxes, PDFs, or document
routing. Use when Codex needs to decide whether DU applies, infer documents and page volume, source
or annualize workload counts, calculate low/base/high consumption, explain assumptions, or produce a
planning estimate for a UiPath customer.

## Required inputs

- Automation or process description.
- Known document, page, batch, or transaction volumes.
- Document types and whether OCR, classification, extraction, or validation is needed.
- Time period for annualization and assumptions to preserve.

## Prompt template

```text
Use $estimate-du-units to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $estimate-du-units to estimate annual DU consumption for this invoice intake process: 18,000 invoices per month, average 3 pages, scanned PDFs, classify plus extract 12 fields, 20 percent human validation.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../estimate-du-units/SKILL.md`](../estimate-du-units/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../estimate-du-units/`](../estimate-du-units/) when present.
