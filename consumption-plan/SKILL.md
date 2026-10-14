---
name: consumption-plan
description: Build a per-account UiPath license consumption plan (Excel) from Salesforce data — active contracts, products, ARR, discount %, and purchased quantities — then leaves utilization and quarterly forecast blank until the user supplies project plans, PMRs, pipeline, or utilization data to inform them. Use when asked to create, build, or update a license consumption plan, utilization tracker, or renewal forecast workbook for one or more customer accounts.
---

# Consumption Plan Builder

Builds a standalone Excel workbook per account, tracking purchased licensing against
ARR, allocation/utilization, and a forward-looking quarterly consumption forecast —
so an account team can see at a glance what's been sold, what's being used, and where
demand is headed before renewal.

This skill was developed against an account with several contracts and a
customer-maintained allocation tracker. That account's extra tabs are **exceptions, not
the default** — see "Multi-contract exceptions" at the bottom before assuming any account
needs them.

## Step 1 — Connect to Salesforce

Look for an already-connected Salesforce MCP connector before falling back to anything else:

```
ToolSearch: query "salesforce" or "soql", max_results 10
```

Tool names carry a per-connection UUID prefix (`mcp__<uuid>__soqlQuery`, `...__find`,
`...__getObjectSchema`, `...__getRelatedRecords`, `...__getUserInfo`) — load them once
with `ToolSearch` and reuse for the whole session.

**Gotchas learned the hard way:**
- A Salesforce connector approved in someone's individual claude.ai chat does **not**
  carry over to a Claude Code CLI session — the two surfaces don't share connector
  state. If `ToolSearch` finds nothing, ask whoever administers connectors to add it
  at the **team/workspace level** for Claude Code specifically, then retry `ToolSearch`
  after a restart.
- If no MCP connector is available at all, fall back to the `sf` (Salesforce CLI) —
  check with `which sf`, and if present, `sf org login web --instance-url
  <org url> --alias <alias> --set-default` (the user runs the browser login
  themselves), then use `sf data query --query "..." --target-org <alias> --json`.
  MCP is strongly preferred once available — it's faster and doesn't need re-auth
  every session.

## Step 2 — Get the account list

Ask the user which account(s) to build plans for. Take the list as given, but confirm
each name resolves to exactly one Salesforce Account before proceeding:

```sql
SELECT Id, Name FROM Account WHERE Name LIKE '%<keyword>%'
```

If a search returns more than one plausible match, confirm with the user which one
before continuing — don't guess.

## Step 3 — Pull active contracts + licensing per account

For **each** account, in order:

**3a. Active contracts:**
```sql
SELECT Id, ContractNumber, Status, StartDate, EndDate,
       SBQQ__Opportunity__c, SBQQ__Opportunity__r.Name,
       SBQQ__Opportunity__r.CloseDate, SBQQ__Opportunity__r.Amount
FROM Contract
WHERE AccountId = '<account id>' AND Status = 'Activated'
ORDER BY StartDate
```

**3b. Products + pricing per contract's Opportunity** (this carries ARR, list price,
discount, and quantity — better than `SBQQ__Subscription__c` for pricing, since
subscriptions don't reliably carry price fields):
```sql
SELECT OpportunityId, Product2.Name, ProductCode, Quantity, ListPrice, UnitPrice,
       Discount, TotalPrice, Product_Family__c
FROM OpportunityLineItem
WHERE OpportunityId IN ('<opp id 1>', '<opp id 2>', ...)
ORDER BY OpportunityId, Product2.Name
```

**3c. (Optional cross-check)** — `SBQQ__Subscription__c` filtered by
`SBQQ__Contract__c` gives term start/end dates per product line and is useful to
confirm segmentation (see pitfall below), but don't rely on it for pricing.

**Reconcile before moving on:** sum each contract's line-item `TotalPrice` and confirm
it equals that Opportunity's `Amount`. If it doesn't match, find out why before
building anything — don't present unreconciled numbers.

**Watch for ramped/segmented lines:** CPQ sometimes splits one product into multiple
subscription segments within a single contract term (e.g., two 6-month periods with
different unit prices). If the **quantity is constant** across segments, sum the
`TotalPrice` values for a full-year ARR and report one line. If the **quantity differs**
across segments, that's a genuine ramp — reflect it, don't flatten it away.

**Combine bundle-size variants of the same consumable into one line.** If a contract
has, say, both a 1M-unit and a 250K-unit bundle of the same consumable (e.g., AI Units),
convert each to total actual units (quantity × bundle size) and report a single combined
row — utilization should be tracked against total units of that consumable, not package
counts of a specific bundle size.

## Step 4 — Build the workbook (one Excel file per account)

