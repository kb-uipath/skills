# Source playbooks

Per-source recipes for the evidence sweep. All access is read-only. Sweep newest first;
stamp every extracted fact with its date and locator (channel + ts, message subject +
date, page title, meeting title + date).

## Salesforce (SFDC)

Use the **`salesforce-account-profile`** skill's `pipeline` preset — read-only by
construction, with exact Account resolution and an explicit disambiguation stop when the
account name is ambiguous:

```
$salesforce-account-profile Give me a pipeline snapshot for <account name> in Production.
```

It returns the selected Account overview, open Opportunities, and owner hierarchy. Do not
use Glean's `salescloud` app filter for authoritative field values — that surface is
summarized, not schema-validated, and is secondary/discovery only (e.g. to spot an
account name variant before running the profile skill). Do not use
`salesforce-meddpicc-update` (write-capable, wrong shape for this read-only flow) or the
retired `sf`-CLI schema-1.4-era flow in `legacy/` — do not port that machinery here.

SFDC is strong for: Sales Plan pipeline `stage`/`estimatedIarrUsd`/`nextGateDate`, the
account team names for `background.region` and `accountTeam.*`, and confirming
`pipelineOpportunities[].owner`. It is weak or unusable for anything judgment- or
narrative-based: `background.accountStrategy`, `salesPlan.executionPlan`
(`day30`/`day60`/`day90`), `salesPlan.nextExecutiveMove`, `background.coreMotions[]`,
`renewalEconomics.assurance`, and any `relationships[].relationshipStatus` or MEDDPICC-style
role judgment. Flag these explicitly as candidates for the conversational interview agent
(the embedded assistant's interview mode) rather than guessing from SFDC data that doesn't
actually state them.

## Slack (public channels)

Tools: `slack_search_channels`, `slack_read_channel`, `slack_read_thread`,
`slack_search_public`.

Public channels only — do not use `slack_search_public_and_private` or read a private
channel for this flow; if the only relevant discussion lives in a private channel, note
the gap and ask the user rather than requesting private access.

1. Find the account channels: search for the account name and common patterns
   (`#<acct>`, `#ps-proj-<acct>`, `#<acct>-dealdesk`). Confirm ambiguous matches with
   the user.
2. Read recent history of each channel across the window; open threads on anything that
   states facts (renewal, owners, blockers, metrics, new stakeholders).
3. `slack_search_public` for the account's full name and key program terms to catch
   discussion outside the account channels.
4. Internal weeklies and "Big Rocks"-style posts are team attestations — usable for
   plans, owners, risks, health judgments. They can still be stale: a newer message in
   the same channel supersedes them.

## Outlook (mail + calendar)

Tools: `outlook_email_search`, `outlook_calendar_search`, `read_resource`.

1. Search mail for the account name, program acronyms, and stakeholder names from the
   baseline document, windowed to the sweep period.
2. Email signatures are the best identity source — use them to resolve nicknames and
   confirm roles before attributing facts.
3. Calendar is the evidence for `relationships[].cadence`: who actually meets whom, how
   often, and the meeting series name. A standing weekly beats a claimed cadence.
4. Customer-authored emails may establish external facts (their priorities, their
   blockers, their asks) — quote nothing verbatim; paraphrase.

## OneNote / SharePoint

Tools: Glean `search` (app filters `o365sharepoint`/`o365onedrive`), `sharepoint_search`,
`read_document`, `read_resource`.

1. Locate the account notebook/folder via Glean first; fall back to asking the user for
   the notebook name.
2. Check freshness before trusting: a notebook untouched for a year is background, not
   current evidence. Note staleness in the findings file.
3. Spreadsheets and decks in the account folder are often the richest source for
   entitlements, consumption plans, and pipeline inventories — record the file's
   last-modified date as the as-of date.

## Tribble Scribe (local call notes)

**Read [tribble-policy.md](tribble-policy.md) first, and get the user's consent every
run.**

Tool: `node scripts/tribble-read.mjs "<match>" [since-ISO-date] [--transcript]`
(Node 22+, uses `node:sqlite`).

1. The reader snapshots the live DB (db + `-wal` + `-shm`) to a temp dir, opens the
   snapshot read-only, queries `meetings ⨝ meeting_details` (and `transcript_entries`
   with `--transcript`), and deletes the snapshot. The live app is never touched.
2. Match by account name, program terms, and known participant names; window with the
   since date.
3. Meeting summaries and user notes are team-side records: usable for owners, status,
   blockers, plans, and explicitly stated judgments. Transcript lines attributed to
   customer speakers may establish customer facts — paraphrase only.
4. Nothing from Tribble leaves the machine: no quotes in the dashboard or report, no
   files committed anywhere.
