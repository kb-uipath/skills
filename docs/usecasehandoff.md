# usecasehandoff

Capture, verify, synthesize, package, and route automation use-case handoffs for delivery teams.

## Runtime And Dependencies

- Runtime: Python 3.10+.
- Dependencies: Python standard library only.
- Entry point: `usecasehandoff/scripts/create_handoff_package.py`.
- External writes: none. The helper only creates, migrates, validates, and updates local package files.

## When To Use

Use this skill when a customer or internal automation idea needs to become an evidence-backed handoff package with executive framing, delivery plan, risks, references, and next steps.

## Inputs

- Customer or internal team.
- Use case name, process name, sponsor, and stakeholders.
- Source materials from chat, files, email, Slack, Teams, SharePoint, Drive, or public sources.
- Current and target process details.
- Metrics, systems, integrations, constraints, and delivery audience.

## Versioned Package Contract

Contract `usecasehandoff.package` schema version `1.0.0` uses exactly nine stable files:

- `README.md`
- `executive-summary.md`
- `analysis.md`
- `evidence-ledger.md`
- `delivery-plan.md`
- `risk-register.md`
- `references.md`
- `cover-message.md`
- `manifest.json`

`manifest.json` records schema, status, classification, retention, package time, last verification time, stable file list, SHA-256 hashes for every non-manifest file, and `no_send: true`.

Package status must be one of `scaffold`, `draft`, `ready`, `routed`, or `archived`. A new scaffold is intentionally not ready to route.

## Prompt

```text
Use $usecasehandoff to package this automation use case for a delivery team. Build an evidence ledger first, separate facts from assumptions, create the delivery plan, and do not upload or send anything without confirmation.
```

## Outputs

- Dated handoff package folder.
- Analysis of current state, pain points, constraints, value drivers, assumptions, and validation questions.
- Evidence ledger.
- Delivery plan.
- Risk register.
- References.
- Cover message.
- Optional ZIP or routed upload only after confirmation.
- Validation result for an existing handoff package.

## Runnable Example

Create a local scaffold:

```bash
python3 usecasehandoff/scripts/create_handoff_package.py \
  --title "Permit Intake Automation" \
  --account "Fixture Agency" \
  --output-dir outputs \
  --date 2026-07-10 \
  --slug permit-intake
```

Confirm the scaffold shape:

```bash
python3 usecasehandoff/scripts/create_handoff_package.py \
  --validate outputs/2026-07-10-permit-intake \
  --level scaffold
```

After filling every source, owner, acceptance criterion, test strategy, first sprint item, and next action, refresh the manifest and run ready validation:

```bash
python3 usecasehandoff/scripts/create_handoff_package.py \
  --refresh-manifest outputs/2026-07-10-permit-intake \
  --status ready

python3 usecasehandoff/scripts/create_handoff_package.py \
  --validate outputs/2026-07-10-permit-intake
```

Migrate an older six-file package before validation:

```bash
python3 usecasehandoff/scripts/create_handoff_package.py \
  --migrate outputs/legacy-handoff-package
```

## Safety

- Do not send, post, upload, or share package artifacts without explicit authorization.
- Do not present uncited metrics as facts.
- Separate customer-specific evidence from public/vendor documentation.
- Use `scripts/create_handoff_package.py` for deterministic local scaffolding before connector writes.
- Use ready validation before routing a package to any external destination.
- Ready validation fails closed for placeholders, uncited non-open claims, ownerless rows, empty acceptance criteria, empty test strategy, empty first sprint backlog, missing next action, stale hashes, or a manifest status other than `ready`.

## Classification And Retention

- Default classification is `internal`.
- Supported classifications are `public`, `internal`, `confidential`, and `restricted`.
- The default retention statement keeps the package with customer/account handoff records and removes local working copies after routing or archival per policy.
- Override classification or retention at scaffold, migration, or manifest refresh time when the customer data handling requirement is stricter.

## Recovery

- If scaffold validation fails, restore the nine stable files or run `--migrate` for legacy packages.
- If ready validation fails, fix the named file and field, then run `--refresh-manifest --status ready` before validating again.
- If a route/upload attempt fails after user authorization, do not retry blindly. Confirm destination, permissions, and manifest hashes before any second attempt.
- If sensitive content lands in the wrong artifact, stop routing, remove the local working copy, rebuild the package, and rerun ready validation.

## Limitations

- The helper does not fetch evidence, search connectors, send messages, upload files, or verify external destinations.
- Ready validation proves package structure and minimum content completeness; it does not prove business truth beyond the supplied citations.
- SHA-256 hashes cover the nine-file package contract only. Additional attachments should be referenced rather than added into the package directory.

## Validation

```bash
python3 -m unittest discover -s usecasehandoff/tests -p 'test_*.py'
python3 tools/validate_repo.py
```

## Certification

Certified locally with unit coverage for deterministic scaffolding, overwrite protection, scaffold-level validation, default ready validation, ready defect rejection, legacy migration guidance, and migrated scaffold validation.

## Last Verified

2026-07-10
