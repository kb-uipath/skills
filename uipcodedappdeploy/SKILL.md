---
name: uipcodedappdeploy
description: Plan, validate, and explicitly execute UiPath coded app deployments with exact source, dist, package, CLI, profile, route, client, and target provenance.
---

# UiPath Coded App Deploy

Use this skill for plan-first deployment of a UiPath Coded App. Planning is
local and non-mutating except for an explicitly requested plan file. Publishing
and deployment are always a separate, human-approved execution.

## Hard Boundaries

- Never deploy directly from planning arguments. Persist and display the v2.0
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
- Executable plans are staging-only: require the explicit
  `https://staging.uipath.com` control plane and exact organization and tenant
  GUIDs. Missing, defaulted, or alpha targets are blocked.
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
3. Confirm valid `pyproject.toml` and `uipath.json` manifests.
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

Review all of the following:

- Plan schema `2.0`, plan hash, deployment-binding hash, and input hashes.
- Exact source SHA, dist digest, deterministic package content digest and
  algorithm, exact candidate package file digest, CLI executable
  digest/version, and safe CLI-profile binding hash.
- CLI control plane, organization, tenant, folder GUID, package/app names,
  route, public client GUID, tags, and optional route verification URL.
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

Execution first revalidates the exact candidate package, then revalidates clean
source, exact commit, dist digest, CLI executable digest/version, authenticated
profile org/tenant, and plan inputs. It updates
the project version, runs any planned local gates, packs, verifies the
deterministic coded-app content digest, records the exact produced package file
digest, rechecks those exact bytes immediately before publish, then publishes,
deploys, and optionally verifies HTTPS. The redacted v2.0 receipt repeats the
approved plan and release provenance hashes.

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

## Validation

```bash
python3.11 -m unittest discover -s uipcodedappdeploy/tests -p 'test_*.py'
python3 tools/validate_repo.py
```

Unit tests stub subprocess and URL execution; they must never contact UiPath or
invoke a live publish/deploy.
