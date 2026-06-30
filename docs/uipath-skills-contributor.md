# uipath-skills-contributor

## Purpose

Use when Codex needs to contribute to the UiPath/skills repository end to end: analyze open issues
and PRs, prioritize high-impact low-effort fixes or enhancements, implement clean external-
contributor patches, validate repo requirements, push branches, create ready pull requests, and
review or repair submitted PRs without Codex branding or inappropriate labels.

## When to use

Use when Codex needs to contribute to the UiPath/skills repository end to end: analyze open issues
and PRs, prioritize high-impact low-effort fixes or enhancements, implement clean external-
contributor patches, validate repo requirements, push branches, create ready pull requests, and
review or repair submitted PRs without Codex branding or inappropriate labels.

## Required inputs

- UiPath/skills repository path, issue, PR, or improvement area.
- Contribution goal and constraints.
- Validation commands required by the repository.
- Branch, commit, and PR expectations.

## Prompt template

```text
Use $uipath-skills-contributor to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-skills-contributor to pick a high-impact open issue in UiPath/skills, implement a clean external-contributor patch, validate it, and prepare a ready PR.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-skills-contributor/SKILL.md`](../uipath-skills-contributor/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-skills-contributor/`](../uipath-skills-contributor/) when present.
