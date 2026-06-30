# uipath-review

## Purpose

UiPath read-only reviewer - audit structure, quality, best practices for RPA (.xaml/.cs), agents
(.py/agent.json), flows (.flow), BPMN (.bpmn), coded apps, solutions (.uipx). Does NOT edit files.

## When to use

UiPath read-only reviewer - audit structure, quality, best practices for RPA (.xaml/.cs), agents
(.py/agent.json), flows (.flow), BPMN (.bpmn), coded apps, solutions (.uipx). Does NOT edit files.
For building/editing->domain skills.

## Required inputs

- Project or solution path.
- Artifact type: RPA, agent, flow, BPMN, coded app, or solution.
- Review depth or areas of concern.
- Whether CLI review output is available.

## Prompt template

```text
Use $uipath-review to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-review to audit this UiPath solution read-only. Prioritize structural, reliability, security, and deployment issues with file references and rule IDs where available.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-review/SKILL.md`](../uipath-review/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-review/`](../uipath-review/) when present.
