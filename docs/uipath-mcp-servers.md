# uipath-mcp-servers

## Purpose

UiPath AgentHub MCP server registration + tool authoring via `uip agenthub mcp` (six server types:
uipath / coded / command / remote / platform / swagger) and `uip agenthub mcp-tools` (three tool
kinds: is-activity / resource / raw on `uipath`-type servers).

## When to use

UiPath AgentHub MCP server registration + tool authoring via `uip agenthub mcp` (six server types:
uipath / coded / command / remote / platform / swagger) and `uip agenthub mcp-tools` (three tool
kinds: is-activity / resource / raw on `uipath`-type servers). For Integration Service activity
authoring->load `references/is-activity-workflow.md`. For Python MCP servers / coded-agent
integration->uipath-agents. For raw IS CLI->uipath-platform.

## Required inputs

- MCP server type: uipath, coded, command, remote, platform, or swagger.
- Tool kind and source API or resource.
- AgentHub target, names, descriptions, arguments, and auth needs.
- Validation and registration intent.

## Prompt template

```text
Use $uipath-mcp-servers to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-mcp-servers to register a command MCP server for this tool, define the allowed arguments, validate it, and show how an agent should call it.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-mcp-servers/SKILL.md`](../uipath-mcp-servers/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-mcp-servers/`](../uipath-mcp-servers/) when present.
