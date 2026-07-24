# kb-uipath skills

This repository contains Codex skills packaged for public GitHub use and broader organizational sharing.

The skills are copied as top-level directories so they can be installed or synced directly into a Codex skills folder. The `docs/` folder contains usage notes, required inputs, and example prompts for each skill.

Last verified: 2026-07-24

## What is included

- 11 top-level Codex skills.
- Per-skill `SKILL.md` files plus bundled references, scripts, assets, and templates.
- Skill-specific documentation in `docs/` with inputs, prompts, outputs, safety notes, and validation commands.
- Repo-level validation through `make validate`, `tools/validate_repo.py`, Python unit tests, Node tests, syntax checks, and whitespace checks.
- Beads development tracking with complete native history on
  `refs/dolt/data`, plus Git-reviewable current state, issue-field history, and
  a hashed manifest under [`.beads/`](./.beads/README.md).
- Hidden backups, `.DS_Store` files, local zip artifacts, and upstream `UiPath/skills` exports are intentionally excluded.

## Latest validated state

As of 2026-07-24, all 11 skills meet the package-quality Org Baseline. Fresh offline forward tests also cover the planner, handoff, availability, GTM proposal, true five-advisor/five-review council, and adaptive Day 2 JSON workflows. Readiness is no longer represented by one score: the repository tracks package quality, functional outcome confidence, and operational certification separately. Salesforce and coded-app deployment remain explicitly uncertified until their opt-in nonproduction workflows run successfully.

See [docs/production-readiness-evaluation.md](./docs/production-readiness-evaluation.md) for the sorted three-axis table, evidence, blockers, and the superseded historical score comparison.

## Runtime And Validation

Expected local validation runtime:

- Python 3.11+ with exact dependencies from `requirements-dev.txt`.
- Node 22+ for Node syntax and test checks.
- GNU-compatible `make`, `git`, and `rg`.

Run the local gate before committing or sharing changes:

```bash
make install-dev
python3 tools/validate_repo.py
make validate
make secrets
```

The gate checks skill metadata, real YAML parsing, docs coverage, relative Markdown links and anchors, external-link safety, local absolute path leaks, plausible secrets, pinned GitHub Actions, pinned development dependencies, root governance files, Python syntax, Python unit tests, Node syntax/tests, and whitespace errors.

The deterministic gate does not make network calls. Run the separate link check when network access is available; failures are reported separately and do not make the offline PR gate flaky:

```bash
make validate-online
```

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
make secrets
```

The gate is the CI-equivalent validation path for this repository. It auto-discovers Python test directories and Node test files so newly added tests are not missed.

`diff-check` compares committed changes with `BASE_REF` (default `origin/main`) and also checks the working tree. Override it for a different target branch with `make validate BASE_REF=origin/release`.

For full DOCX renderer, brand-style, and page-count coverage, use a Python interpreter with `python-docx` and `pypdf` plus `soffice` on `PATH`:

```bash
make validate PYTHON=/path/to/python-with-document-dependencies
```

## Skill index

| Skill | Production outcome | Use when | Docs |
| --- | --- | --- | --- |
| [account-meeting-availability](./account-meeting-availability/SKILL.md) | Maintains a private versioned contact store and ranks slots with privacy-safe availability reasons and bounded diagnostics. | Contact identity, email review, attendee preparation, or deterministic availability ranking is required without sending or scheduling. | [docs](./docs/account-meeting-availability.md) |
| [enrich-day2-dashboard](./enrich-day2-dashboard/SKILL.md) | Builds a schema `1.4` Day 2 dashboard through exact-safe Salesforce seeding, scoped evidence, bounded clarification, and proposal-level approval. | An account team needs executive-ready JSON while keeping protected facts evidence-backed and unsupported gaps explicit. | [docs](./docs/enrich-day2-dashboard.md) |
| [estimate-du-units](./estimate-du-units/SKILL.md) | Produces versioned exact and rounded DU consumption scenarios from verified rate inputs. | A customer needs a defensible AI Unit or Platform Unit estimate with applicability rationale and current source dates. | [docs](./docs/estimate-du-units.md) |
| [gtm-org-proposal-generator](./gtm-org-proposal-generator/SKILL.md) | Validates and renders evidence-backed proposal cards with source-aligned card and aggregate value math. | Public authoritative research must become deployment-aware GTM recommendations without fabricated impact claims. | [docs](./docs/gtm-org-proposal-generator.md) |
| [llm-council](./llm-council/SKILL.md) | Produces a hashed five-advisor/five-review decision record with seeded anonymization, execution evidence, and truthful fallback. | A consequential decision needs independent challenge, disconfirming evidence, and an explicit chairman verdict. | [docs](./docs/llm-council.md) |
| [pubsec-big-rocks-row-research](./pubsec-big-rocks-row-research/SKILL.md) | Creates a validated preview and local workbook copy from manifest-controlled public-sector account evidence. | One Big Rocks account row needs exact matching, fill-eligible evidence, stale-lead separation, and no in-place source edits. | [docs](./docs/pubsec-big-rocks-row-research.md) |
| [repo-hardening-sprint](./repo-hardening-sprint/SKILL.md) | Runs a bounded, base-aware repository validation and governance hardening workflow. | A repository needs scoped cleanup, regression tests, safety scans, or PR readiness without changing public contracts casually. | [docs](./docs/repo-hardening-sprint.md) |
| [salesforce-meddpicc-update](./salesforce-meddpicc-update/SKILL.md) | Builds freshness-bound MEDDPICC transactions, explicit receipts, and read-after-write verification artifacts. | An authorized Salesforce Opportunity update is requested and must pass schema, confirmation, privacy, and retry controls. | [docs](./docs/salesforce-meddpicc-update.md) |
| [uipath-agentic-expansion-planner](./uipath-agentic-expansion-planner/SKILL.md) | Produces a one-to-two-page customer portfolio assessment backed by an analyst-confirmed process map, semantic review, and internal evidence artifacts. | A CSM, TAM, or AE needs the current automation footprint and up to three actionable opportunities with explicit customer-confirmation needs. | [docs](./docs/uipath-agentic-expansion-planner.md) |
| [uipcodedappdeploy](./uipcodedappdeploy/SKILL.md) | Generates hashed deployment plans and redacted resumable receipts before any explicit UiPath deployment. | A coded app needs validated versioning, build, package, publish, deploy, and optional URL verification with no default writes. | [docs](./docs/uipcodedappdeploy.md) |
| [usecasehandoff](./usecasehandoff/SKILL.md) | Builds a nine-file handoff with package hashes, local-source integrity checks, and a no-send boundary. | An automation idea must become evidence-backed analysis, delivery work, risks, references, and a concrete first sprint. | [docs](./docs/usecasehandoff.md) |

## Public repository safety notes

This repo is intended to contain reusable skill instructions and reference material, not live credentials or customer data. Before pushing updates, scan for tokens, secrets, tenant-specific dumps, customer files, and hidden backup directories.

A quick local scan before committing:

```bash
rg -n --hidden -i "(api[_-]?key|secret|password|token|bearer|authorization|client[_-]?secret|private[_-]?key)" .
```

## Governance

- License: [Apache-2.0](./LICENSE).
- Contribution rules: [CONTRIBUTING.md](./CONTRIBUTING.md).
- Code ownership: [CODEOWNERS](./CODEOWNERS), owned by `@kb-uipath`.
- Support policy: [SUPPORT.md](./SUPPORT.md).
- Security reporting: [SECURITY.md](./SECURITY.md), including private advisory guidance.
