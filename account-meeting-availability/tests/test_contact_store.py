import contextlib
import csv
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "contact_store.py"


def load_module():
    spec = importlib.util.spec_from_file_location("contact_store", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ContactStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def run_cli(self, store: Path, *args: str):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = self.module.main(["--store", str(store), *args])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_add_upsert_list_and_delete_use_explicit_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "contacts.csv"

            code, stdout, stderr = self.run_cli(
                store,
                "add",
                "--account",
                "Acme",
                "--name",
                "Alice Lee",
                "--role",
                "CFO",
                "--email",
                "alice@example.com",
            )
            self.assertEqual(code, 0, stderr)
            self.assertIn("added", stdout)

            code, stdout, stderr = self.run_cli(
                store,
                "add",
                "--account",
                "Acme",
                "--name",
                "Alice Lee",
                "--role",
                "Chief Financial Officer",
                "--email",
                "alice@example.com",
            )
            self.assertEqual(code, 0, stderr)
            self.assertIn("updated", stdout)

            code, stdout, stderr = self.run_cli(store, "list", "--format", "json")
            self.assertEqual(code, 0, stderr)
            rows = json.loads(stdout)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["customer role"], "Chief Financial Officer")

            code, stdout, stderr = self.run_cli(
                store,
                "delete",
                "--match-email",
                "alice@example.com",
            )
            self.assertEqual(code, 0, stderr)
            self.assertIn("deleted contact", stdout)

            code, stdout, stderr = self.run_cli(store, "list", "--format", "json")
            self.assertEqual(code, 0, stderr)
            self.assertEqual(json.loads(stdout), [])

    def test_import_skip_existing_export_and_ambiguous_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            store = tmp_path / "contacts.csv"
            source = tmp_path / "import.csv"
            exported = tmp_path / "export.csv"
            source.write_text(
                "Account,Type,Name,Role,Email\n"
                "Acme,Customer,Alice Lee,CFO,alice@example.com\n"
                "Acme,Uipath,Bob Ray,Account Executive,bob@example.com\n",
                encoding="utf-8",
            )

            code, stdout, stderr = self.run_cli(store, "import", str(source))
            self.assertEqual(code, 0, stderr)
            self.assertIn("2 added", stdout)

            code, stdout, stderr = self.run_cli(
                store,
                "import",
                str(source),
                "--mode",
                "skip-existing",
            )
            self.assertEqual(code, 0, stderr)
            self.assertIn("2 skipped", stdout)

            code, stdout, stderr = self.run_cli(
                store,
                "delete",
                "--match-account",
                "Acme",
            )
            self.assertEqual(code, 1)
            self.assertIn("delete requires exactly one match; found 2", stderr)

            code, stdout, stderr = self.run_cli(store, "export", "--output", str(exported))
            self.assertEqual(code, 0, stderr)
            with exported.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]["record type"], "uipath")

    def test_write_rows_uses_atomic_temp_file_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "contacts.csv"
            rows = [
                {
                    "account name": "Acme",
                    "record type": "customer",
                    "customer name": "Alice Lee",
                    "customer role": "CFO",
                    "customer email address": "alice@example.com",
                }
            ]

            self.module.write_rows(store, rows)
            self.module.write_rows(
                store,
                [
                    {
                        **rows[0],
                        "customer role": "Chief Financial Officer",
                    }
                ],
            )

            with store.open(newline="", encoding="utf-8") as handle:
                stored = list(csv.DictReader(handle))
            self.assertEqual(stored[0]["customer role"], "Chief Financial Officer")
            self.assertEqual(list(Path(tmp).glob(".contacts.*.csv")), [])


if __name__ == "__main__":
    unittest.main()
