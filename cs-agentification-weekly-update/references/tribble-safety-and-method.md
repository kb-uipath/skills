# Tribble Scribe: safety and extraction method

This mirrors the org's Tribble Scribe guidance
(`docs/systems/tribble/tribble-scribe-call-notes.md` in the CustomerEngineeringRepo). Read
it there for the authoritative version; this file exists so the skill doesn't depend on
live access to that SharePoint site to remember the rules.

## Approval and consent status

Tribble Scribe was introduced mid-2026 but deliberately held back from general rollout
pending legal review. It is **not** an approved or mandated TAM tool. Open concerns:
recording/consent law (stricter in several international markets, DACH in particular) and
no account-level sync into Salesforce. Einstein Activity Capture is the mandated path for
customer email; Tribble Scribe has no equivalent standing for call capture.

**Practical rule for this skill:** only extract meetings that are internal (UiPath
colleagues only). The `list` command prints participant names for exactly this check --
look at them before running `get`. Participant records store display names only, not email
domains, so this is a judgment call: if a name looks like it could be a customer contact
rather than a colleague, stop and confirm current consent/approval status with the user
before proceeding. Never treat "I didn't recognize the name" as license to proceed anyway.

## Why the extraction is safe to run

Tribble Scribe stores everything unencrypted in a local SQLite database
(`~/Library/Application Support/Tribble Desktop/tribble.db`) with no server call needed to
read past meetings. The database runs in WAL mode, so the newest rows live in the `-wal`
sidecar, not the main file -- reading the main file alone would silently miss recent
meetings.

`scripts/extract_tribble_meetings.py` therefore always:

1. Copies `tribble.db` plus its `-wal`/`-shm` siblings into a fresh temp directory.
2. Opens that copy read-only (`file:...?mode=ro`) -- the live app is never touched and keeps
   working normally.
3. Runs the query.
4. Deletes the temp directory (automatic, even on error, via `tempfile.TemporaryDirectory`).

This is why it's safe to run at any time, including while Tribble Scribe is actively
recording something else.

## Data handling after extraction

- Treat every summary and transcript as confidential customer/internal data, whichever it turns out to be.
- Never commit meeting content -- summaries, transcripts, or participant lists -- to this repository or any other. That includes this skill's own directory: don't paste real transcript text into a references file "for context."
- If you save extracted output to a file for your own working reference, use a scratch/temp location outside any git working tree, and clean it up once the draft is done.
- Drafting a Slack message from a summary is fine (that's the point of this skill); pasting the raw multi-page transcript into a Slack message is not the goal -- summarize it, and only share the transcript itself if the user explicitly asks for it as a separate attachment.
