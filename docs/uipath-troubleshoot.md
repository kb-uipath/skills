# uipath-troubleshoot

## Purpose

UiPath troubleshooting, diagnostics, and root-cause investigations across any UiPath product,
feature, runtime, or artifact. Investigates errors, failures, faults, exceptions, regressions,
performance problems, unexpected behavior, and silent malfunctions - answers why something failed,
broke, stopped, hung, slowed down, returned wrong results, lost access, or stopped working after a
change. Walks the available evidence (logs, traces, incidents, status fields, configuration,
history) to identify the originating fault and explain what changed.

## When to use

User asks why something failed, broke, stopped, hung, was stuck, returns wrong results, or behaves
unexpectedly in any UiPath system. Triggers: 'why did X fail', 'find the cause', 'find why', 'what
changed', 'investigate', 'diagnose', 'debug this', 'triage', 'help me figure out', 'what's wrong',
'root cause', 'fix this error', 'inspect this trace / incident / log / job / instance', 'X worked
yesterday but now …'. Also fires on raw error messages, exception stacks, error codes, job / queue
IDs, or 'stuck / orphan / zombie' state descriptions.

## Required inputs

- Symptom, failure, regression, or unexpected behavior.
- Logs, traces, job IDs, incident IDs, queue IDs, error stacks, or screenshots.
- Environment, tenant, folder, timeframe, and recent changes.
- Whether the goal is root cause only or also a fix plan.

## Prompt template

```text
Use $uipath-troubleshoot to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-troubleshoot to find why this Flow started failing after yesterday's change. Use run history, traces, configuration, and recent edits to identify root cause.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-troubleshoot/SKILL.md`](../uipath-troubleshoot/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-troubleshoot/`](../uipath-troubleshoot/) when present.
