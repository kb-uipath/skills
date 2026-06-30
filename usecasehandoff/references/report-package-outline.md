# Use Case Handoff Artifact Outline

Use this outline when the user asks for a full delivery-team handoff package. Keep file names stable unless the user requests a different format.

## Artifact Folder

Create a dated folder:

`artifacts/<customer_or_program>_<use_case_slug>_<yyyymmdd>/`

Recommended files:

- `README.md`
- `01_executive_summary.md`
- `02_analysis_output.md`
- `03_source_citations.md`
- `04_cover_message.md`
- `05_delivery_team_handoff_report.md`
- `06_download_and_reference_links.md`

Create a ZIP at the workspace root or beside the artifact folder when the user asks to send, upload, or provide a downloadable packet.

## README.md

State the package purpose, intended audience, contents, and recommended reading order. Include the generated date and whether metrics are source-backed, derived, or estimated.

## 01_executive_summary.md

Use these sections:

- Business problem
- Impact and metrics
- High-level solution workflow
- Executive ask

Keep this concise enough for an RVP or account lead. Do not bury the value proposition.

## 02_analysis_output.md

Use these sections:

- Use case identity
- Stakeholders and audience
- Current-state process
- Pain points
- Systems and data touched
- Known volumes, cycle times, and financial impact
- Baseline assumptions and open questions

## 03_source_citations.md

Use a table or concise bullets with:

- Claim or metric
- Source title
- Source type: email, Slack, Teams, SharePoint, Drive, local file, public web, vendor docs
- Date or retrieval date
- Link or local path
- Confidence: high, medium, low

Include a separate section for unsupported or partially supported claims.

## 04_cover_message.md

Write a short post-ready or email-ready message:

- What is attached
- Why it matters
- What the recipient should do next
- Any caveats about source coverage or open assumptions

Do not over-explain the use case in the cover message.

## 05_delivery_team_handoff_report.md

Use these sections:

- Purpose and outcome
- Current-state workflow
- Target-state enterprise workflow
- Recommended architecture
- Data, queues, and exception model
- Security, credentials, access, and audit requirements
- Monitoring, reporting, and support model
- AI/UiPath AI Unit opportunities
- Implementation phases
- Acceptance criteria
- Test strategy
- Risks, dependencies, and decisions needed
- Backlog and next actions

For enterprise hardening, cover queue-based design, config management, credential handling, role-based access, audit logging, retry strategy, business exceptions, system exceptions, alerts, runbooks, deployment environments, and rollback.

## 06_download_and_reference_links.md

Include:

- Local artifact paths
- SharePoint/Drive/file links
- Source thread links where available
- Public documentation links
- Vendor documentation links
- Any unavailable source names that still need retrieval

## Minimum Acceptance Criteria

Before finalizing:

- Every metric is cited or labeled as an estimate.
- The delivery team can identify the first implementation phase.
- AI opportunities are separated from deterministic automation.
- Open questions are explicit and assigned where possible.
- The artifact package has been listed or ZIP-tested.
- Any upload or message send has been verified in the destination.
