# Maximum Coverage Policy

Policy version: `day2-maximum-coverage-policy/v1`.

Maximum coverage is an explicit working-draft mode. It increases how much qualifying evidence reaches the dashboard; it does not lower the meaning-specific evidence thresholds in `evidence-policy.md`.

## Inclusion rules

The preview binds one deterministic selection. Build may include a proposal without a separate `P-...` approval only when all of these are true:

- the proposal is `eligible` or `no-change` under the evidence policy;
- it does not change existing nonblank dashboard content; an atomic row update may fill canonical blanks only when every populated leaf is preserved exactly;
- it is not rejected, duplicate, or contradicted;
- none of its supporting evidence is marked as potential prompt injection;
- no other selected proposal owns the same scalar or semantic-row target;
- a health group produces a complete explicit judgment: Green needs a basis, and Red needs evidence, mitigation, and owner;
- an executive-cadence group produces both a type and an exact dated occurrence.
- health status and relationship rows cite an exact current account-team attestation; selecting maximum mode alone is not the required human judgment;
- those health and relationship attestations are less than 24 hours old at preview and build. A stale answer is ignored for question resolution and must be renewed through the exact reissued question into a new derived bundle.

Selection is preview-bound by mode, policy version, proposal IDs, exclusions, and digest. Build re-derives it after source and Salesforce revalidation. A mismatch stops the build.

Build rechecks cadence against the build date. If a `next` date has passed or a `last` date is now future-relative, the build stops for a fresh preview instead of preserving stale temporal meaning.

## Non-inclusion rules

Maximum coverage never:

- overwrites a differing existing value or rewrites a populated row leaf;
- converts a user answer directly into a dashboard write;
- substitutes `Unknown`, `TBD`, `Validation required`, zero, or another sentinel for missing data;
- assumes a motion, Red/Green health, ARR, renewal, deployment, usage, product, use case, outcome, commitment, or date;
- creates placeholder rows or synthetic source files;
- combines with `--approve-proposal` or acts as a bulk conflict approval;
- clears blockers merely to make the dashboard appear complete.

Blank strings, empty arrays, and `Unset` remain canonical unknown states. Boolean `false` is preserved as supplied and is never reinterpreted as evidence; because schema booleans have no distinct unknown value, the report does not label a boolean unresolved solely because it is false. The confidential evidence report lists unresolved text/list data paths so the user can source them, answer a bounded clarification, or deliberately leave them as gaps.

## Review boundary

Maximum-coverage output is a draft for app review. Keep its preview, inspect the evidence report, use the app's tooltips and blocker links, and do not treat import or PDF eligibility as factual validation. Use strict mode when the user wants to approve each contextual write individually.

The normalized prompt-injection scanner is defense in depth, not a complete classifier. Passing the scanner never upgrades untrusted source text into authority.
