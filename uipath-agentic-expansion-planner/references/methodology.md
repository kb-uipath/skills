# Methodology

## Core principle

Use the customer's inventory as operational evidence and public strategy as relevance evidence. The final customer assessment must explain the current footprint and a small number of end-to-end process opportunities. Do not brainstorm generic AI use cases.

## 1. Intake

Confirm:

- Customer identity and sector.
- One primary inventory file.
- Audience and account objective.
- Deployment, data, GenAI, and human-approval context.
- Whether public research is allowed.

Use `input_contract.md`. Missing inventory or customer identity blocks a full assessment. Missing deployment, value, or entitlement information becomes a named validation requirement.

## 2. Profile the inventory

Run `inventory_profiler.py` and read both outputs. Profile `1.1` provides stable inventory IDs, exact source identity, normalized source-record dates and date quality, detailed lifecycle status, field coverage, process text, owners, departments, systems, and numeric signals. If valid record dates exist, the ledger as-of date must equal the latest valid date; never use the assessment date as source freshness.

Review ambiguous detected columns manually. Regenerate and deliberately remap references after sheet or row changes.

## 3. Normalize lifecycle evidence

Use detailed lifecycle status for the customer footprint:

- Deployed.
- Pipeline.
- Paused.
- Retired.
- Cancelled.
- Rejected.
- Duplicate.
- Idea.
- Unknown or other.

Use the existing coarse status for recommendation safety. Retired, cancelled, rejected, duplicate, and archived records cannot support active value claims.

## 4. Build the evidence ledger

Create schema `1.0` `evidence_ledger.json`:

- `INV-*` rows must match the profile.
- `SRC-*` public sources require dates and evidence summaries.
- `ASM-*` assumptions require category and status.
- Deployment, data classification, GenAI policy, human approvals, and entitlements remain explicit.

Official evidence must use real public HTTPS sources. Mark synthetic fixtures non-official. Never treat a title or linked ID as proof that a source supports a claim.

## 5. Generate specific candidates

Crosswalk customer strategy against repeated inventory patterns. A candidate must identify:

- Business process and outcome.
- Current inventory evidence.
- Customer reason to act.
- Agentic need beyond deterministic automation.
- Value lever.
- Deployment and governance boundary.
- Bounded pilot and accountable owner.

Reject product-first, unsupported, immaterial, or unsafe candidates. A rules-based process can still be a strong robot or orchestration opportunity; do not force agentic or GenAI behavior into it.

## 6. Score and validate

Analysts assign criterion inputs from 0 to 5. `score_portfolio.py` owns arithmetic, rounding, and tie-breaking. Keep high-impact and low-friction rankings as internal decision support.

Use conservative value logic. Do not invent rates, volumes, entitlement, or deployment feasibility. Use qualitative sizing when supported formulas and inputs are unavailable.

## 7. Confirm end-to-end process groups

Create schema `1.0` `process_map.json`. Every inventory ID must appear exactly once in a process or an explicit unmapped record.

For each process, define:

- Business function.
- Start condition.
- End condition.
- Business outcome.
- Exact inventory membership and rationale.

Then record a prioritization decision for every process. State the method and criteria, rank selected and deferred processes, and explain each selection, deferral, or non-priority decision. For each decision, put source-supported facts in `observed_evidence` and unresolved owner/data questions in `validation_needed`; never mix them. A selected rationale explains why it outranks alternatives. A deferred rationale explains why it ranks lower and what triggers reconsideration. Compare strategy alignment, available workload signals, the current automation foundation, process coherence, delivery risk, and evidence quality. Selected process ranks must match portfolio recommendation order.

Treat annual volume and handling time as workload signals, not savings. A stated strategy priority or a higher-workload process may be deferred, but the tradeoff must be explicit and customer-readable.

For each selected opportunity, map the existing automation foundation and ordered orchestration stages. State separate roles for Maestro, agentic support, GenAI, robots, and human review as `applies`, `not_needed`, or `validation_required`.

Add a `measurement_plan` for each selected opportunity. It names the numeric selection method, historical reviewer-owned ground truth, the accountable owner of that truth set, at least two explicit numerator/denominator formulas with comparable units for ratio metrics, cadence, and accountable measurement owner. Mixed results require correction and rerun; no recommendation may proceed until every gate passes. The next action also names data/security approval, UiPath product/deployment validation, and the fallback when access, linkage, taxonomy, or ownership cannot be confirmed.

