import contextlib
import csv
import importlib.util
import io
import json
import stat
import subprocess
import sys
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
            self.assertEqual(list(Path(tmp).glob(".contacts.csv.*.tmp")), [])
            self.assertEqual(stat.S_IMODE(store.stat().st_mode), 0o600)

    def test_export_and_import_guard_against_csv_injection_and_duplicate_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            store = tmp_path / "contacts.csv"
            exported = tmp_path / "export.csv"
            exported_again = tmp_path / "export-again.csv"

            code, stdout, stderr = self.run_cli(
                store,
                "add",
                "--account",
                "=Malicious",
                "--name",
                "@Alice",
                "--role",
                "+CFO",
                "--email",
                "alice@example.com",
            )
            self.assertEqual(code, 0, stderr)

            with store.open(newline="", encoding="utf-8") as handle:
                stored_row = next(csv.DictReader(handle))
            self.assertEqual(stored_row["account name"], "=Malicious")
            self.assertEqual(stored_row["customer name"], "@Alice")
            self.assertEqual(stored_row["customer role"], "+CFO")

            code, stdout, stderr = self.run_cli(store, "export", "--output", str(exported))
            self.assertEqual(code, 0, stderr)
            with exported.open(newline="", encoding="utf-8") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["account name"], "'=Malicious")
            self.assertEqual(row["customer name"], "'@Alice")
            self.assertEqual(row["customer role"], "'+CFO")

            code, stdout, stderr = self.run_cli(store, "list", "--format", "json")
            self.assertEqual(code, 0, stderr)
            listed = json.loads(stdout)[0]
            self.assertEqual(listed["account name"], "=Malicious")
            self.assertEqual(listed["customer name"], "@Alice")

            code, stdout, stderr = self.run_cli(
                store, "export", "--output", str(exported_again)
            )
            self.assertEqual(code, 0, stderr)
            with exported_again.open(newline="", encoding="utf-8") as handle:
                repeated_export = next(csv.DictReader(handle))
            self.assertEqual(repeated_export["account name"], "'=Malicious")
            self.assertNotEqual(repeated_export["account name"], "''=Malicious")

            code, stdout, stderr = self.run_cli(store, "export", "--output", str(store))
            self.assertEqual(code, 1)
            self.assertIn("must not overwrite the contact store", stderr)
            with store.open(newline="", encoding="utf-8") as handle:
                self.assertEqual(next(csv.DictReader(handle))["account name"], "=Malicious")

            duplicate = tmp_path / "duplicate.csv"
            duplicate.write_text(
                "Account,Account Name,Name,Role,Email\n"
                "Acme,Acme,Alice,CFO,alice@example.com\n",
                encoding="utf-8",
            )
            code, stdout, stderr = self.run_cli(store, "import", str(duplicate))
            self.assertEqual(code, 1)
            self.assertIn("Duplicate logical header", stderr)

    def test_new_store_has_private_schema_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "contacts.csv"

            code, stdout, stderr = self.run_cli(store, "init")

            self.assertEqual(code, 0, stderr)
            sidecar = self.module.metadata_path(store)
            metadata = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertEqual(metadata["schema"], self.module.CONTACT_STORE_SCHEMA)
            self.assertEqual(metadata["schema_version"], "2.0")
            self.assertIsNone(metadata["migration"])
            self.assertEqual(stat.S_IMODE(store.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(sidecar.stat().st_mode), 0o600)

    def test_legacy_store_fails_closed_until_explicit_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "contacts.csv"
            store.write_text(
                "account name,customer name,customer role,customer email address\n"
                "Acme,Alice Lee,CFO,alice@example.com\n",
                encoding="utf-8",
            )

            code, stdout, stderr = self.run_cli(store, "list")
            self.assertEqual(code, 1)
            self.assertIn("Legacy unversioned contact store", stderr)
            self.assertIn("migrate", stderr)

            code, stdout, stderr = self.run_cli(store, "migrate")
            self.assertEqual(code, 0, stderr)
            self.assertIn("schema 2.0", stdout)
            sidecar = self.module.metadata_path(store)
            metadata = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertEqual(
                metadata["migration"]["from_schema_version"], "legacy-unversioned"
            )
            self.assertTrue(metadata["migration"]["migrated_at"].endswith("Z"))

            code, stdout, stderr = self.run_cli(store, "list", "--format", "json")
            self.assertEqual(code, 0, stderr)
            rows = json.loads(stdout)
            self.assertEqual(rows[0]["record type"], "customer")
            self.assertEqual(stat.S_IMODE(store.stat().st_mode), 0o600)

    def test_same_email_does_not_merge_different_account_or_type_scopes(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "contacts.csv"
            contacts = [
                ("Acme", "customer", "Alice Acme"),
                ("Beta", "customer", "Alice Beta"),
                ("Acme", "uipath", "Alice UiPath"),
            ]
            for account, record_type, name in contacts:
                code, stdout, stderr = self.run_cli(
                    store,
                    "add",
                    "--account",
                    account,
                    "--record-type",
                    record_type,
                    "--name",
                    name,
                    "--email",
                    "alice@example.com",
                )
                self.assertEqual(code, 0, stderr)
                self.assertIn("added", stdout)

            code, stdout, stderr = self.run_cli(store, "list", "--format", "json")
            self.assertEqual(code, 0, stderr)
            rows = json.loads(stdout)
            self.assertEqual(len(rows), 3)
            self.assertEqual(
                {(row["account name"], row["record type"]) for row in rows},
                {("Acme", "customer"), ("Beta", "customer"), ("Acme", "uipath")},
            )

    def test_duplicate_scoped_identities_and_malformed_emails_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            store = tmp_path / "contacts.csv"
            duplicate = tmp_path / "duplicate-identities.csv"
            duplicate.write_text(
                "Account,Type,Name,Role,Email\n"
                "Acme,Customer,Alice,CFO,alice@example.com\n"
                "Acme,Customer,Alice,Finance Lead,alice2@example.com\n",
                encoding="utf-8",
            )

            code, stdout, stderr = self.run_cli(store, "import", str(duplicate))
            self.assertEqual(code, 1)
            self.assertIn("duplicate scoped identity", stderr)

            code, stdout, stderr = self.run_cli(
                store,
                "add",
                "--account",
                "Acme",
                "--name",
                "Malformed",
                "--email",
                "alice@@example.com",
            )
            self.assertEqual(code, 1)
            self.assertIn("exactly one '@'", stderr)

    def test_lock_timeout_fails_without_removing_an_active_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "contacts.csv"

            with self.module.StoreLock(store, timeout_seconds=1):
                code, stdout, stderr = self.run_cli(
                    store,
                    "--lock-timeout",
                    "0.01",
                    "--lock-poll-interval",
                    "0.005",
                    "list",
                )
                self.assertEqual(code, 1)
                self.assertIn("Timed out waiting for contact store lock", stderr)
                self.assertTrue(self.module.lock_directory_path(store).is_dir())

            self.assertFalse(self.module.lock_directory_path(store).exists())

    def test_concurrent_processes_do_not_lose_contact_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "contacts.csv"

            def command(name: str, email: str):
                return [
                    sys.executable,
                    str(SCRIPT),
                    "--store",
                    str(store),
                    "--lock-timeout",
                    "5",
                    "add",
                    "--account",
                    "Acme",
                    "--name",
                    name,
                    "--email",
                    email,
                ]

            processes = [
                subprocess.Popen(
                    command("Alice", "alice@example.com"),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                ),
                subprocess.Popen(
                    command("Bob", "bob@example.com"),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                ),
            ]
            for process in processes:
                stdout, stderr = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, stdout + stderr)

            code, stdout, stderr = self.run_cli(store, "list", "--format", "json")
            self.assertEqual(code, 0, stderr)
            self.assertEqual(
                {row["customer name"] for row in json.loads(stdout)}, {"Alice", "Bob"}
            )


if __name__ == "__main__":
    unittest.main()
