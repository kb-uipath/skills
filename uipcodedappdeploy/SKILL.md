---
name: uipcodedappdeploy
description: Deploy UiPath coded app projects with the native UiPath CLI. Use when Codex needs to increment a coded app package version, validate the project, build the app dist, pack it, publish it, and deploy it to UiPath Automation Cloud alpha using `uip codedapp pack`, `uip codedapp publish`, and `uip codedapp deploy`.
---

# UiPath Deploy

Use this skill to safely deploy a UiPath coded app to alpha. Default target: `https://alpha.uipath.com`.

## Workflow

1. Confirm the working tree and target:
   - Run `git status --short --branch`.
   - Confirm the project root contains `pyproject.toml` and `uipath.json`.
   - Use `https://alpha.uipath.com` unless the user explicitly gives another target.
   - Do not invent tenant, folder, folder key, client ID, client secret, or app name. Use provided values, infer safe defaults from project metadata, or let the CLI prompt.

2. Verify CLI availability:
   - Run `uip --version`.
   - Run `uip codedapp --help` if command availability is uncertain.
   - If the user needs authentication, run one of:
     - Interactive: `uip login --authority https://alpha.uipath.com --tenant <tenant>`
     - Unattended: `uip login --authority https://alpha.uipath.com --tenant <tenant> --client-id <id> --client-secret env.UIPATH_CLIENT_SECRET --scope "<scopes>"`
   - Never echo secrets. Prefer environment variables for secrets.

3. Increment the package version:
   - Read `[project].version` from `pyproject.toml`.
   - Increment patch by default: `1.0.13` -> `1.0.14`.
   - Use minor/major only when the user asks.
   - After changing `pyproject.toml`, run `uv lock` when `uv.lock` exists so lock metadata stays aligned.

4. Validate before publishing:
   - Run `uv run python -m pytest -q`.
   - If `app/package.json` exists, run `npm run build` in `app/`.
   - Confirm the coded app dist exists. Default dist is `app/dist` when `app/package.json` exists, otherwise `dist`.
   - Stop on validation failure; do not publish a failed build.

5. Pack, publish, and deploy the coded app to alpha:
   - Use `uip codedapp pack <dist> --name <name> --version <version> --output ./.uipath --base-url https://alpha.uipath.com`.
   - Use `uip codedapp publish --name <name> --version <version> --uipath-dir ./.uipath --base-url https://alpha.uipath.com`.
   - Use `uip codedapp deploy --name <name> --version <version> --folder-key <folder-key> --base-url https://alpha.uipath.com`.
   - Resolve folder names to folder keys with `uip or folders get "<folder>" --tenant <tenant> --output json`; coded app deploy takes `--folder-key`, not `--folder`.
   - Do not use `uv run uipath pack`, `uv run uipath publish`, or `uv run uipath deploy` for coded app deployments.

6. Verify and report:
   - Capture package version, target URL, feed/folder, and command results.
   - Run `git status --short --branch`.
   - If version or lock files changed, ask whether to commit unless the user already requested a commit.

## Helper Script

Use `scripts/uipcodedappdeploy.py` for a consistent version bump and command sequence.

Dry run from a project root:

```bash
python scripts/uipcodedappdeploy.py --project-root . --tenant-name "<tenant>" --folder "<folder>"
```

Execute:

```bash
python scripts/uipcodedappdeploy.py --project-root . --tenant-name "<tenant>" --folder "<folder>" --execute
```

Useful options:

- `--part patch|minor|major` controls the version increment; default is `patch`.
- `--set-version X.Y.Z` sets an explicit version.
- `--target-url https://alpha.uipath.com` overrides the default target.
- `--app-dist <path>` overrides the dist directory; default is `app/dist` when `app/package.json` exists.
- `--package-name <name>` overrides the pyproject package name used for pack/publish.
- `--app-name <name>` overrides the app name used for deploy; default is `--package-name`.
- `--folder "<folder>"` resolves a folder path/name to a folder key with `uip or folders get`.
- `--folder-key <key>` passes a folder key directly to `uip codedapp deploy`.
- `--tenant-name <name>` passes the tenant to publish and folder lookup.
- `--org-id`, `--org-name`, and `--tenant-id` pass explicit context to coded app commands when needed.
- `--reuse-client` passes `--reuse-client` to `uip codedapp pack`.
- `--skip-tests` or `--skip-app-build` should only be used when the user explicitly accepts that risk.
- `--offline` produces a command plan without probing `uip` or resolving folder names. Use it for fixture tests, docs examples, and environments without UiPath CLI access. It cannot be combined with `--execute` and requires `--folder-key` for non-GUID folders.

The script defaults to dry-run mode. It only edits `pyproject.toml`, runs `uv lock`, and runs coded app pack/publish/deploy when `--execute` is passed.
