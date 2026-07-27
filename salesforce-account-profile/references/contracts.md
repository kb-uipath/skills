# Contracts And Limits

Contract sets: `salesforce-account-profile/v1` and `salesforce-account-profile/v2`
Classification: confidential
Last verified: 2026-07-27

The v1 command contracts remain compatible advanced primitives. The v2 conversational
orchestrator owns their transport values and exposes only business decisions to the user.

## Command Contracts

All inputs reject unknown keys. JSON input is limited to 1 MiB. A path input must be a regular,
non-symlink file with exact mode `0600`; it is opened with no-follow semantics and rechecked
after reading. Output files are created once with `0600`; existing paths are not overwritten.

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
close-date and StageName filters, field-map version, output type, issue time, and expiry.
Every plan expires within 30 minutes.

Approval receipts record that a conversational approval occurred and bind the complete
current plan, including the pinned runtime and selected Account receipt. They are workflow
consistency evidence, not cryptographic proof of a human
identity or authorization. The runtime carries them privately; a user never copies a digest.

Errors use `salesforce-account-profile-error/v1` with a stable `error.code`, safe
`error.message`, and optional redacted details.

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

The default profile sections are `["overview"]`, scope is `selected_account`, and
Opportunity scope is `open`. Request `family`, `opportunities`, `products`, or `team`
explicitly.

The v2 conversational default is the `pipeline` preset: selected-account overview, open
Opportunities, and owner hierarchy. Other fixed presets are `snapshot`, `team`,
`family_map`, and `full_selected`; `custom` requires explicit sections and filters.

## V2 Read Plan Example

```json
{"schema_version":"salesforce-account-profile-read-plan/v2","classification":"confidential","session_id":"0123456789abcdef0123456789abcdef","org_identity":{"target_org":"explicit-alias","org_id":"00D000000000001AAA","username":"synthetic@example.invalid","instance_url":"https://synthetic.example.invalid/","connected_status":"Connected"},"runtime_attestation_digest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","account_selector":{"mode":"exact_name","value":"Example Account"},"selected_account":null,"account_receipt_digest":null,"family_account_ids":[],"preset":"pipeline","requested_sections":["overview","opportunities","team"],"scope":"selected_account","opportunity_scope":"open","filters":{"close_date_from":null,"close_date_to":null,"stages":[]},"field_map_version":"salesforce-account-profile-field-map/v1","output_type":"rendered","issued_at":"2030-01-01T00:00:00.000Z","expires_at":"2030-01-01T00:30:00.000Z"}
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
| Salesforce data queries per command | 30 |

Any cap, truncation, missing or non-boolean completeness flag, record-count mismatch,
later-batch failure, schema failure, query authorization/FLS failure, or relationship
inconsistency fails the command without a
result artifact.

ParentId family discovery also fails without a family result on cycle or depth-limit
conditions and reports selected-account scope as the safe fallback. Manager cycles and depth
limits remain nonfatal, but the result explicitly carries `MANAGER_HIERARCHY_INCOMPLETE`.

## Retention And Recovery

The runtime creates private temporary directories only for SOQL request files and deletes
them in `finally` blocks. Raw Salesforce CLI output is parsed in memory, allowlisted, and
discarded. The skill does not cache profiles.

If a command fails, correct the input, permissions, schema map, or confirmation and rerun the
whole command. Do not combine a failed partial run with a later result.
