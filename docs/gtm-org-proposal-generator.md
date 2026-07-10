# gtm-org-proposal-generator

Generate source-backed UiPath automation proposal cards from public organizational research, using a versioned JSON contract and deterministic Markdown renderer.

## When To Use

Use this skill for public-sector agencies, companies, universities, healthcare systems, or other institutions where the user wants budget-informed proposal cards and a prioritized use-case table.

Use it only when public authoritative sources are enough for the requested output. If the user wants internal, customer-confidential, Salesforce, Slack, Teams, SharePoint, Drive, or email evidence, confirm the expanded scope and use a more appropriate workflow.

## Runtime And Dependencies

- Runtime: Python 3 standard library.
- Local validator and renderer: `gtm-org-proposal-generator/scripts/validate_gtm_output.py`.
- Network: research requires browsing current public sources and current UiPath documentation; validation and rendering run offline.
- External writes: none. The skill should not write to live customer, CRM, collaboration, or production systems.
- Contract reference: [versioned-contract.md](../gtm-org-proposal-generator/references/versioned-contract.md).

## Versioned Contract

The contract of record is JSON with:

```json
{
  "contract_version": "gtm-org-proposal-generator/v1"
}
```

The v1 contract requires confirmed scope, public classification, source ledger, capability ledger, budget/program areas, prioritized use cases, proposal cards, evidence gaps, and assumptions. Legacy free-form Markdown fails closed with migration guidance; convert it to the v1 JSON contract and render Markdown from the validated JSON.

Fewer than 10 cards are valid when the evidence-backed set is smaller, but every card must be complete and `evidence_gaps` must explain why the portfolio is smaller.

## Inputs

- Organization name and exact target entity.
- Industry or vertical.
- UiPath deployment context.
- Any scope limits, geography, fiscal year, or output format.
- Permission to browse current public sources and current UiPath product documentation.

## Prompt

```text
Use $gtm-org-proposal-generator for Fixture Agency in public sector on Automation Cloud Public Sector. Build a public-source ledger, rank budget-backed program areas, produce the v1 JSON contract, validate it, and render cited proposal cards without unsupported ROI claims.
```

## Runnable Example

Create `fixture.contract.json` with the required v1 fields, then run:

```bash
python3 gtm-org-proposal-generator/scripts/validate_gtm_output.py fixture.contract.json --render fixture.proposal.md
```

Expected success output:

```text
GTM proposal contract validated and rendered to fixture.proposal.md.
```

To validate without rendering:

```bash
python3 gtm-org-proposal-generator/scripts/validate_gtm_output.py fixture.contract.json
```

## Outputs

- Validated `gtm-org-proposal-generator/v1` JSON contract.
- Rendered Markdown with confirmed scope.
- Source ledger with IDs such as `[S1]`.
- Capability ledger with docs checked dates and deployment fit.
- Budget/program-area table.
- Prioritized use cases.
- Executive proposal cards with estimate tier labels and visible impact math.
- Evidence gaps and validation questions.

## Safety

- Use public authoritative sources by default.
- Browse for current laws, budgets, filings, and UiPath capability availability because those details drift.
- Never fabricate budget lines, savings, licensing availability, or deployment eligibility.
- Label impact estimates as `Documented`, `Derived`, `Benchmarked`, or `Assumption`.
- Treat uncited money or percentage claims, unsupported overclaim language, missing impact math, and stale or mismatched capability deployment evidence as validation failures.

## Recovery

If validation fails:

- Fix the JSON contract rather than editing rendered Markdown.
- Add missing source rows before adding claims that depend on them.
- Add current `docs.uipath.com` capability evidence before using a capability in a card.
- If fewer than 10 cards are supportable, keep the smaller complete set and document the evidence gap.
- If the input is legacy Markdown, migrate it to `gtm-org-proposal-generator/v1`; the validator intentionally rejects free-form Markdown.

## Classification And Retention

- Default classification: `Public`.
- Default retention: retain only in approved public-source GTM workspaces per account-team policy.
- Do not include confidential, customer-private, internal-only, or credential-like material in this skill's default contract.
- If the user explicitly expands scope beyond public sources, record that scope change and use a workflow with the right access and retention controls.

## Limitations

- The skill produces planning-grade proposal material, not guaranteed ROI, licensing advice, entitlement confirmation, or implementation sizing.
- UiPath capability availability can drift; the capability ledger must include a current docs checked date.
- Public budgets can be aggregate, stale, overlapping, or incomplete. Do not create fake precision to hide source gaps.
- The renderer is deterministic, but it cannot prove that a cited source truly supports a claim; the operator must verify source relevance during research.

## Certification

- Contract version: `gtm-org-proposal-generator/v1`.
- Local runtime dependency: Python 3 standard library only.
- Validation command: `python3 gtm-org-proposal-generator/scripts/validate_gtm_output.py fixture.contract.json --render fixture.proposal.md`.
- Repository gate: `python3 tools/validate_repo.py`.
- Last verified: 2026-07-10.

## Validation

```bash
python3 -m unittest discover -s gtm-org-proposal-generator/tests -p 'test_*.py'
python3 gtm-org-proposal-generator/scripts/validate_gtm_output.py fixture.contract.json --render fixture.proposal.md
python3 tools/validate_repo.py
```
