# Brand and brief quality rules

Use these rules when preparing the final executive brief. They are derived from UiPath brand guidance, but this repo must not store internal brand files, private links, logos, lockups, or long copied brand-book excerpts.

## Voice

- Be human, direct, warm, and practical.
- Lead with the customer's business need, not UiPath product vocabulary.
- Write peer-to-peer. Avoid sounding like a vendor brochure or a technical lecture.
- Make the brief skimmable with short paragraphs, decision-oriented headings, and clear tables.
- Say something specific. A vague "AI can transform operations" claim is not useful enough to ship.

## Executive impact

Every final brief must make these points easy to find:

1. Why this matters now for the customer.
2. What decision or next step the account team should ask for.
3. Which inventory patterns support the recommendation.
4. Which public strategy priorities make it executive-relevant.
5. Which assumptions still need customer validation.

The executive summary should be 3-5 tight sentences. It should name the strongest opportunity themes, explain the customer-facing value, and state the recommended next action.

## Recommendation quality

Reject or rewrite recommendation cards that are generic, unsupported, or too product-led. Each high-impact recommendation must include:

- `Recommendation`
- `Why now`
- `Inventory evidence`
- `Agentic enhancement`
- `UiPath capability fit`
- `Value levers`
- `Feasibility`
- `Governance`
- `Validation questions`

Each low-friction POC candidate must define a narrow scope, agent role, human role, success metrics, data needed, and exit criteria. If those details cannot be stated, the candidate is not ready to be positioned as a POC.

## Visual brand profile for generated Word briefs

Use a restrained UiPath-derived document style:

- Robotic Orange `#FA4616` for title emphasis and selective highlights.
- Deep Blue `#182126` for table headers, structural rules, and primary document structure.
- Agentic Teal `#0BA2B3` for agentic sections, level-three recommendation headings, and callout accents.
- Bright White `#FFFFFF` and neutral greys for whitespace, alternating rows, and readability.
- Arial as the shared-document fallback font. Do not bundle brand fonts.

Do not create unofficial logos, logo lockups, Otto graphics, custom badges, or decorative pixel systems. Use approved assets only when the user supplies them or explicitly points to an approved template.

## Quality gate

Before rendering the Word file, run:

```bash
python3 scripts/validate_executive_brief.py <brief.md>
```

After rendering, run structural and brand-style verification:

```bash
python3 scripts/verify_executive_docx.py <brief.docx> --require-output-dir --require-brand-style
```

If either validator fails, fix the Markdown or renderer output before delivery.
