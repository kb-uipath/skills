# uipath-maestro-bpmn

## Purpose

Always invoke for `.bpmn`, `project.uiproj`, `entry-points.json`, `operate.json`,
`bindings_v2.json`, or `package-descriptor.json` files. UiPath Maestro BPMN / Process Orchestration
- author, inspect, validate, package, operate, diagnose. Model writes BPMN skeleton + non-IS UiPath
XML; CLI owns Integration Service nodes/templates and generated package files.

## When to use

Always invoke for `.bpmn`, `project.uiproj`, `entry-points.json`, `operate.json`,
`bindings_v2.json`, or `package-descriptor.json` files. UiPath Maestro BPMN / Process Orchestration
- author, inspect, validate, package, operate, diagnose. Model writes BPMN skeleton + non-IS UiPath
XML; CLI owns Integration Service nodes/templates and generated package files. For .flow
JSON->uipath-maestro-flow. For XAML/coded workflows->uipath-rpa. For Python agents->uipath-agents.
For Case plans->uipath-maestro-case.

## Required inputs

- BPMN project path or desired process orchestration design.
- Tasks, events, gateways, subprocesses, and Integration Service needs.
- Packaging, operate, or diagnosis target.
- Validation expectations and generated files to preserve.

## Prompt template

```text
Use $uipath-maestro-bpmn to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-maestro-bpmn to inspect this .bpmn project, add the missing approval branch, validate package metadata, and explain any generated files that must be refreshed by the CLI.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-maestro-bpmn/SKILL.md`](../uipath-maestro-bpmn/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-maestro-bpmn/`](../uipath-maestro-bpmn/) when present.
