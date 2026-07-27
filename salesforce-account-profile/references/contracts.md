# Contracts And Limits

Contract sets: `salesforce-account-profile/v1` and `salesforce-account-profile/v2`
Classification: confidential
Last verified: 2026-07-27

The v1 command contracts remain compatible advanced primitives. The v2 conversational
orchestrator owns their transport values and exposes only business decisions to the user.

## Public V2 Commands

All inputs reject unknown keys. JSON input is limited to 1 MiB. A path input must be a regular,
non-symlink file with exact mode `0600`; it is opened with no-follow semantics and rechecked
after reading. Output files are created once with `0600`; existing paths are not overwritten.

| Command | Request schema | Result schema |
| --- | --- | --- |
| `doctor` | `salesforce-account-profile-doctor-request/v2` | `salesforce-account-profile-doctor-result/v2` |
| `start` | `salesforce-account-profile-start-request/v2` | `salesforce-account-profile-start-result/v2` |
| `continue` | `salesforce-account-profile-continue-request/v2` | `salesforce-account-profile-continue-result/v2` |
| `status` | `salesforce-account-profile-status-request/v2` | `salesforce-account-profile-status-result/v2` |
| `abort` | `salesforce-account-profile-abort-request/v2` | `salesforce-account-profile-abort-result/v2` |

Codex owns these transport contracts. The user sees only the rendered message, enriched
Account chooser, exact family manifest, and business next action. `start` defaults to the
selected-account `pipeline` preset and rendered output. `continue` accepts exactly the
decision expected by the stored state.

The state machine is `new → org_confirmation → account_resolution → account_choice? →
family_approval? → executing → complete`. `status` returns a redacted resumable summary;
`abort`, successful completion, and expiry delete the private session.

The allowed next actions are `confirm_org_and_plan`, `choose_account`,
`approve_family_scope`, `narrow_query`, `reauthenticate`, `request_permissions`, and
`cancel`. The user never supplies a plan, receipt, digest, schema version, or file path.

## Administrative Readiness Commands

These commands are deliberately excluded from the profile conversation. Codex operates
them on behalf of an authorized administrator during one-time readiness work, carrying
private stdin or an exact-mode `0600` file invisibly.

| Command | Request schema | Result schema |
| --- | --- | --- |
| `prepare-sandbox-certification` | `salesforce-account-profile-sandbox-certification-scope-request/v1` | `salesforce-account-profile-sandbox-certification-scope-result/v1` |
| `certify-sandbox` | `salesforce-account-profile-sandbox-certification-request/v1` | `salesforce-account-profile-sandbox-certification-result/v1` |
| `prepare-production-approval` | `salesforce-account-profile-production-approval-scope-request/v1` | `salesforce-account-profile-production-approval-scope-result/v1` |
| `approve-production` | `salesforce-account-profile-production-approval-request/v1` | `salesforce-account-profile-production-approval-result/v1` |

Each preparation result contains a confidential, 30-minute approval scope. Sandbox scope
binds the enrolled org fingerprint, pinned runtime, certification-critical package,
metadata compatibility, field map, suite version, and complete synthetic fixture-manifest
digest. Its authorization is an Ed25519-signed assertion from the configured sandbox
certifier key. The signed payload binds issuer, key ID, subject digest, exact role,
audience, opaque reference, scope digest, nonce, issue time, and expiry.

Production scope resolves one current sandbox receipt internally by evidence digest and
re-attests that sandbox before binding it to the exact production fingerprint, runtime,
package, metadata, and field map. Administrator and risk-owner assertions must be signed by
different trusted role keys, represent different subjects and references, occur inside the
scope window, and bind the identical audience and scope. Assertions are atomically consumed
by nonce before certification work and cannot be replayed. Production approval performs
zero data queries.

Final results expose only readiness state, version/count metadata, verification time, and a
self-validating evidence digest. They do not expose aliases, usernames, org identifiers,
hosts, Salesforce record IDs, local paths, approval references, tokens, or raw CLI output.
See [certification.md](certification.md) for the complete runbook.

