---
name: account-meeting-availability
description: Source, validate, store, edit, and review account meeting contacts for both customer contacts and UiPath team members from a CSV or direct user-provided contact details. Use when the user provides or references an account/contact CSV, asks to add or edit customer or UiPath contacts, asks Codex to maintain an account contact book, fill missing email addresses, verify account contacts, prepare meeting attendees, or identify likely emails from Outlook Email/Calendar evidence without sending messages automatically.
---

# Account Meeting Availability

## Overview

Use this skill to maintain a private account contact store for both customer contacts and UiPath team members. Treat recipient discovery as evidence gathering, not as permission to send external email.

## Contact Store

Store persistent contacts outside the skill folder at:

```text
${CUSTOMER_EMAIL_STORE:-${CODEX_HOME:-~/.codex}/account-meeting-availability/contacts.csv}
```

Use `scripts/contact_store.py` so the user can add, edit, import, list, and export contacts without manually opening the CSV. Do not ask the user to edit this CSV directly unless they explicitly want raw file access.

## Input Options

Accept either direct contact details from chat or a CSV.

For direct entry, collect only the missing fields needed for:

- `account name`
- `record type` (`customer` or `uipath`; default to `customer` for older CSVs)
- `customer name` (person name, including UiPath team members)
- `customer role` (role/title/function)
- `customer email address`

Then run `scripts/contact_store.py add ...` or `scripts/contact_store.py edit ...`. Use `--record-type uipath` for UiPath team members.

For CSV import or export, use the same logical headers.

## CSV Input

Require a CSV with these logical headers:

- `account name`
- `record type`
- `customer name`
- `customer role`
- `customer email address`

Header matching may be case-insensitive and tolerate punctuation/spacing differences, but the normalized output must use the exact headers above. `record type` is optional for backward compatibility and defaults to `customer` when absent. Read `references/csv-contract.md` when implementing or troubleshooting CSV normalization.

## Workflow

1. Decide whether the user is adding/editing stored contacts, importing/exporting the contact store, or sourcing missing emails.
2. For direct add/edit requests, use `scripts/contact_store.py`; do not expose the backing CSV unless needed.
3. For CSV import, validate and normalize with `scripts/prepare_customer_email_csv.py`, then import with `scripts/contact_store.py import`.
4. Preserve every original row and value. Do not overwrite a provided `customer email address` unless the user explicitly asks for verification or correction.
5. For rows with missing or uncertain email addresses, gather evidence from connected Microsoft context, preferring:
   - Outlook Email search results containing the customer name, account name, email domain, role, or thread participants.
   - Outlook Calendar attendees for meetings tied to the account or customer name.
   - Recent threads over old threads when evidence quality is otherwise equal.
6. Exclude obvious internal senders for `customer` records, especially `@uipath.com`. Allow `@uipath.com` for `uipath` records. Always exclude automated/no-reply addresses, bounce addresses, listservs, and generic ticketing systems unless the user explicitly wants distribution lists.
7. Rank candidates with evidence. Never silently choose a recipient for an external send unless the match is high confidence and the user asked to proceed.
8. Return or write a reviewable output with the original five columns plus sourcing columns:
   - `sourced customer email address`
   - `sourcing confidence` (`provided`, `high`, `medium`, `low`, or `none`)
   - `sourcing evidence`
   - `source type`
   - `source date`
   - `needs review`

## Evidence Rules

Prefer exact person evidence over account-only evidence:

- High confidence: exact customer name appears with the candidate email in sender, recipient, attendee, or signature context, and the domain matches the account or known customer domain.
- Medium confidence: name and account are linked in the same thread or meeting, but the email/name pairing is indirect.
- Low confidence: only account/domain or role-level evidence is present.

If multiple candidates remain plausible, leave `customer email address` unchanged, put the best candidate in `sourced customer email address`, set `needs review` to `yes`, and explain the ambiguity.

For meeting availability, include both `customer` and `uipath` records attached to the account unless the user narrows the audience.

## Safety

- Do not send email from this skill.
- Do not create Outlook drafts with sourced recipients unless the user explicitly asks after reviewing the candidates.
- Do not expose unrelated mailbox content. Quote or summarize only the minimal evidence needed to justify the candidate.
- Do not infer a customer email from naming convention alone unless the output clearly marks it as low confidence and needing review.

## Useful Commands

Show the backing contact store path:

Run helper commands from the `account-meeting-availability/` skill directory, or replace `scripts/...` with the equivalent path in your checkout.

```bash
python3 scripts/contact_store.py path
```

Add or update a contact from user-provided details:

```bash
python3 scripts/contact_store.py add --account "SSA" --record-type customer --name "Jane Doe" --role "Program lead" --email "jane.doe@example.gov"
```

Add a UiPath team member:

```bash
python3 scripts/contact_store.py add --account "SSA" --record-type uipath --name "UiPath Teammate" --role "TAM" --email "teammate@uipath.com"
```

Edit exactly one matching contact:

```bash
python3 scripts/contact_store.py edit --match-name "Customer Contact" --email "new.address@example.gov"
```

List contacts without opening the CSV:

```bash
python3 scripts/contact_store.py list --account "SSA"
```

List only UiPath team members for an account:

```bash
python3 scripts/contact_store.py list --account "SSA" --record-type uipath
```

Import contacts into the hidden store:

```bash
python3 scripts/contact_store.py import contacts.csv
```

Export the contact store only when the user asks for a CSV artifact:

```bash
python3 scripts/contact_store.py export --output contacts-export.csv
```

Validate and normalize a CSV:

```bash
python3 scripts/prepare_customer_email_csv.py input.csv --output normalized.csv
```

Create a template CSV:

```bash
python3 scripts/prepare_customer_email_csv.py --template template.csv
```
