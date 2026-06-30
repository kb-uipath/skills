# uipath-rpa-legacy

## Purpose

Always invoke when `project.json` has `targetFramework: Legacy` or the user mentions legacy XAML /
.NET 4.6.1. UiPath legacy RPA (.NET Framework 4.6.1, XAML) via `uip rpa-legacy`.

## When to use

Always invoke when `project.json` has `targetFramework: Legacy` or the user mentions legacy XAML /
.NET 4.6.1. UiPath legacy RPA (.NET Framework 4.6.1, XAML) via `uip rpa-legacy`. For Windows/cross-
platform->uipath-rpa.

## Required inputs

- Legacy UiPath project path with targetFramework Legacy or .NET Framework 4.6.1.
- XAML workflow to create, edit, validate, or debug.
- Activity package constraints and runtime environment.
- Expected validation or debug output.

## Prompt template

```text
Use $uipath-rpa-legacy to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-rpa-legacy for this Windows-Legacy project. Fix the XAML validation errors, preserve legacy compatibility, and show the validation result.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-rpa-legacy/SKILL.md`](../uipath-rpa-legacy/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-rpa-legacy/`](../uipath-rpa-legacy/) when present.
