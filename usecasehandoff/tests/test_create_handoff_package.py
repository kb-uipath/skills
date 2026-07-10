import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "create_handoff_package.py"


def load_module():
    spec = importlib.util.spec_from_file_location("create_handoff_package", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CreateHandoffPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def write_ready_contents(self, package: Path):
        files = {
            "executive-summary.md": """# Executive Summary

Use case: Permit Intake Automation
Account/team: Fixture Agency
Prepared: 2026-07-01

## Business Problem

Permit intake queues rely on manual review and status follow-up.

## Operational Impact

The team reports weekly backlog review and repeated status handling.

## Solution Workflow

Intake records are validated, queued, routed for exception review, and reported through the delivery dashboard.

## Decision Ask

Delivery Lead approves sprint-one build scope by 2026-07-08.
""",
            "analysis.md": """# Analysis

Use case: Permit Intake Automation
Account/team: Fixture Agency
Prepared: 2026-07-01

## Current State

Staff manually review permit intake records, supported by E1.

## Process Pain Points

Manual review creates avoidable queue delay for permit staff.

## Systems And Constraints

The pilot uses fixture records and preserves human approval before any system write.

## Value Drivers

The measurable driver is intake cycle time; the baseline remains an open validation item.

## Assumptions And Validation Questions

Assumption A1: representative fixtures cover the first sprint. Delivery Lead validates coverage before build.
""",
            "evidence-ledger.md": """# Evidence Ledger

Use case: Permit Intake Automation
Account/team: Fixture Agency
Prepared: 2026-07-01

| Claim ID | Claim or metric | Evidence tier | Source title/link | Source date | Owner | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| E1 | Permit intake requires repeated manual status handling | Source-backed | Intake workshop notes | 2026-06-30 | Delivery Lead | Used for scope only |

## Open Evidence Gaps

- No unresolved evidence gaps for sprint-one scope.
""",
            "delivery-plan.md": """# Delivery Plan

Use case: Permit Intake Automation
Account/team: Fixture Agency
Prepared: 2026-07-01

## Current State

Analysts review permit intake records, verify required fields, and manually route exceptions.

## Target Workflow

The automation validates intake records, creates queue items, routes exceptions for human review, and records outcomes.

## Systems and Integrations

Permit intake form, queue storage, notification channel, and reporting dashboard.

## Data, Queue, and Exception Model

Queue items include permit id, submitter, status, validation result, and exception reason.

## Security, Audit, and Governance

Use named service credentials, least-privilege access, audit logs, and retention aligned to account policy.

## Delivery Phases

| Phase | Outcome | Owner | Acceptance criteria |
| --- | --- | --- | --- |
| 1 | Validated intake queue prototype | Delivery Lead | Five fixture records process with expected success and exception states |

## Test Strategy

Run unit, integration, exception, recovery, and UAT checks against fixture intake records before routing the package.

## First Sprint Backlog

- Delivery Lead builds queue schema and fixture-driven intake validation.

## Next Action

Delivery Lead schedules sprint planning on 2026-07-08.
""",
            "risk-register.md": """# Risk Register

Use case: Permit Intake Automation

| Risk | Impact | Mitigation | Owner | Status |
| --- | --- | --- | --- | --- |
| Source coverage narrows sprint scope | Delivery may miss edge cases | Confirm fixture set before build | Delivery Lead | Open |
""",
            "references.md": """# References

Use case: Permit Intake Automation

| Source | Type | Date | Link or path | Claims supported | Owner |
| --- | --- | --- | --- | --- | --- |
| Intake workshop notes | meeting notes | 2026-06-30 | docs/intake-workshop-notes.md | E1 | Delivery Lead |
""",
            "cover-message.md": """# Cover Message

Attached is the handoff package for Permit Intake Automation (Fixture Agency). It separates sourced scope, analysis, delivery work, and risks.

Next action: Delivery Lead schedules sprint planning on 2026-07-08.
""",
        }
        for filename, content in files.items():
            (package / filename).write_text(content, encoding="utf-8")

    def mark_ready(self, package: Path):
        self.module.write_manifest(
            package,
            "Permit Intake Automation",
            "Fixture Agency",
            "2026-07-01",
            self.module.DEFAULT_CLASSIFICATION,
            self.module.DEFAULT_RETENTION,
            "ready",
            self.module.scaffold_time("2026-07-01"),
            "2026-07-01T00:00:00Z",
        )

    def create_ready_package(self, tmp: str) -> Path:
        package = self.module.create_package(
            Path(tmp),
            "Permit Intake Automation",
            "Fixture Agency",
            "2026-07-01",
            slug="permit-intake",
        )
        self.write_ready_contents(package)
        self.mark_ready(package)
        return package

    def test_create_package_writes_deterministic_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = self.module.create_package(
                Path(tmp),
                "Permit Intake Automation",
                "Fixture Agency",
                "2026-07-01",
                slug="permit-intake",
            )

            self.assertEqual(package.name, "2026-07-01-permit-intake")
            expected = set(self.module.STABLE_PACKAGE_FILES)
            self.assertEqual({path.name for path in package.iterdir()}, expected)
            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema"], self.module.PACKAGE_SCHEMA)
            self.assertEqual(manifest["schema_version"], self.module.PACKAGE_SCHEMA_VERSION)
            self.assertEqual(manifest["account"], "Fixture Agency")
            self.assertEqual(manifest["status"], "scaffold")
            self.assertEqual(manifest["classification"], "internal")
            self.assertEqual(manifest["files"], list(self.module.STABLE_PACKAGE_FILES))
            self.assertEqual(set(manifest["hashes"]), set(self.module.CONTENT_FILES))
            self.assertTrue(manifest["no_send"])
            self.assertIn("No connector writes", manifest["safety"])
            self.assertIn("| Claim ID |", (package / "evidence-ledger.md").read_text(encoding="utf-8"))
            self.assertEqual(self.module.validate_package(package, level="scaffold"), [])
            self.assertNotEqual(self.module.validate_package(package), [])

    def test_cli_refuses_to_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = [
                sys.executable,
                str(SCRIPT),
                "--title",
                "Permit Intake Automation",
                "--account",
                "Fixture Agency",
                "--output-dir",
                tmp,
                "--date",
                "2026-07-01",
                "--slug",
                "permit-intake",
            ]

            first = subprocess.run(args, capture_output=True, text=True, check=False)
            second = subprocess.run(args, capture_output=True, text=True, check=False)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 1)
            self.assertIn("Package already exists", second.stderr)

    def test_validate_cli_fails_for_incomplete_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "bad-package"
            package.mkdir()
            (package / "README.md").write_text("# Bad\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--validate", str(package)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("missing required file", result.stderr)

    def test_validate_cli_passes_for_scaffold_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = self.module.create_package(
                Path(tmp),
                "Permit Intake Automation",
                "Fixture Agency",
                "2026-07-01",
                slug="permit-intake",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--validate", str(package), "--level", "scaffold"],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("scaffold level", result.stdout)

    def test_validate_cli_defaults_to_ready_and_rejects_empty_scaffold(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = self.module.create_package(
                Path(tmp),
                "Permit Intake Automation",
                "Fixture Agency",
                "2026-07-01",
                slug="permit-intake",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--validate", str(package)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("status must be 'ready'", result.stderr)
            self.assertIn("placeholder", result.stderr)

    def test_ready_validation_passes_for_completed_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = self.create_ready_package(tmp)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--validate", str(package)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("ready level", result.stdout)

    def test_ready_validation_rejects_completion_defects(self):
        cases = {
            "placeholder": (
                "executive-summary.md",
                lambda text: text + "\nTODO unresolved item\n",
                "placeholder",
            ),
            "uncited": (
                "evidence-ledger.md",
                lambda text: text.replace(
                    "| E1 | Permit intake requires repeated manual status handling | Source-backed | Intake workshop notes | 2026-06-30 | Delivery Lead | Used for scope only |",
                    "| E1 | Permit intake requires repeated manual status handling | Source-backed |  |  | Delivery Lead | Used for scope only |",
                ),
                "uncited",
            ),
            "ownerless": (
                "risk-register.md",
                lambda text: text.replace("| Source coverage narrows sprint scope | Delivery may miss edge cases | Confirm fixture set before build | Delivery Lead | Open |", "| Source coverage narrows sprint scope | Delivery may miss edge cases | Confirm fixture set before build |  | Open |"),
                "owner is empty",
            ),
            "empty acceptance": (
                "delivery-plan.md",
                lambda text: text.replace("| 1 | Validated intake queue prototype | Delivery Lead | Five fixture records process with expected success and exception states |", "| 1 | Validated intake queue prototype | Delivery Lead |  |"),
                "acceptance criteria is empty",
            ),
            "empty test": (
                "delivery-plan.md",
                lambda text: text.replace(
                    "## Test Strategy\n\nRun unit, integration, exception, recovery, and UAT checks against fixture intake records before routing the package.\n\n## First Sprint Backlog",
                    "## Test Strategy\n\n\n## First Sprint Backlog",
                ),
                "Test Strategy",
            ),
            "empty first sprint": (
                "delivery-plan.md",
                lambda text: text.replace(
                    "## First Sprint Backlog\n\n- Delivery Lead builds queue schema and fixture-driven intake validation.\n\n## Next Action",
                    "## First Sprint Backlog\n\n\n## Next Action",
                ),
                "First Sprint Backlog",
            ),
            "no action": (
                "cover-message.md",
                lambda text: text.replace("Next action: Delivery Lead schedules sprint planning on 2026-07-08.", "Next action:"),
                "concrete next action",
            ),
        }
        for name, (filename, mutate, expected_error) in cases.items():
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as tmp:
                    package = self.create_ready_package(tmp)
                    path = package / filename
                    path.write_text(mutate(path.read_text(encoding="utf-8")), encoding="utf-8")
                    self.mark_ready(package)

                    errors = self.module.validate_package(package)

                    self.assertTrue(
                        any(expected_error in error for error in errors),
                        f"{expected_error!r} not found in {errors}",
                    )

    def test_legacy_validation_fails_closed_and_migration_restores_scaffold_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "legacy-package"
            legacy.mkdir()
            (legacy / "README.md").write_text("# Legacy\n", encoding="utf-8")
            (legacy / "evidence-ledger.md").write_text(
                "# Evidence Ledger\n\n| Claim ID | Claim or metric | Evidence tier | Source title/link | Source date | Notes |\n| --- | --- | --- | --- | --- | --- |\n\n## Open Evidence Gaps\n\n- Legacy gap\n",
                encoding="utf-8",
            )
            (legacy / "delivery-plan.md").write_text(
                "# Delivery Plan\n\n## Current State\n\n## Target Workflow\n\n## Systems and Integrations\n\n## Delivery Phases\n\n## Test Strategy\n",
                encoding="utf-8",
            )
            (legacy / "risk-register.md").write_text("# Risk Register\n", encoding="utf-8")
            (legacy / "cover-message.md").write_text("# Cover Message\n", encoding="utf-8")
            (legacy / "manifest.json").write_text(
                json.dumps({"title": "Legacy Package", "account": "Fixture Agency", "date": "2026-07-01"}),
                encoding="utf-8",
            )

            errors = self.module.validate_package(legacy, level="scaffold")
            self.assertTrue(any("legacy six-file package detected" in error for error in errors))

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--migrate", str(legacy)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual({path.name for path in legacy.iterdir()}, set(self.module.STABLE_PACKAGE_FILES))
            self.assertEqual(self.module.validate_package(legacy, level="scaffold"), [])


if __name__ == "__main__":
    unittest.main()
