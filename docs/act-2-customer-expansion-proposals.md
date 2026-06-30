# act-2-customer-expansion-proposals

## Purpose

Create Act 2 customer expansion proposal cards from a customer-provided use case or automation idea
inventory.

## When to use

Create Act 2 customer expansion proposal cards from a customer-provided use case or automation idea
inventory. Use when Codex is asked to analyze an existing UiPath customer, agency, public-sector
entity, enterprise account, or department; identify strategic objectives from public sources; cross-
reference those objectives against an uploaded spreadsheet/CSV/table of automation ideas; prioritize
expansion-ready agentic use cases; estimate planning value; validate UiPath Automation Cloud
capability fit; and produce a concise .docx Word executive briefing as the final artifact.

## Required inputs

- Customer or agency name, vertical, and deployment context.
- Automation idea inventory as XLSX, CSV, table, or deck.
- Any scoring rules, value assumptions, and output format expectations.
- Permission to use public authoritative sources for strategy and budget evidence.

## Prompt template

```text
Use $act-2-customer-expansion-proposals to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $act-2-customer-expansion-proposals for Customer: USDA, Vertical: public sector, Deployment: Automation Cloud Public Sector, and this inventory workbook. Create executive proposal cards plus one prioritization table.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../act-2-customer-expansion-proposals/SKILL.md`](../act-2-customer-expansion-proposals/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../act-2-customer-expansion-proposals/`](../act-2-customer-expansion-proposals/) when present.
