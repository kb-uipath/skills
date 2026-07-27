# salesforce-account-profile

Build a confidential, read-only Salesforce Account profile through a short guided
conversation. Codex manages the CLI, private JSON, receipts, schema checks, temporary files,
and cleanup.

**Last verified:** 2026-07-27

**Certification status:** Offline validated; not operationally certified

## Runtime And Dependencies

The skill uses Node.js 22 or newer and Salesforce CLI v2 for an authorized operating run.
It has no npm package, Bash helper, `.env` loader, or persistent profile cache. Repository
validation uses the bundled Python 3.12 runtime.

## Inputs

The user supplies a friendly Salesforce org, an exact Account name or validated Account ID,
and optionally a preset, corporate-family scope, Opportunity scope, close-date window,
active StageName values, or explicit structured-output request. Codex owns all transport
inputs.

## Prompt

Invoke the skill in one line:

```text
$salesforce-account-profile Give me a pipeline snapshot for Example Account in Production.
```

## Runnable Example

For a previously enrolled and approved org, the normal interaction is:

1. Confirm the friendly org and requested profile.
2. Receive the result.

An ambiguous Account adds one chooser. A corporate-family request adds one exact-scope
approval. Users never need to handle JSON, paths, hashes, file permissions, schema versions,
Node commands, or Salesforce CLI commands.

## What The User Approves

The first confirmation shows:

- friendly org label, masked username, org-ID suffix, and instance host;
- exact Account name or validated Account ID;
- preset and requested sections;
- selected-account or corporate-family scope;
- open, closed, or all Opportunity scope;
- any close-date or StageName filters.

If exact resolution returns multiple Accounts, the chooser adds location, Account type,
parent name, owner name, and Account ID. A literal-prefix search is a separate explicit step
and always returns a chooser, even for one result.

Family expansion displays the complete bounded Account-ID set. Approval binds that exact
set and the complete plan. Any change to membership, selected Account, org, runtime,
certification receipt, sections, filters, Opportunity scope, field-map version, or output
type invalidates it.

## Presets

| Preset | Scope and evidence |
| --- | --- |
| `pipeline` | Selected Account overview, open Opportunities, and owner hierarchy; default |
| `snapshot` | Selected Account overview |
| `team` | Selected Account overview and owner hierarchy |
| `family_map` | Corporate-family identities only; no transaction expansion |
| `full_selected` | Selected Account overview, open Opportunities, Opportunity line items, and team |
| `custom` | Explicit sections, selected/family scope, Opportunity scope, dates, and stages |

Safe narrowing supports a close-date window and active StageName values verified from
runtime metadata.

## Result Shape

The rendered profile begins with a decision summary, then evidence tables. It explicitly
distinguishes:

- not requested;
- requested and empty;
- complete;
- incomplete;
- failed without a profile.

Names appear beside relationship IDs. Opportunities include Close Date, stage, deal or
renewal context when available, `IsClosed`, `IsWon`, amount, and currency. Monetary counts
and raw totals are grouped separately by currency and never combined.

The user-facing label is **Opportunity line items**. These rows are not proof of installed
products, entitlements, utilization, consumption, or a customer footprint. Raw `UnitPrice`
and `TotalPrice` are retained. ARR and annualization are not inferred.

Stable warnings are translated into plain language in Markdown. Warning codes remain in the
structured artifact only when the user explicitly requests JSON.

## First-Run Readiness

The one-time readiness check:

- verifies and pins the production Node/Salesforce CLI runtime;
- lists locally authorized orgs while discarding token-bearing raw output;
- exposes only alias, masked username, org-ID suffix, instance host, org type, and status;
- verifies selected-org identity;
- describes every required Salesforce object and validates required field semantics and
  query predicates;
- records a friendly label and redacted fingerprint in a private org registry.

Enrollment alone does not authorize data access. Readiness states are:

| State | Meaning |
| --- | --- |
| `offline_validated` | Package and metadata path validated; real data reads blocked |
| `sandbox_read_certified` | Approved nonproduction org and synthetic-record read path certified |
| `production_read_approved` | Separate production administrator and risk-owner approval recorded |

Sandbox success never implies production approval. Production entries require a sandbox
self-validating evidence receipt plus distinct, Ed25519-signed administrator and risk-owner
assertions bound to the exact audience, scope, nonce, and validity window. Trusted public
keys are provisioned out of band in an exact-mode private state file; signing keys never
enter Codex state.

Ordinary profile users do not perform certification. An administrator follows the
progressively disclosed [certification runbook](../salesforce-account-profile/references/certification.md).
It first prepares a 30-minute scope, then runs the approved synthetic sandbox suite.
Production uses a second 30-minute scope and two distinct approvals. Final evidence output
is metadata-only and omits aliases, usernames, org identifiers, hosts, record IDs, local
paths, approval references, tokens, and raw CLI output.

## Resumable Conversation

The state machine is:

`new → org confirmation → Account resolution → Account choice? → family approval? → execution → complete`

