# estimate-du-units

Estimate annual UiPath Document Understanding AI Unit and Platform Unit consumption from messy customer automation descriptions.

## When To Use

Use this skill when a user asks whether DU consumption applies, provides annual transactions and page counts, describes document-heavy automation, or needs low/base/high planning ranges for a customer conversation.

## Inputs

- Document or transaction type.
- Annual transaction count, or enough volume detail to annualize it.
- Pages per transaction or pages per document.
- Whether DU, OCR, classification, extraction, indexing, or human review is in scope.
- Current UiPath rate assumptions and date verified from official UiPath documentation.

## Prompt

```text
Use $estimate-du-units to estimate annual DU consumption for this automation. Verify whether DU applies, state the official rate assumptions and verification date, and calculate low/base/high scenarios.
```

## Outputs

- Markdown scenario table with transactions, pages, AI Units, and Platform Units.
- Assumptions and gaps that need customer validation.
- Zero-DU explanation when the automation is API-only or otherwise outside DU consumption.

## Safety

- Do not present rates as current unless official sources were verified during the run.
- Label inferred volume, pages, and rates as assumptions.
- Keep customer-facing language clear that the output is a planning estimate, not a quote or entitlement statement.

## Validation

```bash
python3 -m unittest discover -s estimate-du-units/tests -p 'test_*.py'
python3 tools/validate_repo.py
```
