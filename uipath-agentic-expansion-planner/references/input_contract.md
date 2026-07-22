# Input contract for full-quality output

Use this reference when deciding whether the user has provided enough information to produce a customer-ready UiPath automation portfolio assessment and its internal evidence package.

## Minimum viable inputs

The skill can produce a directional analysis with these inputs:

1. Customer name and sector or industry.
2. Detailed use-case or automation inventory as `.xlsx`, `.xlsm`, `.csv`, or `.tsv`.
3. Target audience, depth, or account objective. The final output format is always a rendered `.docx` Word executive brief; chat summaries, Markdown, slide outlines, spreadsheets, proposal cards, or account-plan sections are supplemental unless the user explicitly prohibits file output.

If any of these are missing, ask for the missing item before attempting a full analysis. If the user asks for a best-effort answer anyway, proceed but label the output as partial.

For auditable output, convert these inputs into schema `1.0` `evidence_ledger.json` and
`portfolio.json` using `references/data_contracts.md`. Unversioned JSON is rejected. A legacy
Markdown brief can be structurally validated, but it cannot certify evidence, scoring, dates,
deployment fit, value math, or entitlement claims.

## Required inputs for full-quality output

Full-quality output requires all of the following.

### 1. Customer identity and context

Required:

- Customer legal or commonly used name.
- Public/private sector indicator.
- Industry, agency type, or operating model.
- Geography or jurisdiction if relevant.
- Known account objective, such as Act 2 expansion, renewal support, executive briefing, CoE roadmap, agentic pilot planning, or value realization planning.

Why this matters: public evidence, governance constraints, and strategy alignment depend on the exact organization and operating context.

### 2. Detailed use-case inventory file

Required file formats:

- Preferred: `.xlsx` or `.csv`.
- Acceptable: `.xlsm`, `.tsv`, or a pasted table if file upload is not available.

Required inventory fields:

- Use-case or automation name.
- Description, business problem, or process summary.
- Status or lifecycle stage.
- Department, agency, function, process area, or business owner group.
- Owner, sponsor, SME, or requestor when available.

`inventory_profiler.py` assigns each physical source row an `INV-*` ID. Use that ID downstream;
names are not keys because names may be duplicated or changed.

Strongly required for high-confidence prioritization:

- Production/live indicator.
- Pipeline, backlog, idea, retired, rejected, cancelled, or duplicate indicator.
- Applications/systems touched.
- Process inputs and outputs.
- Current manual pain points.
- User group or role impacted.
- Volume, frequency, cases, transactions, or requests.
- Average handling time, effort, hours saved, FTE impact, or other labor proxy.
- Existing ROI, benefit, savings, revenue, cost avoidance, or risk-reduction fields.
- Complexity, risk, feasibility, or priority fields if present.
- Dates, such as submitted, approved, go-live, last updated, or retired.

For source freshness, prefer one populated record-update column with ISO dates or another
unambiguous date format. Profile `1.1` normalizes valid row dates and reports invalid or missing
values. When any valid record dates exist, the evidence-ledger `as_of_date` must equal the latest
valid source record date. A run date, assessment date, review date, or file-modified timestamp is
not a substitute. If no reliable record date exists, state that limitation in the customer
assessment and confirm lifecycle state before acting on the recommendations.

Weak inventory signals that reduce output quality:

- Only process titles, no descriptions.
- No status field.
- No owner or department field.
- No production versus idea distinction.
- No value, volume, or handling-time proxy.
- Many duplicate, archived, or cancelled rows with no clear marker.

### 3. Deployment and governance context

Required for full deployment-aware recommendations:

- UiPath deployment model: Automation Cloud, Automation Suite, on-prem, hybrid, FedRAMP, public sector cloud, or unknown.
- Known security constraints: PII, PHI, PCI, CJIS, ITAR, GDPR, data residency, or other regulated data.
- Human approval requirements for recommendations, decisions, and external communications.
- Whether GenAI, LLM, or agentic capabilities are allowed, restricted, blocked, or under review.
- Known integration constraints, such as VPN, VDI, Citrix, mainframe, ERP, SaaS, API access, or no API access.
- Existing governance model: CoE-owned, federated, citizen development, IT-owned, or mixed.

If deployment context is unknown, use conservative language and include deployment validation questions.

### 4. UiPath footprint and capability context

Required for entitlement-aware recommendations:

