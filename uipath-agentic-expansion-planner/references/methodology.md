# Methodology

Use this methodology to execute the UiPath agentic expansion planning workflow from a customer use-case inventory.

## Core principle

Do not brainstorm generic AI use cases. Use the customer's inventory as operational evidence and public strategy as executive relevance evidence. Recommend opportunities only where the overlap is plausible, specific, and defensible.

## Workflow

1. Intake and quality gate.
2. Inventory profiling.
3. Normalization and exclusions.
4. Public strategy ledger.
5. Strategy-to-inventory crosswalk.
6. Candidate generation.
7. Agentic suitability test.
8. Scoring and prioritization.
9. Conservative value sizing.
10. UiPath capability and deployment validation.
11. Executive packaging, Markdown quality validation, required DOCX rendering, and deterministic structural/brand verification.

## 1. Intake and quality gate

Confirm the user has supplied the minimum viable inputs:

- Customer name.
- Detailed inventory file or pasted table.
- Target audience, depth, or account objective. The final output format is always `.docx`; any other requested format is supplemental unless the user explicitly prohibits file output.

Use `references/input_contract.md` to identify missing full-quality inputs. Ask only for inputs that materially affect quality. If the user asks for best effort, proceed with caveats.

## 2. Inventory profiling

Run `scripts/inventory_profiler.py` for uploaded `.xlsx`, `.xlsm`, `.csv`, or `.tsv` inventories.

Read both generated outputs:

- `inventory_profile.md` for analyst-readable current-state summary.
- `inventory_profile.json` for structured details, detected columns, and top metric rows.

Use the script output to understand:

- Row count and sheet structure.
- Detected columns and missing fields.
- Status distribution.
- Department/owner density.
- Systems/applications density.
- Numeric value and volume fields.
- Frequent process terms.
- Duplicate or suspicious rows.

If the script fails because the file structure is unusual, inspect the file manually and summarize the limitation.

## 3. Normalize and exclude weak rows

Classify rows using status and context.

Default treatment:

- Production/live/deployed/completed: strongest operational signal.
- Pipeline/in-progress/pilot/approved: useful but not validated at scale.
- Ideas/candidates/intake: weak signal unless repeated or strategy-backed.
- Retired/decommissioned/cancelled/rejected/duplicate/archived: exclude from primary value calculations unless the user asks for historical analysis.
- Unknown status: include for pattern analysis, but do not treat as production.

Do not erase ambiguity. Preserve caveats when fields are missing or status is unclear.

## 4. Build public strategy ledger

Research the customer using current web sources unless the user explicitly says not to browse. Prioritize official and recent sources:

1. Strategic plans, annual reports, budgets, regulatory filings, agency plans.
2. Official transformation pages, dashboards, press releases, performance reports.
3. Reputable news, analyst commentary, procurement notices, and secondary sources.
4. Generic industry trends only as weak supporting evidence.

The ledger must include:

- Public priority.
- Source name and date.
- Evidence summary.
- Why it matters operationally.
- Potential automation relevance.

Use citations for all public facts.

## 5. Crosswalk strategy against inventory

Map public priorities to inventory clusters.

Strong crosswalk signal:

- Public strategy names a priority and the inventory has multiple related production or pipeline rows.
- The process family appears across departments or systems.
- Rows show volume, time, value, backlog, quality, compliance, or customer experience pressure.
- The work has unstructured data, exceptions, decision support, or knowledge retrieval needs.

Weak crosswalk signal:

- Public strategy is generic and inventory has no related rows.
- Inventory has only one vague idea with no owner, status, or value field.
- The use case is deterministic data movement with little ambiguity.

## 6. Generate candidate opportunities

For each candidate, define:

- Use-case name.
- Current-state evidence from inventory.
- Public strategy alignment.
- Customer "why now" and the decision ask.
- Business problem.
- Agentic enhancement beyond baseline RPA.
- Affected users or process owners.
- Systems likely involved.
- UiPath capability fit.
- Value levers.
- Feasibility and governance considerations.
- Pilot boundary.
- Validation questions.

Reject candidates that cannot be made specific.

## 7. Agentic suitability test

A use case is agentic-suitable when several of these are true:

- Inputs are unstructured or semi-structured.
- The process requires judgment, interpretation, or decision support.
- Exceptions are frequent or expensive.
- Users need summaries, recommendations, or next-best actions.
- The workflow spans multiple systems or knowledge sources.
- Human review can be inserted for high-risk steps.
- There is meaningful volume or business impact.
- A bounded pilot can be defined.

A use case is weak for agentic expansion when it is:

