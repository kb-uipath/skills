# Contracts And Limits

Contract set: `salesforce-account-profile/v1`
Classification: confidential
Last verified: 2026-07-25

## Command Contracts

All inputs reject unknown keys. JSON input is limited to 1 MiB. A path input must be a regular,
non-symlink `0600` file. Output files are created once with `0600`; existing paths are not
overwritten.

| Command | Request schema | Result schema |
| --- | --- | --- |
| `preflight` | `salesforce-account-profile-preflight-request/v1` | `salesforce-account-profile-preflight-result/v1` |
| `resolve` | `salesforce-account-profile-resolve-request/v1` | `salesforce-account-profile-resolve-result/v1` |
| `profile` | `salesforce-account-profile-profile-request/v1` | `salesforce-account-profile-profile-result/v1` |
| `render` | `salesforce-account-profile-render-request/v1` | `salesforce-account-profile-render-result/v1` |

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

## Confirmation Receipts

The preflight digest binds the explicit alias to org ID, username, and instance URL. `resolve`
requires that digest and returns an Account receipt bound to the same org identity. `profile`
revalidates both.

Corporate-family discovery returns a sorted Account-ID set and digest. A request with
`scope: "corporate_family"` and either Opportunities or products returns
`family_confirmation_required` until `confirmed_family_digest` matches the current set.
Changing the set invalidates confirmation.

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

## Retention And Recovery

The runtime creates private temporary directories only for SOQL request files and deletes
them in `finally` blocks. Raw Salesforce CLI output is parsed in memory, allowlisted, and
discarded. The skill does not cache profiles.

If a command fails, correct the input, permissions, schema map, or confirmation and rerun the
whole command. Do not combine a failed partial run with a later result.
