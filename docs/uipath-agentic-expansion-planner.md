# uipath-agentic-expansion-planner

Profile customer automation inventories and produce an on-brand, evidence-backed, verified executive DOCX expansion brief.

## When To Use

Use this skill when the user provides an automation or use-case inventory and wants Act 2 expansion ideas, agentic automation prioritization, top recommendations, POC candidates, and a customer-ready Word brief that is specific, executive-skimmable, and aligned to UiPath brand guidance.

## Inputs

- Inventory file in CSV or XLSX format.
- Customer name, vertical, and deployment context.
- Desired scope, such as top 5 high-impact recommendations and top 3 POC candidates.
- Public strategy or customer context sources when available.
- Optional DOCX renderer dependencies: `python-docx`; optional XLSX profiling dependency: `openpyxl`.
- Whether the output is internal planning or customer-ready. Customer-ready briefs must pass the Markdown quality gate and DOCX brand-style verification.

## Prompt

```text
Use $uipath-agentic-expansion-planner on this inventory. Profile the data, identify top expansion opportunities, write an on-brand executive brief with a clear decision ask, render the DOCX, and verify both content quality and Word brand style before final response.
```

## Outputs

- `inventory_profile.json`.
- `inventory_profile.md`.
- Markdown draft for the executive brief.
- Rendered `.docx` executive brief as the final artifact when file output is possible.
- Markdown quality validation summary.
- Structural and brand-style verification summary for the DOCX.
- Golden inventory profile expectations for regression tests.

## Safety

- Treat sparse inventories as planning signals, not audited telemetry.
- Mark weak value claims as `validation required`.
- Keep deployment context as a hard constraint on capability recommendations.
- If `openpyxl` or `python-docx` is unavailable, explain the fallback: CSV-only profiling or Markdown-only draft until dependencies are installed.
- Treat DOCX verification failure as a blocking defect, not a cosmetic warning.
- The final deliverable contract for this skill is a rendered DOCX when file output is allowed.
- Do not store private brand-book files, private SharePoint URLs, logos, lockups, avatars, badges, or decorative brand assets in this public repo unless approved assets are explicitly supplied.
- Reject generic agentic claims, hype language, and product-first summaries that do not start from the customer's need.

## Validation

```bash
python3 -m unittest discover -s uipath-agentic-expansion-planner/tests -p 'test_*.py'
python3 uipath-agentic-expansion-planner/scripts/validate_executive_brief.py <brief.md>
python3 uipath-agentic-expansion-planner/scripts/verify_executive_docx.py <brief.docx> --require-brand-style
python3 tools/validate_repo.py
```
