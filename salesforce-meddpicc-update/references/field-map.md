# Field Map: UiPath Salesforce Opportunity to MEDDPICC

Verified against `uipath.lightning.force.com` as of 2026-05-12. Re-verify with Opportunity `describe` before every write because Salesforce schema and field security can change.

`references/field-map.json` is the authoritative machine-readable source used by `scripts/meddpicc.mjs`. This Markdown file is an operator-readable summary; do not update it without keeping the JSON contract aligned.

## Query Before Drafting

Use one SOQL query for the current state:

```sql
SELECT Id, Name, AccountId, Account.Name, StageName, CloseDate, Amount,
       LastModifiedDate, NextStep, Opportunity_Next_Steps__c, Metrics__c,
       Economic_Buyer__c, Required_Capabilities__c, Decision_Process_Actual__c,
       Paper_Process__c, Pains_Challenges__c, Champion_Actual__c,
       Competition__c, Competition_meddic__c
FROM Opportunity
WHERE Id = '<oppId>'
```

`LastModifiedDate` is required for stale-draft protection. Re-read before write when the confirmation is stale or the read-back `LastModifiedDate` changed.

## Target Fields

| MEDDPICC element | API name | Type | Length | Write behavior |
|---|---|---:|---:|---|
| Metrics | `Metrics__c` | textarea | 32768 | Append dated narrative |
| Economic Buyer | `Economic_Buyer__c` | reference(Contact) | 18 | Contact ID only |
| Decision Criteria | `Required_Capabilities__c` | textarea | 10000 | Append dated narrative |
| Decision Process | `Decision_Process_Actual__c` | textarea | 32768 | Append dated narrative |
| Paper Process | `Paper_Process__c` | textarea | 32768 | Append dated narrative |
| Identified Pain | `Pains_Challenges__c` | textarea | 32768 | Append dated narrative |
| Champion | `Champion_Actual__c` | reference(Contact) | 18 | Contact ID only |
| Competition picklist | `Competition__c` | multipicklist | 4099 | Semicolon-separated allowed values only |
| Competition narrative | `Competition_meddic__c` | textarea | 32768 | Append dated narrative |
| Next Step | `NextStep` | string | 255 | Replace with concise headline |
| Opportunity Next Steps | `Opportunity_Next_Steps__c` | textarea | 32768 | Append action list, Compelling Event, Champion strategy, EB strategy |

## Missing Fields by Design

- No `Compelling_Event__c`: route to `Opportunity_Next_Steps__c` under `========== COMPELLING EVENT ==========`.
- No `Champion_Notes__c` or `Champion_Strategy__c`: route narrative to `Opportunity_Next_Steps__c` under `========== CHAMPION STRATEGY ==========`.
- No `EB_Strategy__c` or `Economic_Buyer_Notes__c`: route narrative to `Opportunity_Next_Steps__c` under `========== ECONOMIC BUYER STRATEGY ==========`.

## Describe Checks

Before PATCH, verify every proposed field:

- Exists on Opportunity.
- Is updateable.
- Has the expected field type.
- Does not exceed `length`.
- Uses valid picklist values when type is `picklist` or `multipicklist`.
- Uses a Salesforce ID for `reference` fields.

Salesforce PATCH is atomic. One bad field rolls back the entire request.

## Helper Contract

The helper loads `field-map.json` at runtime and uses it for:

- Field aliases and accepted user keys.
- Target Salesforce API names.
- Routing for Compelling Event, Champion strategy, and Economic Buyer strategy.
- Type and length expectations.
- Default connector key and Salesforce API version.
