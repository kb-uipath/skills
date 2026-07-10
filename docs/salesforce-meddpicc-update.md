# salesforce-meddpicc-update

Draft, confirm, prepare, and verify MEDDPICC and Next Steps updates on UiPath Salesforce Opportunities through Integration Service. The local helpers never call Salesforce; the agent workflow owns all external reads and the single confirmed PATCH.

**Last verified:** 2026-07-10

## When To Use

Use this skill when the user provides a Salesforce Opportunity URL or ID and asks to update MEDDPICC, qualification, or Next Steps fields. Do not use it for another Salesforce object, another CRM, or an unconfirmed write.

## Runtime And Dependencies

- Node.js 18 or newer; no npm packages or install step.
- Python 3 only for `tools/validate_repo.py`.
- UiPath Integration Service access to connector `uipath-salesforce-sfdc` for live agent workflows.
- Salesforce Opportunity read, describe, and field update permissions.
- Local helper entrypoints: `scripts/meddpicc.mjs` and `scripts/certify-sandbox.mjs`.

The helpers use only Node.js standard-library modules and have no network client. A caller must resolve the connection and perform reads/PATCH through the approved Integration Service path.

## Inputs

Safety-critical artifacts are explicitly versioned:

| Command | Input contract | Required safety fields |
| --- | --- | --- |
| `draft` | `salesforce-meddpicc-draft-input/v1` | Opportunity ID, author, date, current Opportunity including `LastModifiedDate`, and content |
| `receipt --mode confirmation` | `salesforce-meddpicc-confirmation-input/v1` | Draft v2, `confirmed: true`, ISO `confirmedAt`, optional `confirmedBy` |
| `build-patch` | `salesforce-meddpicc-build-patch-input/v2` | Draft v2, confirmation v1, transaction v1, describe, connection ID, exact `freshLastModifiedDate` |
| `verify` | `salesforce-meddpicc-verify-input/v2` | Draft v2, `patch_prepared` transaction v1, PATCH response, fresh read-back |
| `recover` | `salesforce-meddpicc-recovery-input/v1` | Draft v2, existing transaction v1, fresh read-back |
| `receipt --mode audit` | `salesforce-meddpicc-audit-input/v1` | Available draft/confirmation/patch/verification artifacts |

Input schema labels document the accepted payload shape; output artifacts carry a machine-readable `schema_version`. `parse-id` and `classify-error` remain unversioned compatibility helpers.

## Prompt

```text
Use $salesforce-meddpicc-update for this Opportunity URL. Parse the ID, read the Opportunity including LastModifiedDate, draft the exact field changes, and wait for my explicit approval. After approval, create a confidential confirmation receipt, re-read LastModifiedDate, build at most one PATCH envelope, verify by read-back, and retain only an audit receipt.
```

## Outputs

| Artifact | `schema_version` | Classification |
| --- | --- | --- |
| Draft | `salesforce-meddpicc-draft/v2` | Confidential |
| Confirmation receipt | `salesforce-meddpicc-confirmation/v1` | Confidential |
| Transaction | `salesforce-meddpicc-transaction/v1` | Internal restricted |
| Prepared PATCH | `salesforce-meddpicc-patch/v2` | Confidential; contains connector ID and request body |
| Verification | `salesforce-meddpicc-verification/v2` | Confidential |
| Recovery result | `salesforce-meddpicc-recovery/v1` | Internal restricted |
| Audit receipt | `salesforce-meddpicc-audit-receipt/v1` | Internal; metadata only |
| Telemetry | `salesforce-meddpicc-telemetry/v1` | Internal restricted; includes Opportunity ID |

`operation_id` is a deterministic SHA-256 identifier over Opportunity ID, the base `LastModifiedDate`, and canonical proposed fields. Transactions carry an integrity digest and move from `confirmed` to `patch_prepared`, then to `verified` or `recovery_required`. Reusing a prepared or completed transaction fails with `DUPLICATE_OPERATION`.

## Runnable Example

This fixture-backed example prepares an envelope and verifies recovery logic locally. It performs no external calls or writes.

