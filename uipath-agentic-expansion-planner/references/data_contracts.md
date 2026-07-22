# Versioned data contracts

The customer-assessment path uses five artifacts:

- Profile `1.1` from `inventory_profiler.py`.
- [`evidence_ledger.json`](contracts/evidence_ledger.v1.schema.json) `1.0`.
- [`portfolio.json`](contracts/portfolio.v1.schema.json) `1.0`.
- [`process_map.json`](contracts/process_map.v1.schema.json) `1.0`.
- [`semantic_review.json`](contracts/semantic_review.v1.schema.json) `1.0`.

The detailed legacy path continues to accept profile `1.0`. Customer-ready output requires profile `1.1` and all five artifacts.

## Profile 1.1

Profile `1.1` preserves the existing stable `INV-*` identifiers and adds:

- Safe source basename and source SHA-256. Profile `1.1` does not retain the local source path.
- Raw status and detailed lifecycle status.
- Lifecycle counts for deployed, pipeline, paused, retired, cancelled, rejected, duplicate, idea, unknown, and other.
- Sheet, physical row, field-coverage, department, owner, system, and metric summaries.
- Per-sheet field mappings so valid aliases on different workbook sheets remain distinct.
- Normalized `source_date` on each row plus a `source_date_summary` containing mapped date columns, valid/invalid/nonblank counts, and earliest/latest valid dates.

When valid source dates exist, `evidence_ledger.inventory_profile.as_of_date` must equal the profile's latest valid source record date. Do not substitute the profile generation date, assessment date, or review date for source freshness. If no valid source date exists, keep the summary explicit and state that limitation in the customer assessment.

Never add an absolute source path to the profile, customer document, or public fixture.

## Evidence and portfolio 1.0

Use `INV-*` for source rows, `SRC-*` for public sources, `ASM-*` for assumptions, and `OPP-*` for opportunities. Unknown fields, dangling references, stale scores, excluded evidence, unsupported value math, placeholder owners, unsafe URLs, deployment gaps, and entitlement overclaims fail validation.

Supported calculated-value formulas remain:

- `volume_minutes_rate_v1`: `annual_volume * minutes_saved_per_case / 60 * loaded_hourly_rate`.
- `hours_rate_v1`: `annual_hours * loaded_hourly_rate`.

Use qualitative value framing when evidence is incomplete.

## Process map 1.0

`process_map.json` binds to the profile source SHA-256 and must cover every inventory ID exactly once through an analyst-mapped process or an explicit unmapped record.

Each process requires:

- `PROC-*` ID, name, and business function.
- Start condition, end condition, and business outcome.
- Inventory membership and rationale.
- Linkage status, rationale, and validation step. Multi-automation processes cannot use `not_applicable`; single-automation processes must.

`prioritization` requires:

- A plain-language method and at least three supported criteria.
- One decision for every process: `selected`, `deferred`, or `not_prioritized`.
- Consecutive ranks for selected and deferred processes; `not_prioritized` uses a null rank.
- Strategy-alignment status and comparative rationale for every decision.
- `observed_evidence`: one or more source-supported facts. Assumptions, proposed controls, and validation tasks fail this field.
- `validation_needed`: evidence or owner decisions still required. It cannot be empty for a selected or deferred non-official planning priority.
- Selected ranks that exactly match deterministic portfolio recommendation order.

Reserve `strategy_alignment: confirmed` for customer-confirmed or authoritative evidence. Use `validation_required` for non-official planning context and carry that limitation into the customer comparison.

Every selected rationale explains why that process outranks alternatives. Every deferred rationale explains why it ranks lower and what must occur before reconsideration. This is a decision-quality control, not customer-facing score narration. It prevents a stated strategy priority or material workload signal from disappearing without an explicit tradeoff and prevents a proposed baseline from being mislabeled as observed evidence.

Each selected `OPP-*` requires an orchestration record with:

- Existing automation IDs.
- `stitch_existing`, `extend_single`, or `net_new` pattern.
- Consecutive ordered stages with monotonic `current_state`, `pilot`, and `future_state` phases.
- Separate applicability and roles for Maestro, agentic support, GenAI, robots, and human review.
- `measurement_plan` with a numeric selection method that matches the proceed gate, reviewer-owned ground truth, a non-placeholder `ground_truth_owner`, at least two named numerator/denominator formulas, `daily`, `weekly`, or `per_case` cadence, and a measurement owner matching the pilot and next-step owner. Accuracy, agreement, coverage, linkage, precision, and recall ratios must use comparable numerator and denominator units; for example, use `reviewed cases with complete evidence / reviewed cases`, not `complete fields / reviewed cases`.
- A mixed-result action that requires correction and rerun and prohibits proceeding until every gate passes.
- Customer owner, UiPath account-team owner, next action, deliverable, and target from 1 to 30 days.
- Pilot exit criterion in exact stop-first order: `Stop if ... . Go if ... . Revise if ... .` The go condition names a quantitative success range, the revise condition names the intermediate range, and the stop condition covers the remaining quantitative failure range plus critical control breaches.
- A shadow-pilot phase contains no system-changing action. Any later write is `future_state`, follows human review, requires separate authorization, and records only a human-confirmed or human-approved result.
- A historical read-only shadow cannot use live cycle-time reduction as a go or revise measure. Use record-observable quality or coverage metrics and reserve live outcomes for a separately authorized test.

The rendered next action converts the semantic-review date plus `target_days` into an absolute target kickoff date, then adds `pilot.timeline_days` for the decision date. The date is a workshop target, not an approved launch commitment. Do not expose unanchored `day 14` or `day 21` language. The action must identify data/security approval, product/deployment validation, and what happens when access or linkage prerequisites fail.

`analyst_confirmed` is mandatory for workshop-ready output, but it confirms the analyst's mapping, not customer agreement. The customer assessment labels those groups as analyst-mapped and requiring customer confirmation.

`linkage.status: confirmed` may be supported by an inventory field or by a dated, hash-bound
customer-confirmed source that names the join field and covered exports. The latter does not erase
the inventory omission: `linkage.rationale` must state both the omission and the supporting source
fact, and `validation_step` must require an analyst sample check. Ownership and sample availability
follow the same narrow rule. Confirmation does not cascade to deployment, entitlement, baseline,
value, funding, or pilot authorization.

## Semantic review 1.0

`semantic_review.json` binds exact hashes of the profile, evidence ledger, portfolio, and process map. It reviews each selected recommendation for inventory support, strategy support, process coherence, agentic need, capability fit, value logic, pilot realism, and customer language.

Reviewer modes:

- `human`
- `independent_agent`
- `single_agent_fallback`

A fallback review cannot exceed `exploratory`. Review freshness is 30 days by default and the review cannot predate a bound artifact.

The `agentic_need` claim evaluates whether evidence supports the declared
agentic applicability. It may pass when `agentic` is `not_needed`; never treat
the claim name as a requirement to add an agent.

## Migration

1. Regenerate the profile to produce `1.1` source and lifecycle metadata.
2. Keep valid evidence-ledger and portfolio `1.0` artifacts; rerun scoring if the profile changed inventory IDs or fields.
3. Create and validate `process_map.json`.
4. Run a human or independent semantic review against the exact artifact hashes.
5. Use `build_customer_assessment.py` for the concise DOCX.

Do not add a version field to an old artifact and assume it is migrated. Regenerate or reconcile all IDs and hashes deliberately.
