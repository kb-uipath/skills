# uipcodedappdeploy

Deploy UiPath Coded Apps through one of three deliberately separate lanes.

| Lane | Contract | Authorization | Intended use |
| --- | --- | --- | --- |
| Governed release | Plan/receipt v2.3 | Exact reviewed `plan_hash` | Reviewable Alpha/Staging release candidate |
| Exact upgrade recovery | Plan/receipt v1.2 | Exact reviewed recovery hash | Reconciled route-collision repair |
| Testing-only | Automatic receipt v1.0 | Explicit request plus `--testing-only --execute` | Internal synthetic Alpha/Staging testing |

Production targets are rejected in every current lane. Testing receipts are
explicitly ineligible as production release evidence.

## Runtime And Dependencies

- Python 3.12.
- UiPath CLI exactly `1.198.0`, supplied as an absolute executable path.
- A named UiPath CLI profile authenticated to the exact target organization and
  tenant.
- Node.js only through the pinned and hash-bound runtime used by the selected
  lane.

The helper does not accept access tokens or client secrets. Authentication is
resolved by the named CLI profile, and receipts store only a safe profile hash.

## Inputs

All lanes require explicit Alpha or Staging target identifiers, package and app
names, route, public client ID, CLI path/version/profile, and an ignored output
path. Governed release additionally requires exact source and package evidence;
recovery requires its exact reconciliation plan/runtime; testing requires a
plain-language synthetic testing purpose plus either exact built distribution
bytes or an exact recovery plan.

The versioned input/output contracts are plan/receipt v2.3 for governed release,
plan/receipt v1.2 for recovery, and automatic receipt v1.0 for testing-only.

## Prompt

```text
Use $uipcodedappdeploy to deploy this UiPath Coded App. Classify the request as
governed release, exact recovery, or explicit testing-only deployment; keep the
governed lane as the default when intent or environment is ambiguous. Bind the
exact target, route, profile, CLI, configuration, and candidate bytes, stop on
remote drift or indeterminate writes, and retain the resulting receipt.
```

## Runnable Example

The governed and testing commands below are complete runnable shapes. Replace
every bracketed value with verified non-secret input, use ignored evidence
paths, and never paste profile credentials into arguments.

## Governed v2.3

The governed helper binds:

- the exact Alpha or Staging control plane and verification host suffix;
- organization, tenant, folder, route, public OAuth client, tags, CLI bytes,
  CLI version, and safe named-profile binding;
- exact source commit, raw tracked-worktree states, dist content, candidate
  package content, and candidate file bytes;
- package lookup name separately from the display title; and
- an allowlisted stage sequence plus a human-approved plan hash.

Version 2.3 supersedes 2.2 because 2.2 could not safely preserve a distinct
package lookup name and display title through UiPath CLI 1.198.0. Regenerate
2.2 artifacts; never hand-migrate them.

Generate and review a plan:

```bash
python3.12 uipcodedappdeploy/scripts/uipcodedappdeploy.py \
  --project-root /absolute/project \
  --set-version 0.1.0 \
  --environment alpha \
  --control-plane-url https://alpha.uipath.com \
  --org-id '<org-guid>' \
  --org-name '<organization>' \
  --tenant-id '<tenant-guid>' \
  --tenant-name '<tenant>' \
  --folder-key '<folder-guid>' \
  --package-name '<package>' \
  --app-name '<display-title>' \
  --path-name '<route>' \
  --client-id '<public-client-guid>' \
  --tags governance,internal \
  --source-sha '<full-commit-sha>' \
  --package-digest 'sha256:<content-digest>' \
  --cli-executable /absolute/pinned/uip \
  --cli-version 1.198.0 \
  --cli-profile '<profile>' \
  --plan-output /absolute/ignored/deploy-plan.json \
  --format json
```

Execute only after approval of the displayed hash:

```bash
python3.12 uipcodedappdeploy/scripts/uipcodedappdeploy.py \
  --plan /absolute/ignored/deploy-plan.json \
  --execute \
  --approved-plan-hash 'sha256:<exact-approved-hash>' \
  --format json
```

Interrupted or nonzero external writes are indeterminate. Governed resume is
allowed only for determinate local stages; it is blocked for publish/deploy.

## Exact route-collision recovery v1.2

UiPath CLI 1.198.0 can resend an unchanged `routingName` on an existing-app
PATCH, which some environments reject as `routing name must be unique`. Never
randomize the route, omit the route in a stock retry, delete/recreate the app,
republish an already-published candidate, or infer remote state from local
`.uipath/app.config` alone.

