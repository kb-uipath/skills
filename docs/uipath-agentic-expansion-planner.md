# uipath-agentic-expansion-planner

Produce a concise, evidence-backed UiPath automation portfolio assessment from one customer inventory.

## When To Use

Use this skill when a CSM, TAM, AE, or customer needs to understand:

- What automation exists today.
- How the portfolio is distributed by lifecycle, process, department, and system.
- Which existing automations can form an end-to-end process.
- Where Maestro, agentic support, GenAI, robots, and human review can add value.
- What the account team should do next.

The default customer deliverable is a branded one-to-two-page DOCX with up to three recommendations. Detailed scoring and evidence remain separate internal artifacts.

## Runtime And Dependencies

- Python 3.11 or newer.
- Standard library for CSV/TSV profiling and contract validation.
- `openpyxl==3.1.5` for Excel inventories.
- `python-docx==1.2.0` for DOCX rendering.
- `pypdf==6.10.0` for page verification.
- LibreOffice `soffice` for real DOCX-to-PDF layout validation. The builder checks `PATH` and common install locations; use `--soffice` for a custom executable.

No credentials are required by the included scripts. They read and write local files only.

## Inputs

- One primary CSV, TSV, XLSX, or XLSM inventory.
- Customer name, sector, target audience, and account objective.
- Deployment, data, human-approval, GenAI-policy, and entitlement context where known.
- Public strategy sources or permission to research them.

Versioned artifacts:

- `inventory_profile.json` `1.1` for customer-ready builds.
- `evidence_ledger.json` `1.0`.
- `portfolio.json` `1.0`.
- `process_map.json` `1.0`.
- `semantic_review.json` `1.0`.

Profile `1.1` retains a safe basename and source hash, not a local source path. It also records physical worksheet rows, per-sheet header mappings, field coverage, raw statuses, detailed lifecycle states, normalized row dates, and earliest/latest date quality. When valid record dates exist, the ledger as-of date must equal the latest one; assessment and review dates cannot stand in for source freshness.

Profile `1.0` remains compatible with the legacy detailed path. It cannot support the new customer footprint and source-binding gates.

## Prompt

```text
Use $uipath-agentic-expansion-planner on this inventory. Build the internal evidence package, analyst-map end-to-end process groups while labeling customer-confirmation needs, and separate observed evidence from validation tasks for every selected and deferred process. Account for every not-now and unmapped item. For each selected process, define a read-only human-gated pilot with sample selection, source-backed ground-truth ownership, comparable-unit numerator/denominator formulas, measurement owner, rerun rule, data/security approval, product/deployment validation, fallback, customer-set thresholds from baselines and tolerances, and absolute target kickoff and decision dates. Independently review the top opportunities and produce a verified one-to-two-page workshop-ready customer DOCX with up to three actionable recommendations. State the material deferrals and that the workshop ask is not deployment or investment approval. Do not add filler or expose internal IDs and scoring mechanics.
```

## Runnable Example

The following is the complete customer-ready command sequence after the analyst has created the versioned ledger, portfolio, process map, and semantic review described below.

## Standard Workflow

Profile the inventory:

```bash
python3 uipath-agentic-expansion-planner/scripts/inventory_profiler.py \
  --input work/planner/inventory.xlsx \
  --outdir work/planner/profile
```

Score and validate the internal portfolio:

```bash
python3 uipath-agentic-expansion-planner/scripts/score_portfolio.py \
  --evidence-ledger work/planner/evidence_ledger.json \
  --portfolio work/planner/portfolio_draft.json \
  --output work/planner/portfolio.json

python3 uipath-agentic-expansion-planner/scripts/validate_portfolio.py \
  --evidence-ledger work/planner/evidence_ledger.json \
  --portfolio work/planner/portfolio.json \
  --inventory-profile work/planner/profile/inventory_profile.json
```

Validate the analyst-mapped process map and independent review:

```bash
python3 uipath-agentic-expansion-planner/scripts/validate_process_map.py \
  --inventory-profile work/planner/profile/inventory_profile.json \
  --portfolio work/planner/portfolio.json \
  --process-map work/planner/process_map.json

python3 uipath-agentic-expansion-planner/scripts/validate_semantic_review.py \
  --inventory-profile work/planner/profile/inventory_profile.json \
  --evidence-ledger work/planner/evidence_ledger.json \
  --portfolio work/planner/portfolio.json \
  --process-map work/planner/process_map.json \
  --semantic-review work/planner/semantic_review.json \
  --required-readiness workshop_ready
```

Build the final package:

