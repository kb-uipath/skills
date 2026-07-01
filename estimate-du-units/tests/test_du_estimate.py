import argparse
import importlib.util
import subprocess
import sys
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "du_estimate.py"


def load_module():
    spec = importlib.util.spec_from_file_location("du_estimate", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DuEstimateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_parse_case_accepts_comma_formatted_transactions(self):
        label, transactions, pages = self.module.parse_case("base=1,234,2")

        self.assertEqual(label, "base")
        self.assertEqual(transactions, Decimal("1234"))
        self.assertEqual(pages, Decimal("2"))

    def test_parse_case_rejects_malformed_or_empty_labels(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            self.module.parse_case("base")

        with self.assertRaises(argparse.ArgumentTypeError):
            self.module.parse_case("=100,1")

    def test_formatting_rounds_and_adds_thousands_separators(self):
        self.assertEqual(self.module.fmt(Decimal("1234.56")), "1,234.6")
        self.assertEqual(self.module.fmt(Decimal("1000.0")), "1,000")

    def test_cli_prints_markdown_for_base_and_extra_rates(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--case",
                "base=1,234,2",
                "--ai-rate",
                "1",
                "--platform-rate",
                "0.2",
                "--extra-ai-rate",
                "0.5",
                "--extra-platform-rate",
                "0.1",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "| base | 1,234 | 2 | 3,702 | 740.4 |",
            result.stdout,
        )
        self.assertIn("AI rate/page: 1.5", result.stdout)
        self.assertIn("Platform rate/page: 0.3", result.stdout)

    def test_cli_supports_multiple_document_scenarios(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--case",
                "invoices=12,000,2",
                "--case",
                "claims=5,000,4",
                "--ai-rate",
                "1",
                "--platform-rate",
                "0.2",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("| invoices | 12,000 | 2 | 24,000 | 4,800 |", result.stdout)
        self.assertIn("| claims | 5,000 | 4 | 20,000 | 4,000 |", result.stdout)

    def test_cli_allows_zero_du_when_du_does_not_apply(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--case",
                "api-only=1000,0",
                "--ai-rate",
                "0",
                "--platform-rate",
                "0",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("| api-only | 1,000 | 0 | 0 | 0 |", result.stdout)
        self.assertIn("AI rate/page: 0", result.stdout)

    def test_negative_volumes_and_rates_are_rejected(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            self.module.parse_case("bad=-1,2")

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--case",
                "base=100,1",
                "--ai-rate",
                "-1",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("value cannot be negative", result.stderr)

    def test_decimal_pages_and_rates_are_supported(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--case",
                "mixed=100.5,1.5",
                "--ai-rate",
                "0.5",
                "--platform-rate",
                "0.25",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("| mixed | 100.5 | 1.5 | 75.4 | 37.7 |", result.stdout)


if __name__ == "__main__":
    unittest.main()
