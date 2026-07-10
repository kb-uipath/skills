---
name: pubsec-big-rocks-row-research
description: Research and synthesize evidence for one account row in the PubSec CS Portfolio Big Rocks spreadsheet. Use when Codex is asked to fill, review, validate, or provide organized content for a single account/row/record in the PUBSEC Big Rocks workbook, especially columns for utilization, cloud status, AI Units, Agent Units, Test/IXP/Agentic status, FY27 Big Rocks, value tracking, churn/risk, and notes using SharePoint, Slack, OneNote, migration, TAC, Gov SFDC, Wingman/license, and workbook tabs.
---

# PubSec Big Rocks Row Research

## Objective

Produce evidence-backed recommendations for one account row without mutating the source workbook. Separate fill-eligible current evidence from discovery leads, cite source paths/tools/searches, and leave cells unchanged when evidence or workbook safety checks are insufficient. Use only evidence updated within the past 3 months, measured from the current date at runtime.

## Required Workflow

1. Establish the local input contract.
   - Use only `.xlsx` files already available within the user's authorization boundary.
   - Create a `pubsec-big-rocks-row-research/source-manifest@1` JSON manifest with explicit source paths, classification, retention date, and upstream freshness metadata.
   - Do not use implicit machine-local sources. The legacy `--source` and `--sources-only` flags fail closed; migrate those paths into `--manifest`.
   - Calculate the recency cutoff immediately. Evidence before the cutoff cannot support a cell value.

2. Resolve the target exactly.
   - Run `scripts/research_row_sources.py` with the workbook, manifest, and either `--row` or `--account`.
   - The script dynamically detects the main header row, account column, and target columns from normalized aliases.
   - Account lookup requires one exact normalized match. Never select a fuzzy candidate. If candidates are ambiguous, review the returned rows and rerun with `--row` plus the exact account.
   - Treat bullet-only and dash-only cells as placeholders; all other existing values and formulas are protected.

   ```bash
   python3 scripts/research_row_sources.py \
     --workbook "/absolute/path/PUBSEC-CS-Portfolio-Big-Rocks.xlsx" \
     --manifest "/absolute/path/source-manifest.json" \
     --account "Exact Account Name" \
     --months 3 \
     --format markdown
   ```

3. Use evidence buckets correctly.
   - `evidence.fill_eligible_current` contains exact-account records with a trusted date at or after the cutoff.
   - `evidence.discovery_leads` contains non-exact current candidates and, only with `--include-stale`, stale or undated candidates.
   - `evidence.excluded` contains stale or undated candidates omitted from discovery output.
   - `recommendation_leads` is derived only from `fill_eligible_current`; stale evidence never enters it.
   - Local file modification time is diagnostic only and never establishes fill eligibility.

4. Resolve account-specific workspace evidence before broad searching.
   - Find the TAM/Enterprise Success SharePoint site, account Slack channel, relevant Teams channel/chat, and SFDC account context before broad searches.
   - Use account-specific SharePoint, Slack, Teams, OneNote, or SFDC timestamps at or after the cutoff.
   - If a connector is unavailable, state that limitation. Do not silently substitute a weaker source.
   - Do not perform an external write as part of this skill.

5. Synthesize field recommendations.
   - Read `references/evidence-and-field-rules.md` first.
   - Use exact workbook dropdown values.
   - Never infer utilization from support tier, support level, ARR, entitlement, or engagement.
   - Do not overwrite formulas or substantive existing values.
   - Use `Low` confidence only for notes or follow-up, never for a proposed direct cell value.

6. Preview and write only a verified local copy when explicitly requested.
   - Put proposed changes in a `pubsec-big-rocks-row-research/proposed-updates@1` JSON file.
   - Every proposed update must cite evidence IDs present in `evidence.fill_eligible_current` from the same run. Discovery-lead or unknown IDs block the preview.
   - Run with `--proposed-updates` first. An invalid preview returns nonzero status and does not write.
   - Add `--write-copy /new/local/path.xlsx` only after reviewing a valid preview.
   - The destination must be new and different from the source. The script refuses in-place and overwrite operations.
   - A successful copy verifies dropdown values, unchanged formulas, unchanged non-target values, preserved data validations, exact changed values, and red font after save. A failed verification removes the output copy.

## Output Contract

The JSON root is `pubsec-big-rocks-row-research/output@1` and includes:

- `target_row`: resolved account, dynamic schema, current values, and blank targets.
- `evidence.fill_eligible_current`: current exact-account evidence allowed into synthesis.
- `evidence.discovery_leads`: non-fill candidates for locating better evidence.
- `evidence.excluded`: records blocked by freshness or account rules.
- `recommendation_leads`: investigation prompts generated only from fill-eligible evidence.
- `proposed_update_preview`: per-cell safety checks, when supplied.
- `write_copy`: post-save verification results, when requested and successful.

## Row-Ready Response

```markdown
**Account**
Row: ...
Account: ...

**Recommended Cell Updates**
| Cell/Header | Value | Confidence | Evidence ID |
| --- | --- | --- | --- |

**Notes Column Additions**
- ...

**Do Not Fill**
- Header: reason evidence is insufficient.

**Sources Checked**
- ...

**Discovery Leads / Excluded Evidence**
- ...
```

## Bundled Resources

- `scripts/research_row_sources.py`: deterministic manifest-driven research, preview, and verified copy CLI.
- `references/evidence-and-field-rules.md`: field evidence standards, source priority, dropdown values, and anti-inference rules.
- `tests/fixtures/`: versioned source-manifest and proposed-update examples used by the test suite.
