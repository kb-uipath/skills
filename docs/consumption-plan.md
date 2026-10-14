# consumption-plan

Builds one license consumption plan per customer account from Salesforce — active
contracts, products, ARR, contracted discount, purchased quantities — and renders it
twice from the same plan file: an Excel workbook, and the Consumption Plan tab of a Day 2
Review document (schema version 1.11).

## When To Use

Use when an account team needs to see what was sold, what is being used, and where
demand is headed before renewal, or when a Day 2 draft's Consumption Plan reads
"Not measured". Do not use it to estimate utilization from entitlement; utilization and
forecast stay empty until an artifact supplies them.

## Runtime And Dependencies

- A Salesforce MCP connector, or the `sf` CLI as a fallback, with read access to
  Account, Contract, OpportunityLineItem and SBQQ__Subscription__c.
- Node.js 20 or newer for `scripts/`; standard library only.
- The Day 2 Review dashboard repository for `to-day2.mjs --repo` and for validation
  with `enrich-day2-dashboard`'s `validate-day2-json.mjs --repo`.

## Inputs

- The account name(s), each resolved to exactly one Salesforce Account.
- A plan file written by the skill, `<Account>_Consumption_Plan.json`, versioned by the
  Day 2 schema it targets: rows of `category`, `product`, `productCode`, `unit`,
  `licensingModel`, `arrUsd`, `discountPercent`, `purchasedQuantity`,
  `consumedQuantity`, `forecastUnits.q1`–`q4`, `notes`, plus `asOf`.
- Optional: a baseline Day 2 document to merge into, and supporting artifacts (project
  plans, program reviews, pipeline, utilization exports) for utilization and forecast.

## Prompt

`Use $consumption-plan to build the consumption plan for <account> and feed its Day 2
Consumption Plan tab.`

## Outputs

- `<Account>_Consumption_Plan_DRAFT.xlsx` — the workbook.
- `<account>.day2.json` — the Day 2 document with its `consumptionPlan` filled, plus a
  merge report: rows matched, added, kept, and every changed figure.

## Runnable Example

    node consumption-plan/scripts/resolve-quarters.mjs 2026-08-01
    node consumption-plan/scripts/to-day2.mjs consumption-plan/tests/fixtures/illustrative-plan.json \
      --repo "<dashboard repo>" --out example.day2.json

## Failure Recovery

- `to-day2.mjs` exits 1 and names the field when a plan row carries placeholder text, a
  non-numeric quantity, a discount over 100, or an `asOf` that is not `YYYY-MM-DD`. Fix
  the plan file and rerun; nothing is written on failure.
- Unreconciled Salesforce totals stop the build at Step 3: find the cause before
  writing any plan.

## Safety

- Read-only against every source system.
- Never fabricates utilization or forecast, never writes a derived figure, and never
  lets an empty plan field erase a value already in the Day 2 document.

## Data Classification And Retention

Plan files, workbooks and Day 2 documents are confidential customer artifacts. Keep
them out of every git repository, including this one, and in the user's working folder.

## Known Limitations

- The in-app Day 2 assistant cannot yet propose `discountPercent` or row notes.
- Utilization depends on artifacts the user supplies; there is no telemetry pull.

## Certification Status

Offline workflow validated with `node --test`; not yet exercised end to end on a real
account.

## Last Verified

Last verified: 2026-10-14

## Validation

    node --test consumption-plan/tests/*.mjs
