# Retired: schema-1.4 Salesforce-first flow

This folder holds the previous generation of this skill, retired 2026-08-27 and kept
runnable, not ported.

**Why retired:** the skill was frozen to schema 1.4 and built around a deterministic
Salesforce mapping layer with a proposal/approval (`P-…`/`Q-…`) workflow. The current
Day 2 app is the v6 slide dashboard on schema 1.8 with a shared immutable archive and a
browser draft store; the enrichment process is now a four-source evidence sweep
(Slack / Outlook / OneNote-SharePoint / Tribble Scribe) with recency-first conflict
resolution and lineage-preserving delivery. The Salesforce layer's exact mappings,
coverage modes, and revalidation receipts do not translate to that flow and were
deliberately not carried over.

**When to use this folder:** only for existing schema-1.4 documents or when the user
explicitly asks for the Salesforce-first flow. Follow
[SKILL-1.4.md](SKILL-1.4.md) exactly as written — it is self-contained, with its
references in `references-1.4/`, its Salesforce child layer in `salesforce-layer/`,
and its scripts/tests/agents alongside. Do not mix its outputs into the 1.8 flow, and
do not feed 1.6+ app exports back into it (its own rules cover this).

**Do not** "modernize" files in this folder. If something here is needed by the 1.8
flow, write a fresh equivalent at the skill root instead.
