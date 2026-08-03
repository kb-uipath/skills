# uipcodedappdeploy

Create a reviewable, hash-bound release plan before packaging, publishing, and
deploying a UiPath Coded App with a pinned native `uip` CLI.

| Field | Value |
| --- | --- |
| Skill name | `uipcodedappdeploy` |
| Plan contract | `uipcodedappdeploy.plan` v2.2 |
| Receipt contract | `uipcodedappdeploy.receipt` v2.2 |
| Result contract | `uipcodedappdeploy.result` v1.0 |
| Certification status | Offline hardened; live target certification is per release |
| Last verified | 2026-08-03 |

## Why v2.2 Exists

The v1 helper could emit authentication flags that `codedapp pack` does not
support, relied on whichever `uip` happened to be on `PATH`, and did not bind
the route, public client, tags, source commit, dist, or package into the
approval artifact. That was not a defensible release control.

Plan v2.0 removed authentication from pack and bound the release artifacts.
Plan v2.1 additionally makes the nonproduction environment explicit and binds
it to an allowlisted control plane and verification-host suffix. Alpha support
therefore does not relax the staging guard or make production addressable.

Plan v2.2 closes a clean-filter bypass in v2.1. Git status and Git object hashes
can both report clean when a clean filter maps different raw worktree bytes to
the same object. v2.2 separately binds the raw tracked worktree at the initial,
version-written, and versioned stages, including executable modes, symlink
targets, and recursively checked-out submodules. This still supports legitimate
clean/smudge filters and LFS because the raw approved worktree bytes—not the Git
object representation—are the comparison baseline.

Plan v2.2 binds:

- the absolute CLI executable, executable digest, and exact CLI SemVer;
- a named profile through a safe hash of profile name, environment,
  control-plane origin, organization ID, and tenant ID;
- `staging` only to `https://staging.uipath.com` and
  `*.staging.uipath.host`, or `alpha` only to `https://alpha.uipath.com` and
  `*.alpha.uipath.host`;
- exact organization, tenant, folder GUID, route, public OAuth client GUID, and
  sorted deployment tags;
- source commit SHA, deterministic dist digest, deterministic coded-app package
  content digest, and exact candidate package file digest;
- the input manifests before and after the planned version update;
- deterministic `raw-tracked-worktree-v1` digests for all three source stages;
- an allowlisted stage sequence and an exact human-approved plan hash.

## Runtime And Dependencies

- Python 3.11 or later; no third-party Python runtime dependency.
- Valid UTF-8 `pyproject.toml` and `uipath.json`.
- A built Coded App dist and a prepacked local candidate for the exact planned
  version.
- A pinned UiPath CLI with the Coded App tool installed.
- A named authenticated CLI profile for the reviewed target.
- `uv` and npm only when their stages are enabled.

Planning does not authenticate, run project/release commands, or contact UiPath.
It runs only read-only Git inspection needed to bind the raw tracked worktree,
and may write only an explicitly named plan file.

## Inputs

An executable plan requires:

- canonical project root and a greater SemVer;
- explicit `staging` or `alpha` environment and its exact CLI control-plane
  origin;
- exact organization and tenant GUIDs plus the exact folder GUID;
- package name, display title, lowercase route slug, public client GUID, and
  non-empty sorted tags;
- full source commit SHA;
- current deterministic dist digest;
- deterministic candidate `.nupkg` coded-app content digest and exact candidate
  file digest;
- absolute CLI executable, executable digest, exact version, and named profile;
- optional route verification URL on the selected environment's exact UiPath
  host suffix.

The SDK/API origin used by the browser is not a helper input and must remain a
separate runtime configuration value.

## Prompt

```text
Use $uipcodedappdeploy to build an exact source/dist/package/CLI/environment-
bound v2.2 deployment plan. Display the persisted plan and hash, and do not
execute until I approve that exact hash.
```

## Runnable Example

See the complete plan and execution commands in
`uipcodedappdeploy/SKILL.md`. Run them from the repository root with reviewed
values; never copy the illustrative GUIDs or route labels into a real release.

## Plan And Receipt Contracts

The published JSON Schemas are:

- `uipcodedappdeploy/references/deployment-plan.v2.schema.json`
- `uipcodedappdeploy/references/deployment-receipt.v2.schema.json`

Plan files are written atomically with mode `0600`. The plan hash covers every
normalized field, command, blocker, input hash, and release binding. A loaded
plan is rebuilt from its structured fields and rejected if its stage sequence
has been edited.

