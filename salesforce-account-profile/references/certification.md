# Certification

**Status: Not operationally certified**

Last verified: 2026-07-25

The package is offline-validated with synthetic Salesforce CLI fixtures. No live Salesforce
org, customer record, token, tenant, or credential was used.

Operational certification remains blocked until an authorized nonproduction review verifies
org identity, object and field permissions, query completeness, custom-field semantics,
corporate-family behavior, currency handling, retention, operator review, and recovery
against an explicitly approved synthetic data set. This repository does not perform that
probe.

Annualization is separately uncertified. It requires an org-versioned field map that
explicitly certifies line-item price basis, recurring status, and duration together.
