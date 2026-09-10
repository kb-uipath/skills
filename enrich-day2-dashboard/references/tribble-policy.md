# Tribble Scribe data policy

Tribble Scribe is an **experimental, not-approved** meeting-notes tool. Its local
database contains confidential customer content and personal data (names, transcripts,
private meeting notes). These constraints come from the team's own CE-repo
documentation of the tool and are not negotiable:

1. **Consent every run.** Ask the user whether Tribble is in scope for this specific
   enrichment run, even if they cleared it in a previous run or for a previous account.
2. **Local only.** Tribble-derived content never leaves the machine: never committed to
   any repo, never uploaded, never pasted into shared systems. Findings notes that cite
   Tribble stay in the session scratchpad.
3. **No verbatim quotes.** Neither dashboard fields nor the provenance report may carry
   transcript excerpts or quoted customer speech. Paraphrase, and cite by meeting title
   + date.
4. **Read-only, snapshot-based.** Access only through `scripts/tribble-read.mjs`, which
   copies the db + `-wal` + `-shm` sidecars to a temp dir, opens the snapshot read-only
   via `node:sqlite`, and deletes the snapshot afterward. Never open the live DB
   (`~/Library/Application Support/Tribble Desktop/tribble.db`) directly, never
   write to it, never run while intentionally racing an in-progress recording.
5. **Minimize extraction.** Pull only meetings matching the account/participants within
   the agreed window. Do not browse unrelated meetings.
6. **Personal data discipline.** Participant lists are identity evidence, not content —
   use them to match meetings and resolve names, don't reproduce them in outputs.
