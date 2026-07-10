# Skills documentation

Each page describes when to use the skill, what inputs to provide, and a starter prompt you can paste into Codex.

See [production-readiness-evaluation.md](./production-readiness-evaluation.md) for separate package-quality, functional-confidence, and operational-certification evidence. Prior single scores are historical only.

Last verified: 2026-07-10

## Documentation Contract

When a public skill contract changes, update the matching doc page in the same change. For foundation hardening work, the public page must state runtime and dependencies, versioned contract, runnable example, recovery path, classification and retention rules, limitations, certification status, validation commands, and a last-verified date.

Do not claim full production certification from local validation alone. Certification claims must match the evidence and blocker notes in [production-readiness-evaluation.md](./production-readiness-evaluation.md).

## Latest Readiness Snapshot

All 10 remaining skills meet the package-quality Org Baseline, but no live-write skill is operationally certified. The highest functional-confidence skills are:

| Rank | Skill | Package | Functional | Certification |
| ---: | --- | ---: | ---: | --- |
| 1 | uipath-agentic-expansion-planner | 9.5 | 9.2 | Offline workflow validated |
| 2 | llm-council | 9.4 | 9.1 | Offline workflow validated |
| 3 | usecasehandoff | 9.3 | 9.1 | Offline workflow validated |

Run `make validate` from the repo root before sharing changes. Use a Python runtime with `python-docx` installed for full DOCX renderer coverage.

| Skill | Category | Docs |
| --- | --- | --- |
| account-meeting-availability | Customer operations | [account-meeting-availability.md](./account-meeting-availability.md) |
| estimate-du-units | Consumption planning | [estimate-du-units.md](./estimate-du-units.md) |
| gtm-org-proposal-generator | GTM and executive proposals | [gtm-org-proposal-generator.md](./gtm-org-proposal-generator.md) |
| llm-council | Decision support | [llm-council.md](./llm-council.md) |
| pubsec-big-rocks-row-research | Public-sector account research | [pubsec-big-rocks-row-research.md](./pubsec-big-rocks-row-research.md) |
| repo-hardening-sprint | Engineering quality | [repo-hardening-sprint.md](./repo-hardening-sprint.md) |
| salesforce-meddpicc-update | Sales operations | [salesforce-meddpicc-update.md](./salesforce-meddpicc-update.md) |
| uipath-agentic-expansion-planner | GTM and executive proposals | [uipath-agentic-expansion-planner.md](./uipath-agentic-expansion-planner.md) |
| uipcodedappdeploy | UiPath deploy | [uipcodedappdeploy.md](./uipcodedappdeploy.md) |
| usecasehandoff | Delivery handoff | [usecasehandoff.md](./usecasehandoff.md) |
