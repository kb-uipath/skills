---
name: cs-agentification-weekly-update
description: Draft the weekly (or ad hoc) CS Agentification program update as Slack drafts for #cs-agentification (exec-brief) and #cs-agentification-program-leads (technical). Use this whenever the user asks to draft, prepare, write, or post a CS Agentification program/status/weekly update, a leads-sync or success-plan-migration recap, or anything destined for those two Slack channels -- even if they only name one channel, mention "this week's update," or just say "draft the update" in the context of CS Agentification. Pulls source material from the user's local Tribble Scribe call recordings plus the CS Agentification Confluence space, and always creates saved Slack drafts rather than sending.
---

# CS Agentification Weekly Update

## Overview

Turns this week's CS Agentification calls (recorded locally by Tribble Scribe) plus the
program's Confluence tracker into two Slack drafts, calibrated to two different audiences,
in the same brief bullet style:

- **#cs-agentification** (`C0B8533LJGK`, public) -- exec-level, high-impact-only.
- **#cs-agentification-program-leads** (`C0BRDSM6EHM`, private) -- same brief bullet
  structure, but every bullet carries the real technical detail (owners, systems,
  blockers, dates) that leads need and executives don't.

Channel IDs above are this user's defaults. Override with `CS_AGENTIFICATION_EXEC_CHANNEL_ID`
/ `CS_AGENTIFICATION_LEADS_CHANNEL_ID` if the channels ever change.

## When to run this

Trigger on requests like "draft this week's CS Agentification update," "post the leads
update," "summarize the leads sync and success plan call for the channel," or any ask to
prepare a program update for either Slack channel above -- whether it's the regular weekly
cadence or a one-off recap of a specific call.

## Method

### 1. Find this week's meeting(s)

List recent recordings and eyeball titles/dates/participants:

```bash
python3 cs-agentification-weekly-update/scripts/extract_tribble_meetings.py list --days 7
```

The recurring leads call is usually titled "CS Agentification Weekly Strategy Sync." Also
look for any other CS Agentification-related calls from the same window the user mentions
by name (e.g. "Success Plan Migration"). If nothing obvious matches, ask the user which
call(s) to use rather than guessing.

### 2. Consent/safety gate -- read this before extracting anything

Read `references/tribble-safety-and-method.md` in full before the first use in a session.
The short version: Tribble Scribe is not an approved TAM tool, every transcript/summary is
confidential, and this only proceeds safely for **internal** meetings. The `list` output
prints participant names for exactly this reason -- check them. If anyone looks like an
external customer contact rather than a UiPath colleague, stop and confirm current
consent/approval status with the user before extracting that meeting; don't guess from a
name alone.

### 3. Extract the meeting(s)

```bash
python3 cs-agentification-weekly-update/scripts/extract_tribble_meetings.py get <meeting-id> --transcript
```

This runs entirely against a temporary read-only snapshot of the local Tribble database --
it never touches the live file, and the snapshot is deleted automatically. Keep any saved
output (transcript files, notes) in a scratch/temp location, never in a git-tracked path --
see the Safety section in `references/tribble-safety-and-method.md` for why.

### 4. Cross-check the program record

The Tribble summary is one meeting's view; the program has more state than any single call.
Pull the two live-status Confluence pages in space `CSA` -- "CS Agentification Weekly
Operating Log" and "Latest CS Agentification Status" -- and skim recent activity in the
target Slack channel(s). This catches decisions/context the call alone would miss, and
matters for one specific thing worth calling out in the draft: **the formal decision log
tends to lag informal progress** (tech leads named in Slack before they're recorded in
Confluence, for example). When you see that gap, say so in the update rather than silently
picking one source over the other.

### 5. Draft both versions

Read `references/message-templates.md` for the exact section structure and the worked
example of how the same underlying facts get compressed for execs vs. expanded with detail
for leads. Both drafts share the same skeleton (Status line / High-impact items / Next 1-2
weeks / optional Watch item) and the same brief-bullet voice -- the leads version is denser
per bullet, not longer in structure or written as prose paragraphs.

### 6. Create Slack drafts -- never send

Call the Slack MCP tool `slack_send_message_draft` once per channel (`channel_id` +
`message`), never `slack_send_message`. This tool only saves a draft to the user's own
Drafts & Sent -- nothing is posted until the user sends it themselves. Hand back both
`channel_link` values so the user can review and send.

If a call fails with `draft_already_exists` (or the `channel_not_found` variant of the same
problem -- this MCP server has no edit/delete-draft tool), don't keep retrying: tell the
user a draft already exists in that channel, give them the new text to paste in manually,
and offer to retry once they've cleared the old draft.

## Safety summary

- Tribble output is confidential; never commit it anywhere, including this skill's own repo.
- Internal calls only, without further review; external-participant calls need consent/approval confirmation first.
- Drafts only -- sending is always the user's action, never this skill's.

Full detail: `references/tribble-safety-and-method.md`. Message structure and examples:
`references/message-templates.md`.
