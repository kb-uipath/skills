# pubsec-big-rocks-row-research

Research one account row in the PubSec CS Portfolio Big Rocks workbook, separate current fill-eligible evidence from discovery leads, preview proposed updates, and optionally write a verified local copy without modifying the source.

## Status

- Certification status: Not externally certified. The local deterministic paths are covered by automated hardening tests and repository validation.
- Last verified: 2026-07-10.
- External writes: None. The CLI reads local files, writes JSON/Markdown to stdout, and writes an `.xlsx` only when an explicit new `--write-copy` path is supplied.

## Runtime And Dependencies

- Python 3.10 or newer.
- `openpyxl>=3.1,<4` from `requirements-dev.txt`.
- Standard-library modules only beyond `openpyxl`.
- Local `.xlsx` workbooks. Macros, `.xls`, and `.xlsm` are not supported.

Install the runtime dependency in an isolated environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install 'openpyxl>=3.1,<4'
```

## Inputs

### Versioned Source Manifest `@1`

`--manifest` is required. Relative source paths resolve from the manifest directory. There are no default source paths.

```json
{
  "contract_version": "pubsec-big-rocks-row-research/source-manifest@1",
  "data_classification": "UiPath Confidential",
  "retention_until": "2026-08-10",
  "sources": [
    {
      "id": "tac-account-tracking",
      "kind": "xlsx",
      "path": "./TAC_Account_Tracking.xlsx",
      "required": true,
      "source_updated_at": "2026-07-08T14:30:00Z",
      "freshness_basis": "sharepoint_modified_at"
    }
  ]
}
```

Required top-level fields are `contract_version`, `data_classification`, `retention_until`, and `sources`. Source entries require `id`, `kind: "xlsx"`, and `path`; `required` defaults to `true`. A `source_updated_at` value requires one of these upstream bases: `sharepoint_modified_at`, `sfdc_last_modified_at`, `slack_message_timestamp`, `teams_message_timestamp`, `onenote_modified_at`, `workbook_report_date`, or `source_export_date`.

Required source files must exist. Missing optional sources are reported. Expired retention dates, unknown fields, duplicate IDs/paths, unsupported versions, and invalid freshness metadata return nonzero status.

### Versioned Proposed Updates `@1`

`--proposed-updates` activates read-only preview. Each direct update requires an exact target, `High` or `Medium` confidence, and at least one evidence ID.

```json
{
  "contract_version": "pubsec-big-rocks-row-research/proposed-updates@1",
  "target": {
    "account": "Exact Account Name",
    "row": 42
  },
  "updates": [
    {
      "header": "Cloud Y/N",
      "value": "Y",
      "confidence": "High",
      "evidence": ["tac-account-tracking:Accounts:18"],
      "reason": "Current platform is explicitly Automation Cloud."
    }
  ]
}
```

Preview requires every cited evidence ID to appear in `evidence.fill_eligible_current` from the same run. It blocks stale/discovery/unknown evidence IDs, unknown headers, duplicate updates, invalid dropdown values, formulas, substantive existing values, and target mismatches. A blocked preview is printed with exit status `3`; no workbook is written.

## Prompt

```text
Use $pubsec-big-rocks-row-research for the exact account in this local Big Rocks workbook. Use the supplied source-manifest@1 file, keep stale evidence in discovery leads only, and return output@1 JSON. Preview the supplied proposed-updates@1 file, but do not write a copy unless I explicitly provide a new local destination.
```

## Outputs

### Versioned Output `@1`

JSON output uses `pubsec-big-rocks-row-research/output@1`.

- `target_row`: exact account resolution, detected header row/columns, current values, blank targets, and missing target headers.
- `evidence.fill_eligible_current`: exact-account evidence with a trusted effective date at or after the cutoff.
- `evidence.discovery_leads`: non-exact current candidates plus stale/undated candidates only when `--include-stale` is set.
- `evidence.excluded`: stale/undated evidence omitted from discovery output.
- `recommendation_leads`: generated only from fill-eligible current evidence.
- `proposed_update_preview`: per-cell evidence eligibility, formula, existing-value, and dropdown checks.
- `write_copy`: changed cells and post-save verification checks.

Structured failures use `pubsec-big-rocks-row-research/error@1` on stderr and return nonzero status. Ambiguous account errors include candidate rows but never auto-select one.

## Runnable Example

From the repository root, after creating the manifest above with paths valid on the local machine:

```bash
python3 pubsec-big-rocks-row-research/scripts/research_row_sources.py \
  --workbook "/absolute/path/PUBSEC-CS-Portfolio-Big-Rocks.xlsx" \
  --manifest "/absolute/path/source-manifest.json" \
  --account "Exact Account Name" \
  --as-of-date 2026-07-10 \
  --months 3 \
  --include-stale \
  --format json
