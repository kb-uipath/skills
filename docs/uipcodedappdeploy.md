# uipcodedappdeploy

Plan and execute UiPath coded app packaging, publish, and deploy commands through the native `uip` CLI.

## When To Use

Use this skill when Codex needs to increment a coded app project version, validate/build the app, pack it, publish it, and deploy it to UiPath Automation Cloud.

## Inputs

- Project root containing `pyproject.toml`.
- Target URL, tenant name or ID, and org name or ID as required.
- Folder name or folder key for deploy.
- Version bump part or explicit version.
- Whether to run dry-run planning or `--execute`.

## Prompt

```text
Use $uipcodedappdeploy for this coded app project. Plan the version bump and pack/publish/deploy commands in dry-run mode first, and do not modify files or deploy unless I approve --execute.
```

## Outputs

- Dry-run command plan by default.
- Version bump in `pyproject.toml` only when `--execute` is passed.
- `uip codedapp pack`, `publish`, and `deploy` command sequence.
- Folder key resolution when a folder name is provided.

## Safety

- Dry-run is the default and must not edit files or deploy.
- `--execute` is required for file writes and live CLI commands.
- Do not use `--folder` and `--folder-key` together.
- Do not deploy to a personal workspace without an explicit folder or folder key.
- Do not print or store secrets.

## Validation

```bash
python3 -m unittest discover -s uipcodedappdeploy/tests -p 'test_*.py'
python3 tools/validate_repo.py
```
