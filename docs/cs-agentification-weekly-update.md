# cs-agentification-weekly-update

Draft the weekly (or ad hoc) CS Agentification program update as Slack drafts for two
audiences from one underlying set of facts: local Tribble Scribe call recordings plus the
CS Agentification Confluence tracker. The skill never sends a Slack message -- it only
creates saved drafts for the user to review and send themselves.

## When To Use

Use this skill to:

- pull this week's (or a named) CS Agentification-related meeting from the local Tribble Scribe recording history
- cross-check that meeting against the program's Confluence status pages so the update reflects more than one call
- produce two audience-calibrated drafts -- an exec-brief version for `#cs-agentification` and a technical version for `#cs-agentification-program-leads` -- in the same brief bullet style
- create both as saved Slack drafts via `slack_send_message_draft`

Do not use it to send a Slack message directly, to extract or share a call involving an
external customer participant without confirming consent/approval first, or to persist raw
transcript content anywhere outside a local scratch location.

## Inputs

- Optional meeting title filter or explicit meeting ID (from `scripts/extract_tribble_meetings.py list`).
- The local Tribble Scribe database at `~/Library/Application Support/Tribble Desktop/tribble.db` (or `$TRIBBLE_DB_PATH`).
- Read access to the CS Agentification Confluence space (`CSA`) for the "Weekly Operating Log" and "Latest CS Agentification Status" pages, and to the target Slack channels, when available -- the skill still runs without these, with a narrower, Tribble-only view.
- Target channel IDs, defaulting to `C0B8533LJGK` (`#cs-agentification`) and `C0BRDSM6EHM` (`#cs-agentification-program-leads`); override via `CS_AGENTIFICATION_EXEC_CHANNEL_ID` / `CS_AGENTIFICATION_LEADS_CHANNEL_ID`.

## Prompt

```text
Use $cs-agentification-weekly-update to draft this week's CS Agentification program update as Slack drafts for #cs-agentification and #cs-agentification-program-leads. Never send -- create drafts only.
```

## Runtime And Dependencies

- Python 3.11 or later. Standard library only (`sqlite3`, `argparse`, `itertools`, `tempfile`, `json`) -- no package installation required.
- Local Tribble Scribe app data, present only on the machine where Tribble Scribe recorded the calls (macOS).
- A Slack MCP connection exposing `slack_send_message_draft` to create the drafts. No send-message permission is needed or used.
- Optional: Confluence/Glean read access for the cross-check step; degrades gracefully to Tribble-only context if unavailable.

## Versioned Inputs And Outputs

### Meeting Record 1.0

Returned by `scripts/extract_tribble_meetings.py get <id> [--transcript] [--json]`:
`id`, `title`, `date`, `platform`, `participants` (display names only, no email/domain
data), `summary_markdown`, and `transcript_markdown` (present only when `--transcript` is
passed; consecutive same-speaker rows are merged into one paragraph).

### Channel Draft Contract 1.0

Each Slack draft call is `channel_id` (string) + `message` (Slack markdown, following the
skeleton in `references/message-templates.md`), passed to `slack_send_message_draft`. The
tool's own response contract returns a `channel_link`; this skill hands that link back to
the user rather than treating draft creation as a terminal, unreviewed action.

## Runnable Example

From the repository root:

```bash
python3 cs-agentification-weekly-update/scripts/extract_tribble_meetings.py list --days 7
python3 cs-agentification-weekly-update/scripts/extract_tribble_meetings.py get <meeting-id> --transcript
```

Against the unit-test fixture (no real Tribble data required):

```bash
python3 -m unittest discover -s cs-agentification-weekly-update/tests -p 'test_*.py'
```

## Failure Recovery

### Tribble database not found

`list`/`get` raise a clear error naming the expected path. Open Tribble Scribe and let it
sync at least once, or pass `--db` / set `TRIBBLE_DB_PATH` if it lives somewhere non-default.

### A likely external participant

If a name in the `participants` list doesn't look like an internal colleague, stop before
running `get --transcript` on that meeting. Confirm current consent/approval status with
the user first; there is no automatic way to detect this from the stored data.

### `draft_already_exists` / `channel_not_found` from `slack_send_message_draft`

This MCP server has no edit/delete-draft tool, so a second draft in the same channel fails
-- sometimes surfacing as `channel_not_found` instead of the documented `draft_already_exists`.
Do not keep retrying the same call. Tell the user a draft already exists, give them the new
text to paste in manually, and offer to retry once they've cleared or sent the existing one.

## Safety

- Tribble Scribe is not an approved TAM tool. Treat every summary and transcript as confidential.
- Extract only internal (non-customer) meetings without further review. Any external participant requires a consent/approval check before extraction.
- Never write to the live Tribble database; every read runs against a temporary, automatically-deleted snapshot.
- Never call `slack_send_message_draft`'s sibling send tool from this workflow -- drafts only. Sending is always the user's own action.
- Never commit meeting summaries, transcripts, or participant lists to any repository, including this one.

## Data Classification And Retention

- Classify Tribble summaries and transcripts as confidential (customer-confidential when the meeting involves one).
- Keep any locally saved extraction output in a scratch/temporary location outside a git working tree; delete it once the draft is produced unless the user asks to keep it.
- Do not place transcript or summary content in source control, shared logs, ticket text, or this skill's own reference files -- reference files describe the *method*, not real meeting content.
- The scripts implement no automatic deletion, backup, or enterprise records management beyond the temp-snapshot cleanup described above; organizational policy takes precedence.

## Known Limitations

- Participant records store display names only, not email domains, so internal-vs-external detection is a manual judgment call, not automatic.
- Can only surface a meeting that Tribble Scribe actually recorded and synced; it cannot recover one that wasn't captured.
- The Confluence/Slack cross-check step depends on connector access in the current session; without it, the draft reflects only the Tribble call content.
- Only one attached Slack draft is allowed per channel at a time (a limitation of the Slack draft tool itself, not this skill) -- see Failure Recovery above.

## Certification Status

This skill has not yet gone through the repository's formal production-readiness
evaluation (see `production-readiness-evaluation.md`). Its deterministic extraction logic
(read-only snapshotting, transcript speaker-merging, participant-name parsing) has unit
test coverage under `tests/`; the drafting and cross-check steps are judgment-based and are
not independently scored.

**Last verified:** 2026-08-28

## Validation

```bash
python3 -m unittest discover -s cs-agentification-weekly-update/tests -p 'test_*.py'
python3 tools/validate_repo.py
```
