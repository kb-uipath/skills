# DU Estimation Guide

Use this reference when the estimate needs a full worksheet, source discipline, or a defensible written artifact.

## Source Hierarchy

| Rank | Source | Notes |
|---:|---|---|
| 1 | Customer production logs, queue counts, Orchestrator data | Best for actual customer consumption |
| 2 | Source-system reports | Imaging, claims, ERP, CRM, mailbox, repository, case system |
| 3 | Document repository counts | Folder, batch table, document class, scan count |
| 4 | Official or regulatory workload estimate | Useful for public forms; label as proxy if not customer-specific |
| 5 | SME estimate | Use a confidence discount and scenario band |
| 6 | Scenario band | Use when discovery is early |

## Applicability Decision Table

| Condition | DU estimate |
|---|---|
| Scanned paper, PDF, image, fax, or attachment must be OCRed | Yes |
| Document type must be classified from content or image | Yes |
| Fields must be extracted from a document | Yes |
| Bot only uses structured source-system fields or an API | No |
| Bot only clicks a downstream category from existing metadata | No unless it re-reads the page |
| Description says scan/manual indexing/batch but not OCR/extraction | Conditional |
| GenAI/Semantic Activities process text outside DU | Estimate under that meter, not DU |

## Metering Checklist

Verify from current official UiPath sources:

- Deployment and plan: Automation Cloud, Public Sector, Dedicated, Automation Suite, Flex, Unified, or other.
- Project type: modern, classic, mixed, predefined generative, or standalone activity.
- Package/API path: DocumentUnderstanding.Activities, IntelligentOCR.Activities, REST API, or IXP API.
- Add-ons: Generative Validation, classic extractor/classifier, standalone extraction, duplicate processing.
- Consumption unit: AI Units or Platform Units.

Current public planning defaults to verify before use:

- Modern DU: 1 AI Unit per processed page.
- IXP Document Understanding Platform Units: 0.2 Platform Units per page in the public licensing table.
- Generative Validation and mixed/classic paths can add consumption; do not assume the base page rate covers them.

Official sources to check:

- UiPath Document Understanding metering: https://docs.uipath.com/document-understanding/automation-cloud/latest/user-guide/metering-charging-logic
- UiPath licensing table: https://licensing.uipath.com/

## Formula

Single document type:

```text
annual_units = annual_transactions x average_pages_per_transaction x units_per_page
```

Multiple document types:

```text
annual_units =
  sum(document_type_annual_transactions x document_type_average_pages x document_type_units_per_page)
```

Annualization examples:

```text
90-day count x 365 / 90
monthly average x 12
weekly average x 52
daily average x business_days_per_year
```

## Response Template

````markdown
Expected annual consumption: **[rounded estimate] [AI Units/Platform Units] per year**.

Formula:

```text
[transactions/year] x [pages/transaction] x [units/page] = [units/year]
```

Applicability:
[State whether DU applies, does not apply, or is conditional.]

Assumptions:
- [Document/page assumption]
- [Volume source assumption]
- [Metering model and date/source]
- [Any add-ons excluded or included]

Sensitivity:

| Scenario | Transactions/year | Pages/transaction | Units/page | Annual units |
|---|---:|---:|---:|---:|
| Low |  |  |  |  |
| Base |  |  |  |  |
| High |  |  |  |  |

Confidence: [High/Medium/Low] because [reason].

Clarifying questions:
1. [Only if needed]
````

## Worked Example: SSA CMS-1763

Customer wording:

> TOEL Automation - Assign a HISMI TERM TOEL in Paperless Manual Indexing to a single page batch of CMS-1763 scanned through FECSUI.

Interpretation:

The automation appears to route or index a scanned CMS-1763 Medicare termination form by assigning the HISMI TERM event/category in SSA Paperless Manual Indexing. This sounds like clerical indexing rather than an eligibility decision.

Applicability:

- DU applies if the automation uses OCR/classification/extraction to identify or read the scanned CMS-1763 page.
- DU does not apply if FECSUI or a human already provides the document type and the bot only assigns the downstream TOEL value.

Base planning calculation:

```text
197,518 forms/year x 1 page/form x 1 AI Unit/page = 197,518 AI Units/year
197,518 pages/year x 0.2 Platform Units/page = 39,503.6 Platform Units/year
```

Planning estimate:

Use about 200,000 AI Units/year, or about 40,000 Platform Units/year under Platform Unit metering, assuming every CMS-1763 response is processed through modern DU as a one-page document.

Confidence:

Medium. The page count comes from the customer wording and the public form volume can be sourced, but actual SSA/customer throughput may differ and DU may not be needed if the form is already identified upstream.
