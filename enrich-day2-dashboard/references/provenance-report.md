# Provenance report template

One markdown file per enrichment run, delivered to the user alongside the rendered
result. It is a confidential customer artifact: keep it in the scratchpad, never commit
it, no verbatim customer quotes — paraphrase with a locator.

Values live in the dashboard; evidence lives here. Do not add evidence ledgers or
citation fields inside the dashboard JSON itself.

```markdown
# <Account> Day 2 enrichment — provenance report

Run date: <ISO date>. Baseline: <archive revision id / draft / template>.
Evidence window: <start>–<end> (most recent authoritative statement wins).
Sources swept: <Slack channels>, <mailbox + calendar>, <notebook/site>, <Tribble scope>.

## Changed fields

| Field | New value (short) | Source | As-of |
| --- | --- | --- | --- |
| accountTeam.customerSuccessDirector | <Name> | Slack #<acct-channel>, intro thread | <ISO date> |
| … | … | … | … |

Locator formats: Slack = channel + date (+ thread), email = subject + date,
document = filename + last-modified, Tribble = meeting title + date. No URLs with
tokens, no message bodies.

## Deliberately left empty

| Field | Why |
| --- | --- |
| supportTier | No statement found in window |
| pipelineOpportunities[].estimatedIarrUsd | Hours evidence only; no dollar statement |

## Recency conflicts resolved

| Topic | Older statement | Newer statement (adopted) |
| --- | --- | --- |
| Renewal | "out for bid" (<date>) | "renewal completed" (<later date>) |

## Identity resolutions

| Alias seen | Resolved to | How |
| --- | --- | --- |
| "<nickname>" | <Full name> | Email signature, <date> |
```

Rules:
- Every changed field appears exactly once, with a source and an as-of date.
- The "deliberately left empty" section is mandatory — it is the proof of
  non-fabrication.
- Conflicts and identity resolutions get their own tables so reviewers can audit the
  judgment calls, not just the values.
