# repo-hardening-sprint

## Purpose

Run safe, repository-agnostic cleanup and production-hardening sprints.

## When to use

Run safe, repository-agnostic cleanup and production-hardening sprints. Use when Codex is asked to
review, clean up, refactor, harden, reorganize docs, improve tests, add smoke checks, prepare a repo
for commit, or verify that a change can be safely pushed to main without breaking public behavior.

## Required inputs

- Repository path and target branch or commit state.
- Scope of hardening: tests, docs, lint, security, structure, or release readiness.
- Behavior that must not change.
- Checks that should pass before completion.

## Prompt template

```text
Use $repo-hardening-sprint to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $repo-hardening-sprint on this repository. Identify the highest-impact cleanup, implement safe fixes, run the relevant checks, and summarize remaining risks before commit.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../repo-hardening-sprint/SKILL.md`](../repo-hardening-sprint/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../repo-hardening-sprint/`](../repo-hardening-sprint/) when present.
