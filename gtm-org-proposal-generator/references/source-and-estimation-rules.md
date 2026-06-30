# Source and Estimation Rules

## Source Priority

Use the highest-quality public sources available for each fact.

1. Official organization sources: budget books, enacted budgets, congressional budget justifications, annual comprehensive financial reports, audited financial statements, annual reports, Form 10-K/10-Q filings, strategic plans, performance plans, inspector general reports, procurement forecasts, staffing plans, and official dashboards.
2. Official oversight or regulator sources: federal/state budget offices, legislative fiscal notes, inspector general reports, GAO reports, SEC filings, EDGAR exhibits, credit rating reports from public issuer pages, and official grant or contract databases.
3. Credible secondary context: major rating agency summaries, established news outlets, reputable industry research, and vendor case studies. Use these only for context unless they cite a primary source.
4. Weak sources: Wikipedia, scraped summaries, generic SEO pages, AI-generated summaries, unsourced blogs, and social media. Do not use weak sources for budget values, program rankings, or impact math.

## Citation Ledger

Create a source ledger before the final proposal.

Use stable source IDs: `S1`, `S2`, `S3`.

Capture:

- Source ID
- Title
- Publisher
- Date or fiscal year
- URL
- Accessed date
- Facts supported

Every material number, strategic objective, program ranking, administrative-cost estimate, and impact estimate must point to one or more source IDs.

## Budget Normalization

- Preserve the source's native fiscal year and name it explicitly.
- Normalize monetary units before ranking, such as thousands, millions, or billions.
- State currency when not USD.
- Separate operating budget, capital budget, grants, pass-through funding, one-time appropriations, and multi-year authorization when the source separates them.
- Do not add overlapping budget lines. If a program line is nested under a larger total, rank the most useful level of granularity and note the hierarchy.
- If sources conflict, prefer the most recent official adopted/enacted figure and disclose the discrepancy.
- If only partial budgets are available, rank the source-backed subset and explain what is missing.

## Administrative Cost Estimate Tiers

Label every admin-cost value with one tier:

- `Documented`: The source directly provides administrative, SG&A, general administration, overhead, program support, corporate services, operating support, or equivalent cost.
- `Derived`: The estimate is calculated from source-backed values, such as FTE count times loaded labor cost, transaction volume times handling time, or admin budget divided by program budget.
- `Benchmarked`: The estimate uses a clearly named public benchmark or comparable ratio because organization-specific admin cost is unavailable.
- `Assumption`: The estimate is a reasoned planning assumption. Use only when needed to prioritize ideas, keep it conservative, and mark confidence as low.

Do not use admin-cost estimates as if they were audited facts. Show both the percentage and value when possible:

`Estimated Admin Cost = Program Budget x Admin Cost Assumption`

For public sector agencies, use conservative percentages unless official evidence supports a larger burden. For companies, prefer SG&A, corporate expense, or segment operating expense disclosed in filings before any generic ratio.

## Use Case Prioritization

Prioritize use cases using a simple weighted view:

- Budget or cost pool size
- Administrative burden or document intensity
- Strategic alignment
- Feasibility for UiPath capabilities
- Evidence quality
- Executive relevance

Do not overfit use cases to every large budget line. A large program with no administrative process evidence may rank lower than a smaller program with clear backlog, paperwork, testing, audit, claims, or service friction.

## Anti-Fabrication Rules

- Do not invent the top 20 when fewer are supported.
- Do not infer program budgets from unrelated headcount or national averages unless clearly labeled as an assumption.
- Do not cite a source for a claim it does not directly support.
- Do not imply UiPath capability availability without checking current `docs.uipath.com`.
- Do not present savings as guaranteed. Use `estimated impact`, `planning range`, or `potential annual value`.
- Do not include customer-confidential or internal-only sources unless the user explicitly expands scope beyond this skill's default.
