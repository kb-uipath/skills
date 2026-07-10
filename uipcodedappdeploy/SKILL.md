---
name: uipcodedappdeploy
description: Plan, validate, and explicitly execute UiPath coded app deployments with versioned JSON plans, input hashes, redacted receipts, and the native `uip codedapp` CLI.
---

# UiPath Coded App Deploy

Use this skill for plan-first deployment of a UiPath coded app. Default target: `https://alpha.uipath.com`.

## Hard Boundaries

- Planning is the default and does not modify project files or invoke `uv`, `npm`, `uip`, or HTTP. `--plan-output` is the only explicit planning write.
- Never execute directly from planning arguments. Generate a persisted plan, review it, then use `--plan <file> --execute` only after the user authorizes deployment.
- Never invent a tenant, organization, folder key, app name, package name, target, or verification URL.
- Execution requires a folder GUID embedded in the plan. Resolve a folder name separately with a read-only query and pass `--folder-key` while generating a new plan.
- Never pass or print access tokens or client secrets. Use an existing `uip` login or environment-backed CLI authentication.
- Do not run live certification or external writes unless the user explicitly opts in.

## Prerequisites

1. Use Python 3.11 or later; the helper parses TOML with standard-library `tomllib`.
2. Confirm the worktree and project root with `git status --short --branch`.
3. Confirm both `pyproject.toml` and `uipath.json` are present.
4. Confirm `uip`, `uv`, and npm availability as required by the generated stages.
5. Obtain the exact target origin, tenant/org context, and folder GUID from the user or trusted project context.

## Plan

Run from the skills repository root:

```bash
python3.11 uipcodedappdeploy/scripts/uipcodedappdeploy.py \
  --project-root /absolute/path/to/project \
  --target-url https://alpha.uipath.com \
  --tenant-name '<tenant>' \
  --folder-key 11111111-2222-3333-4444-555555555555 \
  --format json \
  --plan-output /absolute/path/to/deploy-plan.json
```

Review:

- Plan schema and SHA-256 plan hash.
- Initial and versioned input hashes for `pyproject.toml` and `uipath.json`.
- Strict SemVer progression and requested patch/minor/major behavior.
- Project-relative dist and `.uipath` paths.
- Target, tenant/org values, folder GUID, package/app names, and optional verification URL.
- Ordered allowlisted stages and any blockers.
- Any explicit `--skip-tests` or `--skip-app-build` risk acceptance.

Planning without `--plan-output` is useful for inspection but cannot be executed.

## Execute

After explicit approval:

```bash
python3.11 uipcodedappdeploy/scripts/uipcodedappdeploy.py \
  --plan /absolute/path/to/deploy-plan.json \
  --execute \
  --format json
```

Execution atomically updates only `[project].version`, then runs `uv lock` when applicable, tests, app build, dist/main-file validation, `uip --version`, pack, publish, deploy, and optional HTTPS verification. It writes a redacted sibling receipt named `<plan>.receipt.json`.

## Resume And Recovery

For a remediated local or explicitly reviewed failed stage:

```bash
python3.11 uipcodedappdeploy/scripts/uipcodedappdeploy.py \
  --plan /absolute/path/to/deploy-plan.json \
  --execute \
  --resume
```

- Keep the plan and receipt unchanged. Hash mismatches require trusted-artifact recovery, not manual edits.
- The version is intentionally written before lock/test/build. A local failure can therefore leave the planned version in `pyproject.toml`; the versioned input hash supports resume.
- Resume skips succeeded stages and retries the failed stage.
- Resume rejects a `running` publish/deploy receipt because the remote result is indeterminate. Verify live state and create an operator-reviewed recovery plan.
- URL verification failure occurs after deploy and does not roll the deployment back.

## Rejected Legacy Options

The helper keeps legacy flag names only to fail closed with migration guidance:

- Replace `--folder <name>` with a separately resolved `--folder-key <GUID>`.
- Replace ambiguous `--tenant` with `--tenant-name` or `--tenant-id`.
- Replace `--my-workspace` with its explicit folder GUID.
- Remove no-op `--pack-nolock`, `--use-deploy-command`, and `--offline`.
- Replace direct `--execute` with `--plan-output`, review, then `--plan ... --execute`.

## Reporting

Report the old/new version, target origin, tenant/org context, folder key, plan hash, receipt path, verification result, and final `git status --short --branch`. Never include credentials or subprocess output that may contain them.

The public runtime, data handling, failure recovery, limitations, and opt-in nonproduction certification guidance are in `docs/uipcodedappdeploy.md`.
