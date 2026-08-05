---
name: uipcodedappdeploy
description: Plan, validate, and explicitly execute UiPath coded app deployments with exact source, dist, package, CLI, profile, route, client, and target provenance.
---

# UiPath Coded App Deploy

Use this skill for plan-first deployment of a UiPath Coded App. Planning is
local and non-mutating except for an explicitly requested plan file. Publishing
and deployment are always a separate, human-approved execution.

## Hard Boundaries

- Never deploy directly from planning arguments. Persist and display the v2.3
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

- Plan schema `2.3`, explicit environment, plan hash, deployment-binding hash,
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
- When package and display names differ, the plan includes a local app-config
  binding stage after publish. It verifies the CLI-created package, version,
  type, tenant-feed mode, and system name; atomically binds the approved display
  title; records the exact config digest; and deploys without the CLI's
  ambiguous `--name` flag. When the names are identical, deploy uses the exact
  package name directly.
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
rechecks those exact bytes immediately before publish; publishes; binds and
revalidates the CLI-created app config when package/display names differ;
deploys; and optionally verifies HTTPS. The redacted v2.3 receipt repeats the approved plan
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

## Existing-App Route-Collision Recovery

UiPath CLI 1.198.0 includes `routingName` in an existing-app upgrade PATCH when
`--path-name` is supplied. Some environments reject even the unchanged route as
`routing name must be unique`. Do not republish, delete the existing app, change
the route, hand-edit `.uipath/app.config.json`, or direct-run a modified deploy
command.

Use `uipcodedappdeploy_recover.py` only after read-only reconciliation proves:

- the prior deployment succeeded and owns the exact route;
- the new package and app registration succeeded;
- the failed deploy receipt remains indeterminate and blocks blind resume;
- the existing deployment ID, system name, route, folder, client, target,
  profile, CLI, source, and package digests are known; and
- the server failure is exactly the existing-app HTTP 400 route-collision
  signature.

CLI 1.198.0's ordinary deploy command is not upgrade-only: a missed title
lookup enters its fresh-deploy branch. The recovery helper therefore refuses to
run the stock runtime. First create an isolated copy of `node_modules` with a
deterministic, exact-version patch that adds an exact deployment guard and a
read-only target probe. The isolated runtime refuses every `codedapp deploy`
invocation unless all exact-recovery fields are present; it cannot be used as
a general deployment CLI:

```bash
python3.12 uipcodedappdeploy/scripts/uipcodedappdeploy_recover.py \
  --prepare-runtime-from-cli /absolute/source/node_modules/@uipath/cli/dist/index.js \
  --node-executable /absolute/path/to/node \
  --runtime-output /absolute/ignored/evidence/guarded-runtime \
  --runtime-manifest-output /absolute/ignored/evidence/guarded-runtime.manifest.json \
  --format json
```

Preparation requires `@uipath/codedapp-tool` 1.198.0 at its exact published
git head and source digest. Every patch anchor must match once. The resulting
runtime tree, original and patched tool bytes, both package manifests, patch
contract, preparer, and core helper are hash-bound. The helper resolves Node.js
to one absolute executable and binds that path, its SHA-256, and its exact
version, normalized as SemVer without a leading `v`. Syntax checks, self-tests,
guards, and recovery execution invoke those exact bytes instead of relying on
the CLI's `#!/usr/bin/env node` shebang or ambient `PATH`. Preparation also
launches the copied CLI twice without a complete guard, proving both ordinary
deploy and bare
`--recovery-verify-only` fail before network activity.

Recovery subprocesses inherit only `HOME`. They receive fixed values for
`PATH=/usr/bin:/bin:/usr/sbin:/sbin`, `LANG=C`, `LC_ALL=C`, `TERM=dumb`,
`NO_COLOR=1`, `UIPATH_TELEMETRY_DISABLED=true`, and
`UIPATH_CLI_DISABLE_VERSION_SYNC=1`. Disabling CLI version sync is part of the
network boundary: it prevents the CLI's daily pre-command update check from
making an unreviewed request, changing installed bytes, or re-executing a
different CLI before the guarded command is parsed. The helper rejects ambient
Node, dynamic-loader, TLS/OpenSSL, debug, proxy, UiPath target/token, and
feedback-endpoint overrides, including lowercase proxy variants; the complete,
ordered policy is bound in `execution.environment_policy`. This intentionally
means proxy-dependent recovery is blocked until a separately reviewed policy
exists rather than inheriting an unapproved proxy.

The runtime output and manifest output must be distinct, non-overlapping paths
outside the complete source project, and the manifest must remain outside
the copied runtime root. Keep both outputs in an ignored evidence location.
Never patch the release checkout's original `node_modules` in place.