## Advanced V1 Commands

These remain compatible internal primitives; they are not the normal user journey.
The query-capable `resolve` and `profile` commands require an explicit enrolled alias whose
private registry entry is currently `sandbox_read_certified` or
`production_read_approved`. They re-attest the pinned runtime and certification-critical
package before execution, compare the complete compatible-metadata digest with the
certification receipt, and re-attest runtime/package state inside the serialized registry
lease that issues each data query. Missing, offline-only, revoked, or drifted readiness
fails before a query. `preflight` and `render` do not issue Salesforce data queries.

| Command | Request schema | Result schema |
| --- | --- | --- |
| `preflight` | `salesforce-account-profile-preflight-request/v1` | `salesforce-account-profile-preflight-result/v1` |
| `resolve` | `salesforce-account-profile-resolve-request/v1` | `salesforce-account-profile-resolve-result/v1` |
| `profile` | `salesforce-account-profile-profile-request/v1` | `salesforce-account-profile-profile-result/v1` |
| `render` | `salesforce-account-profile-render-request/v1` | `salesforce-account-profile-render-result/v1` |

The v2 control-plane contracts are
`salesforce-account-profile-read-plan/v2` and
`salesforce-account-profile-approval-receipt/v2`. A read plan binds the exact org identity,
Account selector and selected Account when known, sorted corporate-family Account IDs,
preset, requested sections, selected/family scope, open/closed/all Opportunity scope,
close-date and StageName filters, field-map version, current private-registry readiness
digest, output type, issue time, and expiry.
Every plan and session expires exactly 30 minutes after issue; activity does not extend it.

Approval receipts record that a conversational approval occurred and bind the complete
current plan, including the pinned runtime and selected Account receipt. They are workflow
consistency evidence, not cryptographic proof of a human
identity or authorization. The runtime carries them privately; a user never copies a digest.

The org registry uses `salesforce-account-profile-org-registry/v3`. A certified entry
contains a recomputable evidence receipt plus a bounded signed-assertion replay ledger; a
bare hash is insufficient. Legacy v1 and unsigned v2 registries are accepted only for safe
migration and every prior certification is downgraded to `offline_validated`. Runtime,
package, metadata, field-map, receipt, or dependent sandbox drift invalidates readiness and
active plans before a Salesforce data query.

Errors use `salesforce-account-profile-error/v1` with a stable `error.code` and safe
`error.message`. The public CLI does not emit raw exception details.

## Minimal Requests

```json
{"schema_version":"salesforce-account-profile-preflight-request/v1","target_org":"explicit-alias"}
```

```json
{"schema_version":"salesforce-account-profile-resolve-request/v1","target_org":"explicit-alias","confirmed_org_digest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","selector":{"mode":"exact_name","value":"Example Account"}}
```

```json
{"schema_version":"salesforce-account-profile-profile-request/v1","target_org":"explicit-alias","confirmed_org_digest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","account_receipt":{"schema_version":"salesforce-account-profile-account-receipt/v1","classification":"confidential","org_digest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","account":{"Id":"001000000000001AAA","Name":"Example Account"},"receipt_digest":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}}
```

```json
{"schema_version":"salesforce-account-profile-render-request/v1","profile":{"schema_version":"salesforce-account-profile-profile-result/v1","classification":"confidential","status":"complete","selected_account":{"Id":"001000000000001AAA","Name":"Example Account","ParentId":null,"OwnerId":"005000000000001AAA"},"scope":"selected_account","opportunity_scope":"open","accounts":[],"family_confirmation":null,"opportunities":[],"products":[],"team":[],"currencies":[],"warnings":[],"query_count":1}}
```

The advanced v1 profile defaults to `["overview"]`, `selected_account`, and open
Opportunities. The v2 conversational default is different by design.

The v2 conversational default is the `pipeline` preset: selected-account overview, open
Opportunities, and owner hierarchy. Other fixed presets are `snapshot`, `team`,
`family_map`, and `full_selected`; `custom` requires explicit sections and filters.

