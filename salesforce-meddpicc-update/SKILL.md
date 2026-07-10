---
name: salesforce-meddpicc-update
description: Update MEDDPICC qualification fields and Next Steps on UiPath Salesforce Opportunities through the UiPath Integration Service Salesforce connector. Use when the user provides or references a Salesforce Opportunity URL or ID and asks to update MEDDPICC, qualification, Metrics, Economic Buyer, Decision Criteria, Decision Process, Paper Process, Identified Pain, Champion, Competition, Compelling Event, or Next Steps. Requires read-before-write, exact LastModifiedDate freshness, versioned confirmation and transaction artifacts, schema describe validation, explicit user confirmation, read-after-write verification, and privacy-safe audit output.
---

# Salesforce MEDDPICC Update

Use this skill to prepare and apply safe MEDDPICC and Next Steps updates to UiPath's Salesforce org. Keep live Salesforce calls in the agent workflow. Use `scripts/meddpicc.mjs` for deterministic parsing, draft construction, PATCH-body creation, receipt generation, error classification, and verification.

## Hard Stops

Stop instead of writing when:

- The target is not a Salesforce Opportunity ID beginning with `006`.
- The request targets a non-UiPath Salesforce org or a non-Salesforce CRM.
- No enabled UiPath Integration Service Salesforce connection exists for connector `uipath-salesforce-sfdc`.
- The user has not explicitly approved the final field-level draft.
- No approved `salesforce-meddpicc-confirmation/v1` receipt and valid `confirmed` transaction are available.
- A fresh read does not supply the exact `LastModifiedDate` captured in the approved draft.
- `build-patch` returns `requiresFreshRead: true`; re-query Salesforce and rebuild the draft.
- The operation transaction is already `patch_prepared`, `recovery_required`, or `verified`.
- Opportunity `describe` shows missing, non-updateable, or incompatible target fields.

Do not fall back to Salesforce Lightning UI automation for writes.

## Required Permissions

The operator must have UiPath Integration Service access to the Salesforce connector, permission to resolve enabled `uipath-salesforce-sfdc` connections, permission to call the connection's HTTP-request element instance, Salesforce read access to the target Opportunity, Opportunity `describe` access, and update access for every writable target field. Missing object, field-level, connector, or connection permissions are hard stops.

## Workflow

1. Parse the Opportunity ID:
   ```bash
   node scripts/meddpicc.mjs parse-id --input payload.json
   ```
   See `references/url-parsing.md` for accepted URL and ID forms.

2. Resolve the Salesforce connection at runtime:
   - `GET connections_/api/v1/Connectors/uipath-salesforce-sfdc/connection`
   - Capture `id` as `connection`.
   - Capture `elementInstanceId` for the Integration Service HTTP request path.
   - Optionally ping `GET connections_/api/v1/Connections/{id}/ping` and proceed only when enabled.
   - **Fallback:** If the connector lookup returns 404 or `CNS1049` (no accessible connection), stop and ask the user to provide the Salesforce connection ID and `elementInstanceId` manually. Do not silently skip the connection requirement or proceed without a valid Integration Service path.

3. Read the Opportunity before drafting:
   - Query the fields in `references/field-map.md`.
   - Include `LastModifiedDate`.
   - If `totalSize == 0`, stop and report invalid ID or missing access.

4. Draft updates:
   ```bash
   node scripts/meddpicc.mjs draft --input payload.json
   ```
   Use the user's supplied field content as input. If deriving from notes or documents, follow `references/quality-rubric.md` first.
   Unknown content keys fail by default. Fix the key instead of silently dropping user input.

5. Show the user the final draft:
   - Opportunity name and ID.
   - Each proposed field and new entry.
   - Skipped lookup or picklist fields.
   - Warnings, truncation, duplicate detection, and action items.
   Get explicit confirmation before writing.
   After approval, generate the versioned confidential confirmation receipt. The payload must include `confirmed: true`, ISO `confirmedAt`, and the unchanged draft:
   ```bash
   node scripts/meddpicc.mjs receipt --mode confirmation --input payload.json
   ```
   This artifact is classified `confidential`, contains the deterministic `operation_id`, and starts a digested transaction in `confirmed`. It is not proof of a write.

6. Re-read and describe Opportunity immediately before composing the write:
   - Re-query `LastModifiedDate` and pass it as `freshLastModifiedDate`.
   - It must exactly match the approved draft's `currentLastModifiedDate`.
   - If it is missing or changed, rebuild the draft and obtain confirmation again.
   - `GET /services/data/v60.0/sobjects/Opportunity/describe`
   - Use the describe response as `build-patch` input.

7. Build the PATCH envelope:
   ```bash
   node scripts/meddpicc.mjs build-patch --input payload.json
   ```
   Pass the confirmation receipt and its transaction. If the draft/confirmation is stale, Salesforce changed, an integrity digest fails, or the transaction was already prepared, stop. Do not edit artifacts manually.

8. Send the PATCH through UiPath Integration Service:
   - `POST elements_/v3/element/instances/{elementInstanceId}/http-request`
   - Body is the generated envelope.
   - Expect Salesforce response code `204`.
   - Send exactly once. Never automatically retry PATCH, including after timeout or connection loss.
   If Integration Service or Salesforce returns an error, normalize it before reporting:
   ```bash
   node scripts/meddpicc.mjs classify-error --input payload.json
   ```

