---
name: uipath-skills-contributor
description: "Use when Codex needs to contribute to the UiPath/skills repository end to end: analyze open issues and PRs, prioritize high-impact low-effort fixes or enhancements, implement clean external-contributor patches, validate repo requirements, push branches, create ready pull requests, and review or repair submitted PRs without Codex branding or inappropriate labels."
---

# UiPath Skills Contributor

Use this skill to repeat the contribution methodology from the UiPath/skills workstream: careful triage, scoped implementation, strict validation, and clean PR submission.

## Companion Skills

- Use the GitHub plugin skills when available:
  - `github:github` for issue and PR triage
  - `github:yeet` for staging, commit, push, and PR creation
  - `github:gh-fix-ci` for failing GitHub Actions checks
  - `github:gh-address-comments` for actionable review feedback
- If the target change is specifically in `skills/uipath-rpa`, use `uipath-rpa-skill-hardening` for RPA-specific scan and quality checks.

## Workflow

1. Establish repo state:
   - Work in the local `UiPath/skills` checkout.
   - Run `git status --short --branch`, `git remote -v`, and fetch `origin main`.
   - If not already on a work branch, start from fresh `main`.
   - Preserve user changes; do not reset or revert unrelated work.

2. Avoid duplicate work:
   - List open PRs and issues before choosing scope.
   - Check whether existing PRs already cover the issue, file, or behavior.
   - Avoid broad product-surface changes that are assigned or clearly owned unless the patch is tiny and complementary.

3. Prioritize candidates:
   - Prefer high-impact, low-to-medium effort changes that improve agent UX, docs clarity, command correctness, validation, or adoption.
   - Prefer precise fixes over new broad abstractions.
   - Use the rubric in `references/pr-methodology.md` when the next task is ambiguous.

4. Implement narrowly:
   - Create one branch per coherent PR.
   - Match repository wording and PR title style, usually `docs(scope): ...`, `fix(scope): ...`, or `test(scope): ...`.
   - Do not use Codex branding in branch names, commit messages, PR titles, or PR bodies when the user requested that.
   - Do not add labels unless repo rules or the user explicitly require them.
   - Link related issues with `Refs #NNN` unless the PR fully closes the issue.

5. Validate before publishing:
   - Run the checks that match the changed surface.
   - Always run `git diff --check`.
   - For changed `SKILL.md` files, run `bash hooks/validate-skill-descriptions.sh <files>`.
   - For Markdown-only changes, run a fenced-code balance scan across changed `.md` files.
   - For command docs, verify command names and flags against current CLI help where possible.
   - See `references/quality-gates.md`.

6. Publish and review:
   - Commit intentionally.
   - Push to the contributor fork when upstream is not writable.
   - Open a ready PR unless the user asks for draft.
   - Re-check PR title, body, labels, linked issues, draft status, and visible checks.
   - Treat `action_required` on fork workflows as an approval gate unless a real check failure is visible.

## PR Hygiene

- Keep PRs reviewable: one idea, one patch.
- In PR bodies, include summary, validation, and related issues.
- Avoid overclaiming. If no existing issue matches, say so.
- If checks cannot run locally, say exactly why and what substitute validation was performed.
