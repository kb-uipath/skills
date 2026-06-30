# uipath-agentic-expansion-planner

## Purpose

analyze detailed customer automation or use-case inventories to produce evidence-backed uipath act 2
expansion plans, agentic automation portfolios, top 5 high-impact recommendations, top 3 low-
friction poc candidates, and a final verified executive .docx Word brief every run.

## When to use

analyze detailed customer automation or use-case inventories to produce evidence-backed uipath act 2
expansion plans, agentic automation portfolios, top 5 high-impact recommendations, top 3 low-
friction poc candidates, and a final verified executive .docx Word brief every run. use when the
user provides or references a customer inventory spreadsheet, asks for agentic expansion ideas, asks
to prioritize uipath opportunities, or needs a customer-ready proposal grounded in inventory data,
public strategy evidence, deployment-aware validation, and Word-ready executive packaging.

## Required inputs

- Customer name, industry, and deployment context.
- Detailed automation inventory file or table.
- Evidence sources and public-source requirements.
- Output expectations for top recommendations, POCs, and Word brief.

## Prompt template

```text
Use $uipath-agentic-expansion-planner to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-agentic-expansion-planner on this customer inventory. Produce the top 5 agentic expansion recommendations, top 3 low-friction POCs, and a verified executive Word brief.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-agentic-expansion-planner/SKILL.md`](../uipath-agentic-expansion-planner/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-agentic-expansion-planner/`](../uipath-agentic-expansion-planner/) when present.
