# Evidence And Field Rules

## Source Priority

Use account-specific sources before broad lists:

1. Account-specific SharePoint docs: success plans, handoffs, EBR/CVR decks, migration docs, proposals.
2. Account-specific TAM/ES SharePoint site repository files.
3. Account-specific OneNote sections or pages.
4. Account Slack channels or threads, if connector/auth works.
5. Account Teams channels/chats, if connector/auth works.
6. SFDC account-specific data, exports, opportunity/renewal docs, and account plans.
7. Workbook internal tabs: churn forecast, high-risk lists, renewal tabs.
8. Migration master, TAC Account Tracking, PubSec Gov SFDC, Wingman/license sheets.
9. Generic product/industry collateral only for framing, never for cell values.

Apply the 3-month recency gate before source priority. A lower-priority current source beats a higher-priority stale source. When current sources conflict, preserve existing workbook values and put the conflict in the notes column.

## Recency Gate

Use only information updated within the past 3 months, measured from the current date at runtime. State the exact cutoff date in the final output.

Acceptable freshness evidence:

- SharePoint/OneDrive document `updated_at`, modified time, or version history timestamp inside the last 3 months.
- Slack message/file timestamp inside the last 3 months.
- Teams message/file timestamp inside the last 3 months.
- OneNote page/section/backup modified timestamp inside the last 3 months.
- SFDC account/opportunity/renewal `Last Modified`, `Last Activity`, export generation date, or report updated date inside the last 3 months.
- Workbook/source tab update date or workbook modified date inside the last 3 months, when using workbook-internal tabs.

Do not use for cell values:

- Undated snippets.
- Local files whose only freshness signal is the time they were downloaded today.
- Account plans, decks, notes, or exports older than the cutoff.
- Rows with old activity dates unless the containing source has a reliable update timestamp inside the cutoff and the row value itself is not stale.

Stale or undated evidence may be used only to locate newer account-specific sources. It cannot justify a fill value, FY27 Big Rock, status, or risk flag.

## Account-Specific Search Standard

Do not stop after broad SharePoint or spreadsheet searches. For a single-row research task, first resolve and inspect the account-specific collaboration surface:

- TAM/ES SharePoint site, such as `TAM-AccountName` or `ES-AccountName`
- account SharePoint document repository files and site pages
- account OneNote section/page/backups
- account Slack channel, usually but not always `#account-*`
- account Teams channel or chat if used by the team
- SFDC account/opportunity/renewal facts, directly or via exported/internal files

If a connector is unavailable, explicitly record that limitation in the final source coverage. Do not silently replace it with a weaker source.

## Dropdown Values

Use exact workbook values:

- `Bot/License Utilization`: `Low`, `Moderate`, `High`, `Maxed`
- `Cloud Y/N`: `Y`, `N`
- `Consuming AI Units Today: Y/N`: `Y`, `N`
- `Agent Units Purchased Y/N`: `Y`, `N`
- `Test Status`: `Not Yet`, `Exploring`, `PoC`, `PRD`, `Blocked`
- `IXP Status`: `Not Yet`, `Exploring`, `PoC`, `PRD`, `Blocked`
- `Agentic Status`: `Not Yet`, `Exploring`, `PoC`, `PRD`, `Blocked`
- `Regional Leader Only: Bell Curve Adoption Flag`: `Early Adopter`, `Early Majority`, `Late Majority`, `Laggard`
- `Tracking Value Realized`: `Don't Know`, `Partially`, `Yes`, `Won't Share`
- `At Risk/Churn Forecasted: Y/N`: `Y`, `N`

## Field Rules

### Bot/License Utilization

Fill only from explicit utilization/support signals:
- `Enterprise` utilization or high TAC support usually maps to `High`.
- `Standard` utilization or medium support usually maps to `Moderate`.
- Low support / low engagement can map to `Low` only when the account-specific source says low usage or low support.
- Do not infer utilization from ARR alone.

### Cloud Y/N

Fill `Y` only when the current platform or active account source says Automation Cloud, ACPS, GovCloud, or Active Public Sector Cloud.

Fill `N` only when the current platform says MSI, on-prem, Automation Suite, Studio only, or notes explicitly say the customer cannot use cloud.

If target platform is cloud but current platform is not, do not mark `Y`; put the migration target in notes.

### Consuming AI Units Today

Do not mark `Y` from an AI Unit entitlement or bundle alone. Entitlement is not consumption.

Mark `Y` only when a source says the account is actively using DU, Document Understanding, Communications Mining, IXP, GenAI/Autopilot features, or AI Unit-backed production/PoC workloads. If telemetry is not available, mention verification needed in notes.

### Agent Units Purchased

Leave blank unless there is an explicit Agent Units SKU, quote, purchase, entitlement, or order. Interest in agents, Autopilot, or agentic automation is not a purchase.

### Test Status

Fill only from explicit Test Suite/Test Manager/Test Cloud source evidence:
- `Exploring`: interest, discovery, or enablement.
- `PoC`: active pilot or rollout plan.
- `PRD`: production use.
- `Blocked`: explicit blocker.

### IXP Status

Use for IDP/Document Understanding/IXP/Communications Mining-style document or extraction work:
- `Exploring`: discovery, demo, show-and-tell, backlog candidate.
- `PoC`: active pilot, first use case build, UAT, implementation.
- `PRD`: production document workload.
- `Blocked`: funding/security/ATO/procurement blocker.

### Agentic Status

Use only when sources mention agents, agentic automation, Autopilot, Maestro, or similar. Do not infer from generic AI interest.

### FY27 Big Rocks

Write account-specific action bullets. Good bullets include:
- renewal/risk action,
- platform migration or stability action,
- adoption/value action,
- AI/DU/Test/Agentic expansion action,
- stakeholder/sponsor action.

Avoid generic filler. If the only evidence is “active customer, no churn,” keep the bullets conservative and say what must be confirmed.

### Tracking Value Realized

Use:
- `Yes` only for quantified value, ROI, hours saved, dollars saved, or agreed KPI tracking.
- `Partially` for active automation/DU adoption with some evidence but no quantified metric.
- `Don't Know` only if a source says the account will not share or there is no evidence after thorough search.

### At Risk / Churn Forecasted

Use workbook churn forecast/high-risk tabs first.

Mark `Y` for negative churn/downsell forecast, source status `Churn`, explicit high-risk label, renewal risk, program hold, sponsor loss, severe engagement issue, or blocked migration tied to renewal risk.

Mark `N` for active status and no negative churn forecast only when the structured evidence is account-specific. Do not treat the word `churn` inside `no negative churn forecast` as risk.

## Notes Column

Use notes to:
- cite source names and key facts,
- preserve conflicts,
- document why a field remains blank,
- flag telemetry verification needs.

Do not put sensitive personal details in notes unless already present in the workbook and necessary for the account action.
