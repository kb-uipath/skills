import csv
import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prepare_customer_email_csv.py"


def load_module():
    spec = importlib.util.spec_from_file_location("prepare_customer_email_csv", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PrepareCustomerEmailCsvTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_normalizes_alias_headers_and_marks_missing_email_for_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "contacts.csv"
            output = tmp_path / "normalized.csv"
            source.write_text(
                "Account,Type,Name,Title,Email\n"
                "Acme,Client,Alice Lee,CFO,alice@example.com\n"
                "Acme,Internal,Bob Ray,Account Executive,\n",
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = self.module.main([str(source), "--output", str(output)])

            self.assertEqual(result, 0)
            with output.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["record type"], "customer")
            self.assertEqual(rows[0]["needs review"], "no")
            self.assertEqual(rows[0]["sourcing confidence"], "provided")
            self.assertEqual(rows[1]["record type"], "uipath")
            self.assertEqual(rows[1]["needs review"], "yes")
            self.assertEqual(rows[1]["source type"], "none")

    def test_missing_required_header_fails_cleanly(self):
        with self.assertRaisesRegex(ValueError, "Missing required column"):
            self.module.build_header_map(["Account", "Name", "Title"])

    def test_duplicate_logical_header_fails_cleanly(self):
        with self.assertRaisesRegex(ValueError, "Duplicate logical header"):
            self.module.build_header_map(
                [
                    "Account",
                    "Account Name",
                    "Name",
                    "Title",
                    "Email",
                ]
            )

    def test_customer_rows_with_internal_domain_need_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "contacts.csv"
            output = tmp_path / "normalized.csv"
            source.write_text(
                "Account,Type,Name,Title,Email\n"
                "Acme,Customer,Customer Alias,Program Owner,alias@uipath.com\n",
                encoding="utf-8",
            )

            result = self.module.main([str(source), "--output", str(output)])

            self.assertEqual(result, 0)
            with output.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["needs review"], "yes")
            self.assertEqual(rows[0]["sourcing confidence"], "low")
            self.assertIn("UiPath domain", rows[0]["sourcing evidence"])


if __name__ == "__main__":
    unittest.main()
