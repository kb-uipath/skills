import contextlib
import importlib.util
import io
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "uipcodedappdeploy.py"
PLAN_SCHEMA = ROOT / "references" / "deployment-plan.v2.schema.json"
RECEIPT_SCHEMA = ROOT / "references" / "deployment-receipt.v2.schema.json"
GUID = "11111111-2222-3333-4444-555555555555"
TENANT_GUID = "66666666-7777-8888-9999-000000000000"


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


def write_package(
    root: Path,
    *,
    package_name: str = "fixture-app",
    version: str = "1.2.4",
    main_file: str = "index.html",
    envelope_nonce: str = "candidate",
    project_id: str = GUID,
    main_payload: bytes = b"<!doctype html>\n",
) -> Path:
    package = root / ".uipath" / f"{package_name}.{version}.nupkg"
    package.parent.mkdir(parents=True, exist_ok=True)
    core_path = (
        "package/services/metadata/core-properties/"
        f"{envelope_nonce}.psmdcp"
    )
    generated = {
        "projectId": project_id,
        "main": main_file,
        "contentType": "WebApp",
    }
    web_manifest = {
        "type": "Coded",
        "solutionResourceSubType": "Coded",
        "config": {"isCompiled": True, "bundlePath": "dist"},
        "projectId": project_id,
    }
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr(
            "_rels/.rels",
            "<Relationships>"
            '<Relationship Type="http://schemas.microsoft.com/packaging/2010/07/manifest" '
            f'Target="/{package_name}.nuspec" Id="manifest-{envelope_nonce}" />'
            '<Relationship Type="http://schemas.openxmlformats.org/package/2006/'
            'relationships/metadata/core-properties" '
            f'Target="/{core_path}" Id="core-{envelope_nonce}" />'
            "</Relationships>",
        )
        archive.writestr(core_path, "<coreProperties>fixture-app</coreProperties>")
        archive.writestr(
            f"{package_name}.nuspec",
            f"<package><metadata><id>{package_name}</id>"
            f"<version>{version}</version></metadata></package>",
        )
        archive.writestr(f"content/{main_file}", main_payload)
        archive.writestr("content/operate.json", json.dumps(generated))
        archive.writestr("content/webAppManifest.json", json.dumps(web_manifest))
    return package


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
        self.source_guard = mock.patch.object(self.module, "_validate_source")
        self.cli_guard = mock.patch.object(self.module, "_validate_cli")
        self.raw_worktree_guard = mock.patch.object(
            self.module,
            "_planned_raw_worktree_snapshots",
            return_value={
                "algorithm": self.module.RAW_WORKTREE_DIGEST_ALGORITHM,
                "initial": self.module._hash_bytes(b"fixture raw initial"),
                "version_written": self.module._hash_bytes(b"fixture raw version written"),
                "versioned": self.module._hash_bytes(b"fixture raw versioned"),
            },
        )
        self.source_guard.start()
        self.cli_guard.start()
        self.raw_worktree_guard.start()

    def tearDown(self):
        self.raw_worktree_guard.stop()
        self.cli_guard.stop()
        self.source_guard.stop()
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
        environment: str = "staging",
        folder: bool = True,
        skip_tests: bool = True,
        skip_build: bool = True,
        exact_target: bool = True,
        extras: list[str] | None = None,
        filename: str = "deploy-plan.json",
    ):
        plan_path = root / filename
        raw_dist = "app/dist" if (root / "app" / "package.json").is_file() else "dist"
        dist_digest = self.module._directory_digest(root, raw_dist)
        if dist_digest is None:
            dist_digest = self.module._hash_bytes(b"missing-dist-fixture")
        package_path = write_package(root)
        package_digest, _ = self.module._package_evidence(
            package_path,
            package_name="fixture-app",
            main_file="index.html",
        )
        argv = [
            "--project-root",
            str(root),
            "--plan-output",
            str(plan_path),
            "--format",
            "json",
            "--path-name",
            "fixture-app",
            "--client-id",
            GUID,
            "--tags",
            "governance,internal",
            "--source-sha",
            "a" * 40,
            "--dist-digest",
            dist_digest,
            "--package-digest",
            package_digest,
            "--cli-executable",
            sys.executable,
            "--cli-version",
            "1.198.0",
            "--cli-profile",
            "fixture-profile",
        ]
        if exact_target:
            argv.extend(
                [
                    "--environment",
                    environment,
                    "--control-plane-url",
                    self.module.TARGET_ENVIRONMENTS[environment]["control_plane_url"],
                    "--org-id",
                    GUID,
                    "--tenant-id",
                    TENANT_GUID,
                ]
            )
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
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        self.assertEqual(
            root / plan["parameters"]["package_path"],
            package_path,
        )
        return plan_path, plan

    def execution_args(self, plan_path: Path, *extras: str) -> list[str]:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        return [
            "--plan",
            str(plan_path),
            "--execute",
            "--approved-plan-hash",
            plan["plan_hash"],
            *extras,
        ]

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
            self.assertEqual(plan["schema_version"], "2.2")
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
                code, _, _ = self.run_main(self.execution_args(plan_path))

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
            (root / "uv.lock").write_text(
                "version = 1\n"
                "revision = 3\n"
                'requires-python = ">=3.12"\n'
                "\n"
                "[[package]]\n"
                'name = "fixture-app"\n'
                'version = "1.2.3"\n'
                'source = { virtual = "." }\n',
                encoding="utf-8",
            )
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
                self.run_main(self.execution_args(plan_path))

            self.assertEqual(
                [stage["name"] for stage in plan["stages"][:4]],
                ["version", "lock", "test", "build"],
            )
            self.assertEqual(
                [
                    call[0][:3]
                    if call[0][0] in {"uv", "npm"}
                    else ["uip", *call[0][1:3]]
                    for call in calls
                ],
                [
                    ["uv", "lock"],
                    ["uv", "run", "python"],
                    ["npm", "run", "build"],
                    ["uip", "codedapp", "pack"],
                    ["uip", "codedapp", "publish"],
                    ["uip", "codedapp", "deploy"],
                ],
            )
            self.assertTrue(all('version = "1.2.4"' in call[2] for call in calls))
            self.assertEqual(calls[2][1], root.resolve() / "app")
            self.assertIn("app/dist", calls[3][0])

    def test_direct_execute_and_folderless_plan_fail_before_any_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            with self.assertRaisesRegex(SystemExit, "Direct --execute is prohibited"):
                self.module.main(["--project-root", str(root), "--execute"])

            plan_path, plan = self.create_plan(root, folder=False)
            self.assertFalse(plan["execution"]["executable"])
            with self.assertRaisesRegex(SystemExit, "folder-key is mandatory"):
                self.module.main(self.execution_args(plan_path))
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

    def test_executable_plan_requires_explicit_environment_org_and_tenant(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            plan_path, plan = self.create_plan(root, exact_target=False)
            self.assertFalse(plan["execution"]["executable"])
            self.assertIsNone(plan["parameters"]["environment"])
            self.assertIsNone(plan["parameters"]["control_plane_url"])
            self.assertIsNone(plan["parameters"]["org_id"])
            self.assertIsNone(plan["parameters"]["tenant_id"])
            blockers = " ".join(plan["execution"]["blockers"])
            self.assertIn("environment", blockers)
            self.assertIn("control-plane-url", blockers)
            self.assertIn("--org-id", blockers)
            self.assertIn("--tenant-id", blockers)
            with self.assertRaisesRegex(SystemExit, "control-plane-url"):
                self.module.main(self.execution_args(plan_path))
            self.assertFalse(self.module._receipt_path(plan_path).exists())

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            with self.assertRaisesRegex(SystemExit, "requires an explicit environment"):
                self.module.main(
                    [
                        "--project-root",
                        str(root),
                        "--control-plane-url",
                        "https://alpha.uipath.com",
                    ]
                )
            for flag in ("--org-id", "--tenant-id"):
                with self.subTest(flag=flag), self.assertRaisesRegex(
                    SystemExit, "exact UiPath GUID"
                ):
                    self.module.main(
                        [
                            "--project-root",
                            str(root),
                            "--environment",
                            "staging",
                            "--control-plane-url",
                            "https://staging.uipath.com",
                            flag,
                            "not-a-guid",
                        ]
                    )

    def test_alpha_plan_binds_exact_control_plane_and_verification_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            verify_url = "https://agenticgtm.alpha.uipath.host/aura-vdp-v0"
            _, plan = self.create_plan(
                root,
                environment="alpha",
                extras=["--verify-url", verify_url],
            )

            parameters = plan["parameters"]
            self.assertTrue(plan["execution"]["executable"])
            self.assertEqual(parameters["environment"], "alpha")
            self.assertEqual(
                parameters["control_plane_url"],
                self.module.ALPHA_CONTROL_PLANE_URL,
            )
            self.assertEqual(parameters["verify_url"], verify_url)
            for stage_name in ("publish", "deploy"):
                command = next(
                    stage["command"]
                    for stage in plan["stages"]
                    if stage["name"] == stage_name
                )
                base_index = command.index("--base-url")
                self.assertEqual(
                    command[base_index + 1], self.module.ALPHA_CONTROL_PLANE_URL
                )
            receipt = self.module._new_receipt(plan)
            self.assertEqual(receipt["environment"], "alpha")

    def test_environment_target_mismatches_and_production_fail_closed(self):
        cases = [
            (
                [
                    "--environment",
                    "alpha",
                    "--control-plane-url",
                    "https://staging.uipath.com",
                ],
                "environment 'alpha' requires the exact control plane",
            ),
            (
                [
                    "--environment",
                    "staging",
                    "--control-plane-url",
                    "https://alpha.uipath.com",
                ],
                "environment 'staging' requires the exact control plane",
            ),
            (["--environment", "production"], "staging or alpha"),
            (["--environment", "alpha"], "requires the exact control plane"),
            (
                ["--control-plane-url", "https://alpha.uipath.com"],
                "requires an explicit environment",
            ),
        ]
        for extras, expected in cases:
            with self.subTest(extras=extras), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                write_project(root)
                with self.assertRaisesRegex(SystemExit, expected):
                    self.module.main(["--project-root", str(root), *extras])

    def test_verification_host_must_match_selected_environment(self):
        rejected = [
            "https://agenticgtm.staging.uipath.host/aura-vdp-v0",
            "https://alpha.uipath.host/aura-vdp-v0",
            "https://agenticgtm.alpha.uipath.host:443/aura-vdp-v0",
            "https://agenticgtm.alpha.uipath.host.example.com/aura-vdp-v0",
        ]
        for verify_url in rejected:
            with self.subTest(verify_url=verify_url), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                write_project(root)
                with self.assertRaisesRegex(SystemExit, "verification URL|verification host"):
                    self.module.main(
                        [
                            "--project-root",
                            str(root),
                            "--environment",
                            "alpha",
                            "--control-plane-url",
                            "https://alpha.uipath.com",
                            "--verify-url",
                            verify_url,
                        ]
                    )

    def test_reloaded_plan_rejects_repaired_hash_with_environment_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            plan_path, plan = self.create_plan(root, environment="alpha")
            plan["parameters"]["environment"] = "staging"
            plan["plan_hash"] = self.module._document_hash(plan, "plan_hash")
            plan_path.write_text(json.dumps(plan), encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "requires the exact control plane"):
                self.module.main(["--plan", str(plan_path)])

    def test_environment_is_bound_into_profile_and_deployment_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            plan_path, plan = self.create_plan(root, environment="alpha")
            parameters = plan["parameters"]
            self.assertEqual(
                parameters["cli_profile_hash"],
                self.module._hash_json(
                    {
                        "name": parameters["cli_profile"],
                        "environment": "alpha",
                        "control_plane_url": self.module.ALPHA_CONTROL_PLANE_URL,
                        "org_id": parameters["org_id"],
                        "tenant_id": parameters["tenant_id"],
                    }
                ),
            )

            parameters["environment"] = "staging"
            parameters["control_plane_url"] = self.module.STAGING_CONTROL_PLANE_URL
            parameters["cli_profile_hash"] = self.module._hash_json(
                {
                    "name": parameters["cli_profile"],
                    "environment": "staging",
                    "control_plane_url": self.module.STAGING_CONTROL_PLANE_URL,
                    "org_id": parameters["org_id"],
                    "tenant_id": parameters["tenant_id"],
                }
            )
            plan["stages"] = self.module._build_stages(plan["project"], parameters)
            plan["plan_hash"] = self.module._document_hash(plan, "plan_hash")
            plan_path.write_text(json.dumps(plan), encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "deployment_binding_hash"):
                self.module.main(["--plan", str(plan_path)])

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
                self.module.main(self.execution_args(plan_path))
            self.assertIn('version = "1.2.3"', (root / "pyproject.toml").read_text())
            self.assertFalse(self.module._receipt_path(plan_path).exists())

            (root / "dist").mkdir()
            with self.assertRaisesRegex(SystemExit, "Missing coded app main file"):
                self.module.main(self.execution_args(plan_path))
            self.assertIn('version = "1.2.3"', (root / "pyproject.toml").read_text())

    def test_main_file_symlink_cannot_escape_dist(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            write_project(root)
            (root / "dist").mkdir()
            outside_main = Path(outside) / "index.html"
            outside_main.write_text("outside\n")
            (root / "dist" / "index.html").symlink_to(outside_main)
            with self.assertRaisesRegex(SystemExit, "dist may not contain symlinks"):
                self.create_plan(root)
            self.assertIn('version = "1.2.3"', (root / "pyproject.toml").read_text())

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
                    self.module.main(self.execution_args(plan_path))

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
                    self.execution_args(plan_path, "--resume", "--format", "json")
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
                self.run_main(self.execution_args(plan_path, "--resume"))
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
            receipt["package_file_digest"] = plan["parameters"][
                "candidate_package_file_digest"
            ]
            receipt_path = self.module._receipt_path(plan_path)
            self.module._write_receipt(receipt_path, receipt)

            with self.assertRaisesRegex(SystemExit, "indeterminate outcome"):
                self.module.main(self.execution_args(plan_path, "--resume"))

    def test_external_write_interrupt_is_recorded_as_indeterminate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            plan_path, _ = self.create_plan(root)

            def interrupt_publish(cmd, cwd, env):
                if cmd[1:3] == ["codedapp", "publish"]:
                    raise KeyboardInterrupt()

            with mock.patch.object(self.module, "_run", side_effect=interrupt_publish):
                with self.assertRaises(KeyboardInterrupt):
                    self.module.main(self.execution_args(plan_path))

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
                self.module.main(self.execution_args(plan_path, "--resume"))

    def test_external_write_nonzero_exit_is_indeterminate_and_never_blindly_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            plan_path, _ = self.create_plan(root)
            calls = []

            def fail_publish(cmd, cwd, env):
                calls.append(cmd[1:3])
                if cmd[1:3] == ["codedapp", "publish"]:
                    raise subprocess.CalledProcessError(1, cmd)

            with mock.patch.object(self.module, "_run", side_effect=fail_publish):
                with self.assertRaises(subprocess.CalledProcessError):
                    self.module.main(self.execution_args(plan_path))

            receipt_path = self.module._receipt_path(plan_path)
            receipt = json.loads(receipt_path.read_text())
            publish = next(
                stage for stage in receipt["stages"] if stage["name"] == "publish"
            )
            self.assertEqual(receipt["status"], "in_progress")
            self.assertEqual(publish["status"], "running")
            self.assertIn("blind resume prohibited", publish["recovery"])
            self.assertNotIn(["codedapp", "deploy"], calls)

            with mock.patch.object(
                self.module,
                "_run",
                side_effect=AssertionError("indeterminate external write must not retry"),
            ):
                with self.assertRaisesRegex(SystemExit, "blind retry is prohibited"):
                    self.module.main(self.execution_args(plan_path, "--resume"))

    def test_resume_blocks_legacy_failed_external_write_receipt(self):
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
            package_file = plan["parameters"]["candidate_package_file_digest"]
            for stage in receipt["stages"]:
                if stage["name"] == "publish":
                    stage["status"] = "failed"
                    stage["started_at"] = self.module._utc_now()
                    stage["finished_at"] = self.module._utc_now()
                    break
                stage["status"] = "succeeded"
                stage["finished_at"] = self.module._utc_now()
            receipt["package_file_digest"] = package_file
            receipt["status"] = "failed"
            receipt_path = self.module._receipt_path(plan_path)
            self.module._write_receipt(receipt_path, receipt)

            with self.assertRaisesRegex(SystemExit, "blind retry is prohibited"):
                self.module.main(self.execution_args(plan_path, "--resume"))

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
                self.module.main(self.execution_args(plan_path, "--resume"))

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
                self.module.main(self.execution_args(plan_path, "--resume"))

    def test_verify_url_runs_after_deploy_without_retaining_response_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            verify_url = "https://fixture.staging.uipath.host/fixture"
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
                self.run_main(self.execution_args(plan_path))

            self.assertEqual(plan["stages"][-1]["name"], "verify")
            self.assertEqual(events[-2][1:], ["codedapp", "deploy"])
            self.assertEqual(events[-1], ["verify", verify_url, 9])
            receipt_text = self.module._receipt_path(plan_path).read_text()
            self.assertNotIn(verify_url, receipt_text)

    def test_verify_url_rejects_redirect_away_from_exact_approved_route(self):
        approved_url = "https://agenticgtm.alpha.uipath.host/aura-vdp-v0"

        class RedirectedResponse:
            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _traceback):
                return False

            def getcode(self):
                return 200

            def geturl(self):
                return "https://attacker.example/looks-healthy"

        with mock.patch.object(
            self.module.urllib.request,
            "urlopen",
            return_value=RedirectedResponse(),
        ):
            with self.assertRaisesRegex(
                SystemExit,
                "redirected away from the exact approved URL",
            ):
                self.module._verify_url(approved_url, 10)

    def test_url_and_timeout_validation_fail_closed(self):
        cases = [
            (["--control-plane-url", "http://alpha.uipath.com"], "HTTPS URL"),
            (["--control-plane-url", "https://alpha.uipath.com/path"], "without a path"),
            (["--control-plane-url", "https://alpha.uipath.com:bad"], "invalid port"),
            (
                ["--control-plane-url", "https://alpha.uipath.com"],
                "requires an explicit environment",
            ),
            (["--verify-url", "http://example.com/app"], "HTTPS URL"),
            (["--verify-url", "https://example.com/app?token=x"], "query string"),
            (
                [
                    "--environment",
                    "staging",
                    "--control-plane-url",
                    "https://staging.uipath.com",
                    "--verify-url",
                    "https://fixture.staging.uipath.host/app",
                    "--verify-timeout",
                    "0",
                ],
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

    def test_reuse_client_is_rejected_and_pack_has_no_authentication_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            with self.assertRaisesRegex(SystemExit, "unsupported by codedapp pack"):
                self.module.main(["--project-root", str(root), "--reuse-client"])

            _, plan = self.create_plan(root)
            pack = next(stage for stage in plan["stages"] if stage["name"] == "pack")
            self.assertNotIn("--reuse-client", pack["command"])
            self.assertNotIn("--base-url", pack["command"])
            self.assertNotIn("--profile", pack["command"])
            self.assertNotIn("--org-id", pack["command"])
            self.assertNotIn("--tenant-id", pack["command"])

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
            plan["schema_version"] = "9.9"
            plan["plan_hash"] = self.module._document_hash(plan, "plan_hash")
            plan_path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(SystemExit, "Unsupported deployment plan"):
                self.module.main(["--plan", str(plan_path)])

    def test_release_provenance_and_supported_cli_commands_are_hash_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            plan_path, plan = self.create_plan(root)

            self.assertEqual(plan["schema_version"], "2.2")
            self.assertRegex(
                plan["deployment_binding_hash"], r"^sha256:[0-9a-f]{64}$"
            )
            parameters = plan["parameters"]
            self.assertEqual(parameters["environment"], "staging")
            self.assertEqual(parameters["control_plane_url"], "https://staging.uipath.com")
            self.assertEqual(parameters["org_id"], GUID)
            self.assertEqual(parameters["tenant_id"], TENANT_GUID)
            self.assertEqual(parameters["path_name"], "fixture-app")
            self.assertEqual(parameters["client_id"], GUID)
            self.assertEqual(parameters["tags"], ["governance", "internal"])
            self.assertEqual(parameters["source_sha"], "a" * 40)
            self.assertEqual(parameters["cli_version"], "1.198.0")
            self.assertRegex(parameters["cli_profile_hash"], r"^sha256:[0-9a-f]{64}$")
            self.assertRegex(parameters["dist_digest"], r"^sha256:[0-9a-f]{64}$")
            self.assertRegex(parameters["package_digest"], r"^sha256:[0-9a-f]{64}$")
            self.assertEqual(
                parameters["package_digest_algorithm"],
                self.module.PACKAGE_DIGEST_ALGORITHM,
            )
            self.assertRegex(
                parameters["candidate_package_file_digest"],
                r"^sha256:[0-9a-f]{64}$",
            )

            pack = next(stage for stage in plan["stages"] if stage["name"] == "pack")
            publish = next(
                stage for stage in plan["stages"] if stage["name"] == "publish"
            )
            deploy = next(stage for stage in plan["stages"] if stage["name"] == "deploy")
            for unsupported in (
                "--base-url",
                "--org-id",
                "--tenant-id",
                "--profile",
                "--reuse-client",
            ):
                self.assertNotIn(unsupported, pack["command"])
            self.assertIn("--repository-commit", pack["command"])
            self.assertIn("--base-url", publish["command"])
            self.assertIn("--profile", publish["command"])
            self.assertIn("--path-name", deploy["command"])
            self.assertIn("--client-id", deploy["command"])
            self.assertIn("--tags", deploy["command"])

            persisted = json.loads(plan_path.read_text())
            persisted["parameters"]["tags"] = ["governance"]
            persisted["plan_hash"] = self.module._document_hash(
                persisted, "plan_hash"
            )
            plan_path.write_text(json.dumps(persisted))
            with self.assertRaisesRegex(SystemExit, "deployment_binding_hash"):
                self.module.main(["--plan", str(plan_path)])

    def test_execution_requires_the_exact_explicit_plan_hash_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            plan_path, plan = self.create_plan(root)

            with self.assertRaisesRegex(SystemExit, "approved-plan-hash"):
                self.module.main(["--plan", str(plan_path), "--execute"])
            with self.assertRaisesRegex(SystemExit, "approved-plan-hash"):
                self.module.main(
                    [
                        "--plan",
                        str(plan_path),
                        "--execute",
                        "--approved-plan-hash",
                        "sha256:" + "0" * 64,
                    ]
                )
            self.assertIn('version = "1.2.3"', (root / "pyproject.toml").read_text())
            self.assertFalse(self.module._receipt_path(plan_path).exists())
            self.assertRegex(plan["plan_hash"], r"^sha256:[0-9a-f]{64}$")

    def test_package_content_digest_is_stable_while_exact_file_digest_is_audited(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_package = write_package(
                Path(first),
                envelope_nonce="first",
                project_id=GUID,
            )
            second_package = write_package(
                Path(second),
                envelope_nonce="second",
                project_id=TENANT_GUID,
            )
            first_content, first_file = self.module._package_evidence(
                first_package,
                package_name="fixture-app",
                main_file="index.html",
            )
            second_content, second_file = self.module._package_evidence(
                second_package,
                package_name="fixture-app",
                main_file="index.html",
            )
            self.assertEqual(first_content, second_content)
            self.assertNotEqual(first_file, second_file)

            write_package(
                Path(second),
                envelope_nonce="third",
                project_id=TENANT_GUID,
                main_payload=b"changed payload\n",
            )
            changed_content, _ = self.module._package_evidence(
                second_package,
                package_name="fixture-app",
                main_file="index.html",
            )
            self.assertNotEqual(first_content, changed_content)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            plan_path, plan = self.create_plan(root)
            candidate_file = plan["parameters"]["candidate_package_file_digest"]

            def simulate_repack(cmd, cwd, env):
                if cmd[1:3] == ["codedapp", "pack"]:
                    write_package(
                        root,
                        envelope_nonce="execution",
                        project_id=TENANT_GUID,
                    )

            with mock.patch.object(self.module, "_run", side_effect=simulate_repack):
                self.module.main(self.execution_args(plan_path))
            receipt = json.loads(self.module._receipt_path(plan_path).read_text())
            _, execution_file = self.module._package_evidence(
                root / plan["parameters"]["package_path"],
                package_name="fixture-app",
                main_file="index.html",
            )
            self.assertNotEqual(execution_file, candidate_file)
            self.assertEqual(receipt["package_file_digest"], execution_file)
            self.assertEqual(
                receipt["package_digest_algorithm"],
                self.module.PACKAGE_DIGEST_ALGORITHM,
            )

    def test_exact_package_file_drift_after_validation_blocks_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            plan_path, _ = self.create_plan(root)
            original_execute_stage = self.module._execute_stage
            remote_calls = []

            def mutate_after_package(stage, plan, env):
                result = original_execute_stage(stage, plan, env)
                if stage["name"] == "package":
                    write_package(
                        root,
                        envelope_nonce="post-validation-drift",
                        project_id=TENANT_GUID,
                    )
                return result

            with mock.patch.object(
                self.module,
                "_execute_stage",
                side_effect=mutate_after_package,
            ), mock.patch.object(
                self.module,
                "_run",
                side_effect=lambda cmd, cwd, env: remote_calls.append(cmd),
            ):
                with self.assertRaisesRegex(SystemExit, "changed after package validation"):
                    self.module.main(self.execution_args(plan_path))
            self.assertFalse(
                any(
                    command[1:3] in (
                        ["codedapp", "publish"],
                        ["codedapp", "deploy"],
                    )
                    for command in remote_calls
                )
            )

    def test_dist_and_package_digest_drift_fail_before_remote_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            plan_path, _ = self.create_plan(root)
            (root / "dist" / "index.html").write_text("changed\n")
            with self.assertRaisesRegex(SystemExit, "dist digest changed"):
                self.module.main(self.execution_args(plan_path))
            self.assertFalse(self.module._receipt_path(plan_path).exists())

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            plan_path, plan = self.create_plan(root)
            write_package(root, main_payload=b"tampered\n")
            remote_calls = []
            with mock.patch.object(
                self.module,
                "_run",
                side_effect=lambda cmd, cwd, env: remote_calls.append(cmd),
            ):
                with self.assertRaisesRegex(SystemExit, "package content digest"):
                    self.module.main(self.execution_args(plan_path))
            self.assertFalse(
                any(command[1:3] == ["codedapp", "pack"] for command in remote_calls)
            )
            self.assertFalse(
                any(
                    command[1:3] in (
                        ["codedapp", "publish"],
                        ["codedapp", "deploy"],
                    )
                    for command in remote_calls
                )
            )

    def test_receipt_repeats_the_approved_release_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            plan_path, plan = self.create_plan(root)
            receipt = self.module._new_receipt(plan, plan["plan_hash"])

            self.assertEqual(receipt["schema_version"], "2.2")
            self.assertEqual(receipt["environment"], "staging")
            self.assertEqual(receipt["approved_plan_hash"], plan["plan_hash"])
            self.assertEqual(
                receipt["deployment_binding_hash"],
                plan["deployment_binding_hash"],
            )
            for field in (
                "cli_profile_hash",
                "cli_executable_sha256",
                "source_sha",
                "dist_digest",
                "package_digest",
                "package_digest_algorithm",
                "candidate_package_file_digest",
            ):
                self.assertEqual(receipt[field], plan["parameters"][field])
            self.assertEqual(
                receipt["raw_worktree_digest_algorithm"],
                self.module.RAW_WORKTREE_DIGEST_ALGORITHM,
            )
            self.assertEqual(
                receipt["raw_worktree_initial_digest"],
                plan["inputs"]["raw_worktree"]["initial"],
            )

    def test_published_v2_2_contract_schemas_cover_generated_documents(self):
        plan_schema = json.loads(PLAN_SCHEMA.read_text(encoding="utf-8"))
        receipt_schema = json.loads(RECEIPT_SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(plan_schema["properties"]["schema_version"]["const"], "2.2")
        self.assertEqual(receipt_schema["properties"]["schema_version"]["const"], "2.2")
        self.assertFalse(plan_schema["additionalProperties"])
        self.assertFalse(receipt_schema["additionalProperties"])
        self.assertEqual(
            plan_schema["properties"]["parameters"]["properties"][
                "package_digest_algorithm"
            ]["const"],
            self.module.PACKAGE_DIGEST_ALGORITHM,
        )
        self.assertEqual(
            receipt_schema["properties"]["package_digest_algorithm"]["const"],
            self.module.PACKAGE_DIGEST_ALGORITHM,
        )
        control_planes = {
            choice["const"]
            for choice in plan_schema["properties"]["parameters"]["properties"][
                "control_plane_url"
            ]["oneOf"]
            if "const" in choice
        }
        self.assertEqual(
            control_planes,
            {
                self.module.STAGING_CONTROL_PLANE_URL,
                self.module.ALPHA_CONTROL_PLANE_URL,
            },
        )
        environment_schema = plan_schema["properties"]["parameters"]["properties"][
            "environment"
        ]
        self.assertEqual(
            environment_schema["oneOf"][1]["enum"],
            ["staging", "alpha"],
        )
        self.assertEqual(
            receipt_schema["properties"]["environment"]["enum"],
            ["staging", "alpha"],
        )
        self.assertEqual(
            len(plan_schema["properties"]["parameters"]["allOf"]),
            3,
        )
        self.assertEqual(
            {
                tuple(choice["const"])
                for choice in plan_schema["properties"]["inputs"]["properties"][
                    "scope"
                ]["oneOf"]
            },
            {
                ("pyproject.toml", "uipath.json"),
                ("pyproject.toml", "uipath.json", "uv.lock"),
            },
        )
        self.assertEqual(
            plan_schema["$defs"]["inputSnapshot"]["properties"]["files"][
                "maxItems"
            ],
            3,
        )
        self.assertIn(
            "uv.lock",
            plan_schema["$defs"]["fileHash"]["properties"]["path"]["enum"],
        )
        self.assertEqual(
            plan_schema["$defs"]["rawWorktreeSnapshot"]["properties"]["algorithm"][
                "const"
            ],
            self.module.RAW_WORKTREE_DIGEST_ALGORITHM,
        )
        self.assertEqual(
            receipt_schema["properties"]["raw_worktree_digest_algorithm"]["const"],
            self.module.RAW_WORKTREE_DIGEST_ALGORITHM,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            _, plan = self.create_plan(root)
            receipt = self.module._new_receipt(plan, plan["plan_hash"])
            self.assertEqual(set(plan), set(plan_schema["required"]))
            self.assertEqual(set(receipt), set(receipt_schema["required"]))
            self.assertEqual(
                set(plan["parameters"]),
                set(plan_schema["properties"]["parameters"]["required"]),
            )

    def test_v2_1_plan_is_rejected_without_silent_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root)
            write_dist(root)
            plan_path, plan = self.create_plan(root)
            plan["schema_version"] = "2.1"
            plan["plan_hash"] = self.module._document_hash(plan, "plan_hash")
            plan_path.write_text(json.dumps(plan), encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "expected .*version 2.2.*Regenerate"):
                self.module._load_plan(plan_path)


class SourceValidationIntegrationTests(unittest.TestCase):
    """Exercise the real Git source guard without replacing _validate_source."""

    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def run_main(self, argv):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = self.module.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def git(self, root: Path, *arguments: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()

    def prepare_repository(
        self,
        workspace: Path,
        *,
        with_build: bool = False,
        with_lock: bool = False,
        with_submodule: bool = False,
        with_mask_filter: bool = False,
    ) -> tuple[Path, Path, dict]:
        root = workspace / "project"
        root.mkdir()
        write_project(root)
        (root / ".gitignore").write_text(
            ".uipath/\ndist/\napp/dist/\n",
            encoding="utf-8",
        )
        if not with_mask_filter:
            (root / "tracked.txt").write_text("approved\n", encoding="utf-8")
        if with_lock:
            uv = shutil.which("uv")
            if uv is None:
                self.skipTest("uv is unavailable")
            subprocess.run(
                [uv, "lock", "--offline"],
                cwd=root,
                check=True,
                capture_output=True,
            )
        if with_build:
            (root / "app").mkdir()
            (root / "app" / "package.json").write_text(
                '{"scripts":{"build":"vite build"}}\n',
                encoding="utf-8",
            )
            (root / "app" / "generated.ts").write_text(
                "export const generated = 'initial';\n",
                encoding="utf-8",
            )
            write_dist(root, "app/dist")
            dist = "app/dist"
        else:
            write_dist(root)
            dist = "dist"

        self.git(root, "init", "--initial-branch=main")
        self.git(root, "config", "user.email", "fixture@example.invalid")
        self.git(root, "config", "user.name", "Fixture User")
        self.git(root, "add", ".")
        self.git(root, "commit", "-m", "fixture source")
        if with_mask_filter:
            filter_script = workspace / "mask-filter.py"
            filter_script.write_text(
                "import sys\nsys.stdin.buffer.read()\nsys.stdout.buffer.write(b'MASKED\\n')\n",
                encoding="utf-8",
            )
            self.git(
                root,
                "config",
                "filter.mask.clean",
                f"{shlex.quote(sys.executable)} {shlex.quote(str(filter_script))}",
            )
            self.git(root, "config", "filter.mask.smudge", "cat")
            self.git(root, "config", "filter.mask.required", "true")
            (root / ".gitattributes").write_text(
                "tracked.txt filter=mask\n",
                encoding="utf-8",
            )
            self.git(root, "add", ".gitattributes")
            self.git(root, "commit", "-m", "configure deterministic clean filter")
            (root / "tracked.txt").write_text("approved\n", encoding="utf-8")
            self.git(root, "add", "tracked.txt")
            self.git(root, "commit", "-m", "add filtered fixture file")
            self.assertEqual(self.git(root, "status", "--porcelain=v1"), "")
        if with_submodule:
            submodule_origin = workspace / "submodule-origin"
            submodule_origin.mkdir()
            self.git(submodule_origin, "init", "--initial-branch=main")
            self.git(submodule_origin, "config", "user.email", "fixture@example.invalid")
            self.git(submodule_origin, "config", "user.name", "Fixture User")
            (submodule_origin / "source.txt").write_text(
                "approved submodule\n",
                encoding="utf-8",
            )
            self.git(submodule_origin, "add", "source.txt")
            self.git(submodule_origin, "commit", "-m", "fixture submodule")
            self.git(
                root,
                "-c",
                "protocol.file.allow=always",
                "submodule",
                "add",
                str(submodule_origin),
                "modules/fixture",
            )
            self.git(
                root,
                "config",
                "-f",
                ".gitmodules",
                "submodule.modules/fixture.ignore",
                "all",
            )
            self.git(root, "add", ".gitmodules", "modules/fixture")
            self.git(root, "commit", "-m", "add ignored submodule")
        source_sha = self.git(root, "rev-parse", "HEAD")

        package_path = write_package(root)
        package_digest, _ = self.module._package_evidence(
            package_path,
            package_name="fixture-app",
            main_file="index.html",
        )
        dist_digest = self.module._directory_digest(root, dist)
        self.assertIsNotNone(dist_digest)
        plan_path = workspace / "deploy-plan.json"
        argv = [
            "--project-root",
            str(root),
            "--plan-output",
            str(plan_path),
            "--format",
            "json",
            "--environment",
            "staging",
            "--control-plane-url",
            self.module.STAGING_CONTROL_PLANE_URL,
            "--org-id",
            GUID,
            "--tenant-id",
            TENANT_GUID,
            "--folder-key",
            GUID,
            "--set-version",
            "1.2.4",
            "--path-name",
            "fixture-app",
            "--client-id",
            GUID,
            "--tags",
            "governance,internal",
            "--source-sha",
            source_sha,
            "--dist-digest",
            dist_digest,
            "--package-digest",
            package_digest,
            "--cli-executable",
            sys.executable,
            "--cli-version",
            "1.198.0",
            "--cli-profile",
            "fixture-profile",
            "--skip-tests",
        ]
        if not with_build:
            argv.append("--skip-app-build")
        code, stdout, _ = self.run_main(argv)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout)["kind"], self.module.PLAN_KIND)
        return root, plan_path, json.loads(plan_path.read_text(encoding="utf-8"))

    def execute(self, plan_path: Path, *, run_side_effect=None):
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        args = [
            "--plan",
            str(plan_path),
            "--execute",
            "--approved-plan-hash",
            plan["plan_hash"],
            "--format",
            "json",
        ]
        with mock.patch.object(
            self.module,
            "_run",
            side_effect=run_side_effect,
        ), mock.patch.object(self.module, "_validate_cli"):
            return self.run_main(args)

    def test_exact_planned_version_mutation_passes_real_source_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, plan_path, plan = self.prepare_repository(Path(tmp))

            code, stdout, _ = self.execute(plan_path)

            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout)["status"], "succeeded")
            self.assertIn(
                f'version = "{plan["project"]["new_version"]}"',
                (root / "pyproject.toml").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                self.git(root, "status", "--porcelain=v1"),
                "M pyproject.toml",
            )
            receipt = self.module._load_receipt(
                self.module._receipt_path(plan_path),
                plan,
            )
            self.assertEqual(receipt["plan_hash"], plan["plan_hash"])
            self.assertEqual(
                receipt["input_hash"],
                plan["inputs"]["initial"]["hash"],
            )
            self.assertEqual(
                receipt["approved_plan_hash"],
                plan["plan_hash"],
            )

    def test_tracked_build_drift_fails_after_the_versioned_source_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, plan_path, _ = self.prepare_repository(
                Path(tmp),
                with_build=True,
            )

            def mutate_tracked_build_output(cmd, cwd, env):
                if cmd[:3] == ["npm", "run", "build"]:
                    (root / "app" / "generated.ts").write_text(
                        "export const generated = 'drifted';\n",
                        encoding="utf-8",
                    )

            with self.assertRaisesRegex(SystemExit, "HEAD-tracked worktree file"):
                self.execute(plan_path, run_side_effect=mutate_tracked_build_output)

            receipt = json.loads(
                self.module._receipt_path(plan_path).read_text(encoding="utf-8")
            )
            self.assertEqual(receipt["status"], "failed")
            source_stage = next(
                stage for stage in receipt["stages"] if stage["name"] == "source"
            )
            self.assertEqual(source_stage["status"], "failed")

    def test_untracked_source_with_newline_fails_before_any_project_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, plan_path, plan = self.prepare_repository(Path(tmp))
            (root / "untracked\nsource.ts").write_text("drift\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "untracked drift"):
                self.execute(plan_path)

            self.assertIn(
                f'version = "{plan["project"]["old_version"]}"',
                (root / "pyproject.toml").read_text(encoding="utf-8"),
            )
            self.assertFalse(self.module._receipt_path(plan_path).exists())

    def test_assume_unchanged_cannot_hide_a_modified_tracked_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, plan_path, plan = self.prepare_repository(Path(tmp))
            self.git(root, "update-index", "--assume-unchanged", "tracked.txt")
            (root / "tracked.txt").write_text("hidden drift\n", encoding="utf-8")
            self.assertEqual(self.git(root, "status", "--porcelain=v1"), "")

            with self.assertRaisesRegex(SystemExit, "assume-unchanged"):
                self.execute(plan_path)

            self.assertIn(
                f'version = "{plan["project"]["old_version"]}"',
                (root / "pyproject.toml").read_text(encoding="utf-8"),
            )
            self.assertFalse(self.module._receipt_path(plan_path).exists())

    def test_skip_worktree_cannot_hide_a_modified_tracked_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, plan_path, plan = self.prepare_repository(Path(tmp))
            self.git(root, "update-index", "--skip-worktree", "tracked.txt")
            (root / "tracked.txt").write_text("hidden drift\n", encoding="utf-8")
            self.assertEqual(self.git(root, "status", "--porcelain=v1"), "")

            with self.assertRaisesRegex(SystemExit, "skip-worktree"):
                self.execute(plan_path)

            self.assertIn(
                f'version = "{plan["project"]["old_version"]}"',
                (root / "pyproject.toml").read_text(encoding="utf-8"),
            )
            self.assertFalse(self.module._receipt_path(plan_path).exists())

    def test_submodule_ignore_all_cannot_hide_tracked_content_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, plan_path, plan = self.prepare_repository(
                Path(tmp),
                with_submodule=True,
            )
            (root / "modules" / "fixture" / "source.txt").write_text(
                "hidden submodule drift\n",
                encoding="utf-8",
            )
            self.assertEqual(self.git(root, "status", "--porcelain=v1"), "")

            with self.assertRaisesRegex(
                SystemExit,
                "HEAD-tracked worktree file|raw worktree digests|Raw tracked",
            ):
                self.execute(plan_path)

            self.assertIn(
                f'version = "{plan["project"]["old_version"]}"',
                (root / "pyproject.toml").read_text(encoding="utf-8"),
            )
            self.assertFalse(self.module._receipt_path(plan_path).exists())

    def test_clean_filter_cannot_hide_staged_status_empty_raw_byte_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, plan_path, plan = self.prepare_repository(
                Path(tmp),
                with_mask_filter=True,
            )
            self.assertEqual(
                self.git(root, "show", "HEAD:tracked.txt"),
                self.git(root, "show", ":tracked.txt"),
            )
            approved_raw_digest = plan["inputs"]["raw_worktree"]["initial"]
            (root / "tracked.txt").write_text(
                "raw bytes changed after approval\n",
                encoding="utf-8",
            )
            self.git(root, "add", "tracked.txt")
            self.assertEqual(self.git(root, "status", "--porcelain=v1"), "")
            self.assertEqual(
                self.git(root, "diff", "--cached", "--name-only"),
                "",
            )
            self.assertNotEqual(
                self.module._raw_tracked_worktree_digest(
                    root,
                    plan["parameters"]["source_sha"],
                ),
                approved_raw_digest,
            )

            with self.assertRaisesRegex(SystemExit, "raw worktree digests|Raw tracked"):
                self.execute(plan_path)

            self.assertIn(
                f'version = "{plan["project"]["old_version"]}"',
                (root / "pyproject.toml").read_text(encoding="utf-8"),
            )
            self.assertFalse(self.module._receipt_path(plan_path).exists())

    def test_unchanged_filtered_worktree_executes_against_approved_raw_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, plan_path, plan = self.prepare_repository(
                Path(tmp),
                with_mask_filter=True,
            )
            self.assertEqual(
                (root / "tracked.txt").read_text(encoding="utf-8"),
                "approved\n",
            )
            self.assertEqual(self.git(root, "status", "--porcelain=v1"), "")

            code, stdout, _ = self.execute(plan_path)

            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout)["status"], "succeeded")
            receipt = self.module._load_receipt(
                self.module._receipt_path(plan_path),
                plan,
            )
            self.assertEqual(
                receipt["raw_worktree_initial_digest"],
                plan["inputs"]["raw_worktree"]["initial"],
            )

    def test_real_uv_lock_version_transition_is_plan_bound_and_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, plan_path, plan = self.prepare_repository(
                Path(tmp),
                with_lock=True,
            )

            def run_real_uv_only(cmd, cwd, env):
                if cmd[:2] == ["uv", "lock"]:
                    subprocess.run(cmd, cwd=cwd, env=env, check=True, capture_output=True)

            code, stdout, _ = self.execute(
                plan_path,
                run_side_effect=run_real_uv_only,
            )

            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout)["status"], "succeeded")
            self.assertEqual(
                plan["inputs"]["scope"],
                ["pyproject.toml", "uipath.json", "uv.lock"],
            )
            uv_lock = (root / "uv.lock").read_text(encoding="utf-8")
            self.assertIn('version = "1.2.4"', uv_lock)
            self.assertNotIn('version = "1.2.3"', uv_lock)
            receipt = self.module._load_receipt(
                self.module._receipt_path(plan_path),
                plan,
            )
            self.assertEqual(receipt["plan_hash"], plan["plan_hash"])
            self.assertEqual(
                receipt["input_hash"],
                plan["inputs"]["initial"]["hash"],
            )

    def test_resume_accepts_only_the_plan_bound_post_version_pre_lock_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, plan_path, plan = self.prepare_repository(
                Path(tmp),
                with_lock=True,
            )

            def fail_before_uv_mutation(cmd, cwd, env):
                if cmd[:2] == ["uv", "lock"]:
                    raise RuntimeError("synthetic lock failure")

            with self.assertRaisesRegex(RuntimeError, "synthetic lock failure"):
                self.execute(plan_path, run_side_effect=fail_before_uv_mutation)
            self.assertIn(
                f'version = "{plan["project"]["new_version"]}"',
                (root / "pyproject.toml").read_text(encoding="utf-8"),
            )
            self.assertIn(
                f'version = "{plan["project"]["old_version"]}"',
                (root / "uv.lock").read_text(encoding="utf-8"),
            )

            def run_real_uv_only(cmd, cwd, env):
                if cmd[:2] == ["uv", "lock"]:
                    subprocess.run(cmd, cwd=cwd, env=env, check=True, capture_output=True)

            plan_document = json.loads(plan_path.read_text(encoding="utf-8"))
            args = [
                "--plan",
                str(plan_path),
                "--execute",
                "--approved-plan-hash",
                plan_document["plan_hash"],
                "--resume",
                "--format",
                "json",
            ]
            with mock.patch.object(
                self.module,
                "_run",
                side_effect=run_real_uv_only,
            ), mock.patch.object(self.module, "_validate_cli"):
                code, stdout, _ = self.run_main(args)

            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout)["status"], "succeeded")
            self.assertIn(
                f'version = "{plan["project"]["new_version"]}"',
                (root / "uv.lock").read_text(encoding="utf-8"),
            )

    def test_rehashed_arbitrary_uv_lock_transition_fails_before_version_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, plan_path, plan = self.prepare_repository(
                Path(tmp),
                with_lock=True,
            )
            uv_record = next(
                record
                for record in plan["inputs"]["versioned"]["files"]
                if record["path"] == "uv.lock"
            )
            uv_record["sha256"] = self.module._hash_bytes(b"arbitrary lock bytes")
            plan["inputs"]["versioned"]["hash"] = self.module._hash_json(
                {"files": plan["inputs"]["versioned"]["files"]}
            )
            plan["plan_hash"] = self.module._document_hash(plan, "plan_hash")
            plan_path.write_text(json.dumps(plan), encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "versioned uv.lock hash"):
                self.execute(plan_path)

            self.assertIn(
                f'version = "{plan["project"]["old_version"]}"',
                (root / "pyproject.toml").read_text(encoding="utf-8"),
            )
            self.assertFalse(self.module._receipt_path(plan_path).exists())


if __name__ == "__main__":
    unittest.main()
