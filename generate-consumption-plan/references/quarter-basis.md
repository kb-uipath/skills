# What Q+1 to Q+4 mean

## The fiscal grid

UiPath's fiscal year ends 31 January. **FY2027 = 2026-02-01 → 2027-01-31.**
Confirmed from Salesforce's own `FiscalYear`/`FiscalQuarter` fields:

| Fiscal period | Dates |
| --- | --- |
| Q1 FY27 | 1 Feb – 30 Apr 2026 |
| Q2 FY27 | 1 May – 31 Jul 2026 |
| Q3 FY27 | 1 Aug – 31 Oct 2026 |
| Q4 FY27 | 1 Nov 2026 – 31 Jan 2027 |

## The rule

`actualConsumed` is the **current** quarter — the one containing `asOf`.
`forecastUnits.q1` is the next fiscal quarter, and `q2`–`q4` the three after it.

Rolling, not fixed to a fiscal year: a review in Q3 FY27 forecasts into FY28.
The quarters snap to fiscal boundaries so the numbers reconcile with Salesforce
and Power BI reporting, but the labels are relative, which is why the deck's
columns read `Q+1`–`Q+4` rather than `Q1`–`Q4`.

`scripts/resolve-quarters.mjs` computes this. Do not do it by hand.

## Stamp the window

`consumptionPlan.forecastPeriod` is free text, and existing documents carry a
bare `"FY27"`. That does not say what `q1..q4` are, which makes a published deck
unreadable six months later and two consecutive reviews incomparable.

Write the resolved window instead: `Q+1 FY27 Q4 → Q+4 FY28 Q3`.

## The contract-year caveat

**The fiscal grid does not align to contract years.** An ELA may run 1 Jan –
31 Dec, and `ProductUsage__c.ON_PREM_Quantity_Consumed__c` is documented as
"quantity consumed in current **contract** year".

So a consumption figure pulled from Salesforce is measured against a window that
is not the one the deck's columns describe. Pro-rating across that boundary is
an assumption, and it must be written into the row's `entitlementNote` where a
reader can see it — never absorbed silently into the number.

If the contract year and the fiscal quarter cannot be reconciled from evidence,
report the figure against the window it was actually measured in and say so.

## Peak versus cumulative

The row's `forecastBasis` decides how its quarters roll up, and `"auto"` defers
to the matched SKU's `meteringBasis` in the pricebook:

- **`cumulative`** — consumable meters (AI, Agent, Apps and Platform units, API
  calls, process mining rows, alert reviews). Quarters **sum**: 40k + 48k + 30k
  + 30k is 148k over the year.
- **`peak`** — everything else, including seats and robots. Quarters take the
  **busiest** one: 100, 105, 15, 15 robots is a peak of 105, not 235.

Getting this backwards inflates a seat forecast fourfold. Prefer `"auto"` and
let the pricebook decide; override only when the customer's own basis is known
to differ, and say why in `entitlementNote`.
