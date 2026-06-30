# uipath-admin

## Purpose

UiPath Admin via `uip admin` - Identity Server (users, groups, robot accounts, external OAuth2 apps,
secrets), Authorization (custom roles, role assignments, permission catalog, effective-access via
check-access PDP), OMS (org read/update, tenant lifecycle, service provisioning, regions, async
operation polling), IP Restriction (allowlist, enforcement switch, bypass rules, lockout safety),
Audit (event sources, paginated queries, ZIP exports - login history, compliance dumps, who-did-
what-when-where on a resource).

## When to use

UiPath Admin via `uip admin` - Identity Server (users, groups, robot accounts, external OAuth2 apps,
secrets), Authorization (custom roles, role assignments, permission catalog, effective-access via
check-access PDP), OMS (org read/update, tenant lifecycle, service provisioning, regions, async
operation polling), IP Restriction (allowlist, enforcement switch, bypass rules, lockout safety),
Audit (event sources, paginated queries, ZIP exports - login history, compliance dumps, who-did-
what-when-where on a resource). For Orchestrator-specific roles/permissions/folders/jobs->uipath-
platform. For RPA workflows->uipath-rpa.

## Required inputs

- UiPath environment, organization, and tenant.
- Admin object: user, group, role, OAuth app, secret, tenant, IP restriction, or audit query.
- Requested read or write action.
- Identifiers or names to resolve before writing.

## Prompt template

```text
Use $uipath-admin to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-admin to list users in this tenant, find inactive accounts, and show which groups they belong to. Do not modify anything.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-admin/SKILL.md`](../uipath-admin/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-admin/`](../uipath-admin/) when present.
