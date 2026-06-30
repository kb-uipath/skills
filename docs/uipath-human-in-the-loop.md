# uipath-human-in-the-loop

## Purpose

UiPath Human-in-the-Loop / HITL node authoring - building approval gates, escalations, write-back
validation, and data enrichment checkpoints in Flow, Maestro, or Coded Agents. NOT for managing,
reassigning, or monitoring tasks at runtime (use uipath-tasks for that).

## When to use

UiPath Human-in-the-Loop / HITL node authoring - building approval gates, escalations, write-back
validation, and data enrichment checkpoints in Flow, Maestro, or Coded Agents. NOT for managing,
reassigning, or monitoring tasks at runtime (use uipath-tasks for that).

## Required inputs

- Flow, Maestro, or coded-agent project path.
- Approval, validation, escalation, or enrichment checkpoint requirements.
- Task fields, assignees, outcomes, and write-back behavior.
- Business context or SDD when available.

## Prompt template

```text
Use $uipath-human-in-the-loop to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-human-in-the-loop to add an approval gate to this Flow for invoices over $25,000, with approve/reject outcomes and write-back to the case record.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-human-in-the-loop/SKILL.md`](../uipath-human-in-the-loop/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-human-in-the-loop/`](../uipath-human-in-the-loop/) when present.
