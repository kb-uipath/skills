# RPA Agent UX Checklist

Use this checklist to evaluate whether RPA skill docs help an agent succeed without hidden knowledge.

## Command Correctness

- Commands use current `uip rpa ...` names rather than obsolete wrappers.
- Flags appear in current command help or are clearly documented as global flags.
- Examples include `--output json` when output is parsed.
- Multi-command examples are separated by newlines and fenced correctly.
- Docs do not teach legacy flags unless they are still valid and necessary.

## Project Context

- The agent loads or generates project context before creating or editing workflows.
- `AGENTS.md` is treated as a portable context surface.
- Host-specific caches such as `.claude/rules/project-context.md` remain optional unless the workspace already uses that host.
- Generated context records facts from project files, not assumptions.

## XAML Authoring

- XAML guidance tells agents to read project structure, expression language, dependencies, and existing patterns first.
- Agents use `get-default-activity-xaml` as a starting point for activities rather than inventing namespaces or properties.
- Dynamic Integration Service activity configuration blobs are treated as opaque.
- File edits preserve unrelated ViewState and namespace declarations.
- Validation loops have max attempts and diagnostic categorization.

## UI Automation

- Agents do not hand-write selectors.
- UIA target capture and selector recovery follow the documented skill flow.
- Docs warn against dynamic selectors and brittle class names where relevant.
- Debug runs use the workflow that preserves UI state and then cleans up windows.
- Multiple Studio instances and stale Studio cache have recovery guidance.

## Coded Workflows

- Coded workflow guidance distinguishes workflow/test files from source files.
- Entry points and `fileInfoCollection` rules are clear for Process, Tests, and Library projects.
- Package/service mapping is explicit enough to prevent missing service properties.
- Coded workflows use current validation and build commands.

## Acceptance Signals

A hardening PR is strong when it:

- Reduces likely agent retries or invalid artifacts
- Is backed by current CLI help, observed issue evidence, or local docs consistency
- Does not require internal product knowledge
- Has simple local validation
- Leaves existing RPA authoring strategy intact
