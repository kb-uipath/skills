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
            expected = {
                "README.md",
                "evidence-ledger.md",
                "delivery-plan.md",
                "risk-register.md",
                "cover-message.md",
                "manifest.json",
            }
            self.assertEqual({path.name for path in package.iterdir()}, expected)
            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["account"], "Fixture Agency")
            self.assertIn("No connector writes", manifest["safety"])
            self.assertIn("| Claim ID |", (package / "evidence-ledger.md").read_text(encoding="utf-8"))
            self.assertEqual(self.module.validate_package(package), [])

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

    def test_validate_cli_passes_for_scaffolded_package(self):
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

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Handoff package validated", result.stdout)


if __name__ == "__main__":
    unittest.main()
