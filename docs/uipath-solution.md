# uipath-solution

## Purpose

Always invoke for `.uipx` files. UiPath Solution lifecycle via the `uip solution` CLI:
init/pack/publish/deploy/activate/upload, project add|import|remove, resource
refresh|add|remove|edit. Bundles multiple automation projects (RPA/Flow/Case/Agents/API Workflows)
into one deployable `.uipx`.

## When to use

User mentions .uipx / 'uip solution' / 'pack the solution' / 'publish the solution' / 'deploy the
solution' / 'activate' / multi-project / Solution scope / Solution Folder. Fires for 'create a new
solution', 'add project/resource to solution', 'add a queue/asset/bucket/connection to the
solution', 'import a cloud queue/asset', 'edit/remove a resource', 'change a queue/asset field',
'set an asset value in the solution'. Load BEFORE editing .uipx or running uip solution commands.
For PDD->SDD design->uipath-design; for an 'architect then deploy' two-phase request, run uipath-
design first, then return here to pack/deploy.

## Required inputs

- .uipx file or solution folder.
- Projects and resources to add, import, edit, pack, publish, deploy, or activate.
- Tenant, folder, and environment target.
- Versioning and validation requirements.

## Prompt template

```text
Use $uipath-solution to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-solution to add this Flow and RPA project to the solution, refresh resources, pack the .uipx, and show the publish/deploy commands.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-solution/SKILL.md`](../uipath-solution/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-solution/`](../uipath-solution/) when present.
