# Production Readiness Evaluation

This evaluation separates repository package quality from confidence that a skill produces its intended functional outcome and from evidence that its real operating path has been certified. A strong package is not the same thing as a certified live integration.

Last verified: 2026-07-10

## Readiness Axes

### Package Quality

Score from 1 to 10 for metadata, versioned contracts, documentation, deterministic tests, failure handling, privacy controls, recovery guidance, and repository governance.

### Functional Outcome Confidence

Score from 1 to 10 for evidence that representative inputs produce specific, useful, and safe outcomes. Fixture tests, golden outputs, and fresh-agent forward tests increase confidence; structural validation alone does not.

### Operational Certification

This is an evidence state, not a numeric score:

| State | Meaning |
| --- | --- |
| Not operationally certified | Offline controls may pass, but a required sandbox, connector, or deployment path has not been exercised. |
| Offline workflow validated | The complete local artifact or calculation path passes deterministic fixtures without external writes. |
| Nonproduction integration certified | An opt-in sandbox or read-only connector run passed with recorded environment and recovery evidence. |
| Production certified | Monitored production rollout, support ownership, runbooks, and telemetry have passed review. |

No skill in this repository is production certified. Salesforce and coded-app deployment are explicitly **not operationally certified** until their opt-in nonproduction workflows run successfully.

## Current Evaluation

The table is sorted by functional outcome confidence, then package quality. Live-write skills cannot outrank equivalent offline workflows merely because their static controls are strong.

| Rank | Skill | Package quality | Functional confidence | Operational certification | Evidence | Blocking condition |
| ---: | --- | ---: | ---: | --- | --- | --- |
| 1 | `uipath-agentic-expansion-planner` | 9.3 | 8.9 | Offline workflow validated | Versioned evidence and portfolio contracts, deterministic scoring/rendering, golden sparse/noisy/on-prem cases, brief cross-checks, branded DOCX verification, and decision-utility rubric. | Real customer outcomes still depend on inventory quality, current public evidence, entitlement checks, and approved assets. |
| 2 | `estimate-du-units` | 9.2 | 8.8 | Offline workflow validated | Versioned rate/input/output schemas, explicit verified rates, stale-rate controls, exact and rounded multi-document totals, additive-rate fixtures, and JSON/Markdown outputs. | Source authenticity and commercial applicability still require a current official pricing review. |
| 3 | `usecasehandoff` | 9.1 | 8.8 | Offline workflow validated | Exact nine-file package, versioned hash manifest, ready/scaffold validation, cited evidence, owned risks, acceptance tests, first-sprint checks, and no-send boundary. | Connector routing and destination permissions remain outside the local package certification. |
| 4 | `account-meeting-availability` | 9.1 | 8.7 | Offline workflow validated | Versioned contact store, atomic locking, private permissions, scoped identity, formula-safe export, free/busy schemas, deterministic slot ranking, and no-send controls. | Freshness and completeness of real Outlook free/busy evidence have not been connector-certified. |
| 5 | `salesforce-meddpicc-update` | 9.3 | 8.7 | Not operationally certified | Freshness-bound transactions, deterministic operation IDs, tamper checks, mandatory receipt modes, privacy-safe audit output, recovery fixtures, and no blind PATCH retry. | The opt-in Salesforce sandbox certification has not run; no live-write certification is claimed. |
| 6 | `uipcodedappdeploy` | 9.2 | 8.6 | Not operationally certified | TOML-aware atomic versioning, immutable hashed plans, mandatory folder GUID, allowlisted stages, resumable redacted receipts, URL verification, and 33 offline tests. | The opt-in UiPath nonproduction deployment certification has not run; rollback is not implemented. |
| 7 | `pubsec-big-rocks-row-research` | 9.0 | 8.6 | Offline workflow validated | Versioned source manifest, dynamic headers, exact account resolution, stale-lead separation, evidence-bound previews, and verified local-copy tests for formulas, dropdowns, values, and red font. | Generated fixtures do not certify every feature in a production workbook or current connector evidence. |
| 8 | `repo-hardening-sprint` | 9.1 | 8.6 | Offline workflow validated | Auto-discovered tests, real YAML parsing, local anchors, path and secret scans, base-aware whitespace checks, scheduled link checks, pinned CI/dependencies, and public governance. | Results remain limited by each target repository's own contracts and tests; GitHub Actions evidence is recorded per PR. |
| 9 | `gtm-org-proposal-generator` | 9.0 | 8.5 | Offline workflow validated | Canonical source/capability/proposal contract, deterministic renderer, source coverage, date/deployment checks, estimate tiers, impact math, overclaim controls, and golden output. | A validator cannot prove that a source semantically supports a claim; current public research still needs human review. |
| 10 | `llm-council` | 9.0 | 8.4 | Offline workflow validated | Strict five-advisor/five-review schema, bijective seeded anonymization, hashes, criteria, disconfirming evidence, confidence, sensitivity, collision protection, and truthful fallback artifacts. | True advisor independence still depends on available subagents and a fresh multi-agent run for the decision at hand. |

## Historical Comparison

These are the prior single-axis scores reconstructed from pre-hardening commit `4dc3f60` and the v1 hardening evaluation. They are retained only to show improvement; they are superseded by the three-axis model above and are not operational-certification claims.

| Skill | Reconstructed baseline | Historical v1 final | Historical delta |
| --- | ---: | ---: | ---: |
| `salesforce-meddpicc-update` | 8.0 | 9.0 | +1.0 |
| `uipath-agentic-expansion-planner` | 6.5 | 8.9 | +2.4 |
| `account-meeting-availability` | 6.5 | 8.6 | +2.1 |
| `uipcodedappdeploy` | 5.5 | 8.5 | +3.0 |
| `estimate-du-units` | 6.0 | 8.4 | +2.4 |
| `repo-hardening-sprint` | 5.5 | 8.4 | +2.9 |
| `pubsec-big-rocks-row-research` | 5.0 | 8.3 | +3.3 |
| `llm-council` | 5.0 | 8.2 | +3.2 |
| `gtm-org-proposal-generator` | 4.5 | 8.1 | +3.6 |
| `usecasehandoff` | 4.5 | 8.1 | +3.6 |

## Certification Rules

- Offline tests never confer Salesforce, UiPath deployment, Outlook, SharePoint, Slack, Teams, or production-system certification.
- A nonproduction certification record must name the environment, tool version, identity scope, synthetic data set, observed result, recovery result, and review date.
- A 10/10 package or functional score is intentionally withheld without monitored production evidence and accountable operational ownership.
- Re-run this evaluation after any public contract change, newly failing fixture, stale capability source, or readiness regression.
