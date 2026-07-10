# Proposal Output Template

Use the canonical JSON contract as the source of truth for final executive deliverables. Markdown is rendered from the validated contract; it is not the contract itself.

## Canonical Contract

```json
{
  "contract_version": "gtm-org-proposal-generator/v1",
  "confirmed_scope": {
    "organization": "...",
    "target_entity": "...",
    "industry_vertical": "...",
    "uipath_deployment_type": "...",
    "research_scope": "public-authoritative-only",
    "accessed_date": "2026-07-10"
  },
  "classification": {
    "data_classification": "Public",
    "retention": "Retain only in approved public-source GTM workspaces per account-team policy."
  },
  "source_ledger": [],
  "capability_ledger": [],
  "budget_program_areas": [],
  "prioritized_use_cases": [],
  "proposal_cards": [],
  "evidence_gaps": [],
  "assumptions": []
}
```

See `versioned-contract.md` for required fields inside each list.

## Rendered Markdown

The deterministic renderer produces these sections:

- Confirmed Scope
- Source Ledger
- Capability Ledger
- Budget / Program Areas
- Prioritized Use Cases
- Proposal Cards
- Evidence Gaps
- Assumptions and Validation Needed

Do not bypass the renderer for reusable artifacts. Legacy free-form Markdown is rejected by `scripts/validate_gtm_output.py` with migration guidance.

## Use Case Prioritization

Confidence rules:

- `High`: budget, operational pain, and capability fit are all source-backed.
- `Medium`: budget and capability fit are strong, but operational pain or volume is partly inferred.
- `Low`: useful idea, but impact depends on assumptions or missing process data.

## Executive Proposal Cards

Create one complete card for each prioritized use case, up to 10 total. Fewer than 10 cards are allowed when the evidence-backed set is smaller, but `evidence_gaps` must explain the limitation.

Each card must include business challenge, proposed solution, relevant UiPath capabilities, estimated impact, impact math, estimate tier, confidence, sources, and validation required.

## Executive Close

- Best-fit automation themes
- Largest value pools
- Highest-confidence first moves
- Major evidence gaps or assumptions
- Suggested next validation steps, such as process discovery, SME interview, volume pull, or pilot scoping

Do not ask whether the user wants the result. Deliver the core result, then list available export options such as markdown, spreadsheet, brief, or presentation outline.