```bash
node --input-type=module <<'NODE'
import fs from "node:fs";
import { buildPatch, draft, receipt, recover } from "./salesforce-meddpicc-update/scripts/meddpicc.mjs";

const current = JSON.parse(fs.readFileSync("./salesforce-meddpicc-update/tests/fixtures/current-opportunity.json", "utf8"));
const describe = JSON.parse(fs.readFileSync("./salesforce-meddpicc-update/tests/fixtures/describe-opportunity.json", "utf8"));
const prepared = draft({
  opportunityId: current.Id,
  author: "Sandbox Operator",
  date: "2026-07-10",
  generatedAt: "2026-07-10T14:00:00.000Z",
  current,
  content: { NextStep: "Confirm the synthetic sandbox owner." },
});
const confirmation = receipt({
  mode: "confirmation",
  draft: prepared,
  confirmed: true,
  confirmedAt: "2026-07-10T14:00:30.000Z",
});
const patch = buildPatch({
  draft: prepared,
  confirmation,
  transaction: confirmation.transaction,
  describe,
  connectionId: "local-example-only",
  freshLastModifiedDate: current.LastModifiedDate,
  now: "2026-07-10T14:01:00.000Z",
});
const result = recover({
  draft: prepared,
  transaction: patch.transaction,
  readBack: { ...current, ...prepared.proposedFields },
  checkedAt: "2026-07-10T14:02:00.000Z",
});
console.log(JSON.stringify({ operation_id: patch.operation_id, recovery: result.resolution }, null, 2));
NODE
```

Expected recovery is `verified_no_retry`.

## Safety

- `build-patch` emits no envelope without an approved confirmation, valid transaction, and exact matching fresh `LastModifiedDate`.
- `receipt` requires `--mode confirmation` or `--mode audit`; the legacy mode-less command fails with migration guidance.
- Confirmation receipts are explicitly `confidential` and may contain narratives, names, emails, and Opportunity identifiers.
- Audit receipts use a strict metadata allowlist and omit narratives, names, emails, Opportunity IDs, connector IDs, request bodies, and customer content.
- Reads and describe calls may retry with bounded backoff. PATCH is an at-most-once action and must never retry automatically.
- No Salesforce Lightning UI automation fallback is allowed.
- Telemetry construction is non-mutating and emits only its documented allowlist.

Unsafe legacy payloads fail with `UNSUPPORTED_DRAFT_SCHEMA`, `RECEIPT_MODE_REQUIRED`, `EXPLICIT_CONFIRMATION_REQUIRED`, `CONFIRMATION_REQUIRED`, `MISSING_FRESHNESS_PROOF`, or `TRANSACTION_REQUIRED`. Regenerate artifacts instead of bypassing these errors.

## Failure Recovery

For read or describe failures, retry up to three times with bounded exponential backoff and jitter. Reconfirm if the retry window makes the draft or confirmation older than the configured maximum.

For a PATCH timeout, connection loss, or unknown response:

1. Preserve the existing `patch_prepared` transaction and do not resend the envelope.
2. Re-read the Opportunity; reads may retry.
3. Run `recover` with the original draft, transaction, and fresh read-back.
4. If the result is `verified_no_retry`, retain the audit result and stop.
5. If the result is `fresh_read_redraft_reconfirm`, discard the old envelope, draft from the fresh record, obtain new approval, and create a new operation.

For schema, field-security, or picklist failure, correct the source condition and rebuild from a fresh read. A transaction in `patch_prepared`, `recovery_required`, or `verified` cannot create another envelope.

## Data Classification And Retention

- Treat source Opportunity data, drafts, confirmation receipts, prepared PATCH envelopes, and verification output as confidential customer data.
- Delete confirmation and PATCH artifacts immediately after verified audit extraction; 30 days is the hard maximum for unresolved recovery.
- Retain only audit receipts and required telemetry under the organization's approved operational-retention policy.
- Audit receipts intentionally exclude the Opportunity ID. Telemetry includes it and therefore remains internal restricted data, not anonymous analytics.
- Never persist access tokens. Do not place connector IDs, request bodies, names, emails, Opportunity IDs, or narratives in sandbox-certification evidence.
- The helpers do not store or transmit artifacts; retention is the caller's responsibility.

## Known Limitations

- Integrity digests detect accidental modification but are not authenticated signatures; a party able to replace an artifact can recompute them.
- Deterministic `operation_id` is not a Salesforce idempotency key. Duplicate protection depends on preserving and validating transaction artifacts.
- The helper has no durable operation ledger and cannot detect reuse when a caller discards prior state.
- Live schema, permissions, connector behavior, and Salesforce validation rules remain tenant-specific.
- Recovery compares target values. It cannot prove which actor wrote a value that already matches.
- The certification helper evaluates supplied evidence and never performs the sandbox workflow itself.

## Certification Status

As of 2026-07-10, the helper is fixture-tested and repository-validated only. It is **not sandbox-write certified or production certified**. `certify-sandbox.mjs` defaults to no-write evidence evaluation; `--allow-write` only evaluates evidence from an operator-run, approved sandbox probe and still performs no network calls. See the [sandbox certification runbook](../salesforce-meddpicc-update/references/sandbox-certification.md).

## Validation

```bash
node --check salesforce-meddpicc-update/scripts/meddpicc.mjs
node --check salesforce-meddpicc-update/scripts/certify-sandbox.mjs
node --test salesforce-meddpicc-update/tests/*.test.mjs
python3 tools/validate_repo.py
```
