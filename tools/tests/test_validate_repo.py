from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = REPO_ROOT / "tools" / "validate_repo.py"
SPEC = importlib.util.spec_from_file_location("validate_repo", VALIDATOR_PATH)
validate_repo = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validate_repo)


PINNED_SHA = "34e114876b0b11c390a56381ad16ebd13914f8d5"


class ValidateRepoTests(unittest.TestCase):
    def write(self, root: Path, relative_path: str, text: str) -> None:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def create_minimal_repo(self, root: Path) -> None:
        self.write(
            root,
            "README.md",
            """# Test skills

## Runtime And Validation

Last verified: 2026-07-10

[Skill](./repo-hardening-sprint/SKILL.md) and [docs](./docs/repo-hardening-sprint.md).

## Governance
""",
        )
        self.write(
            root,
            "docs/README.md",
            """# Docs

## Documentation Contract

Last verified: 2026-07-10

| Skill | Docs |
| --- | --- |
| repo-hardening-sprint | [repo-hardening-sprint.md](./repo-hardening-sprint.md) |
""",
        )
        self.write(
            root,
            "docs/production-readiness-evaluation.md",
            """# Production Readiness Evaluation

## Readiness Axes

Last verified: 2026-07-10
""",
        )
        self.write(
            root,
            "docs/repo-hardening-sprint.md",
            """# repo-hardening-sprint

## Inputs

Repository path.

## Prompt

```text
Use $repo-hardening-sprint on this repository.
```

## Outputs

Scoped changes.

## Safety

No live writes without explicit authorization.

## Validation

```bash
python3 tools/validate_repo.py
```

## Runtime And Dependencies

Python 3.11 and PyYAML.

## Versioned Contract

Contract version: repo-hardening-sprint/v1.

## Runnable Example

```bash
python3 tools/validate_repo.py
```

## Recovery

Re-run validation and inspect the diff.

## Classification And Retention

Do not commit secrets.

## Limitations

No live certification.

## Certification

Not certified for live production writes.

Last verified: 2026-07-10
""",
        )
        self.write(
            root,
            "repo-hardening-sprint/SKILL.md",
            """---
name: repo-hardening-sprint
description: Run safe repository hardening sprints.
---

# Repo Hardening Sprint
""",
        )
        self.write(
            root,
            "repo-hardening-sprint/agents/openai.yaml",
            """interface:
  display_name: "Repo Hardening Sprint"
  short_description: "Safe repository hardening gates"
  default_prompt: "Use $repo-hardening-sprint on this repository."
""",
        )
        self.write(
            root,
            ".github/workflows/validate.yml",
            f"""name: Validate
on:
  push:
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@{PINNED_SHA}
""",
        )
        self.write(root, "requirements-dev.txt", "PyYAML==6.0.3\n")
        self.write(root, "LICENSE", "Apache License\nVersion 2.0\n")
        self.write(root, "CONTRIBUTING.md", "# Contributing\n")
        self.write(root, "CODEOWNERS", "* @kb-uipath\n")
        self.write(root, "SUPPORT.md", "# Support\n")
        self.write(
            root,
            "SECURITY.md",
            """# Security

## Reporting A Vulnerability

Report sensitive findings through a private advisory.
""",
        )

    def run_validator(self, mutate=None) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.create_minimal_repo(root)
            if mutate is not None:
                mutate(root)
            return validate_repo.run_validation(root)

    def assert_error_contains(self, errors: list[str], expected: str) -> None:
        self.assertTrue(
            any(expected in error for error in errors),
            f"expected {expected!r} in errors: {errors}",
        )

    def test_valid_minimal_repo_passes(self) -> None:
        self.assertEqual([], self.run_validator())

    def test_rejects_invalid_yaml(self) -> None:
        def mutate(root: Path) -> None:
            self.write(root, "repo-hardening-sprint/agents/openai.yaml", "interface: [broken\n")

        self.assert_error_contains(self.run_validator(mutate), "invalid YAML")

    def test_rejects_unpinned_workflow_action(self) -> None:
        def mutate(root: Path) -> None:
            self.write(
                root,
                ".github/workflows/validate.yml",
                """name: Validate
on:
  push:
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
""",
            )

        self.assert_error_contains(self.run_validator(mutate), "pinned to a 40-char SHA")

    def test_rejects_broken_local_anchor(self) -> None:
        def mutate(root: Path) -> None:
            self.write(root, "README.md", "# Test\n\n## Runtime And Validation\n\nLast verified: 2026-07-10\n\n[bad](./docs/repo-hardening-sprint.md#missing)\n\n[Skill](./repo-hardening-sprint/SKILL.md) [docs](./docs/repo-hardening-sprint.md)\n\n## Governance\n")

        self.assert_error_contains(self.run_validator(mutate), "broken anchor")

    def test_rejects_local_path_and_secret_like_assignment(self) -> None:
        def mutate(root: Path) -> None:
            local_path = "/Users" + "/person/project"
            secret_name = "api" + "_key"
            secret_value = "abcdefghijklmnopqrstuvwxyz"
            self.write(root, "docs/leak.md", f"home={local_path}\n{secret_name} = {secret_value}\n")

        errors = self.run_validator(mutate)
        self.assert_error_contains(errors, "local absolute path leak")
        self.assert_error_contains(errors, "possible secret material")

    def test_rejects_non_exact_dependency_pin(self) -> None:
        def mutate(root: Path) -> None:
            self.write(root, "requirements-dev.txt", "PyYAML>=6,<7\n")

        self.assert_error_contains(self.run_validator(mutate), "exact == pin")

    def test_rejects_http_external_link(self) -> None:
        def mutate(root: Path) -> None:
            scheme = "http" + "://"
            self.write(root, "docs/external.md", f"[bad]({scheme}example.com)\nraw {scheme}example.org\n")

        self.assert_error_contains(self.run_validator(mutate), "external link must use https")


if __name__ == "__main__":
    unittest.main()
