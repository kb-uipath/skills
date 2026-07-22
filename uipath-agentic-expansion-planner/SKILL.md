---
name: uipath-agentic-expansion-planner
description: analyze customer automation or use-case inventories and produce a concise, evidence-backed UiPath automation portfolio assessment. use when a CSM, TAM, AE, or customer needs a clear current automation footprint, analyst-mapped end-to-end process groups with explicit customer-confirmation needs, and up to three actionable Act 2, Maestro, agentic, GenAI, robot, and human-review recommendations in a branded one-to-two-page DOCX. preserve detailed evidence and scoring as internal artifacts, require independent semantic review for customer-ready output, and never invent recommendations to fill a quota.
---

# UiPath Agentic Expansion Planner

## Purpose

Turn one customer automation inventory into two layers:

1. A one-to-two-page customer-ready automation portfolio assessment.
2. An internal evidence package containing the profile, ledger, scored portfolio, process map, semantic review, and validation receipt.

The customer document is simple but specific. It shows the source reviewed, current footprint, and up to three end-to-end process recommendations. It must not read like generic AI brainstorming or expose internal evidence IDs and scoring mechanics.

## Required Inputs

Minimum inputs:

- Customer name and sector.
- One primary `.csv`, `.tsv`, `.xlsx`, or `.xlsm` inventory. Multi-sheet workbooks are supported; multi-file consolidation is not.
- Target audience and account objective.

Full-quality inputs:

- Automation name, description, lifecycle status, department, owner, systems, and available volume/value fields.
- Deployment model, data classification, GenAI policy, human-approval rules, and integration constraints.
- Known UiPath footprint and entitlements, using `unknown` when unconfirmed.
- Current authoritative public strategy evidence, customer-confirmed account context, or permission to research.

Read `references/input_contract.md` before proceeding. If the inventory or customer identity is missing, stop and ask for it. If value, deployment, or entitlement details are missing, continue only with explicit validation requirements.

## Standard Workflow

1. Profile the primary inventory with `scripts/inventory_profiler.py`.
2. Read both generated profile files and correct ambiguous field mappings.
3. Build schema `1.0` `evidence_ledger.json` and deterministically scored `portfolio.json`.
4. Create schema `1.0` `process_map.json`, mapping every inventory ID once and recording observed evidence, comparative rationale, and validation needs for every selected or deferred process.
5. Require an account analyst to confirm the mapping as analysis. Keep customer confirmation separate and explicit.
6. Use a human or independent agent to create schema `1.0` `semantic_review.json` without giving the reviewer an expected answer.
7. Run the customer-assessment builder. It validates contracts, review freshness, plain language, branding, and the rendered two-page limit.
8. Deliver the DOCX plus the internal evidence package. Do not represent an exploratory draft as customer-ready.

No step performs live writes to UiPath, SharePoint, Salesforce, Outlook, or another external system.

## Inventory Profile

Run:

```bash
python3 scripts/inventory_profiler.py \
  --input work/planner/inventory.xlsx \
  --outdir work/planner/profile
```

Profile `1.1` adds:

- Safe source basename and source SHA-256.
- Normalized per-record source dates plus earliest/latest, valid, invalid, and nonblank date counts. When valid source dates exist, the ledger `as_of_date` must equal the latest one.
- Sheet and physical row counts, plus per-sheet field mappings for mixed header aliases.
- Field coverage.
- Raw status plus detailed lifecycle categories: deployed, pipeline, paused, retired, cancelled, rejected, duplicate, idea, unknown, and other.
- Stable `INV-*` IDs and normalized metrics.

Profile `1.0` remains valid for the legacy detailed renderer. Customer-ready builds require `1.1`.

## Evidence And Portfolio

Use `references/data_contracts.md` and `references/scoring_model.md`.

```bash
python3 scripts/score_portfolio.py \
  --evidence-ledger work/planner/evidence_ledger.json \
  --portfolio work/planner/portfolio_draft.json \
  --output work/planner/portfolio.json

python3 scripts/validate_portfolio.py \
  --evidence-ledger work/planner/evidence_ledger.json \
  --portfolio work/planner/portfolio.json \
  --inventory-profile work/planner/profile/inventory_profile.json
```

Keep inventory facts, public sources, and assumptions separate as `INV-*`, `SRC-*`, and `ASM-*`. Excluded inventory cannot support an active recommendation. Value math must use supported formulas and referenced inputs. Capability fit is not an entitlement claim.

A dated, hash-bound customer-confirmed account source may resolve a specific inventory omission such
as a join field, outcome owner, or available historical sample. Cite that source, retain the
inventory omission in the narrative, and do not extend the confirmation to deployment,
entitlement, baseline, value, funding, or approval claims that the source does not establish.