After authoritative reconciliation, `uipcodedappdeploy_recover.py` creates an
isolated exact-version runtime. It proves the deployment ID, system name,
current version, route, and published deploy version; prevents the fresh-create
branch; and omits `routingName` only from the one guarded PATCH. A second guard
proves the same deployment now reports the candidate version.

Recovery requires its own reviewed v1.2 plan and exact approval hash. It has no
resume. The complete preparation, evidence, plan, and execution commands are in
`uipcodedappdeploy/SKILL.md`.

## Testing-only v1.0

The testing helper restores one-step deployment for a narrow class of work
without weakening either governed lane. Read
`uipcodedappdeploy/references/testing-only-policy.md` first.

It is allowed only when:

- the user explicitly asks for testing deployment;
- both `--testing-only` and `--execute` are present;
- the target is exactly Alpha or Staging;
- data is synthetic and the app remains internal/authenticated; and
- exact target, CLI, profile, route, client, candidate bytes, and automatic
  receipt output are supplied.

Supported matrices:

- `dist/create` copies and hashes a built dist, produces an isolated package,
  proves that both the deployment and route are absent before publish, then
  performs one fresh deployment.
- `reconciled/upgrade` consumes an exact v1.2 recovery plan/runtime, skips pack
  and publish, and upgrades only the named deployment in place.

Example fresh test deployment from exact built distribution bytes:

```bash
python3.12 uipcodedappdeploy/scripts/uipcodedappdeploy_testing.py \
  --testing-only \
  --execute \
  --intent create \
  --candidate-mode dist \
  --environment alpha \
  --control-plane-url https://alpha.uipath.com \
  --org-id '<org-guid>' \
  --org-name '<organization>' \
  --tenant-id '<tenant-guid>' \
  --tenant-name '<tenant>' \
  --folder-key '<folder-guid>' \
  --package-name '<package>' \
  --app-name '<display-title>' \
  --path-name '<unused-route>' \
  --client-id '<public-client-guid>' \
  --version '<candidate-version>' \
  --tags internal,synthetic-testing \
  --cli-executable /absolute/pinned/node_modules/@uipath/cli/dist/index.js \
  --cli-version 1.198.0 \
  --cli-profile '<profile>' \
  --node-executable /absolute/pinned/node \
  --node-version 24.13.0 \
  --project-root /absolute/project \
  --app-dist /absolute/project/dist \
  --main-file index.html \
  --content-type webapp \
  --testing-purpose 'Synthetic coded app acceptance' \
  --receipt-output /absolute/ignored/testing-receipt.json
```

Example reconciled test upgrade:

```bash
python3.12 uipcodedappdeploy/scripts/uipcodedappdeploy_testing.py \
  --testing-only \
  --execute \
  --intent upgrade \
  --candidate-mode reconciled \
  --environment alpha \
  --control-plane-url https://alpha.uipath.com \
  --org-id '<org-guid>' \
  --org-name '<organization>' \
  --tenant-id '<tenant-guid>' \
  --tenant-name '<tenant>' \
  --folder-key '<folder-guid>' \
  --package-name '<package>' \
  --app-name '<display-title>' \
  --path-name '<route>' \
  --client-id '<public-client-guid>' \
  --version '<candidate-version>' \
  --tags internal,synthetic-testing \
  --cli-executable /absolute/pinned/node_modules/@uipath/cli/dist/index.js \
  --cli-version 1.198.0 \
  --cli-profile '<profile>' \
  --recovery-plan /absolute/ignored/upgrade-recovery-plan.json \
  --recovery-runtime-manifest /absolute/ignored/guarded-runtime.manifest.json \
  --expected-recovery-plan-hash 'sha256:<exact-technical-input-hash>' \
  --expected-deployment-id '<exact-deployment-guid>' \
  --expected-system-name 'ID<32-hex-characters>' \
  --expected-current-version '<currently-deployed-version>' \
  --expected-deploy-version '<published-candidate-number>' \
  --expected-runtime-manifest-hash 'sha256:<exact-runtime-manifest-hash>' \
  --testing-purpose 'Synthetic browser mockup acceptance' \
  --receipt-output /absolute/ignored/testing-receipt.json
```

There is no plan or second approval hash. Before external writes, the helper
exclusively reserves the receipt and creates a durable host-local, home-scoped
operation claim. It is not cross-host serialization, so the same candidate must
not be run concurrently by another user or machine. Dist/create uses stable remote coordinates so repacking cannot evade a
retained indeterminate claim; reconciled/upgrade atomically uses the recovery
lane's exact-candidate claim key so the two lanes cannot race one PATCH. The
receipt records exact artifact/configuration hashes, informational Git state,
policy waivers, and these possible outcomes:

