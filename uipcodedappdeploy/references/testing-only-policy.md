# Testing-only coded app deployments

This policy defines a deliberately separate deployment lane for internal,
synthetic Coded App testing. It does not relax, supersede, or provide evidence
for the governed v2.3 deployment or v1.2 recovery lanes.

## Authorization

An execution is authorized only when all of the following are true:

- The user explicitly asked to deploy the app for testing.
- The helper receives both `--testing-only` and `--execute`.
- `--testing-purpose` is non-empty and is recorded in the receipt.
- The target is exactly UiPath Alpha or Staging.

There is no testing plan and no second plan-hash approval. The helper
exclusively reserves a new receipt path and creates an automatic, atomically
updated receipt before any external write. That receipt is testing evidence
only: it is never release evidence.

Invocation validation precedes reservation: malformed or secret-bearing
arguments, an invalid output path, an unsupported CLI build, or an incomplete
target fail without a receipt. Once the new output path, exact CLI, and complete
target validate, the reservation is durable and every later handled failure is
recorded.

## Non-waivable controls

- Alpha maps only to `https://alpha.uipath.com`; Staging maps only to
  `https://staging.uipath.com`. Production and custom origins are rejected.
- Data is `synthetic_only`; internal authenticated access is required as a
  mandatory rollout-acceptance gate, and public or anonymous deployment is prohibited.
  The helper validates the local non-public configuration but does not claim to
  prove remote access mode. Its receipt keeps authentication certification
  pending until browser acceptance proves anonymous denial and named-user
  sign-in; do not report the rollout complete before that evidence exists.
- Organization, tenant, folder, OAuth client, route, package, version, profile,
  CLI executable/version, and candidate bytes are exact inputs.
- Intent is exactly `create` or `upgrade`; automatic upsert is prohibited.
- A create proves no matching deployment and an unused route before publish.
- An upgrade proves the exact deployment, system, route, current version, and
  published deploy version before and after the write. A dist upgrade also
  binds those identities before publication, rejects a non-progressing version,
  and verifies the published candidate before its single route-omitting PATCH.
- UiPath may expose the existing app title as either the package name or display
  title. Both are exact candidate inputs; the guard accepts only those two
  values and rejects every unrelated title.
- Route changes, random routes, delete/recreate, omit-and-retry, and fresh-app
  fallback are prohibited.
- A host-local atomic operation claim prevents same-host concurrent or blind
  replay. It is not distributed serialization; do not run the same candidate
  from another user or host. Create
  claims use stable remote coordinates rather than repack timestamps; exact
  candidate bytes remain fingerprinted inside the claim and receipt. Both dist
  and reconciled upgrades claim the recovery lane's exact-candidate key,
  preventing cross-lane PATCH races.
- Helper, CLI, Node, package, configuration, and guarded runtime bytes are
  revalidated after the indeterminate stage receipt is durable and immediately
  before each external write. Unknown runtime versions fail closed.
- Access tokens, client secrets, profile contents, environment dumps, commands,
  and subprocess bodies are never persisted in the receipt.
- Any timeout, interruption, non-zero write result, or ambiguous response is
  indeterminate. There is no resume or automatic retry; reconcile remote state
  and obtain a new explicit testing request.

## Waived controls

Only the following release controls are waived:

- clean branch, clean worktree, tag, and source commit as release authority;
- independent approval, protected environment, and signed receipt;
- a second exact plan-hash response;
- rebuilding or rerunning the full test suite when exact audited distribution
  bytes or an already-published reconciled candidate are supplied;
- production-only services absent from a browser-only mockup bundle.

Dirty or uncommitted source is allowed, but Git HEAD and a digest of the raw
worktree status are informational receipt fields. The deployable distribution,
package, exact `uipath.json` configuration, runtime, and target hashes remain
authoritative.

## Candidate modes

`dist` copies the supplied distribution into an isolated evidence workspace,
hashes it, and packs and validates it there. With `create`, it performs a
read-only absence guard before publication and one guarded fresh deployment.
With `upgrade`, it verifies the exact existing deployment before publication,
publishes once, verifies the exact published candidate, and performs one
route-preserving in-place upgrade against that deployment.

`reconciled` validates an existing exact recovery plan and guarded runtime,
skips build, pack, and publish, and permits only the bound in-place upgrade.
The recovery plan hash is recorded as a technical input, not as a user
approval.

## Outcomes

Receipts use one of these terminal or transitional outcomes:

- `in_progress`
- `failed_prewrite`
- `publish_indeterminate`
- `published_not_deployed`
- `deploy_indeterminate`
- `deployed_unverified`
- `succeeded_testing`

A successful receipt must state `production_eligible: false`,
`release_evidence: false`, and `data_classification: synthetic_only`.
`succeeded_testing` is a deployment-helper outcome, not proof of the complete
rollout acceptance. The receipt intentionally retains
`authentication_certification: pending_external_acceptance`; referenced assets,
anonymous denial, named-user authentication, and application behavior require
separate browser evidence before reporting the rollout complete.