Persist a reconciliation JSON document whose raw observations include absolute
paths and SHA-256 digests, then generate an exact-upgrade plan:

```bash
python3.12 uipcodedappdeploy/scripts/uipcodedappdeploy_recover.py \
  --project-root /absolute/path/to/failed-release/source \
  --prior-successful-plan /absolute/evidence/prior-plan.json \
  --prior-successful-receipt /absolute/evidence/prior-plan.json.receipt.json \
  --prior-successful-app-config /absolute/evidence/prior-source/.uipath/app.config.json \
  --failed-plan /absolute/evidence/failed-plan.json \
  --failed-receipt /absolute/evidence/failed-plan.json.receipt.json \
  --reconciliation-evidence /absolute/evidence/reconciliation-evidence.json \
  --recovery-runtime-manifest /absolute/evidence/guarded-runtime.manifest.json \
  --plan-output /absolute/evidence/upgrade-recovery-plan.json \
  --format json
```

Review that the plan contains only an atomic execution claim, reconciliation,
a pre-upgrade read-only guard, a last-moment runtime hash barrier, one upgrade,
a post-upgrade remote identity/version guard, exact-route verification, and
local metadata inspection. It must contain neither `pack` nor `publish`. The
upgrade command retains the approved `--path-name` as a fail-safe, but the
guarded runtime omits `routingName` from
the PATCH only after it resolves the exact deployment ID, current route,
current version, candidate system name, and candidate deploy version. A
missing or mismatched lookup throws before the fresh-deploy branch. The
execution-time pre-guard performs the same checks without mutation before the
receipt enters the external-write stage. The post-guard must then prove the
same deployment ID, route, and system name now report the candidate version;
route availability and local app metadata alone are not sufficient.

The final runtime hash check and Node process creation are separate operating-
system operations, so a small local concurrent-update window remains between
validation and spawn. Do not mutate or replace the bound runtime or Node binary
during execution. This recovery path is suitable only for a controlled,
single-operator staging repair; it is not a signed, atomic production-release
boundary.

Execute only after a human approves the new recovery plan hash:

```bash
python3.12 uipcodedappdeploy/scripts/uipcodedappdeploy_recover.py \
  --plan /absolute/evidence/upgrade-recovery-plan.json \
  --execute \
  --approved-plan-hash 'sha256:<exact-approved-recovery-plan-hash>' \
  --format json
```

Execution creates an atomic claim before any recovery-side remote operation.
The claim is stored under the preserved `HOME` and scoped to the exact
environment, organization, tenant, folder, deployment ID, system name, deploy
version, and candidate version. Exclusive creation means another local process
cannot claim the same exact candidate concurrently; an existing claim blocks
execution rather than being overwritten.

For a handled pre-upgrade guard or runtime-barrier failure, the helper verifies
the claim's exact bytes, removes it, and records the release in the receipt so a
newly reviewed plan can be attempted safely. Once the upgrade stage starts, the
claim remains in place after success and after any failed, interrupted, or
otherwise ambiguous result. A retained claim is deliberate evidence that the
exact candidate must not be executed again.

A hard crash can leave a stale claim without a complete receipt update. There
is no automatic stale-claim cleanup, and deleting the file merely to unblock a
retry is prohibited. Reconcile the exact remote deployment first. Only after
that evidence is reviewed may an operator manually archive the original claim
with its digest, plan, reconciliation evidence, reviewer, timestamp, and
rationale in an audited location. Then generate and approve a new plan; never
reuse the old plan or treat archival as proof that the prior upgrade did not
run.

Recovery has no resume mode. Any interrupted or nonzero upgrade is
indeterminate and requires fresh remote reconciliation plus a new plan. A
route or metadata failure after a successful upgrade is recorded as
`deployed_unverified`; never redeploy that plan. A successful helper receipt
proves the bound exact-upgrade operation and route availability only; browser
authentication and application behavior remain separate acceptance gates.

## Versioned Contracts

- `references/deployment-plan.v2.schema.json`
- `references/deployment-receipt.v2.schema.json`
- `references/deployment-recovery-plan.v1.schema.json`
- `references/deployment-recovery-receipt.v1.schema.json`

Both are integrity contracts, not signatures. Exact-hash approval is required,
but the helper does not claim non-repudiation.

Contract `2.3` is intentionally incompatible with `2.2`. Existing `2.2` plans
and receipts are rejected and must be regenerated; the helper performs no silent
migration because `2.2` could not preserve a distinct package lookup name and
display title through UiPath CLI 1.198.0.

## Validation

```bash
python3.11 -m unittest discover -s uipcodedappdeploy/tests -p 'test_*.py'
python3 tools/validate_repo.py
```

Unit tests stub subprocess and URL execution; they must never contact UiPath or
invoke a live publish/deploy.
