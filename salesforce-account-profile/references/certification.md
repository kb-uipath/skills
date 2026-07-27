# Certification

**Current published state: `offline_validated`**

**Operational status: Not operationally certified**

**Last verified: 2026-07-27**

The package is validated with synthetic Salesforce CLI fixtures. No live Salesforce org,
customer record, token, tenant, or credential was used.

## Readiness States

| State | Permitted use |
| --- | --- |
| `offline_validated` | Package, orchestration, security, and synthetic behavior only; real data reads blocked |
| `sandbox_read_certified` | The recorded nonproduction org may be read under the certified synthetic-data scope |
| `production_read_approved` | The recorded production org may be read only after separate administrator and risk-owner approval |

State is per enrolled org fingerprint and field-map version. A Salesforce identity change,
runtime drift, certification-critical package change, metadata change, field-map change, or
failed recertification blocks use. Sandbox certification cannot be copied to a production
entry. A changed evidence receipt also invalidates every active read plan before its next
Salesforce data query.

## Offline Evidence

Offline gates cover:

- conversational `doctor`, `start`, `continue`, `status`, and `abort`;
- exact selected-account, ambiguous chooser, and explicit literal-prefix journeys;
- exact corporate-family plan approval and approval invalidation;
- incomplete family hard stops and selected-account fallback;
- fixed 30-minute resume, abort, completion, and expiry cleanup;
- authentication, permission, and cap recovery;
- metadata and field-semantic drift;
- exact relationship hydration and replay rejection;
- query completeness, batching, cumulative query budget, and every record cap;
- adversarial CRM text, shell payloads, token-bearing CLI output, and private-file races;
- multiple currencies, raw line-item pricing, and disabled annualization.

The private runtime attestation records the exact Node binary, Salesforce CLI entrypoint, and
package metadata. It is local drift evidence, not software-supply-chain certification or
proof of human approval. Conversational approval receipts are workflow evidence bound to the
current plan, not cryptographic proof of a human identity.

## Sandbox Certification Gate

Advance one explicitly approved sandbox/UAT org only after a read-only run against synthetic
Salesforce records verifies:

1. discovered and displayed org identity matches the enrolled fingerprint;
2. all required object and predicate metadata matches the versioned field map;
3. exact, no-match, ambiguous, and literal-prefix Account resolution behaves correctly;
4. corporate-family membership and fallback behavior match the approved synthetic fixture;
5. object and field permissions allow only the required reads;
6. Opportunities, line items, and Users remain bound to confirmed IDs and predicates;
7. query completeness, currency handling, recovery, token discard, and cleanup pass;
8. the evidence bundle contains no alias, username, org identifier, customer data, token, or
   local path.

Record only a redacted evidence digest and verification date. If no approved sandbox alias
and synthetic records are supplied, this gate remains unexecuted; offline success does not
justify advancing the state.

### Administrator Experience

This is a guided setup flow, not the Account-profile user flow. The administrator states the
approved sandbox/UAT friendly label and identifies the pre-provisioned synthetic fixture
set. Codex privately constructs the JSON, canonical timestamps, fingerprints, manifest and
scope digests, `0600` transport, and cleanup. The administrator never pastes a digest or
runs a Node or Salesforce CLI command.

The fixture set must contain:

- one uniquely named Account;
- two or more Accounts with the same exact synthetic name;
- a name guaranteed not to match;
- one literal-prefix chooser set;
- one bounded corporate-family set with an exact seed and Account-ID manifest;
- open and closed synthetic Opportunities across at least two currencies;
- synthetic Opportunity line items and an owner/manager chain.

Every returned Account, Opportunity, product, owner, manager, and parent name must contain
the same 8-64 character synthetic marker. A missing marker fails with no certification.
Fixture names, IDs, marker, validity window, field-map version, suite version, and enrolled
org fingerprint form one canonical manifest. The manifest is confidential and expires; only
its digest enters the final receipt.

The internal sequence is:

1. `doctor` enrolls or refreshes the explicitly selected sandbox.
2. `prepare-sandbox-certification` verifies org discovery, identity, required metadata, the
   pinned runtime, and the certification-critical package. It performs zero data queries
   and produces a 30-minute scope.
