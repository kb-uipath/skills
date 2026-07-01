---
name: repo-hardening-sprint
description: Run safe, repository-agnostic cleanup and production-hardening sprints. Use when Codex is asked to review, clean up, refactor, harden, reorganize docs, improve tests, add smoke checks, prepare a repo for commit, or verify that a change can be safely pushed to main without breaking public behavior.
---

# Repo Hardening Sprint

Use this skill to turn a messy implementation into a safer, cleaner, commit-ready repo without drifting into a redesign. Optimize reliability, maintainability, docs clarity, and test coverage while preserving the repo's public contracts.

## Core Rules

- Ground every sprint in the current repo state before editing: `git status --short`, branch, remotes, package manifests, test scripts, docs layout, and likely entrypoints.
- Treat the existing product/API surface as a contract unless the user explicitly asks to change it.
- Do not revert or overwrite unrelated user changes. If unrelated changes are present, work around them and call them out in the final summary.
- Avoid dependency upgrades, broad formatting churn, generated artifact churn, and behavior changes that are not required for the cleanup goal.
- Prefer small, reversible edits grouped by subsystem. After each meaningful group, run targeted validation.
- If a cleanup reveals a larger product decision, stop changing that area and document the follow-up instead of guessing.

## Sprint Workflow

1. **Baseline**
   - Inspect `git status --short`, current branch, remotes, and recent commits.
   - Identify build/test/lint/typecheck commands from package manifests, CI config, Makefiles, Cargo/Go/Python tooling, or repo docs.
   - Search for stale docs, public API names, duplicated logic, dead code, generated binaries, local caches, and tracked build artifacts.
   - Run a cheap baseline gate first, such as typecheck or targeted tests, before changing code.

2. **Define Safe Boundaries**
   - List public commands, schemas, env vars, file formats, exported functions, protocol fields, and documented integration points that must not break.
   - Separate current public product docs from legacy, internal, roadmap, or historical docs.
   - Decide what is in scope: implementation cleanup, docs cleanup, tests, smoke checks, packaging, CI.
   - Decide what is out of scope: new product features, migrations, broad rewrites, dependency upgrades, production writes, destructive git operations.

3. **Implement Cleanup**
   - Centralize duplicated constants, validation, error handling, redaction, timeout, or serialization logic when behavior remains unchanged.
   - Split large modules only along existing responsibility boundaries; keep public entrypoints stable.
   - Remove dead wrappers, unused types, stale comments, tracked binaries, and source-tree build artifacts.
   - Make operator-facing UX truthful: help text, docs, error messages, and actual behavior must match.
   - Move legacy docs under an explicit internal/archive area when they confuse the current public surface.
   - Add or tighten tests for every behavior that could regress during cleanup.

4. **Validation**
   - Run targeted tests after each subsystem edit.
   - Run the full repo gate before finalizing. Prefer the repo's CI-equivalent command when present.
   - For this skills repository, prefer `make validate` when available; it wraps `tools/validate_repo.py`, Python syntax checks, Python unit tests, Node syntax checks, Node tests, and `git diff --check`.
   - If `make validate` is not available but `tools/validate_repo.py` exists, run `python3 tools/validate_repo.py` before final review.
   - Add a read-only smoke script when the repo has CLI/integration paths that are hard to validate through unit tests.
   - Run `git diff --check` before commit readiness.
   - If a smoke test requires credentials, production data, or writes to external systems, make it opt-in and document the manual step instead.

5. **Commit/Push Readiness**
   - Read `references/commit-readiness.md` when the user asks to commit, push, open a PR, or says the repo should be ready for main.
   - Commit only after the worktree is intentionally staged, tests are green, and the diff has been reviewed for generated files, secrets, and unrelated changes.

## Useful Search Passes

Use fast repo-native searches:

```bash
git status --short
git branch --show-current
git remote -v
rg -n "TODO|FIXME|deprecated|legacy|internal|archive|public API|schema|contract" .
rg -n "api[_-]?key|token|secret|password|credential|Bearer " . -g '!node_modules' -g '!dist'
rg --files -g 'package.json' -g 'Makefile' -g '.github/workflows/*.yml' -g 'go.mod' -g 'Cargo.toml' -g 'pyproject.toml'
```

Use the results to choose validation commands rather than imposing a fixed stack.

## Final Response Shape

Report:

- What changed, grouped by subsystem.
- What public contracts were preserved.
- Validation commands and results.
- Any residual risks or follow-ups.
- Commit/push details only if those actions actually succeeded.

Use `references/review-report-template.md` for org-shareable hardening summaries when the user wants a written report artifact.
Use `references/readiness-regression-checklist.md` when hardening reusable skills or org-shared automation assets and updating readiness scores.
