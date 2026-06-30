# Output templates

Use these templates to create consistent outputs for UiPath agentic expansion planning. Treat Markdown as the source for the final Word brief or as a supporting artifact; the final deliverable is the verified `.docx` unless the user explicitly prohibits file output.

## Default executive brief structure

Use this structure for the concise Word-source Markdown. Keep it executive-skimmable; if detailed research notes, long source URLs, row-level evidence, or full scoring math are useful, save them as separate supporting Markdown/CSV artifacts instead of loading the main `.docx` with them.

# UiPath agentic expansion proposal for [customer]

## Executive Summary

[3 to 5 sentences. State the current automation footprint, the strategic alignment thesis, the strongest expansion themes, and the recommended next step. Be specific and avoid generic AI language.]

## Source and Assumption Note

- Inventory source: [file name, sheets, row count]
- Public strategy sources: [source count and source types]
- Data limitations: [missing fields, unclear statuses, no volume/value data, deployment unknown]
- Value assumptions: [annualization or labor assumptions, if used]

## Current Automation Footprint

| Dimension | Finding | Implication |
|---|---|---|
| Production density | [finding] | [implication] |
| Department concentration | [finding] | [implication] |
| Process families | [finding] | [implication] |
| Value/volume fields | [finding] | [implication] |
| Data quality | [finding] | [implication] |

## Public Strategy Alignment

| Public priority | Evidence summary | Automation relevance |
|---|---|---|
| [priority] | [source and date] | [relevance] |

## Prioritized Portfolio

| Rank | Opportunity | Category | Score | Confidence | Why it matters |
|---:|---|---|---:|---|---|
| 1 | [name] | [Scale now / Validate next / Pilot first] | [0-100] | [High/Medium/Low] | [summary] |

## Top 5 High-Impact Recommendations

Use the proposal card format below for each recommendation.

## Top 3 Low-Friction POC Candidates

Use the POC card format below for each candidate.

## Value Framing

| Opportunity | Primary value levers | Sizing basis | Confidence | Validation needed |
|---|---|---|---|---|
| [name] | [labor, cycle time, quality, risk] | [inventory fields or assumption] | [H/M/L] | [question] |

## Deployment and Governance Considerations

| Consideration | Implication | Recommended control |
|---|---|---|
| [PII/PHI/data residency/etc.] | [impact] | [control] |

## Facts, Assumptions, and Validation Questions

### Facts

- [Fact grounded in the inventory, public strategy source, or confirmed deployment context.]
- [Fact grounded in the inventory, public strategy source, or confirmed deployment context.]

### Assumptions

- [Assumption used for scoring, value framing, capability fit, or feasibility.]
- [Assumption used for scoring, value framing, capability fit, or feasibility.]

### Validation questions

1. [Question needed to validate value, ownership, volume, deployment, governance, or pilot readiness.]
2. [Question needed to validate value, ownership, volume, deployment, governance, or pilot readiness.]
3. [Question needed to validate value, ownership, volume, deployment, governance, or pilot readiness.]

## Workshop Prep

Use the workshop agenda template below or a shortened version of it. Keep it focused on validating the evidence, choosing a pilot, and assigning owners.

## Recommended Next Steps

1. [Specific validation action]
2. [Specific stakeholder or workshop action]
3. [Specific pilot scoping action]

## Appendix: Source Ledger

| Source | Date | Type | Relevant priority |
|---|---|---|---|
| [source] | [date] | [official plan / annual report / etc.] | [priority] |

## DOCX executive brief structure

Use this AZ DES-style executive portfolio structure when rendering the final Word `.docx` brief. The `.docx` is the required final deliverable every time; chat, Markdown, slide, spreadsheet, or account-plan outputs are supplemental unless the user explicitly prohibits file output. This structure is richer than a compact proposal-card brief and is designed for GTM/account-team use, executive review, and workshop preparation.

1. Title and scope line.
2. Executive summary.
3. Source and assumption note.
4. Current automation footprint.
5. Public strategy alignment.
6. Prioritized portfolio.
7. Top 5 high-impact recommendations.
8. Top 3 low-friction POC candidates.
9. Value framing.
10. Deployment and governance considerations.
11. Facts, assumptions, and validation questions.
12. Workshop prep.
13. Recommended next steps.
14. Appendix: source ledger.

