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


if __name__ == "__main__":
    unittest.main()