```bash
mkdir -p outputs

python3 uipath-agentic-expansion-planner/scripts/build_customer_assessment.py \
  --inventory-profile work/planner/profile/inventory_profile.json \
  --evidence-ledger work/planner/evidence_ledger.json \
  --portfolio work/planner/portfolio.json \
  --process-map work/planner/process_map.json \
  --semantic-review work/planner/semantic_review.json \
  --supporting-source work/planner/strategy-context.md \
  --output outputs/customer-automation-portfolio-assessment.docx
```

The build writes the DOCX, customer Markdown source, exact PDF used for page verification, and validation receipt. Repeat `--supporting-source` for local strategy or account-context files that should be recorded by safe basename and SHA-256. The receipt records the raw inventory hash, latest valid source record date, ledger and portfolio dates, review and build dates, ledger source metadata, and recommendation-to-evidence map. The profile, ledger, portfolio, process map, and semantic review remain the internal package.

## Customer Output Contract

The DOCX contains exactly:

1. Source File Summary.
2. Current Automation Footprint.
3. Top 3 Recommendations.

It contains one to three recommendations, no more than 900 words, and no more than two rendered pages. A compact comparison table states the common ranking basis and explains the order before the recommendation detail; the planner does not create filler. It states a bounded workshop ask, that owners set final thresholds from customer baselines and control tolerances, that no deployment or investment is approved, and which material process groups remain deferred. The source summary distinguishes CSV tables from workbook sheets, reports the latest valid source record date when available, identifies missing source currency and operating baselines, and reports partial field coverage instead of claiming structural completeness. The footprint shows exact lifecycle counts, named analyst-mapped process groups with automation counts and a customer-confirmation label, department and system concentrations, and the unmapped count. Detailed selection evidence, scores, and validation tasks remain in the internal package.

The recommendation preamble assigns concise account-team artifacts and timing: the CSM delivers the
agenda and access by each target, the TAM delivers a product/tenant control note before each charter,
and the AE delivers a sponsor/funding decision after evidence. Failed prerequisites defer.
Shared pilot mechanics keep product roles precise: data joins the frozen exports, Maestro sequences
handoffs, Robots prepare deterministic outputs, humans review, unmatched records pause and rerun,
and the final record system remains a validation item.

Every recommendation uses scan-oriented labeled bullets for the business function plus explicit Start, End, and Outcome boundaries; why it matters; automation count and named foundation with raw lifecycle status; a numeric historical input and selection method matching the proceed gate; reviewer-owned ground truth plus its accountable owner; join or linkage method; observable output; comparable-unit numerator/denominator formulas, review cadence, and measurement owner; qualified capability roles and plain validation needs; no-write control; a measurable proposed stop/proceed/adjust gate with mandatory rerun; one customer decision owner; one UiPath account-team owner; data/security and product/deployment responsibilities; prerequisite fallback; one deliverable; and absolute target kickoff and decision dates. When annual volume and handling minutes are available for every foundation record, the document may show those fields as separate, unvalidated workload signals. It never combines unlike or unlinked units and never presents a signal as savings, demonstrated pilot throughput, or realized value.

Future stages are labeled design assumptions. The shadow-pilot phase contains no system-changing action. Any later write is a separately authorized `future_state` step after human review and records only a human-confirmed or human-approved result. The customer document labels numeric stop/proceed/adjust thresholds as proposed workshop criteria; the named owner must confirm the baseline, measurement protocol, error cost, and final thresholds before launch. Unresolved product availability, connection, deployment, or value items stay explicit.

Only customer-confirmed or authoritative strategy evidence may be labeled confirmed. Non-official account context remains a planning priority to confirm. A proposed checklist, historical label set, approval-history field, or threshold belongs in `validation_needed`, never `observed_evidence`.

A dated, hash-bound customer-confirmed account source may resolve a specific operational omission in
the inventory, such as a join field, outcome owner, or available historical sample. The document
must still disclose the inventory omission and the analyst must sample-check the linkage. This
narrow confirmation cannot be used to imply deployment fit, entitlement, baseline, value, funding,
or pilot approval.

## Readiness

- `exploratory`: draft, unconfirmed process map, fallback review, failed critical claim, or missing layout proof.
- `workshop_ready`: analyst-confirmed map plus fresh human or independent review with all critical claims passed.
- `pilot_authorizable`: all claims passed, assumptions validated, deployment compatible, capabilities supported, and pilot controls complete.

A single-agent fallback cannot claim workshop readiness. Reviews expire after 30 days and cannot predate a bound artifact.