Receipts are also mode `0600`. They contain no commands, process environment variables,
subprocess output, response bodies, access tokens, or detailed errors. They
repeat the selected deployment environment, exact approved plan hash,
deployment-binding hash, CLI/profile
hashes, source SHA, dist digest, package content digest and algorithm, candidate
file digest, and the exact package file digest verified immediately before
publish.

The `2.2` plan and receipt contracts are intentionally incompatible with `2.1`.
All `2.1` plans and receipts must be regenerated. There is no silent migration,
because adding a digest after approval cannot prove what raw bytes were reviewed.

Hashes detect changes; they are not signatures or proof of approver identity.

## Execution Order

1. Require `--plan`, `--execute`, and the exact
   `--approved-plan-hash`.
2. Revalidate the immutable plan, input hashes, blockers, and exact candidate
   package file/content digests before any project write.
3. Verify the current dist before any version or receipt write when the build
   stage is disabled.
4. Atomically update `[project].version`.
5. Run planned lock, test, and build stages.
6. Verify dist, clean tracked source, exact source SHA, the exact plan-bound raw
   execution bytes, CLI executable digest and version, and CLI profile org/tenant.
7. Run `codedapp pack` with no authentication flags.
8. Compare the produced package's deterministic coded-app content digest with
   the approved candidate, record its exact raw file digest, and stop before
   external writes if the content differs.
9. Recheck the exact recorded package bytes and publish with the reviewed
   profile/control plane.
10. Fresh-deploy with exact path, client, tags, folder, org, and tenant.
11. Optionally verify the HTTPS route.

## Failure And Recovery

| Failure | Required response |
| --- | --- |
| Plan, approval, input, source, CLI, profile, or dist mismatch | No external write; regenerate from the corrected source/binding. |
| Package content mismatch or exact pre-publish file drift | Do not publish. Rebuild the candidate or restore the audited execution package, then generate a new plan when required. |
| Local stage failure | Fix locally and resume with the same plan and approval hash if the receipt is determinate. |
| Publish/deploy command fails or is interrupted | Treat the result as indeterminate, reconcile remote state, and create a reviewed recovery plan. Blind `--resume` is prohibited. |
| Verification fails | Deployment may already exist; reconcile the route before resume. |
| Plan/receipt hash mismatch | Restore a trusted artifact or regenerate; never hand-edit retained release evidence. |

There is no automatic rollback, deletion, or package cleanup.

## Safety

The plan is an authorization boundary, not a convenience log. Missing,
implicit, mismatched, or production environments block execution. Exact
organization/tenant bindings remain mandatory, pack receives no authentication
flags, package content or exact-file drift stops before publication, and
indeterminate external writes require remote reconciliation.

## Data Classification And Retention

- Never place secrets, tokens, confidential profile files, or signed URLs in a
  plan.
- Store plans and receipts as internal release evidence in an ignored,
  access-controlled directory.
- Absolute local paths, tenant/folder/client IDs, and package names are internal
  operational metadata.
- Remove obsolete failed artifacts after the owning release-recovery window.
- The helper emits no telemetry of its own.

## Known Limitations

- `uipath.json` validation is structural rather than a complete product-schema
  validation.
- UiPath CLI 1.198.0 produces nondeterministic NuGet envelope bytes and generated
  project GUIDs. The content-v1 digest normalizes only those known generated
  fields while hashing every coded-app content file and the package manifest;
  the exact execution `.nupkg` SHA-256 is still retained and rechecked before
  publication.
- CLI status proves the named profile's reported organization and tenant, not
  the complete effective permission set. Release-specific RBAC checks remain
  mandatory.
- Anonymous HTTPS verification does not prove authenticated app startup or
  functional acceptance.
- One staging or alpha run is not production certification.

## Certification Status

The helper is offline-hardened against its v2.2 contracts and UiPath CLI 1.198.0
command surface. Each live staging or alpha target still requires its own
authenticated RBAC, route, package, and functional acceptance evidence.
Production targets are rejected by this helper.

## Validation

```bash
python3.11 -m unittest discover -s uipcodedappdeploy/tests -p 'test_*.py'
python3 tools/validate_repo.py
```

The unit suite stubs subprocess and network execution. Live certification must
use synthetic data, an isolated nonproduction target, a dedicated
least-privilege identity, explicit plan-hash approval, remote-state inspection,
and retained release receipts.
