# Versioned data contracts

The machine-readable planning path uses two strict JSON artifacts:

- `evidence_ledger.json`, governed by [`contracts/evidence_ledger.v1.schema.json`](contracts/evidence_ledger.v1.schema.json).
- `portfolio.json`, governed by [`contracts/portfolio.v1.schema.json`](contracts/portfolio.v1.schema.json).

Both artifacts require `schema_version: "1.0"`. Unknown fields, unsupported versions, dangling IDs, stale scores, invalid value calculations, deployment gaps, and unsupported entitlement claims fail validation. The Python runtime uses the same contract rules without requiring a JSON Schema package.

## Evidence ledger v1

Use one stable ID namespace per customer analysis:

- `INV-*` for inventory rows. Generate these IDs with `inventory_profiler.py`; do not use row names as keys because names can be duplicated or edited.
- `SRC-*` for public sources. Record publication and access dates separately.
- `ASM-*` for planning assumptions. Mark each assumption `unvalidated`, `validated`, or `rejected`.

The ledger also records deployment model, data classification, GenAI policy, human-approval requirements, and entitlement status. A `confirmed` entitlement requires a public source or validated assumption reference. `unknown` is the safe default.

## Portfolio v1

Each `OPP-*` opportunity must cite inventory IDs and public source IDs. Assumption IDs are required whenever an assumption affects value, feasibility, deployment, or entitlement reasoning. Criteria scores are integers from 0 to 5; the scripts calculate both high-impact and POC scores with scoring model `1.0`.

Calculated value supports only these deterministic formulas:

- `volume_minutes_rate_v1`: `annual_volume * minutes_saved_per_case / 60 * loaded_hourly_rate`.
- `hours_rate_v1`: `annual_hours * loaded_hourly_rate`.

Do not put arbitrary expressions in JSON. Use `qualitative` value framing when evidence is incomplete.

## Migration from legacy artifacts

Unversioned JSON is rejected. Do not add `schema_version` to an old file and assume it is valid.

1. Regenerate `inventory_profile.json` to obtain stable `INV-*` IDs.
2. Build `evidence_ledger.json` with explicit `INV-*`, `SRC-*`, and `ASM-*` records.
3. Convert recommendations to `portfolio.json` with `OPP-*` IDs and evidence references.
4. Run `score_portfolio.py` into a new output path.
5. Run `validate_portfolio.py` before rendering Markdown or DOCX.

The legacy Markdown-only validator remains available for structural checks. It does not certify evidence, scores, dates, deployment fit, value math, or entitlements unless the JSON cross-check options are supplied.
