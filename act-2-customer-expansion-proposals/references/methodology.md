# Inventory-Backed Agentic Proposal Methodology

## Purpose

Use this methodology to create executive UiPath agentic automation recommendations from two evidence streams:

1. Public authoritative customer strategy, budget, performance, policy, and operating evidence.
2. A user-provided automation or use-case inventory.

The discipline is accuracy before persuasion. Do not polish weak inventory data into fake certainty. Treat inventory rows as operational signal, public sources as strategy evidence, and all value math as planning ranges until customer SMEs validate scope, volume, handling time, labor rate, and governance.

## Research Quality Gates

Use source quality gates before crosswalking strategy to inventory:

| Tier | Source type | Treatment |
| --- | --- | --- |
| 1 | Official strategy plans, budget justifications, annual performance plans, audited reports, legislation, official dashboards, executive orders, agency press releases | Primary evidence. Use for strategic objectives, program priorities, budget context, and performance pressure. |
| 2 | Inspector general reports, GAO/state auditor reports, public hearing testimony, procurement notices, official data portals | Strong supporting evidence. Use for operational pain, risk, backlog, compliance, and modernization pressure. |
| 3 | Credible trade press, vendor case studies, association research, analyst reports | Context only. Do not use as the sole basis for customer priority or value. |
| 4 | Blogs, unsourced summaries, outdated pages, AI-generated snippets, social posts | Exclude unless used only to find a better primary source. |

Rules:

- Prefer sources published or updated within the last 24 months. For annual plans, budgets, and performance reports, use the most recent fiscal year available.
- Use older sources only when they are still controlling policy, statute, or long-term strategy; label them as older but still relevant.
- Corroborate high-value recommendations with at least one Tier 1 strategy source and one inventory signal. If either side is missing, label the use case exploratory.
- Resolve source conflicts by preferring newer, more authoritative, and more specific sources. Call out unresolved conflicts rather than averaging them away.
- Generic sector themes are not customer strategy. Do not substitute "government modernization," "customer experience," or "efficiency" unless a customer-specific public source supports the claim.

## Strategy Ledger

Build a short ledger before prioritization. Each strategic fact used in recommendations needs traceability:

| Field | Requirement |
| --- | --- |
| Source ID | Stable label such as `S1`, `S2`. |
| Title and publisher | Exact public source title and issuing organization. |
| Date or fiscal year | Publication date, update date, or fiscal year. |
| URL | Public URL when available. |
| Supported fact | One concise fact the source actually supports. |
| Use-case implication | Why this fact matters for an automation or agentic workflow. |
| Evidence tier | Tier 1-4 from the source quality gate. |

If source-backed strategy is thin, say so. A thin ledger should reduce confidence and narrow the recommendation set.

## Inventory Profiling

Expected inventory fields vary. Look for these concepts, not exact names:

| Concept | Common column names |
| --- | --- |
| Idea name | `Automation Name`, `Use Case`, `Idea`, `Process Name`, `Automation Title` |
| Agency or owner | `Agency`, `Department`, `Business Unit`, `Process Owner`, `Team` |
| Stage/status | `Phase`, `Status`, `Lifecycle`, `Stage` |
| Volume | `Transactions per Year`, `Average Transaction Volume (per week)`, `Requests`, `Cases`, `Tickets` |
| Time | `Time per Transaction`, `Hours per Year`, `Total hours saved`, `Benefit ... hours` |
| Process text | `Process Description`, `Value Statement`, `Qualitative Benefits`, `Tags`, `Systems Used` |
| Reach | `Is this citizen-facing`, `Is this Shared Service`, `Number of agencies`, `Scalability Multiplier` |
| Risk/security | `FedRAMP`, `FTI`, `PII`, `PHI`, `CJIS`, `Restricted`, `Confidential` |

For each inventory, record:

- Total rows and sheets.
- Column names and obvious duplicates.
- Status distribution.
- Top agencies/departments.
- Top volume rows.
- Blankness of benefit, volume, scoring, owner, and process-description fields.
- Suspicious values that need SME validation, including extreme volumes, conflicting statuses, stale dates, and missing system names.

## Row Strength Rubric

Classify each candidate row before using it in a recommendation:

| Strength | Criteria | Use in recommendations |
| --- | --- | --- |
| Strong candidate | Active/live/approved status, named owner, usable process description, plausible volume or handling time, system/context fields, and clear link to strategy. | Eligible for value math and primary evidence. |
| SME validation required | Relevant status or process text, but missing owner, missing/estimated volume, unclear systems, stale date, or ambiguous benefit field. | Include with caveat; do not overstate value. |
| Weak lineage | On hold, postponed, duplicate-like, archived lineage, rejected/cancelled, or thin process detail but repeated by stronger rows. | Mention only as pattern evidence or caution. |
| Excluded from value math | Rejected, cancelled, duplicate, decommissioned, archived without active successor, or impossible volume. | Exclude from estimates unless customer validates current relevance. |

Dirty data belongs in the executive output when it affects prioritization. Do not hide missing volumes, stale statuses, or suspect benefit claims in an appendix.

## Status Treatment

Use this status hierarchy unless the customer provides different meaning:

| Status type | Treatment |
| --- | --- |
| Live, In Production, Hypercare | Strong evidence that the pattern is real; may be extension or agentic upgrade candidate. |
| Approved, In Progress, Development, Testing | Strong candidate for prioritization. |
| Awaiting Review, Assessment, Qualification, Idea | Useful backlog signal; require SME validation. |
| On Hold, Postponed | Weak-to-medium signal; include only if strategically aligned or repeated elsewhere. |
| Archived, Rejected, Cancelled, Duplicate, Decommissioned | Exclude from value math by default; mention only as weak lineage or caution. |

## Crosswalk and Prioritization