- Known UiPath products in use, if available.
- Licenses or entitlements, if known.
- Current use of Document Understanding, Communications Mining, Process Mining, Task Mining, Integration Service, Apps, Action Center, Insights, Test Suite, Agent Builder, Autopilot, or related platform capabilities.
- Current CoE maturity and operating model.
- Existing automations that should be reused or avoided.

Never claim the customer owns, can deploy, or is entitled to a product unless the user provides that fact or a cited source confirms it.

### 5. Public strategy source preferences

Required for strongest strategy alignment:

- Confirm whether public research is allowed.
- Optional: user-provided customer documents, strategic plans, annual reports, budget links, board materials, QBR decks, or public URLs.
- Any sources to prefer or avoid.

If public research is used, prioritize official sources and cite all public facts.

Record each source as a dated `SRC-*` entry and every planning assumption as an `ASM-*` entry.
Confirmed entitlement claims require matching ledger evidence.

When a strategy or account-context source is local, pass it to the customer builder with repeatable `--supporting-source` arguments. The receipt stores only the safe basename and SHA-256, never the local path. Public URL sources remain dated ledger entries.

A dated customer-confirmed account source can supply a narrowly scoped operational fact omitted by
the inventory, including a cross-record identifier, accountable outcome owner, or available sample.
Record that fact in the evidence ledger and bind the source in the receipt. The process map and
customer assessment must still say that the inventory omitted the field. Do not infer the fact from
shared systems or adjacent descriptions, and do not use one confirmation to imply product
availability, deployment compatibility, entitlement, baseline, value, funding, or pilot approval.

### 6. Output expectations

Required:

- Target audience: C-suite, business sponsor, CoE lead, AE/CSM internal planning, solution consultant, or mixed.
- Desired supplemental output, if any: chat excerpt, Markdown source, slide outline, spreadsheet prioritization, proposal cards, or account plan section. These do not replace the final `.docx` deliverable.
- Whether the default customer assessment or legacy internal detailed analysis is needed.
- Number of recommendations if different from default.

Default output if the user does not specify:

- One-to-two-page rendered and verified customer `.docx` in `outputs/`, plus the exact verified PDF.
- Source file summary and limitations.
- Exact current automation footprint, analyst-mapped process groups with explicit customer-confirmation needs, and traceable selection or deferral decisions.
- Up to three evidence-backed end-to-end process recommendations.
- Named process groups with automation counts. Source-reported volume and handling time may appear only as separate, unvalidated workload signals; aggregation and value math stay internal until units and linkage are confirmed.
- One accountable next step per recommendation.
- A measurable read-only pilot for each recommendation: numeric sample selection, reviewer-owned
  ground truth with a named accountable owner, at least two numerator/denominator formulas using
  comparable units for ratio metrics, review cadence, one measurement owner, and correction plus
  rerun before any proceed decision.
- Named customer decision ownership, data/security approval ownership, UiPath product and
  deployment validation ownership, prerequisite fallback, and absolute kickoff and decision
  dates.
- Separate internal profile, evidence, portfolio, process-map, semantic-review, and receipt artifacts.

Full-quality output requires enough context to confirm process boundaries and produce an independent or human semantic review. Without that review, output remains exploratory.

## Optional inputs that improve quality

- Customer strategic themes already known by account team.
- Executive sponsor priorities.
- Renewal, expansion, or consumption goals.
- Recent QBR notes.
- Discovery interview notes.
- Implementation blockers.
- Customer quotes.
- Competitive context.
- Existing success stories.
- Known sensitive areas to avoid.
- Desired UiPath messaging, tone, or template.

## Input triage rules

- If the inventory is missing, do not produce a full output. Ask for the inventory.
- If the customer name is missing, ask for it before doing public strategy research.
- If status is missing, do not assume all rows are production. Treat status as unknown.
- If value and volume are missing, rank using strategic fit, inventory density, and agentic suitability, but label value confidence as low.
- If deployment context is missing, include explicit validation questions and avoid final implementation claims.
- If product entitlement is missing, say capability fit, not current entitlement.
- If a user asks for a non-DOCX output, treat that request as supplemental and still render the final `.docx` unless the user explicitly prohibits file output or file creation is impossible.
- If a versioned artifact is missing `schema_version`, has an unsupported version, or fails ID
  integrity, stop and follow the migration guidance. Do not infer references from names.
