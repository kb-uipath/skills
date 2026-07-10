# repo-hardening-sprint

Run a bounded cleanup and validation sprint on a repository without changing public contracts unnecessarily.

Last verified: 2026-07-10

## When To Use

Use this skill when the user asks to harden, clean up, refactor, document, test, prepare for commit, or make a repo safe to push.

## Inputs

- Repository path.
- Desired hardening goal.
- Public contracts that must not break.
- Validation commands if known.
- Commit, push, or PR expectations.

## Runtime And Dependencies

- Runtime: Codex CLI session with shell access to the target repository.
- Required local tools: `git`, `rg`, and the repository's own language runtimes or package managers.
- For this skills repository: Python 3.11+, Node 22+, `make`, and the exact development dependencies in `requirements-dev.txt`.
- Network access is optional and read-only unless the user explicitly authorizes a live external write.

Do not treat missing optional tools as permission to improvise. Fail closed, state the missing dependency, and give the operator the migration or install path needed to continue.

## Versioned Contract

Contract version: `repo-hardening-sprint/v1`.

Stable public entrypoints:

- Skill name: `$repo-hardening-sprint`.
- Primary skill file: `repo-hardening-sprint/SKILL.md`.
- Public docs: `docs/repo-hardening-sprint.md`.
- Repo validation command: `python3 tools/validate_repo.py`.
- Full local gate when available: `make validate`.

The skill preserves public commands, schemas, prompts, file formats, and documented integration points unless the user explicitly approves a migration. Unsafe legacy behavior fails closed with migration guidance instead of being carried forward silently.

## Prompt

```text
Use $repo-hardening-sprint on this repository. Identify the highest-risk cleanup items, implement safe fixes, run the repo validation gate, and summarize residual risks.
```

## Runnable Example

```bash
git status --short
git branch --show-current
python3 tools/validate_repo.py
make validate
make secrets
make validate-online
git diff --check origin/main...HEAD
```

For a repository that does not provide `make validate`, use the repo's documented CI-equivalent command and still run any available metadata, link, path-leak, secret, syntax, and unit-test checks.

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
- Do not perform live external writes, sends, uploads, deploys, or permission changes from a hardening sprint unless the user explicitly requests that exact operation.
- Keep broad rewrites, dependency upgrades, and generated artifact churn out of scope unless needed for the stated goal.
- For this skills repo, use `make validate` when available.
- Update `docs/production-readiness-evaluation.md` after material skill hardening changes.
- If an old workflow relies on markdown TODO files, unpinned CI actions, unstructured YAML parsing, or unaudited live writes, stop and migrate it to the repository's tracked task system, pinned validation gate, real parser, and explicit operator confirmation.

## Recovery

- Start by recording the baseline: branch, remotes, recent commits, dirty files, validation commands, and base diff.
- If validation fails after an edit, reduce the diff to the smallest subsystem and rerun the targeted test for that subsystem before continuing.
- If unrelated files change while working, assume another worker owns them and do not revert them.
- If a live-write or destructive operation is discovered in a script or doc path, disable the automatic path, document the manual migration, and require explicit confirmation before any future write.
- Before commit, review `git diff --stat`, `git diff --name-status`, `git diff --check`, and the final validation output.

## Classification And Retention

The sprint output should be safe for public repository retention by default. Do not commit:

- Secrets, tokens, private keys, bearer values, customer exports, tenant dumps, connector payloads, or local auth files.
- Local machine paths, hidden backups, generated archives, or cache directories.
- Sensitive subagent notes or customer evidence unless the user explicitly authorizes that exact content and retention location.

Retain only source, tests, docs, validation fixtures, and redacted examples needed to reproduce the hardening result.

## Limitations

- The skill cannot certify a target repo that has no reliable tests, no documented public contract, or missing runtime dependencies.
- It does not replace product security review, live integration certification, or monitored rollout.
- External link availability checks should be deterministic or optional; do not make routine validation depend on flaky network calls.
- The final quality still depends on the target repository's own testability and the operator's scope constraints.

## Certification

This skill is rated org-baseline ready in `docs/production-readiness-evaluation.md`, not fully certified for live production integration. A 10/10 certification would require live-system certification, monitored rollout, and production telemetry outside this no-live-write hardening pass.

## Validation

```bash
make validate
make secrets
python3 tools/validate_repo.py
```

Run `make validate-online` separately. Network failures must be reported, but they are not part of the deterministic PR gate.
