# uipath-planner

## Purpose

UiPath task planner - reads SDDs from uipath-design or elicits non-PDD requests, derives multi-skill
task lists, emits live TaskCreate calls. Detects project type (.cs, .xaml, .flow, .bpmn, .py).

## When to use

User makes a non-trivial UiPath request that spans SEPARATE buildable projects - e.g. 'build a
UiPath solution for X', 'set up a process from scratch', a Flow that orchestrates standalone RPA
processes or agents - OR provides an SDD path. Skip when the request targets a SINGLE project, even
a Flow/Agent/RPA project with inline HITL, script, or connector nodes wrapped in its own solution
(e.g. a Flow with an inline approval step is one uipath-maestro-flow task, not a plan) - invoke that
specialist directly.

## Required inputs

- SDD path or non-trivial multi-project UiPath request.
- Known project types, artifacts, and desired delivery phases.
- Constraints, dependencies, and acceptance criteria.
- Which specialist skills may be used downstream.

## Prompt template

```text
Use $uipath-planner to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-planner on this SDD and produce the multi-skill execution plan for Flow orchestration, RPA fulfillment, Action Center tasks, and solution packaging.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-planner/SKILL.md`](../uipath-planner/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-planner/`](../uipath-planner/) when present.
