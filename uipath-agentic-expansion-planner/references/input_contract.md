# Input contract for full-quality output

Use this reference when deciding whether the user has provided enough information to produce a full executive-quality UiPath agentic expansion proposal.

## Minimum viable inputs

The skill can produce a directional analysis with these inputs:

1. Customer name and sector or industry.
2. Detailed use-case or automation inventory as `.xlsx`, `.xlsm`, `.csv`, or `.tsv`.
3. Target audience, depth, or account objective. The final output format is always a rendered `.docx` Word executive brief; chat summaries, Markdown, slide outlines, spreadsheets, proposal cards, or account-plan sections are supplemental unless the user explicitly prohibits file output.

If any of these are missing, ask for the missing item before attempting a full analysis. If the user asks for a best-effort answer anyway, proceed but label the output as partial.

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

### 6. Output expectations

Required:

- Target audience: C-suite, business sponsor, CoE lead, AE/CSM internal planning, solution consultant, or mixed.
- Desired supplemental output, if any: chat excerpt, Markdown source, slide outline, spreadsheet prioritization, proposal cards, or account plan section. These do not replace the final `.docx` deliverable.
- Desired depth: concise executive summary, full portfolio analysis, or workshop-ready recommendations.
- Number of recommendations if different from default.

Default output if the user does not specify:

- Rendered and verified `.docx` Word executive brief in `outputs/` when available.
- Top 5 high-impact agentic expansion opportunities.
- Top 3 low-friction POC candidates.
- Executive summary.
- Inventory footprint summary.
- Public strategy alignment summary.
- Value assumptions and caveats.
- Deployment and governance validation questions.

Full-quality output requires enough context to write a concise `.docx` scope line: customer, vertical, deployment context, source inventory name, target audience, and whether the brief is internal planning or customer-ready.

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
