# Which source wins

For every number, take the highest source that actually has it, and record which
one you used.

## Consumption (`actualConsumed`)

1. **Utilization telemetry.** Consumption and utilization for Cloud products are
   managed in Boon and surfaced through Snowflake; the recommended place to
   analyse license utilization, bots, consumables and adoption is the dedicated
   Power BI dashboard, which consolidates Cloud and on-prem.
2. **`ProductUsage__c.ON_PREM_Quantity_Consumed__c`, only where
   `Legacy__c = false`.** This field is populated on **100% of Gainsight-legacy
   rows and about 1% of current Boon-sourced rows**. A legacy value is inherited
   from a retired migration, not a current measurement. Treat a legacy row as
   unmeasured.
3. **An attributable statement**, from a named person with a date — a
   utilization discussion, a QBR, a platform owner's message.
4. **Nothing.** Leave `null`. The tab renders "Not measured", which is true.

`Account.Utilization_Users__c`, `Utilization_Robots__c` and
`Utilization_Consumables__c` are pre-computed percentages and are the intended
dashboard source, but are populated on roughly 2% of CS-segmented accounts.
Check them; do not rely on them. They are percentages in any case, and the
document takes quantities.

> **Known gap.** The Power BI connector requires an `artifactId` GUID and
> exposes no discovery tool, so telemetry cannot be reached until someone
> supplies the workspace and report GUIDs from the dashboard URL
> (`app.powerbi.com/groups/<workspaceId>/reports/<reportId>`). Until then,
> source 1 is unavailable and most rows will legitimately come back unmeasured.
> Say so in the handoff rather than substituting entitlement.

## Entitlement (`soldQuantity`)

1. `SBQQ__Subscription__c` on the current contract, ELA bundles decoded
   (see [entitlement-resolution.md](entitlement-resolution.md)).
2. `ProductUsage__c.Quantity_Purchased__c` as a cross-check, not a replacement.
3. A contract document or an explicit statement from the platform owner.

Entitlements are foundational rather than recent: an entitlement from the
current contract stays valid even if the contract predates the usual recency
window.

## ARR (`soldArrUsd`)

1. A known contracted line value → `arrSource: "manual"`.
2. Otherwise leave `null` with `arrSource: "pricebook"` and let the app allocate
   the account's ARR by pricebook list weight.

An allocated figure is an estimate of a line's ARR, not a contract term: it
assumes every line was discounted at the plan's blended rate, which is rarely
exactly true. Never present an allocated figure as contracted.

## Judgment fields

`renewalEconomics.assurance` (`High`/`Medium`/`Low`) and
`consumptionPlan.businessValue.realizedOwner` come from an explicit account-team
statement and nothing else. Do not infer assurance from utilization, and do not
infer an owner from who happens to be the CSM.

## Hours are not dollars

A stated effort figure in hours never becomes a dollar figure in
`businessValue.realizedUsd` without a rate someone actually stated.

## Recency

Prefer the newest evidence, roughly a 180-day window, with these exceptions that
stay valid beyond it: entitlements and quantities on the current contract,
contract dates, and the licensing model.
