import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_gtm_output.py"


def load_module():
    spec = importlib.util.spec_from_file_location("validate_gtm_output", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


VALID_OUTPUT = """# Fixture Proposal

## Confirmed Scope

Organization: Fixture Agency

## Source Ledger

| Source ID | Source | Publisher | Date | URL | Supports |
| --- | --- | --- | --- | --- | --- |
| [S1] | Budget report | Fixture Agency | FY2026 | https://example.gov/budget | Program budget |

## Budget / Program Areas

| Area | Budget | Tier | Source |
| --- | ---: | --- | --- |
| Licensing | $10,000,000 | Documented | [S1] |

## Prioritized Use Cases

| Rank | Use case | Evidence |
| ---: | --- | --- |
| 1 | Intake triage | [S1] |

## Proposal Cards

### Intake Triage

Evidence: [S1]
Estimate tier: Derived
Validation required: confirm current intake volume and deployment availability.

## Assumptions and Validation Needed

- Confirm deployment context before naming capabilities.
"""


class ValidateGtmOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_valid_output_contract_passes(self):
        self.assertEqual(self.module.validate_text(VALID_OUTPUT), [])

    def test_missing_source_ledger_and_citation_fail(self):
        errors = self.module.validate_text(
            "## Confirmed Scope\n\n"
            "## Budget / Program Areas\n\n"
            "## Prioritized Use Cases\n\n"
            "## Proposal Cards\n\n"
            "Validation required: source gaps.\n"
            "## Assumptions and Validation Needed\n\n"
        )

        self.assertIn("missing required heading: ## Source Ledger", errors)
        self.assertIn("at least one source citation like [S1] is required", errors)

    def test_unsupported_overclaim_fails_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            markdown = Path(tmp) / "proposal.md"
            markdown.write_text(VALID_OUTPUT + "\nThis will save money with no risk.\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(markdown)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("unsupported overclaim", result.stderr)


if __name__ == "__main__":
    unittest.main()
