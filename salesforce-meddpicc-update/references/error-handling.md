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

Salesforce PATCH is all-or-nothing. Do not assume partial success.