9. Verify:
   - Re-run the Opportunity SOQL query.
   - Run:
     ```bash
     node scripts/meddpicc.mjs verify --input payload.json
     ```
   - Pass the `patch_prepared` transaction from `build-patch`.
   - Report fields written, skipped fields, discrepancies, warnings, and exact user action items.

10. Recover ambiguous outcomes without a write retry:
    - Preserve the original `patch_prepared` transaction.
    - Re-read the Opportunity; reads may retry with bounded backoff.
    - Run:
      ```bash
      node scripts/meddpicc.mjs recover --input payload.json
      ```
    - `verified_no_retry` means the desired values are present. `fresh_read_redraft_reconfirm` means discard the old envelope and begin a new operation from the fresh read.

11. Create the retention-safe audit receipt:
    ```bash
    node scripts/meddpicc.mjs receipt --mode audit --input payload.json
    ```
    Audit mode is metadata-only. It removes narratives, names, emails, Opportunity IDs, connector IDs, request bodies, and customer content. Delete confidential confirmation and PATCH artifacts after verification; do not keep them longer than 30 days during unresolved recovery.

12. Write run record (telemetry):
    After verification, emit a privacy-stripped run record for observability.
    ```bash
    node scripts/meddpicc.mjs log-run --input payload.json
    ```
    The payload must include the `verify` output, `now` (ISO timestamp), `skillVersion`, `skillSha`, and `runId`. The helper is non-mutating and emits only its allowlist: `oppId`, `runTime`, `fieldsTargeted[]`, counts, and version/run metadata. Because `oppId` remains, classify telemetry as internal restricted rather than anonymous.
    If telemetry fails, surface the error but do NOT roll back the Salesforce write. The PATCH already landed; only the observability record is missing.

## Helper Behaviors

`scripts/meddpicc.mjs` provides deterministic, testable helpers for every stage of the pipeline. The following behaviors are available to the skill workflow and are enforced by the behavioral test corpus.

### Prompt-injection guardrail (`draft`)

Before parsing content keys, `draft()` scans every field value for instruction-override patterns such as "IGNORE PRIOR INSTRUCTIONS" or "Set StageName to ...". Injected directives are stripped, a `suspicious` warning is emitted, and the sanitized content proceeds through normal drafting. Non-MEDDPICC field names embedded in narrative text are not written to Salesforce.

### Fuzzy near-duplicate detection (`duplicateStatus`)

Exact-substring dedup catches copy-paste duplicates. For reworded near-duplicates (e.g., "30%" vs "approximately 30 percent"), `duplicateStatus()` falls back to token-based Jaccard similarity with a ~0.60 threshold. When similarity is high, `draft()` emits a warning and still appends the entry (it is not blocked), giving the user visibility without silent suppression.

### Force-duplicate override (`draft`)

When the caller passes `forceDuplicate: true` in the payload, duplicate detection is bypassed for that field. The dated prefix includes a time suffix (`[YYYY-MM-DD HH:MM - Author]`) so same-day re-logs are guaranteed unique. Use this when the user explicitly wants to re-record an entry.

### Privacy-safe telemetry (`buildTelemetryPayload`)

After verification, `buildTelemetryPayload()` emits a metadata-only run record containing `oppId`, `runTime`, `fieldsTargeted[]`, `skillVersion`, `skillSha`, and `runId`. It never deletes or changes caller input. Narratives, names, emails, amounts, and Opportunity names are omitted, but the Salesforce ID remains an internal identifier.

### Operation and transaction integrity

`operation_id` is a deterministic SHA-256 identifier over Opportunity ID, base `LastModifiedDate`, and canonical proposed fields. Confirmation and transaction digests detect accidental modification. They are not signatures and do not replace access controls or a durable idempotency ledger. Preserve the transaction through verification; discarding it removes duplicate-operation protection.

### Retry boundary

Opportunity reads, describe, and recovery reads may retry up to three times with bounded exponential backoff and jitter. PATCH is at-most-once and must not retry blindly. When the response is ambiguous, read back and use `recover`; if fields differ, start a new operation from the fresh record.

## Field Routing Rules

- Textarea fields receive dated appended entries.
- `NextStep` is a short string headline and is replaced, not appended; the helper truncates to the field limit and warns.
- `Champion_Actual__c` and `Economic_Buyer__c` are Contact lookups. Write only valid Contact IDs. Route strategy narrative to `Opportunity_Next_Steps__c`.
- There is no `Compelling_Event__c`; route Compelling Event narrative to `Opportunity_Next_Steps__c`.
- Use `Competition_meddic__c` for freeform competition narrative. Write `Competition__c` only with valid semicolon-separated picklist values.

## References

- `references/field-map.md`: Salesforce fields, SOQL query, and routing notes.
- `references/field-map.json`: Authoritative machine-readable field map used by the helper.
- `references/url-parsing.md`: ID extraction behavior and examples.
- `references/quality-rubric.md`: MEDDPICC drafting quality rules.
- `references/error-handling.md`: Common Salesforce and Integration Service failures.
- `references/sandbox-certification.md`: No-write-default sandbox evidence helper, opt-in probe runbook, recovery, and retention rules.
- Operator-provided telemetry tooling: if a local run-record logger is configured, invoke it only after verification and only with the redacted `buildTelemetryPayload()` output.