## Process Map

The process map is a semantic artifact, not keyword clustering. For each process, define:

- Business function.
- Start condition, end condition, and business outcome.
- Exact inventory membership.
- Membership rationale.
- Cross-record linkage as `confirmed`, `validation_required`, or `not_applicable`, with the exact pre-launch validation step. Never infer shared cases from common systems alone.
- Selection status, rank when selected or deferred, strategy alignment, and a comparative plain-language rationale.
- `observed_evidence`: source-supported facts only. Never place an assumption, proposed design, or validation task here.
- `validation_needed`: the customer evidence or decision still required.

`confirmed` linkage requires either the inventory join field or a dated, hash-bound customer source
that names the join field and covered records. When the second path is used, state that the inventory
omits the field and require an analyst sample check before the workshop.

Define one prioritization method using at least three supported criteria. Compare strategy alignment, available workload signals, the existing automation foundation, process coherence, delivery risk, and evidence quality as applicable. Selected ranks must match the deterministic portfolio order. Every selected rationale must explain why that process outranks alternatives. Every deferral must explain why it is lower and what would trigger reconsideration. A stated strategy priority or material workload signal must never disappear silently.

The customer layer states one bounded workshop ask: validate prerequisites and historical pilots,
set final thresholds from customer baselines and control tolerances, and make no deployment or
investment approval. Name material deferred process groups and why they remain deferred.

The customer comparison must account for every process and every unmapped record. Do not label a proposed label set, historical sample, approval-history field, checklist, or threshold as evidence unless the source actually contains it.

Use `strategy_alignment: confirmed` only for customer-confirmed or authoritative strategy evidence. A supplied account note or non-official planning source is `validation_required`; the customer document must call it a planning priority to confirm.

For each selected recommendation, define:

- Existing automation foundation.
- `stitch_existing`, `extend_single`, or `net_new` pattern.
- Ordered stages labeled `current_state`, `pilot`, or `future_state`.
- A `measurement_plan` with numeric sample selection, reviewer-owned ground truth, a named ground-truth owner, at least two numerator/denominator formulas with comparable units for ratio metrics, review cadence, measurement owner, and a rerun/no-proceed rule for mixed results.
- An explicit join or linkage test for multi-automation processes and an observable pilot output.
- Separate applicability and plain-language roles for Maestro, agentic support, GenAI, robots, and human review.
- One customer decision owner, one UiPath account-team owner, data/security approval ownership, product/deployment validation ownership, a fallback when prerequisites fail, a deliverable, preparation target within 30 days, and absolute target and decision dates in the rendered assessment.
- A bounded, stop-first pilot gate using `Stop if ... . Go if ... . Revise if ... .` The go outcome needs a quantitative sample or quality measure, the revise outcome must name an intermediate range, and the stop outcome must cover the remaining quantitative failure range.

Future orchestration stages are proposed design, not observed current state. A shadow pilot cannot contain a system-changing action. Any later system-changing robot or system-of-record stage is `future_state`, follows human review, requires separate authorization, and says that it records only a human-confirmed or human-approved result. Thresholds are workshop proposals until the named customer owner confirms the baseline, measurement protocol, error cost, and final thresholds.

A historical read-only shadow may measure agreement, coverage, precision, recall, and source-data baselines. It cannot claim actual live cycle-time reduction; reserve that outcome for a separately authorized live test.

Validate it:

```bash
python3 scripts/validate_process_map.py \
  --inventory-profile work/planner/profile/inventory_profile.json \
  --portfolio work/planner/portfolio.json \
  --process-map work/planner/process_map.json
```

Customer-ready output requires `analyst_confirmed`. Suggestions may remain exploratory.

## Semantic Review

The semantic review binds exact SHA-256 hashes for the profile, ledger, portfolio, and process map. Review every selected recommendation for:

- Inventory support.
- Strategy support.
- Process coherence.
- Genuine agentic need.
- Capability fit.
- Value logic.
- Pilot realism.
- Customer language.

Readiness levels:

- `exploratory`: unconfirmed map, single-agent fallback, failed critical claim, blocking finding, or incomplete evidence.
- `workshop_ready`: analyst-confirmed map, independent or human review, concrete existing foundation, and all critical claims passed. Capability or value details may remain clearly marked for validation.
- `pilot_authorizable`: every review passed, assumptions validated, deployment compatible, capability claims supported, and pilot controls complete.

A review must not predate any bound artifact and must be no more than 30 days old.

`agentic_need: pass` means the evidence supports the declared `applies` or
`not_needed` decision. It does not mean an agent must be present. Marking a
deterministic process `not_needed` is the correct outcome when judgment,
ambiguity, or adaptive reasoning is not established.

