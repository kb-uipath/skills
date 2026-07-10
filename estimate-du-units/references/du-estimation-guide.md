# DU Estimation Guide

Use this reference for source discipline, versioned calculator contracts, migration, and recovery. Rates in test fixtures are synthetic and must not be used as licensing guidance.

## Source Hierarchy

| Rank | Source | Notes |
|---:|---|---|
| 1 | Customer production logs, queue counts, Orchestrator data | Best evidence for actual customer volume |
| 2 | Source-system reports | Imaging, claims, ERP, CRM, mailbox, repository, or case system |
| 3 | Document repository counts | Folder, batch table, document class, or scan count |
| 4 | Official or regulatory workload estimate | Label as a proxy when not customer-specific |
| 5 | SME estimate | Use a confidence discount and scenario band |
| 6 | Scenario band | Use during early discovery |

For rates, use the current official UiPath metering or licensing source applicable to the customer's deployment and package path. A source URL alone is not verification; record when it was accessed, when the rate became effective, and how long the verification may be reused.

## Applicability Decision Table

| Condition | Status | Result behavior |
|---|---|---|
| Scanned paper, PDF, image, fax, or attachment is OCRed | `yes` | Calculate consumption |
| Document type is classified from content or image | `yes` | Calculate consumption |
| Fields are extracted from a document | `yes` | Calculate consumption |
| Automation uses only structured source-system fields or an API | `no` | Preserve page context and force units to zero |
| Automation clicks a downstream category from existing metadata | `no` unless it re-reads the page | Force units to zero when `no` |
| Description mentions scanning, indexing, or batching but not OCR/extraction | `conditional` | Calculate a conditional estimate and state the triggering condition |
| Another metered product processes text outside DU | `no` for DU | Estimate under that product's meter instead |

Every status requires a non-empty rationale. `conditional` is not a substitute for missing analysis; its rationale must name the condition that changes the result.

## Versioned Rate Profile

Contract: `estimate-du-units.rate-profile.v1`. Normative schema: `rate-profile.v1.schema.json`.

| Field | Contract |
|---|---|
| `schema_version` | Exact value `estimate-du-units.rate-profile.v1` |
| `profile_id` | Non-empty identifier for the verified set |
| `rates[].name` | Unique component name |
| `rates[].unit` | `ai_unit` or `platform_unit` |
| `rates[].rate` | Non-negative canonical decimal string per page |
| `rates[].source_url` | Absolute HTTP(S) URL for the source used |
| `rates[].accessed_on` | ISO date on which the source was checked |
| `rates[].effective_on` | ISO date on which the rate became effective |
| `rates[].max_age_days` | Non-negative freshness window for that component |

Components sharing a unit are additive. A profile may carry one unit type without the other. The tool rejects duplicate component names, unsupported fields, malformed URLs or dates, negative or noncanonical rates, sources accessed after `as_of`, and rates not yet effective on `as_of`.

Freshness is calculated as `as_of - accessed_on`. A component is stale only when its age is greater than `max_age_days`; the boundary day is accepted. Stale profiles fail closed unless `--allow-stale-rates` is supplied, in which case every stale component and the override remain visible in the output.

## Versioned Structured Input

Contract: `estimate-du-units.input.v1`. Normative schema: `input.v1.schema.json`.

```json
{
  "schema_version": "estimate-du-units.input.v1",
  "estimate_id": "customer-process-scenario",
  "as_of": "2026-07-10",
  "applicability": {
    "status": "conditional",
    "rationale": "Consumption applies only when scanned attachments are sent through DU."
  },
  "scenarios": [
    {
      "name": "base",
      "documents": [
        {
          "name": "primary-form",
          "annual_transactions": "1200",
          "pages_per_transaction": "2.5"
        },
        {
          "name": "supporting-attachment",
          "annual_transactions": "600",
          "pages_per_transaction": "3"
        }
      ]
    }
  ]
}
```

Scenario and document names must be unique within their scope. Decimal fields are strings so exact base-10 arithmetic survives JSON parsing. Scenarios are alternatives; the calculator aggregates documents within each scenario but never totals across scenarios.

## Output Contract

Contract: `estimate-du-units.output.v1`. Normative schema: `output.v1.schema.json`.

- `--format json` emits the complete versioned object.
- `--format markdown` renders the same object as rate, document, and aggregate tables.
- `exact` is the lossless decimal result.
- `rounded` is a whole-unit decimal string rounded half up.
- `rate_context.components` retains source, dates, age, max age, and stale status.
- `rate_context.totals_per_page` exposes additive totals by unit.
- `calculation_applied` is `false` when applicability is `no`.

## Formula

For each document:

```text
annual_pages = annual_transactions x pages_per_transaction
unit_rate_per_page = sum(all rate components for that unit)
annual_units = annual_pages x unit_rate_per_page
```

For each scenario:

```text
scenario_pages = sum(document annual_pages)
scenario_units = sum(document annual_units for each unit independently)
```

Do not add AI Unit results to Platform Unit results. Do not add low, base, and high scenarios together.

## Legacy Migration

The old command silently supplied rates. That behavior is removed and now fails closed.

Preferred migration: move documents and applicability into `input.v1`, create a sourced `rate-profile.v1`, and run:

```bash
python3 estimate-du-units/scripts/du_estimate.py \
  --input estimate-du-units/tests/fixtures/multi-document-input.v1.json \
  --rate-profile estimate-du-units/tests/fixtures/rate-profile.v1.json \
  --format json
```

Temporary legacy migration: `--case` parsing is preserved only when rates and verification are explicit:

```bash
python3 estimate-du-units/scripts/du_estimate.py \
  --case base=1200,2.5 \
  --ai-rate RATE_FROM_VERIFIED_SOURCE \
  --verified-on YYYY-MM-DD \
  --as-of YYYY-MM-DD \
  --applicability yes \
  --rationale "Pages are sent through DU." \
  --format json
```

Replace placeholders with verified values. Explicit rates use a 30-day freshness window unless `--max-rate-age-days` is supplied. `--extra-ai-rate` and `--extra-platform-rate` are repeatable additive components but require their corresponding base rate. A rate profile is intentionally rejected with `--case`; migrate to structured input to use profile provenance.

## Failure Recovery

| Failure | Recovery |
|---|---|
| No rates supplied | Add `--rate-profile`, or explicit rate flags plus `--verified-on` |
| Explicit rate lacks verification | Re-check the source and pass its actual access date with `--verified-on` |
| Stale rate rejected | Refresh the source and date; use `--allow-stale-rates` only with explicit risk acceptance |
| Future accessed/effective date | Correct the profile or estimate `as_of`; do not override chronology errors |
| Unsupported schema version or field | Migrate to the exact v1 schema; do not delete provenance fields |
| Invalid decimal | Use a non-negative decimal string such as `"1200"` or `"2.5"` |
| Missing applicability rationale | Decide `yes`, `no`, or `conditional` and record the evidence-based reason |
| Legacy `--case` with a profile | Move the scenario into `input.v1`, or use explicit verified rates temporarily |

## Validation Commands

```bash
python3 -m unittest discover -s estimate-du-units/tests -p 'test_*.py'
python3 tools/validate_repo.py
```
