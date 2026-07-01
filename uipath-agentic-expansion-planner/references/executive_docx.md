# Agentic Expansion Executive Word Briefing Rules

Use these rules when `uipath-agentic-expansion-planner` produces its final Word `.docx` executive brief. The final artifact is always a rendered AZ DES-style executive portfolio `.docx` unless file creation is impossible or the user explicitly prohibits file output.

## Document Shape

Create a concise Markdown briefing first, then render it with `scripts/render_executive_docx.py` and verify it with `scripts/verify_executive_docx.py`. Portrait orientation is mandatory unless the user explicitly asks for landscape.

Recommended sections:

1. Title and scope line.
2. Executive summary.
3. Source and assumption note.
4. Current automation footprint.
5. Public strategy alignment.
6. Prioritized portfolio.
7. Top 5 high-impact recommendations.
8. Top 3 low-friction POC candidates.
9. Value framing.
10. Deployment and governance considerations.
11. Facts, assumptions, and validation questions.
12. Workshop prep.
13. Recommended next steps.
14. Appendix: source ledger.

Do not paste the full research narrative into Word. The brief should be executive-skimmable and GTM/workshop-ready, with the source ledger kept in the appendix so it does not dominate the opening pages. If the analysis Markdown is too long, create a separate concise Word-source Markdown and keep the longer analysis as a supporting artifact. Use a shorter compact `.docx` brief only when the user explicitly asks for a short executive summary, minimal proposal-card output, or a very concise table-first artifact.

## Executive Style Rules

- Write for executive skimming and GTM/workshop preparation.
- Prefer short paragraphs of 2-4 sentences.
- Prefer direct headings over clever titles.
- Keep proposal cards direct but GTM-usable: recommendation, why now, inventory evidence, agentic enhancement, capability fit, value levers, feasibility, governance, and validation questions.
- Put assumptions next to estimates, not in a buried footnote.
- Use ranges instead of point estimates.
- Preserve confidence ratings and downgrade reasons.
- Put dirty-data caveats plainly in the main body when they affect priority or value.
- Move URLs and long source details to the source ledger or appendix.

## Table Rules

Use these table patterns unless the user asks otherwise:

| Section | Columns |
| --- | --- |
| Current automation footprint | `Dimension` / `Finding` / `Implication` |
| Public strategy alignment | `Public priority` / `Evidence summary` / `Automation relevance` |
| Prioritized portfolio | `Rank` / `Opportunity` / `Category` / `Score` / `Confidence` / `Why it matters` |
| Value framing | `Opportunity` / `Primary value levers` / `Sizing basis` / `Confidence` / `Validation needed` |
| Deployment and governance considerations | `Consideration` / `Implication` / `Recommended control` |
| Workshop prep | `Segment` / `Time` / `Purpose` / `Output` |

Avoid wide, overloaded tables in Word. If a table becomes cramped, shorten cell text before switching to landscape.

## Rendering Command

Use:

```bash
python3 scripts/render_executive_docx.py <brief.md> <brief.docx> --portrait
```

Optional flags:

```bash
python3 scripts/render_executive_docx.py <brief.md> <brief.docx> --portrait --title "Customer Agentic Expansion Brief" --subtitle "Executive briefing"
python3 scripts/render_executive_docx.py <brief.md> <brief.docx> --auto-landscape
```

If `python3` or `python-docx` is missing, call `load_workspace_dependencies` and use the bundled Python runtime.

## Required Verification Command

After rendering, run:

```bash
python3 scripts/verify_executive_docx.py <brief.docx> --require-output-dir
```

If verification fails, fix the source Markdown, rerender the `.docx`, and rerun verification. Do not deliver a `.docx` that fails this script unless the failure is explicitly explained and accepted by the user.

## Verification

The verification script checks the core structural requirements. If verifying manually, cover at least these checks:

- The document has a non-empty title.
- The document is portrait unless the user explicitly asked for landscape.
- Expected AZ DES-style section headings are present: Executive Summary, Source and Assumption Note, Current Automation Footprint, Public Strategy Alignment, Prioritized Portfolio, Top 5 High-Impact Recommendations, Top 3 Low-Friction POC Candidates, Value Framing, Deployment and Governance Considerations, Facts/Assumptions/Validation Questions, Workshop Prep, Recommended Next Steps, and Appendix/Source Ledger.
- Prioritized Portfolio includes at least one ranked table.
- Top 5 High-Impact Recommendations render as proposal-card headings.
- Top 3 Low-Friction POC Candidates render as headings or a compact table.
- Deployment/governance, Workshop Prep, and Source Ledger sections are present.
- Long source ledgers are not dominating the first pages.
- The file path is in the user-facing `outputs/` directory when that directory exists.
- Final chat response links to the generated `.docx`; Markdown or chat text is never treated as the final deliverable.
- If the Documents skill renderer is available, render the `.docx` to page PNGs and visually inspect for clipping, cramped tables, and broken headings before delivery.
