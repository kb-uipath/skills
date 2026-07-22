# Customer automation portfolio DOCX rules

## Default document

The final customer artifact is a portrait, one-to-two-page Word assessment with exactly three sections:

1. Source File Summary.
2. Current Automation Footprint.
3. Top 3 Recommendations.

Use one compact footprint table and one to three recommendation headings. Do not add an executive-summary section, score table, separate POC section, governance appendix, workshop agenda, or source ledger to the customer document.

## Rendering

Use the standard builder:

```bash
python3 scripts/build_customer_assessment.py \
  --inventory-profile <inventory_profile.json> \
  --evidence-ledger <evidence_ledger.json> \
  --portfolio <portfolio.json> \
  --process-map <process_map.json> \
  --semantic-review <semantic_review.json> \
  --supporting-source <strategy-context.md> \
  --output outputs/<customer>-automation-portfolio-assessment.docx
```

The builder renders Markdown, creates the DOCX with the `customer-assessment` style profile, converts it to PDF with `soffice`, verifies one or two pages with `pypdf`, publishes that exact PDF beside the DOCX, and writes a validation receipt.

Customer-ready builds require `python-docx`, `pypdf`, and `soffice`. `--draft-without-page-check` is an explicit exploratory fallback and adds a draft title.

## Styling

- Robotic Orange `#FA4616` for title emphasis.
- Deep Blue `#182126` for structural headings and table headers.
- Agentic Teal `#0BA2B3` for recommendation headings.
- Arial for shared-document compatibility.
- Compact margins, a narrow label column, short labeled recommendation bullets, page numbers, and no wide tables.
- Customer name as the title; document type, readiness, and prepared date in the subtitle.

Do not add unofficial logos, lockups, Otto graphics, badges, or decorative pixel art.

## Verification

The customer profile verifies:

- Portrait orientation.
- Exact three-section heading contract.
- One to three recommendation headings.
- At least one footprint table.
- No internal IDs.
- Approved colors and Arial, with no legacy Office blue or Aptos.
- A supplied rendered PDF containing one or two pages.

The validation receipt reports readiness, word count, page count, recommendation count, contract,
semantic, language, brand, and layout verification; exact input hashes; raw inventory and optional
local supporting-source basenames and hashes; the latest valid source record date separately from
the ledger, portfolio, review, and build dates; recommendation-to-evidence bindings; and the name and hash of the
published PDF used for page inspection. Absolute local paths are never emitted. If layout or
semantic verification fails, do not deliver the file as customer-ready.

## Legacy detailed mode

`render_portfolio_markdown.py`, `validate_executive_brief.py`, and the renderer's backward-compatible `detailed` profile remain available for internal analysis. Their longer section contract is not the skill's customer default.
