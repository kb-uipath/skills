---
name: gtm-org-proposal-generator
description: Build executive-level UiPath automation proposal cards from public organizational research. Use when Codex is asked to research an organization, agency, department, public company, healthcare system, university, or other institution; analyze budgets, strategic goals, administrative burden, or cost drivers; identify automation use cases; and produce cited GTM, sales, C-suite, public sector, or federal proposal content aligned to a specified industry vertical and UiPath deployment type.
---

# GTM Org Proposal Generator

## Operating Standard

Produce evidence-backed executive proposals, not polished guesses. Treat unsupported program budgets, uncited strategy claims, unverified UiPath capability availability, and vague impact math as defects. If fewer than 20 budget or program areas can be supported from public authoritative sources, report the smaller source-backed set instead of filling the table with weak guesses.

Use only public authoritative sources unless the user explicitly changes scope. Do not search or cite internal Slack, Teams, SharePoint, Drive, email, Salesforce, or customer-confidential material for this skill by default.

Avoid naming UiPath product SKUs. Refer to capabilities only, such as UI/API Automation, Autopilot, Agent Builder, Maestro, Apps, Test Manager, Test Cloud, Document Understanding, Action Center, Communications Mining, and IXP, after validating availability for the requested deployment type against current `docs.uipath.com`.

## Required Workflow

1. Confirm the inputs.
   - Required inputs: organization name, industry vertical, and UiPath deployment type.
   - If any required input is missing, ask for only the missing fields.
   - Before research, restate the confirmed inputs. If the user has not already clearly authorized proceeding, ask for confirmation and wait.
   - If the organization has ambiguous subsidiaries, agencies, fiscal entities, or geographies, resolve the exact research target before continuing.

2. Build a public source ledger.
   - Read `references/source-and-estimation-rules.md` before researching.
   - Prefer official budget documents, annual reports, audited financials, SEC filings, strategic plans, performance plans, inspector general reports, and procurement or staffing documents.
   - Capture source title, publisher, publication date or fiscal year, URL, accessed date, and the facts each source supports.
   - Use web browsing for current public sources and for current UiPath documentation. Public budgets, reports, laws, filings, and product documentation are time-sensitive.

3. Extract and rank budget or program areas.
   - Rank up to 20 programs, divisions, mission areas, budget lines, or operating segments by total source-backed budget.
   - Normalize fiscal years, currencies, units, and one-time versus recurring funding.
   - Do not mix incompatible totals without labeling the basis.
   - If only aggregate organization-level spending is available, explain the limitation and use the most granular source-backed categories available.
   - Present estimated administrative cost only when supported by a documented figure or a clearly labeled estimate methodology from the reference rules.

4. Identify and prioritize use cases.
   - Connect use cases to high-budget areas, administrative burden, labor shortages, backlog, compliance pressure, citizen or customer service friction, document volume, claims or case processing, testing burden, audit needs, or strategic goals.
   - Prefer use cases where UiPath can plausibly reduce cycle time, manual handling, exception work, testing effort, intake triage, or document processing cost.
   - Produce the top 10 use cases only when the evidence supports 10. If fewer are defensible, provide fewer and explain the evidence gap.

5. Validate UiPath capabilities.
   - Check current `docs.uipath.com` sources before finalizing any capability in a proposal card.
   - Verify deployment relevance for the user's requested deployment type, especially for public sector and self-hosted deployment contexts.
   - If availability is unclear, either omit the capability or label it as requiring confirmation.
   - Do not imply licensing, entitlement, SKU packaging, or contractual availability.

6. Generate the executive deliverable.
   - Read `references/proposal-output-template.md` before composing the final response.
   - Use formal, concise language suitable for C-suite, agency executive, or federal review.
   - Keep facts, estimates, and recommendations visibly separated.
   - Include source IDs next to budget values, strategy claims, admin-cost estimates, and impact estimates.
   - When producing a Markdown proposal artifact, validate it with `scripts/validate_gtm_output.py` before sharing when practical.
   - Offer export formats only after delivering the core result.

## Evidence Rules

- Never present a number as fact unless it is directly source-backed.
- Label estimate tiers as `Documented`, `Derived`, `Benchmarked`, or `Assumption`.
- Show impact math in plain language: baseline volume or spend, estimated addressable share, productivity or cost assumption, and resulting range.
- Prefer ranges over false precision.
- Use the source's native fiscal year naming and state any conversion.
- Treat vendor marketing claims, press releases, Wikipedia, generic analyst reports, and unsourced web summaries as weak context only, not primary budget evidence.
- If the user asks for a deck, spreadsheet, markdown artifact, or other file after the analysis, use the relevant document, presentation, or spreadsheet skill.

## References

- `references/source-and-estimation-rules.md`: source priority, citation requirements, budget normalization, admin-cost estimate tiers, and anti-fabrication rules.
- `references/proposal-output-template.md`: required executive output shape for source ledgers, budget tables, use-case prioritization, and proposal cards.
- `scripts/validate_gtm_output.py`: static output-contract check for required sections, source ledger shape, citation IDs, estimate tier labels, and unsafe overclaim phrases.
