# Production Readiness Evaluation

This evaluation separates repository package quality from confidence that a skill produces its intended functional outcome and from evidence that its real operating path has been certified. A strong package is not the same thing as a certified live integration.

Last verified: 2026-07-27

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
| 1 | `uipath-agentic-expansion-planner` | 9.5 | 9.2 | Offline workflow validated | Versioned `1.1` inventory profile plus evidence, portfolio, process-map, and semantic-review contracts; deterministic concise rendering; lifecycle and sparse/noisy/on-prem goldens; branded two-page DOCX checks; and a fresh 12-row multi-domain run producing an 899-word assessment that scored 4/5/5/4 for clarity, process specificity, decision utility, and account-team actionability. | Tenant capability and entitlement, deployment compatibility, data access, baselines, value, funding, and pilot approval still require customer and account-team validation. |
| 2 | `llm-council` | 9.4 | 9.1 | Offline workflow validated | Published strict schema, question hashes, run/model and disjoint agent-ID evidence, seeded anonymization, atomic `0600` artifacts, 13 tests, and a true five-advisor/five-reviewer run plus separately labeled fallback scoring 5/5/5/4. | Future decisions still depend on framing, source data, and subagent availability; concrete child model IDs and production telemetry were not exposed or certified. |
| 3 | `usecasehandoff` | 9.3 | 9.1 | Offline workflow validated | A fresh ready package produced exactly nine files and eight content hashes. Missing or changed local sources failed closed, restored evidence passed, and nine tests cover readiness, source integrity, owned risks, acceptance tests, first-sprint work, and the no-send boundary. | Remote HTTPS evidence cannot be byte-pinned when its declared hash is `N/A`; connector routing and destination permissions remain uncertified. |
| 4 | `account-meeting-availability` | 9.3 | 9.0 | Offline workflow validated | A fresh 215-candidate run was byte-deterministic, emitted no emails, preserved full exclusion counts under bounded diagnostics, and used private modes. Twenty-five tests now include privacy-safe optional-attendee reasons and explicit Python runtime guidance. | Real Outlook free/busy freshness and completeness have not been connector-certified. |
| 5 | `gtm-org-proposal-generator` | 9.3 | 9.0 | Offline workflow validated | A fresh eight-source, three-capability, three-card corpus rendered byte-identically. Twelve tests enforce source alignment, pilot ownership, card math, recomputed overlap-adjusted portfolio ranges, exit criteria, and executive actions. | Citation linkage cannot prove semantic support, and loaded labor rates, implementation cost, and realized benefits still need human validation. |
| 6 | `enrich-day2-dashboard` | 9.3 | 8.9 | Not operationally certified | Self-contained exact-safe Salesforce layer with a final accepted-value/field-map freshness receipt; policy-v2 evidence ledger and preview; stable three-question clarification; bounded attestations; exact proposal approval; and 129 synthetic tests. An optional external-app harness checks schema import and expected blank-template blocker semantics, but it is not part of repository CI. | No real Salesforce org or connector collection was exercised; the optional harness does not certify an app version, browser PDF export, or rendering; account evidence quality, connector coverage, permissions, and leadership usefulness remain run-specific. |
| 7 | `estimate-du-units` | 9.2 | 8.8 | Offline workflow validated | Versioned rate/input/output schemas, explicit verified rates, stale-rate controls, exact and rounded multi-document totals, additive-rate fixtures, and JSON/Markdown outputs. | Source authenticity and commercial applicability still require a current official pricing review. |
| 8 | `salesforce-meddpicc-update` | 9.3 | 8.7 | Not operationally certified | Freshness-bound transactions, deterministic operation IDs, tamper checks, mandatory receipt modes, privacy-safe audit output, recovery fixtures, and no blind PATCH retry. | The opt-in Salesforce sandbox certification has not run; no live-write certification is claimed. |
| 9 | `uipcodedappdeploy` | 9.2 | 8.6 | Not operationally certified | TOML-aware atomic versioning, immutable hashed plans, mandatory folder GUID, allowlisted stages, resumable redacted receipts, URL verification, and 33 offline tests. | The opt-in UiPath nonproduction deployment certification has not run; rollback is not implemented. |
| 10 | `repo-hardening-sprint` | 9.1 | 8.6 | Offline workflow validated | Auto-discovered tests, real YAML parsing, local anchors, path and secret scans, base-aware whitespace checks, scheduled link checks, pinned CI/dependencies, and public governance. | Results remain limited by each target repository's own contracts and tests; GitHub Actions evidence is recorded per PR. |
| 11 | `pubsec-big-rocks-row-research` | 9.0 | 8.6 | Offline workflow validated | Versioned source manifest, dynamic headers, exact account resolution, stale-lead separation, evidence-bound previews, and verified local-copy tests for formulas, dropdowns, values, and red font. | Generated fixtures do not certify every feature in a production workbook or current connector evidence. |
| 12 | `salesforce-account-profile` | 9.0 | 8.5 | Not operationally certified | Conversational v2 defaults with five public commands and v1 compatibility; private 30-minute resume; pinned CLI and redacted org discovery; runtime metadata inspection; plan-bound org/family approval; deterministic presets, filters, recovery, relationship hydration, currency-separated presentation, and 255 targeted tests. The repository gate passed 12 skills and 418 Node tests plus all Python, Beads, syntax, and diff checks. | No approved sandbox/UAT alias or synthetic live-org fixture was supplied, so real permissions/FLS, org-specific custom-field semantics, operator recovery, and cleanup remain uncertified. Production remains separately approval-gated; annualization remains disabled and uncertified. |

