import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CORE_SCRIPT = ROOT / "scripts" / "uipcodedappdeploy.py"
RECOVERY_SCRIPT = ROOT / "scripts" / "uipcodedappdeploy_recover.py"
PLAN_SCHEMA = ROOT / "references" / "deployment-recovery-plan.v1.schema.json"
RECEIPT_SCHEMA = ROOT / "references" / "deployment-recovery-receipt.v1.schema.json"


def load_modules():
    core_spec = importlib.util.spec_from_file_location("uipcodedappdeploy", CORE_SCRIPT)
    core = importlib.util.module_from_spec(core_spec)
    assert core_spec.loader is not None
    sys.modules[core_spec.name] = core
    core_spec.loader.exec_module(core)

    recovery_spec = importlib.util.spec_from_file_location(
        "uipcodedappdeploy_recover_module", RECOVERY_SCRIPT
    )
    recovery = importlib.util.module_from_spec(recovery_spec)
    assert recovery_spec.loader is not None
    sys.modules[recovery_spec.name] = recovery
    recovery_spec.loader.exec_module(recovery)
    return core, recovery


class UiPathCodedAppDeployRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core, cls.recovery = load_modules()

    def context(self, root: Path):
        cli = str(root / "uip")
        node = str(root / "node")
        recovery_cli = str(root / "recovery-runtime" / "node_modules" / "@uipath" / "cli" / "dist" / "index.js")
        command = [
            cli,
            "codedapp",
            "deploy",
            "--version",
            "0.1.2",
            "--path-name",
            "aura-vdp-mockup",
            "--client-id",
            "11111111-2222-3333-4444-555555555555",
            "--tags",
            "aura-vdp,internal,mockup",
            "--base-url",
            "https://alpha.uipath.com",
            "--org-id",
            "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "--org-name",
            "agenticgtm",
            "--tenant-id",
            "66666666-7777-8888-9999-000000000000",
            "--profile",
            "fixture-alpha",
            "--folder-key",
            "99999999-8888-7777-6666-555555555555",
        ]
        parameters = {
            "environment": "alpha",
            "control_plane_url": "https://alpha.uipath.com",
            "org_name": "agenticgtm",
            "org_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "tenant_name": "Dev",
            "tenant_id": "66666666-7777-8888-9999-000000000000",
            "folder_key": "99999999-8888-7777-6666-555555555555",
            "client_id": "11111111-2222-3333-4444-555555555555",
            "app_name": "Aura VDP Template Mockup",
            "package_name": "aura-vdp-template-mockup",
            "app_type": "Web",
            "path_name": "aura-vdp-mockup",
            "source_sha": "1" * 40,
            "package_path": ".uipath/aura-vdp-template-mockup.0.1.2.nupkg",
            "package_digest": "sha256:" + "2" * 64,
            "candidate_package_file_digest": "sha256:" + "3" * 64,
            "cli_executable": cli,
            "cli_executable_sha256": "sha256:" + "4" * 64,
            "cli_version": "1.198.0",
            "cli_profile": "fixture-alpha",
            "cli_profile_hash": "sha256:" + "5" * 64,
            "tags": ["aura-vdp", "internal", "mockup"],
        }
        failed_plan = {
            "project": {"root": str(root), "new_version": "0.1.2"},
            "parameters": parameters,
            "plan_hash": "sha256:" + "6" * 64,
            "deployment_binding_hash": "sha256:" + "7" * 64,
            "stages": [
                {
                    "name": "deploy",
                    "action": "command",
                    "effect": "external_write",
                    "cwd": ".",
                    "command": command,
                }
            ],
        }
        failed_receipt = {
            "approved_plan_hash": failed_plan["plan_hash"],
            "package_file_digest": "sha256:" + "8" * 64,
            "status": "in_progress",
            "stages": [
                {
                    "name": "deploy",
                    "effect": "external_write",
                    "status": "running",
                    "recovery": "redacted_indeterminate_external_write; reconcile remote state; blind resume prohibited",
                }
            ],
        }
        deployment = {
            "system_name": "ID" + "a" * 32,
            "deployment_id": "12345678-1234-1234-1234-123456789abc",
            "app_url": "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup",
        }
        runtime = {
            "root": str(root / "recovery-runtime"),
            "node_modules_root": str(root / "recovery-runtime" / "node_modules"),
            "tree_sha256": "sha256:" + "a" * 64,
            "workspace": str(root / "recovery-runtime" / self.recovery.ISOLATED_WORKSPACE_RELATIVE),
            "workspace_app_config": str(root / "recovery-runtime" / self.recovery.ISOLATED_WORKSPACE_RELATIVE / self.core.APP_CONFIG_RELATIVE_PATH),
            "workspace_app_config_sha256": "sha256:" + "f" * 64,
            "self_test": {
                "node_syntax": "passed",
                "dynamic_tool_resolution": "passed",
                "unguarded_deploy": "blocked_before_network",
                "verify_only_without_guard": "blocked_before_network",
            },
            "node_executable": node,
            "node_executable_sha256": "sha256:" + "0" * 64,
            "node_version": "24.13.0",
            "cli_executable": recovery_cli,
            "cli_executable_sha256": parameters["cli_executable_sha256"],
            "source_tool_file": str(root / "node_modules/@uipath/codedapp-tool/dist/tool.js"),
            "source_tool_file_sha256": self.recovery.EXPECTED_CODEDAPP_TOOL_SHA256,
            "source_tool_manifest": str(root / "node_modules/@uipath/codedapp-tool/package.json"),
            "source_tool_manifest_sha256": "sha256:" + "b" * 64,
            "runtime_tool_file": str(root / "recovery-runtime/node_modules/@uipath/codedapp-tool/dist/tool.js"),
            "runtime_tool_file_sha256": "sha256:" + "c" * 64,
            "runtime_tool_manifest": str(root / "recovery-runtime/node_modules/@uipath/codedapp-tool/package.json"),
            "runtime_tool_manifest_sha256": "sha256:" + "b" * 64,
            "version": "1.198.0",
            "git_head": self.recovery.EXPECTED_CODEDAPP_TOOL_GIT_HEAD,
            "patch_algorithm": self.recovery.PATCH_ALGORITHM,
            "patch_contract_sha256": "sha256:" + "d" * 64,
            "manifest_hash": "sha256:" + "e" * 64,
        }
        recovery_command = self.recovery._guarded_upgrade_command(
            command,
            node_executable=node,
            runtime_cli=recovery_cli,
            deployment_id=deployment["deployment_id"],
            system_name=deployment["system_name"],
            deploy_version=3,
            current_version="0.1.1",
            route_name="aura-vdp-mockup",
        )
        return {
            "prior_plan": {
                "project": {"root": str(root / "prior"), "new_version": "0.1.1"},
                "plan_hash": "sha256:" + "9" * 64,
            },
            "failed_plan": failed_plan,
            "failed_receipt": failed_receipt,
            "deployment": deployment,
            "candidate_system_name": deployment["system_name"],
            "candidate_deploy_version": 3,
            "runtime": runtime,
            "recovery_command": recovery_command,
            "remote_guard_command": self.recovery._remote_guard_command(
                recovery_command
            ),
            "post_upgrade_guard_command": self.recovery._remote_guard_command(
                recovery_command, expected_current_version="0.1.2"
            ),
        }

    def plan(self, root: Path):
        context = self.context(root)
        evidence = [
            {
                "label": label,
                "path": f"/evidence/{label}.json",
                "sha256": "sha256:" + str(index + 1) * 64,
            }
            for index, label in enumerate(self.recovery.EVIDENCE_LABELS)
        ]
        plan = {
            "kind": self.recovery.PLAN_KIND,
            "schema_version": self.recovery.PLAN_SCHEMA_VERSION,
            "created_at": "2026-08-05T06:00:00Z",
            "recovery_helper_sha256": self.core._hash_file(
                RECOVERY_SCRIPT, "recovery helper"
            ),
            "core_helper_path": str(CORE_SCRIPT.resolve()),
            "core_helper_sha256": self.core._hash_file(CORE_SCRIPT, "core helper"),
            "evidence": evidence,
            "evidence_binding_hash": self.core._hash_json(evidence),
            **self.recovery._expected_projection(context),
        }
        plan["plan_hash"] = self.core._document_hash(plan, "plan_hash")
        return plan, context

    def guard_output(self, current_version: str) -> str:
        return json.dumps(
            {
                "Result": "Success",
                "Code": "DeployCompleted",
                "Data": {
                    "Message": "Exact upgrade target verified; no mutation performed.",
                    "DeploymentId": "12345678-1234-1234-1234-123456789abc",
                    "SystemName": "ID" + "a" * 32,
                    "DeployVersion": 3,
                    "CurrentVersion": current_version,
                    "RouteName": "aura-vdp-mockup",
                    "Version": "0.1.2",
                    "AppName": "Aura VDP Template Mockup",
                    "AppUrl": "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup",
                    "Operation": "recovery_verify",
                },
            }
        )

    def claim(self, root: Path, plan: dict):
        claim_path = root / "execution-claim.json"
        claim = {
            "kind": "uipcodedappdeploy.upgrade-recovery-execution-claim",
            "schema_version": "1.0",
            "created_at": "2026-08-05T06:00:00Z",
            "plan_hash": plan["plan_hash"],
            "claim_key": plan["upgrade_guard"]["local_execution_claim_key"],
            "claim_scope": plan["upgrade_guard"]["local_execution_claim_scope"],
            "deployment_id": plan["existing_deployment"]["deployment_id"],
            "candidate_version": plan["candidate"]["version"],
        }
        claim["claim_hash"] = self.core._document_hash(claim, "claim_hash")
        claim_path.write_text(
            json.dumps(claim, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return claim_path, claim

    def test_recovery_command_is_exactly_guarded_and_retains_fail_safe_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = self.context(Path(tmp))
            original = context["failed_plan"]["stages"][0]["command"]
            recovered = context["recovery_command"]
            self.assertIn("--path-name", recovered)
            self.assertGreater(len(recovered), len(original))
            self.assertEqual(recovered[:4], [context["runtime"]["node_executable"], context["runtime"]["cli_executable"], "codedapp", "deploy"])
            for flag in self.recovery.RECOVERY_FLAGS:
                self.assertEqual(recovered.count(flag), 1)
            self.assertIn("12345678-1234-1234-1234-123456789abc", recovered)
            self.assertNotIn("pack", recovered)
            self.assertNotIn("publish", recovered)

    def test_recovery_command_rejects_missing_duplicate_or_changed_route(self):
        kwargs = {
            "node_executable": "/runtime/node",
            "runtime_cli": "/runtime/uip",
            "deployment_id": "12345678-1234-1234-1234-123456789abc",
            "system_name": "ID" + "a" * 32,
            "deploy_version": 3,
            "current_version": "0.1.1",
            "route_name": "route",
        }
        with self.assertRaisesRegex(SystemExit, "exactly one"):
            self.recovery._guarded_upgrade_command(
                ["uip", "codedapp", "deploy"], **kwargs
            )
        with self.assertRaisesRegex(SystemExit, "does not match"):
            self.recovery._guarded_upgrade_command(
                ["uip", "codedapp", "deploy", "--path-name", "other"],
                **kwargs,
            )
        with self.assertRaisesRegex(SystemExit, "exactly one"):
            self.recovery._guarded_upgrade_command(
                [
                    "uip",
                    "codedapp",
                    "deploy",
                    "--path-name",
                    "route",
                    "--path-name",
                    "route",
                ],
                **kwargs,
            )

    def test_plan_is_deterministically_bound_and_rejects_stage_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, context = self.plan(Path(tmp))
            with mock.patch.object(
                self.recovery, "_load_bound_evidence", return_value=context
            ):
                validated, _ = self.recovery._validate_plan(copy.deepcopy(plan))
                self.assertEqual(validated["plan_hash"], plan["plan_hash"])

                tampered = copy.deepcopy(plan)
                tampered["stages"][4]["command"][0] = "/unapproved/node"
                tampered["plan_hash"] = self.core._document_hash(
                    tampered, "plan_hash"
                )
                with self.assertRaisesRegex(SystemExit, "stages"):
                    self.recovery._validate_plan(tampered)

    def test_evidence_digest_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.json"
            path.write_text('{"value":1}\n', encoding="utf-8")
            record = self.recovery._evidence_record(path, "failed_plan")
            path.write_text('{"value":2}\n', encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "changed after plan approval"):
                self.recovery._validate_evidence_record(record, "failed_plan")

    def test_execution_requires_hash_and_never_republishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan, context = self.plan(root)
            plan_path = root / "recovery-plan.json"
            plan_path.write_text(json.dumps(plan) + "\n", encoding="utf-8")
            config_path = Path(plan["candidate"]["recovery_workspace"]) / self.core.APP_CONFIG_RELATIVE_PATH
            config_path.parent.mkdir(parents=True)
            config_path.write_text(
                json.dumps(
                    {
                        "appName": "aura-vdp-template-mockup",
                        "displayName": "Aura VDP Template Mockup",
                        "appType": "Web",
                        "appVersion": "0.1.2",
                        "systemName": "ID" + "a" * 32,
                        "appUrl": "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup",
                        "personalWorkspace": False,
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(SystemExit, "approved-plan-hash"):
                self.recovery._execute(plan, context, plan_path, None)

            claim_path, claim = self.claim(root, plan)
            with mock.patch.object(self.recovery, "_preflight"), mock.patch.object(
                self.recovery,
                "_create_execution_claim",
                return_value=(claim_path, claim),
            ), mock.patch.object(
                self.recovery,
                "_run_capture_recovery",
                side_effect=[self.guard_output("0.1.1"), self.guard_output("0.1.2")],
            ) as capture, mock.patch.object(
                self.recovery, "_revalidate_runtime_barrier"
            ), mock.patch.object(
                self.core, "_run"
            ) as run, mock.patch.object(self.core, "_verify_url") as verify:
                receipt_path = self.recovery._execute(
                    plan, context, plan_path, plan["plan_hash"]
                )

            run.assert_called_once()
            executed = run.call_args.args[0]
            self.assertEqual(executed, plan["stages"][4]["command"])
            self.assertIn("--path-name", executed)
            self.assertIn("--expected-deployment-id", executed)
            self.assertNotIn("pack", executed)
            self.assertNotIn("publish", executed)
            execution_environment = run.call_args.args[2]
            self.assertEqual(
                set(execution_environment),
                {
                    *self.recovery.RECOVERY_ENVIRONMENT_PRESERVE,
                    *self.recovery.RECOVERY_ENVIRONMENT_OVERRIDES,
                },
            )
            self.assertEqual(
                execution_environment["UIPATH_TELEMETRY_DISABLED"], "true"
            )
            self.assertEqual(capture.call_count, 2)
            capture.assert_has_calls(
                [
                    mock.call(
                        plan["stages"][2]["command"],
                        Path(plan["candidate"]["recovery_workspace"]),
                        mock.ANY,
                    ),
                    mock.call(
                        plan["stages"][5]["command"],
                        Path(plan["candidate"]["recovery_workspace"]),
                        mock.ANY,
                    ),
                ]
            )
            verify.assert_called_once_with(
                "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup", 30
            )
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "succeeded")
            self.assertEqual(
                receipt["pre_upgrade_guard_observation"]["currentVersion"],
                "0.1.1",
            )
            self.assertEqual(
                receipt["post_upgrade_guard_observation"]["currentVersion"],
                "0.1.2",
            )
            self.assertTrue(receipt["local_app_url_matches_verified_route"])
            self.assertTrue(all(stage["status"] == "succeeded" for stage in receipt["stages"]))
            self.assertFalse(receipt["execution_claim_released"])
            self.assertTrue(claim_path.exists())
            with self.assertRaisesRegex(SystemExit, "Blind resume is unsupported"):
                self.recovery._execute(
                    plan, context, plan_path, plan["plan_hash"]
                )

    def test_external_failure_stays_indeterminate_and_blocks_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan, context = self.plan(root)
            plan_path = root / "recovery-plan.json"
            plan_path.write_text(json.dumps(plan) + "\n", encoding="utf-8")
            claim_path, claim = self.claim(root, plan)
            with mock.patch.object(self.recovery, "_preflight"), mock.patch.object(
                self.recovery,
                "_create_execution_claim",
                return_value=(claim_path, claim),
            ), mock.patch.object(
                self.recovery, "_run_capture_recovery", return_value=self.guard_output("0.1.1")
            ), mock.patch.object(
                self.recovery, "_revalidate_runtime_barrier"
            ), mock.patch.object(
                self.core, "_run", side_effect=RuntimeError("remote ambiguity")
            ):
                with self.assertRaisesRegex(RuntimeError, "remote ambiguity"):
                    self.recovery._execute(
                        plan, context, plan_path, plan["plan_hash"]
                    )
            receipt = json.loads(
                self.recovery._receipt_path(plan_path).read_text(encoding="utf-8")
            )
            self.assertEqual(receipt["status"], "in_progress")
            self.assertEqual(receipt["stages"][4]["status"], "running")
            self.assertIn("blind retry", receipt["stages"][4]["recovery"])
            self.assertFalse(receipt["execution_claim_released"])
            self.assertTrue(claim_path.exists())

    def test_recovery_schemas_are_versioned_and_strict(self):
        plan_schema = json.loads(PLAN_SCHEMA.read_text(encoding="utf-8"))
        receipt_schema = json.loads(RECEIPT_SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(
            plan_schema["properties"]["kind"]["const"], self.recovery.PLAN_KIND
        )
        self.assertEqual(
            plan_schema["properties"]["schema_version"]["const"], "1.2"
        )
        self.assertFalse(plan_schema["additionalProperties"])
        self.assertEqual(
            receipt_schema["properties"]["kind"]["const"],
            self.recovery.RECEIPT_KIND,
        )
        self.assertFalse(receipt_schema["additionalProperties"])
        self.assertFalse(receipt_schema["$defs"]["target"]["additionalProperties"])
        self.assertFalse(
            receipt_schema["$defs"]["existingDeployment"]["additionalProperties"]
        )
        self.assertFalse(receipt_schema["$defs"]["candidate"]["additionalProperties"])
        self.assertEqual(
            plan_schema["properties"]["execution"]["const"]["environment_policy"],
            {
                "preserved": list(self.recovery.RECOVERY_ENVIRONMENT_PRESERVE),
                "forbidden": list(self.recovery.FORBIDDEN_RECOVERY_ENVIRONMENT),
                "overrides": self.recovery.RECOVERY_ENVIRONMENT_OVERRIDES,
            },
        )

    def test_recovery_environment_is_allowlisted_and_rejects_injection(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = {
                "HOME": tmp,
                "TMPDIR": "/unapproved/tmp",
                "UIPATH_CODING_AGENTS_LAST_UPDATE_CHECK_AT": "ignored",
                "npm_config_arch": "unapproved",
            }
            environment = self.recovery._recovery_environment(source)
            self.assertEqual(environment["HOME"], str(Path(tmp).resolve()))
            self.assertNotIn("TMPDIR", environment)
            self.assertNotIn("UIPATH_CODING_AGENTS_LAST_UPDATE_CHECK_AT", environment)
            self.assertNotIn("npm_config_arch", environment)
            self.assertEqual(
                environment["PATH"],
                self.recovery.RECOVERY_ENVIRONMENT_OVERRIDES["PATH"],
            )
            for name in self.recovery.FORBIDDEN_RECOVERY_ENVIRONMENT:
                with self.subTest(name=name), self.assertRaisesRegex(
                    SystemExit, "prohibited"
                ), mock.patch.object(self.recovery.subprocess, "run") as run:
                    self.recovery._recovery_environment(
                        {"HOME": tmp, name: "unapproved"}
                    )
                run.assert_not_called()

    def test_node_runtime_is_explicit_hashed_and_normalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            node = Path(tmp) / "node"
            node.write_bytes(b"node-fixture")
            node.chmod(0o755)
            version_completed = subprocess.CompletedProcess(
                [str(node), "--version"], 0, "v24.13.0\n", ""
            )
            path_completed = subprocess.CompletedProcess(
                [str(node), "-p", "process.execPath"],
                0,
                str(node.resolve()) + "\n",
                "",
            )
            with mock.patch.object(
                self.recovery.subprocess,
                "run",
                side_effect=[version_completed, path_completed],
            ) as run:
                observed = self.recovery._resolve_node_runtime(
                    node, {"HOME": "/tmp", "PATH": "/usr/bin"}
                )
            self.assertEqual(observed["executable"], str(node.resolve()))
            self.assertEqual(observed["version"], "24.13.0")
            self.assertEqual(
                observed["executable_sha256"], self.core._hash_file(node, "node")
            )
            self.assertEqual(run.call_args_list[0].args[0], [str(node.resolve()), "--version"])
            self.assertEqual(
                run.call_args_list[1].args[0],
                [str(node.resolve()), "-p", "process.execPath"],
            )

    def test_execution_claim_is_atomic_and_exact_candidate_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".uipath").mkdir()
            plan, _ = self.plan(home / "source")
            environment = {"HOME": str(home.resolve())}
            claim_path, claim = self.recovery._create_execution_claim(
                plan, environment
            )
            self.assertTrue(claim_path.is_file())
            self.assertEqual(
                claim["claim_key"],
                plan["upgrade_guard"]["local_execution_claim_key"],
            )
            with self.assertRaisesRegex(SystemExit, "already exists"):
                self.recovery._create_execution_claim(plan, environment)

    def test_patch_is_deterministic_and_contains_fail_closed_guards(self):
        source = "\n".join(old for old, _ in self.recovery.PATCH_EDITS).encode()
        with mock.patch.object(
            self.recovery,
            "EXPECTED_CODEDAPP_TOOL_SHA256",
            self.core._hash_bytes(source),
        ):
            patched = self.recovery._patched_tool_bytes(source).decode()
        self.assertIn("EXACT_UPGRADE_TARGET_MISMATCH", patched)
        self.assertIn("recoveryMode ? undefined", patched)
        self.assertIn("--expected-deployment-id", patched)
        self.assertIn("--recovery-verify-only", patched)
        self.assertIn("EXACT_UPGRADE_GUARD_REQUIRED", patched)
        self.assertIn("const recoveryMode = true", patched)
        self.assertLess(
            patched.index("EXACT_UPGRADE_TARGET_MISMATCH"),
            patched.index("let operationResult"),
        )
        self.assertIn(
            "recoveryMode ? undefined : options.pathName ? routingName : undefined",
            patched,
        )
        self.assertIn('result.operation !== "recovery_verify"', patched)

    def test_runtime_self_test_requires_syntax_and_two_fail_closed_invocations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = root / "uip"
            tool = root / "tool.js"
            cli.write_text("#!/usr/bin/env node\n", encoding="utf-8")
            tool.write_text("export {};\n", encoding="utf-8")
            blocked = json.dumps(
                {
                    "Result": "Failure",
                    "Instructions": "EXACT_UPGRADE_GUARD_REQUIRED",
                }
            )
            completed = [
                subprocess.CompletedProcess([], 0, "", ""),
                subprocess.CompletedProcess([], 1, blocked, ""),
                subprocess.CompletedProcess([], 1, blocked, ""),
            ]
            with mock.patch.object(
                self.recovery.subprocess, "run", side_effect=completed
            ) as run:
                result = self.recovery._self_test_runtime(
                    cli,
                    tool,
                    root,
                    Path("/usr/bin/node"),
                    {
                        "HOME": "/tmp",
                        "UIPATH_CLI_DISABLE_VERSION_SYNC": "1",
                        "UIPATH_TELEMETRY_DISABLED": "true",
                    },
                )
            self.assertEqual(run.call_count, 3)
            self.assertEqual(result["dynamic_tool_resolution"], "passed")
            self.assertEqual(result["unguarded_deploy"], "blocked_before_network")
            for call in run.call_args_list:
                self.assertEqual(call.args[0][0], "/usr/bin/node")
                self.assertEqual(
                    call.kwargs["env"]["UIPATH_TELEMETRY_DISABLED"], "true"
                )
                self.assertEqual(
                    call.kwargs["env"]["UIPATH_CLI_DISABLE_VERSION_SYNC"], "1"
                )

    def test_post_deploy_config_allows_missing_deployment_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan, _ = self.plan(root)
            config = {
                "appName": "aura-vdp-template-mockup",
                "displayName": "Aura VDP Template Mockup",
                "appType": "Web",
                "appVersion": "0.1.2",
                "systemName": "ID" + "a" * 32,
                "appUrl": "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup",
            }
            path = Path(plan["candidate"]["recovery_workspace"]) / self.core.APP_CONFIG_RELATIVE_PATH
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(config), encoding="utf-8")
            claim_path, claim = self.claim(root, plan)
            receipt = self.recovery._new_receipt(
                plan, plan["plan_hash"], claim_path, claim
            )
            self.recovery._inspect_post_deploy_config(
                Path(plan["candidate"]["recovery_workspace"]), plan, receipt
            )
            self.assertIsNone(config.get("deploymentId"))
            self.assertTrue(receipt["local_app_url_matches_verified_route"])

    def test_post_write_verification_failure_is_deployed_unverified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan, context = self.plan(root)
            plan_path = root / "recovery-plan.json"
            plan_path.write_text(json.dumps(plan) + "\n", encoding="utf-8")
            claim_path, claim = self.claim(root, plan)
            with mock.patch.object(self.recovery, "_preflight"), mock.patch.object(
                self.recovery,
                "_create_execution_claim",
                return_value=(claim_path, claim),
            ), mock.patch.object(
                self.recovery,
                "_run_capture_recovery",
                side_effect=[self.guard_output("0.1.1"), self.guard_output("0.1.2")],
            ), mock.patch.object(
                self.recovery, "_revalidate_runtime_barrier"
            ), mock.patch.object(self.core, "_run"), mock.patch.object(
                self.core, "_verify_url", side_effect=SystemExit(1)
            ):
                with self.assertRaises(SystemExit):
                    self.recovery._execute(
                        plan, context, plan_path, plan["plan_hash"]
                    )
            receipt = json.loads(
                self.recovery._receipt_path(plan_path).read_text(encoding="utf-8")
            )
            self.assertEqual(receipt["status"], "deployed_unverified")
            self.assertIn("do not redeploy", receipt["stages"][6]["recovery"])

    def test_post_upgrade_guard_mismatch_is_deployed_unverified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan, context = self.plan(root)
            plan_path = root / "recovery-plan.json"
            plan_path.write_text(json.dumps(plan) + "\n", encoding="utf-8")
            stale = self.guard_output("0.1.1")
            claim_path, claim = self.claim(root, plan)
            with mock.patch.object(self.recovery, "_preflight"), mock.patch.object(
                self.recovery,
                "_create_execution_claim",
                return_value=(claim_path, claim),
            ), mock.patch.object(
                self.recovery,
                "_run_capture_recovery",
                side_effect=[stale, stale, stale, stale],
            ), mock.patch.object(
                self.recovery, "_revalidate_runtime_barrier"
            ), mock.patch.object(self.core, "_run"), mock.patch.object(
                self.recovery.time, "sleep"
            ), mock.patch.object(self.core, "_verify_url") as verify:
                with self.assertRaises(SystemExit):
                    self.recovery._execute(
                        plan, context, plan_path, plan["plan_hash"]
                    )
            receipt = json.loads(
                self.recovery._receipt_path(plan_path).read_text(encoding="utf-8")
            )
            self.assertEqual(receipt["status"], "deployed_unverified")
            self.assertEqual(receipt["stages"][5]["status"], "failed")
            self.assertIn("do not redeploy", receipt["stages"][5]["recovery"])
            verify.assert_not_called()

    def test_runtime_barrier_failure_stops_before_external_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan, context = self.plan(root)
            plan_path = root / "recovery-plan.json"
            plan_path.write_text(json.dumps(plan) + "\n", encoding="utf-8")
            claim_path, claim = self.claim(root, plan)
            with mock.patch.object(self.recovery, "_preflight"), mock.patch.object(
                self.recovery,
                "_create_execution_claim",
                return_value=(claim_path, claim),
            ), mock.patch.object(
                self.recovery, "_run_capture_recovery", return_value=self.guard_output("0.1.1")
            ), mock.patch.object(
                self.recovery,
                "_revalidate_runtime_barrier",
                side_effect=SystemExit(1),
            ), mock.patch.object(self.core, "_run") as run:
                with self.assertRaises(SystemExit):
                    self.recovery._execute(
                        plan, context, plan_path, plan["plan_hash"]
                    )
            receipt = json.loads(
                self.recovery._receipt_path(plan_path).read_text(encoding="utf-8")
            )
            self.assertEqual(receipt["status"], "failed")
            self.assertEqual(receipt["stages"][3]["status"], "failed")
            self.assertTrue(receipt["execution_claim_released"])
            self.assertFalse(claim_path.exists())
            run.assert_not_called()

    def test_runtime_barrier_rejects_node_digest_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, context = self.plan(Path(tmp))
            context["runtime_manifest"] = {}
            observed = copy.deepcopy(context["runtime"])
            observed["node_executable_sha256"] = "sha256:" + "9" * 64
            with mock.patch.object(
                self.recovery, "_validate_runtime_manifest", return_value=observed
            ), mock.patch.object(self.recovery, "_validate_failed_app_config"):
                with self.assertRaisesRegex(
                    SystemExit, "node_executable_sha256"
                ):
                    self.recovery._revalidate_runtime_barrier(
                        plan,
                        context,
                        {"HOME": str(Path(tmp).resolve())},
                    )

    def test_remote_guard_rejects_non_success_or_extra_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, _ = self.plan(Path(tmp))
            failed = json.loads(self.guard_output("0.1.1"))
            failed["Result"] = "Failure"
            with self.assertRaisesRegex(SystemExit, "non-success envelope"):
                self.recovery._validate_remote_guard_output(
                    json.dumps(failed),
                    plan,
                    expected_current_version="0.1.1",
                )
            extra = json.loads(self.guard_output("0.1.1"))
            extra["Data"]["Unexpected"] = True
            with self.assertRaisesRegex(SystemExit, "fields are invalid"):
                self.recovery._validate_remote_guard_output(
                    json.dumps(extra),
                    plan,
                    expected_current_version="0.1.1",
                )

    def test_schema_required_fields_match_generated_plan_and_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, _ = self.plan(Path(tmp))
            claim_path, claim = self.claim(Path(tmp), plan)
            receipt = self.recovery._new_receipt(
                plan, plan["plan_hash"], claim_path, claim
            )
            plan_schema = json.loads(PLAN_SCHEMA.read_text(encoding="utf-8"))
            receipt_schema = json.loads(RECEIPT_SCHEMA.read_text(encoding="utf-8"))
            self.assertEqual(set(plan_schema["required"]), set(plan))
            self.assertEqual(set(receipt_schema["required"]), set(receipt))


if __name__ == "__main__":
    unittest.main()
