# Automation portfolio assessment: Northstar Shared Services Cooperative - Synthetic

## Source File Summary

- **Inventory reviewed:** inventory.csv; 12 records; table: inventory.
- **Information available:** names, descriptions, lifecycle, functions, owners, systems, workload, priorities, dates.
- **Strategy context reviewed:** 2 customer-confirmed synthetic records.
- **Limitations:** Latest record: 2026-07-02; owner 67% populated, systems 92% populated; Unconfirmed: product, deployment, baselines, and value.

## Current Automation Footprint

| Portfolio view | What the inventory shows |
| --- | --- |
| Total reviewed | 12 |
| Lifecycle mix | Deployed: 4; Pipeline: 3; Paused: 1; Retired: 1; Cancelled: 1; Rejected: 0; Duplicate: 1; Idea: 1; Unknown: 0 |
| Process/domain groups | 5 analyst-mapped groups; customer confirmation required: Employee lifecycle requests (2); Quarterly privileged access assurance (2); Supplier invoice exception resolution (2); Vendor onboarding evidence readiness (2); Vendor master creation (1) |
| Department concentration | Finance, Human Resources, and IT/CIO Assurance (2 each); 5 others. |
| System concentration | Document Repository (4); ERP Finance (3); 4 systems tied at 2 each. |
| Unmapped | 3 records |
| Assessment boundary | Workload is not savings. Duplicate excluded. Read-only proposals authorize no writes or decisions. |

## Top 3 Recommendations

Order basis: strategy fit, foundation, evidence, delivery risk. Workshop ask: validate prerequisites and historical pilots; owners set proposed thresholds from baselines and tolerances. No deployment or investment approval.
Account team: CSM delivers agenda/access by each target; TAM delivers product/tenant control note before each charter; AE delivers sponsor/funding decision after evidence; failed prerequisites defer.
Pilot mechanics: data joins frozen exports; Maestro sequences handoffs; Robots prepare outputs; humans review. Unmatched records pause and rerun; final record systems require validation.

| Rank | Process | Why this order |
| --- | --- | --- |
| 1 | Quarterly privileged access assurance | Strongest evidence: confirmed linkage, ownership, foundation, CIO priority. |
| 2 | Supplier invoice exception resolution | Confirmed invoice linkage, ownership, foundation; access governance is stronger. |
| 3 | Vendor onboarding evidence readiness | Confirmed supplier linkage, ownership, foundation; sensitive data adds risk. |

Deferred pending owners, boundaries, or restart: Employee lifecycle requests and Vendor master creation.

### 1. Quarterly privileged access assurance

- **End-to-end process:** Function: IT assurance. Start: quarterly access campaign opens. End: Access Governance Manager records the certification decision. Outcome: traceable evidence closes certification; access changes excluded.

- **Why it matters:** CIO prioritizes access evidence; records list 26,400 lines and 1,200 exceptions.

- **Existing automation foundation:** 2 automations: Quarterly access evidence pull (Deployed), Privileged access exception narrative (UAT).

- **Pilot path:** Proposed. Input: 120 completed exceptions across campaigns and types. Ground truth: Approved disposition and checklist per exception. Ground-truth owner: Access Governance Manager. Correlation: campaign and entitlement IDs. Robot output: evidence-gap bundles. Access Governance Manager reports weekly: coverage = cases with complete evidence / cases; agreement = cases matching final disposition / cases.

- **Roles and controls:** Maestro/Robots proposed; no Agents/GenAI; human decides. Product, deployment, value unconfirmed. Pilot: no writes.

- **Decision gate:** Stop when coverage under 85%, agreement under 80%, or any access breach. Proceed when 120 cases at 98% coverage and 95% agreement. Adjust when coverage 85-97% or agreement 80-94%. Rerun before proceeding. Decision owner: Access Governance Manager. Pilot continuation only.

- **Next action:** Target: 2026-08-04. Customer: Access Governance Manager; UiPath: CSM. Prerequisite: Identity and Security approve export and baseline; otherwise defer. Output: draft pilot charter. Decision: 2026-08-25.

### 2. Supplier invoice exception resolution

- **End-to-end process:** Function: Finance operations. Start: invoice enters the Finance mailbox. End: Finance records disposition and payment-review handoff. Outcome: complete evidence supports review; posting and payment excluded.

- **Why it matters:** Finance prioritizes throughput; 18,000 submissions and 4,200 exceptions show demand.

- **Existing automation foundation:** 2 automations: Supplier invoice mailbox intake (Live - unattended), PO match exception worklist (Pilot / UAT).

- **Pilot path:** Proposed. Input: 100 completed exceptions by documented type. Ground truth: Approved disposition per invoice. Ground-truth owner: Finance Operations Lead. Correlation: invoice ID. Robot output: invoice and PO evidence gaps. Finance Operations Lead reports weekly: agreement = cases matching final disposition / cases; linkage = invoice-linked cases / cases.

- **Roles and controls:** Maestro/Robots proposed; no Agents/GenAI; human decides. Product, deployment, value unconfirmed. Pilot: no writes.

- **Decision gate:** Stop when agreement under 80%, linkage under 90%, or any control breach. Proceed when 100 cases at 95% agreement and 98% linkage. Adjust when agreement 80-94% or linkage 90-97%. Rerun before proceeding. Decision owner: Finance Operations Lead. Pilot continuation only.

- **Next action:** Target: 2026-08-04. Customer: Finance Operations Lead; UiPath: CSM. Prerequisite: Finance data owner approves export and baseline; otherwise defer. Output: draft pilot charter. Decision: 2026-08-25.

### 3. Vendor onboarding evidence readiness

- **End-to-end process:** Function: Procurement operations. Start: supplier request enters portal. End: Supplier Risk Lead records the review outcome. Outcome: traceable risk decision supports onboarding; vendor-master creation excluded.

- **Why it matters:** Supplier prioritizes onboarding; linked outcomes support testing after data approval.

- **Existing automation foundation:** 2 automations: Vendor onboarding request intake (Production), Vendor risk evidence review (Approved backlog).

- **Pilot path:** Proposed. Input: 80 completed redacted files by unit and class. Ground truth: Approved checklist and outcome per file. Ground-truth owner: Supplier Risk Lead. Correlation: supplier request ID. Robot output: checklist and document gaps. Supplier Risk Lead reports weekly: precision = correct flags / all flags; recall = missing documents flagged / known missing documents.

- **Roles and controls:** Maestro/Robots proposed; no Agents/GenAI; human decides. Product, deployment, value unconfirmed. Pilot: no writes.

- **Decision gate:** Stop when precision under 75%, recall under 80%, or any data breach. Proceed when 80 files at 92% precision and 95% recall. Adjust when precision 75-91% or recall 80-94%. Rerun before proceeding. Decision owner: Supplier Risk Lead. Pilot continuation only.

- **Next action:** Target: 2026-08-11. Customer: Supplier Risk Lead; UiPath: solution consultant. Prerequisite: Supplier Risk Lead approves redacted export and baseline; otherwise defer. Output: draft pilot charter. Decision: 2026-09-08.
