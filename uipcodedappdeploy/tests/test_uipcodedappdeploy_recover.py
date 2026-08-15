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

    def governed_predecessor(self):
        return {
            "kind": "governed",
            "depth": 0,
            "trust_anchors": [],
            "chain": [],
            "evidence_closure": [],
            "evidence_closure_sha256": self.core._hash_json([]),
            "runtime_reconstruction": None,
        }

    def context(self, root: Path, predecessor: dict | None = None):
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
            "predecessor": predecessor or self.governed_predecessor(),
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

    def plan(self, root: Path, predecessor: dict | None = None):
        context = self.context(root, predecessor)
        labels = self.recovery.EVIDENCE_LABELS_BY_KIND[
            context["predecessor"]["kind"]
        ]
        evidence = [
            {
                "label": label,
                "path": f"/evidence/{label}.json",
                "sha256": "sha256:" + hex(index + 1)[2:] * 64,
            }
            for index, label in enumerate(labels)
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
        plan["predecessor_binding_hash"] = self.core._hash_json(plan["predecessor"])
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
            plan_schema["properties"]["schema_version"]["const"], "1.3"
        )
        self.assertEqual(
            receipt_schema["properties"]["schema_version"]["const"], "1.3"
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


class ChainedRecoveryPredecessorTests(unittest.TestCase):
    """Contract 1.3 chained recovery: schema 1.2 as historical evidence only."""

    @classmethod
    def setUpClass(cls):
        cls.core, cls.recovery = load_modules()

    def pre_config_bytes(self) -> bytes:
        return json.dumps({"appVersion": "0.1.0"}, sort_keys=True).encode("utf-8")

    def post_config_bytes(self) -> bytes:
        return json.dumps({"appVersion": "0.1.1"}, sort_keys=True).encode("utf-8")

    def write_json(self, path: Path, document: dict) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, sort_keys=True) + "\n", encoding="utf-8")
        path.chmod(0o644)
        return path

    def build(self, base: Path, **overrides):
        """Materialize a complete, valid predecessor recovery on disk."""

        runtime_root = base / "runtime"
        workspace = runtime_root / self.recovery.ISOLATED_WORKSPACE_RELATIVE
        config_path = workspace / self.core.APP_CONFIG_RELATIVE_PATH
        (runtime_root / "node_modules").mkdir(parents=True)
        marker = runtime_root / "node_modules" / "marker.js"
        marker.write_bytes(b"// guarded runtime\n")
        marker.chmod(0o644)
        config_path.parent.mkdir(parents=True)

        # The manifest is created against the pre-upgrade workspace state.
        config_path.write_bytes(self.pre_config_bytes())
        config_path.chmod(0o644)
        pre_digest = self.core._hash_bytes(self.pre_config_bytes())
        tree_sha256 = self.recovery._tree_digest(runtime_root, "fixture runtime")

        manifest = {
            "kind": self.recovery.RUNTIME_MANIFEST_KIND,
            "schema_version": self.recovery.RUNTIME_MANIFEST_SCHEMA_VERSION,
            "patch_algorithm": self.recovery.PATCH_ALGORITHM,
            "runtime": {
                "root": str(runtime_root),
                "workspace": str(workspace),
                "workspace_app_config": str(config_path),
                "workspace_app_config_sha256": pre_digest,
                "tree_sha256": overrides.get("tree_sha256", tree_sha256),
                "self_test": {
                    "node_syntax": "passed",
                    "dynamic_tool_resolution": "passed",
                    "unguarded_deploy": "blocked_before_network",
                    "verify_only_without_guard": "blocked_before_network",
                },
            },
        }
        manifest["manifest_hash"] = self.core._document_hash(manifest, "manifest_hash")
        manifest_path = self.write_json(base / "predecessor-runtime.manifest.json", manifest)

        # Retain the pre-upgrade bytes outside the runtime, then apply the one
        # mutation a succeeded recovery is allowed to have made.
        retained_config = base / "retained-pre-upgrade-app.config.json"
        retained_config.write_bytes(self.pre_config_bytes())
        retained_config.chmod(0o644)
        config_path.write_bytes(
            overrides.get("post_config_bytes", self.post_config_bytes())
        )
        config_path.chmod(overrides.get("post_config_mode", 0o644))
        post_digest = self.core._hash_bytes(self.post_config_bytes())

        # The predecessor's own evidence set: seven records, the first of which
        # is a governed plan and therefore terminates the recursion.
        nested = {
            "prior_successful_plan": {"kind": self.core.PLAN_KIND, "note": "governed"},
            "prior_successful_receipt": {"kind": self.core.RECEIPT_KIND},
            "prior_successful_app_config": {"appVersion": "0.1.0"},
            "failed_plan": {"kind": self.core.PLAN_KIND, "note": "failed"},
            "failed_receipt": {"kind": self.core.RECEIPT_KIND, "note": "failed"},
            "reconciliation_evidence": {"kind": self.recovery.RECONCILIATION_KIND},
            "recovery_runtime_manifest": {"kind": self.recovery.RUNTIME_MANIFEST_KIND},
        }
        evidence = []
        nested_paths = {}
        for label in self.recovery.GOVERNED_EVIDENCE_LABELS:
            path = self.write_json(base / "nested" / f"{label}.json", nested[label])
            nested_paths[label] = path
            evidence.append(
                {
                    "label": label,
                    "path": str(path),
                    "sha256": self.core._hash_file(path, label),
                }
            )

        helper_anchor = overrides.get("plan_helper_hash", "sha256:" + "a" * 64)
        core_anchor = overrides.get("plan_core_hash", "sha256:" + "b" * 64)
        plan = {
            "kind": self.recovery.PLAN_KIND,
            "schema_version": overrides.get("plan_schema_version", "1.2"),
            "created_at": "2026-07-01T00:00:00Z",
            "recovery_helper_sha256": helper_anchor,
            "core_helper_sha256": core_anchor,
            "core_helper_path": "/absolute/uipcodedappdeploy.py",
            "project_root": str(base / "predecessor-release"),
            "evidence": evidence,
            "evidence_binding_hash": self.core._hash_json(evidence),
            "target": {
                "environment": "alpha",
                "control_plane_url": "https://alpha.uipath.com",
                "organization_name": "agenticgtm",
                "organization_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "tenant_name": "Dev",
                "tenant_id": "66666666-7777-8888-9999-000000000000",
                "folder_key": "99999999-8888-7777-6666-555555555555",
                "client_id": "11111111-2222-3333-4444-555555555555",
            },
            "existing_deployment": {
                "app_name": "Aura VDP Template Mockup",
                "package_name": "aura-vdp-template-mockup",
                "app_type": "Web",
                "route_name": "aura-vdp-mockup",
                "deployment_id": "12345678-1234-1234-1234-123456789abc",
            },
            "candidate": {
                "version": "0.1.1",
                "tags": ["aura-vdp", "internal", "mockup"],
                "source_cli_executable_sha256": "sha256:" + "4" * 64,
                "cli_version": "1.198.0",
                "cli_profile": "fixture-alpha",
                "cli_profile_hash": "sha256:" + "5" * 64,
            },
            "upgrade_guard": {
                "fresh_deploy_prohibited": overrides.get("fresh_deploy_prohibited", True),
                "routing_name_omitted_from_patch": True,
            },
            "execution": {
                "resume_supported": overrides.get("resume_supported", False),
                "publishes_package": False,
                "changes_route": False,
            },
        }
        plan["plan_hash"] = self.core._document_hash(plan, "plan_hash")
        plan_path = self.write_json(base / "predecessor-plan.json", plan)

        claim = {
            "kind": "uipcodedappdeploy.upgrade-recovery-execution-claim",
            "schema_version": "1.0",
            "plan_hash": overrides.get("claim_plan_hash", plan["plan_hash"]),
        }
        claim["claim_hash"] = self.core._document_hash(claim, "claim_hash")
        claim_path = self.write_json(base / "retained-claim.json", claim)

        receipt = {
            "kind": self.recovery.RECEIPT_KIND,
            "schema_version": plan["schema_version"],
            "plan_hash": plan["plan_hash"],
            "approved_plan_hash": plan["plan_hash"],
            "status": overrides.get("status", "succeeded"),
            "local_app_url_matches_verified_route": overrides.get(
                "route_verified", True
            ),
            "post_deploy_app_config_digest": post_digest,
            "post_upgrade_guard_observation": {
                "operation": "recovery_verify",
                "currentVersion": overrides.get("observed_version", "0.1.1"),
            },
            "execution_claim_path": str(claim_path),
            "execution_claim_sha256": self.core._hash_file(claim_path, "claim"),
            "execution_claim_hash": claim["claim_hash"],
            "execution_claim_released": overrides.get("claim_released", False),
            "stages": [
                {
                    "name": name,
                    "status": overrides.get("stage_status", {}).get(name, "succeeded"),
                }
                for name in self.recovery.PREDECESSOR_RECEIPT_STAGES
            ],
        }
        receipt["receipt_hash"] = self.core._document_hash(receipt, "receipt_hash")
        receipt_path = self.write_json(base / "predecessor-receipt.json", receipt)

        return {
            "paths": {
                "prior_successful_plan": plan_path,
                "prior_successful_receipt": receipt_path,
                "predecessor_runtime_manifest": manifest_path,
                "predecessor_pre_upgrade_workspace_config": retained_config,
            },
            "anchors": [
                {
                    "recovery_helper_sha256": "sha256:" + "a" * 64,
                    "core_helper_sha256": "sha256:" + "b" * 64,
                }
            ],
            "runtime_root": runtime_root,
            "config_path": config_path,
            "plan": plan,
            "receipt": receipt,
            "receipt_path": receipt_path,
            "claim_path": claim_path,
            "nested_paths": nested_paths,
            "post_digest": post_digest,
            "pre_digest": pre_digest,
            "tree_sha256": tree_sha256,
        }

    def validate(self, fixture, **kwargs):
        return self.recovery._validate_predecessor(
            kind=kwargs.get("kind", "recovery"),
            anchors=kwargs.get("anchors", fixture["anchors"]),
            paths=fixture["paths"],
        )

    def assert_fails_before_subprocess(self, fixture, message, **kwargs):
        """Every predecessor gate must reject before any process is spawned."""

        with mock.patch.object(self.recovery.subprocess, "run") as run:
            with self.assertRaisesRegex(SystemExit, message):
                self.validate(fixture, **kwargs)
        run.assert_not_called()

    # -- happy path -----------------------------------------------------

    def test_valid_chained_predecessor_binds_closure_and_reconstruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build(Path(tmp))
            with mock.patch.object(self.recovery.subprocess, "run") as run:
                result = self.validate(fixture)
            run.assert_not_called()
            block = result["block"]
            self.assertEqual(block["kind"], "recovery")
            self.assertEqual(block["depth"], 1)
            self.assertEqual(block["trust_anchors"], fixture["anchors"])
            self.assertEqual(len(block["chain"]), 1)
            self.assertEqual(block["chain"][0]["status"], "succeeded")
            self.assertEqual(block["chain"][0]["schema_version"], "1.2")
            self.assertEqual(
                block["chain"][0]["plan_hash"], fixture["plan"]["plan_hash"]
            )
            # Raw-byte closure over every evidence file the predecessor bound.
            self.assertEqual(
                len(block["evidence_closure"]),
                len(self.recovery.GOVERNED_EVIDENCE_LABELS),
            )
            self.assertTrue(
                all(record["depth"] == 1 for record in block["evidence_closure"])
            )
            self.assertEqual(
                block["evidence_closure_sha256"],
                self.core._hash_json(block["evidence_closure"]),
            )
            reconstruction = block["runtime_reconstruction"]
            self.assertEqual(reconstruction["permitted_mutation"], "workspace_app_config")
            self.assertEqual(
                reconstruction["approved_tree_sha256"], fixture["tree_sha256"]
            )
            self.assertEqual(
                reconstruction["pre_upgrade_workspace_app_config_sha256"],
                fixture["pre_digest"],
            )
            self.assertEqual(
                reconstruction["post_success_workspace_app_config_sha256"],
                fixture["post_digest"],
            )

    def test_recovery_predecessor_normalizes_onto_the_governed_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build(Path(tmp))
            result = self.validate(fixture)
            prior = result["prior_plan"]
            self.assertEqual(prior["project"]["new_version"], "0.1.1")
            self.assertEqual(prior["plan_hash"], fixture["plan"]["plan_hash"])
            self.assertEqual(prior["parameters"]["path_name"], "aura-vdp-mockup")
            self.assertEqual(prior["parameters"]["org_id"], fixture["plan"]["target"]["organization_id"])
            self.assertEqual(prior["parameters"]["cli_version"], "1.198.0")
            self.assertEqual(result["prior_receipt"]["status"], "succeeded")
            # Every immutable field the cross-validator compares must exist.
            for field in (
                "environment", "control_plane_url", "tenant_name", "tenant_id",
                "org_id", "org_name", "folder_key", "package_name", "app_name",
                "app_type", "path_name", "client_id", "tags",
                "cli_executable_sha256", "cli_version", "cli_profile",
                "cli_profile_hash",
            ):
                self.assertIn(field, prior["parameters"])

    # -- trust anchors --------------------------------------------------

    def test_trust_anchor_mismatch_fails_before_any_subprocess(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build(Path(tmp))
            self.assert_fails_before_subprocess(
                fixture,
                "not bound to a trusted",
                anchors=[
                    {
                        "recovery_helper_sha256": "sha256:" + "c" * 64,
                        "core_helper_sha256": "sha256:" + "d" * 64,
                    }
                ],
            )

    def test_missing_or_unpaired_trust_anchors_are_rejected(self):
        with self.assertRaisesRegex(SystemExit, "at least one"):
            self.recovery._validate_trust_anchors([], [])
        with self.assertRaisesRegex(SystemExit, "exactly one matching"):
            self.recovery._validate_trust_anchors(["sha256:" + "a" * 64], [])
        with self.assertRaisesRegex(SystemExit, "must be unique"):
            self.recovery._validate_trust_anchors(
                ["sha256:" + "a" * 64] * 2, ["sha256:" + "b" * 64] * 2
            )
        with self.assertRaisesRegex(SystemExit, "sha256"):
            self.recovery._validate_trust_anchors(["not-a-hash"], ["sha256:" + "b" * 64])

    def test_governed_predecessor_rejects_trust_anchors(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build(Path(tmp))
            with self.assertRaisesRegex(SystemExit, "only to a recovery predecessor"):
                self.validate(fixture, kind="governed")

    # -- predecessor state gates ----------------------------------------

    def test_incomplete_and_deployed_unverified_predecessors_fail_closed(self):
        for status in self.recovery.PREDECESSOR_REJECTED_STATUSES:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                fixture = self.build(Path(tmp), status=status)
                self.assert_fails_before_subprocess(
                    fixture, f"is {status}; a chained recovery"
                )

    def test_unfinished_stage_breaks_the_eight_stage_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build(
                Path(tmp), stage_status={"post_upgrade_guard": "failed"}
            )
            self.assert_fails_before_subprocess(
                fixture, "stage post_upgrade_guard did not succeed"
            )

    def test_unverified_route_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build(Path(tmp), route_verified=False)
            self.assert_fails_before_subprocess(fixture, "did not verify its retained route")

    def test_post_upgrade_observation_must_prove_its_own_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build(Path(tmp), observed_version="0.1.0")
            self.assert_fails_before_subprocess(
                fixture, "did not verify its own candidate version"
            )

    def test_predecessor_must_preserve_the_fail_closed_invariants(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build(Path(tmp), fresh_deploy_prohibited=False)
            self.assert_fails_before_subprocess(
                fixture, "did not preserve the fail-closed upgrade invariants"
            )
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build(Path(tmp), resume_supported=True)
            self.assert_fails_before_subprocess(
                fixture, "no-publish, no-resume, no-route-change"
            )

    # -- retained claim -------------------------------------------------

    def test_released_claim_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build(Path(tmp), claim_released=True)
            self.assert_fails_before_subprocess(fixture, "released its execution claim")

    def test_missing_retained_claim_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build(Path(tmp))
            fixture["claim_path"].unlink()
            self.assert_fails_before_subprocess(fixture, "not a regular file")

    def test_retained_claim_must_be_plan_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build(Path(tmp), claim_plan_hash="sha256:" + "e" * 64)
            self.assert_fails_before_subprocess(fixture, "not plan-bound")

    # -- evidence closure -----------------------------------------------

    def test_missing_predecessor_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build(Path(tmp))
            fixture["nested_paths"]["reconciliation_evidence"].unlink()
            self.assert_fails_before_subprocess(fixture, "not a regular file")

    def test_predecessor_evidence_byte_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build(Path(tmp))
            fixture["nested_paths"]["failed_receipt"].write_text(
                '{"tampered":true}\n', encoding="utf-8"
            )
            self.assert_fails_before_subprocess(fixture, "changed after plan approval")

    def test_predecessor_plan_tampering_invalidates_its_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build(Path(tmp))
            tampered = copy.deepcopy(fixture["plan"])
            tampered["existing_deployment"]["route_name"] = "other-route"
            self.write_json(fixture["paths"]["prior_successful_plan"], tampered)
            self.assert_fails_before_subprocess(fixture, "hash is invalid")

    def test_unrecognized_nested_prior_plan_kind_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build(Path(tmp))
            path = fixture["nested_paths"]["prior_successful_plan"]
            self.write_json(path, {"kind": "something.else"})
            # Rebind the plan so only the nested kind is wrong.
            fixture = self.rebind(fixture)
            self.assert_fails_before_subprocess(
                fixture, "unrecognized prior plan kind"
            )

    def rebind(self, fixture):
        """Recompute the predecessor evidence binding after editing a file."""

        plan = copy.deepcopy(fixture["plan"])
        for record in plan["evidence"]:
            record["sha256"] = self.core._hash_file(Path(record["path"]), record["label"])
        plan["evidence_binding_hash"] = self.core._hash_json(plan["evidence"])
        plan.pop("plan_hash")
        plan["plan_hash"] = self.core._document_hash(plan, "plan_hash")
        self.write_json(fixture["paths"]["prior_successful_plan"], plan)

        receipt = copy.deepcopy(fixture["receipt"])
        claim = json.loads(fixture["claim_path"].read_text(encoding="utf-8"))
        claim["plan_hash"] = plan["plan_hash"]
        claim.pop("claim_hash")
        claim["claim_hash"] = self.core._document_hash(claim, "claim_hash")
        self.write_json(fixture["claim_path"], claim)
        receipt["plan_hash"] = plan["plan_hash"]
        receipt["approved_plan_hash"] = plan["plan_hash"]
        receipt["execution_claim_hash"] = claim["claim_hash"]
        receipt["execution_claim_sha256"] = self.core._hash_file(
            fixture["claim_path"], "claim"
        )
        receipt.pop("receipt_hash")
        receipt["receipt_hash"] = self.core._document_hash(receipt, "receipt_hash")
        self.write_json(fixture["receipt_path"], receipt)
        fixture["plan"] = plan
        fixture["receipt"] = receipt
        return fixture

    # -- runtime reconstruction -----------------------------------------

    def test_only_the_expected_workspace_config_mutation_is_permitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build(Path(tmp))
            drifted = fixture["runtime_root"] / "node_modules" / "marker.js"
            drifted.write_bytes(b"// tampered\n")
            self.assert_fails_before_subprocess(
                fixture, "drifted beyond the single permitted"
            )

    def test_unexpected_workspace_config_content_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build(Path(tmp))
            fixture["config_path"].write_bytes(b'{"appVersion":"9.9.9"}')
            self.assert_fails_before_subprocess(
                fixture, "not the exact post-success state"
            )

    def test_unmutated_workspace_config_is_not_a_succeeded_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build(Path(tmp))
            fixture["config_path"].write_bytes(self.pre_config_bytes())
            self.assert_fails_before_subprocess(
                fixture, "not the exact post-success state"
            )

    def test_workspace_config_mode_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build(Path(tmp), post_config_mode=0o600)
            self.assert_fails_before_subprocess(fixture, "config mode drifted")

    def test_pre_upgrade_bytes_must_match_the_manifest_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build(Path(tmp))
            fixture["paths"]["predecessor_pre_upgrade_workspace_config"].write_bytes(
                b'{"appVersion":"0.0.9"}'
            )
            self.assert_fails_before_subprocess(
                fixture, "do not match the approved runtime manifest digest"
            )

    def test_runtime_manifest_hash_tampering_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build(Path(tmp))
            path = fixture["paths"]["predecessor_runtime_manifest"]
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["runtime"]["tree_sha256"] = "sha256:" + "f" * 64
            self.write_json(path, manifest)
            self.assert_fails_before_subprocess(fixture, "manifest hash is invalid")

    def test_runtime_self_test_evidence_must_be_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.build(Path(tmp))
            path = fixture["paths"]["predecessor_runtime_manifest"]
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["runtime"]["self_test"]["unguarded_deploy"] = "passed"
            manifest.pop("manifest_hash")
            manifest["manifest_hash"] = self.core._document_hash(
                manifest, "manifest_hash"
            )
            self.write_json(path, manifest)
            self.assert_fails_before_subprocess(fixture, "self-test evidence is invalid")

    # -- ordering: the predecessor gate precedes every outward call -----

    def test_predecessor_gate_runs_before_any_network_capable_validation(self):
        """A broken chain must abort before the runtime/CLI validation path.

        `_cross_validate_v23_evidence` reaches `_validate_runtime_manifest`,
        which resolves and executes Node. Ordering is the security property, so
        assert that stage is never entered when the predecessor is untrusted.
        """

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            fixture = self.build(base)
            filler = {
                label: self.write_json(base / "active" / f"{label}.json", {"label": label})
                for label in (
                    "prior_successful_app_config",
                    "failed_plan",
                    "failed_receipt",
                    "reconciliation_evidence",
                    "recovery_runtime_manifest",
                )
            }
            paths = {**fixture["paths"], **filler}
            evidence = [
                {
                    "label": label,
                    "path": str(paths[label]),
                    "sha256": self.core._hash_file(paths[label], label),
                }
                for label in self.recovery.RECOVERY_PREDECESSOR_EVIDENCE_LABELS
            ]
            untrusted = [
                {
                    "recovery_helper_sha256": "sha256:" + "c" * 64,
                    "core_helper_sha256": "sha256:" + "d" * 64,
                }
            ]
            with mock.patch.object(
                self.recovery, "_cross_validate_v23_evidence"
            ) as cross, mock.patch.object(
                self.recovery, "_validate_runtime_manifest"
            ) as runtime, mock.patch.object(
                self.recovery, "_resolve_node_runtime"
            ) as node, mock.patch.object(
                self.recovery.subprocess, "run"
            ) as run, mock.patch.object(
                self.core, "_load_plan"
            ) as load_plan:
                with self.assertRaisesRegex(SystemExit, "not bound to a trusted"):
                    self.recovery._load_bound_evidence(
                        evidence, kind="recovery", anchors=untrusted
                    )
            cross.assert_not_called()
            runtime.assert_not_called()
            node.assert_not_called()
            run.assert_not_called()
            load_plan.assert_not_called()

    # -- active contract boundary ---------------------------------------

    def test_schema_1_2_is_never_accepted_as_an_active_plan(self):
        superseded = {
            "kind": self.recovery.PLAN_KIND,
            "schema_version": self.recovery.PREDECESSOR_PLAN_SCHEMA_VERSION,
        }
        with self.assertRaisesRegex(SystemExit, "superseded contract"):
            self.recovery._validate_plan(superseded)

    def test_active_contract_versions_are_1_3(self):
        self.assertEqual(self.recovery.PLAN_SCHEMA_VERSION, "1.3")
        self.assertEqual(self.recovery.RECEIPT_SCHEMA_VERSION, "1.3")
        self.assertEqual(self.recovery.PREDECESSOR_PLAN_SCHEMA_VERSION, "1.2")
        self.assertNotEqual(
            self.recovery.PLAN_SCHEMA_VERSION,
            self.recovery.PREDECESSOR_PLAN_SCHEMA_VERSION,
        )

    def test_historical_validator_rejects_unknown_contract_versions(self):
        with self.assertRaisesRegex(SystemExit, "not an accepted historical"):
            self.recovery._validate_historical_predecessor_plan(
                {
                    "kind": self.recovery.PLAN_KIND,
                    "schema_version": "1.1",
                },
                anchors=[],
                depth=1,
            )

    def test_evidence_layout_is_kind_specific(self):
        self.assertEqual(len(self.recovery.GOVERNED_EVIDENCE_LABELS), 7)
        self.assertEqual(len(self.recovery.RECOVERY_PREDECESSOR_EVIDENCE_LABELS), 9)
        self.assertEqual(
            set(self.recovery.RECOVERY_PREDECESSOR_EVIDENCE_LABELS)
            - set(self.recovery.GOVERNED_EVIDENCE_LABELS),
            {
                "predecessor_runtime_manifest",
                "predecessor_pre_upgrade_workspace_config",
            },
        )
        with self.assertRaisesRegex(SystemExit, "evidence set is incomplete"):
            self.recovery._load_bound_evidence([], kind="recovery", anchors=[])


if __name__ == "__main__":
    unittest.main()
