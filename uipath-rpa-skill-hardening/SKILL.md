---
name: uipath-rpa-skill-hardening
description: "Use when Codex needs to improve, review, or repair UiPath/skills RPA skill content for agent reliability: `skills/uipath-rpa`, RPA discovery docs, XAML/UIA guidance, CLI snippets, project-context instructions, activity docs, validation guidance, or RPA-related PRs and issues."
---

# UiPath RPA Skill Hardening

Use this skill to make the UiPath RPA skill easier and safer for LLMs, coding agents, and users to follow.

## Scope

Primary surfaces:

- `skills/uipath-rpa/SKILL.md`
- `skills/uipath-rpa/references/**`
- `skills/uipath-rpa/assets/**`
- `agents/uipath-project-discovery-agent.md` when the change affects RPA project context
- `README.md` only when repo-level wording must match RPA discovery behavior

If the user also wants a PR, combine this with `uipath-skills-contributor`.

## Hardening Workflow

1. Start from issue and PR context:
   - Check open RPA-related issues and PRs.
   - Avoid duplicating existing PRs for Studio IPC, UIA pitfalls, semantic XAML editing, or command snippet cleanup.

2. Identify agent failure modes:
   - Wrong or obsolete commands and flags
   - Copy/paste snippets that concatenate commands
   - Host-specific assumptions that block other coding agents
   - Instructions that make agents hand-author selectors, XAML, project files, or activity metadata without using the intended tools
   - Missing recovery steps for validation, Studio cache, multiple Studio instances, UIA target capture, or Integration Service dynamic activities

3. Verify before changing:
   - Validate current CLI commands with direct `--help --output json`.
   - Read nearby docs before editing so wording remains consistent.
   - Prefer narrow wording updates over broad rewrites.

4. Patch for agent behavior:
   - Make the preferred path explicit.
   - Add stop conditions when repeated retries would waste time.
   - Keep examples copy/pasteable.
   - Keep host-specific instructions optional unless the host truly requires them.
   - Use `AGENTS.md` as the portable project-context surface when discussing cross-agent context.

5. Validate:
   - Run the scans in `references/scan-commands.md`.
   - Run repo quality gates from `uipath-skills-contributor` if publishing a PR.

## Focus Areas

Read `references/rpa-agent-ux-checklist.md` when choosing or reviewing a hardening target.

Read `references/scan-commands.md` before final validation.
