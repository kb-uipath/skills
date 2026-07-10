import contextlib
import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "uipcodedappdeploy.py"
GUID = "11111111-2222-3333-4444-555555555555"


def load_module():
    spec = importlib.util.spec_from_file_location("uipcodedappdeploy_module", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_project(
    root: Path,
    version: str = "1.2.3",
    *,
    pyproject_text: str | None = None,
    uipath: object | None = None,
) -> None:
    if pyproject_text is None:
        pyproject_text = (
            "[project]\n"
            'name = "fixture-app"\n'
            f'version = "{version}"\n'
            'description = "Fixture app"\n'
            'authors = [{ name = "Fixture Author" }]\n'
            "\n"
            "[tool.fixture]\n"
            'version = "9.9.9"\n'
        )
    (root / "pyproject.toml").write_text(pyproject_text, encoding="utf-8")
    if uipath is None:
        uipath = {"projectId": "fixture-project"}
    (root / "uipath.json").write_text(
        json.dumps(uipath, indent=2) + "\n",
        encoding="utf-8",
    )


def write_dist(root: Path, relative: str = "dist", main_file: str = "index.html") -> None:
    dist = root / relative
    dist.mkdir(parents=True, exist_ok=True)
    target = dist / main_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("<!doctype html>\n", encoding="utf-8")


class UiPathCodedAppDeployTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def setUp(self):
        self.subprocess_guard = mock.patch.object(
            self.module.subprocess,
            "run",
            side_effect=AssertionError("unit tests must not invoke live subprocesses"),
        )
        self.urlopen_guard = mock.patch.object(
            self.module.urllib.request,
            "urlopen",
            side_effect=AssertionError("unit tests must not invoke live URLs"),
        )
        self.subprocess_guard.start()
        self.urlopen_guard.start()

    def tearDown(self):
        self.urlopen_guard.stop()
        self.subprocess_guard.stop()

    def run_main(self, argv):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = self.module.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def create_plan(
        self,
        root: Path,
        *,
        folder: bool = True,
        skip_tests: bool = True,
        skip_build: bool = True,
        extras: list[str] | None = None,
        filename: str = "deploy-plan.json",
    ):
        plan_path = root / filename
        argv = [
            "--project-root",
            str(root),
            "--plan-output",
            str(plan_path),
            "--format",
            "json",
        ]
        if folder:
            argv.extend(["--folder-key", GUID])
        if skip_tests:
            argv.append("--skip-tests")
        if skip_build:
            argv.append("--skip-app-build")
        if extras:
            argv.extend(extras)
        code, stdout, _ = self.run_main(argv)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout)["kind"], self.module.PLAN_KIND)
        return plan_path, json.loads(plan_path.read_text(encoding="utf-8"))

    def test_dry_run_json_is_no_write_and_never_runs_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            before = {
                path.name: path.read_bytes()
                for path in root.iterdir()
                if path.is_file()
            }

            code, stdout, stderr = self.run_main(
                [
                    "--project-root",
                    str(root),
                    "--folder-key",
                    GUID,
                    "--skip-tests",
                    "--skip-app-build",
                    "--format",
                    "json",
                ]
            )

            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            plan = json.loads(stdout)
            self.assertEqual(plan["schema_version"], "1.0")
            self.assertRegex(plan["plan_hash"], r"^sha256:[0-9a-f]{64}$")
            self.assertRegex(plan["inputs"]["initial"]["hash"], r"^sha256:[0-9a-f]{64}$")
            self.assertEqual(plan["parameters"]["dist"], "dist")
            pack = next(stage for stage in plan["stages"] if stage["name"] == "pack")
            self.assertEqual(pack["command"][3], "dist")
            self.assertEqual(
                before,
                {
                    path.name: path.read_bytes()
                    for path in root.iterdir()
                    if path.is_file()
                },
            )

    def test_plan_output_is_explicit_atomic_artifact_and_can_be_inspected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            plan_path, plan = self.create_plan(root)

            self.assertEqual(stat.S_IMODE(plan_path.stat().st_mode), 0o600)
            self.assertEqual(plan["execution"]["executable"], True)
            code, stdout, _ = self.run_main(
                ["--plan", str(plan_path), "--format", "json"]
            )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout), plan)
            self.assertIn('version = "1.2.3"', (root / "pyproject.toml").read_text())
            self.assertFalse(self.module._receipt_path(plan_path).exists())

    def test_pyproject_validation_rejects_missing_malformed_and_incomplete_inputs(self):
        cases = [
            (None, "Missing required project manifest"),
            ("not = [valid", "Invalid TOML"),
            ('[tool.fixture]\nname = "x"\n', r"must contain a \[project\] table"),
            ('[project]\nversion = "1.0.0"\n', r"\[project\]\.name"),
            ('[project]\nname = "x"\nversion = 1\n', r"\[project\]\.version must be a string"),
            ('[project]\nname = "x"\nversion = "01.0.0"\n', "not valid SemVer"),
        ]
        for content, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "uipath.json").write_text('{"projectId":"x"}\n')
                if content is not None:
                    (root / "pyproject.toml").write_text(content)
                with self.assertRaisesRegex(SystemExit, expected):
                    self.module.main(["--project-root", str(root)])

    def test_uipath_json_validation_rejects_missing_malformed_and_invalid_shapes(self):
        cases = [
            (None, "Missing required coded app manifest"),
            ("{", "Invalid JSON"),
            ("[]", "non-empty JSON object"),
            ("{}", "non-empty JSON object"),
            ('{"clientId": 4}', "clientId.*non-empty string"),
        ]
        for content, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                write_project(root)
                (root / "uipath.json").unlink()
                if content is not None:
                    (root / "uipath.json").write_text(content)
                with self.assertRaisesRegex(SystemExit, expected):
                    self.module.main(["--project-root", str(root)])

    def test_semver_progression_handles_prerelease_and_rejects_non_progression(self):
        accepted = [
            ("1.0.0-alpha", "1.0.0-alpha.1"),
            ("1.0.0-alpha.1", "1.0.0-alpha.beta"),
            ("1.0.0-rc.1", "1.0.0"),
            ("1.0.0", "1.0.1"),
            ("1.9.9", "2.0.0"),
        ]
        for old, new in accepted:
            with self.subTest(old=old, new=new):
                self.module._validate_progression(old, new)

        rejected = [
            ("1.0.0", "1.0.0"),
            ("1.0.0+one", "1.0.0+two"),
            ("2.0.0", "1.9.9"),
            ("1.0.0", "1.0.0-rc.1"),
        ]
        for old, new in rejected:
            with self.subTest(old=old, new=new), self.assertRaisesRegex(
                SystemExit, "greater SemVer precedence"
            ):
                self.module._validate_progression(old, new)

    def test_auto_bump_strips_prerelease_and_advances_requested_core_part(self):
        self.assertEqual(self.module._next_version("1.2.3-rc.1+build.7", "patch"), "1.2.4")
        self.assertEqual(self.module._next_version("1.2.3", "minor"), "1.3.0")
        self.assertEqual(self.module._next_version("1.2.3", "major"), "2.0.0")

    def test_atomic_update_changes_only_project_version_and_preserves_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = (
                "[project]\n"
                'name = "fixture-app"\n'
                "version = '1.2.3' # release version\n"
                'description = "Fixture app"\n'
                'authors = [{ name = "Fixture Author" }]\n'
                "\n"
                "[tool.fixture]\n"
                'version = "9.9.9"\n'
            )
            write_project(root, pyproject_text=original)
            os.chmod(root / "pyproject.toml", 0o640)
            write_dist(root)
            plan_path, _ = self.create_plan(root)

            with mock.patch.object(self.module, "_run") as run:
                code, _, _ = self.run_main(["--plan", str(plan_path), "--execute"])

            self.assertEqual(code, 0)
            run.assert_called()
            expected = original.replace(
                "version = '1.2.3' # release version",
                'version = "1.2.4" # release version',
            )
            self.assertEqual((root / "pyproject.toml").read_text(), expected)
            self.assertEqual(stat.S_IMODE((root / "pyproject.toml").stat().st_mode), 0o640)

    def test_version_stage_precedes_lock_test_build_and_uip_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            (root / "uv.lock").write_text("fixture\n")
            (root / "app").mkdir()
            (root / "app" / "package.json").write_text('{"scripts":{"build":"vite build"}}\n')
            write_dist(root, "app/dist")
            plan_path, plan = self.create_plan(
                root,
                skip_tests=False,
                skip_build=False,
            )
            calls = []

            def fake_run(cmd, cwd, env):
                calls.append((cmd, cwd, (root / "pyproject.toml").read_text()))

            with mock.patch.object(self.module, "_run", side_effect=fake_run):
                self.run_main(["--plan", str(plan_path), "--execute"])

            self.assertEqual(
                [stage["name"] for stage in plan["stages"][:4]],
                ["version", "lock", "test", "build"],
            )
            self.assertEqual(
                [call[0][:3] for call in calls],
                [
                    ["uv", "lock"],
                    ["uv", "run", "python"],
                    ["npm", "run", "build"],
                    ["uip", "--version"],
                    ["uip", "codedapp", "pack"],
                    ["uip", "codedapp", "publish"],
                    ["uip", "codedapp", "deploy"],
                ],
            )
            self.assertTrue(all('version = "1.2.4"' in call[2] for call in calls))
            self.assertEqual(calls[2][1], root.resolve() / "app")
            self.assertIn("app/dist", calls[4][0])

    def test_direct_execute_and_folderless_plan_fail_before_any_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            with self.assertRaisesRegex(SystemExit, "Direct --execute is prohibited"):
                self.module.main(["--project-root", str(root), "--execute"])

            plan_path, plan = self.create_plan(root, folder=False)
            self.assertFalse(plan["execution"]["executable"])
            with self.assertRaisesRegex(SystemExit, "plan has no folder key"):
                self.module.main(["--plan", str(plan_path), "--execute"])
            self.assertIn('version = "1.2.3"', (root / "pyproject.toml").read_text())
            self.assertFalse(self.module._receipt_path(plan_path).exists())

    def test_folder_key_must_be_a_guid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            with self.assertRaisesRegex(SystemExit, "folder-key must be a GUID"):
                self.module.main(
                    ["--project-root", str(root), "--folder-key", "Shared"]
                )

    def test_loading_plan_without_execute_never_runs_or_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            plan_path, _ = self.create_plan(root)
            with mock.patch.object(
                self.module, "_run", side_effect=AssertionError("must not run")
            ):
                self.run_main(["--plan", str(plan_path)])
            self.assertIn('version = "1.2.3"', (root / "pyproject.toml").read_text())
            self.assertFalse(self.module._receipt_path(plan_path).exists())

    def test_dist_paths_are_project_relative_and_cannot_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            _, plan = self.create_plan(root, extras=["--app-dist", "assets/build"])
            self.assertEqual(plan["parameters"]["dist"], "assets/build")
            pack = next(stage for stage in plan["stages"] if stage["name"] == "pack")
            self.assertEqual(pack["command"][3], "assets/build")

            for value in (str(root / "dist"), "../outside", "."):
                with self.subTest(value=value), self.assertRaisesRegex(
                    SystemExit, "project-relative|project root"
                ):
                    self.module.main(
                        ["--project-root", str(root), "--app-dist", value]
                    )

    def test_dist_symlink_cannot_escape_project_root(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            write_project(root)
            (root / "linked-dist").symlink_to(Path(outside), target_is_directory=True)
            with self.assertRaisesRegex(SystemExit, "resolve inside the project root"):
                self.module.main(
                    ["--project-root", str(root), "--app-dist", "linked-dist"]
                )

    def test_missing_dist_or_main_file_fails_before_version_and_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            plan_path, _ = self.create_plan(root)
            with self.assertRaisesRegex(SystemExit, "Missing coded app dist directory"):
                self.module.main(["--plan", str(plan_path), "--execute"])
            self.assertIn('version = "1.2.3"', (root / "pyproject.toml").read_text())
            self.assertFalse(self.module._receipt_path(plan_path).exists())

            (root / "dist").mkdir()
            with self.assertRaisesRegex(SystemExit, "Missing coded app main file"):
                self.module.main(["--plan", str(plan_path), "--execute"])
            self.assertIn('version = "1.2.3"', (root / "pyproject.toml").read_text())

    def test_main_file_symlink_cannot_escape_dist(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            write_project(root)
            (root / "dist").mkdir()
            outside_main = Path(outside) / "index.html"
            outside_main.write_text("outside\n")
            (root / "dist" / "index.html").symlink_to(outside_main)
            plan_path, _ = self.create_plan(root)

            with self.assertRaisesRegex(SystemExit, "resolves outside the dist directory"):
                self.module.main(["--plan", str(plan_path), "--execute"])
            self.assertIn('version = "1.2.3"', (root / "pyproject.toml").read_text())
            self.assertFalse(self.module._receipt_path(plan_path).exists())

    def test_plan_hash_detects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            plan_path, plan = self.create_plan(root)
            plan["parameters"]["target_url"] = "https://example.com"
            plan_path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(SystemExit, "Plan hash mismatch"):
                self.module.main(["--plan", str(plan_path)])

    def test_input_hash_detects_manifest_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            plan_path, _ = self.create_plan(root)
            with (root / "uipath.json").open("a", encoding="utf-8") as handle:
                handle.write("\n")
            with self.assertRaisesRegex(SystemExit, "input hash mismatch"):
                self.module.main(["--plan", str(plan_path)])

    def test_rehashed_arbitrary_command_is_rejected_by_stage_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            plan_path, plan = self.create_plan(root)
            pack = next(stage for stage in plan["stages"] if stage["name"] == "pack")
            pack["command"] = ["sh", "-c", "echo unsafe"]
            plan["plan_hash"] = self.module._document_hash(plan, "plan_hash")
            plan_path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(SystemExit, "allowlisted command sequence"):
                self.module.main(["--plan", str(plan_path)])

    def test_resume_uses_redacted_receipt_and_skips_completed_version_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            plan_path, _ = self.create_plan(root, skip_tests=False)

            def fail_test(cmd, cwd, env):
                if cmd[:3] == ["uv", "run", "python"]:
                    raise RuntimeError("fixture failure with sensitive details")

            with mock.patch.dict(os.environ, {"UIPATH_ACCESS_TOKEN": "do-not-retain"}), mock.patch.object(
                self.module, "_run", side_effect=fail_test
            ):
                with self.assertRaisesRegex(RuntimeError, "fixture failure"):
                    self.module.main(["--plan", str(plan_path), "--execute"])

            receipt_path = self.module._receipt_path(plan_path)
            receipt_text = receipt_path.read_text(encoding="utf-8")
            receipt = json.loads(receipt_text)
            self.assertEqual(receipt["status"], "failed")
            self.assertEqual(receipt["stages"][0]["status"], "succeeded")
            self.assertEqual(receipt["stages"][1]["status"], "failed")
            self.assertNotIn('"command":', receipt_text)
            self.assertNotIn("do-not-retain", receipt_text)
            self.assertNotIn("sensitive details", receipt_text)
            self.assertEqual(receipt["redaction"], self.module.REDACTION_POLICY)
            self.assertIn('version = "1.2.4"', (root / "pyproject.toml").read_text())

            resumed_calls = []
            with mock.patch.object(
                self.module,
                "_run",
                side_effect=lambda cmd, cwd, env: resumed_calls.append(cmd),
            ):
                code, stdout, _ = self.run_main(
                    [
                        "--plan",
                        str(plan_path),
                        "--execute",
                        "--resume",
                        "--format",
                        "json",
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout)["kind"], self.module.RESULT_KIND)
            self.assertEqual(resumed_calls[0][:3], ["uv", "run", "python"])
            self.assertEqual(json.loads(receipt_path.read_text())["status"], "succeeded")

    def test_resume_reconciles_interrupted_atomic_version_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            plan_path, plan = self.create_plan(root)
            receipt_path = self.module._receipt_path(plan_path)
            receipt = self.module._new_receipt(plan)
            receipt["stages"][0]["status"] = "running"
            receipt["stages"][0]["started_at"] = self.module._utc_now()
            self.module._write_version_atomic(
                root / "pyproject.toml",
                plan["project"]["old_version"],
                plan["project"]["new_version"],
            )
            self.module._write_receipt(receipt_path, receipt)

            with mock.patch.object(self.module, "_run"):
                self.run_main(
                    ["--plan", str(plan_path), "--execute", "--resume"]
                )
            completed = json.loads(receipt_path.read_text())
            self.assertEqual(completed["status"], "succeeded")
            self.assertEqual(
                completed["stages"][0]["recovery"],
                "atomic_version_write_reconciled",
            )

    def test_resume_blocks_indeterminate_external_write_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            plan_path, plan = self.create_plan(root)
            self.module._write_version_atomic(
                root / "pyproject.toml",
                plan["project"]["old_version"],
                plan["project"]["new_version"],
            )
            receipt = self.module._new_receipt(plan)
            for stage in receipt["stages"]:
                if stage["name"] == "publish":
                    stage["status"] = "running"
                    stage["started_at"] = self.module._utc_now()
                    break
                stage["status"] = "succeeded"
                stage["finished_at"] = self.module._utc_now()
            receipt_path = self.module._receipt_path(plan_path)
            self.module._write_receipt(receipt_path, receipt)

            with self.assertRaisesRegex(SystemExit, "indeterminate outcome"):
                self.module.main(
                    ["--plan", str(plan_path), "--execute", "--resume"]
                )

    def test_external_write_interrupt_is_recorded_as_indeterminate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            plan_path, _ = self.create_plan(root)

            def interrupt_publish(cmd, cwd, env):
                if cmd[:3] == ["uip", "codedapp", "publish"]:
                    raise KeyboardInterrupt()

            with mock.patch.object(self.module, "_run", side_effect=interrupt_publish):
                with self.assertRaises(KeyboardInterrupt):
                    self.module.main(["--plan", str(plan_path), "--execute"])

            receipt_path = self.module._receipt_path(plan_path)
            receipt = json.loads(receipt_path.read_text())
            publish = next(
                stage for stage in receipt["stages"] if stage["name"] == "publish"
            )
            self.assertEqual(receipt["status"], "in_progress")
            self.assertEqual(publish["status"], "running")
            self.assertEqual(
                publish["recovery"],
                "redacted_indeterminate_external_write; verify target manually",
            )
            with self.assertRaisesRegex(SystemExit, "indeterminate outcome"):
                self.module.main(
                    ["--plan", str(plan_path), "--execute", "--resume"]
                )

    def test_receipt_hash_detects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            plan_path, plan = self.create_plan(root)
            receipt_path = self.module._receipt_path(plan_path)
            receipt = self.module._new_receipt(plan)
            self.module._write_receipt(receipt_path, receipt)
            receipt["status"] = "failed"
            receipt_path.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(SystemExit, "Receipt hash mismatch"):
                self.module.main(
                    ["--plan", str(plan_path), "--execute", "--resume"]
                )

    def test_receipt_status_must_match_stage_statuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            plan_path, plan = self.create_plan(root)
            receipt_path = self.module._receipt_path(plan_path)
            receipt = self.module._new_receipt(plan)
            receipt["status"] = "succeeded"
            self.module._write_receipt(receipt_path, receipt)
            with self.assertRaisesRegex(SystemExit, "marked succeeded.*incomplete stage"):
                self.module.main(
                    ["--plan", str(plan_path), "--execute", "--resume"]
                )

    def test_verify_url_runs_after_deploy_without_retaining_response_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            verify_url = "https://example.uipath.host/fixture"
            plan_path, plan = self.create_plan(
                root,
                extras=["--verify-url", verify_url, "--verify-timeout", "9"],
            )
            events = []

            def fake_run(cmd, cwd, env):
                events.append(cmd[:3])

            def fake_verify(url, timeout):
                events.append(["verify", url, timeout])

            with mock.patch.object(self.module, "_run", side_effect=fake_run), mock.patch.object(
                self.module, "_verify_url", side_effect=fake_verify
            ):
                self.run_main(["--plan", str(plan_path), "--execute"])

            self.assertEqual(plan["stages"][-1]["name"], "verify")
            self.assertEqual(events[-2], ["uip", "codedapp", "deploy"])
            self.assertEqual(events[-1], ["verify", verify_url, 9])
            receipt_text = self.module._receipt_path(plan_path).read_text()
            self.assertNotIn(verify_url, receipt_text)

    def test_url_and_timeout_validation_fail_closed(self):
        cases = [
            (["--target-url", "http://alpha.uipath.com"], "HTTPS URL"),
            (["--target-url", "https://alpha.uipath.com/path"], "without a path"),
            (["--target-url", "https://alpha.uipath.com:bad"], "invalid port"),
            (["--verify-url", "http://example.com/app"], "HTTPS URL"),
            (["--verify-url", "https://example.com/app?token=x"], "query string"),
            (
                ["--verify-url", "https://example.com/app", "--verify-timeout", "0"],
                "between 1 and 120",
            ),
            (["--verify-timeout", "10"], "requires --verify-url"),
        ]
        for extras, expected in cases:
            with self.subTest(extras=extras), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                write_project(root)
                with self.assertRaisesRegex(SystemExit, expected):
                    self.module.main(["--project-root", str(root), *extras])

    def test_reuse_client_requires_manifest_client_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            with self.assertRaisesRegex(SystemExit, "reuse-client requires.*clientId"):
                self.module.main(["--project-root", str(root), "--reuse-client"])

            write_project(root, uipath={"projectId": "fixture", "clientId": "client-1"})
            _, plan = self.create_plan(root, extras=["--reuse-client"])
            pack = next(stage for stage in plan["stages"] if stage["name"] == "pack")
            self.assertIn("--reuse-client", pack["command"])

    def test_unsafe_legacy_flags_fail_closed_with_migration_guidance(self):
        cases = [
            ["--folder", "Shared"],
            ["--tenant"],
            ["--my-workspace"],
            ["--pack-nolock"],
            ["--use-deploy-command"],
            ["--offline"],
        ]
        for flags in cases:
            with self.subTest(flags=flags), self.assertRaisesRegex(
                SystemExit, "Migration:"
            ):
                self.module.main(flags)

    def test_plan_is_immutable_and_rejects_runtime_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            plan_path, _ = self.create_plan(root)
            with self.assertRaisesRegex(SystemExit, "persisted plan is immutable"):
                self.module.main(
                    [
                        "--plan",
                        str(plan_path),
                        "--folder-key",
                        GUID,
                        "--execute",
                    ]
                )

    def test_plan_output_cannot_overwrite_project_manifests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            original = (root / "pyproject.toml").read_text()
            with self.assertRaisesRegex(SystemExit, "must not overwrite"):
                self.module.main(
                    [
                        "--project-root",
                        str(root),
                        "--plan-output",
                        str(root / "pyproject.toml"),
                    ]
                )
            self.assertEqual((root / "pyproject.toml").read_text(), original)

    def test_plan_output_rejects_dist_and_existing_non_plan_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            existing = root / "notes.json"
            existing.write_text('{"owner":"fixture"}\n')
            with self.assertRaisesRegex(SystemExit, "existing non-plan file"):
                self.module.main(
                    [
                        "--project-root",
                        str(root),
                        "--plan-output",
                        str(existing),
                    ]
                )
            with self.assertRaisesRegex(SystemExit, "must not be inside.*dist"):
                self.module.main(
                    [
                        "--project-root",
                        str(root),
                        "--plan-output",
                        str(root / "dist" / "plan.json"),
                    ]
                )
            self.assertEqual(existing.read_text(), '{"owner":"fixture"}\n')

    def test_explicit_version_and_part_are_mutually_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            with self.assertRaisesRegex(SystemExit, "either --set-version or --part"):
                self.module.main(
                    [
                        "--project-root",
                        str(root),
                        "--set-version",
                        "2.0.0",
                        "--part",
                        "major",
                    ]
                )

    def test_unsupported_plan_schema_requires_regeneration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            plan_path, plan = self.create_plan(root)
            plan["schema_version"] = "2.0"
            plan["plan_hash"] = self.module._document_hash(plan, "plan_hash")
            plan_path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(SystemExit, "Unsupported deployment plan"):
                self.module.main(["--plan", str(plan_path)])


if __name__ == "__main__":
    unittest.main()
