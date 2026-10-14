# Attributing consumption to use cases

Schema 1.10 adds `allocations[]` to each entry in
`consumptionPlan.primaryUseCases[]`:

```json
{
  "category": "In Production",
  "useCases": "Month-end close reconciliation",
  "arrConsumedUsd": 1800000,
  "customerValue": "30% faster close cycle time",
  "allocations": [
    { "rowId": "<consumption row id>", "currentUnits": 180,
      "forecastUnits": { "q1": 100, "q2": 105, "q3": 15, "q4": 15 } }
  ]
}
```

## The row stays authoritative

A consumption row's `actualConsumed` and `forecastUnits` are the **measured
totals**. Allocations only *explain* them. Never adjust a row to match its
allocations — if they disagree, the disagreement is the finding.

The app derives the unattributed remainder (row figure − allocations) and prints
it under the table. You never write it.

## Three states, all legitimate

| State | What to write | What the tab shows |
| --- | --- | --- |
| Nothing attributed | `allocations: []` | Nothing. Silence is the default, not a finding |
| Partly attributed | The allocations you have | "180 of 300 bots unattributed." |
| Over-attributed | The allocations you have | "use cases claim 150 bots more than the row measures." |

Over-attribution is reported, not clamped. It usually means either double
counting across use cases or a stale row figure, and both are worth a
conversation.

An empty `allocations` array means *unrecorded*, not *zero*. Do not add a
zero-unit allocation to signal "this use case uses none of this license" unless
someone actually measured zero.

## Do not force a tie

The temptations, all of which are fabrication:

- Dividing a row's consumption evenly across the use cases that touch it.
- Scaling stated shares up so they reach 100%.
- Inventing a "General / other" use case to absorb the remainder.

The remainder exists to be seen. If the account team wants it closed, they close
it with evidence.

## Converting a stated share

Customers speak in proportions: "roughly half of our AI Units go to invoices."
Convert it, and record that you did:

- Compute against the row's own `actualConsumed`, never against `soldQuantity` —
  a share of consumption is not a share of entitlement.
- Round to a sensible precision; false precision implies a measurement.
- Put the basis in the use case's `customerValue` or the provenance report, e.g.
  "≈50% of measured AI Unit consumption, per <name>, <date>".

## Quarters

An allocation's `forecastUnits` uses the **same four quarters** as the row's, on
the same fiscal grid (see [quarter-basis.md](quarter-basis.md)) and in the row's
unit. Fill only the quarters someone actually gave.

For a `peak` row, an allocation means that use case's share **at the row's
peak**, so the shares still sum to the peak rather than exceeding it.

## Referencing rows

`rowId` must be the `id` of an existing consumption row. Two consequences:

1. **Create the rows first**, then attribute. An allocation written before its
   row exists points at nothing.
2. **Reuse ids when enriching.** Regenerating the plan with fresh ids orphans
   every allocation silently — validation flags the dangling reference, but the
   attribution is already lost.

A dangling `rowId` is excluded from the row's attributed total and reported; it
is never deleted, so the account team can repoint it.
