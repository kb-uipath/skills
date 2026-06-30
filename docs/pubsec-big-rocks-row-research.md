# pubsec-big-rocks-row-research

## Purpose

Research and synthesize evidence for one account row in the PubSec CS Portfolio Big Rocks
spreadsheet.

## When to use

Research and synthesize evidence for one account row in the PubSec CS Portfolio Big Rocks
spreadsheet. Use when Codex is asked to fill, review, validate, or provide organized content for a
single account/row/record in the PUBSEC Big Rocks workbook, especially columns for utilization,
cloud status, AI Units, Agent Units, Test/IXP/Agentic status, FY27 Big Rocks, value tracking,
churn/risk, and notes using SharePoint, Slack, OneNote, migration, TAC, Gov SFDC, Wingman/license,
and workbook tabs.

## Required inputs

- Workbook path or SharePoint location.
- Exact account row or customer name.
- Columns that need filling or validation.
- Allowed evidence systems such as SharePoint, Slack, OneNote, Salesforce, or local files.

## Prompt template

```text
Use $pubsec-big-rocks-row-research to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $pubsec-big-rocks-row-research for the Department of Example row in the PubSec Big Rocks workbook. Fill utilization, cloud status, AI Units, FY27 Big Rocks, risks, and notes with cited evidence.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../pubsec-big-rocks-row-research/SKILL.md`](../pubsec-big-rocks-row-research/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../pubsec-big-rocks-row-research/`](../pubsec-big-rocks-row-research/) when present.
