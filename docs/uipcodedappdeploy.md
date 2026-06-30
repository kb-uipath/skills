# uipcodedappdeploy

## Purpose

Deploy UiPath coded app projects with the native UiPath CLI.

## When to use

Deploy UiPath coded app projects with the native UiPath CLI. Use when Codex needs to increment a
coded app package version, validate the project, build the app dist, pack it, publish it, and deploy
it to UiPath Automation Cloud alpha using `uip codedapp pack`, `uip codedapp publish`, and `uip
codedapp deploy`.

## Required inputs

- Coded app project path.
- Current and target package version.
- Target Automation Cloud environment.
- Build, pack, publish, and deploy requirements.

## Prompt template

```text
Use $uipcodedappdeploy to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipcodedappdeploy for this coded app project. Increment the package version, validate, build dist, pack, publish, and deploy with the native UiPath CLI.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipcodedappdeploy/SKILL.md`](../uipcodedappdeploy/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipcodedappdeploy/`](../uipcodedappdeploy/) when present.
