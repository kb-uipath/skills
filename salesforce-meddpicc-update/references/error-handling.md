# Error Handling

Use `node scripts/meddpicc.mjs classify-error --input payload.json` to normalize Salesforce and UiPath Integration Service responses before reporting them to the user.

| Status or signal | Likely cause | Required response |
|---|---|---|
| `204` | PATCH succeeded | Re-query and verify. Do not report success before verification. |
| `CNS1000` or connection 404 | No Salesforce connection | Tell the user to create or re-authorize the UiPath Integration Service Salesforce connection. |
| `400 MALFORMED_ID` | Narrative was sent to a reference field | Remove the lookup field from the payload and route narrative to `Opportunity_Next_Steps__c`. |
| `400 INVALID_FIELD_FOR_INSERT_UPDATE` | Picklist mismatch or blocked field | Re-describe, show allowed values or blocked field, and ask user to choose or escalate. |
| `400 INVALID_FIELD` | API name changed or field missing | Stop and report schema drift. Do not guess a new field. |
| `400 STRING_TOO_LONG` | Field length exceeded | Truncate only `NextStep`; split or ask for a shorter narrative for other fields. |
| `401` | Expired auth | Tell the user to re-authorize the connection. |
| `403 INSUFFICIENT_ACCESS_OR_READONLY` | Field or object permission problem | Surface the exact field and ask user to escalate to Sales Ops or Salesforce admin. |
| `404` | Bad Opportunity ID or no access | Re-validate the ID and report possible access issue. |
| `requiresFreshRead: true` | Stale draft or changed Opportunity | Re-query current values, rebuild draft, and confirm again. |
| `MISSING_FRESHNESS_PROOF` | Legacy build input omitted one or both `LastModifiedDate` values | Re-read, rebuild if changed, and pass exact `freshLastModifiedDate`. |
| `CONFIRMATION_REQUIRED` | Legacy build input omitted the approved receipt | Generate `receipt --mode confirmation` after explicit approval. |
| `TAMPERED_CONFIRMATION` or `TAMPERED_TRANSACTION` | Artifact content and integrity digest differ | Discard the artifact, re-read, rebuild, and reconfirm. |
| `DUPLICATE_OPERATION` | The same operation is already prepared, recovering, or verified | Do not resend PATCH. Re-read and run `recover` or `verify`. |
| `RECOVERY_READ_REQUIRED` | A PATCH outcome is ambiguous and no read-back was supplied | Retry the read with bounded backoff; never retry the PATCH. |

Salesforce PATCH is all-or-nothing. Do not assume partial success.

## Retry Policy

- Opportunity reads and describe calls may retry up to three times with bounded exponential backoff and jitter.
- PATCH is at-most-once. Never automatically retry a timeout, dropped connection, or unknown response.
- For an ambiguous PATCH outcome, preserve the transaction, re-read the Opportunity, and run `recover`.
- If recovery finds mismatched fields, start a new draft and confirmation from the fresh record. Never reuse the old envelope.
