import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "uipcodedappdeploy.py"
GUID = "11111111-2222-3333-4444-555555555555"


def load_module():
    spec = importlib.util.spec_from_file_location("uipcodedappdeploy", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_project(root: Path, version: str = "1.2.3") -> None:
    (root / "pyproject.toml").write_text(
        "[project]\n"
        'name = "fixture-app"\n'
        f'version = "{version}"\n'
        'description = "Fixture app"\n'
        'authors = [{ name = "Fixture Author" }]\n',
        encoding="utf-8",
    )


class UiPathCodedAppDeployTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def patched_module(self, capture_payload=None):
        calls = []
        captures = []
        original_run = self.module._run
        original_capture_json = self.module._capture_json

        def fake_run(cmd, cwd, env, dry_run):
            calls.append({"cmd": cmd, "cwd": cwd, "dry_run": dry_run})

        def fake_capture_json(cmd, cwd, env):
            captures.append({"cmd": cmd, "cwd": cwd})
            return capture_payload or {"Data": {"Key": GUID}}

        self.module._run = fake_run
        self.module._capture_json = fake_capture_json
        return calls, captures, original_run, original_capture_json

    def restore_module(self, original_run, original_capture_json):
        self.module._run = original_run
        self.module._capture_json = original_capture_json

    def test_dry_run_plans_commands_and_does_not_write_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            calls, captures, original_run, original_capture_json = self.patched_module()
            try:
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = self.module.main(
                        [
                            "--project-root",
                            str(root),
                            "--tenant-name",
                            "alpha",
                            "--folder-key",
                            GUID,
                            "--skip-tests",
                            "--skip-app-build",
                        ]
                    )
            finally:
                self.restore_module(original_run, original_capture_json)

            self.assertEqual(code, 0)
            self.assertIn('version = "1.2.3"', (root / "pyproject.toml").read_text())
            self.assertIn("Dry-run mode", stdout.getvalue())
            self.assertEqual(captures, [])
            self.assertEqual(calls[0]["cmd"], ["uip", "--version"])
            self.assertFalse(calls[0]["dry_run"])
            planned = [call["cmd"] for call in calls[1:]]
            self.assertEqual([cmd[:3] for cmd in planned], [["uip", "codedapp", "pack"], ["uip", "codedapp", "publish"], ["uip", "codedapp", "deploy"]])
            self.assertTrue(all(call["dry_run"] for call in calls[1:]))
            self.assertNotIn("uv", " ".join(" ".join(call["cmd"]) for call in calls))
            self.assertIn("--folder-key", calls[-1]["cmd"])
            self.assertIn(GUID, calls[-1]["cmd"])

    def test_execute_writes_version_only_when_execute_is_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            (root / "dist").mkdir()
            calls, captures, original_run, original_capture_json = self.patched_module()
            try:
                code = self.module.main(
                    [
                        "--project-root",
                        str(root),
                        "--set-version",
                        "2.0.0",
                        "--folder-key",
                        GUID,
                        "--skip-tests",
                        "--skip-app-build",
                        "--execute",
                    ]
                )
            finally:
                self.restore_module(original_run, original_capture_json)

            self.assertEqual(code, 0)
            self.assertIn('version = "2.0.0"', (root / "pyproject.toml").read_text())
            self.assertEqual(captures, [])
            self.assertTrue(all(call["dry_run"] is False for call in calls))

    def test_resolves_folder_name_to_folder_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            calls, captures, original_run, original_capture_json = self.patched_module()
            try:
                code = self.module.main(
                    [
                        "--project-root",
                        str(root),
                        "--tenant-name",
                        "alpha",
                        "--folder",
                        "Shared",
                        "--skip-tests",
                        "--skip-app-build",
                    ]
                )
            finally:
                self.restore_module(original_run, original_capture_json)

            self.assertEqual(code, 0)
            self.assertEqual(captures[0]["cmd"], ["uip", "or", "folders", "get", "Shared", "--output", "json", "--tenant", "alpha"])
            self.assertIn(GUID, calls[-1]["cmd"])

    def test_offline_planning_skips_uip_probe_and_requires_folder_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            calls, captures, original_run, original_capture_json = self.patched_module()
            try:
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = self.module.main(
                        [
                            "--project-root",
                            str(root),
                            "--folder-key",
                            GUID,
                            "--skip-tests",
                            "--skip-app-build",
                            "--offline",
                        ]
                    )
            finally:
                self.restore_module(original_run, original_capture_json)

            self.assertEqual(code, 0)
            self.assertIn("Offline planning mode", stdout.getvalue())
            self.assertEqual(captures, [])
            self.assertNotIn(["uip", "--version"], [call["cmd"] for call in calls])
            self.assertTrue(all(call["dry_run"] for call in calls))

            with self.assertRaisesRegex(SystemExit, "Offline mode cannot resolve folder names"):
                self.module.main(
                    [
                        "--project-root",
                        str(root),
                        "--folder",
                        "Shared",
                        "--skip-tests",
                        "--skip-app-build",
                        "--offline",
                    ]
                )

            with self.assertRaisesRegex(SystemExit, "--offline cannot be combined with --execute"):
                self.module.main(
                    [
                        "--project-root",
                        str(root),
                        "--folder-key",
                        GUID,
                        "--skip-tests",
                        "--skip-app-build",
                        "--offline",
                        "--execute",
                    ]
                )

    def test_rejects_conflicting_folder_inputs_and_workspace_without_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            with self.assertRaisesRegex(SystemExit, "Use either --folder or --folder-key"):
                self.module.main(
                    [
                        "--project-root",
                        str(root),
                        "--folder",
                        "Shared",
                        "--folder-key",
                        GUID,
                    ]
                )
            with self.assertRaisesRegex(SystemExit, "--my-workspace has no codedapp equivalent"):
                self.module.main(["--project-root", str(root), "--my-workspace"])


if __name__ == "__main__":
    unittest.main()
