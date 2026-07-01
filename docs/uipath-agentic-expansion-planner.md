# uipath-agentic-expansion-planner

Profile customer automation inventories and produce a verified executive DOCX expansion brief.

## When To Use

Use this skill when the user provides an automation or use-case inventory and wants Act 2 expansion ideas, agentic automation prioritization, top recommendations, POC candidates, and a customer-ready Word brief.

## Inputs

- Inventory file in CSV or XLSX format.
- Customer name, vertical, and deployment context.
- Desired scope, such as top 5 high-impact recommendations and top 3 POC candidates.
- Public strategy or customer context sources when available.
- Optional DOCX renderer dependencies: `python-docx`; optional XLSX profiling dependency: `openpyxl`.

## Prompt

```text
Use $uipath-agentic-expansion-planner on this inventory. Profile the data, identify top expansion opportunities, render a DOCX executive brief, and verify the Word document structure before final response.
```

## Outputs

- `inventory_profile.json`.
- `inventory_profile.md`.
- Markdown draft for the executive brief.
- Rendered `.docx` executive brief as the final artifact when file output is possible.
- Structural verification summary for the DOCX.
- Golden inventory profile expectations for regression tests.

## Safety

- Treat sparse inventories as planning signals, not audited telemetry.
- Mark weak value claims as `validation required`.
- Keep deployment context as a hard constraint on capability recommendations.
- If `openpyxl` or `python-docx` is unavailable, explain the fallback: CSV-only profiling or Markdown-only draft until dependencies are installed.
- Treat DOCX verification failure as a blocking defect, not a cosmetic warning.
- The final deliverable contract for this skill is a rendered DOCX when file output is allowed.

## Validation

```bash
python3 -m unittest discover -s uipath-agentic-expansion-planner/tests -p 'test_*.py'
python3 tools/validate_repo.py
```
