# Executive Word Briefing Rules

Use these rules for every Act 2 customer expansion proposal run. The final artifact is a Word `.docx` executive brief unless the user explicitly prohibits file output.

## Document Shape

Create a concise Markdown briefing first, then render it with `scripts/render_executive_docx.py`. Portrait orientation is mandatory unless the user explicitly asks for landscape.

Recommended sections:

1. Title and scope line.
2. Source and assumption note, no more than 120 words.
3. Combined prioritization table with the strongest 5-8 recommendations.
4. Proposal cards for the strongest 3-6 recommendations.
5. Validation checklist or caveats.
6. Source ledger or appendix, shortened to essential sources.

Do not paste the full research narrative into Word. If the Markdown deliverable is long, create a shorter Word-brief version before rendering.

## Executive Style Rules

- Write for an executive skimming in under five minutes.
- Prefer short paragraphs of 2-4 sentences.
- Prefer direct headings over clever titles.
- Keep proposal cards compact: challenge, solution, capabilities, impact, evidence/caveat.
- Put assumptions next to estimates, not in a buried footnote.
- Use ranges instead of point estimates.
- Preserve confidence ratings and downgrade reasons.
- Put dirty-data caveats plainly in the main body when they affect priority or value.
- Move URLs and long source details to the source ledger or appendix.

## Table Rules

For the prioritization table, use these columns unless the user asks otherwise:

| Column | Guidance |
| --- | --- |
| Rank | 1, 2, 3... |
| Recommendation | Short executive title. |
| Strategic fit | Public-source objective or program area. |
| Inventory evidence | Named rows plus status or volume where available. |
| Value pool | Range or "validation required." |
| Confidence | High/Medium/Low plus one caveat. |
| Next step | Concrete validation or pilot action. |

Avoid wide, overloaded tables in Word. If a Markdown table has more than seven columns, combine related columns before rendering instead of switching to landscape.

## Rendering Command

Use:

```bash
python3 scripts/render_executive_docx.py <brief.md> <brief.docx> --portrait
```

Optional flags:

```bash
python3 scripts/render_executive_docx.py <brief.md> <brief.docx> --portrait --title "USDA Act 2 Expansion Brief" --subtitle "Executive briefing"
python3 scripts/render_executive_docx.py <brief.md> <brief.docx> --auto-landscape
```

If `python3` or `python-docx` is missing, call `load_workspace_dependencies` and use the bundled Python runtime.

## Verification

After rendering, verify with `python-docx`:

- The document has a non-empty title.
- The document is portrait unless the user explicitly asked for landscape.
- Prioritization output includes at least one table.
- Proposal cards render as headings.
- Long source ledgers are not dominating the first pages.
- The file path is in the user-facing `outputs/` directory when that directory exists.
