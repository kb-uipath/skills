# usecasehandoff

Capture, verify, synthesize, package, and route automation use-case handoffs for delivery teams.

## When To Use

Use this skill when a customer or internal automation idea needs to become an evidence-backed handoff package with executive framing, delivery plan, risks, references, and next steps.

## Inputs

- Customer or internal team.
- Use case name, process name, sponsor, and stakeholders.
- Source materials from chat, files, email, Slack, Teams, SharePoint, Drive, or public sources.
- Current and target process details.
- Metrics, systems, integrations, constraints, and delivery audience.

## Prompt

```text
Use $usecasehandoff to package this automation use case for a delivery team. Build an evidence ledger first, separate facts from assumptions, create the delivery plan, and do not upload or send anything without confirmation.
```

## Outputs

- Dated handoff package folder.
- Evidence ledger.
- Delivery plan.
- Risk register.
- Cover message.
- Optional ZIP or routed upload only after confirmation.
- Validation result for an existing handoff package.

## Safety

- Do not send, post, upload, or share package artifacts without explicit authorization.
- Do not present uncited metrics as facts.
- Separate customer-specific evidence from public/vendor documentation.
- Use `scripts/create_handoff_package.py` for deterministic local scaffolding before connector writes.
- Use `scripts/create_handoff_package.py --validate <package-dir>` before routing a package to any external destination.

## Validation

```bash
python3 -m unittest discover -s usecasehandoff/tests -p 'test_*.py'
python3 tools/validate_repo.py
```
