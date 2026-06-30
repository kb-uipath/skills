# uipath-rpa

## Purpose

Always invoke for `.xaml` or `.cs` workflow files. UiPath RPA - create, edit, build, run, debug
`.cs` coded workflows and `.xaml` workflows. UI automation with Object Repository selectors, test
case authoring, Integration Service connector calls. Live desktop/browser UI exploration and
control. Deploy via `.uipx`->uipath-solution. Non-solution Orchestrator ops->uipath-platform. Test
reports->uipath-test. Agents->uipath-agents.

## When to use

User wants to create, edit, debug, or run a UiPath automation - '.cs' coded workflows or '.xaml'
files. Triggers: 'build a workflow', 'automate Excel/email/web/PDF/queue items', 'add a try-catch',
'fix this XAML error', 'scrape this site', 'process invoices', 'create a test case', or project.json
shows UiPath dependencies. NOT for '.flow' files (->uipath-maestro-flow), Python agents (->uipath-
agents).

## Required inputs

- UiPath project path or automation request.
- .xaml or .cs workflow target.
- Systems, selectors, data sources, queues, assets, and expected outputs.
- Run, debug, package, or test requirements.

## Prompt template

```text
Use $uipath-rpa to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-rpa to add retry-safe queue processing to this coded workflow, validate selectors, run the project checks, and explain the changes.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-rpa/SKILL.md`](../uipath-rpa/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-rpa/`](../uipath-rpa/) when present.
