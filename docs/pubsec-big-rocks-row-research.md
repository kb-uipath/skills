# pubsec-big-rocks-row-research

Research one account row in the PubSec CS Portfolio Big Rocks workbook and return evidence-backed fill recommendations.

## When To Use

Use this skill when the user asks to fill, review, or validate a single Big Rocks account row using workbook tabs and provided internal evidence sources.

## Inputs

- Big Rocks workbook path.
- Target row number or exact account name.
- Optional local source workbook paths.
- Whether to use `--sources-only` to skip built-in local default source paths.
- Recency cutoff, either months or max age days.
- Permission boundaries for SharePoint, Slack, OneNote, Teams, Salesforce, or other internal sources.

## Prompt

```text
Use $pubsec-big-rocks-row-research for row 42 in this Big Rocks workbook. Identify blank target fields, scan only current evidence, and return fill recommendations with source-backed caveats. Do not write to the workbook.
```

## Outputs

- Target account row summary.
- Blank or placeholder target fields.
- Structured source matches.
- Internal workbook tab matches.
- Stale/missing source report.
- Recommendation leads to investigate before filling cells.
- Markdown guidance that stale, missing, or undated evidence must not be used to fill workbook cells.

## Safety

- Do not fill workbook cells unless the user explicitly asks after reviewing evidence.
- Treat stale rows, missing files, placeholder bullets, and weak source timestamps as `do not fill` signals.
- Use `--include-stale` only for discovery; stale matches remain leads, not fill-ready evidence.
- Use internal sources only within the user's authorization.
- Keep customer-specific evidence citations specific enough for review but avoid exposing credentials or private exports in public docs.

## Validation

```bash
python3 -m unittest discover -s pubsec-big-rocks-row-research/tests -p 'test_*.py'
python3 tools/validate_repo.py
```
