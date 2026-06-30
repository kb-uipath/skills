# usecasehandoff

## Purpose

Capture, verify, synthesize, package, and route customer or internal automation use case handoffs.

## When to use

Capture, verify, synthesize, package, and route customer or internal automation use case handoffs.
Use when Codex needs to gather known information from chats, email, Slack, Teams, SharePoint, Drive,
local files, or web sources; produce executive framing, cited metrics, business impact, solution
workflow, delivery plan, enterprise hardening recommendations, AI/UiPath AI Unit consumption
opportunities, risk register, next steps, and downloadable artifacts for a professional services or
automation delivery team.

## Required inputs

- Use case notes, source links, or conversation context.
- Customer, internal owner, and destination team.
- Evidence sources to verify.
- Required deliverables and routing instructions.

## Prompt template

```text
Use $usecasehandoff to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $usecasehandoff to turn these notes into a professional services handoff with executive framing, cited metrics, workflow, delivery plan, risks, next steps, and artifacts.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../usecasehandoff/SKILL.md`](../usecasehandoff/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../usecasehandoff/`](../usecasehandoff/) when present.
