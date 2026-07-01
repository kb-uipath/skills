# salesforce-meddpicc-update

Draft, confirm, write, and verify MEDDPICC and Next Steps updates on UiPath Salesforce Opportunities through Integration Service.

## When To Use

Use this skill when the user provides a Salesforce Opportunity URL or ID and asks to update MEDDPICC, qualification, or Next Steps fields.

## Inputs

- Salesforce Opportunity URL or ID beginning with `006`.
- User-provided MEDDPICC or Next Steps content.
- UiPath Integration Service Salesforce connector access.
- Salesforce connection ID and element instance ID resolved at runtime.
- Opportunity read data, Opportunity describe response, and explicit user confirmation before write.
- Salesforce object, field-level, describe, and update permissions for every target field.

## Prompt

```text
Use $salesforce-meddpicc-update for this Opportunity URL. Parse the ID, draft MEDDPICC updates, show me the exact field-level write plan, and do not write until I explicitly approve.
```

## Outputs

- Parsed Opportunity ID.
- Draft field changes and skipped fields.
- PATCH envelope after describe validation.
- Read-after-write verification receipt.
- Privacy-safe telemetry payload after verification.

## Safety

- No live write without explicit field-level user confirmation.
- No Salesforce Lightning UI automation fallback for writes.
- Stop on missing connection, stale read, schema drift, field security errors, invalid picklists, or malformed Opportunity IDs.
- Telemetry must use `buildTelemetryPayload()` only; narrative content, names, emails, amounts, and Opportunity names must not be logged.
- Confirmation receipts are not proof of write success; only read-after-write verification can be reported as success.
- If telemetry fails after a successful PATCH, report the observability failure but do not roll back the Salesforce write.

## Validation

```bash
node --test salesforce-meddpicc-update/tests/*.mjs
node --check salesforce-meddpicc-update/scripts/meddpicc.mjs
python3 tools/validate_repo.py
```
