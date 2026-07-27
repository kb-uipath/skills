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
runtime drift, field-map change, or failed recertification blocks use. Sandbox certification
cannot be copied to a production entry.

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

## Production Approval Gate

Production remains blocked until its own enrolled fingerprint has:

- a successful sandbox evidence digest;
- a separate administrator approval reference and timestamp;
- a separate risk-owner approval reference and timestamp;
- current identity, runtime, metadata, and field-map verification.

No approval reference is a credential. Public evidence must remain redacted. Production is
never enabled merely because the code, tests, PRs, or sandbox checks passed.

## Annualization

Annualization is separately uncertified. It requires an org-versioned field map that
explicitly certifies line-item price basis, recurring status, and duration together. Until
then, only raw `UnitPrice` and `TotalPrice` are returned.