An analyst must confirm process membership before workshop-ready output. Keyword or model-suggested grouping alone is exploratory.

Inventory omission and evidence status are separate questions. A dated, hash-bound customer source
may confirm a specific join field, outcome owner, or historical sample even when the inventory does
not contain that column. Preserve both facts: say what the inventory omitted, cite the source that
resolved it, and perform the stated analyst sample check. Leave product, deployment, entitlement,
baseline, value, funding, and approval items unresolved unless separately supported.

## 8. Run semantic review

Give a human or independent agent the raw evidence and generated artifacts without an expected answer. Bind the review to exact artifact hashes.

Review every selected recommendation for:

- Inventory and strategy support.
- Process coherence.
- Genuine agentic need.
- Capability fit.
- Value logic.
- Pilot realism.
- Customer language.

Critical failed claims, blocking findings, fallback-only review, or stale review force `exploratory`. Capability or value details may remain `needs_validation` at `workshop_ready` only when the customer language says so plainly.

For agentic need, pass means the reviewer agrees with the evidence-backed
`applies` or `not_needed` determination. Do not equate a passing review with a
requirement to add agentic behavior.

Score the separate answer-blind outcome review against the intended two-page
workshop assessment, not against a solution design, implementation runbook, or
investment-grade business case. Score clarity, process specificity, decision
utility, and account-team actionability from 1 to 5: `1` is unusable, `2` has
major unsafe gaps, `3` needs material restructuring before a workshop, `4` is
workshop-usable with bounded follow-up, and `5` is exceptional. Every dimension
must score at least `4`; a lower score blocks release and requires substantive
revision before another independent review.

## 9. Build the customer assessment

Use `build_customer_assessment.py`. The deterministic customer document contains exactly:

1. Source File Summary.
2. Current Automation Footprint.
3. Top 3 Recommendations.

Render one to three recommendations in high-impact rank order. Never fill empty slots with weaker ideas.

The recommendation section starts with a compact rank comparison, the bounded workshop ask, the customer-baseline and control-tolerance basis for final thresholds, and material deferred process groups. Each recommendation then uses labeled bullets for the business function plus explicit Start, End, and Outcome boundaries; the customer why; automation count and named foundation with raw lifecycle status; a historical input whose sample matches the proceed gate; ground truth and its owner; join or linkage method; observable output; metric formulas, cadence, and measurement owner; qualified capability roles and validation needs; no-write boundary; a measurable stop/proceed/adjust gate with one decision owner; and one owned account-team action with absolute target kickoff and decision dates. The footprint shows the complete lifecycle mix, named analyst-mapped process groups with automation counts, department and system concentrations, and the unmapped count. The customer layer may show source-reported volume and handling time as separate, unvalidated workload signals. Detailed selection evidence, scores, aggregation, value math, and validation tasks remain in the internal package. The customer document names deferrals but keeps their detailed evidence and reconsideration logic internal.

Before the rank table, assign the shared account artifacts and timing: CSM agenda/access by each
target, TAM product/tenant control note before each charter, and AE sponsor/funding decision after
evidence. A failed prerequisite follows the named fallback and defers the pilot.

State the shared stitch mechanics once: the correlation layer joins frozen exports on confirmed
identifiers, Maestro sequences system and human handoffs, Robots produce deterministic outputs,
humans review, unmatched records pause and rerun, and the final record system requires validation.

Treat every future stage as a design assumption. For a multi-automation process, confirm a shared case identifier, sequence, and ownership handoff or state the exact linkage check required before launch. Any system-changing step follows human review and records only a human-confirmed or human-approved result. Label customer-visible numeric gates as proposed workshop criteria. The named owner must confirm the baseline, measurement protocol, error cost, and final thresholds before launch.

The builder enforces 900 words, plain language, approved brand tokens, portrait orientation, and an actual one-to-two-page PDF render. It publishes that exact PDF beside the DOCX so receipt provenance can be checked. Missing page verification produces only a marked exploratory draft.

## 10. Preserve the internal package

Retain:

- Profile JSON and Markdown.
- Evidence ledger.
- Scored portfolio.
- Process map.
- Semantic review.
- Customer Markdown source.
- Build receipt.

Use the legacy detailed renderer only for internal analysis. Do not copy its scores, IDs, validation narration, POC duplication, or source appendix into the default customer DOCX.

## 11. Deliver

Link the final DOCX and state readiness, page count, recommendation count, and verification status. If any critical gate failed, label the artifact exploratory and do not claim it is customer-ready or pilot-authorizable.
