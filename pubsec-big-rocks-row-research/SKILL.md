---
name: pubsec-big-rocks-row-research
description: Research and synthesize evidence for one account row in the PubSec CS Portfolio Big Rocks spreadsheet. Use when Codex is asked to fill, review, validate, or provide organized content for a single account/row/record in the PUBSEC Big Rocks workbook, especially columns for utilization, cloud status, AI Units, Agent Units, Test/IXP/Agentic status, FY27 Big Rocks, value tracking, churn/risk, and notes using SharePoint, Slack, OneNote, migration, TAC, Gov SFDC, Wingman/license, and workbook tabs.
---

# PubSec Big Rocks Row Research

## Objective

Produce evidence-backed fill recommendations for one account row. The output must separate facts from inference, cite the source path/tool/search query used, and avoid filling cells where the evidence is too weak. Use only evidence updated within the past 3 months, measured from the current date at runtime.

## Required Workflow

1. Identify the target row.
   - Use the account name and row number when provided.
   - If the user provides only a SharePoint workbook link, fetch or open the workbook and confirm the sheet, header row, account name, and existing values.
   - Treat bullet-only cells like `• \n• \n•` as blank placeholders.
   - Calculate the recency cutoff date immediately. For example, if today is May 1, 2026, the cutoff is February 1, 2026. Do not use evidence older than that cutoff for cell values.

2. Run the structured-source pass first.
   - Call `load_workspace_dependencies` if needed.
   - Run `scripts/research_row_sources.py` with the workbook path plus either `--row` or `--account`.
   - Use the script output as a candidate evidence map for workbook tabs, migration master, TAC account tracking, PubSec Gov SFDC, Wingman Active Organizations, and org license sheets.
   - Treat local file modified dates as a weak freshness signal only. Prefer SharePoint/SFDC/Slack/Teams document or message timestamps when available.

   ```bash
   /path/to/python3 scripts/research_row_sources.py \
     --workbook "/path/to/PUBSEC CS Portfolio_Big Rocks_MAY2026 - Copy.xlsx" \
     --row 183 \
     --months 3 \
     --format markdown
   ```

3. Resolve the account-specific workspace before broad searching.
   - Find the TAM/Enterprise Success account SharePoint site first. Common patterns include `TAM-<AccountName>`, `ES-<AccountName>`, or links from TAC Account Tracking / migration master. Browse that site before generic SharePoint search.
   - Find the account Slack channel first. Common patterns include `#account-<name/acronym>`, but use Slack channel search rather than guessing. Read the channel or search within it before workspace-wide Slack search.
   - Find relevant Teams channels/chats if the Teams connector is available. Search exact account name, acronym, TAM, CSM, AE, and migration/product terms.
   - Find SFDC account-specific evidence. If no SFDC connector is available, use SFDC exports in SharePoint, TAC Account Tracking, PubSec Gov SFDC, account plans, opportunity/renewal docs, and account-specific SharePoint files that cite SFDC.
   - Discard account workspace sources whose last modified/message/activity timestamp is older than the cutoff. Undated sources can help locate newer sources but cannot support cell values.

4. Search unstructured/internal sources.
   - Slack: search the exact account name, common acronym, TAM/CSM, and product terms (`ACPS`, `Automation Suite`, `DU`, `Document Understanding`, `AI Units`, `Agentic`, `Autopilot`, `Test Suite`, `IXP`, `churn`, `renewal`) with an `after:` date or timestamp at/after the cutoff. If Slack returns `invalid_auth_token` or similar, state that no Slack evidence was used.
   - SharePoint: search exact account name and acronym with `recency_days` or inspect returned `updated_at` metadata. Fetch relevant account plans, handoff docs, CSP/CVR/EBR decks, TAC docs, migration docs, proposals, and files inside the account-specific TAM/ES site only when updated within the cutoff window.
   - OneNote: inspect account-specific OneNote sections/backups first, then local OneNote backups under `/Users/keith.born/Library/Containers/com.microsoft.onenote.mac/Data/Library/Application Support/Microsoft User Data/OneNote/15.0/Backup/Keith @ UiPath` when available. Use only sections/pages/backups modified within the cutoff window.
   - Teams: search account-specific Teams channels/chats and nearby messages within the cutoff window if the connector is available. If not available, state that Teams evidence was not used.
   - Existing workbook tabs: check churn forecast, high-risk tabs, renewal tabs, and any notes/evidence column already present only if the workbook or tab source is updated within the cutoff window.

5. Synthesize field recommendations.
   - Read `references/evidence-and-field-rules.md` before making recommendations.
   - Use the workbook's exact dropdown values.
   - Do not overwrite existing substantive values. If an existing value needs augmentation, recommend red text for the notes column to the right of column V/W, depending on the workbook layout.
   - Leave a field blank when the only support is stale evidence, undated evidence, entitlement, generic interest, or a broad account profile.

6. Return a row-ready result.
   - Include account, row, current blanks, source coverage, recommended cell updates, notes/evidence additions, and unresolved gaps.
   - Mark each recommendation as `High`, `Medium`, or `Low` confidence.
   - Use `Low` confidence only for notes or follow-up, not for direct cell values.

## Output Shape

Use this structure unless the user asked for workbook edits:

```markdown
**Account**
Row: ...
Account: ...

**Recommended Cell Updates**
| Cell/Header | Value | Confidence | Evidence |
| --- | --- | --- | --- |

**Notes Column Additions**
- ...

**Do Not Fill**
- Header: reason evidence is insufficient.

**Sources Checked**
- ...

**Excluded As Stale Or Undated**
- ...
```

## Editing Discipline

If the user asks to edit the workbook:
- Use workbook-aware tooling such as `openpyxl`; never flatten the workbook to CSV.
- Back up the workbook before writing.
- Format all newly entered or appended content in red text.
- Preserve formulas, validations, sheets, and existing substantive cell values.
- Verify exact changed cells, dropdown validity, and red font after save.

## Bundled Resources

- `scripts/research_row_sources.py`: deterministic local structured-source lookup for one workbook row/account.
- `references/evidence-and-field-rules.md`: field-specific evidence standards, source priority, and anti-mistake rules.
