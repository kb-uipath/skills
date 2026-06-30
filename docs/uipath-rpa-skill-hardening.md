# uipath-rpa-skill-hardening

## Purpose

Use when Codex needs to improve, review, or repair UiPath/skills RPA skill content for agent
reliability: `skills/uipath-rpa`, RPA discovery docs, XAML/UIA guidance, CLI snippets, project-
context instructions, activity docs, validation guidance, or RPA-related PRs and issues.

## When to use

Use when Codex needs to improve, review, or repair UiPath/skills RPA skill content for agent
reliability: `skills/uipath-rpa`, RPA discovery docs, XAML/UIA guidance, CLI snippets, project-
context instructions, activity docs, validation guidance, or RPA-related PRs and issues.

## Required inputs

- RPA skill file, reference doc, issue, or PR to improve.
- Reliability problem, ambiguity, or validation failure.
- Expected agent behavior after the hardening change.
- Validation commands or review criteria.

## Prompt template

```text
Use $uipath-rpa-skill-hardening to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-rpa-skill-hardening to review this RPA skill issue, patch the guidance, validate the examples, and summarize why the change improves agent reliability.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-rpa-skill-hardening/SKILL.md`](../uipath-rpa-skill-hardening/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-rpa-skill-hardening/`](../uipath-rpa-skill-hardening/) when present.
