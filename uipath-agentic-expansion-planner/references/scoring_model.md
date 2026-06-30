# Scoring model

Use this scoring model to prioritize UiPath agentic expansion opportunities from a customer use-case inventory.

## Scoring scale

Score each criterion from 0 to 5.

| Score | Meaning |
|---|---|
| 5 | Strong direct evidence and clear execution path |
| 4 | Good evidence with manageable assumptions |
| 3 | Plausible but requires validation |
| 2 | Weak evidence or unclear feasibility |
| 1 | Speculative or low value |
| 0 | Not recommended or actively contradicted |

Use judgment. Do not pretend the score is mathematically precise.

## Default weighted criteria

| Criterion | Weight | What to test |
|---|---:|---|
| Strategic alignment | 20 | Public customer priority, executive relevance, urgency |
| Inventory evidence | 20 | Production density, repeated pattern, owner clarity, value/volume fields |
| Agentic suitability | 15 | Unstructured input, ambiguity, exceptions, knowledge retrieval, recommendations |
| Value potential | 15 | Labor, cycle time, quality, compliance, risk, experience, reuse |
| Feasibility | 10 | Data access, integration, process boundary, readiness |
| Enterprise scalability | 10 | Reusable pattern across departments, systems, or process families |
| Governance readiness | 5 | Human review, auditability, data sensitivity, model governance |
| Time-to-pilot | 5 | Bounded scope, low dependency load, available SMEs, clear success metrics |

Weighted score calculation:

`weighted score = sum(score_0_to_5 * weight) / 5`

This yields a 0 to 100 score.

## High-impact recommendation ranking

Use the default weighted criteria. Favor candidates with:

- Strong strategic alignment.
- Multiple inventory rows or high-value process density.
- Clear executive relevance.
- Enterprise scalability.
- Meaningful value levers.
- Credible capability fit.

High-impact opportunities can be larger and more complex, but they must still be actionable.

## Low-friction POC ranking

For POC ranking, use this weighting instead:

| Criterion | Weight |
|---|---:|
| Time-to-pilot | 25 |
| Feasibility | 20 |
| Governance readiness | 15 |
| Agentic suitability | 15 |
| Inventory evidence | 10 |
| Strategic alignment | 10 |
| Value potential | 5 |
| Enterprise scalability | 0 |

Favor bounded pilots with clear data, clear owner, low-risk decision boundaries, and measurable outcomes. A POC does not need the largest enterprise value, but it must prove a pattern that can scale.

## Confidence rating

Assign confidence separately from score.

| Confidence | Conditions |
|---|---|
| High | Strong inventory fields, production evidence, strategy evidence, value/volume signal, deployment context available |
| Medium | Good inventory and strategy evidence, but missing some value or deployment details |
| Low | Sparse inventory fields, unclear status, weak value data, or strategy alignment based on inference |

Do not let a high score hide low confidence. A candidate can be strategically attractive and still have low confidence because the input data is incomplete.

## Recommendation categories

Use these categories to make ranking easier to understand:

- Scale now: high score, high confidence, strong production evidence, manageable risk.
- Validate next: high potential, medium confidence, needs SME or data validation.
- Pilot first: narrow scope, fast proof, useful for proving agentic pattern.
- Monitor: plausible but weak data, not ready for executive recommendation.
- Reject: generic, unsupported, low value, or unsuitable for agentic automation.

## Red flags

Downgrade or reject candidates when:

- No owner or department can be identified.
- No process description exists.
- Status is cancelled, rejected, retired, duplicate, or archived.
- The work is simple deterministic data transfer with no exception, judgment, or unstructured input.
- The opportunity requires autonomous high-risk decisions without human approval.
- The recommendation depends on unconfirmed product entitlement.
- The value case requires invented assumptions.
- Public strategy evidence is unrelated or generic.

## Required scoring output fields

For each ranked recommendation, include:

- Rank.
- Use-case name.
- Recommendation category.
- Weighted score.
- Confidence.
- Strategic alignment evidence.
- Inventory evidence.
- Agentic enhancement.
- Value levers.
- Feasibility notes.
- Governance notes.
- Validation questions.
