# uipath-diagnostics

## Purpose

UiPath cross-platform diagnostics - failed or stuck Orchestrator jobs, faulted queue items, publish
errors, selector failures, healing agent issues, permission problems.

## When to use

UiPath cross-platform diagnostics - failed or stuck Orchestrator jobs, faulted queue items, publish
errors, selector failures, healing agent issues, permission problems. For .flow run
diagnosis->uipath-maestro-flow. For .bpmn run diagnosis->uipath-maestro-bpmn. For .xaml/.cs workflow
debug->uipath-rpa. For platform ops->uipath-platform.

## Required inputs

- Failure symptom or error message.
- Relevant job, process, queue item, trace, incident, package, or run ID.
- Environment, tenant, folder, and timeframe.
- What changed recently and what behavior is expected.

## Prompt template

```text
Use $uipath-diagnostics to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-diagnostics to investigate why this Orchestrator job failed yesterday. Use the job ID, queue item ID, logs, and trace evidence to identify the originating fault.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-diagnostics/SKILL.md`](../uipath-diagnostics/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-diagnostics/`](../uipath-diagnostics/) when present.
