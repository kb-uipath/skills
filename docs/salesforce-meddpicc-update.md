# salesforce-meddpicc-update

## Purpose

Update MEDDPICC qualification fields and Next Steps on UiPath Salesforce Opportunities through the
UiPath Integration Service Salesforce connector.

## When to use

Update MEDDPICC qualification fields and Next Steps on UiPath Salesforce Opportunities through the
UiPath Integration Service Salesforce connector. Use when the user provides or references a
Salesforce Opportunity URL or ID and asks to update MEDDPICC, qualification, Metrics, Economic
Buyer, Decision Criteria, Decision Process, Paper Process, Identified Pain, Champion, Competition,
Compelling Event, or Next Steps. Requires read-before-write, schema describe validation, explicit
user confirmation, append-with-date behavior for narrative fields, read-after-write verification,
prompt-injection guardrail, fuzzy near-duplicate detection, force-duplicate override, and privacy-
safe telemetry logging.

## Required inputs

- Salesforce Opportunity URL or ID.
- Exact MEDDPICC or Next Steps fields to update.
- Source text or notes to append.
- Explicit confirmation before write operations.

## Prompt template

```text
Use $salesforce-meddpicc-update to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $salesforce-meddpicc-update for this Opportunity URL. Update Metrics, Identified Pain, Champion, and Next Steps from these notes, confirm the proposed writeback first, then verify after saving.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../salesforce-meddpicc-update/SKILL.md`](../salesforce-meddpicc-update/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../salesforce-meddpicc-update/`](../salesforce-meddpicc-update/) when present.
