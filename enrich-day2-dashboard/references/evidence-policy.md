# Day 2 Evidence Policy

Policy version: `day2-evidence-policy/v2`.

Use this policy when creating or reviewing evidence ledger items and proposals. The dashboard is an executive decision artifact, not a repository for every discovered fact.

## Claim classes

- `actual`: Observed or realized fact with a defined scope and date.
- `target`: Intended quantified outcome that has not yet been realized.
- `plan`: Intended action, milestone, or future state.
- `risk`: Explicit blocker, exposure, or unresolved dependency.
- `opinion`: Interpretation, sentiment, or judgment.
- `meeting-scheduled`: A calendar occurrence or invitation. It does not prove decisions, outcomes, attendance, or relationship quality.

Never rewrite a target or plan as an actual. Never infer Green health from silence.

## Account-team attestation

`account-team-attestation` is bounded authority captured through an exact preview question. It may support:

- motion selection and rationale;
- goals, targets, workstreams, milestones, internal owners, risks, and mitigations;
- ELT asks, relationship actions, internal pipeline, and plan/risk/owner motion answers;
- explicit health judgments with a stated basis;
- status progress, risk/decision, and next action.

It may classify an explicit internal pipeline status, workstream progress, or status progress as an internal `actual`. It may not be sole authority for ARR, renewal, purchases, deployment, delivery model, utilization, product consumption, production automation/agent counts, realized value, actual customer use cases, customer commitments/outcomes, or occurred cadence. `unknown` is an evidence gap, never dashboard content.

The status value line always requires external actual evidence. An attested Green health indicator requires separately approved status and evidence proposals. Red health requires evidence, mitigation, and owner.

## Authority by dashboard meaning

| Dashboard meaning | Minimum acceptable authority | Rejected shortcuts |
|---|---|---|
| Current ARR, purchased products | Dated contract, order, or license record | Slack, email recollection, personal notes |
| Actual utilization or production counts | Product telemetry or dated validated account document | Forecasts, plans, generic Salesforce Assets |
| Realized savings or value | Dated validated outcome record with scope | Target business case, internal estimate |
| Deployment or delivery model | Explicit dated account/system record | Product names or team attendance |
| Customer intent or commitment | Direct customer statement or validated customer/account record | Internal paraphrase alone |
| Internal owner, task, or blocker | Explicit internal operational record | Calendar attendance |
| QBR/EBC/account milestone | Salesforce exact date or dated validated source | Unconfirmed narrative date |
| Calendar event | Calendar record for date, invitees, and schedule only | Inferred decision or outcome |
| Detailed health | Explicit evidence plus human approval | Sentiment, absence of escalation |
| Relationship pairing or strength | Identified people/roles plus human approval | Email receipt or meeting attendance |

`public-web` evidence may support external customer priorities in a headline, goal, or motion answer. It may never support UiPath account health, delivery status, realized value, internal ownership, or customer commitments.

## Source and authority compatibility

Never assign authority from content alone. The source type and connector-envelope author must permit it:

| Source type | Allowed authority |
|---|---|
| Salesforce | `salesforce-exact` |
| SharePoint, OneDrive | `contract-order`, `license-record`, `validated-account-document` |
| Outlook attachment, local file | `contract-order`, `license-record`, `validated-account-document` |
| Outlook Email, Slack, Teams | `customer-statement` for authenticated customer authors; `internal-operations` for UiPath/system authors |
| Telemetry | `product-telemetry` |
| Outlook Calendar | `calendar-event` |
| OneNote | `personal-note` |
| Public web | `public-web` from a public author |

OneNote is corroboration-only for every dashboard proposal. A proposal supported solely by OneNote is invalid, regardless of field.

## Dates and search window

- Treat `windowStart` and `windowEnd` as inclusive. Default to the prior 180 days through today.
- Use Calendar occurrence date for window eligibility. For other sources, use modification date when present, otherwise occurrence date.
- Retrieval or verification time never makes an old claim current.
- Reject future-dated source modification times. Reject future source occurrence dates except for an Outlook Calendar item classified `meeting-scheduled`; a future date can never prove an actual.
- Accept older foundational evidence only when the user explicitly supplies its link or stable ID, that exact `sourceId` appears in `scope.foundationalSourceIds`, and the ID resolves to exactly one collected item. Reject ambiguous IDs across containers.
- Preserve the source's claim date and class. A current plan referencing an older target does not turn the target into an actual.

## Proposal policy

- Auto-apply no contextual proposal. The Salesforce child skill is the only automatic blank-field layer.
- Require the contextual input to contain the Salesforce child's compact provenance, the same `001...` Account ID as the ledger, and a current `Account.Name` exactly matching both the dashboard customer name and ledger canonical name. Aliases never replace this check.
- For field-specific authority rules, the same evidence item must carry both the proposal claim class and the required authority. Do not pool an `actual` personal note with an unrelated validated `plan`.
- Require one stable proposal ID per approval. Never accept an approval wildcard or `approve all`.
- Preserve existing nonblank values unless their exact proposal ID is approved.
- Surface contradictory evidence as a conflict. Do not select the newest item automatically.
- Retain exactly one current evidence item for each `{sourceType, tenantId, container, sourceId}` identity. Reject parallel captures of the same identity; record a changed or contradictory capture as a gap requiring a new preview.
- Treat array placement as part of the proposal. Page 1 displays the first three goals and workstreams, first two ELT asks, and first seven relationships.
- Do not expose a generic JSON Patch surface. Permit only typed scalar `set` and atomic semantic-row `insert` or `update` operations from the deterministic helper allowlist.
- De-duplicate arrays by meaning, not array index.
- Leave `statusSummary` unchanged or blank unless four substantive evidence-backed lines satisfy the dashboard limits.
- Generate `statusSummary`; do not ask the user to write it. Gather only missing progress, risk/decision, and next-action inputs.
- Require evidence, mitigation, and owner when an approved proposal creates a Red health state.
- Allow a product forecast plan only for an existing source-backed Consumption Plan row. Update Q1–Q4 forecast and comments atomically; never touch purchased quantity, utilization, or utilization status.
- Treat starter Consumption Plan rows and unsubstantiated Green health defaults as unsupported.

## Source provenance

Keep raw evidence in the confidential ledger, which build never auto-deletes. Keep only the minimum excerpt required to understand a claim.

Each accepted item must retain in the confidential ledger:

- provider source type and stable locator;
- author and author kind;
- occurrence or modification date;
- content digest;
- account-match signals and rationale;
- claim class and authority;
- limitations and coverage gaps.

Append compact accepted-source references to `sourceNotes`. The external report must retain minimized accepted-source provenance—stable evidence ID, source type, claim class, authority, content digest, and non-sensitive date—plus search limitations, without source locators, raw bodies, private URLs, or unnecessary PII.