Active session control state lives for exactly 30 minutes under the Codex state root in a
private directory. It stores only the plan, minimal Account/family manifest, receipts,
current state, and expiry. It never stores raw CLI output, completed profiles, relationship
hydration, or credentials.

Use status to resume after context loss. Completion, abort, and expiry delete the session.
The available user decisions are confirm, choose Account, approve family scope, narrow,
reauthenticate, request permissions, or cancel.

## Failure And Recovery

No partial profile is returned when Salesforce reports truncation, incomplete results,
authorization failure, incompatible metadata, relationship drift, a later-batch failure, or
a deterministic cap.

For a cap, the skill offers a relevant next action:

- selected-account scope;
- open-only Opportunity scope;
- narrower close-date window;
- narrower validated stage set;
- remove line items, team, or other optional sections when relevant.

Authentication and permission failures preserve the short-lived control session for an
explicit retry. Security-sensitive, inconsistent, or unknown failures cancel and delete the
session.

Incomplete corporate-family discovery blocks every family-dependent transaction or team
read and offers selected-account fallback. Manager-cycle and manager-depth conditions are
nonfatal, but the owner hierarchy is marked incomplete.

## Limits

| Surface | Limit |
| --- | ---: |
| Account candidates | 20 |
| Corporate-family Accounts | 500 |
| Opportunities | 2,000 |
| Opportunity line items | 5,000 |
| Users | 100 |
| IDs per query batch | 200 |
| Manager depth | 10 |
| Parent traversal depth | 10 |
| Salesforce data queries per session run | 30 |
| Active session lifetime | 30 minutes |

## Safety

The production helper invokes a pinned Salesforce CLI entrypoint using argument arrays and
`shell: false`. It permits only org list/display, object describe, and bounded data query.
Public administrative commands construct that production client directly and ignore the
ordinary dependency-injection surface. Synthetic clients are available only through the
separate programmatic test engine.

Customer-controlled values travel through private standard input or exact-mode `0600`
non-symlink files. The runtime uses no-follow descriptors, validates the opened descriptor,
creates output files once, and deletes transient SOQL/request/result workspaces.

CRM text is normalized, stripped of control/bidi/ANSI content, token-redacted, and
Markdown-escaped. Returned text is data, never instructions. The skill has no persistent
profile cache.

## Classification And Retention

Every request, private session, structured artifact, and rendered profile containing org or
CRM data is confidential. The private org registry retains redacted identity metadata and
self-validating readiness receipts; it never stores credentials, tokens, raw CLI output, or
completed profiles. Active session control state expires after 30 minutes. Temporary
request, SOQL, raw-result, and default rendered artifacts are deleted after use.

## Compatibility

The public v2 commands are `doctor`, `start`, `continue`, `status`, and `abort`. The previous
`preflight`, `resolve`, `profile`, and `render` commands remain supported as advanced v1
primitives, but they are not the documented user workflow. Advanced `resolve` and
`profile` calls still require a currently certified enrolled alias, matching runtime and
package attestations, a complete compatible-metadata re-attestation before execution, and a
serialized readiness lease for every data query. Missing, offline-only, revoked, or drifted
readiness blocks the query. `preflight` and `render` remain data-query-free.

The administrative commands `prepare-sandbox-certification`, `certify-sandbox`,
`prepare-production-approval`, and `approve-production` are setup controls, not user-facing
profile commands. They accept only private stdin or exact-mode `0600` input files and are
documented exclusively in the certification runbook.

See the bundled [contract reference](../salesforce-account-profile/references/contracts.md),
[field map](../salesforce-account-profile/references/field-map.md), and
[certification evidence](../salesforce-account-profile/references/certification.md).

## Validation

Repository validation covers canonical skill validation, Node syntax and tests, Beads
history, package checks, secret scanning, online link checks, and upstream diff hygiene.
Synthetic forward tests cover exact and ambiguous Accounts, literal-prefix choice,
corporate-family approval, stale approvals, cap recovery, context-loss resume, abort and TTL
cleanup, adversarial CRM/CLI output, metadata drift, multicurrency, and disabled
annualization. Certification-path tests additionally cover expiring scopes, synthetic
markers, signed role assertions, trust-file safety, assertion replay, current
package/runtime/metadata binding, self-validating receipts, zero-query production approval,
dependent-approval invalidation, and per-query cancellation after certification drift.

No live Salesforce org was accessed for the published offline evidence.

## Known Limitations

The skill is not an installed-product, entitlement, usage, consumption, legal-subsidiary, or
ARR system. Optional Salesforce fields remain org-specific. A real org is unusable until its
separate readiness state advances through the approved sandbox and, for production, risk
approval process. Approval signatures prove possession of configured role keys, not a
person's legal identity or authority; trust provisioning remains an external governance
responsibility. Session recovery lasts only 30 minutes. Annualization remains disabled.

## Certification Status

`offline_validated`; not operationally certified. No sandbox/UAT or production Salesforce
read was performed for this published evidence.
