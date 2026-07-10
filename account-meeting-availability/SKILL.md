---
name: account-meeting-availability
description: Manage versioned account contact records and deterministically rank meeting slots from read-only Outlook free/busy evidence without creating meetings or sending messages. Use when a user provides an account contact CSV, asks to add or edit customer or UiPath contacts, needs missing emails reviewed, wants account attendees prepared, or asks for common availability across customer and UiPath participants.
---

# Account Meeting Availability

## Overview

Use this skill to maintain a private account contact store and produce reviewable meeting-slot recommendations. Contact management is local. Availability collection is read-only. The skill never creates calendar events, drafts, messages, or invitations.

## Contact Store

Store persistent contacts outside the skill folder at:

```text
${CUSTOMER_EMAIL_STORE:-${CODEX_HOME:-~/.codex}/account-meeting-availability/contacts.csv}
```

Use `scripts/contact_store.py` for add, edit, delete, import, list, and export operations. Contact store schema `2.0` keeps the canonical CSV plus a `<store>.metadata.json` sidecar. Store commands coordinate through `<store>.lock`, replace files atomically, and restrict contact data and metadata to the current user where the operating system supports POSIX-style permissions.

Do not edit the backing CSV or metadata directly. An existing CSV without metadata is a legacy unversioned store and fails closed. Back it up, then run the explicit `migrate` command. Migration validates headers, scoped identities, record types, and email syntax before changing the file.

## Contact Inputs

Accept direct contact details or an import CSV. Collect only the fields needed for:

- `account name`
- `record type` (`customer` or `uipath`; legacy imports default to `customer`)
- `customer name`
- `customer role`
- `customer email address`

Nonblank email addresses must be practical ASCII mailbox addresses with a fully qualified domain. Display-name forms, quoted addresses, whitespace, address literals, malformed domains, and multiple `@` characters are rejected.

CSV header matching may be case-insensitive and tolerate punctuation or spacing differences, but normalized output uses the exact canonical headers. Read `references/csv-contract.md` for the complete storage and migration contract.

## Contact Workflow

1. Decide whether the user is adding or editing stored contacts, importing or exporting, or sourcing missing emails.
2. Use `scripts/contact_store.py`; do not expose or edit the backing files unless recovery requires it.
3. Import the original CSV with `scripts/contact_store.py import`, which validates and normalizes it directly. Use `scripts/prepare_customer_email_csv.py` only when a reviewable, formula-guarded CSV artifact is needed; do not treat that export artifact as lossless storage.
4. Match identities within `account name` plus `record type`. The same email in another account or participant type is a separate identity and must not overwrite an existing record.
5. Preserve provided email values unless the user explicitly asks for verification or correction.
6. For missing or uncertain addresses, gather minimal evidence from connected Outlook Email or Calendar context. Prefer exact person evidence over account-only evidence.
7. Exclude `@uipath.com` for `customer` records and allow it for `uipath` records. Exclude automated, bounce, listserv, ticketing, and generic distribution addresses unless the user explicitly requests one.
8. Leave ambiguous candidates review-required. Never use a sourced address as permission to send.

## Availability Input

Use the version `1.0` request contract at `references/schemas/free-busy-request-v1.schema.json`. Build it only from Outlook schedule/free-busy information obtained through a read-only connector operation. The normalized request includes:

- an offset-aware search window of no more than 31 days
- duration, increment, and result limit
- unique participant IDs and emails, plus optional privacy-safe display names
- required or optional status
- an installed IANA time zone and same-day working hours for each participant
- half-open free/busy intervals with an Outlook status
- source metadata with `provider=outlook` and `retrieval_mode=read-only`

Include both `customer` and `uipath` contacts for the account unless the user narrows the audience. Do not infer missing free/busy data as availability. A participant with unavailable or incomplete evidence must be resolved before ranking.

## Availability Ranking

Run `scripts/rank_meeting_slots.py` with the normalized request. The CLI performs no network calls.

1. Generate candidates from the window start at the requested increment.
2. Reject a candidate outside any required participant's local working hours.
3. Reject a candidate overlapping any non-`free` interval for a required participant. `tentative`, `busy`, `out_of_office`, `working_elsewhere`, and `unknown` all block required attendance.
4. Rank remaining candidates by optional participants available, descending.
5. Break ties by earliest UTC start.
6. Return version `1.0` result JSON with display labels, privacy-safe optional-attendee unavailability reasons, and bounded exclusion diagnostics. Email addresses never appear in the result. `no_common_slot` is a valid result, not permission to relax constraints.

Read `references/availability-contract.md` for the full deterministic contract and limitations.

## Evidence Rules

- High confidence: exact contact name and email are linked in sender, recipient, attendee, or signature context and the domain matches the account.
- Medium confidence: name and account are linked in the same thread or meeting, but the address pairing is indirect.
- Low confidence: only account, domain, naming convention, or role evidence is present.

If multiple candidates remain plausible, keep the stored email unchanged, place the best candidate in the sourced output, set `needs review=yes`, and describe the ambiguity with minimal mailbox detail.

## Safety And Retention

- Never send email or messages, create drafts, create or modify meetings, respond to invitations, or write to external systems.
- Treat contacts, email addresses, roles, working hours, and free/busy intervals as confidential personal and scheduling data.
- Store only active account contacts. Review the persistent contact store at least quarterly and remove contacts no longer needed for the account relationship.
- Delete transient free/busy requests and ranking results after the meeting is coordinated, with 30 days as the recommended maximum unless policy requires a shorter period.
- The scripts do not delete retained data automatically. Follow the user's organizational retention and legal-hold rules.
- CSV formula guards are applied only to exports and CSV stdout. The private persistent store keeps normalized raw values so repeated exports do not corrupt data.

## Commands

Run commands from the `account-meeting-availability/` directory.

```bash
python3 scripts/contact_store.py path
python3 scripts/contact_store.py init
python3 scripts/contact_store.py migrate
```

Add and edit contacts:

```bash
python3 scripts/contact_store.py add --account "SSA" --record-type customer --name "Jane Doe" --role "Program lead" --email "jane.doe@example.gov"
python3 scripts/contact_store.py edit --match-account "SSA" --match-record-type customer --match-name "Jane Doe" --role "Program owner"
```

List, import, and export:

```bash
python3 scripts/contact_store.py list --account "SSA" --format json
python3 scripts/contact_store.py import input.csv
python3 scripts/prepare_customer_email_csv.py input.csv --output review-output.csv
python3 scripts/contact_store.py export --output contacts-export.csv
```

Rank captured read-only availability:

```bash
python3 scripts/rank_meeting_slots.py tests/fixtures/free_busy_rankable_v1.json --output ranked-slots.json
```

Review the result with the user. Stop there unless the user separately invokes an approved scheduling workflow outside this skill.
