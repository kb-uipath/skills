# Commit and Push Readiness

Use this checklist only when the user asks to commit, push, prepare for main, or publish.

## Pre-Commit Gate

1. Confirm branch and remote state:
   ```bash
   git status --short
   git branch --show-current
   git remote -v
   git fetch origin
   ```

2. Confirm the diff is intentional:
   ```bash
   git diff --stat
   git diff --name-status
   git diff --check
   ```

3. Look for common commit blockers:
   - tracked binaries or build artifacts
   - generated lockfile churn that does not match manifest changes
   - secrets or realistic credentials
   - unrelated user edits
   - broken doc links after moves
   - deleted files that should have been renames

4. Run the full gate:
   - Prefer the repo's CI command.
   - Otherwise run typecheck/build/tests/lint in the same order CI would.
   - Add smoke tests for CLI and integration behavior when available.

## Staging and Commit

- Use `git add -A` only after reviewing the full diff and confirming deletions/renames are intentional.
- Use a concise conventional commit when the repo has no stronger convention, for example:
  ```bash
  git commit -m "chore: harden repo cleanup path"
  ```
- After commit, verify:
  ```bash
  git status --short
  git log --oneline --max-count=3
  ```

## Push Safety

- Before pushing to main, verify fast-forward relationship:
  ```bash
  git fetch origin main
  git rev-list --left-right --count origin/main...HEAD
  ```
- Safe direct push condition for main: left count is `0` and right count is the number of local commits to push.
- If local branch is not `main` but the user explicitly asked to push to main, push the reviewed commit with:
  ```bash
  git push origin HEAD:main
  ```
- If remote main has diverged, do not force push. Pull/rebase or ask for direction.

## Final Report

Include commit SHA, pushed branch, validation commands, and any residual risk. Emit git stage/commit/push directives only after those actions succeeded.
