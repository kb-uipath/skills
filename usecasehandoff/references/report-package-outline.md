# Use Case Handoff Artifact Outline

Use this outline when the user asks for a full delivery-team handoff package. Keep file names stable unless the user requests a different format.

## Artifact Folder

Create a dated folder:

`artifacts/<yyyy-mm-dd>-<use-case-slug>/`

Required stable files for schema `usecasehandoff.package` version `1.0.0`:

- `README.md`
- `executive-summary.md`
- `analysis.md`
- `evidence-ledger.md`
- `delivery-plan.md`
- `risk-register.md`
- `references.md`
- `cover-message.md`
- `manifest.json`

Create a ZIP at the workspace root or beside the artifact folder when the user asks to send, upload, or provide a downloadable packet.

Do not add extra files to the package directory. Reference source attachments in `references.md` so manifest hashes continue to cover the stable package contract.

## README.md

State the package purpose, intended audience, contents, and recommended reading order. Include the generated date and whether metrics are source-backed, derived, or estimated.

## executive-summary.md

Use these sections:

- Business problem
- Impact and metrics
- High-level solution workflow
- Executive ask

Keep this concise enough for an RVP or account lead. Do not bury the value proposition.

## analysis.md

Cover the current state, verified pain points, systems and constraints, value drivers, assumptions, and validation questions. Link material claims to evidence IDs and keep assumptions visibly separate from facts.

## evidence-ledger.md

Use a table with:

- Claim ID
- Claim or metric
- Evidence tier: `Source-backed`, `Derived`, `Estimate`, or `Open`
- Source title/link
- Source date
- Owner
- Notes

Include `## Open Evidence Gaps`. Every non-open claim needs a source title/link and source date before ready validation.

## delivery-plan.md

Use these sections:

- Current-state process
- Target-state enterprise workflow
- Systems and integrations
- Data, queue, and exception model
- Security, credentials, access, and audit requirements
- Delivery phases with owner and acceptance criteria
- Test strategy
- First sprint backlog
- Next action

For enterprise hardening, cover queue-based design, config management, credential handling, role-based access, audit logging, retry strategy, business exceptions, system exceptions, alerts, runbooks, deployment environments, and rollback.

## risk-register.md

Track risk, impact, mitigation, owner, and status. Ready validation rejects ownerless risk rows.

## references.md

Include:

- Source names
- Source type: email, Slack, Teams, SharePoint, Drive, local file, public web, vendor docs
- Date or retrieval date
- Link or local path
- Claims supported
- `SHA-256` for every relative local source, or `N/A` for an HTTPS source
- Owner

Relative local sources must exist under the artifact output root and match the recorded lowercase SHA-256 before ready validation passes. Absolute local paths and paths that escape the output root fail closed. Every non-open evidence claim ID and source name must resolve to this table.

## cover-message.md

Write a short post-ready or email-ready message:

- What is attached
- Why it matters
- What the recipient should do next
- Any caveats about source coverage or open assumptions

It must include a concrete `Next action:` line before ready validation passes. Do not over-explain the use case in the cover message.

## manifest.json

The manifest records schema, schema version, title, account, package date, status, classification, retention, generated time, last verification time, stable file list, SHA-256 hashes for every non-manifest file, `no_send: true`, and the no-send/no-upload safety statement.

Supported statuses: `scaffold`, `draft`, `ready`, `routed`, `archived`.

Supported classifications: `public`, `internal`, `confidential`, `restricted`.

## Reference Handling

Include:

- Local artifact paths when they are stable and non-sensitive
- SharePoint/Drive/file links when authorized
- Source thread links where available
- Public documentation links
- Vendor documentation links
- Any unavailable source names that still need retrieval

## Minimum Acceptance Criteria

Before finalizing:

- Every metric is cited or labeled as an estimate.
- The delivery team can identify the first implementation phase.
- Every delivery phase, risk, and source row has an owner.
- Acceptance criteria, test strategy, first sprint backlog, and next action are populated.
- AI opportunities are separated from deterministic automation.
- Open questions are explicit and assigned where possible.
- Scaffold validation passes, manifest hashes are refreshed, and ready validation passes.
- Any upload or message send has been verified in the destination.
