# gtm-org-proposal-generator

## Purpose

Build executive-level UiPath automation proposal cards from public organizational research.

## When to use

Build executive-level UiPath automation proposal cards from public organizational research. Use when
Codex is asked to research an organization, agency, department, public company, healthcare system,
university, or other institution; analyze budgets, strategic goals, administrative burden, or cost
drivers; identify automation use cases; and produce cited GTM, sales, C-suite, public sector, or
federal proposal content aligned to a specified industry vertical and UiPath deployment type.

## Required inputs

- Target organization or account.
- Industry or public-sector vertical.
- UiPath deployment context and capability constraints.
- Desired number of use cases and final format.

## Prompt template

```text
Use $gtm-org-proposal-generator to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $gtm-org-proposal-generator for Tennessee STS, vertical public sector, deployment Automation Cloud Public Sector. Research public sources and generate five cited UiPath proposal cards.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../gtm-org-proposal-generator/SKILL.md`](../gtm-org-proposal-generator/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../gtm-org-proposal-generator/`](../gtm-org-proposal-generator/) when present.