Each recommended use case must show both:

1. Customer-specific public strategy alignment.
2. Named inventory rows that support the operational workflow.

If one side is missing, label the recommendation exploratory and downgrade confidence.

Rank proposed use cases with weighted judgment, not a black-box score:

- Strategic fit: direct match to public priorities, budget programs, performance goals, risk findings, or executive agenda.
- Inventory evidence: row strength, active status, repeated pattern, plausible volume, systems, owner, and process text.
- Agentic fit: unstructured intake, exceptions, routing, summarization, document extraction, communications, multi-step coordination, or human review.
- Enterprise reach: shared service, multi-agency, citizen-facing, high-volume, or repeatable pattern.
- Feasibility: clear workflow boundaries, available systems, low-dependency first pilot, and measurable validation path.
- Governance risk: safety, legal, regulated, sensitive data, high-consequence decisions, and required human review.
- Value confidence: validated volume/time beats speculative benefit fields.

Do not let a large budget line outrank a smaller use case with stronger process evidence and clearer automation fit. Keep the executive table to the strongest 5-8 recommendations and proposal cards to the strongest 3-6. Do not invent a top 10 if the evidence supports fewer.

## Value Estimation

Use planning ranges. Never imply guaranteed ROI, savings, recovered budget, or committed value.

Preferred formula:

`Annual value pool = Annual volume * minutes saved per transaction / 60 * loaded labor rate`

Rules:

- Use inventory `Transactions per Year` when available.
- If annual volume is missing and weekly volume is available, use `weekly volume * 50` and label it as estimated.
- If volume is missing, do not invent a value. Use "volume validation required."
- If actual handling time is available, use a conservative percentage of handling time as minutes saved.
- Put volume, minutes saved, labor rate, formula, value range, and caveat next to the estimate.
- Keep customer-provided benefit claims separate from independently calculated planning ranges.
- If handling time is missing, use conservative default ranges:

| Use case type | Default minutes saved per transaction |
| --- | ---: |
| Simple notification, routing, or status update | 1-3 |
| IT service request fulfillment | 2-6 |
| HR/back-office data update | 2-6 |
| Benefits, ticket, or communication triage | 1.5-4 |
| Licensing, permit, or inspection workflow | 3-8 |
| Document/application completeness review | 4-10 |
| Public records, legal, or compliance packet preparation | 4-12 |
| Public safety analyst assist | 1-5 |

Use a loaded labor rate only as an assumption unless the customer provides one. If no rate is provided, `$60/hour` is a conservative planning placeholder for public-sector administrative and analyst work. Label it as an assumption.

## Capability Fit

Validate UiPath capability names against current `docs.uipath.com` for the deployment context before finalizing.

Rules:

- Refer to capabilities, not SKU or entitlement claims.
- Mark deployment availability as "requires confirmation" when public docs do not clearly support the target context.
- For Automation Cloud Public Sector or other constrained deployments, be explicit that tenant availability, FedRAMP boundary, region, and licensing require customer confirmation.
- High-risk workflows should use assistive automation with human review unless governance evidence supports more.

## Confidence Ratings

- `High`: Tier 1 strategy evidence, strong inventory rows, validated or plausible volume, direct UiPath capability fit, low-to-medium governance risk, and clear pilot boundary.
- `Medium`: good strategy and inventory fit, but volume is estimated, status is early/on hold, capability availability requires confirmation, or governance risk needs review.
- `Low`: plausible strategy idea, but inventory evidence is sparse, volume is missing, source evidence is thin, or process data is too dirty.

Downgrade confidence for:

- Safety-critical decisions.
- Child welfare, healthcare, benefits eligibility, legal, law enforcement, public safety, or regulated decisions.
- Unvalidated extreme volumes.
- Archived/rejected/cancelled rows.
- Missing process descriptions, owners, or system names.
- Strategy claims supported only by Tier 3 context sources.

## Executive Proposal Card Format

Use this shape for each card:

```markdown
### N. [Use Case Title]

**Business Challenge:** [Specific problem tied to strategy, budget/program area, and named inventory rows.]

**Proposed Solution:** [High-level agentic workflow. Include human review for high-risk processes.]

**Relevant UiPath Capabilities:** [Capability names only, validated against current docs; availability caveat if needed.]

**Estimated Impact:** [Volume, minutes-saved range, labor-rate assumption, formula, value range, and confidence. Say planning estimate.]

**Evidence and Assumptions:** Sources: [S...]. Inventory rows: [...]. Assumptions: [...]. Dirty-data caveat: [...]. Confidence: [High/Medium/Low].
```

## Executive Table Columns

For Word briefs, keep the table portrait-safe and decision-useful:

| Column | Content |
| --- | --- |
| Rank | Prioritized order by value, strategic alignment, confidence, and feasibility. |
| Recommendation | Short agentic use case title. |
| Strategic fit | Public-source objective or program area. |
| Inventory evidence | Specific rows with status and volume when available. |
| Value pool | Range or "validation required." |
| Confidence | High/Medium/Low plus reason. |
| Next step | Concrete validation or pilot action. |

If more detail is needed, move source URLs and full formulas to an appendix instead of widening the table.

## Anti-Patterns

- Do not present inventory rows as customer strategy.
- Do not use stale/dead inventory rows as primary proof.
- Do not present generic sector themes as customer-specific priorities.
- Do not use Tier 3 or Tier 4 sources as sole proof for a recommendation.
- Do not invent a top 10 if the inventory supports fewer.
- Do not include UiPath SKU or entitlement claims.
- Do not call planning value "ROI," "savings," or "guaranteed value."
- Do not let generative AI appear to make decisions in high-risk workflows; frame those as assistive and human-reviewed.
- Do not bury assumptions in prose. Put them next to the value estimate.
