# Production Readiness Evaluation

This evaluation grades each remaining skill on a 1-10 scale from conceptual brainstorm to production ready. Baseline scores are reconstructed from commit `4dc3f60`, the pre-hardening state used for comparison. They are not the original human score table.

## Rubric

| Score | Meaning |
| ---: | --- |
| 1-2 | Concept only; no reliable instructions, tests, or repeatable workflow. |
| 3-4 | Useful prompt or notes, but weak safety boundaries and little deterministic validation. |
| 5-6 | Usable locally with scripts or references, but incomplete docs, tests, or failure handling. |
| 7 | Strong single-user workflow with meaningful tests, but not yet org-shareable by default. |
| 8 | Org Baseline: valid metadata, docs, safety boundaries, deterministic validation, and no local path leaks. |
| 9 | Production-ready for broad sharing: robust failure handling, offline/no-write test paths, validators, and clear residual risks. |
| 10 | Fully certified live integration with monitored rollout, operational runbooks, and production telemetry. |

## Sorted Readiness Scores

| Rank | Skill | Baseline | Final | Delta | Evidence | Remaining blocker |
| ---: | --- | ---: | ---: | ---: | --- | --- |
| 1 | `salesforce-meddpicc-update` | 8.0 | 9.0 | +1.0 | Mature Node helper and fixture corpus; added metadata cleanup, connector-permission docs, confirmation receipt boundaries, telemetry CLI coverage, structured error CLI tests, and no-write hard stops. | Live Salesforce certification and monitored telemetry sink are still outside this repo. |
| 2 | `account-meeting-availability` | 6.5 | 8.6 | +2.1 | CSV normalization/store tests, temp-store isolation, atomic writes, internal-domain review, distribution-address review, duplicate logical header failure, and CSV formula-output guarding. | Real connector sourcing still depends on operator-authorized Outlook evidence. |
| 3 | `uipath-agentic-expansion-planner` | 6.5 | 8.6 | +2.1 | Inventory profiler tests, golden profile fixture, DOCX render/verify coverage, negative DOCX verification test, current metadata, and DOCX/fallback docs. | Live customer brief quality still depends on source inventory richness and public evidence validation. |
| 4 | `uipcodedappdeploy` | 5.5 | 8.5 | +3.0 | Dry-run default, explicit offline planning, no `--execute` with offline mode, version/folder tests, folder-key validation, and no live deploy tests. | Full live deployment certification requires a tenant-specific smoke run. |
| 5 | `estimate-du-units` | 6.0 | 8.4 | +2.4 | Deterministic calculator, multi-document and zero-DU tests, decimal support, negative volume/rate rejection, and docs requiring official-source verification dates. | Rates still require live official-source verification during customer-facing use. |
| 6 | `pubsec-big-rocks-row-research` | 5.0 | 8.3 | +3.3 | Workbook fixture tests, stale-date bug fix, source-only mode, include-stale discovery test, placeholder detection, missing-source reporting, and explicit do-not-fill guidance. | SharePoint/Slack/OneNote evidence remains connector- and permission-dependent. |
| 7 | `llm-council` | 5.0 | 8.2 | +3.2 | Renderer tests, schema validation, validate-only mode, HTML/Markdown artifact checks, missing-advisor failures, and fallback wording. | True independence requires subagent availability at runtime. |
| 8 | `gtm-org-proposal-generator` | 4.5 | 8.1 | +3.6 | Public-source operating rules plus static validator for required sections, source ledger, citation IDs, estimate tiers, uncited money/percent claims, and overclaim language. | Final proposal quality still depends on current public research and UiPath docs verification. |
| 9 | `usecasehandoff` | 4.5 | 8.1 | +3.6 | Deterministic package scaffolder, required artifact templates, no-send manifest boundary, package validator, overwrite protection, and evidence-ledger/delivery-plan checks. | Delivery routing still requires connector-specific confirmation and destination verification. |
| 10 | `repo-hardening-sprint` | 5.5 | 8.0 | +2.5 | Repo-level validator, CI gate, review-report template, readiness-regression checklist, and explicit evaluation-update guidance. | It remains a meta-skill; final quality depends on each target repo's own available tests. |

## Summary

All remaining skills now meet or exceed the Org Baseline threshold of 8/10. The largest gains came from previously prompt-heavy or weakly-tested skills: `gtm-org-proposal-generator`, `usecasehandoff`, `pubsec-big-rocks-row-research`, and `llm-council`. No skill is graded as fully certified 10/10 because live-system certification, monitored rollout, and production telemetry are intentionally outside this no-live-write hardening pass.
