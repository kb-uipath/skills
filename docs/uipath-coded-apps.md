# uipath-coded-apps

## Purpose

Always invoke for `app.config.json` or `action-schema.json` files. UiPath Coded Web Apps & Coded
Action Apps via `uip codedapp` and `@uipath/uipath-typescript` SDK. Scaffold, build, debug, deploy.

## When to use

Always invoke for `app.config.json` or `action-schema.json` files. UiPath Coded Web Apps & Coded
Action Apps via `uip codedapp` and `@uipath/uipath-typescript` SDK. Scaffold, build, debug, deploy.
For .cs/XAML->uipath-rpa, Python->uipath-agents.

## Required inputs

- Coded app project path or desired scaffold.
- Whether it is a web app or action app.
- Action schema, app config, UI requirements, and deployment target.
- Validation, build, pack, publish, or deploy intent.

## Prompt template

```text
Use $uipath-coded-apps to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-coded-apps for this app.config.json project. Add the requested action form fields, build it, pack it, and prepare the deploy command.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-coded-apps/SKILL.md`](../uipath-coded-apps/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-coded-apps/`](../uipath-coded-apps/) when present.
