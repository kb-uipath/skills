# Sandbox Certification Runbook

This runbook certifies the deterministic workflow against a Salesforce sandbox. The repository helper evaluates redacted evidence only. It has no network client and never performs external reads or writes.

## Default No-Write Check

1. Use a dedicated Salesforce sandbox and non-production UiPath Integration Service connection.
2. Run the targeted tests and repository validator.
3. Confirm that an Opportunity read and Opportunity describe succeed without changing data.
4. Create a local evidence file containing booleans only:

   ```json
   {
     "environment": "sandbox",
     "read_succeeded": true,
     "describe_succeeded": true,
     "targeted_tests_passed": true,
     "repo_validation_passed": true
   }
   ```

5. Evaluate it in the default no-write mode:

   ```bash
   node salesforce-meddpicc-update/scripts/certify-sandbox.mjs --input evidence.json
   ```

The maximum result is `read_only_validated`. It is not live-write certification.

## Opt-In Write Probe

Use a write probe only in an approved sandbox change window with a named recovery owner. The operator, not the helper, performs the normal confirmed workflow. Never target production, never use realistic customer narrative, and never place connector IDs, request bodies, names, emails, Opportunity IDs, or field values in certification evidence.

1. Prepare synthetic MEDDPICC content and record the original sandbox field values outside the evidence file.
2. Obtain explicit confirmation and build one PATCH envelope with matching fresh `LastModifiedDate`.
3. Send the PATCH once. Do not automatically retry a timeout or ambiguous response.
4. Re-read the Opportunity. Use `recover` when the response is ambiguous.
5. Confirm duplicate `build-patch` use is blocked for the prepared transaction.
6. Restore the sandbox record through a new, separately confirmed operation and verify cleanup.
7. Add only the following redacted evidence fields:

   ```json
   {
     "environment": "sandbox",
     "read_succeeded": true,
     "describe_succeeded": true,
     "targeted_tests_passed": true,
     "repo_validation_passed": true,
     "acknowledge_external_write": true,
     "change_window_approved": true,
     "recovery_owner": "assigned",
     "patch_response_code": 204,
     "read_back_matched": true,
     "duplicate_operation_blocked": true,
     "recovery_exercised": true,
     "cleanup_verified": true
   }
   ```

8. Evaluate the evidence explicitly:

   ```bash
   node salesforce-meddpicc-update/scripts/certify-sandbox.mjs --allow-write --input evidence.json
   ```

`--allow-write` allows evaluation of write evidence; it does not enable a network call.

## Recovery

- Reads and describe calls may retry with bounded backoff.
- PATCH must never retry automatically or reuse a `patch_prepared`, `recovery_required`, or `verified` transaction.
- For timeout, connection loss, or unknown response, re-read the Opportunity and run `recover` with the existing transaction.
- If every proposed field matches, retain the `verified_no_retry` result.
- If any field differs, rebuild from the fresh read and obtain a new confirmation. Do not resend the old envelope.

## Evidence Handling

Keep the metadata-only certification result with release evidence. Delete input evidence after review. Never retain confidential confirmation receipts with certification evidence. A sandbox result does not certify production permissions, schema, connector configuration, or runtime behavior.
