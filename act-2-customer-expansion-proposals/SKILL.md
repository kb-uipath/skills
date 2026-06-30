---
name: act-2-customer-expansion-proposals
description: Create Act 2 customer expansion proposal cards from a customer-provided use case or automation idea inventory. Use when Codex is asked to analyze an existing UiPath customer, agency, public-sector entity, enterprise account, or department; identify strategic objectives from public sources; cross-reference those objectives against an uploaded spreadsheet/CSV/table of automation ideas; prioritize expansion-ready agentic use cases; estimate planning value; validate UiPath Automation Cloud capability fit; and produce a concise .docx Word executive briefing as the final artifact.
---

# Act 2 Customer Expansion Proposals

## Overview

Use this skill to turn a customer automation inventory into an evidence-backed Word executive brief with Act 2 expansion recommendations. The skill forces the handoff boundaries that matter: public strategy evidence first, inventory profiling second, crosswalk and prioritization third, capability validation fourth, executive proposal cards last.

Read `references/methodology.md` before doing the analysis. Use `scripts/profile_inventory.py` when the user provides an `.xlsx`, `.csv`, or `.tsv` inventory file.

Always produce a Word `.docx` executive brief as the final deliverable. Do not stop to ask the user whether they want Markdown, chat output, or Word. Write a concise Markdown briefing only as the renderer source, then render and verify the `.docx`. Read `references/executive_docx.md` before drafting the deliverable.

## Required Inputs

Proceed with these inputs before analysis. Confirm known values in the response, but do not pause to ask for output format:

- Customer or organization name.
- Industry or public-sector vertical.
- UiPath deployment context, especially Automation Cloud, Automation Cloud Public Sector, Automation Suite, or unknown.
- Customer use case inventory path or uploaded table.
- Optional output path or filename. If unspecified, create a concise filename and write the final `.docx` to the current workspace's `outputs/` directory when available.

Output format is not a required input. Default to a Word `.docx` final artifact unless the user explicitly prohibits file output. If another field is missing and cannot be inferred safely, ask only for the missing field. If the inventory is absent, explain that the skill cannot produce inventory-backed recommendations without it.

## Workflow

1. **Confirm scope.**
   - Restate the confirmed organization, vertical, deployment context, inventory file, and that the final artifact will be a Word `.docx` executive brief.
   - Default to public authoritative sources plus the user-provided inventory. Do not use internal email, Slack, Teams, SharePoint, Drive, Salesforce, or customer-confidential sources unless the user explicitly expands scope.

2. **Profile the inventory.**
   - For spreadsheets, use the spreadsheet skill where workbook fidelity matters.
   - Run `scripts/profile_inventory.py <inventory-path>` to identify sheets, columns, status distributions, volume fields, and top volume rows.
   - If the active Python lacks `pandas` or Excel readers, use the Codex bundled Python runtime from `load_workspace_dependencies`.
   - Treat inventory rows as customer-provided operational signals, not audited facts.
   - Treat `Rejected`, `Cancelled`, `Archived`, `Duplicate`, and `Decommissioned` rows as weak evidence unless repeated by active rows.

3. **Build the public strategy ledger.**
   - Browse current public authoritative sources for strategy, budgets, annual plans, performance plans, public dashboards, audited reports, legislation, or official executive priorities.
   - Capture source IDs, title, publisher, date or fiscal year, URL, accessed date, and facts supported.
   - If source-backed strategy is thin, say so rather than filling gaps with generic sector themes.

4. **Crosswalk strategy to inventory.**
   - Group inventory rows into candidate agentic themes by agency, program, process description, systems, citizen-facing/shared-service flags, document/communication intensity, status, and volume.
   - Prioritize rows that appear in both the public strategic objectives and the inventory.
   - Keep the explicit related inventory rows with each proposed use case.

5. **Estimate planning value.**
   - Use the rules in `references/methodology.md`.
   - Prefer source/inventory volume over assumptions.
   - Convert weekly volume to annual volume with `weekly * 50` only when the workbook lacks an annual value, and label it as an estimate.
   - Use conservative minutes-saved ranges by use-case type and a visible loaded labor rate assumption.
   - Never call the result ROI, savings, or guaranteed value until the customer validates volume, handling time, salary/load rate, and implementation scope.

6. **Validate UiPath capability fit.**
   - Browse current `docs.uipath.com` for the requested deployment context before finalizing capability names.
   - Refer to capabilities, not SKU/contract entitlement claims.
   - Common capability families: Agent Builder, Maestro, Apps, Action Center, UI/API Automation, Document Understanding, IXP, Communications Mining, Test Manager, Test Cloud.
   - Label unclear deployment availability as "requires confirmation."

7. **Draft the executive deliverable source.**
   - Start with a concise source and assumption note.
   - Provide one combined executive table when the user wants prioritization.
   - Provide proposal cards when the user asks for executive proposal card format.
   - Keep facts, estimates, assumptions, and caveats visibly separated.
   - Do not stop after producing Markdown or chat text. Markdown is only the intermediate source for the Word brief.

8. **Package as the required Word executive brief.**
   - First write a concise Markdown briefing version, not a raw research dump.
   - Read and follow `references/executive_docx.md`.
   - Run `scripts/render_executive_docx.py <brief.md> <brief.docx> --portrait` to create the Word file.
   - Use the bundled Python runtime from `load_workspace_dependencies` if the active Python lacks `python-docx`.
   - Verify the `.docx` opens structurally by reading it back with `python-docx` and checking for portrait orientation, a title, at least one table when prioritization is requested, and the expected number of proposal-card headings.
   - If `.docx` rendering fails, fix the renderer or environment and retry. Do not treat Markdown as the final output unless file creation is explicitly impossible in the current environment; in that case, report the blocker plainly.

## Output Standards

- Lead with the highest-value and highest-confidence use cases.
- Include specific inventory row names under each recommendation.
- Include strategic objective alignment and budget/program area where source-backed.
- Include a confidence rating and the reason for any downgrade.
- Call out dirty data plainly: missing benefit fields, stale statuses, suspect volumes, or weak strategic evidence.
- For safety, child welfare, public safety, legal, healthcare, benefits eligibility, and compliance workflows, propose human-in-the-loop assistance unless the source evidence and deployment governance justify more.
- For the required `.docx` output, be concise and executive-readable: lead with the decision table, limit proposal cards to the strongest recommendations unless the user asks for exhaustive coverage, move source details to an appendix, and avoid dense research prose.
- Final chat responses should link to the generated `.docx`, mention any verification performed, and keep narrative summary brief.

## Bundled Resources

- `references/methodology.md`: scoring, value-estimation, status treatment, and executive card rules.
- `references/executive_docx.md`: concise Word briefing structure, style rules, and packaging checks.
- `scripts/profile_inventory.py`: inventory profiling utility for `.xlsx`, `.csv`, and `.tsv` inputs.
- `scripts/render_executive_docx.py`: deterministic Markdown-to-`.docx` renderer for polished executive briefing files.
