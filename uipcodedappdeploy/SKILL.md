---
name: uipcodedappdeploy
description: Plan, validate, and explicitly execute UiPath coded app deployments with exact source, dist, package, CLI, profile, route, client, and target provenance.
---

# UiPath Coded App Deploy

Use this skill for plan-first deployment of a UiPath Coded App. Planning is
local and non-mutating except for an explicitly requested plan file. Publishing
and deployment are always a separate, human-approved execution.

## Hard Boundaries

- Never deploy directly from planning arguments. Persist and display the v2.2
  plan, obtain approval of its exact `plan_hash`, then pass that hash through
  `--approved-plan-hash`.
- Never invent or reuse a target, tenant, organization, folder, OAuth client,
  route, CLI profile, tag set, package identity, or verification URL.
- Resolve folder names and OAuth applications separately with read-only UiPath
  commands. Plans contain the exact folder GUID and dedicated non-confidential
  client GUID.
- Pin an absolute UiPath CLI executable, its exact SemVer, and a named login
  profile. Do not rely on `PATH` for a release.
- The CLI control-plane origin belongs in `--control-plane-url`. Do not confuse
  it with a browser SDK/API origin.
- Executable plans require an explicit `--environment` and its exact control
  plane: `staging` maps only to `https://staging.uipath.com`, while `alpha`
  maps only to `https://alpha.uipath.com`. Never infer one from the other.
  Missing, mismatched, implicit, and production targets are blocked.
- When route verification is requested, staging accepts only
  `*.staging.uipath.host` and alpha accepts only `*.alpha.uipath.host`. Bare
  suffixes, cross-environment hosts, credentials, ports, and query strings are
  rejected.
- `codedapp pack` is local and receives no authentication flags. The helper
  rejects legacy `--reuse-client`; the dedicated client is bound only through
  `codedapp deploy --client-id`.
- Never pass, print, or persist access tokens, client secrets, profile files, or
  subprocess response bodies.
- Do not run `publish`, `deploy`, live route verification, or any other external
  write without explicit user authorization of the persisted plan hash.

## Prerequisites

1. Use Python 3.11 or later.
2. Confirm the repository, branch, clean tracked state, and exact source commit.
   Execution also rejects every non-ignored untracked path, so keep plan,
   receipt, candidate-package, build, and evidence outputs either in reviewed
   ignored locations or outside the project root.
3. Confirm valid `pyproject.toml` and `uipath.json` manifests.
   When a `uv.lock` exists, it must contain exactly one local project package
   whose version matches `[project].version`; the plan binds the deterministic
   project-version-only lockfile transition.
4. Run the repository's complete test/build gates before accepting
   `--skip-tests --skip-app-build`.
5. Build the dist and compute its deterministic digest.
6. Create a local candidate package with the same pinned CLI, package name, and
   target version. The helper binds its deterministic coded-app content digest
   and exact candidate file SHA-256. Execution may produce different ZIP
   envelope bytes, but it refuses to publish different coded-app content.
7. Confirm the named CLI profile is logged into the exact approved org and
   tenant.

## Generate The Plan

Run from the skills repository root:

```bash
python3.11 uipcodedappdeploy/scripts/uipcodedappdeploy.py \
  --project-root /absolute/path/to/project \
  --set-version 0.1.0 \
  --environment staging \
  --control-plane-url https://staging.uipath.com \
  --org-id 11111111-2222-3333-4444-555555555555 \
  --org-name '<organization>' \
  --tenant-id 66666666-7777-8888-9999-000000000000 \
  --tenant-name '<tenant>' \
  --folder-key aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee \
  --package-name '<package-name>' \
  --app-name '<display-title>' \
  --path-name '<route-slug>' \
  --client-id ffffffff-1111-2222-3333-444444444444 \
  --tags governance,internal \
  --source-sha '<full-commit-sha>' \
  --package-digest 'sha256:<candidate-coded-app-content-digest>' \
  --cli-executable /absolute/path/to/pinned/uip \
  --cli-version 1.198.0 \
  --cli-profile '<named-profile>' \
  --skip-tests \
  --skip-app-build \
  --format json \
  --plan-output /absolute/ignored/evidence/deploy-plan.json
```

