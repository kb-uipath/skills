# uipath-api-workflow

## Purpose

UiPath API Workflow assistant - author, run, package, publish JSON workflows executed by `uip api-
workflow run`. Covers logical/hierarchical structure (Sequence, Assign, JavaScript, If with
#Wrapper/#Then/#Else, ForEach, DoWhile, Break, TryCatch, Wait, Response - including nested patterns)
AND HTTP / Integration Service connector activities (Gmail, Outlook, GitHub, Slack, etc.) authored
via `uip api-workflow registry resolve` + `stub`. Triggers on prompts about UiPath API workflows,
project type \"Api\", JSON workflow files containing `document.dsl`/`do[]`, any of those activity
types, or fetching data from a public/vendor API. Uses `uip api-workflow run` for local execution
and `uip solution pack`/`publish` for deployment.

## When to use

UiPath API Workflow assistant - author, run, package, publish JSON workflows executed by `uip api-
workflow run`. Covers logical/hierarchical structure (Sequence, Assign, JavaScript, If with
#Wrapper/#Then/#Else, ForEach, DoWhile, Break, TryCatch, Wait, Response - including nested patterns)
AND HTTP / Integration Service connector activities (Gmail, Outlook, GitHub, Slack, etc.) authored
via `uip api-workflow registry resolve` + `stub`. Triggers on prompts about UiPath API workflows,
project type \"Api\", JSON workflow files containing `document.dsl`/`do[]`, any of those activity
types, or fetching data from a public/vendor API. Uses `uip api-workflow run` for local execution
and `uip solution pack`/`publish` for deployment. For .flow Maestro->uipath-maestro-flow. For
.xaml/coded RPA->uipath-rpa. For coded agents->uipath-agents. For Coded Apps->uipath-coded-apps.

## Required inputs

- Workflow goal and API or connector endpoints.
- Existing JSON workflow path or request to create one.
- Inputs, outputs, error handling, and test data.
- Packaging or publishing requirements.

## Prompt template

```text
Use $uipath-api-workflow to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-api-workflow to create a JSON API workflow that receives a customer ID, calls the CRM connector, branches on account status, and returns a normalized response.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-api-workflow/SKILL.md`](../uipath-api-workflow/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-api-workflow/`](../uipath-api-workflow/) when present.