For `agentic_need`, a passing review means the evidence supports the selected
`applies` or `not_needed` role. It never means the workflow must contain an
agent. Deterministic rules, robots, Maestro, or human review are preferable when
the source does not establish ambiguity or discretionary reasoning.

## Failure Recovery

- Profile `1.0`: regenerate with the current profiler for customer-ready output.
- Source-date mismatch: use the latest valid record date from `source_date_summary`; never substitute the run, assessment, or review date.
- Process coverage failure: assign every inventory ID once or add an explicit unmapped reason.
- Duplicate process assignment: correct the process map; do not rely on names as keys.
- Linkage failure: do not infer shared cases from common systems; record `validation_required` and the exact pre-launch identifier, sequence, and ownership check.
- Prioritization failure: cover every process once, rank selected and deferred processes consecutively, make selected ranks match portfolio order, and explain why each selected process outranks alternatives.
- Evidence-label failure: keep source-supported facts in `observed_evidence`; move proposed labels, baselines, samples, and confirmation tasks to `validation_needed`.
- Deferred-priority failure: state why the process ranks lower and what evidence or event triggers reconsideration.
- Pilot-gate failure: use `Stop if ... . Go if ... . Revise if ... .`; define a quantitative go range, an intermediate revise range, the remaining quantitative stop range, and the bounded next decision without authorizing writes.
- Measurement-plan failure: define numeric selection, reviewer-owned ground truth and its accountable owner, at least two comparable-unit numerator/denominator formulas, cadence, matching measurement owner, and correction plus rerun before proceeding.
- System-write failure: move the write after human review and describe it as recording only a human-confirmed or human-approved result; otherwise keep the pilot read-only.
- Stage-phase failure: order stages from `current_state` to `pilot` to `future_state`; never place a write in the shadow-pilot phase.
- Source-lineage gap: pass local context files with `--supporting-source`; never expose their absolute paths.
- Hash mismatch: rerun semantic review against the exact current artifacts.
- Stale review: repeat independent or human review.
- Readiness failure: fix the failed claim or issue an exploratory draft.
- Plain-language failure: remove internal IDs, score narration, hype, long sentences, or technical contract language.
- Missing `soffice`: supply its path or use `--draft-without-page-check`; the latter is not customer-ready.
- Output collision: choose distinct DOCX, Markdown, PDF, receipt, and input paths; `--force` never permits replacing an input artifact.
- More than two pages: shorten process and recommendation language. Do not raise the page limit.

## Safety

- Never claim customer-ready readiness without a fresh independent or human review and an actual page-count check.
- Never force Maestro, agents, or GenAI into a process where they are not needed.
- Never invent a third recommendation when only one or two have defensible evidence.
- Never omit a stated strategy priority or material workload signal without an explicit selection or deferral rationale.
- Never present proposed stages, case linkage, or workshop thresholds as observed or approved current-state facts.
- Never perform live external writes during analysis or validation.

## Data Classification And Retention

- Treat inventory rows, owners, metrics, process maps, reviews, and outputs as customer-confidential unless classified otherwise.
- Do not commit customer artifacts, private URLs, credentials, or internal brand files.
- Do not submit restricted data to an unapproved model endpoint.
- Never claim entitlement, deployment compatibility, or value without evidence.
- Do not perform live UiPath, SharePoint, Salesforce, Outlook, or other external writes during analysis or validation.
- Retain working artifacts only for the approved account-planning period, then delete temporary renders and superseded drafts.

## Known Limitations

- One primary inventory file is supported per run; workbook sheets may be combined.
- Process grouping still requires analyst confirmation.
- Semantic review records judgment and provenance; it does not replace customer validation.
- The scripts do not inspect a live UiPath tenant or confirm licensing.
- Source relevance and current process feasibility remain human/account-team responsibilities.

## Certification Status

Status: **Maintainer-verified offline workflow**. Synthetic tests cover profile `1.1`, lifecycle handling, source hashes and record-date freshness, process coverage, sample-to-gate alignment, ground truth, metric formulas, linkage mechanics, observable outputs, review cadence and ownership, mixed-result reruns, semantic-review freshness and tampering, fallback honesty, deterministic concise rendering, UiPath brand tokens, and actual one-to-two-page LibreOffice output.

This is not UiPath product certification, licensing confirmation, security accreditation, or customer deployment approval.

## Last Verified

Last verified: **2026-07-21**.

## Validation

```bash
python3 -m unittest discover -s uipath-agentic-expansion-planner/tests -p 'test_*.py'
python3 tools/validate_repo.py
make validate
make secrets
git diff --check
```
