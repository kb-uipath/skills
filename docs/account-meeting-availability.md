# account-meeting-availability

Manage account meeting contact records for customer contacts and UiPath team members.

## When To Use

Use this skill when a user provides a contact CSV, asks to build or maintain an account contact book, wants missing customer emails flagged for sourcing, or needs meeting-attendee contact data prepared without sending messages.

## Inputs

- Account name or contact CSV.
- Contact type: `customer` or `uipath`.
- Contact name, role/title, and email when known.
- Optional store path through `--store` or `CUSTOMER_EMAIL_STORE`.
- Optional connector evidence from Outlook Calendar or Email when the user asks to source emails.

## Prompt

```text
Use $account-meeting-availability to normalize this account contact CSV, flag missing or suspicious emails for review, and prepare an updated contact store. Do not send messages or modify calendars.
```

## Outputs

- Normalized CSV with canonical contact columns and review flags.
- Contact store add/edit/list/import/export operations.
- Clear review status for missing email addresses and customer rows that contain internal UiPath-domain addresses.

## Safety

- Do not send email, calendar invites, Slack, Teams, or CRM updates from this skill.
- Treat customer contact data as sensitive personal data; only store the minimum fields in the CSV contract.
- Use temp `--store` paths in tests and dry runs. Do not touch a real Codex home contact store unless the user explicitly requests it.
- Mark ambiguous candidates or low-confidence sourced emails as `needs review=yes`.

## Validation

```bash
python3 -m unittest discover -s account-meeting-availability/tests -p 'test_*.py'
python3 tools/validate_repo.py
```
