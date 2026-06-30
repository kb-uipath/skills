# uipath-solution-design

## Purpose

Always invoke for `sdd.md`, `pdd.md`, or PDD/SDD documents. UiPath PDD->SDD: analyze PDDs
(PDF/docx/md), pick scope (single product or multi-project Solution: RPA/Flow/Case/Agents/Apps/API
Workflows), write implementation-ready SDD.

## When to use

Always invoke for `sdd.md`, `pdd.md`, or PDD/SDD documents. UiPath PDD->SDD: analyze PDDs
(PDF/docx/md), pick scope (single product or multi-project Solution: RPA/Flow/Case/Agents/Apps/API
Workflows), write implementation-ready SDD. For task plans->uipath-planner. For project
setup->uipath-platform.

## Required inputs

- PDD, SDD, or process document path.
- Target products and solution scope.
- Business rules, exception paths, integrations, and nonfunctional requirements.
- Output location for the implementation-ready SDD.

## Prompt template

```text
Use $uipath-solution-design to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-solution-design to analyze this PDD and create an SDD for a UiPath solution using Flow, RPA, Action Center, and queues.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-solution-design/SKILL.md`](../uipath-solution-design/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-solution-design/`](../uipath-solution-design/) when present.
