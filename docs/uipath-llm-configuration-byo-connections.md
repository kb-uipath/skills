# uipath-llm-configuration-byo-connections

## Purpose

UiPath BYO LLM product configurations in the LLM Gateway via `uip llm-configuration byo-connections`
- list, get, create, update, delete, list-product-configs. Register tenant-owned OpenAI / Azure
OpenAI / AWS Bedrock / Anthropic / Google Vertex / Mistral keys against UiPath products (agents,
agenthub, jarvis, IXP, agent builder). Wraps product-level llm-configurations endpoints.

## When to use

UiPath BYO LLM product configurations in the LLM Gateway via `uip llm-configuration byo-connections`
- list, get, create, update, delete, list-product-configs. Register tenant-owned OpenAI / Azure
OpenAI / AWS Bedrock / Anthropic / Google Vertex / Mistral keys against UiPath products (agents,
agenthub, jarvis, IXP, agent builder). Wraps product-level llm-configurations endpoints. For tenant-
wide AI governance (allowed providers, blocked models)->uipath-governance.

## Required inputs

- Target UiPath product feature for BYO LLM routing.
- Provider and Integration Service connection details.
- Model mapping shape and model names.
- Create, update, list, audit, delete, or validation intent.

## Prompt template

```text
Use $uipath-llm-configuration-byo-connections to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-llm-configuration-byo-connections to audit BYO LLM configurations for Agent Builder, list product configs, and identify disabled or stale mappings.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-llm-configuration-byo-connections/SKILL.md`](../uipath-llm-configuration-byo-connections/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-llm-configuration-byo-connections/`](../uipath-llm-configuration-byo-connections/) when present.
