# account-meeting-availability

Manage private account contacts and rank common meeting slots from normalized, read-only Outlook free/busy evidence. The skill does not create meetings, drafts, invitations, email, Slack messages, Teams messages, or external-system records.

## When To Use

Use this skill to:

- add, edit, delete, import, list, or export customer and UiPath account contacts
- normalize a contact CSV and flag missing or suspicious addresses for review
- prepare the customer and UiPath participant set for an account meeting
- deterministically rank common slots after Outlook free/busy intervals have been collected through a read-only connector operation

Do not use it as a scheduling or messaging workflow. A ranked result is a review artifact only.

## Inputs

- Direct contact details or a CSV with account, record type, name, role, and email columns.
- Optional contact store path through `--store` or `CUSTOMER_EMAIL_STORE`.
- For ranking, a free/busy request JSON conforming to schema version `1.0` and populated only from read-only Outlook schedule evidence.
- Explicit required/optional participant classification, IANA time zones, local working hours, and offset-aware intervals.

## Prompt

```text
Use $account-meeting-availability to maintain the account contacts and rank common meeting slots from read-only Outlook free/busy evidence. Return a reviewable result only. Do not create meetings, drafts, invitations, or messages.
```

## Runtime And Dependencies

- Python 3.9 or later.
- Python standard library only; no package installation is required.
- `zoneinfo` plus an installed IANA time zone database for availability ranking.
- Read-only Outlook connector access is optional and upstream of the CLI. The scripts make no network or connector calls.
- Local filesystem access is required for contact storage and optional JSON/CSV outputs.

On Windows systems without IANA time zone data, install time zone data according to the organization's managed Python policy or normalize and rank in an environment that provides it. Windows Outlook time zone names such as `Eastern Standard Time` must be converted to IANA names such as `America/New_York` before ranking.

## Versioned Inputs And Outputs

### Contact Store 2.0

The persistent store defaults to:

```text
${CUSTOMER_EMAIL_STORE:-${CODEX_HOME:-~/.codex}/account-meeting-availability/contacts.csv}
```

It has five canonical CSV columns: `account name`, `record type`, `customer name`, `customer role`, and `customer email address`. Schema metadata is stored in `<store>.metadata.json` with schema `account-meeting-availability/contact-store` and version `2.0`.

The CSV and metadata are atomically replaced and restricted to the current user (`0600`) where POSIX permissions are supported. `<store>.lock` provides process coordination through atomic directory creation. Contact identity matching is scoped by account and record type, so the same email cannot merge unrelated account/type identities.

Existing unversioned CSV stores do not auto-upgrade. They fail closed with an explicit migration command. Formula-like values remain raw in the private store and receive a leading apostrophe only in exported CSV or CSV stdout.

### Free/Busy Request 1.0

Reference schema: `account-meeting-availability/references/schemas/free-busy-request-v1.schema.json`.

The request contains a bounded offset-aware window, slot duration and increment, unique required/optional participants, IANA time zones, same-day local working hours, Outlook free/busy intervals, and source provenance fixed to `provider=outlook` and `retrieval_mode=read-only`.

### Free/Busy Result 1.0

Reference schema: `account-meeting-availability/references/schemas/free-busy-result-v1.schema.json`.

The result is deterministic for identical input. Required-participant conflicts are excluded. Remaining slots are ranked by optional attendance descending and UTC start ascending. Each slot includes UTC timestamps and participant-local timestamps. No result timestamp or generated ID is added.

`status=no_common_slot` with an empty `ranked_slots` array is a valid successful outcome. It does not authorize dropping participants or widening constraints.

## Runnable Example

From the repository root:

```bash
python3 account-meeting-availability/scripts/rank_meeting_slots.py \
  account-meeting-availability/tests/fixtures/free_busy_rankable_v1.json \
  --output /tmp/ranked-slots.json
```

The fixture produces three ranked results. Its first result is `2026-07-15T16:00:00Z`, rendered as noon in New York, 11:00 in Chicago, and 09:00 in Los Angeles.

Initialize and use a temporary contact store:

