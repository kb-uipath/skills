# uipath-maestro-flow

## Purpose

TRIGGER for `.flow` files, UiPath Flow / Maestro Flow build or edit requests, adding IxP/document-
extraction nodes to a flow, or asking what IxP / document-extraction models are available in
Maestro. UiPath Maestro Flow (.flow) - build, edit, run, debug, fix, evaluate. Create, connect
nodes; connector, approval, script, subflow, ixp; list IxP / document-extraction models for a flow
through `uip maestro flow registry search \"uipath.ixp\"`; triggers, schedules; validate. Upload,
publish, manage runs, instances. Diagnose errors, incidents, traces. Design eval sets, evaluators,
run Studio Web evals via `uip maestro flow eval`. `uip maestro flow` CLI. DO NOT TRIGGER for raw IxP
project labelling/prediction review/prompt tuning outside Flow->uipath-ixp; C#/XAML->uipath-rpa;
standalone agents->uipath-agents.

## When to use

TRIGGER for `.flow` files, UiPath Flow / Maestro Flow build or edit requests, adding IxP/document-
extraction nodes to a flow, or asking what IxP / document-extraction models are available in
Maestro. UiPath Maestro Flow (.flow) - build, edit, run, debug, fix, evaluate. Create, connect
nodes; connector, approval, script, subflow, ixp; list IxP / document-extraction models for a flow
through `uip maestro flow registry search \"uipath.ixp\"`; triggers, schedules; validate. Upload,
publish, manage runs, instances. Diagnose errors, incidents, traces. Design eval sets, evaluators,
run Studio Web evals via `uip maestro flow eval`. `uip maestro flow` CLI. DO NOT TRIGGER for raw IxP
project labelling/prediction review/prompt tuning outside Flow->uipath-ixp; C#/XAML->uipath-rpa;
standalone agents->uipath-agents.

## Required inputs

- .flow file path or new flow objective.
- Nodes, connectors, approvals, scripts, subflows, IXP models, triggers, or schedules.
- Run, debug, publish, or eval requirements.
- Tenant context when registry or live execution is required.

## Prompt template

```text
Use $uipath-maestro-flow to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-maestro-flow to add an IXP extraction node to this .flow, connect it to approval and queue update steps, validate the flow, and run a smoke test.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-maestro-flow/SKILL.md`](../uipath-maestro-flow/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-maestro-flow/`](../uipath-maestro-flow/) when present.