```bash
python3 scripts/validate_semantic_review.py \
  --inventory-profile work/planner/profile/inventory_profile.json \
  --evidence-ledger work/planner/evidence_ledger.json \
  --portfolio work/planner/portfolio.json \
  --process-map work/planner/process_map.json \
  --semantic-review work/planner/semantic_review.json \
  --required-readiness workshop_ready
```

## Customer-Ready Build

Use the standard entrypoint:

```bash
python3 scripts/build_customer_assessment.py \
  --inventory-profile work/planner/profile/inventory_profile.json \
  --evidence-ledger work/planner/evidence_ledger.json \
  --portfolio work/planner/portfolio.json \
  --process-map work/planner/process_map.json \
  --semantic-review work/planner/semantic_review.json \
  --supporting-source work/planner/strategy-context.md \
  --output outputs/customer-automation-portfolio-assessment.docx
```

The builder requires `python-docx`, `pypdf`, and `soffice`. Repeat `--supporting-source` for local strategy or account-context files that must be hash-bound; only safe basenames and SHA-256 values enter the receipt. The builder publishes the DOCX, its Markdown source, the exact PDF used for page verification, and a validation receipt. It fails unless the final DOCX:

- Is in an `outputs/` directory.
- Contains exactly `Source File Summary`, `Current Automation Footprint`, and `Top 3 Recommendations` sections.
- Contains one to three recommendations in deterministic portfolio order.
- Is no more than 900 words and two rendered pages.
- Uses UiPath-derived brand colors and Arial.
- Contains no internal IDs, score narration, schema language, hype, or oversized prose.

The builder discovers LibreOffice on `PATH` and in common install locations; use `--soffice` for a custom executable. `--draft-without-page-check` is allowed only for an internal exploratory artifact. It adds a draft title and cannot produce customer-ready readiness. Output paths must not collide with any input or supporting source, even with `--force`.

## Customer Document Content

The three sections must communicate:

1. Source basename, tables or sheets, records, available fields, observed field-coverage gaps, and the three most material limitations or unconfirmed planning assumptions.
2. Exact lifecycle mix, named analyst-mapped process groups with automation counts and a customer-confirmation label, department/system concentrations, and the unmapped count.
3. A rank comparison, bounded workshop ask, and material deferrals followed by up to three scan-oriented recommendations. Each recommendation includes business function plus explicit Start/End/Outcome boundaries, separate source-reported workload signals when units or linkage are unconfirmed, automation count and named foundation with raw lifecycle status, a read-only pilot input and selection method, ground truth plus its accountable owner, linkage method, observable output, metric formulas with auditable units, review cadence and measurement owner, qualified capability roles and validation needs, no-write controls, a measurable stop/proceed/adjust gate with one decision owner, and one dated next action with fallback.

The recommendation preamble also assigns shared account artifacts and timing: the CSM delivers the
agenda and access by each target, the TAM delivers a product/tenant control note before each charter,
and the AE delivers a sponsor/funding decision after evidence. Failed prerequisites defer.
It also separates data correlation from product roles: frozen exports join on confirmed identifiers,
Maestro sequences handoffs, Robots prepare deterministic outputs, humans review, unmatched records
pause and rerun, and the final record system remains a validation item.

When capability, product availability, deployment, or value evidence is incomplete, add a plain validation statement in the recommendation controls. Do not hide that limitation in the internal package.

Use customer language. Lead with the business process and outcome; name products only to explain their role. Never add weak recommendations to reach three.

## Internal Detailed Mode

The existing detailed path remains available for analysts:

```bash
python3 scripts/render_portfolio_markdown.py \
  --evidence-ledger work/planner/evidence_ledger.json \
  --portfolio work/planner/portfolio.json \
  --inventory-profile work/planner/profile/inventory_profile.json \
  --output work/planner/detailed-brief.md
```

This detailed Markdown is supporting analysis. It is not the default customer deliverable.

## Final Response

Link the final DOCX and its verified PDF, then state:

- Readiness level.
- Page count.
- Recommendation count.
- Whether brand, semantic, and layout verification passed.

If any required check was unavailable or failed, label the artifact exploratory and do not call it customer-ready.

## References

- `references/input_contract.md`: input sufficiency.
- `references/data_contracts.md`: versioned artifacts and migration.
- `references/methodology.md`: evidence-first analysis.
- `references/scoring_model.md`: deterministic ranking.
- `references/output_templates.md`: customer and internal output patterns.
- `references/brand_and_brief_quality.md`: voice and visual rules.
- `references/executive_docx.md`: DOCX rendering and inspection.
