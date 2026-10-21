# Pipeline demand, draws and other activity

How this skill turns an account's open Salesforce opportunities, the pursuits the team
sized itself, and the team's quarterly forecasts into the Day 2 v7 numbers that depend on
the pipeline: each Renewal Test row's pipeline driver and +6/+12-month demand, the unit draw
of each pursuit card the team sized, and the Snapshot's other pipeline activity. `scripts/pipeline.mjs`
applies every rule on this page. Your job is to give it a plan file that holds the right
opportunities and use cases, with each line decoded to units and mapped to a row, and the
team's forecasts in the rows' `forecastUnits`.

## Which figure wins

Each window of each row is decided on its own:

| The row's window | +6 or +12-month demand | Pipeline driver |
| --- | --- | --- |
| The team's forecast sets every quarter the window counts | [The team's forecast](#the-teams-forecast-wins) | The opportunities and use cases landing in the window |
| It does not | [The opportunity rule](#the-rule): open opportunities, and use cases with a start date | The same |
| A platform tier or plan bundle | Nothing: a tier is granted, not consumed | Nothing |

So a row whose forecast covers both windows keeps the opportunity as its driver while its
figures come from the forecast, and an opportunity's or use case's units count only in the
windows the forecast leaves. A use case's draw on its card always comes from its own lines;
an opportunity [draws nothing](#an-opportunity-draws-nothing).

## The team's forecast wins

A row's `forecastUnits` are the team's attestation, already in the plan file (Step 9.4),
so they outrank what the opportunity lines imply. The windows count fiscal quarters, from
`resolve-quarters.mjs`: `q1` is the quarter after the one holding `asOf`.

| Window | Quarters it counts |
| --- | --- |
| +6 months | `q1` and `q2` |
| +12 months | `q1` to `q4` |

- **Only quarters that start before the contract's renewal date count**, in both windows:
  a quarter after the renewal is a renewal question, and +12 months always includes the
  +6-month figure. A renewal inside the six-month window cuts both at it. A plan with no
  renewal date counts all four. When no quarter starts before the renewal, the forecast
  gives neither window.
- **Every counted quarter must be set** for the forecast to give the window. A window
  with an empty counted quarter falls back to the opportunity rule, window by window: a
  forecast of `q1` and `q2` only gives +6 months, and +12 months stays the
  opportunities' figure. When that leaves the +6-month figure above the +12-month one, a
  conflict line names the row, since +12 months includes +6.
- **The row's basis decides the roll-up** ([quarter-basis.md](quarter-basis.md#peak-versus-cumulative)).
  The plan row carries no basis of its own, so its kind (else its category) decides: a
  `Consumables` row adds its quarters; a `Users` or `Robots` row, and any other consumed
  row, takes the window's busiest quarter less its consumed figure, never below `0`, and
  no figure when it has no consumed figure.
- **A seat or robot forecast with no consumed figure writes nothing** in the windows it
  covers: a new Renewal Test row with nothing else to say is not added, an opportunity
  figure this plan wrote earlier stays (it is not refreshed to no figure for that reason
  alone), and a conflict line names the missing `consumedQuantity`.
- **A `0` from the busiest-quarter floor** (the forecast at or below what is consumed) is
  written, with a conflict line saying so: with no pipeline driver the app shows the row
  as Not adopted, so the gap list asks the team to confirm it.
- **Source and date.** The finding's source is `team forecast (forecastUnits)`, dated by
  the row's `consumedAsOf`, else the plan's `asOf`. The driver keeps its own source, in a
  finding of its own.
- **The refresh rule applies.** An opportunity figure this plan wrote earlier is
  refreshed to the forecast's on the next run (with the reason "refreshed from the team
  forecast"); a figure the team entered in the app stays, with a conflict line giving the
  forecast's figure.
- **Reconfirm it every review.** A forecast keeps outranking the opportunities after its
  stated basis is overtaken (a go-live slips, a program grows), so the hand-off lists every
  forecast that gave demand for the team to reconfirm or restate.

## The rule

An open, non-renewal opportunity's product quantities are stated demand on the plan rows
they map to, timed by its close date, and so are a use case's once it states a start
date, timed by that, in every window the team's forecast leaves. Counted from the plan's
`asOf`:

| Close date (a use case's start date) | +6-month demand | +12-month demand |
| --- | --- | --- |
| Before `asOf` (stale) | nothing | nothing |
| `asOf` to `asOf` + 6 months | counts | counts |
| After `asOf` + 6 months, to `asOf` + 12 months | nothing | counts |
| After `asOf` + 12 months | nothing | nothing |

- Both windows include their last day, and a close date equal to `asOf` counts. A
  month-end `asOf` clamps: 31 August + 6 months is 28 February.
- The windows are cumulative: +12-month demand includes the +6-month units.
- Several opportunities and use cases on one row add up.
- A row that nothing sizes (no opportunity, use case or team forecast) keeps `null`
  demand, never `0`. `0` says the team stated nothing is mapped, and the app renders it as
  "Not adopted".
- A line on the row with `units: null` makes the row's figure unknown in each window its
  opportunity closes in: that window's demand is `null`, not the sum of the sized lines,
  which would look complete. The opportunity still drives the row.

### "Line items are new sales, not consumption"

This objection is why drafts used to come back with every demand cell empty. It is
settled for this skill, for demand: an open opportunity's product quantities **are** the
stated forecast for the rows they map to, and its close date is when they land. The field
instructions' "only a stated forecast for the mapped pipeline" is met by the opportunity
itself: the account team's own forecast, in the system of record, in each row's unit. The
objection does hold for draws: a draw's "sized figure from the pursuit's design or
estimate" is a use case's sizing, never an opportunity's lines, since those are new
entitlement ([An opportunity draws nothing](#an-opportunity-draws-nothing)).

- **It is not double counting.** The Renewal Test measures demand against today's
  entitlement: % after is (consumed + 12-month demand) ÷ purchased, and above 100% the
  app reads "Capacity uplift". An expansion opportunity is exactly that signal.
- **Units come from quantities, never from dollars.** An opportunity's `Amount` sizes
  nothing, and no figure is back-solved from it.
- **The team's stated forecast wins.** When the enrichment sweep finds the team's
  quarterly forecast for a row, it goes into `forecastUnits` and gives that row's demand
  in every window it covers, whatever the opportunity lines say
  ([above](#the-teams-forecast-wins)). Opportunity figures carry the opportunity's
  last-modified date as their as-of date.

## An opportunity draws nothing

A pursuit card's draw is use of the entitlement the account already holds: the app prices
it at today's contracted unit prices as the card's Est. rev., and the Renewal Test counts
it within the row's 12-month demand. An opportunity's product lines are new entitlement
the customer is buying, so no opportunity (open, stale, renewal or any other, whatever its
close date) draws on today's rows: `pipeline.mjs` writes no `/snapshot/pursuits` draw for
one. Only a pursuit the team sized draws ([Use cases](#use-cases-pursuits-the-team-sized)).

- **Its lines still count everywhere else.** They give its record (products, the rows it
  touches, projected consumption), the Renewal Test demand of the rows they map to in
  every window the team's forecast leaves, the row's pipeline driver, and, when the cards
  do not show it, other pipeline activity priced at contracted unit prices.
- **Units come from quantities, never from its amount**, here as everywhere: no draw, and
  no other figure, is back-solved from it.
- **Its card shows no Est. rev.** When the app shows an opportunity on a card, Known
  pipeline demand stays blank, and the gap list's "blocks Known pipeline demand" item asks
  the AE to pick top pursuits that draw on existing entitlement (team-sized use cases),
  then rerun Step 9.5 on the exported draft.
- **A draw an earlier run wrote is reported, never cleared.** On a draft that still holds a
  draw this plan wrote for an opportunity (before this rule), a refresh neither refreshes
  nor clears it: a conflict line names the rows ("this plan no longer draws for
  opportunities") and the AE removes them in the app. A draw line the team changed or
  cleared is the team's, and one it already removed leaves nothing to say.

## Which opportunities go in the plan file

Query every open opportunity (`IsClosed = false`) on every Salesforce account in scope,
with its line items. Write each one to `pipeline.opportunities[]`, renewals and stale ones
included: the script sets them aside itself, and reports the stale ones.

| Opportunity | `isRenewal` | What the script does |
| --- | --- | --- |
| `Type = 'Renewal'` | `true` | Nothing: not demand, not a card, not other activity, not in the document |
| Close date before `asOf` | `false` | Nothing, and a gap-list item asks the AE to re-date or close it |
| Close date more than 12 months after `asOf` | `false` | A record in the document, and other activity when it is not a card; no demand |
| Any other | `false` | Demand, a record in the document, and other activity when it is not a card |

None of them draws: an opportunity's lines are new entitlement
([above](#an-opportunity-draws-nothing)).

A renewal-named opportunity of another type whose close date has passed is caught by the
stale rule. Cut every Salesforce timestamp (`LastModifiedDate`) to its `YYYY-MM-DD` date.

**Name and stage must fit the app.** The v1.12 field instructions take an opportunity
name of at most 48 characters with no word over 17, and a stage of at most 20 characters
with no word over 14 (`apply-findings.mjs` names any limit it refuses). When Salesforce's
value is longer, write a faithful short form in the plan file ("Technical Qualification"
becomes "Tech Qualification") and give the full value in the hand-off. Never let the run
stop on it.

**The amount.** `amountUsd` is the amount field the org's Opportunity schema guidance
names as the authoritative annual value, else `Amount`; the hand-off names which. It
becomes the record's estimated IARR, which only ranks the pursuit cards: no demand, draw
or other activity is ever sized or priced from it.

## Decoding line units

`units` is the line's quantity times its bundle size, decoded exactly as entitlements are.
Reshape the line items into the subscription shape and run `decode-entitlements.mjs`
(which uses `volumeFromName` and `matchSku`):

```json
[{ "SBQQ__ProductName__c": "<Product2.Name>", "ProductCode": "<ProductCode>", "SBQQ__Quantity__c": <Quantity> }]
```

```bash
node "<skill root>/scripts/decode-entitlements.mjs" "<working folder>/<account>-opportunity-lines.json" \
  --pricebook "<dashboard repo>/src/data/uipath-pricebook.json"
```

| Decoder output | `units` |
| --- | --- |
| The product name states a volume ("AI Unit Bundle - 250K", "(5)", "250 Users") | its `soldQuantity` |
| `matchedBy` is `productCode` or `name` | its `soldQuantity` |
| `soldQuantity` is `null`, or `matchedBy` is `unmatched` and the name states no volume | `null` |

A line with `units: null` is reported as unsized; it is never counted as 1, nor as 0. Its
row's demand in its window, the other pipeline activity it is part of and, on a use case,
its draw (written with no units, so the app withholds the card's Est. rev.) stay blank
until it is sized. A line with a negative quantity is an amendment credit, never demand: leave it out
of `lines` and name it in the hand-off. Keep its opportunity, which the stale rule usually
catches.

## Mapping each line to a plan row

`row` names the plan row of the same consumable, by the rule that combines bundle-size
variants into one row in Step 3: every AI Unit bundle maps to the AI Units row, every
Unattended Robot SKU to the Unattended Robot row.

- Write the plan row's `product` exactly. When two plan rows carry that product, write
  `"<category>|<product>"`; the script refuses the bare name.
- Write `""` when the account holds no row for the product (a product it never bought).
  The line adds nothing, and the gap list asks the AE to confirm.
- **Leave out a platform tier or plan bundle line the plan has no row for.** It is not
  consumption and not a new purchase decision, so it does not go into the plan's `lines`
  with `""` (which would raise a "never-bought product" item): leave it out, as a
  negative-quantity credit is, and name it in the hand-off.
- **An opportunity whose lines are all never-bought products** still goes into the
  document as an opportunity record (name, stage, amount, products), but it gets no
  `projectedConsumption` and no Renewal Test row: it touches no entitlement the account
  holds. Its "never-bought product" item asks the AE whether it is a new purchase. When
  the app ranks it onto a pursuit card, the card has no Est. rev. (no opportunity draws),
  so Known pipeline demand stays blank, and a "blocks Known pipeline demand" item names it.
- A line on a `Platform / Capabilities` row (a platform tier, a plan bundle) maps to that
  row and adds no demand, no draw and no other activity: a tier is granted, not consumed.
  A row is a platform tier by its `kind` when it has one, else by its `category`. In a
  grouped plan (a category per contract or program) the category is only a label, so set
  `kind` on every row: without it the tier's line counts as demand (and a use case's line
  draws on the row). Platform Units, and every other unit bundle, are `Consumables` even
  where the pricebook files them under platform: they are metered units, so their lines do
  add demand (and a use case's draw), and a row filed as a tier would lose both.

## Use cases: pursuits the team sized

A pursuit the team sized in its own workbook or deck, with no Salesforce opportunity, goes
into `pipeline.useCases[]` (Step 9.4 writes it from the sweep):

```json
{ "key": "invoice-intake-agent", "name": "Invoice intake agent",
  "source": "<workbook or deck title, tab or slide, date>", "asOf": "YYYY-MM-DD",
  "startDate": "YYYY-MM-DD", "amountUsd": null,
  "lines": [{ "product": "AI Units", "units": 200000, "row": "AI Units" }] }
```

- **`key`** is a stable slug of the team's own name for it: lower-case letters and
  digits joined by hyphens, at most 80 characters, unique among the use cases and never
  an opportunity's Salesforce id. It keys the record in the document, so keep it the same
  on every refresh. `name` fits the app as an opportunity name does.
- **`lines`** follow the opportunity line rules: `units` in the row's unit (`null` when
  the team gave none, which withholds as an unsized opportunity line does), `row` the plan
  row's product, `"<category>|<product>"`, or `""` for a product the account never bought.
- **`startDate`** is optional: when the source says when the pursuit starts consuming, it
  times the use case's demand as a close date times an opportunity's. With none, the use
  case adds no demand and drives no row. One before the plan's `asOf` adds no demand
  either: if the pursuit is live, its use is already in the row's consumed figure, and the
  gap list asks the CSM to confirm it is ("already started"). One more than 12 months after
  `asOf` gets no draw: it adds nothing in the window, so its draw would read as an
  overdrawn row.
- **`amountUsd`** only when the source states new ARR.

What the script does with each one, as it does with an opportunity except for the draw,
which only a use case gets: the team sized it on the entitlement the account already holds.

| | A use case |
| --- | --- |
| Record | A `/pipelineOpportunities` record keyed by `key`: name, status `Open`, products, the rows it sizes, projected consumption, and estimated iARR: `amountUsd`, or `0` when the source states none, with the basis "draws on existing entitlement; no new ARR" in that finding's source. No stage, owner, motions or next gate: the gap list names them as the use case's ("Use case stage") and asks for each from the team's own tracker, since the pursuit has no Salesforce record |
| Pursuit draw | On every consumed row it sizes, unless it starts more than 12 months after `asOf`; with no start date it draws. An unsized line on the row draws with no units; platform and unmapped lines draw nothing. A draw that adds no demand (no start date, or one already started) can leave the row overdrawn, which the gap list names |
| Renewal Test demand | Only with a `startDate` from `asOf` on, timed as a close date, and only in windows the row's team forecast leaves; it drives the row either way |
| Other pipeline activity | Counted when the cards do not show it, as an unshown opportunity is |
| Refresh, removal, departure | The same rules: a record of the same name with no key is adopted (its key set), one keyed otherwise is left alone with a re-key line, and what the team changed or deleted stays. A use case dropped from the plan is reported, never cleared |

When Salesforce later carries the pursuit as an opportunity, drop the use case from the
plan: its departure line asks the AE to remove the use case's record, and the
opportunity's re-key line (a record of its name keyed by the slug) asks to re-key it.

## What the script writes

**Numbers stage** (`--stage numbers`), on the document `to-day2.mjs` built:

- `renewalDate` and `snapshot.contractStartDate` from the plan's `contract`.
- One `pipelineOpportunities` record per open, non-stale, non-renewal opportunity, keyed
  by its Salesforce id: name, stage, amount, status `Open`, products, the rows it sizes,
  and its projected consumption ("AI Units: 400000 units; Unattended Robot: 20 robots").
  A record is found by its key compared as the app compares keys (NFKC, trimmed,
  lower-cased, hyphens and underscores read as spaces, whitespace collapsed), since the
  app blocks publication on two keys that agree that way; the findings then address it
  by the key it already holds, so a team spelling (`Invoice_Intake Agent`) is filled, not
  duplicated. Repeated Salesforce ids and use-case keys are refused by the same comparison.
  The app keys an opportunity the team added in the app as `""`, so a record of the same
  name (compared ignoring case, spacing and punctuation) with no key is claimed: a
  finding sets its key to the Salesforce id, and the record is filled, not duplicated. A
  record of the same name keyed otherwise is left alone, with no second record, and a
  conflict line asks the AE to re-key it.
- One `pipelineOpportunities` record per use case, keyed by its `key`, and, for a use
  case starting within 12 months (or undated), a pursuit with a unit draw on every
  consumed row it sizes (no units where a line there is unsized;
  [above](#use-cases-pursuits-the-team-sized)). The app prices the draw at the account's
  contracted unit prices to show Est. rev.; nothing stores that dollar figure. No
  opportunity gets a pursuit ([An opportunity draws nothing](#an-opportunity-draws-nothing)).
- A Renewal Test row per row an opportunity or timed use case in the window maps to, or
  the team forecasts: the driver (each mapped opportunity's name and close month, or use
  case's name and start month, "Invoice automation (Mar 27)"), and +6/+12-month demand
  (the team's forecast where it covers the window; else `null` in a window an unsized
  line closes in). The forecast's figures come in a finding of their own, sourced
  `team forecast (forecastUnits)`.

A pipeline driver always names an opportunity or a use case and when it lands. A remark
with no landing date ("the idle robots wait for the next rollout") is a lead for the
hand-off, never a driver.

**Final stage** (`--stage final`), after the enrichment sweep:

- `snapshot.otherPipelineActivityUsd`: every open opportunity and use case the Snapshot
  does not show as a card, each sized consumption line priced at its row's contracted unit price (row
  ARR ÷ purchased quantity), summed and rounded to whole USD. Salesforce amounts are
  never used: the field is entitlement value, the same pricing the app gives a card's
  Est. rev. Opportunities beyond the 12-month window are open and count here.
- **It is `0` when nothing else open draws on a priced row.** The open pipeline in
  Salesforce is the team's record of what it is pursuing, so a remainder of
  never-bought products, platform tiers, $0 rows or no lines is a stated `0`, and the
  Snapshot equation completes. The gap list names those opportunities and asks the AE
  to confirm they add nothing.
- It is no figure when a line off the cards has no units, or a sized line's row has no
  unit price (no ARR or no purchased quantity): a partial sum would look complete. A
  figure this plan wrote earlier is then cleared, as the refresh rule clears a draw or
  demand, and a figure the team entered stays. A conflict line names the lines, and says
  which happened. This is the usual case when the team names other top pursuits and an
  unsized line falls off the cards.

This stage runs last because the cards depend on the document: the app shows the
opportunities ranked by customer value, else amount, and a customer value the sweep finds
can reorder them. The script mirrors that ranking to know which three are cards. When the
team names other top pursuits in the app, rerun this stage on the app's Export JSON: the
refresh rule updates the value this plan wrote.

## What the script never writes

- `snapshot.topPursuitIds`. The team names its top three in the app, or the app's
  default ranking stands. Ask the team to confirm the three in the hand-off: the ranking
  puts opportunities first (a use case with no stated amount ranks at $0), and an
  opportunity's card shows no Est. rev., so the team may name use cases instead.
- An opportunity's owner, motions, next gate and next-gate date, and every status,
  confidence, card status and healthy threshold. They are the team's. Offer the Salesforce
  owner (`ownerName`) as a suggestion in the hand-off; the gap list asks the AE.

## Refresh

Run the same commands on every refresh. The script decides each value against the
document and against `pipeline.written`, the record of what this plan last wrote:

| The document holds | Stage, amount, contract dates | Everything else the plan writes (name, status, products, row links, projected consumption, draws, driver, demand, other activity) |
| --- | --- | --- |
| Nothing, and `written` has no value there | Written | Written |
| Nothing, where `written` says this plan wrote a value | Written | Left blank: the team cleared it, and a conflict line says so |
| The same value | Left alone | Left alone |
| What `written` says this plan wrote | Replaced: Salesforce is the system of record | Replaced, with the refresh reported (to no figure, when a line became unsized) |
| Anything else | Replaced: Salesforce is the system of record | Kept as the team's, and a conflict line says what Salesforce, the use case or the team forecast now gives (none when it gives no figure) |

So a name the team shortened stands, while a name this plan wrote follows Salesforce.

A use case's stage is not the plan's (it has none), and its amount follows the refresh
rule like its other fields: the team's workbook is not a system of record.

A record this plan added that the team deleted in the app (an opportunity or use-case
record, a use case's pursuit card, one of its draw lines, a Renewal Test row) is not added
again: a conflict line says so, and the AE adds it back in the app if the removal was a
mistake.

An opportunity, use case, draw or Renewal Test row the plan wrote that no longer has a
source (the opportunity closed or went stale; the use case left the plan, lost the line or
now starts more than 12 months out) is reported, never cleared: the AE confirms and removes
it in the app. So is a draw an earlier run wrote for an open opportunity that its card
still holds: the line says this plan no longer draws for opportunities, and the AE removes
it. A row the team's forecast now sizes alone keeps the driver this plan wrote, and a line
says so.

`written` is maintained by `--record`, and holds `null` where this plan wrote no figure.
Never edit it by hand, except to delete keys for items the AE has already resolved, which
stops their lines repeating; deleting the keys of a cleared value or a removed record also
lets the next run write it again.

## The command order

```text
pipeline.mjs findings --stage numbers --out --conflicts   (document from to-day2.mjs)
apply-findings.mjs                                        (writes the numbers document)
pipeline.mjs findings --stage numbers --record            (against the numbers document)
  ... enrichment sweep, and a row re-merge if it found usage statements, forecasts or use cases ...
  ... whenever the sweep changed the plan file: the numbers stage again (its three lines), on the re-merged document ...
pipeline.mjs findings --stage final --out --conflicts     (against the enriched document)
apply-findings.mjs                                        (writes the final document)
pipeline.mjs findings --stage final --record              (against the final document)
  ... the team names other top pursuits in the app: the final stage again, on its export ...
```

The numbers stage is idempotent (a second run on its own output finds nothing to change),
so rerun it whenever the sweep changed the plan file, not only when it wrote a forecast or a
use case: a consumed figure the sweep brings moves a seat or robot forecast's demand, which
is the window's busiest quarter less what is consumed, and the workbook (printed from the
plan file) and the draft would otherwise disagree.

`--record` refuses while any finding is unapplied, which keeps `written` honest: it
records only values the document holds.

## The workbook's demand columns

The workbook's "+6-mo pipeline demand" and "+12-mo pipeline demand" columns show the
Renewal Test's figures per row: the team's forecast where it covers the window, else this
rule's. Print them from the plan file:

```bash
node --input-type=module -e '
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
const [scripts, planPath] = process.argv.slice(1);
const { pipelineDemand } = await import(pathToFileURL(`${scripts}/pipeline.mjs`).href);
for (const [row, d] of pipelineDemand(JSON.parse(readFileSync(planPath, "utf8"))).byRow) console.log(`${row}\t${d.demand6MoUnits}\t${d.demand12MoUnits}`);
' "<skill root>/scripts" "<working folder>/<Account Name>_Consumption_Plan.json"
```

A row it does not print has no demand: show `TBD - no sized pipeline` in the workbook,
and leave it `null` everywhere else.

## What the gap list says

`gap-list.mjs` gives every remaining blank one item: what is missing, why, the owner role
and the next step. Blocking items come first, then the deck's tab order.

| Why | When | Owner |
| --- | --- | --- |
| blocks Snapshot Consumed | A row other than a $0 one (platform tiers included) has no consumed figure or no contracted price, as the app reads them, so the Snapshot withholds Consumed and Remaining. One item per row, naming its own reason (no source, partial coverage, estimate, no contracted price) and next step | TAM; CSM for user licenses; AE for a row missing only its price |
| blocks Known pipeline demand | A pursuit card the app shows has no Est. rev.: no pursuit or draw (every opportunity, whose lines are new entitlement, and a use case starting more than 12 months out), an unsized draw, or a draw on a row with no contracted price. An opportunity's card asks the AE to pick top pursuits that draw on existing entitlement (team-sized use cases); a use case's asks to size its draw, or re-date it. Choosing other pursuits means rerunning Step 9.5 on the exported draft | AE |
| overdrawn | The shown cards draw more of a row than its 12-month demand, which the app footnotes on the Renewal Test (the draws are part of that demand): a team forecast below a use case's sizing, or a use case with no start date or one already started. Reconcile the forecast with the sizing, or date the use case; a draw on an opportunity's card counts as the app counts it, and the AE removes it | AE |
| already started | A use case whose start date is before the plan's `asOf`: confirm it is live (its use is then in Consumed, so drop it), or give the date it will start | CSM |
| no source | A field a dated source could fill, and none did; a consumed figure nothing measured on a $0 row (a priced one blocks Snapshot Consumed) | By field: CSM by default, AE for pipeline fields, TAM for consumed figures (CSM for user licenses) |
| partial coverage | The same, where telemetry covers only part of the account, or the row's `consumedBasis` is `coverage-gap` (listed whatever figure the document holds, since the merge clears a baseline figure for it) | TAM; CSM for user licenses |
| estimate | A robot figure from the estimate, to confirm or replace | TAM |
| unlicensed in use | A row's `unlicensedInUse`: robots running on trial or unlicensed keys beyond those purchased, not in Consumed. Settle their licensing before the keys lapse or the robots are counted | TAM |
| stale opportunity | An open opportunity whose close date has passed: re-date or close it | AE |
| never-bought product | A line no plan row can take (a platform tier or plan bundle with no row is left out of the plan's lines instead): confirm it is a new purchase, or map it | AE |
| unsized line | An opportunity line with no decoded volume, or a use-case line the team gave no units: state its units (a use case's in the plan file) | AE |
| team only | A field only the team states, including a `0` other pipeline activity to confirm, naming the open opportunities and use cases off the cards valued at $0 | By field: AE, CSM, or AE + CSM + TAM for the healthy threshold |
| conflict | A team value kept against Salesforce's, a use case's or the team forecast's; a value the team cleared or a record it deleted, left so; a same-named record to re-key; something the plan wrote that lost its source (a use case dropped from the plan included); a draw an earlier run wrote for an opportunity, still on its card; or a note on the team forecast's roll-up (+6 months above +12, a seat or robot forecast with no consumed figure, a `0` from the busiest-quarter floor) | AE |

## Where each rule lives

| Rule | `pipeline.mjs` export |
| --- | --- |
| Reading and checking the plan's `contract`, `pipeline.opportunities` and `pipeline.useCases` | `readPipeline` |
| Windows, stale and renewal set-asides, unmapped and unsized lines; the team forecast's precedence | `pipelineDemand` |
| The quarters each window counts, cut at the renewal | `forecastWindows` |
| Platform rows and unmapped lines add nothing; unsized lines withhold | `isConsumptionLine` |
| Contracted unit price per row (ARR ÷ purchased) | `unitPriceByRow` |
| The app's top-three ranking | `shownPursuitKeys`, `shownPursuits` |
| Other pipeline activity, `0`, unpriced and unsized lines | `otherActivityUsd` |
| Numbers-stage and final-stage findings, with the refresh rule, cleared values, removed records and claimed opportunities and use cases | `numberFindings`, `otherActivityFindings` |

`gap-list.mjs` turns the plan, the final document, `gap-inventory.mjs --json` and the
conflicts files into the gap list; `OWNER_ROLES` there says who closes each field.
