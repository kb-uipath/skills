# Testing-only coded app operations

Read `testing-only-policy.md` first. These commands are execution shapes, not
authorization. Run them only after the user explicitly requests an internal,
synthetic Alpha or Staging deployment in the current task. Replace every
placeholder with independently verified, non-secret input and use a new ignored
receipt path.

The helper certifies exact UiPath CLI 1.198.0 and its supported Node runtime.
Do not substitute npm's current `latest` build. There is no plan, second
approval hash, resume, automatic retry, or cross-host serialization.

## Dist create

```bash
python3.12 uipcodedappdeploy/scripts/uipcodedappdeploy_testing.py \
  --testing-only \
  --execute \
  --intent create \
  --candidate-mode dist \
  --environment alpha \
  --control-plane-url https://alpha.uipath.com \
  --org-id '<exact-org-guid>' \
  --org-name '<organization>' \
  --tenant-id '<exact-tenant-guid>' \
  --tenant-name '<tenant>' \
  --folder-key '<exact-folder-guid>' \
  --package-name '<package-name>' \
  --app-name '<display-title>' \
  --path-name '<unused-route>' \
  --client-id '<public-client-guid>' \
  --version '<candidate-version>' \
  --tags internal,synthetic-testing \
  --cli-executable /absolute/pinned/node_modules/@uipath/cli/dist/index.js \
  --cli-version 1.198.0 \
  --cli-profile '<named-profile>' \
  --node-executable /absolute/pinned/node \
  --node-version 24.13.0 \
  --project-root /absolute/project \
  --app-dist /absolute/project/dist \
  --main-file index.html \
  --content-type webapp \
  --testing-purpose 'Synthetic coded app acceptance' \
  --receipt-output /absolute/ignored/evidence/testing-receipt.json
```

## Dist upgrade

Use the dist-create command with `--intent upgrade`, the existing route, and
these additional exact inputs:

```bash
  --expected-deployment-id '<exact-deployment-guid>' \
  --expected-system-name 'ID<32-hex-characters>' \
  --expected-current-version '<currently-deployed-version>' \
  --expected-deploy-version '<new-published-candidate-number>'
```

The candidate version must progress semantically. The expected system name and
deploy version must match both the publish response and a fresh remote read.
The helper publishes once, performs one route-omitting upgrade PATCH, and
verifies the same deployment, route, system name, and new version afterward.

## Reconciled upgrade

Use `--candidate-mode reconciled --intent upgrade` with the common target,
package, app, route, client, version, tags, CLI, profile, purpose, and receipt
arguments from the dist command. Replace the dist and Node inputs with:

```bash
  --recovery-plan /absolute/ignored/evidence/upgrade-recovery-plan.json \
  --recovery-runtime-manifest /absolute/ignored/evidence/guarded-runtime.manifest.json \
  --expected-recovery-plan-hash 'sha256:<exact-technical-input-hash>' \
  --expected-deployment-id '<exact-deployment-guid>' \
  --expected-system-name 'ID<32-hex-characters>' \
  --expected-current-version '<currently-deployed-version>' \
  --expected-deploy-version '<published-candidate-number>' \
  --expected-runtime-manifest-hash 'sha256:<exact-runtime-manifest-hash>'
```

The recovery plan hash is a technical binding, not approval. This mode skips
build, pack, and publish and uses the recovery lane's exact-candidate claim key.

## Published recovery

Use only when a dist-upgrade receipt ended `publish_indeterminate` and the exact
package later became remotely queryable. The source must be an exact schema 1.1
or 1.2 receipt. A schema 1.2 source must have `recovery_source: null`; chained
recovery is rejected.

Use `--candidate-mode published-recovery --intent upgrade` with the common
target, package, app, route, client, version, tags, CLI, profile, purpose, and a
new receipt path. Add:

```bash
  --failed-testing-receipt /absolute/ignored/evidence/failed-testing-receipt.json \
  --expected-failed-receipt-hash 'sha256:<receipt-document-hash>' \
  --expected-failed-receipt-file-sha256 'sha256:<receipt-file-hash>' \
  --expected-retained-claim-hash 'sha256:<claim-document-hash>' \
  --expected-retained-claim-file-sha256 'sha256:<claim-file-hash>' \
  --expected-package-file-sha256 'sha256:<package-file-hash>' \
  --expected-source-helper-sha256 'sha256:<failed-run-helper-hash>' \
  --recovery-runtime-manifest /absolute/ignored/evidence/create-guard-runtime.manifest.json \
  --expected-runtime-manifest-hash 'sha256:<runtime-manifest-document-hash>' \
  --expected-deployment-id '<exact-deployment-guid>' \
  --expected-system-name 'ID<32-hex-characters>' \
  --expected-current-version '<currently-deployed-version>' \
  --expected-deploy-version '<published-candidate-number>'
```

The helper rehashes the source receipt, original claim, package,
configuration, runtime manifest, immutable runtime tree, CLI, and Node runtime.
It creates a separate transition claim, performs a read-only candidate guard,
and invokes exactly one route-omitting upgrade. It never republishes or changes
the original receipt or claim.

## Outcomes

Malformed or secret-bearing arguments, invalid output paths, unsupported CLI
bytes, and incomplete targets fail before receipt reservation. Later handled
failures are recorded. Any interrupted, nonzero, timed-out, or ambiguous write
becomes `publish_indeterminate` or `deploy_indeterminate`; do not rerun it.
Reconcile exact remote state and require a fresh explicit testing request.

`succeeded_testing` means only that the exact deployment, route, and local app
configuration passed technical checks. The receipt retains
`authentication_certification: pending_external_acceptance`; anonymous denial,
named-user authentication, referenced assets, and browser behavior require
separate evidence.
