# uipath-design

## Purpose

Always invoke for `sdd.md` / `pdd.md` files. UiPath Solution Design Document (SDD) authoring from
Process Design Documents (PDDs). Selects scope (single product or multi-project SDD scope:
RPA/Flow/Case/Agents/Apps/API Workflows), writes implementation-ready SDD.

## When to use

User mentions sdd.md / pdd.md / Process Design Document / Solution Design Document / SDD / PDD /
multi-project / Solution scope. Fires for 'design this automation', 'architect the solution',
'generate SDD', 'analyze this PDD', 'turn this PDD into code', 'design from this PDD'. Load BEFORE
authoring an SDD. For running `uip solution` commands or editing `.uipx`->uipath-solution.

## Required inputs

- PDD, SDD, process notes, or desired automation description.
- Target scope: RPA, Flow, Case, Agents, Apps, API Workflows, or multi-project solution.
- Business rules, systems, exceptions, and compliance constraints.
- Implementation output path and level of detail.

## Prompt template

```text
Use $uipath-design to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-design to turn this PDD into an implementation-ready SDD for a multi-project UiPath solution with Flow orchestration, RPA fulfillment, and Action Center approval.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-design/SKILL.md`](../uipath-design/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-design/`](../uipath-design/) when present.
