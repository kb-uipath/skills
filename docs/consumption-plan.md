# consumption-plan

Fills every number on a Day 2 Review draft for one customer account, then hands off to
`enrich-day2-dashboard` for the words. It builds one license consumption plan from
Salesforce (active contracts, products, ARR, contracted discount, purchased quantities,
open opportunities) and governed telemetry, and renders it twice from the same plan
file: an Excel workbook, and the numbers of a Day 2 Review document — the consumption
rows, contract dates, pipeline opportunities, the use cases' pursuit draws, Renewal Test
demand and the other pipeline activity on `/day2-v7` (schema version 1.12), or the
Consumption Plan tab on `/day2-v6` (schema version 1.11). The team's own quarterly
forecast gives a row's Renewal Test demand ahead of the opportunities, and a pursuit the
team sized in its own workbook or deck becomes a pipeline record even without a
Salesforce opportunity. A Salesforce opportunity's product lines are new entitlement, so
an opportunity never draws on today's rows: only the team-sized use cases
(`pipeline.useCases`) draw, while an opportunity's quantities still give Renewal Test
demand on rows with no team forecast and still name the driver, and units are never
back-solved from an amount. Every blank that remains is listed with an owner role and a
next step.

## When To Use

Use when an account team needs a complete Day 2 draft or deck for an account, its
Snapshot or Renewal Test numbers filled, or a consumption plan built or refreshed: what
was sold, what is being used, and what the open pipeline will add before renewal. Also
use when a Day 2 draft's Consumption Plan reads "Not measured". It never estimates
utilization from entitlement; only a robot figure may be estimated, from the team's own
stated figures (or, when they give none, Salesforce's robot-utilization percentage), and
it is labelled and sent to the TAM to confirm.

## Runtime And Dependencies

- A Salesforce MCP connector, or the `sf` CLI as a fallback, with read access to
  Account, Contract, Opportunity, OpportunityLineItem and SBQQ__Subscription__c.
- Node.js 20 or newer for `scripts/`; standard library only.
- The `enrich-day2-dashboard` skill, whose `apply-findings.mjs`, `gap-inventory.mjs` and
  `validate-day2-json.mjs` the one run uses, and which writes the words.
- Optional, for consumption telemetry: the `account-portfolio-review` and
  `curated-data-interaction` skills, with the user signing in to Snowflake in the
  browser. Without them, consumption falls back to dated statements and the hand-off says
  telemetry was not reached.
- The Day 2 Review dashboard repository for `to-day2.mjs --repo`, the pricebook, and
  `--repo` validation.

## Inputs

- The account name(s), each resolved to exactly one Salesforce Account, and whether a
  customer spanning several accounts is one draft.
- A plan file written by the skill, `<Account>_Consumption_Plan.json`, versioned by the
  Day 2 schema it targets: `asOf`, `contract` (number, start date, renewal date), optional
  `telemetry` (as-of, coverage, note), rows of `category`, `product`, `productCode`,
  `unit`, `licensingModel`, `arrUsd`, `discountPercent`, `purchasedQuantity`,
  `consumedQuantity`, `consumedBasis`, `consumedAsOf`, `forecastUnits.q1`–`q4` (the
  team's forecast, which gives the row's Renewal Test demand in each window it covers),
  `notes`, optional `unlicensedInUse` (robots on trial or unlicensed keys: count, source,
  date; a TAM gap item, never written to the Day 2 row), `pipeline.opportunities[]` with each line's decoded `units` and plan `row`,
  optional `pipeline.useCases[]` (pursuits the team sized with no Salesforce opportunity:
  a slug `key`, `name`, `source`, `asOf`, optional `startDate` and `amountUsd`, and sized
  `lines`), plus `pipeline.written`, which the scripts maintain.
- Optional: a baseline Day 2 document to merge into, and supporting artifacts (project
  plans, program reviews, customer trackers, the team's own sizing workbooks or decks) for
  team forecasts and team-sized pursuits.

## Prompt

`Use $consumption-plan to complete the Day 2 draft for <account>.`

## Outputs

- `<Account>_Consumption_Plan_DRAFT.xlsx` — the workbook, with +6-month and +12-month
  pipeline-demand columns (the team forecast where it covers the window, else the
  opportunities and timed use cases) and a red "missing information and recommended next
  steps" block.
- `<account>.final.day2.json` — the Day 2 document with its numbers and words filled,
  delivered into the app as a draft; the archive save is left to the user.
- `<account>-gaps.md` and `<account>-gaps.json` — every remaining blank with why, an
  owner role (CSM, TAM, AE) and a next step.
- Merge reports, findings and conflicts files from each stage.

## Runnable Example

From the repository root, where `<skill root>` is `consumption-plan` and `<ED root>` is
`enrich-day2-dashboard`. The illustrative fixture is safe to run from the checkout, but
copy it to a scratch folder outside the repository first, because `--record` writes into
the plan file, and keep every output there:

    cp "<skill root>/tests/fixtures/illustrative-pipeline-plan.json" "<scratch folder>/plan.json"
    node "<skill root>/scripts/to-day2.mjs" "<scratch folder>/plan.json" --repo "<dashboard repo>" \
      --out "<scratch folder>/example.day2.json" --report "<scratch folder>/example-merge.md"
    node "<skill root>/scripts/pipeline.mjs" findings "<scratch folder>/plan.json" \
      --document "<scratch folder>/example.day2.json" --stage numbers \
      --out "<scratch folder>/numbers.findings.json" --conflicts "<scratch folder>/numbers.conflicts.json"
    node "<ED root>/scripts/apply-findings.mjs" "<scratch folder>/example.day2.json" \
      "<scratch folder>/numbers.findings.json" --out "<scratch folder>/example.numbers.day2.json" \
      --repo "<dashboard repo>"
    node "<ED root>/scripts/gap-inventory.mjs" "<scratch folder>/example.numbers.day2.json" \
      --repo "<dashboard repo>" --json > "<scratch folder>/inventory.json"
    node "<skill root>/scripts/gap-list.mjs" "<scratch folder>/plan.json" \
      --document "<scratch folder>/example.numbers.day2.json" --inventory "<scratch folder>/inventory.json" \
      --conflicts "<scratch folder>/numbers.conflicts.json" --markdown "<scratch folder>/gaps.md"

The full sequence, including the final stage and `--record`, is Step 9 of the skill.

## Failure Recovery

- `to-day2.mjs` exits 1 and names the field when a plan row carries placeholder text, a
  non-numeric quantity, a discount over 100, an `asOf` that is not `YYYY-MM-DD`, or an
  estimated consumed figure with no basis in its notes. Fix the plan file and rerun;
  nothing is written on failure.
- `pipeline.mjs` exits 1 and names the opportunity, use case, line or row when a date is
  not `YYYY-MM-DD`, a quantity or forecast quarter is negative or not a number, a line's
  `row` matches no plan row (or more than one; name it `"<category>|<product>"`), or a use
  case's key is not a slug, repeats, or is an opportunity's Salesforce id. `--record`
  refuses while any finding is unapplied: apply the findings first, then record against
  the document they wrote.
- `apply-findings.mjs` refuses the whole run on a value over the app's limits (an
  opportunity name over 48 characters or with a word over 17, a stage over 20 or with a
  word over 14): write a faithful short form in the plan file and rerun.
- Unreconciled Salesforce totals stop the build at Step 3: find the cause before
  writing any plan.

## Safety

- Read-only against every source system.
- Never fabricates utilization, never back-solves units from an opportunity amount, never
  writes a derived figure, and never lets an empty plan field erase a value already in
  the Day 2 document.
- Never writes the account team's calls: opportunity owner, motions, next gate, top
  pursuits, statuses, confidence or the healthy threshold. A value the team changed or
  cleared in the app, a name it shortened, and a record, pursuit card, draw line or
  Renewal Test row it deleted survive a refresh and are reported as conflicts. An
  opportunity or use case the team added in the app under its name is claimed, not
  duplicated. A use case with no stated amount is $0 of estimated iARR, never a figure
  back-solved from its units.

## Data Classification And Retention

Plan files, workbooks, Day 2 documents, findings, conflicts and gap lists are
confidential customer artifacts. Keep them out of every git repository, including this
one, and in the user's working folder.

## Known Limitations

- Governed robot and seat-allocation telemetry covers plain Automation Cloud only;
  Automation Suite, on-premises and Public Sector cloud deployments come back as
  coverage gaps (`consumedBasis: "coverage-gap"`, no figure, which clears a baseline `0`
  in the merge), and their robots fall back to a labelled estimate.
- Telemetry needs the user at the keyboard for the Snowflake browser sign-in.
- Departure lines for opportunities and use cases the plan wrote, and the lines for
  values the team cleared or records it deleted, repeat until their keys are deleted from
  `pipeline.written`.
- A team forecast outranks the opportunities until the team restates it, even after its
  stated basis is overtaken; the hand-off lists each one to reconfirm at every review.
- A forecast row's peak or cumulative roll-up comes from its kind, not the pricebook's
  metering basis, since the plan file carries no `forecastBasis`.
- Whether a row with no ARR of its own is priced is read from the account's ARR alone;
  the app also needs the row's SKU in its pricebook to allocate it a share.
- The in-app Day 2 assistant cannot yet propose `discountPercent` or row notes.

## Certification Status

Offline workflow validated with `node --test`; not yet exercised end to end on a real
account.

## Last Verified

Last verified: 2026-10-20

## Validation

    node --test "consumption-plan/tests/*.test.mjs"
