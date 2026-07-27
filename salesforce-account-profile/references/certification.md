# Certification

**Status: Offline validated; not operationally certified**

Last verified: 2026-07-27

The package is offline-validated with synthetic Salesforce CLI fixtures. No live Salesforce
org, customer record, token, tenant, or credential was used.

Offline trust-boundary evidence covers complete-plan receipt invalidation, family cycle/depth
hard stops, exact User-reference validation, race-free private-file reads, and a private
create-once Node/Salesforce CLI/package-metadata attestation that fails closed after drift.
The runtime attestation is local drift evidence, not software-supply-chain certification or
proof of human approval.

Operational certification remains blocked until an authorized nonproduction review verifies
org identity, object and field permissions, query completeness, custom-field semantics,
corporate-family behavior, currency handling, retention, operator review, and recovery
against an explicitly approved synthetic data set. This repository does not perform that
probe.

Annualization is separately uncertified. It requires an org-versioned field map that
explicitly certifies line-item price basis, recurring status, and duration together.
