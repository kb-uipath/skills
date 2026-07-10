# Contributing

This repository contains reusable Codex skills, documentation, and validation tooling. Keep changes scoped, deterministic, and safe for public sharing.

## Required Checks

Run the validation gate before opening a pull request or committing hardening work:

```bash
make install-dev
python3 tools/validate_repo.py
make validate
make secrets
```

Install the exact development dependencies from `requirements-dev.txt` when running the full gate locally.

Run `make validate-online` separately when network access is available. External-link availability is monitored on a schedule and is intentionally outside the deterministic PR gate.

## Change Rules

- Preserve skill directory names, `SKILL.md` frontmatter names, and primary invocation prompts unless a migration is explicitly approved.
- Do not add live credentials, customer exports, connector payloads, tenant-specific dumps, or local cache artifacts.
- No live external writes, sends, uploads, deploys, or permission changes may be performed from validation paths.
- Update the matching public doc page when changing a public skill contract, runtime dependency, validation command, or safety boundary.
- Keep generated files and broad formatting churn out of pull requests unless they are the direct deliverable.

## Review Expectations

Pull requests should explain the changed public contract, tests run, residual limitations, and any manual recovery steps. Claims of certification must be backed by the evidence in `docs/production-readiness-evaluation.md`.
