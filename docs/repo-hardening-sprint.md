# repo-hardening-sprint

Run a bounded cleanup and validation sprint on a repository without changing public contracts unnecessarily.

## When To Use

Use this skill when the user asks to harden, clean up, refactor, document, test, prepare for commit, or make a repo safe to push.

## Inputs

- Repository path.
- Desired hardening goal.
- Public contracts that must not break.
- Validation commands if known.
- Commit, push, or PR expectations.

## Prompt

```text
Use $repo-hardening-sprint on this repository. Identify the highest-risk cleanup items, implement safe fixes, run the repo validation gate, and summarize residual risks.
```

## Outputs

- Scoped findings and changes.
- Tests or validation gates added or run.
- Public contracts preserved.
- Residual risks and follow-ups.
- Optional review report based on `references/review-report-template.md`.
- Readiness regression checklist for reusable skills and org-shared automation assets.

## Safety

- Do not revert unrelated user changes.
- Do not perform destructive git operations unless explicitly requested.
- Keep broad rewrites, dependency upgrades, and generated artifact churn out of scope unless needed for the stated goal.
- For this skills repo, use `make validate` when available.
- Update `docs/production-readiness-evaluation.md` after material skill hardening changes.

## Validation

```bash
make validate
python3 tools/validate_repo.py
```