Use a shorter compact `.docx` brief only when the user explicitly asks for a short executive summary, minimal proposal-card output, or a very concise table-first artifact. Even compact briefs still need a title/scope line, executive summary, ranked prioritization, recommendation cards or compact card table, deployment/governance caveats, validation questions, and a source ledger.

### DOCX table patterns

Use these table patterns unless the user asks for a different format:

| Section | Columns |
|---|---|
| Current automation footprint | `Dimension` / `Finding` / `Implication` |
| Public strategy alignment | `Public priority` / `Evidence summary` / `Automation relevance` |
| Prioritized portfolio | `Rank` / `Opportunity` / `Category` / `Score` / `Confidence` / `Why it matters` |
| Value framing | `Opportunity` / `Primary value levers` / `Sizing basis` / `Confidence` / `Validation needed` |
| Deployment and governance considerations | `Consideration` / `Implication` / `Recommended control` |
| Workshop prep | `Segment` / `Time` / `Purpose` / `Output` |

Avoid wide Word tables. If a table becomes cramped, shorten cell text before switching orientation. Do not place every inventory field or URL in the main prioritization table; keep the table to executive decision fields and move detail to supporting artifacts or appendix notes.

### DOCX proposal card format

Use the full GTM-ready proposal card format for the Top 5 High-Impact Recommendations:

**Recommendation:** [One sentence stating what to do.]

**Why now:** [Public strategy and account context.]

**Inventory evidence:** [Specific process clusters, departments, statuses, volume/value fields, or row examples.]

**Agentic enhancement:** [What an agent does beyond baseline RPA: interpret, summarize, retrieve, recommend, route, orchestrate, draft, classify, or handle exceptions.]

**UiPath capability fit:** [Likely capability pattern. Do not claim entitlement unless confirmed.]

**Value levers:** [Labor, cycle time, quality, compliance, experience, risk, reuse.]

**Feasibility:** [Data, systems, process boundary, owner, and integration notes.]

**Governance:** [Human review, auditability, data sensitivity, model governance.]

**Validation questions:**

- [Question 1]
- [Question 2]
- [Question 3]

Cards should be detailed enough for GTM use but short enough that executives can skim the section quickly.

## Proposal card format

### [Opportunity name]

**Recommendation:** [One sentence stating what to do.]

**Why now:** [Public strategy and account context.]

**Inventory evidence:** [Specific process clusters, departments, statuses, volume/value fields, or row examples.]

**Agentic enhancement:** [What an agent does beyond baseline RPA: interpret, summarize, retrieve, recommend, route, orchestrate, draft, classify, or handle exceptions.]

**UiPath capability fit:** [Likely capability pattern. Do not claim entitlement unless confirmed.]

**Value levers:** [Labor, cycle time, quality, compliance, experience, risk, reuse.]

**Feasibility:** [Data, systems, process boundary, owner, and integration notes.]

**Governance:** [Human review, auditability, data sensitivity, model governance.]

**Validation questions:**

- [Question 1]
- [Question 2]
- [Question 3]

## Low-friction POC card format

### [POC name]

**Pilot objective:** [What the pilot proves.]

**Narrow scope:** [Specific process slice, department, document type, queue, case type, or user group.]

**Agent role:** [Specific agent actions.]

**Human role:** [Approvals, review, exception handling.]

**Success metrics:** [Cycle time, accuracy, manual minutes avoided, backlog reduction, adoption, quality.]

**Data needed:** [Inputs, sample records, policies, system access.]

**Exit criteria:** [Decision standard for scale/no-scale.]

## Workshop agenda template

Use this if the output is meant to support a customer workshop.

| Segment | Time | Purpose | Output |
|---|---:|---|---|
| Current-state validation | 20 min | Confirm inventory patterns and owners | Validated process clusters |
| Strategy alignment | 15 min | Confirm executive priorities | Ranked business outcomes |
| Opportunity review | 30 min | Discuss top recommendations | Shortlist |
| POC scoping | 30 min | Select one pilot | Pilot charter inputs |
| Governance review | 15 min | Identify constraints | Risk and control list |
| Next steps | 10 min | Assign owners and dates | Action plan |

## Tone rules

- Be direct and executive-ready.
- Use evidence-backed claims.
- Separate facts, assumptions, and inferences.
- Avoid hype words such as revolutionary, game-changing, or guaranteed.
- Avoid generic use-case language.
- Use specific workflow names, departments, and value levers whenever possible.
