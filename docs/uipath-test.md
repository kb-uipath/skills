# uipath-test

## Purpose

UiPath Test Manager - manage test projects, cases, sets, executions; generate reports.

## When to use

UiPath Test Manager - manage test projects, cases, sets, executions; generate reports. For
Orchestrator->uipath-platform. For test automation->uipath-rpa.

## Required inputs

- Test Manager project, test case, test set, or execution target.
- Operation: create, list, update, run, inspect, or report.
- Related automation project or Orchestrator context.
- Reporting format or evidence needed.

## Prompt template

```text
Use $uipath-test to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-test to list failed executions for this test set, summarize failures by test case, and generate a concise report.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-test/SKILL.md`](../uipath-test/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-test/`](../uipath-test/) when present.
