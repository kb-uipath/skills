---
name: uipath-agentic-expansion-planner
description: analyze detailed customer automation or use-case inventories to produce evidence-backed uipath act 2 expansion plans, agentic automation portfolios, top 5 high-impact recommendations, top 3 low-friction poc candidates, and a final on-brand verified executive .docx Word brief every run. use when the user provides or references a customer inventory spreadsheet, asks for agentic expansion ideas, asks to prioritize uipath opportunities, or needs a customer-ready proposal grounded in inventory data, public strategy evidence, deployment-aware validation, UiPath brand-aware executive writing, and Word-ready packaging.
---

# UiPath Agentic Expansion Planner

## Purpose

Transform a detailed customer automation/use-case inventory into a defensible UiPath agentic expansion portfolio and a polished, on-brand, verified executive `.docx` briefing as the final deliverable every time. Anchor recommendations in two evidence sources: the customer's actual inventory and current public strategy evidence. Do not produce generic AI brainstorming.

## Required inputs

Use `references/input_contract.md` to assess input quality.

Minimum viable inputs:

1. Customer name and sector/industry.
2. Detailed use-case or automation inventory as `.xlsx`, `.xlsm`, `.csv`, `.tsv`, or pasted table.
3. Target audience, depth, or account objective. The final output format is always a rendered `.docx`; requested chat, Markdown, slide, spreadsheet, or table formats are supplemental unless the user explicitly prohibits file output.

Full-quality output requires:

- Use-case name, description, status, department/owner, and production/pipeline indicators.
- Systems/applications, volume, handling time, hours saved, benefit, value, ROI, priority, complexity, or similar fields where available.
- Deployment context: cloud/on-prem/hybrid/FedRAMP/public sector cloud, security constraints, GenAI policy, human approval needs, integration constraints, and governance model.
- UiPath footprint: known products, entitlements, CoE maturity, and existing capability usage.
- Permission to use public research, or user-provided strategy sources.
- Target audience, output depth, and whether the `.docx` brief is internal planning or customer-ready.

The auditable machine path also requires versioned `evidence_ledger.json` and `portfolio.json`
artifacts. Use `references/data_contracts.md`. Unversioned JSON and unsupported versions fail
closed; do not treat legacy JSON or Markdown-only validation as evidence certification.

If the inventory or customer name is missing, ask for it before full analysis. If deployment, value, or entitlement details are missing, proceed only with explicit caveats.

## Execution workflow

Follow this sequence:

1. Intake gate: confirm minimum viable inputs and note missing full-quality inputs.
2. Inventory profiling: run `scripts/inventory_profiler.py` for spreadsheet/csv inventories.
3. Inventory normalization: classify production, pipeline, idea, unknown, and excluded rows; preserve generated `INV-*` IDs.
4. Public strategy ledger: research current customer strategy using authoritative sources unless the user says not to browse; assign dated `SRC-*` IDs.
5. Assumption ledger: record every planning assumption with an `ASM-*` ID and validation status.
6. Strategy-to-inventory crosswalk: map public priorities to inventory clusters by ID.
7. Candidate generation: create specific `OPP-*` opportunities from strong crosswalks.
8. Agentic suitability test: reject deterministic, low-value, or unsupported candidates.
9. Deterministic scoring and validation: run `scripts/score_portfolio.py`, then `scripts/validate_portfolio.py`.
10. Value framing: use supported deterministic formulas or qualitative sizing; never invent arithmetic.
11. Capability and deployment validation: map likely capability fit without entitlement overclaims; assign each applicable deployment constraint to at least one active opportunity so the portfolio covers every constraint without repeating irrelevant controls.
12. Executive packaging: require accountable pilot owners, render Markdown with visible score rationale and deterministic tie handling, cross-check it with `scripts/validate_executive_brief.py` plus the JSON artifacts, then preserve the DOCX render and brand-verification flow.

## Inventory profiling script

For uploaded inventory files, run:

```bash
python scripts/inventory_profiler.py --input work/planner/inventory.xlsx --outdir work/planner/profile
```

For a specific worksheet:

```bash
python scripts/inventory_profiler.py --input work/planner/inventory.xlsx --sheet "Sheet Name" --outdir work/planner/profile
```

Read both outputs before recommending:

- `inventory_profile.md`: analyst-readable summary.
- `inventory_profile.json`: structured detected columns, data quality, status counts, numeric fields, and top metric rows.

Profile schema `1.0` also emits `inventory_items` with stable IDs in the form
`INV-<SHEET>-R<ROW>`, canonical profile fields, and detected metric values. Shorthand quantities
such as `~24k` are normalized numerically. Inserting rows or renaming a sheet changes IDs;
regenerate the profile and deliberately migrate ledger references instead of silently reusing
stale IDs. Strict validation reconciles name, description, status, department, owner, systems,
source row, and detected metrics against the ledger.

Use the script output as a starting point, not final truth. Validate suspicious mappings manually when column names are ambiguous.

## Evidence rules

- Treat inventory rows as operational signals, not audited facts.
- Treat production/live rows as strongest evidence.
- Exclude retired, cancelled, rejected, duplicate, archived, and decommissioned rows from primary value calculations unless the user asks for historical analysis.
- Do not treat idea backlog as production demand.
- Use public sources for strategy alignment and cite public facts.
- Prioritize official strategic plans, annual reports, budgets, performance reports, regulatory filings, official dashboards, and official press releases.
- Use secondary sources only as support.
- Separate facts, assumptions, and inferences.
- Cite inventory facts with `INV-*`, public facts with `SRC-*`, and planning assumptions with `ASM-*`.
- Do not use excluded inventory IDs as recommendation evidence.
- Record publication and access dates for every public source.
- Mark synthetic sources as non-official. Official sources require HTTPS and cannot use reserved,
  local, private, or non-resolving placeholder hosts.
