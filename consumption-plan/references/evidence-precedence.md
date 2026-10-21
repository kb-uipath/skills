# Which source wins

For every number, take the highest source that actually has it, and record which
one you used.

## Consumption (`actualConsumed`)

Take the first source that has the row's figure, and record it in the plan row:
`consumedQuantity`, `consumedBasis`, `consumedAsOf` (the date the figure describes), and
the source in `notes`. When no source reaches the row (a coverage gap, below), the basis is
`coverage-gap` and the figure is `null`.

1. **Governed telemetry from the curated layer** (basis `telemetry`). Reach it through the
   `account-portfolio-review` skill's governed capture for the account, with the
   `curated-data-interaction` skill for any per-row figure the capture does not show.
   The user signs in to Snowflake in the browser, so run this while they are at the
   keyboard. Ask for the governed measures by name, never by table:
   - **Unattended robots: official utilization.** That is the official utilization
     dashboard's Utilization Rate as the governed glossary defines it: robots allocated
     over robots licensed. Consumed is the allocated robot count, or the governed
     percentage × purchased quantity rounded to whole robots. The hours-based
     utilization some reviews compute (`account-portfolio-review`'s robot lens among
     them) is not the dashboard's definition; do not write it as Consumed.
     **Consumed counts contracted licences only, capped at purchased.** Robots running
     on trial or unlicensed keys hold no contracted licence, so they are not in it: state
     their count, source and date in the row's `unlicensedInUse`
     (`{ "count", "source", "asOf" }`), which the gap list turns into a TAM item ("27 robots
     run on trial or unlicensed keys beyond the 100 purchased"), and name them in `notes`.
   - **User licenses: seats assigned to named users**, per license type, from the
     governed seat allocation. Active or engaged users are never written as assigned
     seats.
   - **Consumables:** consumed-to-date on the active distribution of each license, in the
     row's unit.
   - **Coverage.** The robot and seat-allocation figures cover plain Automation Cloud
     only. A `0` consumed or `0` allocated from Automation Suite, an on-premises
     deployment or the Public Sector cloud is a coverage gap, never a measured zero:
     Consumed stays `null`, the row's `consumedBasis` is `"coverage-gap"`, and the plan's
     `telemetry.coverage` is `"partial"`. The same holds for a consumable's `0` on a
     deployment the layer captures only in part. The basis matters on a refresh: the
     baseline may already hold the `0` (an earlier merge, or the team's entry), and
     `to-day2.mjs` never erases a figure otherwise. With `coverage-gap` and no figure it
     clears the matched row's `actualConsumed` and reports
     `cleared <row> actualConsumed <old>: coverage gap`; it refuses a coverage gap that
     carries a figure, since a gap has none. The gap list then names the row as partial
     coverage, with the usual consumed next step, whatever the document holds.
2. **`ProductUsage__c.ON_PREM_Quantity_Consumed__c`, only where
   `Legacy__c = false`** (basis `telemetry`). This field is populated on **100% of
   Gainsight-legacy rows and about 1% of current Boon-sourced rows**. A legacy value is
   inherited from a retired migration, not a current measurement. Treat a legacy row as
   unmeasured.
3. **Unattended robots with no telemetry, or only a coverage gap: the estimate** (basis
   `estimate`), in this order:
   1. **A figure the team states directly** in its notes, mail or channels — a count of
      robots in production, a stated share of the fleet, production processes and the
      robots they run on — the most recent first.
   2. **Only when the team's sources give nothing:** Salesforce's
      `Account.Utilization_Robots__c` percentage × purchased quantity, rounded to whole
      robots. It is never compared by date against a team statement.

   A count or share of robots *in production* (running production jobs) measures robots
   at work, not robots allocated. It is still an accepted input: the estimate is the
   closest figure the evidence states. Write in `notes` what was counted ("30 robots
   running production jobs"), its source and its date; when Salesforce's percentage also
   exists, name it there as a cross-check for the TAM. The gap list asks the TAM to
   confirm or replace the estimate. The estimate counts contracted licences only and never
   exceeds purchased: robots on trial or unlicensed keys go in the row's `unlicensedInUse`,
   which the gap list makes a TAM item, not in the figure. Never estimate from entitlement, ARR or tone, and never for users or
   consumables. A robot figure a person states while telemetry is missing is this
   estimate, not a statement.
4. **An attributable statement** (basis `statement`), for user licenses and consumables:
   a customer tracker or export, or a dated statement from a named person — a
   utilization discussion, a QBR, a platform owner's message. For users it must count
   seats assigned to named users.
5. **Nothing.** Leave `null`. The tab renders "Not measured", which is true, and the gap
   list gives the row an owner and a next step.

**Platform / Capabilities rows** (a platform tier, a plan bundle) are used whole, not unit
by unit. **Platform Units, and every other unit bundle, are not this kind:** they are
metered units, `Consumables`, even where the pricebook files them under platform, and take
a consumed-to-date figure like any consumable. When telemetry or a dated team statement
shows the platform in production use, Consumed is the row's purchased quantity, basis
`telemetry` or `statement`, with the evidence in `notes`. Otherwise it stays `null`. This
matters because the app prices a tier that carries ARR into the Snapshot's Consumed total,
and it withholds that total, and Remaining, while any priced row has no figure. The gap
list's "blocks Snapshot Consumed" item then asks the TAM to confirm the platform is in use.

**When telemetry is not reached** — `account-portfolio-review` or
`curated-data-interaction` is not installed, or the user cannot sign in — skip source 1,
set `telemetry.coverage` to `"none"`, and say in the hand-off that telemetry was not
reached. The other sources still apply.

**The plan's `telemetry` block** records how far measurement reached for the account:
`{ "asOf": "YYYY-MM-DD", "coverage": "complete" | "partial" | "none", "note": "" }`.
`complete` when every deployment is plain Automation Cloud and telemetry was read;
`partial` when any deployment is one the layer sees only in part; `none` when telemetry
was not reached. The gap list adds `note` to every unmeasured row's next step whenever
coverage is not complete, so use it to name the deployments involved. A row whose basis is
`coverage-gap` is always listed as partial coverage, and carries the note too.

`Account.Utilization_Users__c` and `Utilization_Consumables__c` are pre-computed
percentages that the curated layer does not reproduce. They are leads, never a Consumed
figure: name them, with their values, in `telemetry.note` so the gap list hands them to
the row's owner. `Utilization_Robots__c` is the robot estimate's fallback (source 3),
used only when the team's own sources give no robot figure.

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

Where the renewal board or `account-portfolio-review` rates the account, offer that
rating in the hand-off as a suggestion, with the rule behind it. Never write it.

## Hours are not dollars

A stated effort figure in hours never becomes a dollar figure in
`businessValue.realizedUsd` without a rate someone actually stated.

## Recency

Prefer the newest evidence, roughly a 180-day window, with these exceptions that
stay valid beyond it: entitlements and quantities on the current contract,
contract dates, and the licensing model.
