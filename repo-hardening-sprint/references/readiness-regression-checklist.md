# Readiness Regression Checklist

Use this checklist when a repository contains reusable Codex skills or other org-shared automation assets.

## Metadata and Docs

- Every public entrypoint has current usage docs.
- Metadata invokes the correct skill name and has no stale or nonstandard fields.
- Docs state required inputs, outputs, safety boundaries, and validation commands.
- Examples use relative paths or placeholders, not local machine paths.

## Safety Boundaries

- Live writes, sends, uploads, deploys, and permission changes require explicit confirmation.
- Dry-run or validate-only behavior is available for risky workflows.
- Secrets, credentials, customer exports, and local caches are not committed.
- Privacy-sensitive outputs redact or avoid names, emails, request bodies, and connector IDs unless necessary and authorized.

## Deterministic Validation

- Every script has unit or fixture coverage for the main path and at least one failure path.
- Output validators reject uncited claims, malformed inputs, stale evidence, or unsafe writes where applicable.
- CI and local validation use the same command when possible.

## Readiness Scoring

- Re-score any changed skill using `docs/production-readiness-evaluation.md`.
- Record final score, baseline score, delta, evidence, and remaining blocker.
- A skill below 8/10 needs an explicit follow-up before broad org rollout.
