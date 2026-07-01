# kb-uipath skills

This repository contains Codex skills packaged for public GitHub use and broader organizational sharing.

The skills are copied as top-level directories so they can be installed or synced directly into a Codex skills folder. The `docs/` folder contains usage notes, required inputs, and example prompts for each skill.

## What is included

- 10 top-level Codex skills.
- Per-skill `SKILL.md` files plus bundled references, scripts, assets, and templates.
- Skill-specific documentation in `docs/` with inputs, prompts, outputs, safety notes, and validation commands.
- Repo-level validation through `make validate`, `tools/validate_repo.py`, Python unit tests, Node tests, syntax checks, and whitespace checks.
- Hidden backups, `.DS_Store` files, local zip artifacts, and upstream `UiPath/skills` exports are intentionally excluded.

## Latest validated state

As of the latest merged `main`, all 10 remaining skills meet the Org Baseline readiness bar of 8/10 or higher. The top readiness scores are:

| Rank | Skill | Score | Notes |
| ---: | --- | ---: | --- |
| 1 | `salesforce-meddpicc-update` | 9.0 | Mature fixture coverage, write safety, receipt redaction, and connector-permission docs. |
| 2 | `uipath-agentic-expansion-planner` | 8.9 | Adds Markdown brief quality gates and UiPath brand-style DOCX verification. |
| 3 | `account-meeting-availability` | 8.6 | Hardened CSV normalization, privacy handling, and isolated contact-store tests. |

See [docs/production-readiness-evaluation.md](./docs/production-readiness-evaluation.md) for the full sorted table, baseline scores, deltas, evidence, and remaining blockers.

## Install

Clone the repository and copy the skill directories you want into your Codex skills directory.

```bash
git clone https://github.com/kb-uipath/skills.git
cd skills
mkdir -p ~/.codex/skills
cp -R <skill-name> ~/.codex/skills/
```

To sync every skill without copying repo scaffolding into the Codex skills folder:

```bash
mkdir -p ~/.codex/skills
for skill in */SKILL.md; do
  skill_dir="${skill%/SKILL.md}"
  mkdir -p ~/.codex/skills/"$skill_dir"
  rsync -a --delete "$skill_dir"/ ~/.codex/skills/"$skill_dir"/
done
```

Restart Codex after installing or syncing skills so the updated skill metadata is loaded.

## Use

Invoke a skill by name in a Codex prompt, usually with a `$` prefix, then provide the concrete inputs listed in the matching doc page.

Upstream `UiPath/skills` exports are not vendored here.

```text
Use $repo-hardening-sprint on this repository. Identify the highest-impact cleanup, implement safe fixes, run the relevant checks, and summarize remaining risks before commit.
```

## Validate

Run the local gate before committing or sharing changes:

```bash
make validate
```

The gate checks skill metadata, docs coverage, relative Markdown links, local absolute path leaks, Python syntax, Python unit tests, Node syntax/tests, and whitespace errors.

For full DOCX renderer and brand-style test coverage, run `make validate` with a Python interpreter that has `python-docx` installed:

```bash
make validate PYTHON=/path/to/python-with-python-docx
```

## Skill index

### Consumption planning

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [estimate-du-units](./estimate-du-units/SKILL.md) | Estimate annual UiPath Document Understanding AI Unit or Platform Unit consumption from customer automation descriptions, especially messy natural-language descriptions involving scanned documents, forms, OCR, classification, extraction, indexing, manual queues, batches, faxes, PDFs, or document routing. | Estimate annual UiPath Document Understanding AI Unit or Platform Unit consumption from customer automation descriptions, especially messy natural-language descriptions involving scanned documents, forms, OCR, classification, extraction, indexing, manual queues, batches, faxes, PDFs, or document routing. Use when Codex needs to decide whether DU applies, infer documents and page volume, source or annualize workload counts, calculate low/base/high consumption, explain assumptions, or produce a planning estimate for a UiPath customer. | [docs](./docs/estimate-du-units.md) |

### Customer operations

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [account-meeting-availability](./account-meeting-availability/SKILL.md) | Source, validate, store, edit, and review account meeting contacts for both customer contacts and UiPath team members from a CSV or direct user-provided contact details. | Source, validate, store, edit, and review account meeting contacts for both customer contacts and UiPath team members from a CSV or direct user-provided contact details. Use when the user provides or references an account/contact CSV, asks to add or edit customer or UiPath contacts, asks Codex to maintain an account contact book, fill missing email addresses, verify account contacts, prepare meeting attendees, or identify likely emails from Outlook Email/Calendar evidence without sending messages automatically. | [docs](./docs/account-meeting-availability.md) |

### Decision support

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [llm-council](./llm-council/SKILL.md) | Run a structured multi-perspective council for high-stakes decisions using five independent advisor subagents, anonymous peer review, and a chairman verdict with report artifacts. | Run a structured multi-perspective council for high-stakes decisions using five independent advisor subagents, anonymous peer review, and a chairman verdict with report artifacts. Use when the user explicitly invokes $llm-council, says "council this", asks to run a council or multi-agent advisor panel, or wants to stress-test a pivot, pricing, positioning, hiring, launch, strategy, or other expensive-to-get-wrong choice. Do not use for factual lookups, simple content generation, summaries, or tasks with one correct answer. | [docs](./docs/llm-council.md) |

