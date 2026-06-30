# uipath-governance

## Purpose

UiPath governance via `uip gov` - author and deploy policies on two layers. AOps product policies
(`uip gov aops-policy`): block/restrict/enforce features in Studio, StudioX, Assistant, Robot, AI
Trust Layer, Agent Builder; deploy to user/group/tenant. Access ToolUsePolicy (`uip gov access-
policy`): allow/deny when one workflow invokes another as a tool
(Agent->Agent/Maestro/Flow/RPA/API/Case), gated by tag, caller, or actor (User/Group). Skill
classifies product-layer vs resource/tool-use intent before authoring.

## When to use

UiPath governance via `uip gov` - author and deploy policies on two layers. AOps product policies
(`uip gov aops-policy`): block/restrict/enforce features in Studio, StudioX, Assistant, Robot, AI
Trust Layer, Agent Builder; deploy to user/group/tenant. Access ToolUsePolicy (`uip gov access-
policy`): allow/deny when one workflow invokes another as a tool
(Agent->Agent/Maestro/Flow/RPA/API/Case), gated by tag, caller, or actor (User/Group). Skill
classifies product-layer vs resource/tool-use intent before authoring. For platform ops->uipath-
platform.

## Required inputs

- Governance intent: product policy or tool-use access policy.
- Target users, groups, tenants, products, tools, tags, or resources.
- Allow, deny, restrict, enforce, or audit behavior.
- Deployment and evaluation target.

## Prompt template

```text
Use $uipath-governance to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-governance to draft an AOps policy that restricts unapproved LLM providers for Agent Builder users in this tenant, then show the deploy plan before applying it.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-governance/SKILL.md`](../uipath-governance/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-governance/`](../uipath-governance/) when present.
