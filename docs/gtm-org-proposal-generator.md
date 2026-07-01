# gtm-org-proposal-generator

Generate source-backed UiPath automation proposal cards from public organizational research.

## When To Use

Use this skill for public-sector agencies, companies, universities, healthcare systems, or other institutions where the user wants budget-informed proposal cards and a prioritized use-case table.

## Inputs

- Organization name and exact target entity.
- Industry or vertical.
- UiPath deployment context.
- Any scope limits, geography, fiscal year, or output format.
- Permission to browse current public sources and current UiPath product documentation.

## Prompt

```text
Use $gtm-org-proposal-generator for Fixture Agency in public sector on Automation Cloud Public Sector. Build a public-source ledger, rank budget-backed program areas, and produce cited proposal cards without unsupported ROI claims.
```

## Outputs

- Confirmed scope.
- Source ledger with IDs such as `[S1]`.
- Budget/program-area table.
- Prioritized use cases.
- Executive proposal cards with estimate tier labels.
- Assumptions and validation questions.
- Static validation for required sections, source IDs, cited money/percentage claims, estimate tiers, and overclaim language.

## Safety

- Use public authoritative sources by default; do not use internal Slack, Teams, SharePoint, Drive, email, or Salesforce unless the user explicitly changes scope.
- Browse for current laws, budgets, filings, and UiPath capability availability because those details drift.
- Never fabricate budget lines, savings, licensing availability, or deployment eligibility.
- Label impact estimates as `Documented`, `Derived`, `Benchmarked`, or `Assumption`.
- Treat uncited money or percentage claims as validation failures.

## Validation

```bash
python3 -m unittest discover -s gtm-org-proposal-generator/tests -p 'test_*.py'
python3 gtm-org-proposal-generator/scripts/validate_gtm_output.py path/to/proposal.md
python3 tools/validate_repo.py
```