The helper hashes the current dist and a candidate at the planned
`.uipath/<name>.<version>.nupkg` path automatically. Use `--dist-digest` or
`--package-digest` when independently computed values must be cross-checked.

For alpha, change both target arguments together to `--environment alpha` and
`--control-plane-url https://alpha.uipath.com`; do not change only one.

Review all of the following:

- Plan schema `2.2`, explicit environment, plan hash, deployment-binding hash,
  and input hashes.
- Three plan-bound `raw-tracked-worktree-v1` digests for the exact initial,
  version-written, and versioned tracked worktree states.
- Exact source SHA, dist digest, deterministic package content digest and
  algorithm, exact candidate package file digest, CLI executable
  digest/version, and safe CLI-profile binding hash.
- CLI control plane, organization, tenant, folder GUID, package/app names,
  route, public client GUID, tags, and optional environment-matched route
  verification URL.
- The pack command contains no `--base-url`, `--profile`, org, tenant, token, or
  reuse-client flag.
- Publish and deploy commands use only the reviewed target/profile fields.
- There are no execution blockers.

Planning without `--plan-output` is inspectable but cannot be executed.

## Execute

After the user explicitly approves the displayed hash:

```bash
python3.11 uipcodedappdeploy/scripts/uipcodedappdeploy.py \
  --plan /absolute/ignored/evidence/deploy-plan.json \
  --execute \
  --approved-plan-hash 'sha256:<exact-approved-plan-hash>' \
  --format json
```

Execution first revalidates the exact candidate package, initial input snapshot,
exact commit, plan-bound raw worktree bytes, and zero tracked or untracked source
drift. It rejects
assume-unchanged, skip-worktree, sparse, or other hidden index state and verifies
the type, executable mode, raw regular-file bytes, symlink target, and content of
every HEAD-tracked path recursively, including submodules with ignore disabled.
Raw checks do not apply Git clean filters, while the separate Git-object check
continues to support legitimate clean/smudge and LFS worktrees. It updates only the planned
`[project].version`, runs any planned local gates, validates the dist, then
checks the versioned input snapshot. The only permitted unstaged mutations are
the exact plan-bound `pyproject.toml` version update and, when the lock stage is
present, its exact project-version-only `uv.lock` update. Any other
build-generated, tracked, staged, submodule, or untracked drift stops execution.
It then validates the CLI executable digest/version, authenticated profile
org/tenant, and package; records the exact produced package file digest;
rechecks those exact bytes immediately before publish; publishes; deploys; and
optionally verifies HTTPS. The redacted v2.2 receipt repeats the approved plan
and release provenance hashes.

## Resume And Indeterminate Writes

For a remediated local failure:

```bash
python3.11 uipcodedappdeploy/scripts/uipcodedappdeploy.py \
  --plan /absolute/ignored/evidence/deploy-plan.json \
  --execute \
  --approved-plan-hash 'sha256:<exact-approved-plan-hash>' \
  --resume
```

- Keep plan and receipt unchanged. Any hash mismatch requires recovery from a
  trusted copy or a new plan.
- Resume skips completed local stages.
- Any interrupted or nonzero publish/deploy result is indeterminate. Inspect
  and reconcile remote state before creating a reviewed recovery plan; this
  helper blocks blind `--resume` for both running and failed external writes.
- There is no automatic rollback.

## Versioned Contracts

- `references/deployment-plan.v2.schema.json`
- `references/deployment-receipt.v2.schema.json`

Both are integrity contracts, not signatures. Exact-hash approval is required,
but the helper does not claim non-repudiation.

Contract `2.2` is intentionally incompatible with `2.1`. Existing `2.1` plans
and receipts are rejected and must be regenerated; the helper performs no silent
migration because `2.1` did not bind raw execution bytes.

## Validation

```bash
python3.11 -m unittest discover -s uipcodedappdeploy/tests -p 'test_*.py'
python3 tools/validate_repo.py
```

Unit tests stub subprocess and URL execution; they must never contact UiPath or
invoke a live publish/deploy.
