# uipath-data-fabric

## Purpose

UiPath Data Fabric entity/record CRUD via `uip df`. Create entities, insert/query/update/delete
records, CSV import, file attachments.

## When to use

UiPath Data Fabric entity/record CRUD via `uip df`. Create entities, insert/query/update/delete
records, CSV import, file attachments. For Flow connector nodes (query/create/update/delete/get-by-
id inside a `.flow`)->uipath-maestro-flow. For Orchestrator->uipath-platform. For Integration
Service->uipath-platform.

## Required inputs

- Entity name or entity definition.
- Record data, query filters, CSV file, or attachment paths.
- CRUD operation requested.
- Tenant and folder context when live operations are needed.

## Prompt template

```text
Use $uipath-data-fabric to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-data-fabric to create an entity for vendor onboarding, import these CSV records, and verify the first five records after import.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-data-fabric/SKILL.md`](../uipath-data-fabric/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-data-fabric/`](../uipath-data-fabric/) when present.
