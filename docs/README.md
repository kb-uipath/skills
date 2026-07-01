# Skills documentation

Each page describes when to use the skill, what inputs to provide, and a starter prompt you can paste into Codex.

See [production-readiness-evaluation.md](./production-readiness-evaluation.md) for the current production-readiness scores and improvement deltas.

## Latest Readiness Snapshot

All 10 remaining skills are at or above the Org Baseline threshold of 8/10. The current top three are:

| Rank | Skill | Score | Latest hardening signal |
| ---: | --- | ---: | --- |
| 1 | salesforce-meddpicc-update | 9.0 | Mature no-write safety, fixture coverage, redacted receipts, and connector permission docs. |
| 2 | uipath-agentic-expansion-planner | 8.9 | On-brand DOCX renderer, Markdown brief quality validator, and brand-style verification. |
| 3 | account-meeting-availability | 8.6 | CSV privacy handling, isolated store tests, and robust contact normalization. |

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
