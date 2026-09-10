# Resolving entitlements from Salesforce

`SBQQ__Subscription__c` is the authoritative entitlement line. The org is
Salesforce CPQ, so the chain is `Account` → `Contract` → `SBQQ__Subscription__c`
→ `Product2`, with `Asset` and `ProductUsage__c` as parallel views.

## Which rows are current

There is **no boolean "active" field**. Currency comes from the dates plus the
contract status:

```sql
SELECT Id, SBQQ__ProductName__c, SBQQ__Quantity__c,
       SBQQ__StartDate__c, SBQQ__EndDate__c, SBQQ__ContractNumber__c,
       SBQQ__NetPrice__c, SBQQ__Product__r.ProductCode,
       SBQQ__Product__r.License_Model__c, SBQQ__Product__r.Unit_of_measure__c
FROM SBQQ__Subscription__c
WHERE SBQQ__Account__c = :accountId
  AND SBQQ__StartDate__c <= TODAY
  AND SBQQ__EndDate__c   >= TODAY
  AND SBQQ__TerminatedDate__c = NULL
  AND SBQQ__Contract__r.Status = 'Activated'
```

Every clause earns its place. Measured across the org's live-dated
subscriptions, `SBQQ__TerminatedDate__c` is populated on about **22%** of them —
omitting that one clause materially overcounts entitlement.

`SBQQ__RevisedSubscription__c` (about 4%) marks CPQ amendment chains. Amendments
post delta rows, so summing the chain is correct; just do not deduplicate by
product name, which would drop the deltas.

Prefer `SBQQ__StartDate__c`/`SBQQ__EndDate__c` over
`SBQQ__SubscriptionStartDate__c`/`SBQQ__SubscriptionEndDate__c`. The latter pair
fall back to contract dates when blank; the former are always populated.

## The ELA trap

**On Enterprise License Agreement contracts, `SBQQ__Quantity__c` is `1` on every
line.** The entitled volume is encoded in the product name:

| `SBQQ__ProductName__c` | `SBQQ__Quantity__c` | Actual entitlement |
| --- | --- | --- |
| ELA - AI Unit Bundle - 60K | 1 | 60,000 units |
| ELA - Robot Units Bundle - 72K | 1 | 72,000 units |
| ELA - Process Mining Rows Bundle - 20M | 1 | 20,000,000 rows |
| ELA - Unattended Robot | 1 | *not stated in the name — ask* |

Summing quantity on an ELA account produces a confident, meaningless number.
That is the worst possible failure for a figure going into a CFO-chaired review,
because nothing about it looks wrong.

Decode against the dashboard repo's pricebook snapshot,
`src/data/uipath-pricebook.json`, which carries `productCode`, `skuName`,
`listPriceUsd`, `unitsPerSku`, and `meteringBasis` for each SKU.
`scripts/decode-entitlements.mjs` does this and reports what it could not match.

Where a name gives no volume (`ELA - Unattended Robot`), the number is not in
Salesforce. Ask the account team; do not guess from list price.

## Classifying a row

`Product2` carries the fields that decide unit and grouping:

- `License_Model__c` — `Named User`, `Node Locked`, `Server`,
  `Concurrent Runtime`, `Concurrent User`, `Consumption`, `Platform`, `Add-On`,
  `Robot`, `N/A`. Use it for the `element` group and to tell seats from meters.
- `Unit_of_measure__c` — about 42 values (`Per page`, `Per LLM Call`,
  `Per Action`, `Per Runtime Minute`, `Per prediction`, …). Source for `unit`,
  shortened to fit: `unit` is capped at 24 characters with no token over 10.
- `Family`, `ProductCode`, `StockKeepingUnit`, `SBQQ__HasConsumptionSchedule__c`.

`SBQQ__ChargeType__c` of `Usage` and `SBQQ__HasConsumptionSchedule__c` mark
consumable meters, which is what `forecastBasis: "cumulative"` is for.

Do **not** use `SBQQ__SubscriptionConsumptionSchedule__c`,
`SBQQ__SubscriptionConsumptionRate__c`, or
`SBQQ__OrderItemConsumptionSchedule__c` as usage data. They are CPQ *pricing*
tiers, not telemetry.

## Cross-checking

`ProductUsage__c.Quantity_Purchased__c` is populated on 100% of rows and is a
good independent check on the entitlement total. Join on the **SKU name string**
(`Boon_SKU_Name__c` for current rows, `Product_Name__c` for legacy ones):
`ProductUsage__c.Product__c` is populated zero times org-wide, so the Product2
lookup is unusable.

A disagreement between the subscription sum and `Quantity_Purchased__c` is worth
surfacing to the account team, not silently resolving in favour of either.