```bash
python3 account-meeting-availability/scripts/contact_store.py \
  --store /tmp/account-contacts.csv init
python3 account-meeting-availability/scripts/contact_store.py \
  --store /tmp/account-contacts.csv add \
  --account "SSA" --record-type customer --name "Jane Doe" \
  --role "Program lead" --email "jane.doe@example.gov"
python3 account-meeting-availability/scripts/contact_store.py \
  --store /tmp/account-contacts.csv list --format json
```

## Failure Recovery

### Legacy Store

If the CLI reports `Legacy unversioned contact store`, back up the local CSV and run:

```bash
python3 account-meeting-availability/scripts/contact_store.py \
  --store /path/to/contacts.csv migrate
```

Migration validates the entire file before replacing it. Malformed emails, duplicate scoped identities, missing headers, and invalid record types must be corrected in a backed-up copy before retrying. Never fabricate or hand-edit the metadata version to bypass validation.

### Lock Timeout

The default lock timeout is 10 seconds. If a timeout persists, inspect `<store>.lock/owner.json`. Confirm the recorded PID is no longer active before removing only `<store>.lock`; removing an active lock risks lost updates. Increase the wait with global option `--lock-timeout SECONDS` when another legitimate command is still running.

### Missing Or Unsupported Metadata

If metadata exists without its CSV, restore the matching CSV from a trusted backup or remove both files and initialize a new empty store. If the metadata schema/version is unsupported, use the compatible skill release or an approved migration. Do not edit the CSV under an unknown schema.

### Invalid Availability Input

Correct the named field and rerun. Unknown fields, duplicate JSON keys, duplicate participant IDs/emails, timestamps without offsets, non-IANA time zones, non-read-only source metadata, and unsupported schema versions all fail closed. The CLI never falls back to guessed availability.

## Safety

- Never create, update, accept, decline, or cancel a meeting.
- Never send or draft email, Slack, Teams, or other external messages.
- Never treat a sourced address or ranked slot as authorization for an external write.
- Minimize mailbox evidence and do not expose unrelated message or calendar content.
- Use temporary `--store` paths for tests. Do not touch the user's persistent store unless the request requires contact management.
- Keep ambiguous addresses review-required and incomplete free/busy evidence unresolved.

## Data Classification And Retention

Classify contact names, email addresses, roles, working hours, and free/busy intervals as confidential personal and scheduling data. They may expose reporting relationships, customer associations, and absence patterns even when no event subjects are present.

- Store only the minimum contact and availability data needed for the active account workflow.
- Review persistent account contacts at least quarterly and remove stale records.
- Delete transient free/busy request and result files after meeting coordination; 30 days is the recommended maximum absent a stricter policy.
- Do not place these artifacts in source control, shared logs, issue text, or broadly accessible folders.
- The scripts do not implement automatic deletion, legal hold, backup, encryption at rest, or enterprise records management. Organizational policy takes precedence.

## Known Limitations

- The skill ranks supplied evidence; it does not query Outlook itself.
- Availability becomes stale as calendars change. Collect a fresh read-only snapshot before acting on old results.
- All non-`free` statuses, including tentative and working elsewhere, are treated as unavailable.
- Working hours cannot cross midnight. Holidays, travel time, rooms, recurrence, delegates, quorum rules, and per-date working-hour exceptions are not modeled.
- Search windows are limited to 31 days, requests to 100 participants and 1,000 intervals per participant, and results to 100 slots.
- Practical email validation intentionally rejects quoted local parts, comments, address literals, local-only domains, display-name forms, and non-ASCII addresses.
- POSIX `0600` and `0700` modes are best-effort on filesystems and operating systems with different permission models.
- CSV formula escaping protects exported values but cannot make arbitrary downstream spreadsheet macros or transformations safe.

## Certification Status

Repository-tested, not independently security-, privacy-, or compliance-certified. The targeted unit suite covers ranking, time zones, no-common-slot outcomes, concurrency, lock timeout, permissions, migration metadata, scoped duplicate identities, malformed email, and formula preservation/export. Production use still requires organizational security, privacy, Outlook connector, and retention review.

**Last verified:** 2026-07-10

## Validation

```bash
python3 -m unittest discover -s account-meeting-availability/tests -p 'test_*.py'
python3 tools/validate_repo.py
```