## Fresh Forward Tests

These scores come from independent synthetic runs without expected output files. They measure the observed workflow, not live-system certification.

| Skill | Blunt outcome scores (1-5) | Residual finding |
| --- | --- | --- |
| `uipath-agentic-expansion-planner` | Clarity 4; process specificity 5; decision utility 5; account-team actionability 4 | The independent answer-blind reviewer found the two-page assessment workshop-usable with no structural blocker. Page-two density and recommendation-level mapping of TAM/AE timing remain bounded polish opportunities; deployment, entitlement, data-access, baseline, value, and approval items remain validation tasks. |
| `usecasehandoff` | Evidence 4.5; specificity 5; delivery completeness 4.5; risk ownership 5; first-sprint actionability 5 | Local evidence is hash-bound; remote HTTPS evidence may be declared `N/A`. |
| `account-meeting-availability` | Specificity 5; scheduling utility 4; determinism 5; privacy 5; actionability 4 | The forward test's optional-reason and truncation-test gaps now have deterministic coverage; real Outlook evidence remains uncertified. |
| `gtm-org-proposal-generator` | Specificity 5; evidence coverage 4; value math 5; decision utility 4; actionability 5 | The output is pilot-authorizable, not yet an investment-grade business case. |
| `llm-council` | Decision utility 5; independence 5; auditability 5; operational actionability 4 | Anonymous reviewers caught automation bias, statistical power, selection bias, and pilot economics; model IDs were not exposed by the orchestration tool. |
| `salesforce-account-profile` | Contract safety 5; deterministic resolution 5; data minimization 4; rendering utility 4; operational confidence 3 | Synthetic conversational journeys passed for one-confirmation pipeline, ambiguity, literal-prefix choice, exact family approval, cap narrowing, context-loss resume, TTL/abort cleanup, token and Markdown attacks, metadata drift, multiple currencies, and disabled annualization. A fresh independent adversarial audit found and drove fixes for classification, approval, recovery, lock, and usability defects. No live-org evidence exists, so this remains offline validation only. |

## Supplied Draft Baseline

The downloaded requirement draft was evaluated only as a private starting point; it was not
copied into the public package. Its baseline scores are retained in axes compatible with the
current evaluation:

| Artifact | Package baseline | Functional baseline |
| --- | ---: | ---: |
| `salesforce-account-profile` supplied draft | 2.0 | 2.0 |

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