Malformed or secret-bearing arguments, an invalid receipt path, an unsupported
CLI build, or an incomplete target are rejected before attempt reservation and
therefore produce no receipt. After the output path, pinned CLI, and complete
target validate, every later handled failure is recorded.

- `failed_prewrite`
- `publish_indeterminate`
- `published_not_deployed`
- `deploy_indeterminate`
- `deployed_unverified`
- `succeeded_testing`

The claim is released only for a handled pre-write failure. Once a write may
have occurred, it remains as replay protection. There is no resume or automatic
retry. Reconcile remote state and require a fresh explicit testing request.
The helper revalidates exact helper, CLI, Node, package, configuration, and
guarded-runtime bytes after the indeterminate stage receipt is durable and
immediately before each write. Unknown runtime versions fail closed.

`succeeded_testing` certifies only the helper's exact deployment, route, and
local app-configuration checks. The receipt intentionally leaves
`authentication_certification` as `pending_external_acceptance`; anonymous
denial, named-user authentication, referenced assets, and browser behavior must
be certified separately before the rollout is reported complete.

## Contracts

- `uipcodedappdeploy/references/deployment-plan.v2.schema.json`
- `uipcodedappdeploy/references/deployment-receipt.v2.schema.json`
- `uipcodedappdeploy/references/deployment-recovery-plan.v1.schema.json`
- `uipcodedappdeploy/references/deployment-recovery-receipt.v1.schema.json`
- `uipcodedappdeploy/references/deployment-testing-receipt.v1.schema.json`
- `uipcodedappdeploy/references/testing-only-policy.md`

Hashes detect change; they are not signatures or proof of approver identity.
The automatic testing receipt additionally states
`production_eligible: false`, `release_evidence: false`, and
`data_classification: synthetic_only`.

## Failure Recovery

| Failure | Required response |
| --- | --- |
| Local input, CLI, profile, target, artifact, or guard mismatch | No external write; correct inputs and start a new invocation. |
| Publish fails, times out, or is interrupted | Mark indeterminate; inspect remote package state; never blindly republish. |
| Deploy fails, times out, or is interrupted | Mark indeterminate; reconcile exact deployment and route; never retry as a new app. |
| Route or post-deploy metadata verification fails | Treat as deployed but unverified; inspect the exact app before any new request. |
| Existing execution claim or receipt | Stop; do not delete it merely to unblock replay. |

There is no automatic rollback, deletion, route change, or package cleanup.

## Safety

- Treat governed release as the default unless the user explicitly requests a
  synthetic internal Alpha/Staging test.
- Never bypass exact create-versus-upgrade intent or remote identity guards.
- Never retry an indeterminate publish/deploy, mutate the route, or
  delete/recreate an occupied app.
- Never put bearer tokens, secrets, environment dumps, or unredacted service
  responses in arguments, logs, plans, or receipts.
- Never describe a testing receipt as signed, production eligible, release
  evidence, or customer-data approval.

## Data Classification And Retention

Testing-only inputs and app data must be synthetic. Governed/recovery evidence
may contain internal deployment metadata and must remain in ignored,
access-controlled evidence storage. Retain claims and indeterminate receipts
until remote reconciliation is complete; retain successful receipts according
to the release record policy. Do not retain credentials, raw authentication
responses, or unredacted environment state.

## Known limitations

- UiPath CLI 1.198.0 generates nondeterministic NuGet envelope data. Governed
  and testing helpers retain both normalized coded-app content and exact file
  digests.
- CLI login status proves the reported organization and tenant, not all
  effective permissions.
- Route availability does not prove authenticated application behavior; that
  remains a separate acceptance test.
- Testing-only deployment is not production certification, even when it
  succeeds.

## Certification Status

Status: **Maintainer-verified deployment helper; live target acceptance remains
per deployment.** Unit tests certify fail-closed argument, artifact, receipt,
claim, and recovery boundaries using synthetic fixtures. They do not certify a
UiPath tenant, effective permissions, authenticated application behavior, or
production readiness.

## Last Verified

Last verified: **2026-08-05**.

## Validation

```bash
python3.12 -m unittest discover -s uipcodedappdeploy/tests -p 'test_*.py'
python3 tools/validate_repo.py
```

Unit tests stub subprocess and network activity. Live testing must use
synthetic data, exact nonproduction targets, internal authentication, remote
state reconciliation, and retained automatic receipts.
