# uipath-ixp

## Purpose

UiPath IXP (Document Understanding) - review IXP predictions with Claude, confirm valid fields,
improve prompts, publish models.

## When to use

UiPath IXP (Document Understanding) - review IXP predictions with Claude, confirm valid fields,
improve prompts, publish models.

## Required inputs

- IXP project name or existing project context.
- Documents, taxonomy, fields, predictions, prompts, or model version target.
- Action: review predictions, label, tune prompts, publish model version, or upload documents.
- Any quality metric or validation rule to apply.

## Prompt template

```text
Use $uipath-ixp to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-ixp to review the latest predictions for this IXP project, identify weak fields, suggest prompt improvements, and publish a model version if quality is acceptable.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-ixp/SKILL.md`](../uipath-ixp/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-ixp/`](../uipath-ixp/) when present.
