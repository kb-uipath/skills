# uipath-agents

## Purpose

End-to-end work with UiPath Agents of all types: build, integrate with UiPath Products (e.g.,
Orchestrator, Flow, Maestro), design with UiPath Tools (e.g., Agent Builder/Studio Web), and deploy.

## When to use

Must use when user mentions or implies any Agent lifecycle phase - e.g., auth, design, scaffold,
Studio Web sync, flow integration, editing, pack/deploy/version bump, eval, tracing, guardrails,
memory spaces, bindings, attachments. Example requests: 'create/build a UiPath agent', 'build a low-
code / Agent Builder agent', 'add agent memory spaces', 'build a coded / Python agent (LangGraph /
LlamaIndex / OpenAI Agents)', 'scaffold an agent project', 'run / evaluate / deploy my agent'.

## Required inputs

- Agent type: low-code Agent Builder or coded Python agent.
- Project path or request to scaffold a new project.
- Tools, resources, memory, guardrails, evals, and deployment target.
- UiPath environment and tenant when deployment or live validation is required.

## Prompt template

```text
Use $uipath-agents to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-agents to scaffold a coded agent that checks invoice status using Orchestrator queues, adds evaluation cases, and prepares it for deployment.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-agents/SKILL.md`](../uipath-agents/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-agents/`](../uipath-agents/) when present.
