# uipath-platform

## Purpose

UiPath platform ops via the uip CLI - use this skill for ANY task hitting UiPath Cloud /
Orchestrator / Studio Web / Integration Service / LLM Gateway. Load BEFORE writing any code that
calls a UiPath API. Covers auth, folders, assets, queues, storage buckets, bucket files, libraries,
webhooks, triggers, processes, jobs, machines, users, roles, sessions, calendars, IS
connectors/connections/activities, BYO LLM product configurations (`uip llm-configuration byo-
connections` - register / audit / re-probe / troubleshoot tenant-owned OpenAI / Azure OpenAI /
Bedrock / Vertex / Anthropic keys against UiPath products), traces, licensing.

## When to use

User mentions UiPath / Orchestrator / Studio Web / Integration Service / LLM Gateway / 'uip' CLI /
asset / queue / bucket / library / webhook / trigger / connector / connection / tenant / folder /
robot / package / BYO LLM. Also 'upload to UiPath', 'create asset', 'start job', 'list queues',
'deploy a single package to Orchestrator', 'OAuth2 token', 'register my own LLM key', 'configure a
model substitution', 'my BYO LLM key stopped working / returns errors', 're-probe / audit a BYO
configuration', 'uipath.com REST'. Load BEFORE composing any HTTP request - most UiPath tasks have a
`uip` command. For `uip solution` ops or `.uipx` deploys->uipath-solution.

## Required inputs

- UiPath environment, organization, tenant, and folder when relevant.
- Platform object: asset, queue, bucket, job, trigger, process, package, connector, connection, library, trace, license, or LLM config.
- Operation requested and target identifiers.
- Read-only versus write intent.

## Prompt template

```text
Use $uipath-platform to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-platform to list queues in this folder, inspect failed queue items from the last 24 hours, and summarize the failure categories without changing anything.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-platform/SKILL.md`](../uipath-platform/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-platform/`](../uipath-platform/) when present.
