# uipath-interact

## Purpose

UiPath UI interaction (`uip rpa uia`) - drive live desktop/browser apps: click, type, read values,
screenshot, inspect UI state, verify behavior, fill forms, navigate menus, extract table data from
running applications.

## When to use

User wants to drive or inspect a live running app (Windows desktop or browser) - 'click the button',
'fill this form', 'read the value from the screen', 'screenshot the dialog', 'extract this table',
'verify the UI shows X', 'walk through this app'. Live execution only - NOT for authoring XAML/coded
selectors at design time (use uipath-rpa).

## Required inputs

- Running desktop or browser app to inspect.
- Concrete UI action: click, type, read, screenshot, verify, or extract.
- Selectors, visible labels, URLs, or navigation path when known.
- Expected result for verification.

## Prompt template

```text
Use $uipath-interact to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $uipath-interact to open the running browser app, read the status table, extract the visible rows, and verify whether the Submit button is enabled.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../uipath-interact/SKILL.md`](../uipath-interact/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../uipath-interact/`](../uipath-interact/) when present.
