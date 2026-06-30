# uipath-feedback

## Purpose

UiPath bug reports and improvement suggestions via `uip feedback send`. Use for 'report issue',
'send feedback', 'file a bug', or the /uipath-feedback command.

## When to use

User says 'this is broken', 'this isn't working', 'report a bug', 'send feedback', 'something is
wrong', 'file an issue', 'this crashed', 'wrong result' about a UiPath product, CLI, or skill. Also
fires on the /uipath-feedback slash command.

## Required inputs

- Bug, crash, bad result, or improvement request.
- Minimal reproduction steps and expected versus actual behavior.
- Sanitized logs, errors, screenshots, or project snippets.
- Confirmation before sending feedback.

## Prompt template

```text
Use $uipath-feedback to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-feedback to file a sanitized bug report for this CLI error. Include reproduction steps and environment, strip secrets and customer data, and confirm before sending.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-feedback/SKILL.md`](../uipath-feedback/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-feedback/`](../uipath-feedback/) when present.
