import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CORE_SCRIPT = ROOT / "scripts" / "uipcodedappdeploy.py"
RECOVERY_SCRIPT = ROOT / "scripts" / "uipcodedappdeploy_recover.py"
LEGACY_PLAN_SCHEMA = ROOT / "references" / "deployment-recovery-plan.v1.schema.json"
LEGACY_RECEIPT_SCHEMA = ROOT / "references" / "deployment-recovery-receipt.v1.schema.json"
PLAN_SCHEMA = ROOT / "references" / "deployment-recovery-plan.v1.3.schema.json"
RECEIPT_SCHEMA = ROOT / "references" / "deployment-recovery-receipt.v1.3.schema.json"


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

    def context(
        self,
        root: Path,
        *,
        current_version: str = "0.1.1",
        candidate_version: str = "0.1.2",
        deploy_version: int = 3,
    ):
        cli = str(root / "uip")
        node = str(root / "node")
        recovery_cli = str(root / "recovery-runtime" / "node_modules" / "@uipath" / "cli" / "dist" / "index.js")
        command = [
            cli,
            "codedapp",
            "deploy",
            "--version",
            candidate_version,
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
            "package_path": (
                f".uipath/aura-vdp-template-mockup.{candidate_version}.nupkg"
            ),
            "package_digest": "sha256:" + "2" * 64,
            "candidate_package_file_digest": "sha256:" + "3" * 64,
            "cli_executable": cli,
            "cli_executable_sha256": "sha256:" + "4" * 64,
            "cli_version": "1.198.0",
            "cli_profile": "fixture-alpha",
            "cli_profile_hash": self.core._hash_json(
                {
                    "name": "fixture-alpha",
                    "environment": "alpha",
                    "control_plane_url": "https://alpha.uipath.com",
                    "org_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                    "tenant_id": "66666666-7777-8888-9999-000000000000",
                }
            ),
            "tags": ["aura-vdp", "internal", "mockup"],
        }
        failed_plan = {
            "project": {"root": str(root), "new_version": candidate_version},
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
            "app_config_file_digest": "sha256:" + "f" * 64,
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
            "source_app_config": str(root / self.core.APP_CONFIG_RELATIVE_PATH),
            "source_app_config_sha256": "sha256:" + "f" * 64,
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
            deploy_version=deploy_version,
            current_version=current_version,
            route_name="aura-vdp-mockup",
        )
        closure_files = [
            {
                "path": str((root / name).resolve()),
                "sha256": "sha256:" + token * 64,
                "size": 1,
                "roles": [f"predecessor.{role}"],
            }
            for name, token, role in (
                ("governed-plan.json", "1", "plan"),
                ("governed-receipt.json", "2", "receipt"),
                ("governed-app-config.json", "3", "app_config"),
            )
        ]
        closure = {
            "algorithm": self.recovery.PREDECESSOR_CLOSURE_ALGORITHM,
            "files": closure_files,
            "file_count": len(closure_files),
            "total_bytes": 3,
        }
        closure["sha256"] = self.core._hash_json(closure)
        predecessor_binding = {
            "type": "governed",
            "trust": {"mode": "validated-core-v2.3"},
            "plan": {
                "kind": self.core.PLAN_KIND,
                "schema_version": self.core.PLAN_SCHEMA_VERSION,
                "plan_hash": "sha256:" + "9" * 64,
                "file_sha256": "sha256:" + "1" * 64,
            },
            "receipt": {
                "kind": self.core.RECEIPT_KIND,
                "schema_version": self.core.RECEIPT_SCHEMA_VERSION,
                "receipt_hash": "sha256:" + "4" * 64,
                "approved_plan_hash": "sha256:" + "9" * 64,
                "status": "succeeded",
                "file_sha256": "sha256:" + "2" * 64,
            },
            "app_config": {
                "path": str((root / "governed-app-config.json").resolve()),
                "sha256": "sha256:" + "3" * 64,
            },
            "closure": closure,
        }
        predecessor_binding["binding_hash"] = self.recovery._binding_hash(
            predecessor_binding
        )
        return {
            "prior_plan": {
                "project": {
                    "root": str(root / "prior"),
                    "new_version": current_version,
                },
                "plan_hash": "sha256:" + "9" * 64,
            },
            "failed_plan": failed_plan,
            "failed_receipt": failed_receipt,
            "deployment": deployment,
            "candidate_system_name": deployment["system_name"],
            "candidate_deploy_version": deploy_version,
            "predecessor_version": current_version,
            "predecessor_binding": predecessor_binding,
            "runtime": runtime,
            "recovery_command": recovery_command,
            "remote_guard_command": self.recovery._remote_guard_command(
                recovery_command
            ),
            "post_upgrade_guard_command": self.recovery._remote_guard_command(
                recovery_command, expected_current_version=candidate_version
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

    def candidate_app_config(self, *, version: str = "0.1.2") -> dict:
        return {
            "appName": "aura-vdp-template-mockup",
            "displayName": "Aura VDP Template Mockup",
            "appType": "Web",
            "appVersion": version,
            "systemName": "ID" + "a" * 32,
            "personalWorkspace": False,
        }

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

    def successful_recovery_predecessor(
        self, root: Path, *, include_deployment_id: bool = False
    ):
        plan, _ = self.plan(root)
        plan.pop("predecessor")
        plan["schema_version"] = self.recovery.LEGACY_RECOVERY_SCHEMA_VERSION
        plan["plan_hash"] = self.core._document_hash(plan, "plan_hash")
        claim_path, claim = self.claim(root, plan)
        config = {
            "appName": plan["existing_deployment"]["package_name"],
            "displayName": plan["existing_deployment"]["app_name"],
            "appType": plan["existing_deployment"]["app_type"],
            "appVersion": plan["candidate"]["version"],
            "systemName": plan["candidate"]["system_name"],
            "appUrl": plan["existing_deployment"]["app_url"],
            "personalWorkspace": False,
            "deployedAt": "2026-08-05T06:10:00Z",
        }
        if include_deployment_id:
            config["deploymentId"] = plan["existing_deployment"]["deployment_id"]
        config_path = root / "prior-recovery-app.config.json"
        config_path.write_text(
            json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        receipt = self.recovery._new_receipt(
            plan, plan["plan_hash"], claim_path, claim
        )
        receipt["status"] = "succeeded"
        receipt["post_deploy_app_config_digest"] = self.core._hash_file(
            config_path, "prior recovery app config"
        )
        receipt["observed_local_app_url"] = plan["existing_deployment"]["app_url"]
        receipt["local_app_url_matches_verified_route"] = True

        def observation(current_version: str):
            return {
                "deploymentId": plan["existing_deployment"]["deployment_id"],
                "systemName": plan["candidate"]["system_name"],
                "deployVersion": plan["candidate"]["deploy_version"],
                "currentVersion": current_version,
                "routeName": plan["existing_deployment"]["route_name"],
                "version": plan["candidate"]["version"],
                "appName": plan["existing_deployment"]["app_name"],
                "appUrl": plan["existing_deployment"]["app_url"],
                "operation": "recovery_verify",
            }

        receipt["pre_upgrade_guard_observation"] = observation(
            plan["upgrade_guard"]["current_version"]
        )
        receipt["post_upgrade_guard_observation"] = observation(
            plan["candidate"]["version"]
        )
        for stage in receipt["stages"]:
            stage.update(
                {
                    "status": "succeeded",
                    "started_at": "2026-08-05T06:01:00Z",
                    "finished_at": "2026-08-05T06:09:00Z",
                }
            )
        receipt["receipt_hash"] = self.core._document_hash(receipt, "receipt_hash")

        plan_path = root / "prior-recovery-plan.json"
        receipt_path = root / "prior-recovery-plan.json.receipt.json"
        plan_path.write_text(
            json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return plan_path, receipt_path, config_path, plan, receipt, config

    def load_fixture_predecessor(self, plan_path: Path, receipt_path: Path):
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        return self.recovery._load_predecessor(
            plan_path,
            receipt_path,
            trusted_recovery_helper_sha256=plan["recovery_helper_sha256"],
            trusted_core_helper_sha256=plan["core_helper_sha256"],
        )

    def historical_runtime_fixture(self, root: Path):
        failed_root = (root / "failed-release").resolve()
        source_cli = failed_root / "node_modules/@uipath/cli/dist/index.js"
        source_tool = failed_root / "node_modules/@uipath/codedapp-tool/dist/tool.js"
        source_tool_manifest = (
            failed_root / "node_modules/@uipath/codedapp-tool/package.json"
        )
        source_config = failed_root / self.core.APP_CONFIG_RELATIVE_PATH
        for path in (source_cli, source_tool, source_tool_manifest, source_config):
            path.parent.mkdir(parents=True, exist_ok=True)

        source_cli.write_text("fixture cli\n", encoding="utf-8")
        source_tool_bytes = (
            "\n/* fixture patch boundary */\n".join(
                source for source, _replacement in self.recovery.PATCH_EDITS
            )
        ).encode("utf-8")
        source_tool.write_bytes(source_tool_bytes)
        tool_manifest = {
            "version": self.recovery.EXPECTED_CODEDAPP_TOOL_VERSION,
            "gitHead": self.recovery.EXPECTED_CODEDAPP_TOOL_GIT_HEAD,
            "main": "./dist/tool.js",
        }
        source_tool_manifest.write_text(
            json.dumps(tool_manifest, sort_keys=True) + "\n", encoding="utf-8"
        )
        source_config.write_text(
            json.dumps(self.candidate_app_config(), sort_keys=True) + "\n",
            encoding="utf-8",
        )

        runtime_root = (root / "guarded-runtime").resolve()
        runtime_cli = runtime_root / "node_modules/@uipath/cli/dist/index.js"
        runtime_tool = runtime_root / "node_modules/@uipath/codedapp-tool/dist/tool.js"
        runtime_tool_manifest = (
            runtime_root / "node_modules/@uipath/codedapp-tool/package.json"
        )
        runtime_workspace = runtime_root / self.recovery.ISOLATED_WORKSPACE_RELATIVE
        runtime_config = runtime_workspace / self.core.APP_CONFIG_RELATIVE_PATH
        for path in (runtime_cli, runtime_tool, runtime_tool_manifest, runtime_config):
            path.parent.mkdir(parents=True, exist_ok=True)
        runtime_cli.write_bytes(source_cli.read_bytes())
        tool_hash = self.core._hash_bytes(source_tool_bytes)
        with mock.patch.object(
            self.recovery, "EXPECTED_CODEDAPP_TOOL_SHA256", tool_hash
        ):
            runtime_tool.write_bytes(
                self.recovery._patched_tool_bytes(source_tool_bytes)
            )
            patch_contract_hash = self.recovery._patch_contract_hash()
        runtime_tool_manifest.write_bytes(source_tool_manifest.read_bytes())
        runtime_config.write_bytes(source_config.read_bytes())

        node = (root / "node").resolve()
        node.write_text("fixture node\n", encoding="utf-8")
        source_config_hash = self.core._hash_file(source_config, "source config")
        original_tree_hash = self.recovery._tree_digest(
            runtime_root, "legacy runtime fixture"
        )
        post_config = {
            **self.candidate_app_config(),
            "appUrl": "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup",
            "deployedAt": "2026-08-05T06:10:00Z",
        }
        runtime_config.write_text(
            json.dumps(post_config, sort_keys=True) + "\n", encoding="utf-8"
        )
        post_config_hash = self.core._hash_file(runtime_config, "post config")

        document = {
            "kind": self.recovery.RUNTIME_MANIFEST_KIND,
            "schema_version": self.recovery.LEGACY_RUNTIME_MANIFEST_SCHEMA_VERSION,
            "created_at": "2026-08-05T06:00:00Z",
            "preparer_sha256": "sha256:" + "1" * 64,
            "patch_algorithm": self.recovery.PATCH_ALGORITHM,
            "patch_contract_sha256": patch_contract_hash,
            "source": {
                "node_modules_root": str(failed_root / "node_modules"),
                "cli_executable": str(source_cli),
                "cli_executable_sha256": self.core._hash_file(
                    source_cli, "source cli"
                ),
                "codedapp_tool_file": str(source_tool),
                "codedapp_tool_file_sha256": tool_hash,
                "codedapp_tool_manifest": str(source_tool_manifest),
                "codedapp_tool_manifest_sha256": self.core._hash_file(
                    source_tool_manifest, "source tool manifest"
                ),
                "codedapp_tool_version": self.recovery.EXPECTED_CODEDAPP_TOOL_VERSION,
                "codedapp_tool_git_head": self.recovery.EXPECTED_CODEDAPP_TOOL_GIT_HEAD,
            },
            "runtime": {
                "root": str(runtime_root),
                "node_modules_root": str(runtime_root / "node_modules"),
                "tree_sha256": original_tree_hash,
                "workspace": str(runtime_workspace),
                "workspace_app_config": str(runtime_config),
                "workspace_app_config_sha256": source_config_hash,
                "self_test": {
                    "node_syntax": "passed",
                    "dynamic_tool_resolution": "passed",
                    "unguarded_deploy": "blocked_before_network",
                    "verify_only_without_guard": "blocked_before_network",
                },
                "node_executable": str(node),
                "node_executable_sha256": self.core._hash_file(node, "node"),
                "node_version": "24.13.0",
                "cli_executable": str(runtime_cli),
                "cli_executable_sha256": self.core._hash_file(
                    runtime_cli, "runtime cli"
                ),
                "codedapp_tool_file": str(runtime_tool),
                "codedapp_tool_file_sha256": self.core._hash_file(
                    runtime_tool, "runtime tool"
                ),
                "codedapp_tool_manifest": str(runtime_tool_manifest),
                "codedapp_tool_manifest_sha256": self.core._hash_file(
                    runtime_tool_manifest, "runtime tool manifest"
                ),
            },
        }
        document["manifest_hash"] = self.core._document_hash(
            document, "manifest_hash"
        )
        failed_plan = {
            "project": {"root": str(failed_root)},
            "parameters": {
                "cli_executable": str(source_cli),
                "cli_executable_sha256": document["source"][
                    "cli_executable_sha256"
                ],
            },
        }
        failed_receipt = {"app_config_file_digest": source_config_hash}
        receipt = {"post_deploy_app_config_digest": post_config_hash}
        return {
            "document": document,
            "failed_plan": failed_plan,
            "failed_receipt": failed_receipt,
            "receipt": receipt,
            "tool_hash": tool_hash,
            "source_config": source_config,
            "runtime_config": runtime_config,
            "runtime_tool_manifest": runtime_tool_manifest,
        }

    def synthetic_runtime_evidence(
        self, root: Path, context: dict, *, candidate_version: str
    ):
        failed_root = Path(context["failed_plan"]["project"]["root"])
        source_cli = failed_root / "node_modules/@uipath/cli/dist/index.js"
        source_tool = failed_root / "node_modules/@uipath/codedapp-tool/dist/tool.js"
        source_tool_manifest = (
            failed_root / "node_modules/@uipath/codedapp-tool/package.json"
        )
        source_config = failed_root / self.core.APP_CONFIG_RELATIVE_PATH
        source_document = self.candidate_app_config(version=candidate_version)
        for path in (source_cli, source_tool, source_tool_manifest, source_config):
            path.parent.mkdir(parents=True, exist_ok=True)
        source_cli.write_text("synthetic pinned cli\n", encoding="utf-8")
        source_tool.write_text("synthetic pinned tool\n", encoding="utf-8")
        source_tool_manifest.write_text(
            json.dumps(
                {
                    "version": self.recovery.EXPECTED_CODEDAPP_TOOL_VERSION,
                    "gitHead": self.recovery.EXPECTED_CODEDAPP_TOOL_GIT_HEAD,
                    "main": "./dist/tool.js",
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        source_config.write_text(
            json.dumps(source_document, sort_keys=True) + "\n", encoding="utf-8"
        )

        runtime_root = (root / "runtime").resolve()
        runtime_cli = runtime_root / "node_modules/@uipath/cli/dist/index.js"
        runtime_tool = runtime_root / "node_modules/@uipath/codedapp-tool/dist/tool.js"
        runtime_tool_manifest = (
            runtime_root / "node_modules/@uipath/codedapp-tool/package.json"
        )
        workspace = runtime_root / self.recovery.ISOLATED_WORKSPACE_RELATIVE
        workspace_config = workspace / self.core.APP_CONFIG_RELATIVE_PATH
        for path in (runtime_cli, runtime_tool, runtime_tool_manifest, workspace_config):
            path.parent.mkdir(parents=True, exist_ok=True)
        runtime_cli.write_bytes(source_cli.read_bytes())
        runtime_tool.write_text("synthetic guarded tool\n", encoding="utf-8")
        runtime_tool_manifest.write_bytes(source_tool_manifest.read_bytes())
        workspace_config.write_bytes(source_config.read_bytes())
        node = (root / "node").resolve()
        node.write_text("synthetic node\n", encoding="utf-8")

        source_config_hash = self.core._hash_file(source_config, "source config")
        tree_hash = self.recovery._tree_digest(runtime_root, "synthetic runtime")
        self_test = {
            "node_syntax": "passed",
            "dynamic_tool_resolution": "passed",
            "unguarded_deploy": "blocked_before_network",
            "verify_only_without_guard": "blocked_before_network",
        }
        runtime_result = {
            "root": str(runtime_root),
            "node_modules_root": str(runtime_root / "node_modules"),
            "tree_sha256": tree_hash,
            "workspace": str(workspace),
            "workspace_app_config": str(workspace_config),
            "workspace_app_config_sha256": source_config_hash,
            "source_app_config": str(source_config),
            "source_app_config_sha256": source_config_hash,
            "self_test": self_test,
            "node_executable": str(node),
            "node_executable_sha256": self.core._hash_file(node, "node"),
            "node_version": "24.13.0",
            "cli_executable": str(runtime_cli),
            "cli_executable_sha256": self.core._hash_file(
                runtime_cli, "runtime cli"
            ),
            "source_tool_file": str(source_tool),
            "source_tool_file_sha256": self.core._hash_file(
                source_tool, "source tool"
            ),
            "source_tool_manifest": str(source_tool_manifest),
            "source_tool_manifest_sha256": self.core._hash_file(
                source_tool_manifest, "source tool manifest"
            ),
            "runtime_tool_file": str(runtime_tool),
            "runtime_tool_file_sha256": self.core._hash_file(
                runtime_tool, "runtime tool"
            ),
            "runtime_tool_manifest": str(runtime_tool_manifest),
            "runtime_tool_manifest_sha256": self.core._hash_file(
                runtime_tool_manifest, "runtime tool manifest"
            ),
            "version": self.recovery.EXPECTED_CODEDAPP_TOOL_VERSION,
            "git_head": self.recovery.EXPECTED_CODEDAPP_TOOL_GIT_HEAD,
            "patch_algorithm": self.recovery.PATCH_ALGORITHM,
            "patch_contract_sha256": self.recovery._patch_contract_hash(),
        }
        leaves = []
        for role, path in (
            ("source_cli", source_cli),
            ("source_tool", source_tool),
            ("source_tool_manifest", source_tool_manifest),
            ("runtime_cli", runtime_cli),
            ("runtime_tool", runtime_tool),
            ("runtime_tool_manifest", runtime_tool_manifest),
            ("node_executable", node),
        ):
            leaves.append(
                {
                    "role": role,
                    "path": str(path),
                    "sha256": self.core._hash_file(path, role),
                }
            )
        manifest = {
            "kind": self.recovery.RUNTIME_MANIFEST_KIND,
            "schema_version": self.recovery.RUNTIME_MANIFEST_SCHEMA_VERSION,
            "leaves": leaves,
            "runtime": copy.deepcopy(runtime_result),
        }
        manifest["manifest_hash"] = self.core._document_hash(
            manifest, "manifest_hash"
        )
        runtime_result["manifest_hash"] = manifest["manifest_hash"]
        manifest["runtime"]["manifest_hash"] = manifest["manifest_hash"]
        manifest_path = (root / "runtime-manifest.json").resolve()
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        parameters = context["failed_plan"]["parameters"]
        parameters["cli_executable"] = str(source_cli)
        parameters["cli_executable_sha256"] = self.core._hash_file(
            source_cli, "failed cli"
        )
        context["runtime"] = runtime_result
        original_command = context["failed_plan"]["stages"][0]["command"]
        original_command[0] = str(source_cli)
        context["recovery_command"] = self.recovery._guarded_upgrade_command(
            original_command,
            node_executable=str(node),
            runtime_cli=str(runtime_cli),
            deployment_id=context["deployment"]["deployment_id"],
            system_name=context["deployment"]["system_name"],
            deploy_version=context["candidate_deploy_version"],
            current_version=context["predecessor_version"],
            route_name=parameters["path_name"],
        )
        context["remote_guard_command"] = self.recovery._remote_guard_command(
            context["recovery_command"]
        )
        context["post_upgrade_guard_command"] = (
            self.recovery._remote_guard_command(
                context["recovery_command"], expected_current_version=candidate_version
            )
        )
        return manifest_path, manifest, runtime_result, source_config, workspace_config

    def synthetic_governed_predecessor(self, root: Path, context: dict):
        parameters = copy.deepcopy(context["failed_plan"]["parameters"])
        plan = {
            "kind": self.core.PLAN_KIND,
            "schema_version": self.core.PLAN_SCHEMA_VERSION,
            "project": {
                "root": str((root / "governed-project").resolve()),
                "new_version": context["predecessor_version"],
            },
            "parameters": parameters,
        }
        plan["plan_hash"] = self.core._document_hash(plan, "plan_hash")
        receipt = {
            "kind": self.core.RECEIPT_KIND,
            "schema_version": self.core.RECEIPT_SCHEMA_VERSION,
            "plan_hash": plan["plan_hash"],
            "approved_plan_hash": plan["plan_hash"],
            "status": "succeeded",
        }
        receipt["receipt_hash"] = self.core._document_hash(
            receipt, "receipt_hash"
        )
        config = {
            **self.candidate_app_config(version=context["predecessor_version"]),
            "deploymentId": context["deployment"]["deployment_id"],
            "appUrl": context["deployment"]["app_url"],
            "deployedAt": "2026-08-05T05:00:00Z",
        }
        plan_path = (root / "governed-plan.json").resolve()
        receipt_path = (root / "governed-receipt.json").resolve()
        config_path = (root / "governed-app-config.json").resolve()
        for path, document in (
            (plan_path, plan),
            (receipt_path, receipt),
            (config_path, config),
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        normalized = self.recovery._normalize_prior_core_plan(plan, receipt)
        block = self.recovery._build_governed_predecessor_binding(
            normalized,
            plan_path=plan_path,
            receipt_path=receipt_path,
            app_config_path=config_path,
        )
        return plan_path, receipt_path, config_path, normalized, block

    def synthetic_failed_attempt(
        self,
        root: Path,
        context: dict,
        *,
        source_config: Path,
    ):
        plan = context["failed_plan"]
        plan["kind"] = self.core.PLAN_KIND
        plan["schema_version"] = self.core.PLAN_SCHEMA_VERSION
        plan["stages"] = [
            {"name": "publish", "effect": "external_write"},
            {"name": "app_config", "effect": "project_write"},
            {
                "name": "deploy",
                "effect": "external_write",
                "command": context["failed_plan"]["stages"][0]["command"],
            },
        ]
        plan["plan_hash"] = self.core._document_hash(plan, "plan_hash")
        receipt = {
            "kind": self.core.RECEIPT_KIND,
            "schema_version": self.core.RECEIPT_SCHEMA_VERSION,
            "approved_plan_hash": plan["plan_hash"],
            "package_file_digest": "sha256:" + "8" * 64,
            "app_config_file_digest": self.core._hash_file(
                source_config, "failed app config"
            ),
            "status": "in_progress",
            "stages": [
                {"name": "publish", "effect": "external_write", "status": "succeeded"},
                {"name": "app_config", "effect": "project_write", "status": "succeeded"},
                {
                    "name": "deploy",
                    "effect": "external_write",
                    "status": "running",
                    "recovery": (
                        "redacted_indeterminate_external_write; reconcile remote state; "
                        "blind resume prohibited"
                    ),
                },
            ],
        }
        receipt["receipt_hash"] = self.core._document_hash(
            receipt, "receipt_hash"
        )
        context["failed_receipt"] = receipt
        plan_path = (root / "failed-plan.json").resolve()
        receipt_path = (root / "failed-receipt.json").resolve()
        plan_path.write_text(
            json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return plan_path, receipt_path

    def synthetic_reconciliation(self, root: Path, context: dict):
        observations = []
        for name in (
            "named profile status",
            "package catalog",
            "OAuth client",
            "published package candidate",
            "pre-recovery live route",
            "deployed app recovery probe",
        ):
            path = (root / "observations" / f"{name.replace(' ', '-')}.json").resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"name": name}) + "\n", encoding="utf-8")
            observations.append(
                {
                    "name": name,
                    "path": str(path),
                    "sha256": self.core._hash_file(path, name),
                }
            )
        document = {
            "kind": self.recovery.RECONCILIATION_KIND,
            "candidate_system_name": context["candidate_system_name"],
            "candidate_deploy_version": context["candidate_deploy_version"],
            "evidence": observations,
        }
        path = (root / "reconciliation.json").resolve()
        path.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path, document

    def synthetic_recovery_artifact(
        self,
        root: Path,
        *,
        context: dict,
        nested_paths: tuple[Path, Path, Path],
        nested_block: dict,
        runtime_path: Path,
        runtime_document: dict,
        workspace_config: Path,
        failed_paths: tuple[Path, Path],
        reconciliation_path: Path,
        schema_version: str,
        home: Path,
    ):
        evidence_paths = (
            *nested_paths,
            *failed_paths,
            reconciliation_path,
            runtime_path,
        )
        evidence = [
            self.recovery._evidence_record(path, label)
            for label, path in zip(self.recovery.EVIDENCE_LABELS, evidence_paths)
        ]
        context["predecessor_binding"] = copy.deepcopy(nested_block)
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
        if schema_version == self.recovery.LEGACY_RECOVERY_SCHEMA_VERSION:
            plan.pop("predecessor")
            plan["schema_version"] = schema_version
        plan["plan_hash"] = self.core._document_hash(plan, "plan_hash")
        plan_path = (root / "recovery-plan.json").resolve()
        plan_path.write_text(
            json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        claim_path, claim = self.recovery._create_execution_claim(
            plan, {"HOME": str(home)}
        )
        post_config = {
            **self.candidate_app_config(version=plan["candidate"]["version"]),
            "deploymentId": plan["existing_deployment"]["deployment_id"],
            "appUrl": plan["existing_deployment"]["app_url"],
            "deployedAt": "2026-08-05T06:10:00Z",
        }
        workspace_config.write_text(
            json.dumps(post_config, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        receipt = self.recovery._new_receipt(
            plan, plan["plan_hash"], claim_path, claim
        )
        receipt["status"] = "succeeded"
        receipt["post_deploy_app_config_digest"] = self.core._hash_file(
            workspace_config, "post recovery config"
        )
        receipt["observed_local_app_url"] = plan["existing_deployment"]["app_url"]
        receipt["local_app_url_matches_verified_route"] = True

        def observation(current_version: str):
            return {
                "deploymentId": plan["existing_deployment"]["deployment_id"],
                "systemName": plan["candidate"]["system_name"],
                "deployVersion": plan["candidate"]["deploy_version"],
                "currentVersion": current_version,
                "routeName": plan["existing_deployment"]["route_name"],
                "version": plan["candidate"]["version"],
                "appName": plan["existing_deployment"]["app_name"],
                "appUrl": plan["existing_deployment"]["app_url"],
                "operation": "recovery_verify",
            }

        receipt["pre_upgrade_guard_observation"] = observation(
            plan["upgrade_guard"]["current_version"]
        )
        receipt["post_upgrade_guard_observation"] = observation(
            plan["candidate"]["version"]
        )
        for stage in receipt["stages"]:
            stage.update(
                {
                    "status": "succeeded",
                    "started_at": "2026-08-05T06:01:00Z",
                    "finished_at": "2026-08-05T06:09:00Z",
                }
            )
        receipt["receipt_hash"] = self.core._document_hash(
            receipt, "receipt_hash"
        )
        receipt_path = (root / "recovery-receipt.json").resolve()
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return {
            "plan_path": plan_path,
            "receipt_path": receipt_path,
            "config_path": workspace_config,
            "plan": plan,
            "receipt": receipt,
            "claim_path": claim_path,
            "runtime_document": runtime_document,
        }

    def validate_synthetic_reconciliation(
        self,
        document: dict,
        *,
        closure_state=None,
        reconciliation_path=None,
        role_prefix="reconciliation",
        **_kwargs,
    ):
        if closure_state is None or reconciliation_path is None:
            self.fail("synthetic recursive reconciliation must bind its closure")
        for observation in document["evidence"]:
            self.recovery._read_bound_json(
                Path(observation["path"]),
                f"synthetic reconciliation {observation['name']}",
                state=closure_state,
                role=f"{role_prefix}.observation.{observation['name']}",
                expected_sha256=observation["sha256"],
            )
        return {
            "candidate_system_name": document["candidate_system_name"],
            "candidate_deploy_version": document["candidate_deploy_version"],
        }

    def validate_synthetic_historical_runtime(
        self,
        document: dict,
        *,
        receipt: dict,
        failed_plan: dict,
        failed_receipt: dict,
        state: dict,
        role_prefix: str,
        **_kwargs,
    ):
        runtime = document["runtime"]
        for leaf in document["leaves"]:
            self.recovery._read_bound_file(
                Path(leaf["path"]),
                f"synthetic historical runtime {leaf['role']}",
                state=state,
                role=f"{role_prefix}.{leaf['role']}",
                expected_sha256=leaf["sha256"],
                capture_payload=False,
            )
        source_config = Path(failed_plan["project"]["root"]) / self.core.APP_CONFIG_RELATIVE_PATH
        self.recovery._read_bound_file(
            source_config,
            "synthetic historical source config",
            state=state,
            role=f"{role_prefix}.source_app_config",
            expected_sha256=failed_receipt["app_config_file_digest"],
        )
        workspace_config = Path(runtime["workspace_app_config"])
        self.recovery._read_bound_file(
            workspace_config,
            "synthetic historical post config",
            state=state,
            role=f"{role_prefix}.post_deploy_app_config",
            expected_sha256=receipt["post_deploy_app_config_digest"],
        )
        return {
            **runtime,
            "workspace_app_config_sha256": receipt[
                "post_deploy_app_config_digest"
            ],
            "source_app_config": str(source_config),
            "source_app_config_sha256": failed_receipt[
                "app_config_file_digest"
            ],
            "manifest_hash": document["manifest_hash"],
        }

    def recursive_recovery_chain_fixture(self, root: Path, home: Path):
        layer_b = (root / "layer-b").resolve()
        context_b = self.context(
            (layer_b / "failed-release").resolve(),
            current_version="0.1.1",
            candidate_version="0.1.2",
            deploy_version=2,
        )
        runtime_b_path, runtime_b, _, source_b, workspace_b = (
            self.synthetic_runtime_evidence(
                layer_b / "runtime-evidence",
                context_b,
                candidate_version="0.1.2",
            )
        )
        governed = self.synthetic_governed_predecessor(
            layer_b / "governed", context_b
        )
        failed_b = self.synthetic_failed_attempt(
            layer_b / "failed-evidence", context_b, source_config=source_b
        )
        reconciliation_b, _ = self.synthetic_reconciliation(
            layer_b / "reconciliation-evidence", context_b
        )
        artifact_b = self.synthetic_recovery_artifact(
            layer_b,
            context=context_b,
            nested_paths=governed[:3],
            nested_block=governed[4],
            runtime_path=runtime_b_path,
            runtime_document=runtime_b,
            workspace_config=workspace_b,
            failed_paths=failed_b,
            reconciliation_path=reconciliation_b,
            schema_version=self.recovery.LEGACY_RECOVERY_SCHEMA_VERSION,
            home=home,
        )
        predecessor_b = self.load_fixture_predecessor(
            artifact_b["plan_path"], artifact_b["receipt_path"]
        )
        block_b = self.recovery._build_recovery_predecessor_binding(
            predecessor_b,
            plan_path=artifact_b["plan_path"],
            receipt_path=artifact_b["receipt_path"],
            app_config_path=artifact_b["config_path"],
        )

        layer_c = (root / "layer-c").resolve()
        context_c = self.context(
            (layer_c / "failed-release").resolve(),
            current_version="0.1.2",
            candidate_version="0.1.3",
            deploy_version=3,
        )
        runtime_c_path, runtime_c, _, source_c, workspace_c = (
            self.synthetic_runtime_evidence(
                layer_c / "runtime-evidence",
                context_c,
                candidate_version="0.1.3",
            )
        )
        failed_c = self.synthetic_failed_attempt(
            layer_c / "failed-evidence", context_c, source_config=source_c
        )
        reconciliation_c, _ = self.synthetic_reconciliation(
            layer_c / "reconciliation-evidence", context_c
        )
        artifact_c = self.synthetic_recovery_artifact(
            layer_c,
            context=context_c,
            nested_paths=(
                artifact_b["plan_path"],
                artifact_b["receipt_path"],
                artifact_b["config_path"],
            ),
            nested_block=block_b,
            runtime_path=runtime_c_path,
            runtime_document=runtime_c,
            workspace_config=workspace_c,
            failed_paths=failed_c,
            reconciliation_path=reconciliation_c,
            schema_version=self.recovery.PLAN_SCHEMA_VERSION,
            home=home,
        )
        predecessor_c = self.load_fixture_predecessor(
            artifact_c["plan_path"], artifact_c["receipt_path"]
        )
        block_c = self.recovery._build_recovery_predecessor_binding(
            predecessor_c,
            plan_path=artifact_c["plan_path"],
            receipt_path=artifact_c["receipt_path"],
            app_config_path=artifact_c["config_path"],
        )
        return {
            "governed": governed,
            "layer_b": artifact_b,
            "block_b": block_b,
            "layer_c": artifact_c,
            "predecessor_c": predecessor_c,
            "block_c": block_c,
            "runtime_b": runtime_b,
            "runtime_c": runtime_c,
        }

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

    def test_successful_recovery_is_a_valid_predecessor_at_candidate_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path, receipt_path, config_path, plan, _, config = (
                self.successful_recovery_predecessor(root)
            )
            predecessor = self.load_fixture_predecessor(plan_path, receipt_path)
            self.assertEqual(predecessor["kind"], "recovery_v1.2")
            self.assertEqual(predecessor["version"], plan["candidate"]["version"])
            self.assertNotEqual(
                predecessor["version"],
                plan["existing_deployment"]["deployed_version"],
            )
            deployment = self.recovery._validate_predecessor_app_config(
                config_path, config, predecessor
            )
            self.assertNotIn("deploymentId", config)
            self.assertEqual(
                deployment["deployment_id"],
                plan["existing_deployment"]["deployment_id"],
            )

    def test_recovery_predecessor_requires_both_exact_trust_anchors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path, receipt_path, _, plan, _, _ = (
                self.successful_recovery_predecessor(root)
            )
            for helper_hash, core_hash in (
                (None, None),
                (plan["recovery_helper_sha256"], None),
                (None, plan["core_helper_sha256"]),
                ("sha256:" + "0" * 64, plan["core_helper_sha256"]),
                (plan["recovery_helper_sha256"], "sha256:" + "0" * 64),
            ):
                with self.subTest(helper_hash=helper_hash, core_hash=core_hash):
                    with mock.patch.object(subprocess, "run") as run, mock.patch.object(
                        self.core, "_run"
                    ) as core_run:
                        with self.assertRaises(SystemExit):
                            self.recovery._load_predecessor(
                                plan_path,
                                receipt_path,
                                trusted_recovery_helper_sha256=helper_hash,
                                trusted_core_helper_sha256=core_hash,
                            )
                    run.assert_not_called()
                    core_run.assert_not_called()

    def test_active_plan_validation_rejects_legacy_recovery_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path, _, _, plan, _, _ = self.successful_recovery_predecessor(
                Path(tmp)
            )
            self.assertEqual(
                plan["schema_version"], self.recovery.LEGACY_RECOVERY_SCHEMA_VERSION
            )
            with self.assertRaises(SystemExit):
                self.recovery._validate_plan(
                    json.loads(plan_path.read_text(encoding="utf-8"))
                )

    def test_closure_rejects_symlink_and_hard_link_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            original = root / "original.json"
            original.write_text('{"value":1}\n', encoding="utf-8")
            state = self.recovery._new_closure_state()
            self.recovery._read_bound_file(
                original, "original", state=state, role="one"
            )
            hard_link = root / "hard-link.json"
            hard_link.hardlink_to(original)
            with self.assertRaisesRegex(SystemExit, "hard-link"):
                self.recovery._read_bound_file(
                    hard_link, "hard link", state=state, role="two"
                )
            symlink = root / "symlink.json"
            symlink.symlink_to(original)
            with self.assertRaisesRegex(SystemExit, "symlink"):
                self.recovery._read_bound_file(
                    symlink,
                    "symlink",
                    state=self.recovery._new_closure_state(),
                    role="three",
                )

            prelinked = root / "prelinked.json"
            prelinked.write_text('{"value":2}\n', encoding="utf-8")
            (root / "prelinked-alias.json").hardlink_to(prelinked)
            with self.assertRaisesRegex(SystemExit, "hard-link aliases"):
                self.recovery._read_bound_file(
                    prelinked,
                    "prelinked",
                    state=self.recovery._new_closure_state(),
                    role="four",
                )

    def test_historical_tree_digest_permits_only_bound_config_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runtime"
            config = root / "workspace" / ".uipath" / "app.config.json"
            other = root / "tool.js"
            config.parent.mkdir(parents=True)
            config.write_text('{"version":"before"}\n', encoding="utf-8")
            other.write_text("tool\n", encoding="utf-8")
            source_stat = config.stat()
            source_hash = self.core._hash_file(config, "source config")
            original_tree = self.recovery._tree_digest(root, "fixture runtime")
            config.write_text('{"version":"after"}\n', encoding="utf-8")
            reconstructed = self.recovery._tree_digest_with_substitution(
                root,
                substitute_path=config,
                substitute_mode=source_stat.st_mode & 0o777,
                substitute_size=source_stat.st_size,
                substitute_sha256=source_hash,
                label="fixture runtime",
            )
            self.assertEqual(reconstructed, original_tree)
            other.write_text("drift\n", encoding="utf-8")
            self.assertNotEqual(
                self.recovery._tree_digest_with_substitution(
                    root,
                    substitute_path=config,
                    substitute_mode=source_stat.st_mode & 0o777,
                    substitute_size=source_stat.st_size,
                    substitute_sha256=source_hash,
                    label="fixture runtime",
                ),
                original_tree,
            )

    def test_legacy_runtime_1_1_is_valid_only_for_a_1_2_predecessor(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.historical_runtime_fixture(Path(tmp).resolve())
            with mock.patch.object(
                self.recovery,
                "EXPECTED_CODEDAPP_TOOL_SHA256",
                fixture["tool_hash"],
            ), mock.patch.object(self.recovery.subprocess, "run") as run, mock.patch.object(
                self.core, "_run"
            ) as core_run:
                result = self.recovery._validate_historical_runtime_manifest(
                    fixture["document"],
                    predecessor_plan_schema=self.recovery.LEGACY_RECOVERY_SCHEMA_VERSION,
                    trusted_preparer_sha256=fixture["document"]["preparer_sha256"],
                    receipt=fixture["receipt"],
                    failed_plan=fixture["failed_plan"],
                    failed_receipt=fixture["failed_receipt"],
                    state=self.recovery._new_closure_state(),
                    role_prefix="fixture.runtime",
                )
                self.assertEqual(
                    result["source_app_config"], str(fixture["source_config"])
                )
                self.assertEqual(
                    result["workspace_app_config"], str(fixture["runtime_config"])
                )
                with self.assertRaisesRegex(SystemExit, "schema-1.2"):
                    self.recovery._validate_historical_runtime_manifest(
                        fixture["document"],
                        predecessor_plan_schema=self.recovery.PLAN_SCHEMA_VERSION,
                        trusted_preparer_sha256=fixture["document"][
                            "preparer_sha256"
                        ],
                        receipt=fixture["receipt"],
                        failed_plan=fixture["failed_plan"],
                        failed_receipt=fixture["failed_receipt"],
                        state=self.recovery._new_closure_state(),
                        role_prefix="fixture.runtime",
                    )
            run.assert_not_called()
            core_run.assert_not_called()

    def test_legacy_runtime_1_1_rejects_mixed_shape_and_runtime_drift_offline(self):
        cases = ("mixed_source_shape", "source_config_drift", "runtime_drift")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                fixture = self.historical_runtime_fixture(Path(tmp).resolve())
                document = copy.deepcopy(fixture["document"])
                if case == "mixed_source_shape":
                    document["source"]["app_config_source"] = str(
                        fixture["source_config"]
                    )
                    document["source"]["app_config_source_sha256"] = fixture[
                        "failed_receipt"
                    ]["app_config_file_digest"]
                    document["manifest_hash"] = self.core._document_hash(
                        document, "manifest_hash"
                    )
                    expected = "source fields"
                elif case == "source_config_drift":
                    fixture["source_config"].write_text(
                        '{"drifted":true}\n', encoding="utf-8"
                    )
                    expected = "bound hash"
                else:
                    fixture["runtime_tool_manifest"].write_text(
                        '{"drifted":true}\n', encoding="utf-8"
                    )
                    expected = "bound hash"
                with mock.patch.object(
                    self.recovery,
                    "EXPECTED_CODEDAPP_TOOL_SHA256",
                    fixture["tool_hash"],
                ), mock.patch.object(
                    self.recovery.subprocess, "run"
                ) as run, mock.patch.object(self.core, "_run") as core_run:
                    with self.assertRaisesRegex(SystemExit, expected):
                        self.recovery._validate_historical_runtime_manifest(
                            document,
                            predecessor_plan_schema=(
                                self.recovery.LEGACY_RECOVERY_SCHEMA_VERSION
                            ),
                            trusted_preparer_sha256=document["preparer_sha256"],
                            receipt=fixture["receipt"],
                            failed_plan=fixture["failed_plan"],
                            failed_receipt=fixture["failed_receipt"],
                            state=self.recovery._new_closure_state(),
                            role_prefix="fixture.runtime",
                        )
                run.assert_not_called()
                core_run.assert_not_called()

    def test_prior_recovery_rejects_plan_receipt_and_claim_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)

            first = base / "plan"
            first.mkdir()
            plan_path, receipt_path, _, plan, _, _ = (
                self.successful_recovery_predecessor(first)
            )
            tampered_plan = copy.deepcopy(plan)
            tampered_plan["candidate"]["version"] = "9.9.9"
            plan_path.write_text(json.dumps(tampered_plan), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "plan hash"):
                self.load_fixture_predecessor(plan_path, receipt_path)

            second = base / "receipt"
            second.mkdir()
            plan_path, receipt_path, _, _, receipt, _ = (
                self.successful_recovery_predecessor(second)
            )
            tampered_receipt = copy.deepcopy(receipt)
            tampered_receipt["post_upgrade_guard_observation"]["currentVersion"] = "9.9.9"
            tampered_receipt["receipt_hash"] = self.core._document_hash(
                tampered_receipt, "receipt_hash"
            )
            receipt_path.write_text(json.dumps(tampered_receipt), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "post-upgrade guard"):
                self.load_fixture_predecessor(plan_path, receipt_path)

            third = base / "claim"
            third.mkdir()
            plan_path, receipt_path, _, _, receipt, _ = (
                self.successful_recovery_predecessor(third)
            )
            Path(receipt["execution_claim_path"]).write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "claim bytes changed"):
                self.load_fixture_predecessor(plan_path, receipt_path)

    def test_prior_recovery_rejects_failed_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path, receipt_path, _, _, receipt, _ = (
                self.successful_recovery_predecessor(root)
            )
            receipt["status"] = "failed"
            receipt["receipt_hash"] = self.core._document_hash(receipt, "receipt_hash")
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "must be succeeded"):
                self.load_fixture_predecessor(plan_path, receipt_path)

    def test_prior_recovery_app_config_is_digest_and_metadata_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            digest_root = base / "digest"
            digest_root.mkdir()
            plan_path, receipt_path, config_path, _, _, config = (
                self.successful_recovery_predecessor(digest_root)
            )
            predecessor = self.load_fixture_predecessor(plan_path, receipt_path)
            config["displayName"] = "tampered"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "post-deploy digest"):
                self.recovery._validate_predecessor_app_config(
                    config_path, config, predecessor
                )

            mutations = {
                "route": ("appUrl", "https://agenticgtm.alpha.uipath.host/wrong"),
                "deployment": ("deploymentId", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                "version": ("appVersion", "9.9.9"),
            }
            for label, (field, value) in mutations.items():
                with self.subTest(label=label):
                    root = base / label
                    root.mkdir()
                    plan_path, receipt_path, config_path, _, receipt, config = (
                        self.successful_recovery_predecessor(
                            root, include_deployment_id=True
                        )
                    )
                    config[field] = value
                    config_path.write_text(
                        json.dumps(config, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    receipt["post_deploy_app_config_digest"] = self.core._hash_file(
                        config_path, "mutated prior app config"
                    )
                    receipt["receipt_hash"] = self.core._document_hash(
                        receipt, "receipt_hash"
                    )
                    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
                    predecessor = self.load_fixture_predecessor(plan_path, receipt_path)
                    with self.assertRaisesRegex(SystemExit, field):
                        self.recovery._validate_predecessor_app_config(
                            config_path, config, predecessor
                        )

    def test_prior_recovery_app_config_requires_deployed_at(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path, receipt_path, config_path, _, receipt, config = (
                self.successful_recovery_predecessor(root)
            )
            config.pop("deployedAt")
            config_path.write_text(json.dumps(config), encoding="utf-8")
            receipt["post_deploy_app_config_digest"] = self.core._hash_file(
                config_path, "prior app config without deployedAt"
            )
            receipt["receipt_hash"] = self.core._document_hash(receipt, "receipt_hash")
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            predecessor = self.load_fixture_predecessor(plan_path, receipt_path)
            with self.assertRaisesRegex(SystemExit, "deployedAt"):
                self.recovery._validate_predecessor_app_config(
                    config_path, config, predecessor
                )

    def test_cross_release_tag_drift_is_safe_but_identity_drift_is_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            prior_root = base / "prior"
            prior_root.mkdir()
            plan_path, receipt_path, _, _, _, _ = (
                self.successful_recovery_predecessor(prior_root)
            )
            predecessor = self.load_fixture_predecessor(plan_path, receipt_path)
            failed_plan = self.context(base / "current")["failed_plan"]
            failed_plan["project"]["new_version"] = "0.1.3"
            failed_plan["parameters"]["tags"] = ["alpha4", "browser-local"]
            self.recovery._validate_predecessor_release_binding(
                predecessor, failed_plan
            )
            self.assertEqual(
                failed_plan["parameters"]["tags"], ["alpha4", "browser-local"]
            )

            drifted = copy.deepcopy(failed_plan)
            drifted["parameters"]["folder_key"] = (
                "aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb"
            )
            with self.assertRaisesRegex(SystemExit, "folder_key"):
                self.recovery._validate_predecessor_release_binding(
                    predecessor, drifted
                )

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
        # Schema 1.2 is frozen predecessor-only input, not an active contract.
        self.assertEqual(
            self.core._hash_file(LEGACY_PLAN_SCHEMA, "legacy plan schema"),
            "sha256:d4dba708270aab97ec671cc8696ce5c1b2109c53a92be429201cb8725674cdb0",
        )
        self.assertEqual(
            self.core._hash_file(LEGACY_RECEIPT_SCHEMA, "legacy receipt schema"),
            "sha256:dac1e7712819f6ea3dbeb93c4f108ccdb3a1d4bb441aa73b24e931377921d9fe",
        )
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
        self.assertEqual(
            json.loads(LEGACY_PLAN_SCHEMA.read_text(encoding="utf-8"))[
                "properties"
            ]["schema_version"]["const"],
            "1.2",
        )
        self.assertEqual(
            json.loads(LEGACY_RECEIPT_SCHEMA.read_text(encoding="utf-8"))[
                "properties"
            ]["schema_version"]["const"],
            "1.2",
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

    def test_runtime_preparation_binds_explicit_candidate_app_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cli_root = base / "cli-source"
            failed_root = base / "failed-release"
            runtime_root = base / "evidence" / "guarded-runtime"
            manifest_path = base / "evidence" / "guarded-runtime.manifest.json"
            cli = cli_root / "node_modules/@uipath/cli/dist/index.js"
            tool = cli_root / "node_modules/@uipath/codedapp-tool/dist/tool.js"
            tool_manifest = cli_root / "node_modules/@uipath/codedapp-tool/package.json"
            app_config = failed_root / self.core.APP_CONFIG_RELATIVE_PATH
            node = base / "toolchain/node"
            for path in (cli, tool, tool_manifest, app_config, node):
                path.parent.mkdir(parents=True, exist_ok=True)
            cli.write_bytes(b"pinned-cli")
            tool.write_bytes(b"approved-tool")
            tool_manifest.write_text(
                json.dumps(
                    {
                        "version": self.recovery.EXPECTED_CODEDAPP_TOOL_VERSION,
                        "gitHead": self.recovery.EXPECTED_CODEDAPP_TOOL_GIT_HEAD,
                        "main": "./dist/tool.js",
                    }
                ),
                encoding="utf-8",
            )
            app_config.write_text(
                json.dumps(self.candidate_app_config(), sort_keys=True) + "\n",
                encoding="utf-8",
            )
            node.write_bytes(b"node")
            node.chmod(0o755)
            expected_self_test = {
                "node_syntax": "passed",
                "dynamic_tool_resolution": "passed",
                "unguarded_deploy": "blocked_before_network",
                "verify_only_without_guard": "blocked_before_network",
            }
            node_runtime = {
                "executable": str(node.resolve()),
                "executable_sha256": self.core._hash_file(node, "node"),
                "version": "24.13.0",
            }

            with mock.patch.object(
                self.recovery,
                "_recovery_environment",
                return_value={"HOME": str(base), "PATH": "/usr/bin:/bin"},
            ), mock.patch.object(
                self.recovery, "_resolve_node_runtime", return_value=node_runtime
            ), mock.patch.object(
                self.recovery, "_patched_tool_bytes", return_value=b"patched-tool"
            ), mock.patch.object(
                self.recovery, "_self_test_runtime", return_value=expected_self_test
            ):
                manifest = self.recovery._prepare_runtime(
                    cli,
                    node,
                    app_config,
                    runtime_root,
                    manifest_path,
                )

            source_digest = self.core._hash_file(app_config, "candidate app config")
            self.assertEqual(manifest["schema_version"], "1.2")
            self.assertEqual(
                manifest["source"]["app_config_source"], str(app_config.resolve())
            )
            self.assertEqual(
                manifest["source"]["app_config_source_sha256"], source_digest
            )
            self.assertEqual(
                manifest["runtime"]["workspace_app_config_sha256"], source_digest
            )
            runtime_config = (
                runtime_root
                / self.recovery.ISOLATED_WORKSPACE_RELATIVE
                / self.core.APP_CONFIG_RELATIVE_PATH
            )
            self.assertEqual(runtime_config.read_bytes(), app_config.read_bytes())
            self.assertEqual(
                json.loads(manifest_path.read_text(encoding="utf-8")), manifest
            )

    def test_runtime_preparation_requires_explicit_app_config_source(self):
        with self.assertRaisesRegex(SystemExit, "runtime-app-config-source"):
            self.recovery.main(
                [
                    "--prepare-runtime-from-cli",
                    "/source/node_modules/@uipath/cli/dist/index.js",
                    "--node-executable",
                    "/toolchain/node",
                    "--runtime-output",
                    "/evidence/runtime",
                    "--runtime-manifest-output",
                    "/evidence/runtime.manifest.json",
                ]
            )

    def test_runtime_app_config_binding_rejects_other_worktree_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            failed_root = base / "failed-release"
            other_root = base / "prior-release"
            context = self.context(failed_root)
            failed_config = failed_root / self.core.APP_CONFIG_RELATIVE_PATH
            other_config = other_root / self.core.APP_CONFIG_RELATIVE_PATH
            workspace_config = (
                base
                / "guarded-runtime"
                / self.recovery.ISOLATED_WORKSPACE_RELATIVE
                / self.core.APP_CONFIG_RELATIVE_PATH
            )
            payload = json.dumps(self.candidate_app_config(), sort_keys=True) + "\n"
            for path in (failed_config, other_config, workspace_config):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(payload, encoding="utf-8")
            digest = self.core._hash_file(other_config, "other app config")
            runtime = copy.deepcopy(context["runtime"])
            runtime.update(
                {
                    "source_app_config": str(other_config),
                    "source_app_config_sha256": digest,
                    "workspace_app_config": str(workspace_config),
                    "workspace_app_config_sha256": digest,
                }
            )
            context["failed_receipt"]["app_config_file_digest"] = digest

            with self.assertRaisesRegex(
                SystemExit, "does not match the failed project config"
            ):
                self.recovery._validate_runtime_app_config_binding(
                    runtime,
                    failed_plan=context["failed_plan"],
                    failed_receipt=context["failed_receipt"],
                    deployment=context["deployment"],
                )

    def test_runtime_app_config_binding_rejects_non_candidate_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            failed_root = base / "failed-release"
            context = self.context(failed_root)
            failed_config = failed_root / self.core.APP_CONFIG_RELATIVE_PATH
            workspace_config = (
                base
                / "guarded-runtime"
                / self.recovery.ISOLATED_WORKSPACE_RELATIVE
                / self.core.APP_CONFIG_RELATIVE_PATH
            )
            payload = (
                json.dumps(
                    self.candidate_app_config(version="0.1.1"), sort_keys=True
                )
                + "\n"
            )
            for path in (failed_config, workspace_config):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(payload, encoding="utf-8")
            digest = self.core._hash_file(failed_config, "failed app config")
            runtime = copy.deepcopy(context["runtime"])
            runtime.update(
                {
                    "source_app_config": str(failed_config),
                    "source_app_config_sha256": digest,
                    "workspace_app_config": str(workspace_config),
                    "workspace_app_config_sha256": digest,
                }
            )
            context["failed_receipt"]["app_config_file_digest"] = digest

            with self.assertRaisesRegex(
                SystemExit, "appVersion is not exactly bound to the candidate"
            ):
                self.recovery._validate_runtime_app_config_binding(
                    runtime,
                    failed_plan=context["failed_plan"],
                    failed_receipt=context["failed_receipt"],
                    deployment=context["deployment"],
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
            ), mock.patch.object(
                self.recovery, "_load_bound_evidence", return_value=context
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
            try:
                from jsonschema import Draft202012Validator
            except ImportError:
                self.skipTest("jsonschema is installed by requirements-dev.txt")
            Draft202012Validator.check_schema(plan_schema)
            Draft202012Validator.check_schema(receipt_schema)
            Draft202012Validator(plan_schema).validate(plan)
            Draft202012Validator(receipt_schema).validate(receipt)


if __name__ == "__main__":
    unittest.main()
