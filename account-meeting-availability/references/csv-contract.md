# Contact CSV Contract

## Persistent Store Version 2.0

The private backing store is:

```text
${CUSTOMER_EMAIL_STORE:-${CODEX_HOME:-~/.codex}/account-meeting-availability/contacts.csv}
```

Schema `2.0` consists of:

- `contacts.csv`: canonical contact rows.
- `contacts.csv.metadata.json`: schema name, schema version, storage format, creation time, and migration provenance.
- `contacts.csv.lock`: transient lock directory while a command is reading or writing the store.

The CSV and metadata files are written atomically and restricted to the current user (`0600`) on POSIX systems. Newly created private parent and lock directories use `0700`. The lock directory uses atomic directory creation so independent Python processes coordinate on Windows, macOS, and Linux without platform-specific file-lock APIs.

Do not open the persistent CSV as a spreadsheet. Formula-like values are deliberately stored raw. Formula guards are added only to `export` output and `list --format csv` so the persistent value does not acquire repeated apostrophes.

## Schema Metadata And Migration

The metadata sidecar declares:

```json
{
  "schema": "account-meeting-availability/contact-store",
  "schema_version": "2.0",
  "storage_format": "csv",
  "created_at": "2026-07-10T14:00:00Z",
  "migration": null
}
```

A migrated store replaces `migration: null` with `from_schema_version=legacy-unversioned` and an RFC 3339 migration time. A CSV without metadata is never modified automatically. Back it up and run:

```bash
python3 scripts/contact_store.py --store /path/to/contacts.csv migrate
```

Migration accepts legacy alias headers and a missing `record type`, which defaults to `customer`. It fails without changing the original when rows contain malformed email addresses, invalid record types, duplicate scoped identities, or missing required headers. Metadata from an unsupported version also fails closed; use a compatible skill release instead of editing the version marker.

## Canonical Columns

| Canonical header | Required header | Purpose |
| --- | --- | --- |
| `account name` | yes | Agency, company, or organization used as an identity and search scope. |
| `record type` | no for legacy import | `customer` or `uipath`; defaults to `customer` only when absent from a legacy/import CSV. |
| `customer name` | yes | Person name, including UiPath team members. A blank value is reserved for explicit account-level discovery. |
| `customer role` | yes | Role, title, or function. The value may be blank. |
| `customer email address` | yes | Practical mailbox address, or blank while sourcing is required. |

Imports accept case, whitespace, underscore, and hyphen header variations. Examples:

- `Account Name`, `account_name`, `account-name` -> `account name`
- `Record Type`, `type`, `participant type`, `UiPath or Customer` -> `record type`
- `Customer Email`, `Customer Email Address`, `email` -> `customer email address`

Duplicate logical headers are rejected.

## Scoped Identity Matching

Contact matching is limited to the normalized pair `account name` plus `record type`. Within that scope, an exact nonblank contact name or exact nonblank email can update the existing row. The same email under another account or participant type is a separate record and cannot silently overwrite the first identity.

Two rows with the same normalized account, record type, and name are an ambiguous duplicate and fail closed. Resolve the duplicate through a reviewed edit or corrected import before retrying.

## Email Validation

Nonblank email values must use the common ASCII dot-atom mailbox form and a fully qualified DNS domain. The validator rejects spaces and control characters, multiple `@` characters, leading/trailing or consecutive dots in the local part, invalid domain labels, local-only domains, display-name forms, comments, quoted local parts, and address literals. Empty cells remain valid only for contact sourcing.

## Sourcing Output Columns

`prepare_customer_email_csv.py` appends:

| Column | Values |
| --- | --- |
| `sourced customer email address` | Best candidate, or blank. |
| `sourcing confidence` | `provided`, `high`, `medium`, `low`, or `none`. |
| `sourcing evidence` | Minimal evidence summary without unrelated mailbox content. |
| `source type` | `outlook-email`, `outlook-calendar`, `provided-csv`, `inferred`, or `none`. |
| `source date` | ISO date when available. |
| `needs review` | `yes` or `no`. |

Treat a provided, syntactically valid address as user-provided truth unless verification is requested. Customer records using `@uipath.com` and automated or distribution-style local parts remain review-required.

## Lock Recovery

Commands wait up to 10 seconds for `<store>.lock`; override with `--lock-timeout`. A timeout does not remove another process's lock. If a process crashed, inspect `<store>.lock/owner.json`, confirm that the recorded PID is no longer active, then remove only that lock directory. Never remove it while a store command is running.
