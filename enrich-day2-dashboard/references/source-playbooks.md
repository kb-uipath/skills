# Source playbooks

Per-source recipes for the evidence sweep. All access is read-only. Sweep newest first;
stamp every extracted fact with its date and locator (channel + ts, message subject +
date, page title, meeting title + date).

## Salesforce (SFDC) — system of record, query it first

**Salesforce is the system of record for basic account data. Query the Salesforce MCP
for every field it can authoritatively answer before sweeping Slack, Outlook, OneNote or
call notes.** Those sources carry judgment and narrative; they are not where a region,
an account-team name, a pipeline stage or a close date should come from. A Day 2 review
that disagrees with SFDC on basics is wrong in the way most likely to be noticed in
front of a customer or an exec.

Use these read tools on the Salesforce MCP, and only these — nothing in this flow writes
to Salesforce:

- `getObjectSchema` — call with no parameters for the object index, then with
  `Account,Opportunity` (etc.) for field detail. **Read its admin-authored guidance
  before choosing a field**: the org annotates which field is actually authoritative
  (for example "use `Calculated_ACV__c` instead of `Amount` for accurate forecasting").
  Taking the obvious-looking field over the annotated one is a silent accuracy bug.
- `soqlQuery` — the primary read. Always include `WHERE` and `LIMIT`, and filter on
  indexed fields (`Id`, `Name`, foreign keys, External IDs).
- `getRelatedRecords`, `listRecentSobjectRecords`, `find` — for child records, recent
  activity, and locating a record when the exact name is unknown.

**Resolve the account exactly, and stop if it is ambiguous.** Raw SOQL will happily
match the wrong account or several at once, so this guarantee is yours to enforce now
rather than something the tooling provides: query candidates by name, and if more than
one plausible Account comes back, stop and ask the user which one — never pick the first
row, and never merge two candidates' data. Record the resolved Account `Id` in the
findings file and filter every subsequent query on it.

**One customer, several accounts.** A Day 2 document can span more than one Salesforce
account (one customer can hold two accounts on two contracts). Resolve each
exactly and record each Id; use the primary account for the cover and account-team fields,
and group consumption rows by contract. Opportunities from every account feed the same
pipeline, so de-duplicate by name and close date before assigning `key`s. Entitlement and
subscription queries (`SBQQ__Subscription__c`, contracts, `ProductUsage__c`) belong to
`consumption-plan`, not to this sweep.

The **`salesforce-account-profile`** skill's `pipeline` preset remains available as a
secondary convenience when a packaged snapshot is wanted (it returns the Account
overview, open Opportunities and owner hierarchy, with its own disambiguation stop):

```
$salesforce-account-profile Give me a pipeline snapshot for <account name> in Production.
```

Prefer the MCP for basic account data; reach for the profile skill when you want that
curated shape or a second read on account resolution. Do not use Glean's `salescloud`
app filter for authoritative field values — that surface is summarized, not
schema-validated, and is secondary/discovery only (e.g. to spot an account name variant
before resolving the Account). Do not use `salesforce-meddpicc-update` (write-capable,
wrong shape for this read-only flow) or the retired `sf`-CLI schema-1.4-era flow in
`legacy/` — do not port that machinery here.

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

## Owner-authored working documents

Check the owner's own working folder for the account before the external sources: status
pages, weekly updates, planning workbooks and decks the account owner wrote. A dated
document the owner authored is an attributable account-team statement, which is what
`attest` fields need — but only for the sentences the owner wrote. A deck or tracker an
assistant drafted ("severities drafted for X to confirm") is not. Record the file's
last-modified date as the as-of date, and note who authored each part when it is mixed.

## Second-brain vault (local)

The owner's local LLM wiki, at the path the owner gives you.
Read-only in this flow; its `AGENTS.md` is its own schema, so skim the ownership and
page-contract sections before relying on a page.

1. Find the account page at `wiki/accounts/<id>.md` and the `wiki/people/`,
   `wiki/decisions/` and `wiki/contracts/` pages that link to it (`wiki/index.md` is the
   catalog; `python3 scripts/wiki.py search "<question>"` is a read-only ranked lookup).
2. **Check what it holds before using it.** Frontmatter `status: draft`, `sources: []` or a
   "No approved evidence has been compiled" body means the vault knows nothing about the
   account yet. That is a finding for the report, not evidence; its `health: unknown` is
   not a statement about the account.
3. What counts as evidence: compiled `wiki/` claims that cite a raw source (digest-bound
   `type: source` pages). Read the raw source for anything decisive. `ops/` pages are
   pointers and measurements, and `briefs/` are generated, disposable outputs: neither is
   ever cited. The `briefs/*-telemetry-*.md` files are the practical exception for
   locating the latest Power BI readings; cite the dashboard and its data-updated date, and
   say the brief is generated.
4. The vault is local-only by owner decision and forbids record-level content for some
   accounts (it can bar patient, beneficiary, member, claim, case and medical-record
   material). Keep to program-level facts, and treat a claim sourced from
   `call-notes://` as Tribble-derived: it needs the Tribble consent.
5. Never write to the vault from this flow.

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