### Delivery handoff

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [usecasehandoff](./usecasehandoff/SKILL.md) | Capture, verify, synthesize, package, and route customer or internal automation use case handoffs. | Capture, verify, synthesize, package, and route customer or internal automation use case handoffs. Use when Codex needs to gather known information from chats, email, Slack, Teams, SharePoint, Drive, local files, or web sources; produce executive framing, cited metrics, business impact, solution workflow, delivery plan, enterprise hardening recommendations, AI/UiPath AI Unit consumption opportunities, risk register, next steps, and downloadable artifacts for a professional services or automation delivery team. | [docs](./docs/usecasehandoff.md) |

### Engineering quality

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [repo-hardening-sprint](./repo-hardening-sprint/SKILL.md) | Run safe, repository-agnostic cleanup and production-hardening sprints. | Run safe, repository-agnostic cleanup and production-hardening sprints. Use when Codex is asked to review, clean up, refactor, harden, reorganize docs, improve tests, add smoke checks, prepare a repo for commit, or verify that a change can be safely pushed to main without breaking public behavior. | [docs](./docs/repo-hardening-sprint.md) |

### GTM and executive proposals

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [gtm-org-proposal-generator](./gtm-org-proposal-generator/SKILL.md) | Build executive-level UiPath automation proposal cards from public organizational research. | Build executive-level UiPath automation proposal cards from public organizational research. Use when Codex is asked to research an organization, agency, department, public company, healthcare system, university, or other institution; analyze budgets, strategic goals, administrative burden, or cost drivers; identify automation use cases; and produce cited GTM, sales, C-suite, public sector, or federal proposal content aligned to a specified industry vertical and UiPath deployment type. | [docs](./docs/gtm-org-proposal-generator.md) |
| [uipath-agentic-expansion-planner](./uipath-agentic-expansion-planner/SKILL.md) | Produces evidence-backed UiPath Act 2 expansion plans, agentic automation portfolios, top recommendations, POC candidates, and an on-brand verified executive DOCX brief from customer inventories. | Use when the user provides or references a customer inventory spreadsheet, asks for agentic expansion ideas, asks to prioritize UiPath opportunities, or needs a customer-ready proposal grounded in inventory data, public strategy evidence, deployment-aware validation, UiPath brand-aware writing, and Word-ready packaging. | [docs](./docs/uipath-agentic-expansion-planner.md) |

### Public-sector account research

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [pubsec-big-rocks-row-research](./pubsec-big-rocks-row-research/SKILL.md) | Research and synthesize evidence for one account row in the PubSec CS Portfolio Big Rocks spreadsheet. | Research and synthesize evidence for one account row in the PubSec CS Portfolio Big Rocks spreadsheet. Use when Codex is asked to fill, review, validate, or provide organized content for a single account/row/record in the PUBSEC Big Rocks workbook, especially columns for utilization, cloud status, AI Units, Agent Units, Test/IXP/Agentic status, FY27 Big Rocks, value tracking, churn/risk, and notes using SharePoint, Slack, OneNote, migration, TAC, Gov SFDC, Wingman/license, and workbook tabs. | [docs](./docs/pubsec-big-rocks-row-research.md) |

### Sales operations

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [salesforce-meddpicc-update](./salesforce-meddpicc-update/SKILL.md) | Update MEDDPICC qualification fields and Next Steps on UiPath Salesforce Opportunities through the UiPath Integration Service Salesforce connector. | Update MEDDPICC qualification fields and Next Steps on UiPath Salesforce Opportunities through the UiPath Integration Service Salesforce connector. Use when the user provides or references a Salesforce Opportunity URL or ID and asks to update MEDDPICC, qualification, Metrics, Economic Buyer, Decision Criteria, Decision Process, Paper Process, Identified Pain, Champion, Competition, Compelling Event, or Next Steps. Requires read-before-write, schema describe validation, explicit user confirmation, append-with-date behavior for narrative fields, read-after-write verification, prompt-injection guardrail, fuzzy near-duplicate detection, force-duplicate override, and privacy-safe telemetry logging. | [docs](./docs/salesforce-meddpicc-update.md) |

### UiPath deploy

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [uipcodedappdeploy](./uipcodedappdeploy/SKILL.md) | Deploy UiPath coded app projects with the native UiPath CLI. | Deploy UiPath coded app projects with the native UiPath CLI. Use when Codex needs to increment a coded app package version, validate the project, build the app dist, pack it, publish it, and deploy it to UiPath Automation Cloud alpha using `uip codedapp pack`, `uip codedapp publish`, and `uip codedapp deploy`. | [docs](./docs/uipcodedappdeploy.md) |

## Public repository safety notes

This repo is intended to contain reusable skill instructions and reference material, not live credentials or customer data. Before pushing updates, scan for tokens, secrets, tenant-specific dumps, customer files, and hidden backup directories.

A quick local scan before committing:

```bash
rg -n --hidden -i "(api[_-]?key|secret|password|token|bearer|authorization|client[_-]?secret|private[_-]?key)" .
```
