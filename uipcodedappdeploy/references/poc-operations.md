# Fast POC Operations

Use this lane only when the user explicitly requests a quick POC deployment.
It is not governed release evidence, even when the target is Production.

## Configure once

Configuration provisions and verifies a private UiPath CLI `1.199.0` runtime,
checks the named login profile, resolves exactly one folder, and stores only
non-secret target bindings under `~/.uipath/poc-deploy/targets/` with mode
`0600`.

```bash
python3.12 uipcodedappdeploy/scripts/uipcodedappdeploy_poc.py configure \
  --project-root /absolute/project \
  --environment alpha \
  --profile dev \
  --folder 'Shared/POC' \
  --app-type web
```

For a Web app, `uipath.json` supplies the dedicated public client and exact
redirect route. For an Action app, `action-schema.json` is mandatory and the
route is an internal deployment binding; use `--path-name` only when the
derived app-name slug is not the intended binding. Use `--replace` only to
replace the current project's existing private target configuration.

## Deploy

The helper always runs the declared package-manager `build` script, copies and
hashes the resulting dist, resolves the next unused SemVer, packs, publishes
once, and performs one guarded create or in-place upgrade.

```bash
python3.12 uipcodedappdeploy/scripts/uipcodedappdeploy_poc.py deploy \
  --project-root /absolute/project \
  --intent create \
  --data-classification synthetic \
  --execute
```

- Add `--production-execute` for Production.
- Add `--customer-data-approved` whenever the classification is `customer`.
- Production customer-data execution requires all three flags:
  `--execute --production-execute --customer-data-approved`.
- `create` proves no exact deployment and an available route. `upgrade` binds
  one exact deployment and omits `routingName` from the PATCH.
- Action success proves remote app metadata and version only. Rendering,
  submission, outcomes, and write-back remain pending Action Center checks.

## Published recovery

Never repeat `deploy` after `publish_indeterminate` or
`published_not_deployed`. Reconcile and deploy the already-published exact
candidate with:

```bash
python3.12 uipcodedappdeploy/scripts/uipcodedappdeploy_poc.py recover-published \
  --receipt /absolute/failed-poc-receipt.json \
  --execute
```

Repeat the Production and customer-data authorization flags when applicable.
Recovery never builds, packs, or publishes. It refuses chained recovery,
changed evidence, changed target state, and replayed candidate claims.

## Deploy-indeterminate recovery

Never repeat `deploy` after `deploy_indeterminate`. First reconcile that the
exact deployment still reports the source receipt's prior version and that the
published candidate resolves uniquely. Preserve a copy of the exact source
helper whose digest is recorded in the failed receipt, then run:

```bash
python3.12 uipcodedappdeploy/scripts/uipcodedappdeploy_poc.py recover-deploy-indeterminate \
  --receipt /absolute/deploy-indeterminate-receipt.json \
  --source-helper /absolute/source-uipcodedappdeploy-poc.py \
  --receipt-output /absolute/new-deploy-recovery-receipt.json \
  --execute
```

This command supports exact upgrades only. It revalidates the source receipt,
source helper, original retained claim, package, dist, app configuration,
runtime, target, deployment ID/current version/route, and published system and
deploy-version identity. It creates a separate atomic transition claim and
performs one route-omitting guarded upgrade. It never rewrites the source
receipt or original claim and never rebuilds, packs, or publishes. If this
recovery becomes indeterminate, do not retry it.

## Evidence boundary

Receipts follow `deployment-poc-receipt.v1.schema.json`, omit commands,
environment values, subprocess output, and secrets, and always set
`production_eligible: false` and `release_evidence: false`. Any ambiguous
publish or deploy remains indeterminate and is never retried automatically.
