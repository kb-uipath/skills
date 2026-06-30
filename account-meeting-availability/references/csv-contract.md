# CSV Contract

## Persistent Store

The backing contact CSV is an implementation detail. Store it outside the skill directory at:

```text
${CUSTOMER_EMAIL_STORE:-${CODEX_HOME:-~/.codex}/account-meeting-availability/contacts.csv}
```

Use `scripts/contact_store.py` for normal user-facing operations. Export a CSV only when the user asks for one.

## Required Columns

The persistent store and imported CSV files use these logical columns:

| Canonical header | Required | Purpose |
| --- | --- | --- |
| `account name` | yes | Customer account, agency, company, or organization name used to scope searches. |
| `record type` | no | `customer` or `uipath`; defaults to `customer` for older CSVs. |
| `customer name` | yes | Person name to source or verify, including UiPath team members. May be blank only when the user wants account-level discovery. |
| `customer role` | yes | Role/title/function, such as CIO, program manager, sponsor, contracting officer, AE, TAM, or solution engineer. |
| `customer email address` | yes | Existing email if known; blank when sourcing is needed. |

## Header Normalization

Accept case, whitespace, underscore, and hyphen variations. Examples:

- `Account Name`, `account_name`, `account-name` -> `account name`
- `Record Type`, `type`, `participant type`, `UiPath or Customer` -> `record type`
- `Customer Email`, `Customer Email Address`, `email` -> `customer email address`

Reject the CSV if any logical required column other than `record type` cannot be found. Normalize `record type` values to `customer` or `uipath`.

## Output Columns

Append these columns for sourced output:

| Column | Values |
| --- | --- |
| `sourced customer email address` | Best candidate email, or blank if none found. |
| `sourcing confidence` | `provided`, `high`, `medium`, `low`, or `none`. |
| `sourcing evidence` | Short evidence summary with subject/date/person context; avoid unnecessary mailbox details. |
| `source type` | `outlook-email`, `outlook-calendar`, `provided-csv`, `inferred`, or `none`. |
| `source date` | ISO date if available. |
| `needs review` | `yes` or `no`; default `yes` unless evidence is high confidence or already provided. |

## Matching Guidance

Treat a filled `customer email address` as user-provided truth unless the user asks for verification. For missing addresses, search by exact customer name first, then account name plus role, then account/domain patterns. Exclude internal domains for `customer` records. Include `@uipath.com` as valid for `uipath` records.