- Fully deterministic.
- Low volume.
- Already solved by stable RPA or API integration.
- Too risky to automate without controls.
- Unsupported by inventory evidence.
- Unsupported by strategy evidence.

## 8. Score and prioritize

Use `references/scoring_model.md`. Produce two rankings by default:

- Top 5 high-impact recommendations.
- Top 3 low-friction POC candidates.

High-impact candidates optimize for strategic value, scale, and enterprise relevance. POC candidates optimize for bounded scope, feasibility, governance safety, and fast validation.

## 9. Value sizing

Use conservative planning logic.

Rules:

- Prefer inventory-provided volume, handling time, hours, FTE, or benefit values.
- If weekly volume exists and annual volume does not, annualize as weekly volume times 50 and label it estimated.
- If monthly volume exists and annual volume does not, annualize as monthly volume times 12 and label it estimated.
- If no labor rate is supplied, do not invent a precise savings figure unless the user explicitly approves a placeholder.
- Present value as a planning range, not guaranteed savings.
- If assumptions are weak, use qualitative sizing: low, medium, high.

Value levers can include:

- Labor capacity.
- Cycle-time reduction.
- Backlog reduction.
- Quality improvement.
- Compliance and audit readiness.
- Customer, citizen, patient, or employee experience.
- Revenue protection.
- Risk reduction.
- Reuse across process families.

## 10. Capability and deployment validation

Map recommendations to UiPath capabilities as likely fit, not entitlement.

Possible capability patterns:

- Agentic orchestration for multi-step reasoning and tool use.
- Robots for deterministic actions and system execution.
- Integration Service for API-based actions.
- Document Understanding for document extraction and classification.
- Communications Mining for email/message classification and routing.
- Action Center for human-in-the-loop approvals.
- Apps for front-end experiences.
- Process Mining or Task Mining for discovery and validation.
- Insights for operational tracking.
- Test Suite for resilient change management.

Validate deployment context:

- Cloud/on-prem/hybrid/FedRAMP/public sector cloud.
- PII/PHI/PCI/CJIS/GDPR/data residency.
- Human approval controls.
- Audit logs and explainability.
- System access and integration constraints.
- Model governance and prompt/data controls.

## 11. Executive packaging

Use `references/output_templates.md` and `references/brand_and_brief_quality.md`. Keep executive outputs concise, defensible, and aligned to UiPath voice: direct, human, practical, and customer-need-first.

Every final output should include:

- Executive summary.
- Inventory footprint summary.
- Strategy alignment summary.
- Prioritized recommendations.
- Top 5 high-impact opportunities.
- Top 3 low-friction POCs.
- Value assumptions.
- Risks and validation questions.
- Source and assumption notes.
- A rendered and structurally verified `.docx` Word executive brief in `outputs/` when that directory exists.

Do not include raw chain-of-thought or excessive research narrative. Show evidence, assumptions, and decisions. Markdown, chat summaries, slide outlines, spreadsheets, and other formats can support the work, but they are not the final deliverable. If the analysis draft is long, create a separate concise Word-source Markdown before rendering instead of dumping raw research into the `.docx`.

Before rendering, validate that the brief:

- Leads with why the customer should care now.
- States the decision ask, workshop ask, or pilot next step.
- Connects inventory evidence to public strategy evidence.
- Uses specific process names, owners, value levers, and validation questions.
- Avoids hype, generic agentic brainstorming, unofficial brand assets, and product-first language.

### Word executive brief rendering

For every run:

1. Create a concise Markdown brief using `references/output_templates.md`.
2. Shape the Word version as the default AZ DES-style executive portfolio brief. If the analysis draft is long, shorten supporting prose before rendering rather than dropping required sections.
3. Load `references/brand_and_brief_quality.md` and `references/executive_docx.md`, then follow the document-shape, tone, table, and brand-safe styling rules.
4. Run `scripts/validate_executive_brief.py <brief.md>` before rendering. Fix the Markdown if it fails.
5. Render with `scripts/render_executive_docx.py` in portrait orientation unless the user explicitly requests landscape.
6. Verify the output with `scripts/verify_executive_docx.py <brief.docx> --require-output-dir --require-brand-style`. Fix the Markdown or rerender if verification fails.
7. Visually inspect with the Documents skill renderer or another local preview path when available.
8. Link the final `.docx` in the chat response and summarize verification. Do not stop at Markdown or chat text unless `.docx` creation is impossible or the user explicitly prohibits file output.

The target format is a polished executive Word brief, not a transcript of the analysis. If the user needs the full research ledger, provide it as a separate Markdown, CSV, or appendix artifact rather than bloating the Word brief.