## V2 Read Plan Example

```json
{"schema_version":"salesforce-account-profile-read-plan/v2","classification":"confidential","session_id":"0123456789abcdef0123456789abcdef","org_identity":{"target_org":"explicit-alias","org_id":"00D000000000001AAA","username":"synthetic@example.invalid","instance_url":"https://synthetic.example.invalid/","connected_status":"Connected"},"runtime_attestation_digest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","registry_readiness_digest":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd","account_selector":{"mode":"exact_name","value":"Example Account"},"selected_account":null,"account_receipt_digest":null,"family_account_ids":[],"preset":"pipeline","requested_sections":["overview","opportunities","team"],"scope":"selected_account","opportunity_scope":"open","filters":{"close_date_from":null,"close_date_to":null,"stages":[]},"field_map_version":"salesforce-account-profile-field-map/v1","output_type":"rendered","issued_at":"2030-01-01T00:00:00.000Z","expires_at":"2030-01-01T00:30:00.000Z"}
```

## Confirmation Receipts

The legacy preflight digest binds the explicit alias to org ID, username, instance URL, and
the private Salesforce CLI runtime-attestation digest. `resolve` requires that digest and
returns an Account receipt bound to the same org identity. `profile` revalidates both.

Corporate-family discovery returns a sorted Account-ID set and legacy consistency digest. A
request with `scope: "corporate_family"` and Opportunities, opportunity line items, or team
hierarchy returns `family_confirmation_required` until `confirmed_family_digest` matches the
current plan. The digest binds the org/runtime, selected Account, exact family IDs, requested
sections, selected/family scope, open/closed/all Opportunity scope, filters, field-map
version, and output type. Changing any bound value invalidates confirmation. This unkeyed
digest detects state drift; it is not proof of human identity or authorization.

Exact Account name and prefix binding follow Salesforce's case-insensitive comparison
semantics after deterministic Unicode NFKC normalization and `en-US` lowercase folding.
Exact still means full-name equality: no substring or wildcard semantics are introduced.

## Deterministic Limits

| Surface | Limit |
| --- | ---: |
| Account candidates | 20 |
| Corporate-family Accounts | 500 |
| Opportunities | 2,000 |
| Opportunity line items | 5,000 |
| Users | 100 |
| IDs per query batch | 200 |
| Manager depth | 10 |
| Parent traversal depth | 10 |
| Salesforce data queries per conversational run or advanced command | 30 |

Any cap, truncation, missing or non-boolean completeness flag, record-count mismatch,
later-batch failure, schema failure, query authorization/FLS failure, or relationship
inconsistency fails the command without a
result artifact.

ParentId family discovery also fails without a family result on cycle or depth-limit
conditions and reports selected-account scope as the safe fallback. Manager cycles and depth
limits remain nonfatal, but the result explicitly carries `MANAGER_HIERARCHY_INCOMPLETE`.

## Org Registry, Retention, And Recovery

The runtime creates private temporary directories only for SOQL request files and deletes
them in `finally` blocks. Raw Salesforce CLI output is parsed in memory, allowlisted, and
discarded. The skill does not cache profiles.

The private org registry retains only an alias, friendly label, org fingerprint, org-ID
suffix, instance host, org/environment type, field-map version, readiness state,
verification dates, and—only for production approval—redacted evidence references. It never
retains a username, full org ID, instance URL, credential, or token. `doctor` verifies all
required object metadata and predicate fields before recording metadata verification.

Active session control state is stored in an exact-mode `0700` directory and `0600` files.
It contains only the plan, minimal Account/family manifest, receipts, state, cumulative
query count, and fixed expiry. Raw CLI output, relationship hydration, completed profiles,
and credentials are rejected recursively.

Authentication and permission failures map to explicit correction and retry. Atomic cap
failures map to deterministic narrowing. Security-sensitive, inconsistent, or unknown
failures cancel the session. Never combine a failed partial run with a later result.
