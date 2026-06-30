# uipath-maestro-case

## Purpose

Always invoke for `caseplan.json` files. UiPath Case Management authoring (caseplan.json) from
sdd.md, or via lightweight interview if sdd.md absent. Produces tasks.md plan, writes caseplan.json
via per-plugin JSON recipes.

## When to use

Always invoke for `caseplan.json` files. UiPath Case Management authoring (caseplan.json) from
sdd.md, or via lightweight interview if sdd.md absent. Produces tasks.md plan, writes caseplan.json
via per-plugin JSON recipes. For .xaml->uipath-rpa, .flow->uipath-maestro-flow, .bpmn->uipath-
maestro-bpmn. For PDD->SDD or complex/multi-product->uipath-design.

## Required inputs

- caseplan.json path or request to create a case plan.
- SDD, process notes, or interview answers.
- Case tasks, roles, variables, forms, SLAs, and transitions.
- Validation and packaging expectations.

## Prompt template

```text
Use $uipath-maestro-case to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-maestro-case to generate caseplan.json from this SDD, including tasks, variables, role assignments, and validation rules.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-maestro-case/SKILL.md`](../uipath-maestro-case/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-maestro-case/`](../uipath-maestro-case/) when present.
