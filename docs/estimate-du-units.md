# estimate-du-units

Estimate annual UiPath Document Understanding AI Unit or Platform Unit consumption with explicit applicability, versioned inputs, sourced rate provenance, deterministic decimal arithmetic, and stale-rate controls.

## When To Use

Use this skill when a user asks whether DU consumption applies, supplies document volumes or page counts, describes a document-heavy automation, or needs low/base/high planning scenarios. Do not use it to quote licensing, infer entitlement, or substitute remembered rates for current official sources.

## Runtime And Dependencies

- Python 3.9 or newer; verified with Python 3.9.6.
- Python standard library only; no package installation, credentials, network access, or service connection is required.
- UTF-8 JSON files for structured input and rate profiles.
- The calculator reads local files and writes Markdown or JSON to stdout. It does not modify source files or perform external writes.

## Inputs

One workload input and one rate source are mandatory.

Workload modes:

- Preferred: `--input PATH` using [`estimate-du-units.input.v1`](../estimate-du-units/references/input.v1.schema.json). It requires `estimate_id`, `as_of`, applicability `status` and `rationale`, and one or more scenarios containing one or more documents. Transaction and page values are non-negative decimal strings.
- Migration only: repeated `--case label=transactions,pages`. This legacy parser requires explicit verified rates, `--applicability yes|no|conditional`, and `--rationale`. It intentionally rejects `--rate-profile`.

Rate modes:

- Preferred: `--rate-profile PATH` using [`estimate-du-units.rate-profile.v1`](../estimate-du-units/references/rate-profile.v1.schema.json). Every additive component requires a unique name, `unit`, decimal-string `rate`, HTTP(S) `source_url`, `accessed_on`, `effective_on`, and `max_age_days`.
- Migration only: `--ai-rate` and/or `--platform-rate` with `--verified-on`. Repeatable `--extra-ai-rate` and `--extra-platform-rate` values are additive and require the corresponding base rate. Explicit rates use a 30-day maximum age unless `--max-rate-age-days` is supplied.

No rates are built in. Missing, stale, future-dated, malformed, or not-yet-effective rates fail closed. A rate is stale when `as_of - accessed_on` is greater than its maximum age. `--allow-stale-rates` permits a deliberate stale-rate override but records it in warnings and component status.

## Prompt

```text
Use $estimate-du-units to decide yes, no, or conditional DU applicability with a rationale; build a versioned multi-document input; verify current rate components into a sourced rate profile; and return exact and rounded scenario totals as a planning estimate.
```

## Outputs

Both formats are projections of [`estimate-du-units.output.v1`](../estimate-du-units/references/output.v1.schema.json):

- `--format markdown` emits applicability, rationale, source and freshness details for every additive rate component, per-document calculations, aggregate totals per scenario, warnings, and the planning-only disclaimer.
- `--format json` emits the machine-readable contract with exact decimal strings and whole-unit `rounded` strings using half-up rounding.
- AI Units and Platform Units remain separate. Components of the same unit are added per page.
- Applicability `no` preserves page-volume context but sets `calculation_applied` to `false` and forces unit results to zero.
- Scenarios are alternatives. Documents are aggregated within a scenario; low, base, and high scenarios are never added together.

## Runnable Example

Run from the repository root:

```bash
python3 estimate-du-units/scripts/du_estimate.py \
  --input estimate-du-units/tests/fixtures/multi-document-input.v1.json \
  --rate-profile estimate-du-units/tests/fixtures/rate-profile.v1.json \
  --format markdown
```

The fixtures are synthetic and exist only to demonstrate the contracts and arithmetic. They are not current UiPath rates and must not be copied into a customer estimate.

## Migration

Commands that relied on omitted `--ai-rate` or `--platform-rate` now exit with code 2. This is intentional. The preferred fix is a structured input plus a sourced rate profile.

For temporary compatibility, preserve `--case` only with explicit verified rates:

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

Replace placeholders with actual verified values. Explicit CLI mode records the verification date but cannot retain a source URL or effective date, so it has lower provenance quality than a rate profile.

## Failure Recovery

| Failure | Recovery |
|---|---|
| `no rates supplied` | Add a v1 rate profile, or explicit rates plus `--verified-on` |
| `explicit rates require --verified-on` | Re-check the source and pass the actual access date |
| `stale rate component(s)` | Refresh the source and date; override only with documented risk acceptance |
| `accessed after` or `not effective` | Correct the profile chronology or estimate `as_of`; these errors cannot be overridden |
| Missing or unsupported contract fields | Validate against the linked v1 schema and migrate the file |
| Invalid decimal | Encode non-negative values as canonical strings such as `"1200"` or `"2.5"` |
| Missing applicability rationale | Decide `yes`, `no`, or `conditional` and state why |
| Rate profile used with `--case` | Move documents into `input.v1`; profiles are unavailable in legacy mode |

Do not recover by deleting source fields, changing dates to today without re-verification, or using `--allow-stale-rates` as a routine default.

## Safety

- Treat every estimate as planning guidance, not a quote or entitlement statement.
- Verify deployment, plan, project type, package/API path, add-ons, and unit type against current official sources.
- Do not infer a current rate from this documentation, examples, prior conversations, or model memory.
- Reject negative or non-finite values and keep AI Units separate from Platform Units.
- Include retries, duplicate processing, attachments, blanks, and other page multipliers in the input assumptions when applicable.
- Never claim that a source URL was checked unless `accessed_on` reflects a real verification event.

## Data Classification And Retention

- Classification: treat customer names, process details, transaction volumes, document types, and source URLs as customer confidential or internal business data unless the owner classifies them otherwise.
- Minimize input: use aggregate counts and document labels; do not include document contents, personal data, secrets, credentials, or unnecessary customer identifiers.
- Processing: the script performs local in-memory arithmetic and no network calls. Output goes to stdout and may be retained by terminal, CI, or Codex session logging.
- Retention: the skill creates no database, cache, or output file. Source JSON and captured output remain wherever the operator or calling system stores them and must be deleted according to the applicable customer and company retention policy.

## Known Limitations

- The calculator does not discover, fetch, or validate live UiPath rates; provenance is structurally validated, not independently authenticated.
- Only per-page `ai_unit` and `platform_unit` components are modeled. It does not model currencies, bundles, tiers, minimums, discounts, entitlements, or non-page meters.
- It does not convert between AI Units and Platform Units.
- Scenarios must be pre-annualized. Calendar effects, growth curves, retry rates, and confidence distributions must be represented in the supplied scenario values.
- Decimal output is exact for supplied values, but the business estimate remains only as accurate as applicability, volume, page, and rate assumptions.
- A stale override documents risk; it does not make an old rate current.

## Certification Status

Maintainer-verified for deterministic local planning use against the bundled contract and failure-path tests. Not certified by UiPath Licensing, Legal, Finance, or a customer procurement authority. The bundled fixtures are synthetic and uncertified for commercial use.

## Last Verified

2026-07-10.

## Validation

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s estimate-du-units/tests -p 'test_*.py'
python3 tools/validate_repo.py
```
