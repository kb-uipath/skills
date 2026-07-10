# Availability Ranking Contract

## Versioned Artifacts

- Request schema `1.0`: `schemas/free-busy-request-v1.schema.json`
- Result schema `1.0`: `schemas/free-busy-result-v1.schema.json`
- CLI: `../scripts/rank_meeting_slots.py`

The request is a normalized snapshot of read-only Outlook schedule evidence. It is not a request to create an event. The CLI performs no connector or network operations and emits only a recommendation artifact.

## Request Rules

Every request must declare the exact schema name and version, a stable request ID, an offset-aware window, slot duration and increment, result limit, participants, and source provenance. Unknown fields and duplicate JSON keys fail closed.

Participant IDs and emails must be unique. Each participant declares:

- whether attendance is required
- an optional human-readable `display_name` copied to the result; it defaults to the participant ID
- a practical email address
- an installed IANA time zone
- non-overnight local working hours and weekdays
- zero or more half-open busy intervals `[start, end)`

At least one participant must be required. Every timestamp must be RFC 3339 with `Z` or a numeric offset. `provider` must be `outlook` and `retrieval_mode` must be `read-only`.

## Status Interpretation

Only `free` is available. These statuses block a candidate:

- `tentative`
- `busy`
- `out_of_office`
- `working_elsewhere`
- `unknown`

This conservative rule prevents uncertain Outlook evidence from being treated as permission to schedule.

## Deterministic Ranking

1. Convert the window and intervals to UTC.
2. Generate candidate starts from the exact window start using `slot_increment_minutes`.
3. Keep candidates whose end is within the window.
4. Reject candidates outside any required participant's local working hours.
5. Reject candidates overlapping any blocking interval for a required participant.
6. Score each remaining candidate by the number of optional participants available and within working hours.
7. Sort by optional availability descending, then UTC start ascending.
8. Return at most `max_results`, with ranks starting at 1, local times rendered for every participant, and privacy-safe reason records for unavailable optional participants.
9. Return a privacy-safe participant label map and up to 100 excluded-slot details with required blockers and deterministic reason counts. Never emit participant email addresses.

The result has no generated timestamp, random ID, locale-sensitive value, or current-time dependency. Identical input produces identical JSON data. `source.retrieved_at` is copied from the evidence snapshot.

## No Common Slot

When no candidate satisfies every required participant, the CLI exits successfully with:

```json
{
  "status": "no_common_slot",
  "eligible_slot_count": 0,
  "ranked_slots": []
}
```

Do not silently broaden working hours, ignore a status, drop a required participant, or schedule anyway. Ask the user which constraint to change, collect a new read-only snapshot, and rank a new versioned request.

## Limits

- Search window: 31 days maximum.
- Participants: 100 maximum.
- Busy intervals: 1,000 per participant maximum.
- Result count: 100 maximum.
- Excluded-slot details: first 100; `excluded_slots_truncated` states when more were omitted.
- Slot duration and increment: 5 to 1,440 minutes.
- Working hours must start and end on the same local day.
- IANA time zone data must be installed in the Python runtime environment.

The ranker does not model travel time, meeting rooms, recurrence, delegates, attendee quorum rules, Outlook category semantics, organizational holidays, or working-hour exceptions beyond the supplied snapshot.
