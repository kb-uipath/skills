# llm-council

## Purpose

Run a structured multi-perspective council for high-stakes decisions using five independent advisor
subagents, anonymous peer review, and a chairman verdict with report artifacts.

## When to use

Run a structured multi-perspective council for high-stakes decisions using five independent advisor
subagents, anonymous peer review, and a chairman verdict with report artifacts. Use when the user
explicitly invokes $llm-council, says "council this", asks to run a council or multi-agent advisor
panel, or wants to stress-test a pivot, pricing, positioning, hiring, launch, strategy, or other
expensive-to-get-wrong choice. Do not use for factual lookups, simple content generation, summaries,
or tasks with one correct answer.

## Required inputs

- Decision statement and options under consideration.
- Constraints, stakes, time horizon, and success criteria.
- Known evidence or artifacts the council must consider.
- Preferred output format for the chairman verdict.

## Prompt template

```text
Use $llm-council to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $llm-council to stress-test whether we should launch this productized services offer now or wait one quarter. Include constraints, risks, and a final chairman recommendation.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../llm-council/SKILL.md`](../llm-council/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../llm-council/`](../llm-council/) when present.
