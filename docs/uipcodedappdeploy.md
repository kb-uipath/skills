# uipcodedappdeploy

Create a reviewable, hashed plan before packaging, publishing, and deploying a UiPath coded app with the native `uip` CLI.

| Field | Value |
| --- | --- |
| Skill name | `uipcodedappdeploy` |
| Plan contract | `uipcodedappdeploy.plan` v1.0 |
| Receipt contract | `uipcodedappdeploy.receipt` v1.0 |
| Result contract | `uipcodedappdeploy.result` v1.0 |
| Certification status | Offline hardened; not live-certified |
| Last verified | 2026-07-10 |

## When To Use

Use this skill to increment a coded app version, refresh its lock file, test and build it, then run `uip codedapp pack`, `publish`, and `deploy`. Planning is the default. Live deployment requires a persisted plan and a separate `--execute` invocation.

## Runtime And Dependencies

- Python 3.11 or later. The helper uses the standard-library `tomllib` parser and has no third-party Python dependencies.
- A project root with valid UTF-8 `pyproject.toml` and `uipath.json` files.
- `uv` when `uv.lock` exists or tests are enabled. The default test command is `uv run python -m pytest -q`.
- Node.js and npm when `app/package.json` exists. The default build command is `npm run build` in `app/`.
- UiPath CLI with the coded app tool available and an authenticated identity authorized for the selected nonproduction or production target.
- An HTTPS UiPath base origin and an Orchestrator folder key formatted as a GUID. A folder key is mandatory for execution.

The helper does not install runtimes, tools, dependencies, or credentials. Confirm the exact installed `uip codedapp` command surface before an opt-in certification run because CLI tool versions can change independently.

## Inputs

- Absolute coded app project root.
- Version bump part or explicit greater SemVer.
- HTTPS target origin and any required tenant or organization identifiers.
- Explicit folder-key GUID for an executable plan.
- Optional project-relative dist, package/app metadata, and HTTPS verification URL overrides.
- Explicit risk acceptance for `--skip-tests` or `--skip-app-build`, when applicable.

## Versioned Inputs

Plan v1.0 validates:

- `[project].name`, `[project].version`, optional description, and optional authors in `pyproject.toml` using `tomllib`.
- Strict SemVer 2.0.0 syntax and a new version with greater precedence. A build-metadata-only change is rejected.
- A non-empty JSON object in `uipath.json`; known `clientId` and `projectId` values must be non-empty strings. `--reuse-client` requires `clientId`.
- A project-relative dist path that cannot be absolute, resolve to the project root, traverse with `..`, or escape through a symlink.
- HTTPS target and verification URLs without embedded credentials. Retained verification URLs cannot contain query strings.
- Normalized package, app, author, main-file, app-type, tenant, organization, and folder-key values.

The input hash covers exactly `pyproject.toml` and `uipath.json`. The plan also contains the expected hash after the atomic version update. Source files, built assets, `uv.lock`, and `app/package.json` are not part of the input hash.

## Versioned Outputs

### Plan v1.0

`--format json` writes a JSON plan to standard output. `--plan-output <path>` additionally writes that plan atomically with mode `0600`. The document contains normalized parameters, project-relative paths, the allowlisted stage sequence, initial and versioned input hashes, and a SHA-256 plan hash.

Default planning does not modify project files, invoke `uv`, `npm`, or `uip`, resolve folder names, or contact a URL. `--plan-output` is the only planning write and occurs only when explicitly requested.

### Receipt v1.0

Execution creates `<plan>.receipt.json` atomically with mode `0600`. It records the plan and input hashes plus stage names, effects, timestamps, and status. Commands, environment variables, subprocess output, URL response data, and detailed errors are omitted. The receipt has its own SHA-256 hash.

### Result v1.0

Successful execution emits a text summary or, with `--format json`, a result containing status, version transition, target origin, plan hash, and receipt path.

Hashes detect accidental changes; they are not signatures and do not establish who approved a plan.

## Prompt

```text
Use $uipcodedappdeploy to validate this coded app and create a hashed JSON deployment plan for review. Do not modify project files or perform pack, publish, deploy, or URL verification until I explicitly approve execution of that persisted plan.
```

## Runnable Example

From the skills repository root, set a real coded app project and a reviewed folder GUID:

```bash
PROJECT_ROOT=/absolute/path/to/coded-app
PLAN="$PROJECT_ROOT/deploy-plan.json"

python3.11 uipcodedappdeploy/scripts/uipcodedappdeploy.py \
  --project-root "$PROJECT_ROOT" \
  --target-url https://alpha.uipath.com \
  --tenant-name '<nonproduction-tenant>' \
  --folder-key 11111111-2222-3333-4444-555555555555 \
  --verify-url https://example-org.uipath.host/example-app \
  --format json \
  --plan-output "$PLAN"

python3.11 uipcodedappdeploy/scripts/uipcodedappdeploy.py \
  --plan "$PLAN" \
  --format json
```

Review the target, version, folder key, commands, hashes, and blockers in the persisted plan. Execution is a separate, explicit external-write step:

