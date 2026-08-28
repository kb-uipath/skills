# Message templates: exec-brief vs. leads-technical

Both channels get the same underlying facts and the same skeleton. What changes is density
and jargon, not structure or length of the skeleton itself. Neither version should read as
a wall of paragraphs -- if a bullet is running past 2-3 lines, it's carrying too much; split
it or cut it.

## Shared skeleton

```
📋 *CS Agentification — <Channel label> Update (<date>)*

*Status:* <one line -- program phase / gate, and whether things are actually moving>

*High-impact items:*
• <bullet>
• <bullet>
• <bullet>
(3-5 bullets, no sub-bullets)

*Next 1–2 weeks:*
• <owner> — <action>, <timeframe>
(as many as there are real near-term commitments; don't pad this out)

*Watch item:* <optional -- one thing worth flagging that doesn't fit "high-impact" or "next steps", e.g. a process/governance gap>
```

## #cs-agentification (exec-brief)

Audience: people who need to know the program is healthy and where the big rocks are, not
how they're being moved. Cut anything that requires knowing what a specific internal tool
or system does. Every bullet should be readable by someone who hasn't been in the calls.

**Worked example (illustrative, not real program content):**

> 📋 *CS Agentification — Program Update (illustrative)*
>
> *Status:* Moving from planning to execution. Formal gate still open, but direction and first workstreams are in motion.
>
> *High-impact items:*
> • *Target platform confirmed.* The three overlapping internal tools keep running while the team consolidates them into one long-term home.
> • *Pilot expands this month* — then the team shifts focus from features to hardening for the long-term integration.
> • *Data quality fix underway* — moving account plans off manual documents into the system of record. Blocked on a data-model decision, expected mid-next-week.
> • *Shared data layer is the critical dependency* — not yet in production, no firm date.
>
> *Next 1–2 weeks:*
> • Tool owners finalize a capability comparison → used at next week's sync to assign ownership and cut duplication.
> • Data-migration plan continues once the data model lands.
>
> *Watch item:* The formal decision record hasn't caught up to what's already been agreed informally -- worth closing that gap as the program scales.

## #cs-agentification-program-leads (technical)

Audience: the people who were in the calls, or need to be able to act without asking a
follow-up question. Same bullet count and same brevity per section -- the density goes
*into* each bullet (specific owner, specific system, specific date, specific blocker), not
into extra sub-bullets or longer prose. A useful test: could someone action a bullet without
pinging you first? If not, add the missing specific (who, what system, what date) rather
than the missing sentence.

**Worked example (illustrative, not real program content) -- same underlying update as above:**

> 📋 *CS Agentification — Leads Update (illustrative)*
>
> *Status:* Gate G0 -- formal decision log lagging actual progress (owners named, direction set in practice). Close that gap this week.
>
> *High-impact items:*
> • *Tool alignment set:* Owner A → Tool A, Owner B → Tool B, Owner C → Tool C. Target platform is Tool D; existing tools stay live — priority is componentizing (skills/APIs), not maintaining UIs. Capability inventories due early next week → comparison at Friday's sync.
> • *Data layer is the bottleneck:* Shared layer still in UAT, no ship date. Tool A partially on it (legacy fallback unclear); Tool B still fully on the old connector. No agreed metric definitions yet.
> • *Success plan → system of record:* Approach set — extract data from existing documents, map to fields, bulk import (direct write access isn't available). Blocked on the data model, targeting mid-next-week; also consolidating three record types into one.
> • *Pilot:* ~N users, expansion this month, then UI freeze → shift to hardening components for the target platform.
>
> *Next 1–2 weeks:*
> • Owner A/B — finalize capability inventories, early next week
> • Owner C — sync with data-layer team on production date
> • Program lead / data-model owner — reconvene Monday on migration workflow
> • Data-model owner — target mid-next week
> • Friday sync — cross-tool comparison + seed-owner assignments

## Producing the real drafts

1. Fill the skeleton from the actual meeting summary/transcript and the Confluence
   cross-check -- never from the illustrative examples above, which exist only to show shape
   and tone.
2. Write the leads version first (it has all the detail); the exec version is usually a
   compression of it, not a separate research pass.
3. Sanity-check both against the shared skeleton before sending them to
   `slack_send_message_draft` -- same section order, same "no sub-bullets" rule, same
   3-5 item cap on "High-impact items."
