import argparse
import contextlib
import copy
import importlib.util
import io
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
CORE_SCRIPT = ROOT / "scripts" / "uipcodedappdeploy.py"
RECOVERY_SCRIPT = ROOT / "scripts" / "uipcodedappdeploy_recover.py"
TESTING_SCRIPT = ROOT / "scripts" / "uipcodedappdeploy_testing.py"
POC_SCRIPT = ROOT / "scripts" / "uipcodedappdeploy_poc.py"
POC_SCHEMA = ROOT / "references" / "deployment-poc-receipt.v1.schema.json"

ORG_ID = "83a60daf-a85e-4834-8980-2aaa3f6ac2e0"
TENANT_ID = "5d2f728f-9b74-45cc-bdce-e1b2818dbcf8"
FOLDER_ID = "99999999-8888-7777-6666-555555555555"
CLIENT_ID = "11111111-2222-3333-4444-555555555555"
DEPLOYMENT_ID = "4d27d32b-06a2-4599-abc0-add36d900bdf"
SYSTEM_NAME = "IDe01ca22e102b4a33bbfadf0970bea626"


def load_modules():
    for name, script in (
        ("uipcodedappdeploy", CORE_SCRIPT),
        ("uipcodedappdeploy_recover", RECOVERY_SCRIPT),
        ("uipcodedappdeploy_testing", TESTING_SCRIPT),
        ("uipcodedappdeploy_poc_module", POC_SCRIPT),
    ):
        spec = importlib.util.spec_from_file_location(name, script)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return (
        sys.modules["uipcodedappdeploy"],
        sys.modules["uipcodedappdeploy_recover"],
        sys.modules["uipcodedappdeploy_testing"],
        sys.modules["uipcodedappdeploy_poc_module"],
    )


class UiPathCodedAppDeployPocTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core, cls.recovery, cls.testing, cls.poc = load_modules()
        cls.schema = json.loads(POC_SCHEMA.read_text(encoding="utf-8"))
        cls.validator = Draft202012Validator(cls.schema, format_checker=FormatChecker())

    def config(self, root: Path, *, environment="alpha", app_type="web"):
        control = {
            "alpha": "https://alpha.uipath.com",
            "staging": "https://staging.uipath.com",
            "production": "https://cloud.uipath.com",
        }[environment]
        api = {
            "alpha": "https://alpha.api.uipath.com",
            "staging": "https://staging.api.uipath.com",
            "production": "https://api.uipath.com",
        }[environment]
        profile_hash = self.core._hash_bytes(b"profile")
        config = {
            "kind": self.poc.CONFIG_KIND,
            "schema_version": self.poc.CONFIG_VERSION,
            "project_key": self.poc._project_key(root),
            "project_root": str(root),
            "environment": environment,
            "control_plane_url": control,
            "api_url": api,
            "organization_id": ORG_ID,
            "organization_name": "agenticgtm",
            "tenant_id": TENANT_ID,
            "tenant_name": "Dev",
            "folder_key": FOLDER_ID,
            "folder_name": "POC",
            "folder_path": "Shared/POC",
            "folder_type": "Standard",
            "cli_profile": "dev",
            "cli_profile_hash": profile_hash,
            "app_type": app_type,
            "package_name": "example-poc",
            "app_name": "Example POC",
            "path_name": "example-poc",
            "client_id": CLIENT_ID if app_type == "web" else None,
            "tags": ["poc", "internal"],
            "node_executable": "/absolute/node",
            "node_executable_sha256": self.core._hash_bytes(b"node"),
            "node_version": "24.13.0",
            "runtime_manifest": "/absolute/runtime.json",
            "runtime_manifest_sha256": self.core._hash_bytes(b"runtime-manifest"),
            "configured_at": "2026-08-12T00:00:00+00:00",
        }
        config["config_hash"] = self.core._document_hash(config, "config_hash")
        return config

    def runtime(self):
        return {
            "manifest": "/absolute/runtime.json",
            "manifest_sha256": self.core._hash_bytes(b"runtime-manifest"),
            "cli": "/absolute/uip",
            "cli_sha256": self.poc.CLI_SHA256,
            "codedapp_guarded_sha256": self.poc.CODEDAPP_GUARDED_SHA256,
            "orchestrator_sha256": self.poc.ORCHESTRATOR_SHA256,
            "patch_contract_sha256": self.core._hash_bytes(b"patch"),
        }

    def candidate(self, *, intent="create"):
        return {
            "intent": intent,
            "version": "1.0.1",
            "local_version": "1.0.0",
            "deployment_id": DEPLOYMENT_ID if intent == "upgrade" else None,
            "current_version": "1.0.0" if intent == "upgrade" else None,
            "system_name": SYSTEM_NAME,
            "deploy_version": 2,
            "evidence": {
                "dist_sha256": self.core._hash_bytes(b"dist"),
                "app_config_sha256": self.core._hash_bytes(b"config"),
                "package_content_sha256": self.core._hash_bytes(b"content"),
                "package_file_sha256": self.core._hash_bytes(b"file"),
            },
            "package_path": "/absolute/example-poc.1.0.1.nupkg",
        }

    def args(self, **overrides):
        values = {
            "execute": True,
            "production_execute": False,
            "customer_data_approved": False,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def receipt(self, root: Path, *, app_type="web"):
        config = self.config(root, app_type=app_type)
        reservation = {"path": "/absolute/reservation", "sha256": self.core._hash_bytes(b"reservation")}
        receipt = self.poc._new_receipt(
            config,
            {
                "execute": True,
                "production_execute": False,
                "customer_data_approved": False,
                "data_classification": "synthetic",
                "current_request_only": True,
            },
            self.candidate(),
            self.runtime(),
            root / "receipt.json",
            reservation,
            root / "workspace",
            root / "claim.json",
        )
        receipt["status"] = "succeeded_poc_deploy"
        receipt["verification"]["configuration_verified"] = True
        receipt["verification"]["route_verified"] = app_type == "web"
        receipt["receipt_hash"] = self.core._document_hash(receipt, "receipt_hash")
        return receipt

    def test_exact_199_patch_is_deterministic_and_all_anchors_are_unique(self):
        synthetic = "\n".join(old for old, _ in self.poc.POC_PATCH_EDITS).encode()
        with mock.patch.object(self.poc.core, "_hash_bytes", return_value=self.poc.CODEDAPP_SHA256):
            patched = self.poc._patched_tool_bytes(synthetic).decode()
        for old, new in self.poc.POC_PATCH_EDITS:
            self.assertNotIn(old, patched)
            self.assertIn(new, patched)
        self.assertIn("fresh deploy prohibited", patched)
        self.assertIn("pocUpgradeMode ? undefined", patched)
        self.assertIn("POC_DEPLOYMENT_IDENTITY_AMBIGUOUS", patched)
        self.assertIn("POC_PUBLISHED_IDENTITY_AMBIGUOUS", patched)

    def test_runtime_contract_is_exact_199_and_disables_cli_mutation(self):
        self.assertEqual(self.poc.CLI_VERSION, "1.199.0")
        self.assertEqual(self.poc.CLI_GIT_HEAD, "723e6801b77b5926ba75e75b6a756cc38b1b7adc")
        environment = self.poc._safe_environment({"HOME": str(Path.home())})
        self.assertEqual(environment["UIPATH_CLI_DISABLE_VERSION_SYNC"], "1")
        self.assertEqual(environment["UIPATH_CLI_DISABLE_AUTOINSTALL"], "1")
        self.assertNotIn("UIPATH_ACCESS_TOKEN", environment)

    def test_runtime_provision_self_test_requires_syntax_and_guard_rejection(self):
        paths = {
            "root": Path("/runtime"),
            "cli": Path("/runtime/node_modules/@uipath/cli/dist/index.js"),
            "codedapp": Path("/runtime/node_modules/@uipath/codedapp-tool/dist/tool.js"),
        }
        node = {"executable": "/node"}
        syntax = mock.Mock(returncode=0, stdout="", stderr="")
        blocked = mock.Mock(
            returncode=1,
            stdout=json.dumps({
                "Result": "Failure",
                "Instructions": "POC_GUARD_REQUIRED: isolated runtime",
            }),
            stderr="",
        )
        with mock.patch.object(self.poc.subprocess, "run", side_effect=[syntax, blocked]) as run:
            self.poc._runtime_self_test(paths, node)
        self.assertEqual(run.call_count, 2)
        self.assertIn("--check", run.call_args_list[0].args[0])
        self.assertNotIn("--poc-mode", run.call_args_list[1].args[0])
        unguarded = mock.Mock(
            returncode=0,
            stdout=json.dumps({"Result": "Success", "Instructions": ""}),
            stderr="",
        )
        with (
            mock.patch.object(self.poc.subprocess, "run", side_effect=[syntax, unguarded]),
            self.assertRaises(SystemExit),
        ):
            self.poc._runtime_self_test(paths, node)

    def test_safe_environment_rejects_node_and_token_injection(self):
        for name in ("NODE_OPTIONS", "UIPATH_ACCESS_TOKEN", "HTTPS_PROXY"):
            with self.subTest(name=name), self.assertRaises(SystemExit):
                self.poc._safe_environment({"HOME": str(Path.home()), name: "x"})

    def test_authorization_matrix_for_all_environments_and_customer_data(self):
        for environment in ("alpha", "staging"):
            self.poc._authorize(self.args(), environment, "synthetic")
        with self.assertRaises(SystemExit):
            self.poc._authorize(self.args(), "production", "synthetic")
        self.poc._authorize(self.args(production_execute=True), "production", "internal")
        with self.assertRaises(SystemExit):
            self.poc._authorize(self.args(production_execute=True), "production", "customer")
        approved = self.poc._authorize(
            self.args(production_execute=True, customer_data_approved=True),
            "production",
            "customer",
        )
        self.assertTrue(approved["production_execute"])
        self.assertTrue(approved["customer_data_approved"])
        with self.assertRaises(SystemExit):
            self.poc._authorize(self.args(execute=False), "alpha", "synthetic")
        with mock.patch.dict(
            self.poc.os.environ,
            {"PRODUCTION_EXECUTE": "1", "CUSTOMER_DATA_APPROVED": "1"},
            clear=False,
        ), self.assertRaises(SystemExit):
            self.poc._authorize(self.args(), "production", "customer")

    def test_public_parser_exposes_only_explicit_four_command_interface(self):
        parser = self.poc._parser()
        configure = parser.parse_args([
            "configure", "--project-root", "/project", "--environment", "production",
            "--profile", "dev", "--folder", "Shared/POC", "--app-type", "action",
        ])
        self.assertEqual(configure.command, "configure")
        deploy = parser.parse_args([
            "deploy", "--project-root", "/project", "--intent", "upgrade",
            "--data-classification", "customer", "--execute", "--production-execute",
            "--customer-data-approved",
        ])
        self.assertEqual(deploy.intent, "upgrade")
        recovery = parser.parse_args(["recover-published", "--receipt", "/receipt", "--execute"])
        self.assertEqual(recovery.command, "recover-published")
        deploy_recovery = parser.parse_args([
            "recover-deploy-indeterminate", "--receipt", "/receipt",
            "--source-helper", "/source-helper", "--execute",
        ])
        self.assertEqual(deploy_recovery.command, "recover-deploy-indeterminate")
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            parser.parse_args(["deploy", "--project-root", "/project", "--intent", "create"])

    def test_next_semver_uses_local_or_advances_remote_deterministically(self):
        cases = (
            ("1.2.3", [], "1.2.3"),
            ("1.2.4", ["1.2.3"], "1.2.4"),
            ("1.2.3", ["1.2.3"], "1.2.4"),
            ("1.2.3-alpha.2", ["1.2.3-alpha.2"], "1.2.3-alpha.3"),
            ("1.2.3-preview", ["1.2.3-preview"], "1.2.3-preview.1"),
            ("1.0.0", ["1.9.9", "2.0.0"], "2.0.1"),
        )
        for local, remote, expected in cases:
            with self.subTest(local=local, remote=remote):
                self.assertEqual(self.poc._next_version(local, remote), expected)

    def test_project_requires_one_lockfile_and_declared_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "package-lock.json").write_text("{}\n", encoding="utf-8")
            with mock.patch.object(self.poc.shutil, "which", return_value="/bin/sh"):
                executable, command = self.poc._package_manager(root)
            self.assertEqual(executable, "/bin/sh")
            self.assertEqual(command[-2:], ["run", "build"])
            (root / "yarn.lock").write_text("\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                self.poc._package_manager(root)

    def test_private_config_is_mode_0600_hash_bound_and_strict(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self.config(root)
            with mock.patch.object(self.poc, "_poc_root", return_value=root / ".poc"):
                path = self.poc._config_path(root)
                self.poc._atomic_private_json(path, config, overwrite=False)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                _, loaded = self.poc._load_config(root)
                self.assertEqual(loaded, config)
                tampered = copy.deepcopy(config)
                tampered["unexpected"] = True
                self.poc._atomic_private_json(path, tampered, overwrite=True)
                with self.assertRaises(SystemExit):
                    self.poc._load_config(root)
                path.unlink()
                path.symlink_to(root / "elsewhere")
                with self.assertRaises(SystemExit):
                    self.poc._load_config(root)

    def test_web_binding_enforces_each_environment_host_and_api(self):
        for environment, host in (
            ("alpha", "agenticgtm.alpha.uipath.host"),
            ("staging", "agenticgtm.staging.uipath.host"),
            ("production", "agenticgtm.uipath.host"),
        ):
            project = {
                "uipath": {
                    "clientId": CLIENT_ID,
                    "scope": "openid profile OR.Default Apps.Read Apps.Write",
                    "baseUrl": self.poc.TARGETS[environment]["api_url"],
                    "redirectUri": f"https://{host}/example-poc",
                }
            }
            self.assertEqual(
                self.poc._web_binding(project, environment, "agenticgtm"),
                {"client_id": CLIENT_ID, "path_name": "example-poc"},
            )
            project["uipath"]["baseUrl"] = "https://api.uipath.com"
            if environment != "production":
                with self.assertRaises(SystemExit):
                    self.poc._web_binding(project, environment, "agenticgtm")

    def test_configure_binds_each_environment_and_both_app_types(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            node = {"executable": "/node", "sha256": self.core._hash_bytes(b"node"), "version": "24.13.0"}
            runtime = self.runtime()
            folder = {
                "folder_key": FOLDER_ID,
                "folder_name": "POC",
                "folder_path": "Shared/POC",
                "folder_type": "Standard",
            }
            for environment in ("alpha", "staging", "production"):
                for app_type in ("web", "action"):
                    with self.subTest(environment=environment, app_type=app_type):
                        status = {
                            "Status": "Logged in",
                            "BaseUrl": self.poc.TARGETS[environment]["control_plane_url"],
                            "OrganizationId": ORG_ID,
                            "OrganizationName": "agenticgtm",
                            "TenantId": TENANT_ID,
                            "TenantName": "Dev",
                        }
                        args = argparse.Namespace(
                            project_root=str(root), environment=environment,
                            profile="dev", folder="Shared/POC", app_type=app_type,
                            app_name=None, path_name=None, client_id=None, tags=None,
                            node_executable=None, npm_executable=None, replace=True,
                        )
                        project = {
                            "package_name": "example-poc",
                            "version": "1.0.0",
                            "author": "UiPath Developer",
                            "uipath": {} if app_type == "web" else None,
                        }
                        binding = {"client_id": CLIENT_ID, "path_name": "example-poc"}
                        with (
                            mock.patch.object(self.poc, "_node_runtime", return_value=node),
                            mock.patch.object(self.poc, "_poc_root", return_value=root / ".poc"),
                            mock.patch.object(self.poc, "_provision_runtime", return_value=runtime),
                            mock.patch.object(self.poc, "_profile_status", return_value=status),
                            mock.patch.object(self.poc, "_resolve_folder", return_value=folder),
                            mock.patch.object(self.poc, "_load_project", return_value=project),
                            mock.patch.object(self.poc, "_web_binding", return_value=binding),
                        ):
                            path = self.poc._configure(args)
                        document = self.poc._load_private_json(path, "configured target")
                        self.assertEqual(document["environment"], environment)
                        self.assertEqual(document["app_type"], app_type)
                        self.assertEqual(document["control_plane_url"], self.poc.TARGETS[environment]["control_plane_url"])
                        self.assertEqual(document["client_id"], CLIENT_ID if app_type == "web" else None)

    def test_revalidation_detects_profile_and_folder_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self.config(root)
            project = {"package_name": "example-poc", "version": "1.0.0", "author": "x", "uipath": {}}
            status = {
                "Status": "Logged in",
                "BaseUrl": config["control_plane_url"],
                "OrganizationId": ORG_ID,
                "OrganizationName": "agenticgtm",
                "TenantId": TENANT_ID,
                "TenantName": "Dev",
            }
            folder = {key: config[key] for key in ("folder_key", "folder_name", "folder_path", "folder_type")}
            with (
                mock.patch.object(self.poc, "_load_project", return_value=project),
                mock.patch.object(self.poc, "_web_binding", return_value={"client_id": CLIENT_ID, "path_name": "example-poc"}),
                mock.patch.object(self.poc, "_profile_status", return_value=status),
                mock.patch.object(self.poc, "_resolve_folder", return_value=folder),
            ):
                self.poc._revalidate_target(root, config, self.runtime(), {"executable": "/node"})
            drifted = copy.deepcopy(status)
            drifted["TenantId"] = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
            with (
                mock.patch.object(self.poc, "_load_project", return_value=project),
                mock.patch.object(self.poc, "_web_binding", return_value={"client_id": CLIENT_ID, "path_name": "example-poc"}),
                mock.patch.object(self.poc, "_profile_status", return_value=drifted),
                self.assertRaises(SystemExit),
            ):
                self.poc._revalidate_target(root, config, self.runtime(), {"executable": "/node"})

    def test_web_and_action_command_shapes_are_distinct_and_guarded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = self.runtime()
            node = {"executable": "/node"}
            web = self.config(root, app_type="web")
            action = self.config(root, app_type="action")
            for config in (web, action):
                command = self.poc._guard_command(
                    runtime, node, config, self.candidate(intent="upgrade"),
                    "upgrade-execute",
                    {"system_name": SYSTEM_NAME, "deploy_version": 2},
                )
                self.assertNotIn("--name", command)
                self.assertIn("--poc-expected-deployment-id", command)
                self.assertIn("--poc-expected-current-version", command)
                self.assertIn("--poc-expected-route-name", command)
                self.assertEqual(command[command.index("--poc-mode") + 1], "upgrade-execute")
            self.assertIn("--client-id", self.poc._base_guard_command(runtime, node, web, "1.0.0", "inspect"))
            self.assertNotIn("--client-id", self.poc._base_guard_command(runtime, node, action, "1.0.0", "inspect"))
            self.assertIsNone(self.poc._app_url(action))
            self.assertEqual(self.poc._app_url(web), "https://agenticgtm.alpha.uipath.host/example-poc")

    def test_inspect_accepts_cli_pascal_case_nested_observations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self.config(root)
            envelope = {
                "Result": "Success",
                "Code": "DeployCompleted",
                "Data": {
                    "Message": "POC remote state inspected.",
                    "AppType": "Web",
                    "AppName": "Example POC",
                    "RouteName": "example-poc",
                    "AppUrl": "https://agenticgtm.alpha.uipath.host/example-poc",
                    "RouteAvailable": False,
                    "Deployment": {
                        "Id": DEPLOYMENT_ID,
                        "Title": "example-poc",
                        "RoutingName": "example-poc",
                        "SemVersion": "1.0.0",
                    },
                    "PublishedVersions": [{
                        "Version": "1.0.1",
                        "SystemName": SYSTEM_NAME,
                        "DeployVersion": 2,
                    }],
                    "Operation": "poc_inspect",
                },
            }
            with mock.patch.object(self.poc, "_run_read", return_value=json.dumps(envelope)):
                observed = self.poc._inspect(
                    self.runtime(), {"executable": "/node"}, config, root, "1.0.1"
                )
            self.assertEqual(observed["deployment"]["id"], DEPLOYMENT_ID)
            self.assertEqual(observed["deployment"]["semVersion"], "1.0.0")
            self.assertEqual(observed["published_versions"][0]["version"], "1.0.1")
            self.assertEqual(observed["published_versions"][0]["deploy_version"], 2)

    def test_create_and_upgrade_preconditions_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self.config(Path(temporary))
            absent = {"deployment": None, "route_available": True}
            self.assertEqual(self.poc._validate_intent(absent, config, "create")["deployment_id"], None)
            occupied = {"deployment": None, "route_available": False}
            with self.assertRaises(SystemExit):
                self.poc._validate_intent(occupied, config, "create")
            with self.assertRaises(SystemExit):
                self.poc._validate_intent(absent, config, "upgrade")
            deployed = {
                "deployment": {
                    "id": DEPLOYMENT_ID,
                    "title": "Example POC",
                    "routingName": "example-poc",
                    "semVersion": "1.0.0",
                },
                "route_available": False,
            }
            self.assertEqual(self.poc._validate_intent(deployed, config, "upgrade")["deployment_id"], DEPLOYMENT_ID)

    def test_publish_uses_action_type_and_one_write_call(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self.config(root, app_type="action")
            document = {
                "Result": "Success",
                "Code": "PublishCompleted",
                "Data": {
                    "PackageName": "example-poc",
                    "PackageVersion": "1.0.1",
                    "AppType": "Action",
                },
            }
            with mock.patch.object(self.poc, "_run_write", return_value=document) as write:
                self.poc._publish(self.runtime(), {"executable": "/node"}, config, root, "1.0.1")
            write.assert_called_once()
            command = write.call_args.args[0]
            self.assertEqual(command[command.index("--type") + 1], "Action")

    def test_external_write_failure_is_indeterminate_and_never_replayed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "receipt.json"
            receipt = self.receipt(root)
            receipt["status"] = "in_progress"
            self.poc._write_receipt(path, receipt)
            with self.assertRaises(self.poc.PocCommandError):
                self.poc._stage(
                    receipt, path, "publish", "external_write",
                    lambda: (_ for _ in ()).throw(self.poc.PocCommandError("PUBLISH_INDETERMINATE")),
                    external_write=True,
                    failure_status="publish_indeterminate",
                    failure_code="PUBLISH_INDETERMINATE",
                )
            loaded = self.poc._load_private_json(path, "receipt")
            self.assertEqual(loaded["status"], "publish_indeterminate")
            self.assertTrue(loaded["external_write_started"])
            self.assertEqual(loaded["stages"][-1]["status"], "indeterminate")

    def test_receipt_schema_accepts_web_and_action_and_rejects_overclaim(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for app_type in ("web", "action"):
                receipt = self.receipt(root, app_type=app_type)
                errors = list(self.validator.iter_errors(receipt))
                self.assertEqual(errors, [], [error.message for error in errors])
            receipt["policy"]["release_evidence"] = True
            self.assertTrue(list(self.validator.iter_errors(receipt)))
            receipt = self.receipt(root)
            receipt["unknown"] = True
            self.assertTrue(list(self.validator.iter_errors(receipt)))

    def test_source_receipt_recovery_accepts_only_unrecovered_publish_states(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "source.json"
            for status in ("publish_indeterminate", "published_not_deployed"):
                receipt = self.receipt(root)
                receipt["status"] = status
                receipt["receipt_hash"] = self.core._document_hash(receipt, "receipt_hash")
                self.poc._atomic_private_json(path, receipt, overwrite=path.exists())
                self.assertEqual(self.poc._load_source_receipt(path)["status"], status)
            receipt["recovery_source"] = {"path": "x", "receipt_hash": self.core._hash_bytes(b"x"), "file_sha256": self.core._hash_bytes(b"y")}
            receipt["receipt_hash"] = self.core._document_hash(receipt, "receipt_hash")
            self.poc._atomic_private_json(path, receipt, overwrite=True)
            with self.assertRaises(SystemExit):
                self.poc._load_source_receipt(path)

    def test_deploy_recovery_accepts_only_unrecovered_indeterminate_receipts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "source.json"
            receipt = self.receipt(root)
            receipt["status"] = "deploy_indeterminate"
            receipt["external_write_started"] = True
            receipt["receipt_hash"] = self.core._document_hash(receipt, "receipt_hash")
            self.poc._atomic_private_json(path, receipt, overwrite=False)
            loaded = self.poc._load_source_receipt(
                path,
                allowed_statuses=frozenset({"deploy_indeterminate"}),
                command_name="recover-deploy-indeterminate",
            )
            self.assertEqual(loaded["status"], "deploy_indeterminate")
            receipt["status"] = "succeeded_poc_deploy"
            receipt["receipt_hash"] = self.core._document_hash(receipt, "receipt_hash")
            self.poc._atomic_private_json(path, receipt, overwrite=True)
            with self.assertRaises(SystemExit):
                self.poc._load_source_receipt(
                    path,
                    allowed_statuses=frozenset({"deploy_indeterminate"}),
                    command_name="recover-deploy-indeterminate",
                )

    def test_deploy_recovery_validates_original_retained_claim_namespace_and_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            poc_root = Path(temporary) / ".poc"
            claims = poc_root / "claims"
            claims.mkdir(parents=True)
            root = Path(temporary) / "project"
            root.mkdir()
            config = self.config(root)
            candidate = self.candidate(intent="upgrade")
            source = {"claim": {"retained": True}, "candidate": candidate}
            expected_key = self.core._hash_json({
                "environment": config["environment"], "organization_id": config["organization_id"],
                "tenant_id": config["tenant_id"], "folder_key": config["folder_key"],
                "app_name": config["app_name"], "intent": candidate["intent"],
                "version": candidate["version"], "source_hash": None,
            })
            path = claims / f"{expected_key.removeprefix('sha256:')}.json"
            document = {
                "kind": "uipcodedappdeploy.poc-claim", "schema_version": "1.0",
                "key": expected_key, "created_at": "2026-08-12T00:00:00+00:00",
            }
            document["claim_hash"] = self.core._document_hash(document, "claim_hash")
            self.poc._atomic_private_json(path, document, overwrite=False)
            source["claim"]["path"] = str(path)
            with mock.patch.object(self.poc, "_poc_root", return_value=poc_root):
                evidence = self.poc._validate_retained_source_claim(source, config)
            self.assertEqual(Path(evidence["path"]), path.resolve())
            document["key"] = self.core._hash_bytes(b"drift")
            document["claim_hash"] = self.core._document_hash(document, "claim_hash")
            self.poc._atomic_private_json(path, document, overwrite=True)
            with mock.patch.object(self.poc, "_poc_root", return_value=poc_root), self.assertRaises(SystemExit):
                self.poc._validate_retained_source_claim(source, config)

    def test_deploy_recovery_observation_requires_exact_prior_and_candidate_identity(self):
        root = Path("/project")
        config = self.config(root)
        candidate = self.candidate(intent="upgrade")
        observation = {
            "route_available": False,
            "deployment": {
                "id": DEPLOYMENT_ID, "title": config["app_name"],
                "routingName": config["path_name"], "semVersion": "1.0.0",
            },
            "published_versions": [{
                "version": "1.0.1", "system_name": SYSTEM_NAME, "deploy_version": 2,
            }],
        }
        self.assertEqual(
            self.poc._validate_deploy_recovery_observation(observation, config, candidate)["deploy_version"],
            2,
        )
        observation["deployment"]["semVersion"] = "1.0.1"
        with self.assertRaises(SystemExit):
            self.poc._validate_deploy_recovery_observation(observation, config, candidate)

    def test_deploy_recovery_executes_one_guarded_upgrade_without_rebuild_or_publish(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            workspace = root / "retained-workspace"
            (workspace / "dist").mkdir(parents=True)
            app_config = workspace / self.core.APP_CONFIG_RELATIVE_PATH
            app_config.parent.mkdir(parents=True, exist_ok=True)
            app_config.write_bytes(b"retained-app-config")
            package = workspace / "example-poc.1.0.1.nupkg"
            package.write_bytes(b"retained-package")
            source_helper = root / "source-helper.py"
            source_helper.write_bytes(b"source-helper")

            config = self.config(root)
            runtime = self.runtime()
            candidate = self.candidate(intent="upgrade")
            candidate["package_path"] = str(package)
            candidate["evidence"]["app_config_sha256"] = self.core._hash_file(
                app_config, "fixture app config"
            )
            source = self.receipt(root)
            source["status"] = "deploy_indeterminate"
            source["external_write_started"] = True
            source["candidate"] = copy.deepcopy(candidate)
            source["runtime"] = copy.deepcopy(runtime)
            source["evidence"]["project_root"] = str(root)
            source["evidence"]["workspace"] = str(workspace)
            source["receipt_hash"] = self.core._document_hash(source, "receipt_hash")
            source_path = root / "source-receipt.json"
            self.poc._atomic_private_json(source_path, source, overwrite=False)

            before = {
                "route_available": False,
                "deployment": {
                    "id": DEPLOYMENT_ID,
                    "title": config["app_name"],
                    "routingName": config["path_name"],
                    "semVersion": candidate["current_version"],
                },
                "published_versions": [{
                    "version": candidate["version"],
                    "system_name": SYSTEM_NAME,
                    "deploy_version": 2,
                }],
            }
            after = copy.deepcopy(before)
            after["deployment"]["semVersion"] = candidate["version"]
            output = root / "recovery-receipt.json"
            claim_path = root / "transition-claim.json"
            args = self.args(
                receipt=str(source_path),
                source_helper=str(source_helper),
                receipt_output=str(output),
                verify_timeout=15,
            )

            with (
                mock.patch.object(self.poc, "_load_source_receipt", return_value=source),
                mock.patch.object(self.poc, "_project_root", return_value=root),
                mock.patch.object(self.poc, "_load_config", return_value=(root / "target.json", config)),
                mock.patch.object(self.poc, "_configured_node", return_value={"executable": "/node"}),
                mock.patch.object(self.poc, "_validate_runtime", return_value=runtime),
                mock.patch.object(self.poc, "_revalidate_target"),
                mock.patch.object(
                    self.poc, "_validate_source_helper",
                    return_value={"path": str(source_helper), "sha256": self.core._hash_file(source_helper, "fixture helper")},
                ),
                mock.patch.object(
                    self.poc, "_validate_retained_source_claim",
                    return_value={"path": str(root / "source-claim.json"), "file_sha256": self.core._hash_bytes(b"claim")},
                ),
                mock.patch.object(self.poc.testing, "_directory_digest", return_value=candidate["evidence"]["dist_sha256"]),
                mock.patch.object(
                    self.poc.core, "_package_evidence",
                    return_value=(candidate["evidence"]["package_content_sha256"], candidate["evidence"]["package_file_sha256"]),
                ),
                mock.patch.object(self.poc, "_inspect", side_effect=[before, before, after]),
                mock.patch.object(
                    self.poc, "_reserve",
                    return_value={"path": str(root / "reservation"), "sha256": self.core._hash_bytes(b"reservation")},
                ),
                mock.patch.object(self.poc, "_claim", return_value=(claim_path, {"claim": "fixture"})),
                mock.patch.object(self.poc, "_run_write", return_value={"Result": "Success"}) as write,
                mock.patch.object(self.poc.core, "_verify_url", return_value={"status": 200}),
                mock.patch.object(self.poc, "_verify_config", return_value=candidate["evidence"]["app_config_sha256"]),
                mock.patch.object(self.poc, "_build") as build,
                mock.patch.object(self.poc, "_pack") as pack,
                mock.patch.object(self.poc, "_publish") as publish,
            ):
                self.assertEqual(self.poc._recover_deploy_indeterminate(args), output.resolve())

            write.assert_called_once()
            command = write.call_args.args[0]
            self.assertEqual(command[command.index("--poc-mode") + 1], "upgrade-execute")
            build.assert_not_called()
            pack.assert_not_called()
            publish.assert_not_called()
            recovered = self.poc._load_private_json(output, "recovery receipt")
            self.assertEqual(recovered["status"], "succeeded_poc_deploy")
            self.assertEqual(recovered["candidate"], candidate)
            self.assertTrue(recovered["verification"]["route_verified"])
            self.assertEqual(list(self.validator.iter_errors(recovered)), [])

    def test_existing_governed_and_testing_contract_versions_are_unchanged(self):
        self.assertEqual(self.core.PLAN_SCHEMA_VERSION, "2.3")
        self.assertEqual(self.core.RECEIPT_SCHEMA_VERSION, "2.3")
        self.assertEqual(self.testing.RECEIPT_SCHEMA_VERSION, "1.2")
        self.assertEqual(self.testing.POLICY_VERSION, "1.2")


if __name__ == "__main__":
    unittest.main()