- A confirmed entitlement claim requires matching confirmed ledger evidence; otherwise say `likely fit`.

## Versioned portfolio pipeline

Use schema version `1.0` and score model `1.0`:

```bash
python3 scripts/score_portfolio.py \
  --evidence-ledger evidence_ledger.json \
  --portfolio portfolio_draft.json \
  --output portfolio.json

python3 scripts/validate_portfolio.py \
  --evidence-ledger evidence_ledger.json \
  --portfolio portfolio.json \
  --inventory-profile inventory_profile.json

python3 scripts/render_portfolio_markdown.py \
  --evidence-ledger evidence_ledger.json \
  --portfolio portfolio.json \
  --inventory-profile inventory_profile.json \
  --output brief.md
```

The scorer refuses in-place overwrite. Validation rejects unknown fields, missing versions,
dangling evidence, excluded evidence, stale scores/ranks, unsupported value math, missing
deployment controls, rejected assumptions, and entitlement overclaims. Follow the migration
steps in `references/data_contracts.md`; do not weaken a failure into a warning.

Active pilots require an accountable person or role; `TBD`, `unassigned`, and similar placeholders
fail validation. Narrative fields are bounded for executive use, the renderer refuses briefs above
3,500 words by default, and the prioritized table exposes scoring strengths and limiting criteria.

## Recommendation rules

A recommendation must include:

- Specific use-case name.
- Inventory evidence.
- Public strategy alignment.
- The customer "why now" and the decision ask or next step.
- Agentic enhancement beyond baseline RPA.
- UiPath capability fit stated as likely fit, not entitlement.
- Value levers.
- Feasibility notes.
- Governance notes.
- Validation questions.

Reject or downgrade recommendations that are generic, unsupported by inventory, unsupported by strategy, deterministic with no agentic need, high-risk without human review, or dependent on invented ROI.

Before rendering, apply `references/brand_and_brief_quality.md`. Reject vendor-brochure language, hype terms, or product-first summaries that do not start from the customer's need.

## Default outputs

Unless the user asks for something else, produce:

1. Versioned `evidence_ledger.json` and deterministically scored `portfolio.json`.
2. Executive summary.
3. Source and assumption note.
4. Current automation footprint.
5. Public strategy alignment summary.
6. Prioritized portfolio table.
7. Top 5 high-impact agentic recommendations.
8. Top 3 low-friction POC candidates.
9. Value framing and assumptions.
10. Deployment and governance considerations.
11. Facts, assumptions, and validation questions.
12. Workshop prep.
13. Recommended next steps.
14. Appendix: source ledger.

The final artifact is always a structurally verified `.docx` Word executive brief in `outputs/` when that directory exists. If the user asks for chat, Markdown, slide, spreadsheet, proposal-card, or account-plan content, provide it only as a supporting artifact or excerpt; do not treat it as the final output unless `.docx` creation is impossible or the user explicitly prohibits file output.

## Word executive briefing output

For every run:

1. Write a concise Markdown briefing first. Do not render raw research notes directly to Word.
2. Follow `references/brand_and_brief_quality.md` and `references/executive_docx.md` for executive voice, default AZ DES-style executive portfolio structure, table patterns, proposal-card density, workshop prep, brand-safe styling, and verification. If the analysis draft is long, create a separate concise Word-source Markdown rather than rendering raw research notes.
3. Validate the Markdown quality gate with:

```bash
python3 scripts/validate_executive_brief.py <brief.md> \
  --evidence-ledger <evidence_ledger.json> \
  --portfolio <portfolio.json> \
  --inventory-profile <inventory_profile.json>
```

The JSON arguments are required for evidence-certified output. Calling the validator without
them performs legacy structural checks only and must not be represented as claim certification.

4. Render the Markdown with:

```bash
python scripts/render_executive_docx.py <brief.md> <brief.docx> --portrait
```

5. Save the final `.docx` under the user-facing `outputs/` directory when that directory exists.
6. Verify the resulting document with structural and brand-style checks:

```bash
python scripts/verify_executive_docx.py <brief.docx> --require-output-dir --require-brand-style
```

7. If the environment has the Documents skill renderer available, render the `.docx` to page images and visually inspect them before delivery. If visual rendering is unavailable, state that only structural verification was completed.
8. Final chat responses must link to the generated `.docx` and summarize the verification result. Do not stop with Markdown, CSV, slide outline, or chat text as the final deliverable.

The default Word brief must be executive-skimmable and GTM/workshop-ready. It should contain the executive thesis, current footprint, strategy alignment, ranked portfolio, top 5 high-impact recommendations, top 3 low-friction POC candidates, value framing, deployment/governance considerations, facts/assumptions/validation questions, workshop prep, recommended next steps, and a concise appendix source ledger. Use a shorter compact brief only when the user explicitly asks for a short executive summary, minimal proposal-card output, or a very concise table-first artifact. It should not include raw research notes or every row-level detail.

## Reference loading guide

- Use `references/input_contract.md` when assessing whether inputs are sufficient.
- Use `references/methodology.md` for the complete workflow and evidence gates.
- Use `references/scoring_model.md` for ranking, weighting, confidence, and rejection criteria.
- Use `references/data_contracts.md` for v1 evidence, portfolio, migration, and value-formula rules.
- Use `references/output_templates.md` for executive briefs, proposal cards, POC cards, source ledger, and workshop agenda.
- Use `references/brand_and_brief_quality.md` before writing the final Markdown and before rendering any Word brief.
- Use `references/executive_docx.md` when the output is a Word executive brief or `.docx`.
