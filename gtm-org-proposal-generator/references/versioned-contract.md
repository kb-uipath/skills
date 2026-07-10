# Versioned Contract

The canonical proposal handoff is a JSON object with:

```json
{
  "contract_version": "gtm-org-proposal-generator/v1"
}
```

The validator rejects unversioned or legacy free-form Markdown inputs. Migration path: create the JSON contract below, validate it, then render Markdown with `scripts/validate_gtm_output.py --render`.

## Contract Sections

Required top-level keys:

- `contract_version`
- `confirmed_scope`
- `classification`
- `source_ledger`
- `capability_ledger`
- `budget_program_areas`
- `prioritized_use_cases`
- `proposal_cards`
- `executive_close`
- `evidence_gaps`
- `assumptions`

`confirmed_scope` must include organization, target entity, industry vertical, UiPath deployment type, research scope, and accessed date. `research_scope` must be `public-authoritative-only` for this skill.

`classification` must use `data_classification: "Public"` and a retention statement that does not authorize confidential or internal-only material.

## Source Ledger

Every source row must include:

- `source_id`: stable ID such as `S1`
- `title`
- `publisher`
- `publication_date`
- `url`
- `accessed_date`
- `facts_supported`

Every material number, strategic claim, program ranking, administrative-cost estimate, capability claim, and impact estimate must reference one or more `source_ids`.

## Capability Ledger

Every UiPath capability used by a card must include:

- `capability_id`: stable ID such as `C1`
- `capability_name`
- `deployment_type`
- `availability`: `available` or `requires-confirmation`
- `docs_url`: current `docs.uipath.com` URL
- `docs_checked_date`
- `source_ids`

`deployment_type` must match the confirmed scope. `docs_checked_date` cannot be later than the contract accessed date. If availability is `requires-confirmation`, every dependent card must include deployment or availability validation guidance.

Every capability `source_ids` list must include a UiPath-published source whose URL exactly matches `docs_url`. A valid source ID that points to an unrelated budget or strategy page is not capability evidence.

## Proposal Completeness

The contract allows 1 to 10 complete proposal cards. Do not invent cards to reach 10.

Each card must include:

- rank
- use case
- business challenge
- proposed solution
- capability IDs
- estimated impact
- estimate tier
- impact math
- confidence
- source IDs
- validation required
- pilot owner
- target decision date
- measurable pilot exit criteria

If fewer than 10 cards are present, `evidence_gaps` must explain why the smaller portfolio is the only defensible set. This is not a weakness; pretending weak ideas are sourced is the weakness.

## Impact Math

Each use case and proposal card must include `impact_math` with:

- `baseline`
- `addressable_share`
- `productivity_or_cost_assumption`
- `resulting_range`
- `source_ids`

Any money or percentage value must be tied to source IDs. Estimate tiers are exactly `Documented`, `Derived`, `Benchmarked`, or `Assumption`.

`impact_range` and `estimated_impact` must exactly match their own `impact_math.resulting_range`. Nested impact-math source IDs must also appear in the parent card or use-case source list.

## Executive Close

The executive close must include a decision ask, overlap-aware portfolio value range, aggregation method, double-counting caveat, executive owner, decision date, source IDs, and one or more next-step objects with action, owner, and due date. A single-card portfolio range must exactly match that card's range.

For two or more cards, also include `portfolio_math`:

- `included_card_ranks`: every emitted card rank, in order
- `lower_adjustment_factor`: number greater than 0 and at most 1
- `upper_adjustment_factor`: number greater than 0 and at most 1
- `resulting_range`: exact displayed executive portfolio range

The validator parses each card's dollar range, sums lower and upper bounds, applies the stated
factors, and recomputes the executive range. It rejects selective card omission, reversed factors,
and aggregate mismatch. Do not sum overlapping value pools without a documented factor,
aggregation method, and caveat.

## Deterministic Rendering

Render Markdown only from a validated contract:

```bash
python3 gtm-org-proposal-generator/scripts/validate_gtm_output.py proposal.contract.json --render proposal.md
```

The renderer sorts source IDs, capability IDs, budget rows, use cases, and proposal cards deterministically. Manual Markdown editing after render is allowed for presentation polish only if the source JSON remains the contract of record.
