---
name: estimate-du-units
description: Estimate annual UiPath Document Understanding AI Unit or Platform Unit consumption from customer automation descriptions, especially messy natural-language descriptions involving scanned documents, forms, OCR, classification, extraction, indexing, manual queues, batches, faxes, PDFs, or document routing. Use when Codex needs to decide whether DU applies, infer documents and page volume, source or annualize workload counts, calculate low/base/high consumption, explain assumptions, or produce a planning estimate for a UiPath customer.
---

# Estimate DU Units

## Operating Rules

- Treat licensing and metering as time-sensitive. Never infer, remember, or silently default a rate.
- Require either a versioned `rate-profile.v1` file or explicit `--ai-rate` and/or `--platform-rate` values with `--verified-on`.
- Prefer official UiPath sources for metering, customer operational data for volume, and official or regulatory sources only when customer data is unavailable.
- Keep AI Units and Platform Units separate. Do not convert or combine them.
- Classify applicability as `yes`, `no`, or `conditional`, and require a concrete rationale for every call.
- State that every result is a planning estimate, not a quote or entitlement statement.
- Do not perform external writes. The bundled calculator reads local inputs and emits to stdout only.

## Workflow

1. Normalize the customer wording.
   - Extract action verbs: read, classify, extract, index, route, validate, assign, click.
   - Extract document cues: scanned, PDF, image, fax, form number, attachment, batch, manual indexing, OCR.
   - Extract systems: scanner, mailbox, repository, case system, Orchestrator, queue, target app.
   - Rewrite as: "This appears to [process action] [document type] from [source] and [write/route/assign] [output] in [target]."

2. Decide whether Document Understanding applies.
   - Use `yes` only when pages are digitized, classified, extracted, or otherwise processed by DU/IXP.
   - Use `no` when the automation only uses structured data, APIs, existing metadata, or clicks a value after an upstream actor identified the document.
   - Use `conditional` when the path is unclear, and state the exact condition under which pages reach DU.
   - The calculator forces unit results to zero for `no` while retaining page-volume context.

3. Build a structured document inventory.
   - For each scenario and document type, capture annual transactions and pages per transaction.
   - Include cover sheets, attachments, blanks, split packets, retries, rejects, duplicate scans, and reprocessing in those values when applicable.
   - Count pages processed, not cases, batches, or work items.
   - Encode numeric JSON values as non-negative decimal strings to preserve exact arithmetic.

4. Establish annual volume.
   - Source priority: customer production logs, source-system reports, repository counts, official or regulatory workload data, SME estimate, scenario band.
   - Annualize partial data transparently: 90-day count x 365 / 90, monthly average x 12, weekly average x 52, daily average x business days.
   - Keep public or national form volume separate from customer-specific volume.

5. Build and verify rate provenance.
   - Record each additive rate component with `name`, `unit`, `rate`, `source_url`, `accessed_on`, `effective_on`, and `max_age_days`.
   - Use only `ai_unit` or `platform_unit`; multiple components for one unit are added before calculation.
   - Verify deployment, plan, project type, package/API path, add-ons, and consumption unit from current official sources.
   - Reject stale or future-dated components. Use `--allow-stale-rates` only when the user explicitly accepts the risk; the override remains visible in output.

6. Calculate and sanity-check.
   - Base formula: `annual_units = annual_transactions x pages_per_transaction x additive_rate_per_page`.
   - Sum documents within each scenario. Do not sum alternative low/base/high scenarios together.
   - Preserve exact decimals and separately round annual units to whole units using half-up rounding.
   - Use `scripts/du_estimate.py` for deterministic arithmetic.

7. Present the estimate.
   - Lead with aggregate scenario totals and the applicability call.
   - Include per-document results, exact and rounded values, rate components, verification dates, warnings, assumptions, confidence, and source links.
   - Ask only clarifying questions that would materially change applicability, page volume, or rate selection.

## Calculator

Preferred invocation:

```bash
python3 estimate-du-units/scripts/du_estimate.py \
  --input estimate-du-units/tests/fixtures/multi-document-input.v1.json \
  --rate-profile estimate-du-units/tests/fixtures/rate-profile.v1.json \
  --format markdown
```

The bundled fixtures are synthetic contract examples, not current licensing rates. For machine output, use `--format json`. Legacy `--case label=transactions,pages` remains available only with explicit rates, `--verified-on`, `--applicability`, and `--rationale`; it does not accept a rate profile.

## Confidence

- High: current metering profile passes its freshness gate, page count is sampled, and annual volume comes from production data.
- Medium: metering and page count are verified, but volume is public, annualized, or SME-estimated.
- Low: DU routing is conditional, packet shape is unknown, volume is weak, or mixed/classic/generative add-ons may be missing.

## Robustness Checks

Before finalizing, confirm:

- The automation sends pages to DU rather than using only structured metadata.
- The page count includes every processing and reprocessing path in scope.
- Annual volume is customer-specific unless clearly labeled as public or proxy volume.
- Every rate component has current source provenance and is effective on the estimate date.
- The output uses `estimate-du-units.output.v1`, exposes stale overrides, and keeps unit types separate.
- Customer-facing text retains the planning-only disclaimer.

## References

- Read `references/du-estimation-guide.md` for contract semantics, migration guidance, source hierarchy, and failure recovery.
- Validate rate profiles against `references/rate-profile.v1.schema.json`.
- Validate structured inputs against `references/input.v1.schema.json`.
- Consume machine output according to `references/output.v1.schema.json`.