```bash
python3.11 uipcodedappdeploy/scripts/uipcodedappdeploy.py \
  --plan "$PLAN" \
  --execute \
  --format json
```

The execution order is version, `uv lock` when applicable, tests, app build, dist validation, CLI probe, pack, publish, deploy, and optional URL verification. The version is intentionally written before lock, test, and build so generated metadata and packages use one version.

## Safety Boundaries

- Direct `--execute` is prohibited. Only `--plan <file> --execute` can reach write stages.
- A valid folder GUID must already be embedded in the hashed plan. Execution never resolves folder names.
- Plan output cannot replace project manifests, lock files, dist contents, or an existing non-plan file.
- Plan-time options cannot override a loaded plan. Regenerate the plan when any input changes.
- Loaded stages are rebuilt from structured fields and compared with an allowlist before execution; a rehashed arbitrary command is rejected.
- `pyproject.toml` is written atomically, and the parsed document must differ only at `[project].version`.
- `--folder`, `--tenant`, `--my-workspace`, `--pack-nolock`, `--use-deploy-command`, and `--offline` fail closed with migration guidance.
- `--skip-tests` and `--skip-app-build` are planning-time risk acceptances. Do not use them for certification or production release unless an equivalent validated stage ran elsewhere.
- Secrets are not accepted as arguments or persisted. Authenticate with the UiPath CLI; never put tokens in plan fields or verification URLs.

## Failure Recovery

| Failure | Recovery |
| --- | --- |
| Manifest, SemVer, path, URL, plan hash, or input hash validation | No deployment stage runs. Correct the source and generate a new plan. |
| Missing dist or main file when the build stage is disabled | No version or receipt is written. Build the app or regenerate a plan with the build stage enabled. |
| Lock, test, build, dist, probe, or pack failure | The version may already be updated. Fix the local failure, leave the plan and receipt intact, then run `--plan <file> --execute --resume`. |
| Publish or deploy exits with failure | Inspect the console and live target before using `--resume`; retrying an external stage can encounter a partial remote side effect. |
| Process stops while publish or deploy is marked `running` | Resume fails closed because the remote outcome is indeterminate. Verify the target manually and create an operator-reviewed recovery plan; do not edit the receipt. |
| Verification fails | Deployment may already be complete. Fix reachability or the URL, then `--resume` retries the failed verification stage only. |
| Plan or receipt hash mismatch | Treat the artifact as untrusted. Restore from a trusted copy or reconcile project and remote state before generating a new versioned plan. |

There is no automatic rollback. A successful publish or deploy is never reversed by this helper.

## Data Classification And Retention

- **Project manifests:** potentially internal source metadata. They are read locally and are not copied into plans; only selected metadata and hashes are retained.
- **Plan:** internal deployment metadata. It contains an absolute local path, package/app names, tenant or organization identifiers, a folder GUID, target URLs, and commands. Store it with release artifacts under the same access policy.
- **Receipt:** internal operational metadata. It is redacted but still contains hashes, stage timing, and release status.
- **Secrets:** prohibited. The helper does not retain credentials, environment variables, command output, response bodies, or detailed errors.
- **Telemetry:** none. The helper sends no telemetry of its own.

The helper does not auto-delete artifacts. Retain the plan and receipt only for the release audit window required by the owning organization, then delete them with the surrounding release artifacts. Do not retain failed plans containing obsolete tenant, folder, or local-path metadata longer than required for recovery.

## Known Limitations

- `uipath.json` validation is structural, not a full version-specific UiPath product schema validation.
- Input hashes do not cover source code, dist contents, lock files, npm manifests, or installed tool versions. Tests/build and the live CLI remain the authoritative validators for those inputs.
- URL verification checks only anonymous HTTPS reachability and status below 400. It does not authenticate, validate page content, or prove the expected version is serving.
- Plan and receipt hashes provide integrity detection, not signing, identity, approval, or non-repudiation.
- Resume cannot prove whether a failed external command produced a partial remote side effect. An interrupted `running` publish/deploy is blocked for manual reconciliation.
- The helper does not provide rollback, package cleanup, deployment deletion, or environment promotion.

## Opt-In Nonproduction Certification

Live certification is intentionally not part of the repository test suite. To certify a specific CLI/tool version, use a disposable app with synthetic data, a dedicated least-privilege identity, and an isolated nonproduction tenant/folder. Record `python3.11 --version`, `uip --version`, and `uip codedapp --help`; generate and peer-review the plan; execute it with `--verify-url`; confirm the deployed app and folder in UiPath; inspect the redacted receipt; then remove the disposable deployment according to local policy.

Do not treat one nonproduction run as production certification. Record the tested CLI version, tenant class, date, operator, result, and any cleanup evidence in the owning release system.

## Validation

```bash
python3.11 -m unittest discover -s uipcodedappdeploy/tests -p 'test_*.py'
python3 tools/validate_repo.py
```

The unit suite stubs subprocess and URL execution. It must never call a live `uip`, `uv`, `npm`, or HTTP endpoint.
