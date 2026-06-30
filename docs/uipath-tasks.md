# uipath-tasks

## Purpose

UiPath Action Center human-in-the-loop tasks via `uip tasks` - list, assign, complete
approval/validation tasks.

## When to use

User says 'approve task', 'pending approval', 'pending action item', 'review action', 'list my
tasks', 'reassign task' in an Orchestrator/Action Center context. NOT for TaskCreate/TaskUpdate
(general session-task tracking) or Document Understanding validation.

## Required inputs

- Task, action, approval, validation, or queue context.
- Requested action: list, inspect, assign, complete, approve, or reject.
- Tenant and folder context.
- Completion payload or outcome when writing.

## Prompt template

```text
Use $uipath-tasks to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-tasks to list my pending Action Center approvals, inspect the highest-priority item, and ask before completing anything.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-tasks/SKILL.md`](../uipath-tasks/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-tasks/`](../uipath-tasks/) when present.
