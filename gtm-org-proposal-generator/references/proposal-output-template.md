# Proposal Output Template

Use this structure for the final executive deliverable unless the user requests a different artifact format.

## Input Confirmation

```markdown
**Confirmed Inputs**
- Organization: ...
- Industry vertical: ...
- UiPath deployment type: ...
- Research scope: Public authoritative sources only
- Accessed date: ...
```

## Source Ledger

```markdown
**Source Ledger**
| ID | Source | Publisher | Date/FY | Facts Used |
| --- | --- | --- | --- | --- |
| S1 | Title - URL | ... | ... | ... |
```

Keep source titles concise. Include URLs in markdown links when available.

## Budget and Administrative-Cost Table

```markdown
**Top Source-Backed Budget / Program Areas**
| Rank | Program / Area | Total Budget | Estimated Admin Cost | Estimate Tier | Evidence |
| ---: | --- | ---: | ---: | --- | --- |
| 1 | ... | $... | ...% / $... | Documented/Derived/Benchmarked/Assumption | S1, S2 |
```

If fewer than 20 rows are source-backed, title the section with the actual count and include: `Only N source-backed program areas were available from public authoritative sources.`

## Use Case Prioritization

```markdown
**Prioritized Automation Use Cases**
| Rank | Use Case | Target Program / Area | Evidence-Based Driver | UiPath Capability Fit | Estimated Impact Range | Confidence |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | ... | ... | ... | ... | ... | High/Medium/Low |
```

Confidence rules:

- `High`: budget, operational pain, and capability fit are all source-backed.
- `Medium`: budget and capability fit are strong, but operational pain or volume is partly inferred.
- `Low`: useful idea, but impact depends on assumptions or missing process data.

## Executive Proposal Cards

Create one card for each prioritized use case, up to 10 total.

```markdown
### 1. [Use Case Title]

**Business Challenge**
Concise executive description of the current problem, tied to sourced budget, strategy, backlog, labor, compliance, citizen/customer experience, or cost pressure. Cite source IDs.

**Proposed Solution**
High-level, deployment-appropriate UiPath automation workflow. Include systems and human review only at the level supported by evidence.

**Relevant UiPath Capabilities**
Capability names only. Include a brief phrase for why each applies. Cite current UiPath docs source IDs or note `UiPath docs checked on [date]`.

**Estimated Impact**
Planning range with visible math. Label documented inputs, assumptions, and confidence. Avoid guaranteed savings language.

**Evidence and Assumptions**
Sources: S...
Assumptions: ...
Confidence: High/Medium/Low
```

## Executive Summary

Close with a short briefing summary:

- Best-fit automation themes
- Largest value pools
- Highest-confidence first moves
- Major evidence gaps or assumptions
- Suggested next validation steps, such as process discovery, SME interview, volume pull, or pilot scoping

Do not ask whether the user wants the result. Deliver the core result, then list available export options such as markdown, spreadsheet, brief, or presentation outline.
