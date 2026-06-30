# account-meeting-availability

## Purpose

Source, validate, store, edit, and review account meeting contacts for both customer contacts and
UiPath team members from a CSV or direct user-provided contact details.

## When to use

Source, validate, store, edit, and review account meeting contacts for both customer contacts and
UiPath team members from a CSV or direct user-provided contact details. Use when the user provides
or references an account/contact CSV, asks to add or edit customer or UiPath contacts, asks Codex to
maintain an account contact book, fill missing email addresses, verify account contacts, prepare
meeting attendees, or identify likely emails from Outlook Email/Calendar evidence without sending
messages automatically.

## Required inputs

- Account name and meeting purpose.
- CSV path or direct contact details for customer and UiPath attendees.
- Which contacts to add, verify, edit, or prepare.
- Allowed evidence sources for email or attendee validation.

## Prompt template

```text
Use $account-meeting-availability to <desired outcome>.

Context:
- Target/account/project: <name or path>
- Source files or IDs: <paths, URLs, record IDs, job IDs, or screenshots>
- Constraints: <deployment context, read-only/write intent, timeline, output format>
- Acceptance criteria: <how to know the work is done>
```

## Example prompt

```text
Use $account-meeting-availability to validate the contacts in ./contacts.csv for the Acme QBR, fill missing emails from Outlook evidence, and produce the final attendee list without sending messages.
```

## Expected output

A task-specific result that follows the skill's `SKILL.md` instructions, cites or references the evidence used, and calls out assumptions, blockers, and verification steps. For write-capable UiPath or Salesforce skills, expect explicit read-before-write behavior and confirmation where the skill requires it.

## Source files

- Skill instructions: [`../account-meeting-availability/SKILL.md`](../account-meeting-availability/SKILL.md)
- Bundled references, templates, scripts, and assets live under [`../account-meeting-availability/`](../account-meeting-availability/) when present.
