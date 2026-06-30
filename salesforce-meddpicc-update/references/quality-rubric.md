# MEDDPICC Drafting Quality Rubric

Use this before drafting content from notes, transcripts, spreadsheets, PDFs, email, or Slack.

## Non-Negotiables

- Use specific facts from the source material. Do not invent metrics, dates, names, titles, competitors, budgets, legal steps, or close plans.
- Mark weakly supported content with confidence: `Confidence: high`, `Confidence: moderate`, `Confidence: low`, or `Confidence: unknown`.
- Prefer concise, sales-useful language over meeting-summary prose.
- Keep each MEDDPICC field focused on its own purpose. Do not dump the same paragraph into every field.
- Put unresolved assumptions in warnings or action items, not in Salesforce as fact.

## Field Quality

- Metrics: business impact, quantified value, scale, cost, time, risk, or efficiency. If there are no numbers, say what metric is missing.
- Economic Buyer: identify the buyer or buyer gap. Write Contact ID only to the lookup; put strategy narrative in Opportunity Next Steps.
- Decision Criteria: buying requirements in the customer's language, especially high-priority capabilities and differentiators.
- Decision Process: who decides, sequence of approvals, evaluation gates, and timing.
- Paper Process: procurement, legal, security, vendor onboarding, order-form, or signature path.
- Identified Pain: concrete operational or strategic pain, not generic transformation language.
- Champion: power, influence, access, selling behavior, and risk. Write Contact ID only to the lookup; put strategy narrative in Opportunity Next Steps.
- Competition: use `Competition_meddic__c` for narrative; use `Competition__c` only for allowed picklist values.
- Compelling Event: time-bound business reason. Route to Opportunity Next Steps.
- NextStep: one short, owner-oriented headline under 255 characters.

## Confirmation Summary

Before writing, show:

- Opportunity name and ID.
- Proposed API fields and plain-language labels.
- New dated entry text for appended fields.
- Replaced `NextStep` value, if any.
- Skipped lookup or picklist fields.
- Warnings, confidence gaps, duplicates, truncation, stale-read risk, and action items.