3. The external approval authority signs that exact scope with the configured sandbox
   certifier key. The assertion binds issuer, key ID, subject digest, role, audience, opaque
   reference, scope digest, nonce, issue time, and expiry.
4. `certify-sandbox` recomputes every binding, runs the answer-blind read-only suite, deletes
   every session and transient artifact, then atomically stores a self-validating receipt.

The private state directory must contain `approval-trust.json`, provisioned out of band with
only Ed25519 public keys for the exact sandbox-certifier, production-administrator, and
production-risk-owner roles. The file must be a real, stable, exact-mode `0600` file; private
keys never enter Codex state. Each accepted assertion is reserved atomically before any
certification query and recorded in a bounded replay ledger. A failed attempt consumes that
assertion and leaves prior readiness downgraded.

The production administrative CLI constructs the pinned Salesforce client directly. It
does not accept a caller-provided executable, runner, runtime path, offline override, or
client factory. Tests use a separate programmatic engine and cannot advance a real registry
through the public command.

### Sandbox Evidence Receipt

The private receipt binds:

- org fingerprint;
- Salesforce runtime attestation;
- certification-critical package digest;
- metadata-compatibility digest and field-map version;
- suite version and fixture-manifest digest;
- exact canonical scenario IDs and total query count;
- authorization-scope digest;
- signed-authorization assertion digest;
- start/completion times and pass outcome;
- a recomputable receipt digest.

A bare 64-character value is not certification evidence. Legacy v1 and unsigned v2 registry
certifications downgrade to `offline_validated`. Failed or successful recertification
invalidates every production approval that depends on the prior sandbox receipt.

## Production Approval Gate

Production remains blocked until its own enrolled fingerprint has:

- one current, freshly re-attested, internally stored sandbox evidence receipt;
- a signed production-administrator assertion from its configured role key;
- a signed production-risk-owner assertion from a different role key and subject;
- current identity, runtime, metadata, and field-map verification.

`prepare-production-approval` re-attests the referenced sandbox, then performs production
org and metadata verification with zero data queries. It creates a 30-minute scope bound to
the production fingerprint, current sandbox receipt, runtime, package, metadata, and field
map. Both signed assertions must bind that identical audience and scope inside its validity
window. `approve-production` re-attests the sandbox again, resolves its receipt internally,
recomputes all bindings, performs zero data queries, atomically reserves both nonces, and
records a self-validating production receipt.

The signatures prove possession of configured role keys; they do not independently prove a
person's legal identity or authority. Trust-root provisioning and external approval-system
governance remain administrator responsibilities. Final evidence stays redacted. Production
is never enabled merely because code, tests, PRs, or sandbox checks passed.

## Failure And Revocation

- Any scenario failure, truncation, permission or authentication failure, non-synthetic
  record, query-cap failure, cleanup failure, expiry, or concurrent registry change prevents
  certification.
- Any recertification reserves a fresh signed assertion, revokes the prior sandbox receipt,
  and invalidates dependent production approvals before queries begin.
- Runtime, package, metadata, receipt, or field-map drift blocks reads. `doctor` downgrades
  stale readiness and dependent approvals when it observes that drift.
- Active sessions bind the exact readiness receipt. Each data query holds the serialized
  registry lease through completion. Every queued writer publishes its own private queue
  ticket before contending for the writer mutex and releases that ticket last, so pending
  state remains continuous across writer handoffs. After active reads drain, the writer
  acquires the registry lock and only then publishes the write-intent lease. Query issuance
  performs one final ticket/pending check. Replacement or revocation therefore blocks the
  next query and cancels the session.
- Runtime and package bindings are rechecked at query issuance. The complete metadata map is
  re-attested once per continuation, while the query kernel still describes every field it
  uses. This preserves drift detection without repeating a six-object metadata sweep before
  every Salesforce query.
- Public final evidence contains no alias, username, org identifier, hostname, local path,
  Salesforce record ID, fixture ID, approval reference, token, or raw CLI output.

## Annualization

Annualization is separately uncertified. It requires an org-versioned field map that
explicitly certifies line-item price basis, recurring status, and duration together. Until
then, only raw `UnitPrice` and `TotalPrice` are returned.
