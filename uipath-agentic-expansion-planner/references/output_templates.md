# Output templates

## Default customer assessment

The builder renders this structure deterministically. Do not add sections to the customer document.

```markdown
# Automation portfolio assessment: [customer]

## Source File Summary

- **Inventory reviewed:** [safe basename, record count, sheet names]
- **Information available:** [detected portfolio fields]
- **Strategy context reviewed:** [source names, no internal IDs]
- **Limitations:** [up to three observed field-coverage gaps or unconfirmed planning assumptions; never claim structural completeness]

## Current Automation Footprint

| Portfolio view | What the inventory shows |
| --- | --- |
| Total reviewed | [count] |
| Lifecycle mix | [detailed status counts] |
| Process/domain groups | [analyst-mapped group names and automation counts, with explicit customer-confirmation requirement] |
| Department concentration | [highest department/function counts, excluding duplicate records] |
| System concentration | [highest system counts, excluding duplicate records] |
| Unmapped | [count not mapped to a process group] |
| Assessment boundary | [workload is not savings; read-only workshop proposals authorize no writes or decisions] |

## Top 3 Recommendations

Order basis: [shared strategy, foundation, evidence, and delivery-risk criteria]. Workshop ask: [prerequisite validation and historical pilot decision only]. Owners set proposed thresholds from baselines and tolerances. State that this is not deployment or investment approval. Name material deferred process groups and their reconsideration conditions.

Account team: CSM [agenda/access artifact by each target]; TAM [product/tenant control note before each charter]; AE [sponsor/funding decision after evidence]; failed prerequisites defer.

Pilot mechanics: data joins frozen exports on confirmed identifiers; Maestro sequences handoffs; Robots prepare deterministic outputs; humans review; unmatched records pause and rerun; final record systems require validation.

| Rank | Process | Why this order |
| --- | --- | --- |
| 1 | [process] | [recommendation-specific comparison] |

### 1. [Specific end-to-end process]

- **End-to-end process:** Function: [business function]. Start: [trigger]. End: [human-owned completion]. Outcome: [business result].

- **Why it matters:** [customer-specific reason or explicitly unvalidated source-derived workload signal]

- **Existing automation foundation:** [count and names with lifecycle states]

- **Pilot path:** Proposed. Input: [numeric historical sample and selection method matching the proceed gate]. Ground truth: [historical reviewer-owned result]. Ground-truth owner: [accountable role]. [Maestro/robot/agent handoffs, join key, and observable output]. [Measurement owner] reports [metric = numerator / denominator with auditable units] [daily, weekly, or per case].

- **Roles and controls:** [which capabilities apply, need validation, or are excluded], [plain entitlement/deployment/value checks], [human review], [cross-record linkage], [no-write boundary]

- **Decision gate:** Stop when [quantitative failure range or control breach]. Proceed when [sample and quality thresholds pass]. Adjust when [intermediate ranges apply]. Rerun before proceeding. Decision owner: [one customer role]. [Bounded decision only].

- **Next action:** Target: [YYYY-MM-DD]. Customer: [owner]; UiPath: [account-team owner]. [Data/security approval, access, linkage, sample, product/deployment validation, and fallback action]. Output: [deliverable]. Decision: [YYYY-MM-DD].
```

Render one to three recommendations in portfolio rank order. If fewer than three qualify, say so and do not add filler.

## Internal package

Retain these artifacts separately from the customer DOCX:

- `inventory_profile.json` and `.md`
- `evidence_ledger.json`
- `portfolio.json`
- `process_map.json`
- `semantic_review.json`
- Customer Markdown source
- Exact PDF used for page verification
- Build validation receipt

Use `render_portfolio_markdown.py` only when the account team asks for the legacy detailed analysis. That output may include scores, evidence IDs, value formulas, deployment controls, workshop detail, and source ledger. It is not the default customer deliverable.

## Final response

Link the DOCX and its verified PDF, then report readiness, page count, recommendation count, and whether semantic, brand, and layout checks passed. Never call a draft customer-ready.