**Default: one tab per account**, covering all of that account's active contracts
combined into a single product table — do **not** split into multiple tabs unless the
account has genuinely distinct, separately-run programs under the same account (rare;
confirm with the user before splitting).

**Columns** (left to right):

| Category | Product | ARR | % of Total ARR | Discount % | Purchased Qty | % Utilized / Allocated | Q1 | Q2 | Q3 | Q4 | Comments / Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|

- **Category** groups products (merge repeated cells within a group): **Users**
  (Attended, Automation Developer, Citizen Developer, Action Center, Tester, etc.),
  **Robots** (Unattended Robot, Unattended Robot Test), **Platform / Capabilities**
  (Platform Standard/Advanced, Tailored Offering, Plan Bundle), **Consumables**
  (AI Unit Bundle, Apps Units Bundle, etc.)
- **ARR** — annual value per product (see reconciliation note above)
- **% of Total ARR** — that row's ARR ÷ the account's total ARR across every product
  line in the table (the account's grand total, not any per-category subtotal).
  Compute this for every account's plan, always — it's what tells the account team
  which product lines actually move the needle and are worth prioritizing for
  utilization/expansion conversations, versus which are rounding errors. Format as a
  percentage; the column should sum to ~100% across all product rows (excluding the
  totals row) as a sanity check on the arithmetic.
- **Discount %** — computed from `1 - UnitPrice/ListPrice`
- **Purchased Qty** — combined across all of that account's active contracts
- **Q1–Q4** — quarterly forecast columns for the contract year (label with actual
  calendar-quarter date ranges, e.g. "Q3 2026 (Jul-Sep)", so the meaning is unambiguous
  even across contracts with different start dates)
- **Comments / Notes** — always cite the specific artifact behind any forecast or
  utilization claim (see Step 6)

**Formatting** (mirrors the team's `TEMPLATE Consumption Plan.pptx` structure, adapted
to Excel — do not copy the pptx template literally, just its column/grouping logic):
navy header row with white bold text, light category-tinted row bands, currency
format on ARR, percent format on Discount/% Utilized, wrapped text on the forecast and
comments columns, a bold totals row, and a "Last Updated" footer.

**File naming:** one workbook per account, e.g. `<Account Name>_Consumption_Plan_DRAFT.xlsx`.

## Step 5 — Leave utilization and forecast blank

On first pass, populate only what Salesforce tells you: Category, Product, ARR,
Discount %, Purchased Qty. Leave:
- **% Utilized/Allocated** = `"TBD - team to provide"`
- **Q1–Q4** = `"TBD - awaiting utilization/pipeline data"`
- **Comments** = blank or a placeholder noting what's needed

Do not fabricate utilization or forecast numbers. This is current-state licensing only
until Step 6 supplies real signal.

## Step 6 — Prompt for supporting artifacts, then fill in utilization + forecast

Ask the user (per account) for anything that can inform actual usage and forward
demand:
- Project plans / Gantt charts (PDF, MS Project exports — these are often huge
  image-based PDFs; extract embedded images and read them in slices rather than
  assuming text extraction will work)
- Program Management Reviews / status decks (pptx) — extract with `python-pptx` or
  `markitdown`
- Backlog / pipeline — open (non-Closed-Won) Opportunities on the account
- Utilization screenshots or spreadsheets (Orchestrator exports, License Management
  reports, customer-maintained trackers)

When you use one of these to inform a forecast, **name it explicitly** in the Comments
column (artifact name/date, and the specific fact driving the call — a milestone date,
a go-live, a program expansion) so anyone reading the plan later can trace the reasoning
back to its source.

**If a customer-supplied tracker has its own subtotals/grand totals**, foot them
yourself (cross-check columns against rows) before trusting them — don't propagate a
source document's own arithmetic errors into the plan. A running-subtotal row counted
inside its own column sum, for example, inflates an allocation and raises a false
"over-allocated" alarm.

## Multi-contract exceptions (do not apply by default)

Two structures exist for accounts that genuinely need them, and should **not** be
replicated automatically:

1. **A tab per separately-run program.** The default (Step 4) already combines an
   account's active contracts into one table, including several contracts that fund one
   shared license pool. Split by contract or program only when one account holds a
   distinct program for a different organization, with its own contract, and confirm
   with the user before splitting.
2. **A tab importing a customer-maintained allocation tracker**, breaking pooled
   licensing down by sub-organization — only if the account has such a document *and*
   the user asks for it. Don't assume one exists.

Every other account gets the plain two-part structure: current licensing plus whatever
forecast and utilization signal the supporting artifacts turn up — no extra tabs unless
the account specifically calls for them.