```

Preview a versioned proposal without writing:

```bash
python3 pubsec-big-rocks-row-research/scripts/research_row_sources.py \
  --workbook "/absolute/path/PUBSEC-CS-Portfolio-Big-Rocks.xlsx" \
  --manifest "/absolute/path/source-manifest.json" \
  --row 42 \
  --proposed-updates "/absolute/path/proposed-updates.json" \
  --format markdown
```

After reviewing a valid preview, write a new verified local copy:

```bash
python3 pubsec-big-rocks-row-research/scripts/research_row_sources.py \
  --workbook "/absolute/path/PUBSEC-CS-Portfolio-Big-Rocks.xlsx" \
  --manifest "/absolute/path/source-manifest.json" \
  --row 42 \
  --proposed-updates "/absolute/path/proposed-updates.json" \
  --write-copy "/absolute/path/PUBSEC-CS-Portfolio-Big-Rocks.review-copy.xlsx"
```

The destination must not exist and must not resolve to the source. After save, the CLI verifies source bytes are unchanged, formulas and non-target values are preserved, data validations remain intact, dropdown values are valid, changed values match, and changed cells use red font. A failed verification removes the copy.

## Failure Recovery

| Failure | Recovery |
| --- | --- |
| `manifest_required` or `legacy_source_flags_removed` | Move every intended source into a `source-manifest@1` file and pass `--manifest`. |
| `unsupported_manifest_version` or `invalid_contract` | Use the exact `@1` schema and remove unknown fields. Do not guess forward-version behavior. |
| `required_sources_missing` | Restore the reviewed source file, or mark it optional only after accepting the coverage gap. |
| `retention_expired` | Delete expired local data or obtain authorization and create a manifest with a new retention date. |
| `ambiguous_account` | Review returned candidates and rerun with the intended `--row` plus exact `--account`. |
| `main_schema_not_found` or `ambiguous_main_schema` | Correct the workbook header aliases or duplicate columns; do not use fixed coordinates as a workaround. |
| Exit status `3` with invalid preview | Correct target, evidence, dropdown, formula, or existing-value conflicts; rerun preview before writing. |
| `in_place_write_refused` or `output_exists` | Choose a new `.xlsx` destination path. |
| `copy_verification_failed` | Treat the removed copy as unusable. Inspect unsupported workbook features and use a workbook-native tool if needed. |

## Data Classification And Retention

- Treat the workbook, source files, stdout, previews, and local copies at the manifest's declared classification; Big Rocks account evidence should normally be handled as UiPath Confidential unless the data owner specifies a stricter class.
- Store inputs and outputs only in authorized local locations. Do not put credentials, tokens, or secrets in manifests or proposed-update files.
- `retention_until` is mandatory and enforced against the run date. The CLI does not delete files automatically; the operator remains responsible for deleting manifests, source exports, previews, logs, and copies by that date.
- `--include-stale` changes discovery visibility only. It does not make stale evidence fill-eligible or extend retention.
- The CLI performs no SharePoint, Slack, Teams, OneNote, Salesforce, email, or other external writes.

## Safety

- Never use a fuzzy account candidate as the target or as fill-eligible evidence.
- Never use stale, undated, or local-file-mtime-only evidence for a cell value.
- Never infer utilization from support, engagement, entitlement, ARR, or account tier.
- Never overwrite a formula, substantive existing value, source workbook, or existing destination file.
- Treat invalid preview status, missing required sources, expired retention, schema ambiguity, and failed copy verification as stop conditions.
- Keep all customer evidence within its authorized classification and retention boundary.

## Known Limitations

- Only `.xlsx` is supported. VBA, legacy Excel formats, password-protected files, and macros are outside the contract.
- Deterministic scanning and copy verification are capped at 20,000 rows and 500 columns per worksheet.
- Header detection recognizes the aliases bundled in the script. Unknown naming conventions fail or appear as missing target headers and require an explicit code update.
- Manifest freshness metadata is an operator assertion. Row-level dates take precedence, but the CLI cannot independently verify upstream SharePoint, SFDC, Slack, Teams, or OneNote timestamps.
- Local file modification time is reported only as diagnostics and never proves evidence freshness.
- The verified-copy gate checks values, formulas, data validations, dropdowns, and red font. It does not certify charts, slicers, pivot caches, external links, conditional formatting behavior, or every vendor-specific Excel extension.
- Recommendation leads are search prompts, not approved cell values. Human review remains mandatory.

## Validation

```bash
python3 -m unittest discover -s pubsec-big-rocks-row-research/tests -p 'test_*.py' -v
python3 tools/validate_repo.py
```
