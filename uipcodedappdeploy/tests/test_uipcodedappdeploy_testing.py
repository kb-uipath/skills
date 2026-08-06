import contextlib
import copy
import concurrent.futures
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
CORE_SCRIPT = ROOT / "scripts" / "uipcodedappdeploy.py"
RECOVERY_SCRIPT = ROOT / "scripts" / "uipcodedappdeploy_recover.py"
TESTING_SCRIPT = ROOT / "scripts" / "uipcodedappdeploy_testing.py"
RECEIPT_SCHEMA = ROOT / "references" / "deployment-testing-receipt.v1.schema.json"
TESTING_POLICY = ROOT / "references" / "testing-only-policy.md"

ORG_ID = "83a60daf-a85e-4834-8980-2aaa3f6ac2e0"
TENANT_ID = "5d2f728f-9b74-45cc-bdce-e1b2818dbcf8"
FOLDER_ID = "99999999-8888-7777-6666-555555555555"
CLIENT_ID = "11111111-2222-3333-4444-555555555555"
DEPLOYMENT_ID = "4d27d32b-06a2-4599-abc0-add36d900bdf"
SYSTEM_NAME = "IDe01ca22e102b4a33bbfadf0970bea626"
SOURCE_SHA = "52e9a69c9ea0f4aa0398fd3e80856f2dc517333f"


def load_modules():
    core_spec = importlib.util.spec_from_file_location("uipcodedappdeploy", CORE_SCRIPT)
    core = importlib.util.module_from_spec(core_spec)
    assert core_spec.loader is not None
    sys.modules[core_spec.name] = core
    core_spec.loader.exec_module(core)

    recovery_spec = importlib.util.spec_from_file_location(
        "uipcodedappdeploy_recover", RECOVERY_SCRIPT
    )
    recovery = importlib.util.module_from_spec(recovery_spec)
    assert recovery_spec.loader is not None
    sys.modules[recovery_spec.name] = recovery
    recovery_spec.loader.exec_module(recovery)

    testing_spec = importlib.util.spec_from_file_location(
        "uipcodedappdeploy_testing_module", TESTING_SCRIPT
    )
    testing = importlib.util.module_from_spec(testing_spec)
    assert testing_spec.loader is not None
    sys.modules[testing_spec.name] = testing
    testing_spec.loader.exec_module(testing)
    return core, recovery, testing


def all_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from all_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from all_keys(nested)


class UiPathCodedAppDeployTestingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core, cls.recovery, cls.testing = load_modules()

    def executable(self, root: Path) -> Path:
        cli = root / "node_modules" / "@uipath" / "cli" / "dist" / "index.js"
        cli.parent.mkdir(parents=True, exist_ok=True)
        cli.write_bytes(b"pinned-uip-cli-1.198.0\n")
        cli.chmod(0o755)
        (cli.parents[1] / "package.json").write_text(
            json.dumps(
                {
                    "version": "1.198.0",
                    "gitHead": self.testing.EXPECTED_CLI_GIT_HEAD,
                    "main": "./dist/index.js",
                    "exports": {
                        ".": {
                            "browser": "./dist/index.browser.js",
                            "default": "./dist/index.js",
                        },
                        "./browser": "./dist/index.browser.js",
                    },
                    "bin": {"uip": "./dist/index.js"},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return cli.resolve()

    def target(self, cli: Path, *, environment: str = "alpha") -> dict:
        control_plane = {
            "alpha": "https://alpha.uipath.com",
            "staging": "https://staging.uipath.com",
        }[environment]
        profile = f"fixture-{environment}"
        return {
            "environment": environment,
            "control_plane_url": control_plane,
            "organization_name": "agenticgtm" if environment == "alpha" else "tam_global",
            "organization_id": ORG_ID,
            "tenant_name": "Dev",
            "tenant_id": TENANT_ID,
            "folder_key": FOLDER_ID,
            "client_id": CLIENT_ID,
            "cli_profile": profile,
            "cli_profile_hash": self.core._hash_json(
                {
                    "name": profile,
                    "environment": environment,
                    "control_plane_url": control_plane,
                    "org_id": ORG_ID,
                    "tenant_id": TENANT_ID,
                }
            ),
            "cli_executable": str(cli),
            "cli_executable_sha256": self.core._hash_file(cli, "fixture CLI"),
            "cli_version": "1.198.0",
        }

    def candidate(self, *, mode: str = "reconciled", intent: str = "upgrade") -> dict:
        is_upgrade = intent == "upgrade"
        return {
            "mode": mode,
            "intent": intent,
            "package_name": "aura-vdp-template-mockup",
            "app_name": "Aura VDP Template Mockup",
            "version": "0.1.2",
            "path_name": "aura-vdp-mockup",
            "tags": ["aura-vdp", "internal", "mockup"],
            "git_head": SOURCE_SHA,
            "git_status_digest": self.core._hash_bytes(b" M package.json\0"),
            "source_sha": SOURCE_SHA,
            "dist_digest": self.core._hash_bytes(b"dist") if mode == "dist" else None,
            "uipath_config_digest": self.core._hash_bytes(b"uipath-config"),
            "package_content_digest": self.core._hash_bytes(b"package-content"),
            "package_file_digest": self.core._hash_bytes(b"package-file"),
            "recovery_plan_hash": self.core._hash_bytes(b"recovery-plan")
            if mode == "reconciled"
            else None,
            "deployment_id": DEPLOYMENT_ID if is_upgrade else None,
            "system_name": SYSTEM_NAME if is_upgrade else None,
            "deploy_version": (3 if mode == "reconciled" else 4) if is_upgrade else None,
            "current_version": "0.1.1" if is_upgrade else None,
            "runtime_manifest_hash": self.core._hash_bytes(b"runtime"),
            "node_executable": "/usr/local/bin/node",
            "node_executable_sha256": self.testing.SUPPORTED_NODE_RUNTIMES["24.13.0"],
            "node_version": "24.13.0",
            "runtime_app_config_digest": self.core._hash_bytes(b"runtime-app-config"),
            "runtime_immutable_digest": self.core._hash_bytes(
                b"runtime-immutable"
            ),
            "helper_sha256": self.core._hash_file(
                TESTING_SCRIPT,
                "testing helper fixture",
            ),
            "main_file": "index.html",
            "content_type": "webapp",
        }

    def args(self, cli: Path, root: Path, **overrides):
        values = {
            "testing_only": True,
            "execute": True,
            "intent": "upgrade",
            "candidate_mode": "reconciled",
            "environment": "alpha",
            "control_plane_url": "https://alpha.uipath.com",
            "org_id": ORG_ID,
            "org_name": "agenticgtm",
            "tenant_id": TENANT_ID,
            "tenant_name": "Dev",
            "folder_key": FOLDER_ID,
            "package_name": "aura-vdp-template-mockup",
            "app_name": "Aura VDP Template Mockup",
            "path_name": "aura-vdp-mockup",
            "client_id": CLIENT_ID,
            "version": "0.1.2",
            "tags": "aura-vdp,internal,mockup",
            "cli_executable": str(cli),
            "cli_version": "1.198.0",
            "cli_profile": "fixture-alpha",
            "node_executable": "/usr/local/bin/node",
            "node_version": "24.13.0",
            "testing_purpose": "Synthetic browser mockup acceptance",
            "receipt_output": str(root / "testing-receipt.json"),
            "project_root": str((root / "source").resolve()),
            "app_dist": None,
            "main_file": None,
            "content_type": None,
            "author": None,
            "recovery_plan": str(root / "recovery-plan.json"),
            "recovery_runtime_manifest": None,
            "expected_recovery_plan_hash": None,
            "expected_deployment_id": DEPLOYMENT_ID,
            "expected_system_name": SYSTEM_NAME,
            "expected_current_version": "0.1.1",
            "expected_deploy_version": 3,
            "expected_runtime_manifest_hash": self.core._hash_bytes(b"runtime"),
            "verify_timeout": 15,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def recovery_plan(self, cli: Path, root: Path) -> tuple[dict, dict]:
        target = self.target(cli)
        runtime_root = root / "recovery-runtime"
        runtime_root.mkdir(exist_ok=True)
        (runtime_root / "guarded-runtime.js").write_text(
            "// immutable runtime fixture\n", encoding="utf-8"
        )
        recovery_workspace = runtime_root / "workspace"
        recovery_workspace.mkdir(exist_ok=True)
        recovery_app_config = recovery_workspace / self.core.APP_CONFIG_RELATIVE_PATH
        recovery_app_config.parent.mkdir(parents=True, exist_ok=True)
        recovery_app_config.write_text(
            json.dumps(
                {
                    "appName": "aura-vdp-template-mockup",
                    "displayName": "Aura VDP Template Mockup",
                    "appVersion": "0.1.2",
                    "appType": "Web",
                    "personalWorkspace": False,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        runtime_manifest = root / "runtime.manifest.json"
        runtime_manifest.write_text("{}\n", encoding="utf-8")
        recovery_claim_key = self.core._hash_json(
            {
                "scope": "home_scoped_exact_candidate_v1",
                "environment": target["environment"],
                "organization_id": target["organization_id"],
                "tenant_id": target["tenant_id"],
                "folder_key": target["folder_key"],
                "deployment_id": DEPLOYMENT_ID,
                "system_name": SYSTEM_NAME,
                "deploy_version": 3,
                "candidate_version": "0.1.2",
            }
        )
        plan = {
            "project_root": str((root / "source").resolve()),
            "target": {
                key: target[key]
                for key in (
                    "environment",
                    "control_plane_url",
                    "organization_name",
                    "organization_id",
                    "tenant_name",
                    "tenant_id",
                    "folder_key",
                    "client_id",
                )
            },
            "existing_deployment": {
                "app_name": "Aura VDP Template Mockup",
                "package_name": "aura-vdp-template-mockup",
                "deployment_id": DEPLOYMENT_ID,
                "route_name": "aura-vdp-mockup",
                "deployed_version": "0.1.1",
                "app_url": "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup",
            },
            "candidate": {
                "version": "0.1.2",
                "system_name": SYSTEM_NAME,
                "deploy_version": 3,
                "package_path": "candidate.nupkg",
                "package_content_digest": self.core._hash_bytes(b"package-content"),
                "package_file_digest": self.core._hash_bytes(b"package-file"),
                "source_cli_executable": str(cli),
                "source_cli_executable_sha256": target["cli_executable_sha256"],
                "cli_version": "1.198.0",
                "cli_profile": "fixture-alpha",
                "cli_profile_hash": target["cli_profile_hash"],
                "recovery_runtime_manifest_hash": self.core._hash_bytes(b"runtime"),
                "recovery_runtime_root": str(runtime_root.resolve()),
                "recovery_node_executable": "/usr/local/bin/node",
                "recovery_node_executable_sha256": self.testing.SUPPORTED_NODE_RUNTIMES[
                    "24.13.0"
                ],
                "recovery_node_version": "24.13.0",
                "recovery_workspace_app_config_sha256": self.core._hash_file(
                    recovery_app_config, "fixture recovery app config"
                ),
                "recovery_workspace": str(recovery_workspace.resolve()),
                "tags": ["aura-vdp", "internal", "mockup"],
            },
            "upgrade_guard": {
                "current_version": "0.1.1",
                "local_execution_claim_key": recovery_claim_key,
            },
            "stages": [
                {},
                {},
                {"name": "remote_pre_guard", "command": ["guard-before"]},
                {},
                {
                    "name": "upgrade",
                    "command": ["guarded-runtime", "codedapp", "deploy"],
                    "cwd": str(recovery_workspace.resolve()),
                },
                {"name": "remote_post_guard", "command": ["guard-after"]},
            ],
        }
        plan["plan_hash"] = self.core._document_hash(plan, "plan_hash")
        return plan, {
            "runtime_manifest": {},
            "paths": {
                "recovery_runtime_manifest": runtime_manifest.resolve(),
            },
            "failed_plan": {
                "parameters": {
                    "main_file": "index.html",
                    "content_type": "webapp",
                }
            },
        }

    def claim_and_receipt(self, root: Path, cli: Path):
        home = root / "home"
        (home / ".uipath").mkdir(parents=True)
        target = self.target(cli)
        candidate = self.candidate()
        environment = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
        claim_path, claim = self.testing._create_claim(target, candidate, environment)
        args = self.args(cli, root)
        reservation = self.testing._reserve_receipt(root / "testing-receipt.json")
        stages = self.testing._stages(
            self.testing.RECONCILED_STAGE_CONTRACT,
            set(),
        )
        receipt = self.testing._new_receipt(
            args, target, candidate, claim_path, claim, reservation, stages
        )
        receipt_path = root / "testing-receipt.json"
        with mock.patch.object(
            self.testing, "EXPECTED_CLI_SHA256", target["cli_executable_sha256"]
        ):
            self.testing._write_receipt(receipt_path, receipt)
        return environment, claim_path, claim, receipt_path, receipt

    def observation(self, *, current_version: str) -> dict:
        return {
            "deploymentId": DEPLOYMENT_ID,
            "systemName": SYSTEM_NAME,
            "deployVersion": 3,
            "currentVersion": current_version,
            "routeName": "aura-vdp-mockup",
            "version": "0.1.2",
            "appName": "Aura VDP Template Mockup",
            "appUrl": "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup",
            "operation": "recovery_verify",
        }

    def run_reconciled(
        self,
        root: Path,
        *,
        pre_guard_effect=None,
        runtime_effect=None,
        immutable_effect=None,
        deploy_effect=None,
        post_guard_effect=None,
        route_effect=None,
        config_effect=None,
    ):
        cli = self.executable(root)
        source = root / "source"
        source.mkdir()
        (source / "uipath.json").write_text(
            json.dumps(
                {
                    "clientId": CLIENT_ID,
                    "scope": "openid profile",
                    "baseUrl": "https://alpha.api.uipath.com",
                    "redirectUri": "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup",
                    "public": False,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        workspace = root / "recovery-workspace"
        home = root / "home"
        (home / ".uipath").mkdir(parents=True)
        environment = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
        target = self.target(cli)
        plan, context = self.recovery_plan(cli, root)
        args = self.args(
            cli,
            root,
            recovery_runtime_manifest=str(
                context["paths"]["recovery_runtime_manifest"]
            ),
            expected_recovery_plan_hash=plan["plan_hash"],
            expected_runtime_manifest_hash=plan["candidate"][
                "recovery_runtime_manifest_hash"
            ],
        )
        Path(args.recovery_plan).write_text("{}\n", encoding="utf-8")
        reservation = self.testing._reserve_receipt(root / "testing-receipt.json")
        guard_before = self.observation(current_version="0.1.1")
        guard_after = self.observation(current_version="0.1.2")
        pre_guard = pre_guard_effect if pre_guard_effect is not None else guard_before
        post_guard = post_guard_effect if post_guard_effect is not None else guard_after
        with mock.patch.object(
            self.testing.recovery, "_load_plan", return_value=(plan, context)
        ), mock.patch.object(
            self.testing, "_git_state", return_value=(SOURCE_SHA, self.core._hash_bytes(b"dirty"), SOURCE_SHA)
        ), mock.patch.object(
            self.testing.recovery, "_preflight"
        ), mock.patch.object(
            self.testing, "_audit_tracked_source"
        ), mock.patch.object(
            self.testing, "_resolve_reconciled_package"
        ), mock.patch.object(
            self.testing.recovery,
            "_run_remote_guard",
            side_effect=[pre_guard, post_guard]
            if not isinstance(pre_guard, BaseException)
            else pre_guard,
        ) as remote_guard, mock.patch.object(
            self.testing,
            "_revalidate_reconciled_testing_barrier",
            side_effect=runtime_effect,
        ), mock.patch.object(
            self.testing,
            "_revalidate_reconciled_immutable_runtime",
            side_effect=immutable_effect,
        ), mock.patch.object(
            self.testing, "_run_write", side_effect=deploy_effect
        ) as deploy, mock.patch.object(
            self.testing.core, "_verify_url", side_effect=route_effect
        ) as verify, mock.patch.object(
            self.testing.recovery,
            "_inspect_post_deploy_config",
            side_effect=config_effect,
        ) as inspect:
            with mock.patch.object(
                self.testing,
                "EXPECTED_CLI_SHA256",
                target["cli_executable_sha256"],
            ):
                try:
                    receipt_path = self.testing._reconciled_upgrade(
                        args,
                        target,
                        cli,
                        environment,
                        root / "testing-receipt.json",
                        reservation,
                    )
                    error = None
                except BaseException as exc:  # assertions inspect preserved evidence
                    receipt_path = root / "testing-receipt.json"
                    error = exc
        if not receipt_path.is_file():
            raise AssertionError(
                f"reconciled fixture failed before receipt creation: {error!r}"
            ) from error
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        claim_path = Path(receipt["execution_claim"]["path"])
        return receipt, claim_path, error, remote_guard, deploy, verify, inspect

    def publish_recovery_fixture(self, root: Path):
        cli = self.executable(root)
        target = self.target(cli)
        home = root / "home"
        (home / ".uipath").mkdir(parents=True)
        environment = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
        failed_path = root / "failed-testing-receipt.json"
        workspace = self.testing._workspace_for(failed_path)
        dist = workspace / "dist"
        dist.mkdir(parents=True)
        (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")
        config = workspace / "uipath.json"
        config.write_text(
            json.dumps(
                {
                    "clientId": CLIENT_ID,
                    "scope": "openid profile",
                    "baseUrl": "https://alpha.api.uipath.com",
                    "redirectUri": "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup",
                    "public": False,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        package = workspace / ".uipath" / "aura-vdp-template-mockup.0.1.2.nupkg"
        package.parent.mkdir()
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("content/index.html", "<!doctype html>")
            archive.writestr(
                "aura-vdp-template-mockup.nuspec",
                "<package><metadata><id>aura-vdp-template-mockup</id><version>0.1.2</version></metadata></package>",
            )
        runtime_root = workspace / "create-guard-runtime"
        runtime_workspace = runtime_root / "workspace"
        runtime_config = runtime_workspace / self.core.APP_CONFIG_RELATIVE_PATH
        runtime_config.parent.mkdir(parents=True)
        runtime_config.write_text(
            json.dumps(
                {
                    "appName": "aura-vdp-template-mockup",
                    "displayName": "Aura VDP Template Mockup",
                    "appVersion": "0.1.2",
                    "appUrl": "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup",
                    "appType": "Web",
                    "personalWorkspace": False,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        candidate = self.candidate(mode="dist", intent="upgrade")
        source_helper_sha256 = self.core._hash_bytes(
            b"distinct-schema-1.1-source-helper"
        )
        candidate["helper_sha256"] = source_helper_sha256
        candidate["runtime_app_config_digest"] = self.core._hash_file(
            runtime_config,
            "retained guard config",
        )
        candidate["dist_digest"] = self.testing._directory_digest(dist)
        candidate["uipath_config_digest"] = self.core._hash_file(config, "config")
        candidate["package_content_digest"] = self.core._hash_bytes(
            b"fixture-package-content"
        )
        candidate["package_file_digest"] = self.core._hash_file(
            package, "fixture package"
        )
        manifest = {
            "kind": self.testing.CREATE_GUARD_RUNTIME_KIND,
            "schema_version": self.testing.CREATE_GUARD_RUNTIME_VERSION,
            "created_at": "2026-08-06T03:26:00Z",
            "helper_sha256": candidate["helper_sha256"],
            "patch_algorithm": self.testing.CREATE_GUARD_PATCH_ALGORITHM,
            "patch_contract_sha256": self.testing._create_guard_patch_hash(),
            "source_cli": str(cli),
            "source_cli_sha256": target["cli_executable_sha256"],
            "source_cli_manifest": str(cli.parents[1] / "package.json"),
            "source_cli_manifest_sha256": self.core._hash_file(cli.parents[1] / "package.json", "manifest"),
            "source_tool": str(root / "source-tool.js"),
            "source_tool_sha256": self.core._hash_bytes(b"source-tool"),
            "source_tool_manifest": str(root / "source-tool-package.json"),
            "source_tool_manifest_sha256": self.core._hash_bytes(b"source-tool-package"),
            "runtime_cli": str(cli),
            "runtime_root": str(runtime_root),
            "runtime_cli_sha256": target["cli_executable_sha256"],
            "runtime_cli_manifest": str(cli.parents[1] / "package.json"),
            "runtime_cli_manifest_sha256": self.core._hash_file(cli.parents[1] / "package.json", "manifest"),
            "runtime_tool": str(root / "runtime-tool.js"),
            "runtime_tool_sha256": self.core._hash_bytes(b"runtime-tool"),
            "runtime_tool_manifest": str(root / "runtime-tool-package.json"),
            "runtime_tool_manifest_sha256": self.core._hash_bytes(b"runtime-tool-package"),
            "runtime_workspace": str(runtime_workspace),
            "runtime_app_config_sha256": self.core._hash_bytes(b"pre-publish-config"),
            "node_executable": candidate["node_executable"],
            "node_executable_sha256": candidate["node_executable_sha256"],
            "node_version": candidate["node_version"],
            "runtime_tree_sha256": self.core._hash_bytes(b"runtime-tree"),
            "runtime_immutable_sha256": candidate["runtime_immutable_digest"],
            "self_test": {"node_syntax": "passed", "ordinary_deploy": "blocked_before_network"},
        }
        manifest["manifest_hash"] = self.core._document_hash(manifest, "manifest_hash")
        candidate["runtime_manifest_hash"] = manifest["manifest_hash"]
        manifest_path = workspace / "create-guard-runtime.manifest.json"
        self.core._atomic_write_json(manifest_path, manifest)
        claim_path, claim = self.testing._create_claim(target, candidate, environment)
        source_reservation = self.testing._reserve_receipt(failed_path)
        source_args = self.args(
            cli,
            root,
            candidate_mode="dist",
            intent="upgrade",
            recovery_plan=None,
            expected_current_version=candidate["current_version"],
            expected_deploy_version=candidate["deploy_version"],
        )
        source_receipt = self.testing._new_receipt(
            source_args,
            target,
            candidate,
            claim_path,
            claim,
            source_reservation,
            self.testing._stages(self.testing.DIST_UPGRADE_STAGE_CONTRACT, set()),
        )
        source_receipt.pop("recovery_source")
        source_receipt["schema_version"] = "1.1"
        source_receipt["helper_sha256"] = source_helper_sha256
        source_receipt["policy"]["policy_version"] = "1.1"
        now = "2026-08-06T03:26:00Z"
        for stage in source_receipt["stages"][:8]:
            stage.update(status="succeeded", started_at=now, finished_at=now)
        source_receipt["stages"][8].update(
            status="failed",
            started_at=now,
            finished_at=now,
            error_code="PUBLISH_INDETERMINATE",
            recovery="reconcile remote package state; blind retry and republish prohibited",
        )
        source_receipt["status"] = "publish_indeterminate"
        source_receipt["external_write_started"] = True
        source_receipt["observations"]["prewrite"] = {
            "deploymentId": DEPLOYMENT_ID,
            "systemName": None,
            "deployVersion": None,
            "currentVersion": candidate["current_version"],
            "routeName": candidate["path_name"],
            "version": candidate["version"],
            "appName": candidate["app_name"],
            "appUrl": "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup",
            "operation": "testing_upgrade_pre",
        }
        source_receipt["receipt_hash"] = self.core._document_hash(source_receipt, "receipt_hash")
        self.core._atomic_write_json(failed_path, source_receipt)
        recovery_args = self.args(
            cli,
            root,
            candidate_mode="published-recovery",
            intent="upgrade",
            version=candidate["version"],
            recovery_plan=None,
            recovery_runtime_manifest=str(manifest_path),
            expected_current_version=candidate["current_version"],
            expected_deploy_version=candidate["deploy_version"],
            failed_testing_receipt=str(failed_path),
            expected_failed_receipt_hash=source_receipt["receipt_hash"],
            expected_failed_receipt_file_sha256=self.core._hash_file(failed_path, "failed"),
            expected_retained_claim_hash=claim["claim_hash"],
            expected_retained_claim_file_sha256=self.core._hash_file(claim_path, "claim"),
            expected_package_file_sha256=candidate["package_file_digest"],
            expected_source_helper_sha256=candidate["helper_sha256"],
            expected_runtime_manifest_hash=candidate["runtime_manifest_hash"],
        )
        return {
            "cli": cli,
            "target": target,
            "environment": environment,
            "source_receipt": source_receipt,
            "source_path": failed_path,
            "original_claim_path": claim_path,
            "runtime_config": runtime_config,
            "args": recovery_args,
        }

    def test_reconciled_runtime_manifest_argument_binds_evidence_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = root / "runtime.manifest.json"
            expected.write_text("{}\n", encoding="utf-8")
            other = root / "other.manifest.json"
            other.write_text("{}\n", encoding="utf-8")
            context = {
                "runtime_manifest": {},
                "paths": {"recovery_runtime_manifest": expected.resolve()},
            }
            self.assertEqual(
                self.testing._reconciled_runtime_manifest_path(
                    str(expected), context
                ),
                expected.resolve(),
            )
            with self.assertRaisesRegex(SystemExit, "does not match recovery evidence"):
                self.testing._reconciled_runtime_manifest_path(str(other), context)
            with self.assertRaisesRegex(SystemExit, "lacks an exact"):
                self.testing._reconciled_runtime_manifest_path(
                    str(expected), {"runtime_manifest": {}}
                )

    def test_main_requires_explicit_testing_and_execute_flags(self):
        base = ["--intent", "upgrade", "--candidate-mode", "reconciled"]
        for missing, argv in (
            ("testing-only", ["--execute", *base]),
            ("execute", ["--testing-only", *base]),
        ):
            with self.subTest(missing=missing), self.assertRaisesRegex(
                SystemExit, "requires both --testing-only and --execute"
            ):
                self.testing.main(argv)

    def test_main_requires_explicit_intent_and_candidate_mode(self):
        for argv in (
            ["--testing-only", "--execute", "--candidate-mode", "reconciled"],
            ["--testing-only", "--execute", "--intent", "upgrade"],
        ):
            with self.subTest(argv=argv), self.assertRaisesRegex(
                SystemExit, "requires explicit --intent and --candidate-mode"
            ):
                self.testing.main(argv)

    def test_main_dispatches_once_without_plan_or_approval_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = self.executable(root)
            receipt = root / "receipt.json"
            argv = [
                "--testing-only", "--execute", "--intent", "upgrade",
                "--candidate-mode", "reconciled", "--testing-purpose", "synthetic",
                "--receipt-output", str(receipt), "--cli-executable", str(cli),
                "--environment", "alpha", "--control-plane-url", "https://alpha.uipath.com",
                "--org-id", ORG_ID, "--org-name", "agenticgtm",
                "--tenant-id", TENANT_ID, "--tenant-name", "Dev",
                "--folder-key", FOLDER_ID, "--client-id", CLIENT_ID,
                "--package-name", "aura-vdp-template-mockup",
                "--app-name", "Aura VDP Template Mockup",
                "--path-name", "aura-vdp-mockup", "--version", "0.1.2",
                "--tags", "internal,mockup", "--cli-version", "1.198.0",
                "--cli-profile", "fixture-alpha",
            ]
            target = self.target(cli)
            with mock.patch.object(self.testing, "_resolve_cli", return_value=cli), mock.patch.object(
                self.testing, "_target", return_value=target
            ), mock.patch.object(
                self.testing, "_safe_environment", return_value={"HOME": str(root), "PATH": "/bin"}
            ), mock.patch.object(
                self.testing, "_reconciled_upgrade", return_value=receipt
            ) as execute:
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    self.assertEqual(self.testing.main(argv), 0)
            execute.assert_called_once()
            output = json.loads(stdout.getvalue())
            self.assertEqual(output["status"], "succeeded_testing")
            self.assertFalse(output["production_eligible"])
            self.assertFalse(output["release_evidence"])
            self.assertNotIn("plan_hash", output)
            self.assertNotIn("approved_plan_hash", output)

    def test_target_accepts_only_exact_alpha_and_staging_mappings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = self.executable(root)
            for environment, url in (
                ("alpha", "https://alpha.uipath.com"),
                ("staging", "https://staging.uipath.com"),
            ):
                args = self.args(
                    cli,
                    root,
                    environment=environment,
                    control_plane_url=url,
                    org_name="agenticgtm" if environment == "alpha" else "tam_global",
                    cli_profile=f"fixture-{environment}",
                )
                observed = self.testing._target(args, cli)
                self.assertEqual(observed["environment"], environment)
                self.assertEqual(observed["control_plane_url"], url)
                self.assertEqual(observed["cli_version"], "1.198.0")

    def test_target_rejects_cross_environment_custom_and_production_origins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = self.executable(root)
            cases = (
                ("alpha", "https://staging.uipath.com"),
                ("staging", "https://alpha.uipath.com"),
                ("alpha", "https://cloud.uipath.com"),
                ("alpha", "https://example.test"),
            )
            for environment, url in cases:
                with self.subTest(environment=environment, url=url), self.assertRaises(SystemExit):
                    self.testing._target(
                        self.args(cli, root, environment=environment, control_plane_url=url), cli
                    )
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.testing._parser().parse_args(["--environment", "production"])

    def test_target_rejects_unknown_cli_version_before_any_cli_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = self.executable(root)
            with self.assertRaisesRegex(SystemExit, "exactly 1.198.0"):
                self.testing._target(self.args(cli, root, cli_version="1.199.0"), cli)

    def test_internal_config_requires_exact_auth_client_origin_and_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            cli = self.executable(Path(tmp))
            target = self.target(cli)
            valid = {
                "clientId": CLIENT_ID,
                "scope": "openid profile",
                "baseUrl": "https://alpha.api.uipath.com",
                "redirectUri": "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup",
                "public": False,
            }
            self.testing._validate_internal_config(valid, target, "aura-vdp-mockup")
            cases = {
                "client": {**valid, "clientId": FOLDER_ID},
                "scope": {**valid, "scope": "openid"},
                "api": {**valid, "baseUrl": "https://staging.api.uipath.com"},
                "route": {**valid, "redirectUri": "https://agenticgtm.alpha.uipath.host/other"},
                "public": {**valid, "public": True},
                "anonymous": {**valid, "allowAnonymous": True},
            }
            for label, document in cases.items():
                with self.subTest(label=label), self.assertRaises(SystemExit):
                    self.testing._validate_internal_config(
                        document, target, "aura-vdp-mockup"
                    )

    def test_candidate_mode_matrix_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = self.executable(root)
            target = self.target(cli)
            environment = {"HOME": str(root), "PATH": "/bin"}
            reservation = {
                "path": str(root / ".receipt.json.reservation.json"),
                "file_sha256": self.core._hash_bytes(b"reservation"),
                "reservation_hash": self.core._hash_bytes(b"reservation-document"),
            }
            with self.assertRaisesRegex(SystemExit, "expected-current-version"):
                self.testing._dist_create(
                    self.args(
                        cli,
                        root,
                        candidate_mode="dist",
                        intent="upgrade",
                        expected_current_version=None,
                    ),
                    target,
                    cli,
                    environment,
                    root / "receipt.json",
                    reservation,
                )
            with self.assertRaisesRegex(SystemExit, "reconciled supports only --intent upgrade"):
                self.testing._reconciled_upgrade(
                    self.args(cli, root, candidate_mode="reconciled", intent="create"),
                    target,
                    cli,
                    environment,
                    root / "receipt.json",
                    reservation,
                )

    def test_receipt_is_redacted_nonproduction_and_has_exact_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = self.executable(root)
            _, _, _, _, receipt = self.claim_and_receipt(root, cli)
            with mock.patch.object(
                self.testing,
                "EXPECTED_CLI_SHA256",
                receipt["target"]["cli_executable_sha256"],
            ):
                self.testing._validate_receipt(receipt)
            keys = set(all_keys(receipt))
            self.assertTrue(
                {"plan_hash", "approved_plan_hash", "access_token", "client_secret"}.isdisjoint(keys)
            )
            self.assertEqual(receipt["authorization"]["mode"], "explicit_testing_request")
            self.assertEqual(receipt["policy"]["policy_version"], self.testing.POLICY_VERSION)
            self.assertEqual(receipt["policy"]["waived_gates"], self.testing.WAIVED_GATES)
            self.assertEqual(
                receipt["policy"]["nonwaivable_controls"],
                self.testing.NONWAIVABLE_CONTROLS,
            )
            self.assertEqual(receipt["policy"]["data_classification"], "synthetic_only")
            self.assertTrue(receipt["policy"]["internal_authenticated_required"])
            self.assertFalse(receipt["policy"]["production_eligible"])
            self.assertFalse(receipt["policy"]["release_evidence"])
            self.assertEqual(receipt["redaction"], self.testing.REDACTION)

    def test_testing_receipt_schema_is_strict_and_matches_policy_constants(self):
        schema = json.loads(RECEIPT_SCHEMA.read_text(encoding="utf-8"))
        policy = TESTING_POLICY.read_text(encoding="utf-8")
        self.assertEqual(schema["properties"]["kind"]["const"], self.testing.RECEIPT_KIND)
        self.assertEqual(
            schema["properties"]["schema_version"]["const"],
            self.testing.RECEIPT_SCHEMA_VERSION,
        )
        self.assertFalse(schema["additionalProperties"])
        for definition in ("target", "candidate", "stage"):
            self.assertFalse(schema["$defs"][definition]["additionalProperties"])
        policy_schema = schema["properties"]["policy"]["properties"]
        self.assertEqual(policy_schema["policy_version"]["const"], self.testing.POLICY_VERSION)
        self.assertEqual(policy_schema["waived_gates"]["const"], self.testing.WAIVED_GATES)
        self.assertEqual(
            policy_schema["nonwaivable_controls"]["const"],
            self.testing.NONWAIVABLE_CONTROLS,
        )
        self.assertIn("## Non-waivable controls", policy)
        self.assertIn("synthetic_only", policy)
        self.assertIn("internal authenticated access is required", policy)
        self.assertIn("atomic operation claim", policy)
        self.assertIn("never persisted in the receipt", policy)
        self.assertIn("no resume or automatic retry", policy.lower())

    def test_generated_receipt_required_fields_match_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = self.executable(root)
            _, _, _, _, receipt = self.claim_and_receipt(root, cli)
            schema = json.loads(RECEIPT_SCHEMA.read_text(encoding="utf-8"))
            self.assertEqual(set(receipt), set(schema["required"]))
            self.assertEqual(set(receipt["target"]), set(schema["$defs"]["target"]["required"]))
            self.assertEqual(
                set(receipt["candidate"]), set(schema["$defs"]["candidate"]["required"])
            )

    def test_draft_2020_12_schema_accepts_both_receipt_phases_and_rejects_state_drift(self):
        schema = json.loads(RECEIPT_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = self.executable(root)
            _, _, _, _, claimed = self.claim_and_receipt(root, cli)
            self.assertEqual(list(validator.iter_errors(claimed)), [])
            preflight_reservation = self.testing._reserve_receipt(
                root / "preflight-receipt.json"
            )
            preflight = self.testing._new_preflight_failure_receipt(
                self.args(cli, root, receipt_output=str(root / "preflight-receipt.json")),
                self.target(cli),
                preflight_reservation,
                "LOCAL_PREFLIGHT_FAILED",
            )
            self.assertEqual(list(validator.iter_errors(preflight)), [])

            succeeded, _, error, _, _, _, _ = self.run_reconciled(
                root / "succeeded"
            )
            self.assertIsNone(error)
            self.assertEqual(succeeded["status"], "succeeded_testing")
            self.assertEqual(list(validator.iter_errors(succeeded)), [])

            invalid = {}
            invalid["environment_origin"] = copy.deepcopy(claimed)
            invalid["environment_origin"]["target"]["control_plane_url"] = (
                "https://staging.uipath.com"
            )
            invalid["mode_intent"] = copy.deepcopy(claimed)
            invalid["mode_intent"]["candidate"]["intent"] = "create"
            invalid["stage_order"] = copy.deepcopy(claimed)
            invalid["stage_order"]["stages"][0], invalid["stage_order"]["stages"][1] = (
                invalid["stage_order"]["stages"][1],
                invalid["stage_order"]["stages"][0],
            )
            invalid["running_without_timestamp"] = copy.deepcopy(claimed)
            invalid["running_without_timestamp"]["stages"][1]["status"] = "running"
            invalid["false_success"] = copy.deepcopy(claimed)
            invalid["false_success"]["status"] = "succeeded_testing"
            invalid["false_success"]["external_write_started"] = True
            for label, document in invalid.items():
                with self.subTest(label=label):
                    self.assertTrue(
                        list(validator.iter_errors(document)),
                        f"schema unexpectedly accepted {label}",
                    )

    def test_execution_claim_is_atomic_scoped_and_released_only_prewrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = self.executable(root)
            environment, claim_path, claim, receipt_path, receipt = self.claim_and_receipt(root, cli)
            with self.assertRaisesRegex(SystemExit, "already exists"):
                self.testing._create_claim(self.target(cli), self.candidate(), environment)
            changed_config = self.candidate()
            changed_config["uipath_config_digest"] = self.core._hash_bytes(
                b"different-uipath-config"
            )
            with self.assertRaisesRegex(SystemExit, "already exists"):
                self.testing._create_claim(
                    self.target(cli), changed_config, environment
                )
            dist_candidate = self.candidate(mode="dist", intent="create")
            first_dist_path, _ = self.testing._create_claim(
                self.target(cli), dist_candidate, environment
            )
            changed_dist = copy.deepcopy(dist_candidate)
            changed_dist["uipath_config_digest"] = self.core._hash_bytes(
                b"different-dist-uipath-config"
            )
            with self.assertRaisesRegex(SystemExit, "already exists"):
                self.testing._create_claim(
                    self.target(cli), changed_dist, environment
                )
            different_route = copy.deepcopy(dist_candidate)
            different_route["path_name"] = "another-mockup-route"
            distinct_path, _ = self.testing._create_claim(
                self.target(cli), different_route, environment
            )
            self.assertNotEqual(distinct_path, first_dist_path)
            receipt["status"] = "failed_prewrite"
            with mock.patch.object(
                self.testing,
                "EXPECTED_CLI_SHA256",
                receipt["target"]["cli_executable_sha256"],
            ):
                self.testing._release_claim(
                    claim_path, claim, receipt, receipt_path
                )
            self.assertFalse(claim_path.exists())
            self.assertTrue(first_dist_path.exists())
            self.assertTrue(distinct_path.exists())
            persisted = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertTrue(persisted["execution_claim"]["released"])
            with self.assertRaises((FileNotFoundError, SystemExit)):
                self.testing._release_claim(claim_path, claim, receipt, receipt_path)

    def test_receipt_and_workspace_refuse_overwrite_or_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt = root / "receipt.json"
            receipt.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "refuses to overwrite"):
                self.testing._receipt_path(str(receipt))
            workspace = root / "receipt.workspace"
            workspace.mkdir()
            dist = root / "dist"
            dist.mkdir()
            (dist / "index.html").write_text("fixture", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "blind replay"):
                self.testing._copy_exact_dist(dist, workspace)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.testing._parser().parse_args(["--resume"])

    def test_git_state_hashes_raw_dirty_porcelain_bytes(self):
        head = SOURCE_SHA + "\n"
        dirty = b" M package.json\0?? local-only.txt\0"
        completed = [
            subprocess.CompletedProcess(["git"], 0, head, ""),
            subprocess.CompletedProcess(["git"], 0, dirty, b""),
        ]
        with mock.patch.object(self.testing.subprocess, "run", side_effect=completed) as run:
            observed_head, status_digest, source_sha = self.testing._git_state(
                Path(tempfile.gettempdir()) / "source"
            )
        self.assertEqual(observed_head, SOURCE_SHA)
        self.assertEqual(source_sha, SOURCE_SHA)
        self.assertEqual(status_digest, self.core._hash_bytes(dirty))
        self.assertEqual(run.call_count, 2)
        self.assertIn("--porcelain=v1", run.call_args_list[1].args[0])
        self.assertIn("-z", run.call_args_list[1].args[0])

    def test_dist_copy_binds_exact_bytes_modes_and_audits_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source-dist"
            source.mkdir()
            index = source / "index.html"
            index.write_text("<!doctype html>", encoding="utf-8")
            index.chmod(0o640)
            (source / "assets").mkdir()
            (source / "assets" / "app.js").write_text("console.log('fixture')", encoding="utf-8")
            copied, digest = self.testing._copy_exact_dist(source, root / "evidence")
            self.assertEqual(digest, self.testing._directory_digest(source))
            self.assertEqual(digest, self.testing._directory_digest(copied))
            self.assertEqual((copied / "index.html").stat().st_mode & 0o777, 0o640)
            secret = root / "secret-dist"
            secret.mkdir()
            secret_field = "client_" + "secret"
            (secret / "bundle.js").write_text(
                f'const {secret_field} = "this-is-a-real-looking-secret-value";',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                SystemExit, "(?:secret audit failed|prohibited secret-like field)"
            ):
                self.testing._audit_dist(secret)

    def test_reconciled_audits_ignored_config_and_exact_package_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "uipath.json"
            config.write_text(
                json.dumps(
                    {
                        "clientId": CLIENT_ID,
                        "client_secret": "this-is-a-real-looking-secret-value",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                SystemExit, "(?:secret audit failed|prohibited secret-like field)"
            ):
                self.testing._load_and_audit_uipath_config(
                    config, "Reconciled source"
                )

            package = root / "candidate.nupkg"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr(
                    "content/bundle.js",
                    'const access_token = "this-is-a-real-looking-secret-value";',
                )
            content_digest = self.core._hash_bytes(b"content")
            file_digest = self.core._hash_file(package, "secret fixture package")
            plan = {
                "candidate": {
                    "package_path": "candidate.nupkg",
                    "package_content_digest": content_digest,
                    "package_file_digest": file_digest,
                },
                "existing_deployment": {
                    "package_name": "aura-vdp-template-mockup"
                },
            }
            context = {"failed_plan": {"parameters": {"main_file": "index.html"}}}
            with mock.patch.object(
                self.testing.core,
                "_package_evidence",
                return_value=(content_digest, file_digest),
            ), self.assertRaisesRegex(SystemExit, "secret audit failed"):
                self.testing._resolve_reconciled_package(root, plan, context)

    def test_source_audit_allows_only_exact_path_and_line_commitments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            decode_fixture = bytes.fromhex
            fixture_lines = {
                "apps/frontend/src/uipath/commandGateway.v0.test.ts": [
                    decode_fixture(
                        "20202020636f6e737420616363657373546f6b656e203d2076616c69644163"
                        "63657373546f6b656e28293b"
                    )
                ],
                "release/certification/test/certification.test.mjs": [
                    decode_fixture(
                        "2020706c616e2e676f7665726e616e63652e636c69656e7453656372657420"
                        "3d202273686f756c642d6e6f742d62652d68657265223b"
                    )
                ],
                "release/config/validate-release-profile.test.mjs": [
                    decode_fixture(
                        "202070726f66696c652e7569706174682e636c69656e74536563726574203d"
                        "20226e6f742d6576656e2d612d7265616c2d736563726574223b"
                    ),
                    decode_fixture(
                        "2020202022726566732f68656164732f65794a68624763694f694a49557a49"
                        "314e694a392e6162636465666768696a6b6c6d6e6f702e7172737475767778"
                        "797a303132333435223b"
                    ),
                ],
                "release/test/package-inspection.test.mjs": [
                    decode_fixture(
                        "202020202020202064697374496e6465783a20224265617265722061626364"
                        "65666768696a6b6c6d6e6f707172737475767778797a222c"
                    ),
                    decode_fixture(
                        "202020202020202061726368697665496e6465783a20224265617265722061"
                        "62636465666768696a6b6c6d6e6f707172737475767778797a222c"
                    ),
                ],
            }
            fixtures = {
                relative: b"\n".join(lines) + b"\n"
                for relative, lines in fixture_lines.items()
            }
            findings = [
                finding
                for payload in fixtures.values()
                for finding in self.testing._secret_like_matches(payload)
            ]
            self.assertEqual(len(findings), 6)
            observed_line_commitments = {
                relative: frozenset(self.core._hash_bytes(line) for line in lines)
                for relative, lines in fixture_lines.items()
            }
            self.assertEqual(
                observed_line_commitments,
                self.testing.KNOWN_SYNTHETIC_SOURCE_LINES,
            )
            for relative, payload in fixtures.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
            listing = subprocess.CompletedProcess(
                ["git", "ls-files"],
                0,
                b"\0".join(path.encode() for path in fixtures) + b"\0",
                b"",
            )
            with mock.patch.object(
                self.testing.subprocess, "run", return_value=listing
            ):
                self.testing._audit_tracked_source(root, root)

            committed_path = "apps/frontend/src/uipath/commandGateway.v0.test.ts"
            committed_line = fixture_lines[committed_path][0]
            random_line = (
                bytes.fromhex("636f6e7374206163636573735f746f6b656e203d2022")
                + os.urandom(24).hex().encode("ascii")
                + b'";'
            )

            def assert_source_rejected(relative, payload):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
                source_listing = subprocess.CompletedProcess(
                    ["git", "ls-files"], 0, relative.encode() + b"\0", b""
                )
                with mock.patch.object(
                    self.testing.subprocess, "run", return_value=source_listing
                ), self.assertRaisesRegex(SystemExit, "secret audit failed"):
                    self.testing._audit_tracked_source(root, root)

            for near_miss in (
                "apps/frontend/src/uipath/application.ts",
                "apps/frontend/src/uipath/copied.test.ts",
                "apps/frontend/src/contest/commandGateway.v0.test.ts",
                "apps/frontend/src/test-data/commandGateway.v0.test.ts",
                "apps/frontend/src/uipath/latest.ts",
            ):
                assert_source_rejected(near_miss, committed_line + b"\n")

            for random_path in (
                "src/credential.test.ts",
                "src/tests/credential.ts",
            ):
                assert_source_rejected(random_path, random_line + b"\n")

            for mutation in (
                b" " + committed_line,
                committed_line.replace(b"validAccess", b"validaccess", 1),
                committed_line + b"$" + os.urandom(12).hex().encode("ascii"),
                committed_line + b' + "' + os.urandom(12).hex().encode("ascii") + b'"',
                committed_line + b"\n" + random_line,
            ):
                assert_source_rejected(committed_path, mutation + b"\n")

    def test_reviewed_source_line_remains_strict_outside_tracked_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sentinel = bytes.fromhex(
                "20202020636f6e737420616363657373546f6b656e203d2076616c69644163"
                "63657373546f6b656e28293b"
            )
            dist = root / "dist"
            dist.mkdir()
            (dist / "index.js").write_bytes(sentinel)
            with self.assertRaisesRegex(SystemExit, "secret audit failed"):
                self.testing._audit_dist(dist)

            package = Path(tmp) / "candidate.nupkg"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("content/index.js", sentinel)
            with self.assertRaisesRegex(SystemExit, "secret audit failed"):
                self.testing._audit_package_archive(package)

            config = root / "uipath.json"
            config.write_text(
                json.dumps({"sourceFixture": sentinel.decode("utf-8")}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SystemExit, "secret audit failed"):
                self.testing._load_and_audit_uipath_config(config, "Testing")

            serialized_arguments = json.dumps(
                ["--testing-purpose", sentinel.decode("utf-8")]
            ).encode("utf-8")
            with self.assertRaisesRegex(SystemExit, "secret audit failed"):
                self.testing._audit_payload(serialized_arguments)

    def test_dist_digest_rejects_symlinks_and_empty_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(SystemExit, "contains no files"):
                self.testing._directory_digest(root)
            target = root / "target"
            target.write_text("fixture", encoding="utf-8")
            link = root / "link"
            link.symlink_to(target)
            with self.assertRaisesRegex(SystemExit, "may not contain symlinks"):
                self.testing._directory_digest(root)

    def test_create_guard_patch_is_exact_deterministic_and_fail_closed(self):
        source = "\n".join(old for old, _ in self.testing.CREATE_GUARD_PATCH_EDITS).encode()
        with mock.patch.object(
            self.testing.recovery,
            "EXPECTED_CODEDAPP_TOOL_SHA256",
            self.core._hash_bytes(source),
        ):
            first = self.testing._patched_create_guard_bytes(source)
            second = self.testing._patched_create_guard_bytes(source)
        self.assertEqual(first, second)
        patched = first.decode()
        self.assertIn("TESTING_CREATE_GUARD_REQUIRED", patched)
        self.assertIn("TESTING_CREATE_DEPLOYMENT_EXISTS", patched)
        self.assertIn("--testing-create-mode", patched)
        self.assertIn("checkAppNameUniqueness", patched)
        self.assertIn('operation: "testing_create_verify"', patched)
        self.assertLess(
            patched.index("TESTING_CREATE_DEPLOYMENT_EXISTS"),
            patched.index("let operationResult"),
        )
        with mock.patch.object(
            self.testing.recovery,
            "EXPECTED_CODEDAPP_TOOL_SHA256",
            self.core._hash_bytes(source + b"drift"),
        ), self.assertRaisesRegex(SystemExit, "not the supported"):
            self.testing._patched_create_guard_bytes(source)

    def test_create_guard_prep_and_barriers_reject_manifest_entrypoint_redirection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = self.executable(root)
            cli_manifest = cli.parents[1] / "package.json"
            tool_root = root / "node_modules" / "@uipath" / "codedapp-tool"
            tool = tool_root / "dist" / "tool.js"
            tool.parent.mkdir(parents=True)
            tool.write_text("// exact tool fixture\n", encoding="utf-8")
            malicious_manifest = {
                "version": self.testing.recovery.EXPECTED_CODEDAPP_TOOL_VERSION,
                "gitHead": self.testing.recovery.EXPECTED_CODEDAPP_TOOL_GIT_HEAD,
                "main": "./dist/attacker.js",
                "exports": {".": "./dist/attacker.js"},
                "bin": {"codedapp-tool": "./dist/index.js"},
            }
            tool_manifest = tool_root / "package.json"
            tool_manifest.write_text(
                json.dumps(malicious_manifest, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            cli_digest = self.core._hash_file(cli, "fixture CLI")
            cli_manifest_digest = self.core._hash_file(
                cli_manifest, "fixture CLI manifest"
            )
            tool_digest = self.core._hash_file(tool, "fixture tool")
            tool_manifest_digest = self.core._hash_file(
                tool_manifest, "malicious tool manifest"
            )
            node = root / "node"
            node.write_text("node fixture\n", encoding="utf-8")
            node.chmod(0o755)
            node_runtime = {
                "executable": str(node.resolve()),
                "executable_sha256": self.core._hash_file(node, "fixture node"),
                "version": "24.13.0",
            }
            with mock.patch.object(
                self.testing, "EXPECTED_CLI_SHA256", cli_digest
            ), mock.patch.object(
                self.testing,
                "EXPECTED_CLI_MANIFEST_SHA256",
                cli_manifest_digest,
            ), mock.patch.object(
                self.testing.recovery,
                "EXPECTED_CODEDAPP_TOOL_SHA256",
                tool_digest,
            ), mock.patch.object(
                self.testing,
                "EXPECTED_CODEDAPP_TOOL_MANIFEST_SHA256",
                tool_manifest_digest,
            ), mock.patch.object(
                self.testing.shutil, "copytree"
            ) as copytree, mock.patch.object(
                self.testing.subprocess, "run"
            ) as run, self.assertRaisesRegex(SystemExit, "entrypoints are unsupported"):
                self.testing._prepare_create_guard_runtime(
                    cli,
                    node_runtime,
                    root / "evidence",
                    {"appVersion": "0.1.2"},
                    {"HOME": str(root), "PATH": "/usr/bin:/bin"},
                )
            copytree.assert_not_called()
            run.assert_not_called()

            runtime_manifest = {
                "source_cli_manifest": str(cli_manifest.resolve()),
                "source_cli_manifest_sha256": cli_manifest_digest,
                "runtime_cli_manifest": str(cli_manifest.resolve()),
                "runtime_cli_manifest_sha256": cli_manifest_digest,
                "source_tool_manifest": str(tool_manifest.resolve()),
                "source_tool_manifest_sha256": tool_manifest_digest,
                "runtime_tool_manifest": str(tool_manifest.resolve()),
                "runtime_tool_manifest_sha256": tool_manifest_digest,
            }
            runtime_manifest["manifest_hash"] = self.core._document_hash(
                runtime_manifest, "manifest_hash"
            )
            runtime_manifest_path = root / "runtime.manifest.json"
            runtime_manifest_path.write_text(
                json.dumps(runtime_manifest), encoding="utf-8"
            )
            runtime = {"manifest_path": str(runtime_manifest_path)}
            candidate = {"runtime_manifest_hash": runtime_manifest["manifest_hash"]}
            for barrier in (
                self.testing._revalidate_create_runtime,
                self.testing._revalidate_create_runtime_immutable,
            ):
                with self.subTest(barrier=barrier.__name__), mock.patch.object(
                    self.testing,
                    "EXPECTED_CLI_MANIFEST_SHA256",
                    cli_manifest_digest,
                ), mock.patch.object(
                    self.testing,
                    "EXPECTED_CODEDAPP_TOOL_MANIFEST_SHA256",
                    tool_manifest_digest,
                ), self.assertRaisesRegex(SystemExit, "entrypoints are unsupported"):
                    barrier(runtime, candidate)

    def test_create_guard_command_is_read_only_bound_and_contains_no_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            cli = self.executable(Path(tmp))
            target = self.target(cli)
            runtime = {
                "node_executable": "/exact/node",
                "runtime_cli": "/exact/runtime/uip",
            }
            command = self.testing._create_guard_command(runtime, target, self.candidate(mode="dist", intent="create"))
            self.assertEqual(command[:4], ["/exact/node", "/exact/runtime/uip", "codedapp", "deploy"])
            self.assertEqual(command[command.index("--testing-create-mode") + 1], "verify")
            self.assertIn("--path-name", command)
            self.assertIn("--client-id", command)
            self.assertNotIn("--access-token", command)
            self.assertNotIn("--client-secret", command)

    def test_create_guard_output_requires_exact_envelope_fields_and_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            cli = self.executable(Path(tmp))
            target = self.target(cli)
            candidate = self.candidate(mode="dist", intent="create")
            expected = {
                "Message": "Testing create target verified absent; no mutation performed.",
                "DeploymentId": None,
                "SystemName": None,
                "DeployVersion": None,
                "CurrentVersion": None,
                "RouteName": candidate["path_name"],
                "Version": candidate["version"],
                "AppName": candidate["app_name"],
                "AppUrl": self.testing._route_url(target, candidate["path_name"]),
                "Operation": "testing_create_verify",
            }
            envelope = {"Result": "Success", "Code": "DeployCompleted", "Data": expected}
            observation = self.testing._validate_create_guard_output(
                json.dumps(envelope), target, candidate
            )
            self.assertEqual(observation["operation"], "testing_create_verify")
            for mutation in ("extra", "route", "operation", "result"):
                bad = json.loads(json.dumps(envelope))
                if mutation == "extra":
                    bad["Data"]["Unexpected"] = True
                elif mutation == "route":
                    bad["Data"]["RouteName"] = "other-route"
                elif mutation == "operation":
                    bad["Data"]["Operation"] = "deploy"
                else:
                    bad["Result"] = "Failure"
                with self.subTest(mutation=mutation), self.assertRaises(SystemExit):
                    self.testing._validate_create_guard_output(json.dumps(bad), target, candidate)

    def test_reconciled_inputs_bind_every_target_candidate_and_runtime_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = self.executable(root)
            (root / "source").mkdir()
            target = self.target(cli)
            plan, _ = self.recovery_plan(cli, root)
            args = self.args(
                cli,
                root,
                expected_recovery_plan_hash=plan["plan_hash"],
                expected_runtime_manifest_hash=plan["candidate"][
                    "recovery_runtime_manifest_hash"
                ],
            )
            self.testing._match_recovery_inputs(args, plan, target, cli)
            cases = {
                "target": ("organization_id", ORG_ID[:-1] + "1"),
                "package": ("package_name", "other-package"),
                "app": ("app_name", "Other app"),
                "route": ("path_name", "other-route"),
                "version": ("version", "0.1.3"),
                "tags": ("tags", "internal,other"),
                "profile": ("cli_profile", "other-profile"),
            }
            for label, (field, value) in cases.items():
                bad_args = self.args(
                    cli,
                    root,
                    expected_recovery_plan_hash=plan["plan_hash"],
                    expected_runtime_manifest_hash=plan["candidate"][
                        "recovery_runtime_manifest_hash"
                    ],
                )
                bad_target = dict(target)
                if field == "organization_id":
                    bad_target[field] = value
                elif field == "cli_profile":
                    bad_target[field] = value
                else:
                    setattr(bad_args, field, value)
                with self.subTest(label=label), self.assertRaises(SystemExit):
                    self.testing._match_recovery_inputs(bad_args, plan, bad_target, cli)

    def test_reconciled_success_retains_claim_and_records_testing_only_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_reconciled(Path(tmp))
            receipt, claim_path, error, _, deploy, verify, inspect = result
            self.assertIsNone(error)
            self.assertEqual(receipt["status"], "succeeded_testing")
            self.assertTrue(receipt["external_write_started"])
            self.assertFalse(receipt["execution_claim"]["released"])
            self.assertTrue(claim_path.exists())
            deploy.assert_called_once()
            verify.assert_called_once_with(
                "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup", 15
            )
            inspect.assert_called_once()
            self.assertTrue(all(stage["status"] == "succeeded" for stage in receipt["stages"]))

    def test_reconciled_pre_guard_failure_releases_claim_and_never_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt, claim_path, error, _, deploy, verify, _ = self.run_reconciled(
                Path(tmp), pre_guard_effect=SystemExit("stale target")
            )
            self.assertIsInstance(error, SystemExit)
            self.assertEqual(receipt["status"], "failed_prewrite")
            self.assertTrue(receipt["execution_claim"]["released"])
            self.assertFalse(claim_path.exists())
            self.assertFalse(receipt["external_write_started"])
            deploy.assert_not_called()
            verify.assert_not_called()

    def test_reconciled_runtime_failure_releases_claim_and_never_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt, claim_path, error, _, deploy, _, _ = self.run_reconciled(
                Path(tmp), runtime_effect=SystemExit("runtime drift")
            )
            self.assertIsInstance(error, SystemExit)
            self.assertEqual(receipt["status"], "failed_prewrite")
            self.assertTrue(receipt["execution_claim"]["released"])
            self.assertFalse(claim_path.exists())
            deploy.assert_not_called()

    def test_reconciled_last_moment_barrier_failure_is_indeterminate_without_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt, claim_path, error, _, deploy, verify, _ = self.run_reconciled(
                Path(tmp), runtime_effect=[None, SystemExit("last-moment drift")]
            )
            self.assertIsInstance(error, SystemExit)
            self.assertEqual(receipt["status"], "deploy_indeterminate")
            self.assertTrue(receipt["external_write_started"])
            self.assertTrue(claim_path.exists())
            deploy.assert_not_called()
            verify.assert_not_called()
            deploy_stage = next(
                stage for stage in receipt["stages"] if stage["name"] == "deploy"
            )
            self.assertEqual(deploy_stage["status"], "failed")
            self.assertEqual(deploy_stage["error_code"], "DEPLOY_INDETERMINATE")

    def test_reconciled_post_guard_rechecks_immutable_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt, claim_path, error, remote, deploy, verify, _ = self.run_reconciled(
                Path(tmp), immutable_effect=SystemExit("immutable runtime drift")
            )
            self.assertIsInstance(error, SystemExit)
            self.assertEqual(receipt["status"], "deployed_unverified")
            self.assertTrue(claim_path.exists())
            deploy.assert_called_once()
            self.assertEqual(remote.call_count, 1)
            verify.assert_not_called()

    def test_reconciled_deploy_failure_is_indeterminate_and_retains_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt, claim_path, error, remote, deploy, verify, _ = self.run_reconciled(
                Path(tmp), deploy_effect=RuntimeError("ambiguous write")
            )
            self.assertIsInstance(error, RuntimeError)
            self.assertEqual(receipt["status"], "deploy_indeterminate")
            self.assertTrue(receipt["external_write_started"])
            self.assertFalse(receipt["execution_claim"]["released"])
            self.assertTrue(claim_path.exists())
            self.assertEqual(remote.call_count, 1)
            deploy.assert_called_once()
            verify.assert_not_called()

    def test_reconciled_post_guard_failure_is_deployed_unverified(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt, claim_path, error, _, deploy, verify, _ = self.run_reconciled(
                Path(tmp), post_guard_effect=SystemExit("version mismatch")
            )
            self.assertIsInstance(error, SystemExit)
            self.assertEqual(receipt["status"], "deployed_unverified")
            self.assertTrue(claim_path.exists())
            deploy.assert_called_once()
            verify.assert_not_called()

    def test_reconciled_route_or_config_failure_is_deployed_unverified(self):
        for boundary, kwargs in (
            ("route", {"route_effect": SystemExit("route unavailable")}),
            ("config", {"config_effect": SystemExit("config mismatch")}),
        ):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as tmp:
                receipt, claim_path, error, _, deploy, _, _ = self.run_reconciled(
                    Path(tmp), **kwargs
                )
                self.assertIsInstance(error, SystemExit)
                self.assertEqual(receipt["status"], "deployed_unverified")
                self.assertTrue(claim_path.exists())
                deploy.assert_called_once()

    def test_dist_create_publish_failure_is_indeterminate_and_never_deploys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = self.executable(root)
            source = root / "source"
            dist = source / "dist"
            dist.mkdir(parents=True)
            (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")
            (source / "uipath.json").write_text(
                json.dumps(
                    {
                        "clientId": CLIENT_ID,
                        "scope": "openid profile",
                        "baseUrl": "https://alpha.api.uipath.com",
                        "redirectUri": "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup",
                        "public": False,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            home = root / "home"
            (home / ".uipath").mkdir(parents=True)
            environment = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
            target = self.target(cli)
            args = self.args(
                cli,
                root,
                intent="create",
                candidate_mode="dist",
                app_name="aura-vdp-template-mockup",
                recovery_plan=None,
            )
            reservation = self.testing._reserve_receipt(
                root / "testing-receipt.json"
            )
            runtime = {
                "manifest_hash": self.core._hash_bytes(b"runtime"),
                "runtime_workspace": str(root / "guard-workspace"),
                "node_executable": "/exact/node",
                "runtime_cli": "/exact/runtime/uip",
                "runtime_app_config_sha256": self.core._hash_bytes(
                    b"runtime-app-config"
                ),
                "runtime_immutable_sha256": self.core._hash_bytes(
                    b"runtime-immutable"
                ),
            }
            Path(runtime["runtime_workspace"]).mkdir()
            guard_output = json.dumps(
                {
                    "Result": "Success",
                    "Code": "DeployCompleted",
                    "Data": {
                        "Message": "Testing create target verified absent; no mutation performed.",
                        "DeploymentId": None,
                        "SystemName": None,
                        "DeployVersion": None,
                        "CurrentVersion": None,
                        "RouteName": "aura-vdp-mockup",
                        "Version": "0.1.2",
                        "AppName": "aura-vdp-template-mockup",
                        "AppUrl": "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup",
                        "Operation": "testing_create_verify",
                    },
                }
            )

            calls = []

            def fake_write(command, cwd, env, code):
                calls.append((command, code))
                if code == "PUBLISH_INDETERMINATE":
                    raise self.testing.TestingCommandError(code)
                return {"Result": "Success"}

            with mock.patch.object(
                self.testing,
                "EXPECTED_CLI_SHA256",
                target["cli_executable_sha256"],
            ), mock.patch.object(
                self.testing,
                "_resolve_node",
                return_value={
                    "executable": "/usr/local/bin/node",
                    "executable_sha256": self.testing.SUPPORTED_NODE_RUNTIMES[
                        "24.13.0"
                    ],
                    "version": "24.13.0",
                },
            ), mock.patch.object(
                self.testing, "_audit_tracked_source"
            ), mock.patch.object(
                self.testing, "_git_state", return_value=(SOURCE_SHA, self.core._hash_bytes(b"dirty"), SOURCE_SHA)
            ), mock.patch.object(
                self.testing, "_validate_cli"
            ), mock.patch.object(
                self.testing.core,
                "_package_evidence",
                return_value=(self.core._hash_bytes(b"package-content"), self.core._hash_bytes(b"package-file")),
            ), mock.patch.object(
                self.testing, "_audit_package_archive"
            ), mock.patch.object(
                self.testing, "_prepare_create_guard_runtime", return_value=runtime
            ), mock.patch.object(
                self.testing, "_revalidate_dist_barrier"
            ), mock.patch.object(
                self.testing, "_run_read", return_value=guard_output
            ), mock.patch.object(
                self.testing, "_run_write", side_effect=fake_write
            ):
                with self.assertRaises(self.testing.TestingCommandError):
                    self.testing._dist_create(
                        args,
                        target,
                        cli,
                        environment,
                        root / "testing-receipt.json",
                        reservation,
                    )
            receipt = json.loads((root / "testing-receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "publish_indeterminate")
            self.assertTrue(receipt["external_write_started"])
            self.assertTrue(Path(receipt["execution_claim"]["path"]).exists())
            self.assertEqual([code for _, code in calls], ["PACK_FAILED", "PUBLISH_INDETERMINATE"])

    def test_dist_upgrade_full_mocked_orchestration_succeeds_exactly_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = self.executable(root)
            source = root / "source"
            dist = source / "dist"
            dist.mkdir(parents=True)
            (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")
            (source / "uipath.json").write_text(
                json.dumps(
                    {
                        "clientId": CLIENT_ID,
                        "scope": "openid profile",
                        "baseUrl": "https://alpha.api.uipath.com",
                        "redirectUri": "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup",
                        "public": False,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            home = root / "home"
            (home / ".uipath").mkdir(parents=True)
            environment = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
            target = self.target(cli)
            args = self.args(
                cli,
                root,
                intent="upgrade",
                candidate_mode="dist",
                version="0.1.3",
                expected_current_version="0.1.2",
                expected_system_name=SYSTEM_NAME,
                expected_deploy_version=4,
                recovery_plan=None,
            )
            reservation = self.testing._reserve_receipt(root / "testing-receipt.json")
            runtime_workspace = root / "guard-workspace"
            runtime_config = runtime_workspace / self.core.APP_CONFIG_RELATIVE_PATH
            runtime_config.parent.mkdir(parents=True)
            runtime_config.write_text(
                json.dumps(
                    {
                        "appName": "aura-vdp-template-mockup",
                        "displayName": "Aura VDP Template Mockup",
                        "appVersion": "0.1.3",
                        "appType": "Web",
                        "personalWorkspace": False,
                        "appUrl": "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup",
                        "deployedAt": "2026-08-06T03:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            runtime = {
                "manifest_hash": self.core._hash_bytes(b"runtime"),
                "runtime_workspace": str(runtime_workspace),
                "node_executable": "/exact/node",
                "runtime_cli": "/exact/runtime/uip",
                "runtime_app_config_sha256": self.core._hash_bytes(b"runtime-app-config"),
                "runtime_immutable_sha256": self.core._hash_bytes(b"runtime-immutable"),
            }

            def observation(operation, current, system=SYSTEM_NAME, deploy=4):
                messages = {
                    "testing_upgrade_pre": "Testing upgrade target verified; no mutation performed.",
                    "testing_upgrade_candidate": "Testing upgrade candidate verified; no mutation performed.",
                    "testing_upgrade_post": "Testing upgrade post-state verified.",
                }
                return json.dumps(
                    {
                        "Result": "Success",
                        "Code": "DeployCompleted",
                        "Data": {
                            "Message": messages[operation],
                            "DeploymentId": DEPLOYMENT_ID,
                            "SystemName": None if operation == "testing_upgrade_pre" else system,
                            "DeployVersion": None if operation == "testing_upgrade_pre" else deploy,
                            "CurrentVersion": current,
                            "RouteName": "aura-vdp-mockup",
                            "Version": "0.1.3",
                            "AppName": "Aura VDP Template Mockup",
                            "AppUrl": "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup",
                            "Operation": operation,
                        },
                    }
                )

            read_results = [
                observation("testing_upgrade_pre", "0.1.2"),
                observation("testing_upgrade_candidate", "0.1.2"),
                observation("testing_upgrade_post", "0.1.3"),
            ]
            writes = []

            def fake_read(command, cwd, env, code):
                mode = command[command.index("--testing-create-mode") + 1]
                if mode == "upgrade-candidate":
                    checkpoint = json.loads(
                        (root / "testing-receipt.json").read_text(encoding="utf-8")
                    )
                    self.assertIsNone(
                        checkpoint["observations"]["published_candidate"]
                    )
                return read_results.pop(0)

            def fake_write(command, cwd, env, code):
                writes.append((command, code))
                if code == "PUBLISH_INDETERMINATE":
                    return {
                        "Result": "Success",
                        "Code": "PublishCompleted",
                        "Data": {
                            "Message": "Package published successfully.",
                            "PackageName": "aura-vdp-template-mockup",
                            "PackageVersion": "0.1.3",
                            "SystemName": SYSTEM_NAME,
                            "PersonalWorkspace": False,
                            "AppType": "Web",
                        },
                    }
                if code == "DEPLOY_INDETERMINATE":
                    return json.loads(
                        observation("testing_upgrade_post", "0.1.3")
                        .replace("testing_upgrade_post", "testing_upgrade_execute")
                        .replace("Testing upgrade post-state verified.", "Testing upgrade completed.")
                    )
                return {"Result": "Success"}

            with mock.patch.object(
                self.testing, "EXPECTED_CLI_SHA256", target["cli_executable_sha256"]
            ), mock.patch.object(
                self.testing,
                "_resolve_node",
                return_value={
                    "executable": "/usr/local/bin/node",
                    "executable_sha256": self.testing.SUPPORTED_NODE_RUNTIMES["24.13.0"],
                    "version": "24.13.0",
                },
            ), mock.patch.object(
                self.testing, "_audit_tracked_source"
            ), mock.patch.object(
                self.testing,
                "_git_state",
                return_value=(SOURCE_SHA, self.core._hash_bytes(b"dirty"), SOURCE_SHA),
            ), mock.patch.object(
                self.testing, "_validate_cli"
            ), mock.patch.object(
                self.testing.core,
                "_package_evidence",
                return_value=(
                    self.core._hash_bytes(b"package-content"),
                    self.core._hash_bytes(b"package-file"),
                ),
            ), mock.patch.object(
                self.testing, "_audit_package_archive"
            ), mock.patch.object(
                self.testing, "_prepare_create_guard_runtime", return_value=runtime
            ), mock.patch.object(
                self.testing, "_revalidate_dist_barrier"
            ), mock.patch.object(
                self.testing, "_revalidate_create_runtime_immutable"
            ), mock.patch.object(
                self.testing, "_run_read", side_effect=fake_read
            ), mock.patch.object(
                self.testing, "_run_write", side_effect=fake_write
            ), mock.patch.object(
                self.testing.core, "_bind_app_config"
            ), mock.patch.object(
                self.testing.core, "_verify_url"
            ):
                receipt_path = self.testing._dist_create(
                    args,
                    target,
                    cli,
                    environment,
                    root / "testing-receipt.json",
                    reservation,
                )

            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "succeeded_testing")
            self.assertEqual(
                [stage["name"] for stage in receipt["stages"]],
                [name for name, _ in self.testing.DIST_UPGRADE_STAGE_CONTRACT],
            )
            self.assertTrue(all(stage["status"] == "succeeded" for stage in receipt["stages"]))
            self.assertEqual(receipt["observations"]["prewrite"]["operation"], "testing_upgrade_pre")
            self.assertEqual(
                receipt["observations"]["published_candidate"]["operation"],
                "testing_upgrade_candidate",
            )
            self.assertEqual(receipt["observations"]["postwrite"]["operation"], "testing_upgrade_post")
            self.assertEqual(
                [code for _, code in writes],
                ["PACK_FAILED", "PUBLISH_INDETERMINATE", "DEPLOY_INDETERMINATE"],
            )
            deploy_commands = [command for command, code in writes if code == "DEPLOY_INDETERMINATE"]
            self.assertEqual(len(deploy_commands), 1)
            self.assertEqual(
                deploy_commands[0][deploy_commands[0].index("--testing-create-mode") + 1],
                "upgrade-execute",
            )

    def test_publish_ack_may_omit_deploy_version_but_rejects_mismatch(self):
        candidate = self.candidate(mode="dist", intent="upgrade")
        base = {
            "Message": "Package published successfully.",
            "PackageName": candidate["package_name"],
            "PackageVersion": candidate["version"],
            "SystemName": candidate["system_name"],
            "PersonalWorkspace": False,
            "AppType": "Web",
        }
        omitted = {
            "Result": "Success",
            "Code": "PublishCompleted",
            "Data": copy.deepcopy(base),
        }
        self.assertEqual(
            self.testing._validate_published_candidate(omitted, candidate),
            {"systemName": candidate["system_name"], "deployVersion": candidate["deploy_version"]},
        )
        exact = copy.deepcopy(omitted)
        exact["Data"]["DeployVersion"] = candidate["deploy_version"]
        self.assertEqual(
            self.testing._validate_published_candidate(exact, candidate),
            {"systemName": candidate["system_name"], "deployVersion": candidate["deploy_version"]},
        )
        wrong = copy.deepcopy(exact)
        wrong["Data"]["DeployVersion"] += 1
        with self.assertRaises(self.testing.TestingCommandError):
            self.testing._validate_published_candidate(wrong, candidate)

    def test_dist_upgrade_candidate_guard_mismatch_stops_before_deploy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = self.executable(root)
            source = root / "source"
            dist = source / "dist"
            dist.mkdir(parents=True)
            (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")
            (source / "uipath.json").write_text(
                json.dumps(
                    {
                        "clientId": CLIENT_ID,
                        "scope": "openid profile",
                        "baseUrl": "https://alpha.api.uipath.com",
                        "redirectUri": "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup",
                        "public": False,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            home = root / "home"
            (home / ".uipath").mkdir(parents=True)
            environment = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
            target = self.target(cli)
            args = self.args(
                cli,
                root,
                intent="upgrade",
                candidate_mode="dist",
                version="0.1.3",
                expected_current_version="0.1.2",
                expected_system_name=SYSTEM_NAME,
                expected_deploy_version=4,
                recovery_plan=None,
            )
            receipt_path = root / "testing-receipt.json"
            reservation = self.testing._reserve_receipt(receipt_path)
            runtime_workspace = root / "guard-workspace"
            runtime_config = runtime_workspace / self.core.APP_CONFIG_RELATIVE_PATH
            runtime_config.parent.mkdir(parents=True)
            runtime_config.write_text("{}\n", encoding="utf-8")
            runtime = {
                "manifest_hash": self.core._hash_bytes(b"runtime"),
                "runtime_workspace": str(runtime_workspace),
                "node_executable": "/exact/node",
                "runtime_cli": "/exact/runtime/uip",
                "runtime_app_config_sha256": self.core._hash_bytes(b"runtime-app-config"),
                "runtime_immutable_sha256": self.core._hash_bytes(b"runtime-immutable"),
            }
            prewrite = {
                "deploymentId": DEPLOYMENT_ID,
                "systemName": None,
                "deployVersion": None,
                "currentVersion": "0.1.2",
                "routeName": "aura-vdp-mockup",
                "version": "0.1.3",
                "appName": "Aura VDP Template Mockup",
                "appUrl": "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup",
                "operation": "testing_upgrade_pre",
            }
            writes = []

            def fake_write(command, cwd, env, code):
                writes.append(code)
                if code == "PUBLISH_INDETERMINATE":
                    return {
                        "Result": "Success",
                        "Code": "PublishCompleted",
                        "Data": {
                            "Message": "Package published successfully.",
                            "PackageName": "aura-vdp-template-mockup",
                            "PackageVersion": "0.1.3",
                            "SystemName": SYSTEM_NAME,
                            "PersonalWorkspace": False,
                            "AppType": "Web",
                        },
                    }
                if code == "DEPLOY_INDETERMINATE":
                    self.fail("candidate mismatch must stop before deploy")
                return {"Result": "Success"}

            with mock.patch.object(
                self.testing, "EXPECTED_CLI_SHA256", target["cli_executable_sha256"]
            ), mock.patch.object(
                self.testing,
                "_resolve_node",
                return_value={
                    "executable": "/usr/local/bin/node",
                    "executable_sha256": self.testing.SUPPORTED_NODE_RUNTIMES["24.13.0"],
                    "version": "24.13.0",
                },
            ), mock.patch.object(
                self.testing, "_audit_tracked_source"
            ), mock.patch.object(
                self.testing,
                "_git_state",
                return_value=(SOURCE_SHA, self.core._hash_bytes(b"dirty"), SOURCE_SHA),
            ), mock.patch.object(
                self.testing, "_validate_cli"
            ), mock.patch.object(
                self.testing.core,
                "_package_evidence",
                return_value=(
                    self.core._hash_bytes(b"package-content"),
                    self.core._hash_bytes(b"package-file"),
                ),
            ), mock.patch.object(
                self.testing, "_audit_package_archive"
            ), mock.patch.object(
                self.testing, "_prepare_create_guard_runtime", return_value=runtime
            ), mock.patch.object(
                self.testing, "_revalidate_dist_barrier"
            ), mock.patch.object(
                self.testing, "_run_read", return_value="{}"
            ), mock.patch.object(
                self.testing,
                "_validate_upgrade_guard_output",
                side_effect=[prewrite, self.testing.TestingCommandError("candidate mismatch")],
            ), mock.patch.object(
                self.testing, "_run_write", side_effect=fake_write
            ), mock.patch.object(
                self.testing.core, "_bind_app_config"
            ):
                with self.assertRaises(self.testing.TestingCommandError):
                    self.testing._dist_create(
                        args,
                        target,
                        cli,
                        environment,
                        receipt_path,
                        reservation,
                    )
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "published_not_deployed")
            self.assertIsNone(receipt["observations"]["published_candidate"])
            self.assertEqual(writes, ["PACK_FAILED", "PUBLISH_INDETERMINATE"])

    def test_publish_recovery_reuses_exact_candidate_without_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self.publish_recovery_fixture(root)
            candidate = fixture["source_receipt"]["candidate"]

            def observation(operation, current):
                message = {
                    "testing_upgrade_candidate": "Testing upgrade candidate verified; no mutation performed.",
                    "testing_upgrade_execute": "Testing upgrade completed.",
                    "testing_upgrade_post": "Testing upgrade post-state verified.",
                }[operation]
                return {
                    "Result": "Success",
                    "Code": "DeployCompleted",
                    "Data": {
                        "Message": message,
                        "DeploymentId": candidate["deployment_id"],
                        "SystemName": candidate["system_name"],
                        "DeployVersion": candidate["deploy_version"],
                        "CurrentVersion": current,
                        "RouteName": candidate["path_name"],
                        "Version": candidate["version"],
                        "AppName": candidate["app_name"],
                        "AppUrl": "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup",
                        "Operation": operation,
                    },
                }

            reads = [
                json.dumps(observation("testing_upgrade_candidate", candidate["current_version"])),
                json.dumps(observation("testing_upgrade_post", candidate["version"])),
            ]
            writes = []

            def deploy(command, cwd, env, code):
                writes.append((copy.deepcopy(command), code))
                document = json.loads(fixture["runtime_config"].read_text(encoding="utf-8"))
                document["appUrl"] = "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup"
                document["deployedAt"] = "2026-08-06T03:40:00Z"
                self.core._atomic_write_json(fixture["runtime_config"], document)
                return observation("testing_upgrade_execute", candidate["version"])

            receipt_path = root / "publish-recovery-receipt.json"
            reservation = self.testing._reserve_receipt(receipt_path)
            with mock.patch.object(
                self.testing, "EXPECTED_CLI_SHA256", fixture["target"]["cli_executable_sha256"]
            ), mock.patch.object(
                self.testing, "_validate_cli"
            ), mock.patch.object(
                self.testing, "_revalidate_create_runtime_immutable"
            ), mock.patch.object(
                self.testing, "_revalidate_publish_recovery_barrier"
            ), mock.patch.object(
                self.testing, "_run_read", side_effect=reads
            ), mock.patch.object(
                self.testing, "_run_write", side_effect=deploy
            ), mock.patch.object(
                self.testing.core, "_verify_url"
            ):
                result = self.testing._published_recovery_upgrade(
                    fixture["args"],
                    fixture["target"],
                    fixture["cli"],
                    fixture["environment"],
                    receipt_path,
                    reservation,
                )
            receipt = json.loads(result.read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "succeeded_testing")
            self.assertEqual(receipt["candidate"]["mode"], "published-recovery")
            self.assertEqual(receipt["helper_sha256"], receipt["candidate"]["helper_sha256"])
            self.assertNotEqual(
                receipt["helper_sha256"],
                fixture["source_receipt"]["helper_sha256"],
            )
            self.assertEqual(
                receipt["recovery_source"]["failed_helper_sha256"],
                fixture["source_receipt"]["helper_sha256"],
            )
            self.assertEqual(len(writes), 1)
            self.assertEqual(writes[0][1], "DEPLOY_INDETERMINATE")
            self.assertNotIn("publish", writes[0][0])
            self.assertEqual(
                writes[0][0][writes[0][0].index("--testing-create-mode") + 1],
                "upgrade-execute",
            )
            self.assertFalse(any(item == "--path-name" for item in writes[0][0][writes[0][0].index("--testing-create-mode") + 2 :]))
            self.assertTrue(fixture["original_claim_path"].is_file())
            self.assertTrue(Path(receipt["execution_claim"]["path"]).is_file())
            self.assertFalse(receipt["execution_claim"]["released"])
            self.assertEqual(
                receipt["observations"]["published_candidate"]["operation"],
                "testing_upgrade_candidate",
            )
            schema = json.loads(RECEIPT_SCHEMA.read_text(encoding="utf-8"))
            validator = Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            )
            self.assertEqual(list(validator.iter_errors(receipt)), [])

    def test_publish_recovery_indeterminate_deploy_retains_both_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self.publish_recovery_fixture(root)
            candidate = fixture["source_receipt"]["candidate"]
            candidate_guard = json.dumps(
                {
                    "Result": "Success",
                    "Code": "DeployCompleted",
                    "Data": {
                        "Message": "Testing upgrade candidate verified; no mutation performed.",
                        "DeploymentId": candidate["deployment_id"],
                        "SystemName": candidate["system_name"],
                        "DeployVersion": candidate["deploy_version"],
                        "CurrentVersion": candidate["current_version"],
                        "RouteName": candidate["path_name"],
                        "Version": candidate["version"],
                        "AppName": candidate["app_name"],
                        "AppUrl": "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup",
                        "Operation": "testing_upgrade_candidate",
                    },
                }
            )
            receipt_path = root / "publish-recovery-indeterminate-receipt.json"
            reservation = self.testing._reserve_receipt(receipt_path)
            with mock.patch.object(
                self.testing,
                "EXPECTED_CLI_SHA256",
                fixture["target"]["cli_executable_sha256"],
            ), mock.patch.object(
                self.testing,
                "_validate_cli",
            ), mock.patch.object(
                self.testing,
                "_revalidate_create_runtime_immutable",
            ), mock.patch.object(
                self.testing,
                "_revalidate_publish_recovery_barrier",
            ), mock.patch.object(
                self.testing,
                "_run_read",
                return_value=candidate_guard,
            ) as read, mock.patch.object(
                self.testing,
                "_run_write",
                side_effect=KeyboardInterrupt(),
            ) as write:
                with self.assertRaises(KeyboardInterrupt):
                    self.testing._published_recovery_upgrade(
                        fixture["args"],
                        fixture["target"],
                        fixture["cli"],
                        fixture["environment"],
                        receipt_path,
                        reservation,
                    )
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "deploy_indeterminate")
            self.assertTrue(receipt["external_write_started"])
            self.assertTrue(fixture["original_claim_path"].is_file())
            self.assertTrue(Path(receipt["execution_claim"]["path"]).is_file())
            self.assertFalse(receipt["execution_claim"]["released"])
            read.assert_called_once()
            write.assert_called_once()

    def test_publish_recovery_tampered_runtime_never_invokes_remote_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self.publish_recovery_fixture(root)
            receipt_path = root / "publish-recovery-tamper-receipt.json"
            reservation = self.testing._reserve_receipt(receipt_path)
            with mock.patch.object(
                self.testing,
                "EXPECTED_CLI_SHA256",
                fixture["target"]["cli_executable_sha256"],
            ), mock.patch.object(
                self.testing,
                "_validate_cli",
            ), mock.patch.object(
                self.testing,
                "_revalidate_create_runtime_immutable",
            ), mock.patch.object(
                self.testing,
                "_revalidate_publish_recovery_barrier",
                side_effect=SystemExit("runtime changed"),
            ) as barrier, mock.patch.object(
                self.testing,
                "_run_read",
            ) as read, mock.patch.object(
                self.testing,
                "_run_write",
            ) as write:
                with self.assertRaisesRegex(SystemExit, "runtime changed"):
                    self.testing._published_recovery_upgrade(
                        fixture["args"],
                        fixture["target"],
                        fixture["cli"],
                        fixture["environment"],
                        receipt_path,
                        reservation,
                    )
            barrier.assert_called_once()
            read.assert_not_called()
            write.assert_not_called()
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "failed_prewrite")
            self.assertTrue(receipt["execution_claim"]["released"])
            self.assertTrue(fixture["original_claim_path"].is_file())

    def test_publish_recovery_rejects_symlinked_runtime_workspace_before_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self.publish_recovery_fixture(root)
            runtime_workspace = fixture["runtime_config"].parents[1]
            displaced = root / "displaced-runtime-workspace"
            runtime_workspace.rename(displaced)
            runtime_workspace.symlink_to(displaced, target_is_directory=True)
            receipt_path = root / "publish-recovery-symlink-receipt.json"
            reservation = self.testing._reserve_receipt(receipt_path)
            with mock.patch.object(
                self.testing,
                "EXPECTED_CLI_SHA256",
                fixture["target"]["cli_executable_sha256"],
            ), mock.patch.object(
                self.testing,
                "_revalidate_create_runtime_immutable",
            ), mock.patch.object(
                self.testing,
                "_run_read",
            ) as read, mock.patch.object(
                self.testing,
                "_run_write",
            ) as write:
                with self.assertRaisesRegex(SystemExit, "real directory"):
                    self.testing._published_recovery_upgrade(
                        fixture["args"],
                        fixture["target"],
                        fixture["cli"],
                        fixture["environment"],
                        receipt_path,
                        reservation,
                    )
            read.assert_not_called()
            write.assert_not_called()
            self.assertFalse(receipt_path.exists())
            self.assertTrue(fixture["original_claim_path"].is_file())

    def test_publish_recovery_candidate_mismatch_never_deploys_and_releases_transition(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self.publish_recovery_fixture(root)
            receipt_path = root / "publish-recovery-receipt.json"
            reservation = self.testing._reserve_receipt(receipt_path)
            with mock.patch.object(
                self.testing, "EXPECTED_CLI_SHA256", fixture["target"]["cli_executable_sha256"]
            ), mock.patch.object(
                self.testing, "_validate_cli"
            ), mock.patch.object(
                self.testing, "_revalidate_create_runtime_immutable"
            ), mock.patch.object(
                self.testing, "_revalidate_publish_recovery_barrier"
            ), mock.patch.object(
                self.testing, "_run_read", side_effect=self.testing.TestingCommandError("mismatch")
            ), mock.patch.object(
                self.testing, "_run_write"
            ) as write:
                with self.assertRaises(self.testing.TestingCommandError):
                    self.testing._published_recovery_upgrade(
                        fixture["args"], fixture["target"], fixture["cli"],
                        fixture["environment"], receipt_path, reservation,
                    )
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "failed_prewrite")
            self.assertTrue(receipt["execution_claim"]["released"])
            self.assertTrue(fixture["original_claim_path"].is_file())
            write.assert_not_called()

    def test_publish_recovery_transition_is_atomic_and_non_replayable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self.publish_recovery_fixture(root)
            candidate = copy.deepcopy(fixture["source_receipt"]["candidate"])
            candidate["mode"] = "published-recovery"
            reservation = self.testing._reserve_receipt(root / "recovery.json")
            first_path, _ = self.testing._create_publish_recovery_transition_claim(
                fixture["source_path"], fixture["source_receipt"], candidate, reservation
            )
            self.assertEqual(
                first_path.name,
                f"{fixture['source_receipt']['execution_claim']['key'].removeprefix('sha256:')}.publish-recovery.json",
            )
            with self.assertRaisesRegex(SystemExit, "already exists"):
                self.testing._create_publish_recovery_transition_claim(
                    fixture["source_path"], fixture["source_receipt"], candidate, reservation
                )
            self.assertTrue(first_path.is_file())
            self.assertTrue(fixture["original_claim_path"].is_file())

    def test_publish_recovery_requires_exact_retained_six_field_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self.publish_recovery_fixture(root)
            candidate = fixture["source_receipt"]["candidate"]
            before, document, bound = self.testing._publish_recovery_bound_config(
                fixture["runtime_config"],
                candidate,
                fixture["target"],
            )
            self.assertEqual(before, candidate["runtime_app_config_digest"])
            self.assertEqual(bound, before)
            self.assertEqual(
                set(document),
                {
                    "appName", "displayName", "appVersion", "appUrl",
                    "appType", "personalWorkspace",
                },
            )
            mutated = copy.deepcopy(document)
            mutated["systemName"] = candidate["system_name"]
            self.core._atomic_write_json(fixture["runtime_config"], mutated)
            with self.assertRaisesRegex(SystemExit, "exact retained guard state"):
                self.testing._publish_recovery_bound_config(
                    fixture["runtime_config"],
                    candidate,
                    fixture["target"],
                )

    def test_publish_recovery_accepts_exact_crash_receipt_with_running_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self.publish_recovery_fixture(root)
            source = copy.deepcopy(fixture["source_receipt"])
            publish = source["stages"][8]
            publish["status"] = "running"
            publish.pop("finished_at")
            publish.pop("error_code")
            publish.pop("recovery")
            source["receipt_hash"] = self.core._document_hash(source, "receipt_hash")
            self.core._atomic_write_json(fixture["source_path"], source)
            with mock.patch.object(
                self.testing,
                "EXPECTED_CLI_SHA256",
                fixture["target"]["cli_executable_sha256"],
            ):
                loaded = self.testing._load_publish_recovery_receipt(
                    fixture["source_path"],
                    expected_receipt_hash=source["receipt_hash"],
                    expected_file_sha256=self.core._hash_file(
                        fixture["source_path"],
                        "running publish receipt",
                    ),
                )
            self.assertEqual(loaded["stages"][8]["status"], "running")

    def test_create_execute_rechecks_occupied_route_and_cannot_stock_upgrade(self):
        source = "\n".join(old for old, _ in self.testing.CREATE_GUARD_PATCH_EDITS).encode()
        with mock.patch.object(
            self.testing.recovery,
            "EXPECTED_CODEDAPP_TOOL_SHA256",
            self.core._hash_bytes(source),
        ):
            patched = self.testing._patched_create_guard_bytes(source).decode()
            occupied = patched.index('if (deployedApp && !testingUpgradeMode) {\n      throw new Error("TESTING_CREATE_DEPLOYMENT_EXISTS")')
        verify_only = patched.index('if (testingCreateMode === "verify")')
        mutation = patched.index("let operationResult", occupied)
        self.assertLess(occupied, verify_only)
        self.assertLess(occupied, mutation)
        with tempfile.TemporaryDirectory() as tmp:
            cli = self.executable(Path(tmp))
            target = self.target(cli)
            runtime = {
                "node_executable": "/exact/node",
                "runtime_cli": "/exact/runtime/uip",
            }
            command = self.testing._create_execute_command(
                runtime, target, self.candidate(mode="dist", intent="create")
            )
        self.assertEqual(command[command.index("--testing-create-mode") + 1], "execute")
        self.assertEqual(command.count("--path-name"), 1)
        self.assertNotIn("--upgrade", command)

    def test_dist_upgrade_guard_is_exact_and_omits_route_from_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = self.executable(root)
            target = self.target(cli)
            candidate = self.candidate(mode="dist", intent="upgrade")
            self.testing._validate_candidate_record(candidate)
            guard_config = self.testing._dist_guard_config(
                candidate["package_name"],
                candidate["app_name"],
                candidate["version"],
                target,
                candidate["path_name"],
                candidate["intent"],
            )
            self.assertEqual(
                guard_config["appUrl"],
                "https://agenticgtm.alpha.uipath.host/aura-vdp-mockup",
            )
            self.assertNotIn("deploymentId", guard_config)
            for invalid_version in (
                "0.1.1",
                "0.1.1+build.1",
                "0.1.1-rc.1",
                "0.1.0",
            ):
                stale = copy.deepcopy(candidate)
                stale["version"] = invalid_version
                with self.subTest(invalid_version=invalid_version), self.assertRaisesRegex(
                    SystemExit, "strictly newer"
                ):
                    self.testing._validate_candidate_record(stale)
            promoted = copy.deepcopy(candidate)
            promoted["current_version"] = "0.1.2-rc.1"
            promoted["version"] = "0.1.2"
            self.testing._validate_candidate_record(promoted)
            runtime = {
                "node_executable": "/usr/local/bin/node",
                "runtime_cli": "/evidence/runtime/node_modules/@uipath/cli/dist/index.js",
            }
            pre = self.testing._upgrade_guard_command(
                runtime, target, candidate, "upgrade-pre"
            )
            self.assertIn("--testing-expected-deployment-id", pre)
            self.assertIn("--testing-expected-current-version", pre)
            self.assertIn("--testing-expected-route-name", pre)
            self.assertNotIn("--testing-expected-system-name", pre)
            published = {"systemName": SYSTEM_NAME, "deployVersion": 4}
            execute = self.testing._upgrade_guard_command(
                runtime,
                target,
                candidate,
                "upgrade-execute",
                published=published,
            )
            self.assertEqual(
                execute[execute.index("--testing-create-mode") + 1],
                "upgrade-execute",
            )
            self.assertEqual(
                execute[execute.index("--testing-expected-system-name") + 1],
                SYSTEM_NAME,
            )
            reconciled = copy.deepcopy(candidate)
            reconciled["mode"] = "reconciled"
            reconciled["dist_digest"] = None
            reconciled["recovery_plan_hash"] = self.core._hash_bytes(b"recovery-plan")
            self.assertEqual(
                self.testing._claim_key(target, candidate),
                self.testing._claim_key(target, reconciled),
            )
        source = "\n".join(old for old, _ in self.testing.CREATE_GUARD_PATCH_EDITS).encode()
        with mock.patch.object(
            self.testing.recovery,
            "EXPECTED_CODEDAPP_TOOL_SHA256",
            self.core._hash_bytes(source),
        ):
            patched = self.testing._patched_create_guard_bytes(source).decode()
        self.assertIn(
            "deployedApp.title !== appName && deployedApp.title !== displayTitle",
            patched,
        )
        self.assertNotIn("if (deployedApp.title !== displayTitle)", patched)
        self.assertLess(
            patched.index('testingCreateMode === "upgrade-pre"'),
            patched.index("getPublishedAppWithRetry(appName, envConfig, options.version"),
        )
        self.assertIn(
            "publishedApp.deployVersion, testingUpgradeMode ? undefined : options.pathName ? routingName : undefined",
            patched,
        )

    def test_dist_external_writes_have_last_moment_barriers_and_post_guard_recheck(self):
        helper = TESTING_SCRIPT.read_text(encoding="utf-8")
        dist_body = helper[
            helper.index("def _dist_create(") : helper.index("def _match_recovery_inputs(")
        ]
        publish_start = dist_body.index(
            '_start_stage(receipt, receipt_path, "publish", external_write=True)'
        )
        publish_finish = dist_body.index("_finish_stage(", publish_start)
        publish_segment = dist_body[publish_start:publish_finish]
        self.assertLess(
            publish_segment.index("_revalidate_dist_barrier"),
            publish_segment.index("_run_write"),
        )
        deploy_start = dist_body.index(
            '_start_stage(receipt, receipt_path, "deploy", external_write=True)'
        )
        deploy_finish = dist_body.index("_finish_stage(", deploy_start)
        deploy_segment = dist_body[deploy_start:deploy_finish]
        self.assertLess(
            deploy_segment.index("_revalidate_dist_barrier"),
            deploy_segment.index("_run_write"),
        )
        post_start = dist_body.index("post_guard_stage = (")
        post_finish = dist_body.index("_finish_stage(", post_start)
        post_segment = dist_body[post_start:post_finish]
        self.assertLess(
            post_segment.index("_revalidate_create_runtime_immutable"),
            post_segment.index("_run_read"),
        )

    def test_create_execute_and_post_outputs_bind_exact_remote_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            cli = self.executable(Path(tmp))
            target = self.target(cli)
            candidate = self.candidate(mode="dist", intent="create")
            execute = {
                "Result": "Success",
                "Code": "DeployCompleted",
                "Data": {
                    "Message": "Testing create completed.",
                    "DeploymentId": DEPLOYMENT_ID,
                    "SystemName": SYSTEM_NAME,
                    "DeployVersion": 3,
                    "Version": candidate["version"],
                    "AppName": candidate["app_name"],
                    "AppUrl": self.testing._route_url(target, candidate["path_name"]),
                    "Operation": "deploy",
                },
            }
            deployed = self.testing._validate_create_execute_output(
                execute, target, candidate
            )
            post = {
                "Result": "Success",
                "Code": "DeployCompleted",
                "Data": {
                    "Message": "Testing create post-state verified.",
                    "DeploymentId": DEPLOYMENT_ID,
                    "SystemName": SYSTEM_NAME,
                    "DeployVersion": 3,
                    "CurrentVersion": candidate["version"],
                    "RouteName": candidate["path_name"],
                    "Version": candidate["version"],
                    "AppName": candidate["app_name"],
                    "AppUrl": self.testing._route_url(target, candidate["path_name"]),
                    "Operation": "testing_create_post",
                },
            }
            observed = self.testing._validate_create_post_output(
                json.dumps(post), target, candidate, deployed
            )
            self.assertEqual(observed["deploymentId"], DEPLOYMENT_ID)
            self.assertEqual(observed["systemName"], SYSTEM_NAME)
            for field, value in (
                ("DeploymentId", FOLDER_ID),
                ("SystemName", "ID" + "f" * 32),
                ("RouteName", "other-route"),
                ("CurrentVersion", "0.1.1"),
            ):
                changed = copy.deepcopy(post)
                changed["Data"][field] = value
                with self.subTest(field=field), self.assertRaises(SystemExit):
                    self.testing._validate_create_post_output(
                        json.dumps(changed), target, candidate, deployed
                    )

    def test_reconciled_explicit_authority_flags_all_bind_the_loaded_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = self.executable(root)
            (root / "source").mkdir()
            target = self.target(cli)
            plan, _ = self.recovery_plan(cli, root)
            baseline = self.args(
                cli,
                root,
                expected_recovery_plan_hash=plan["plan_hash"],
                expected_runtime_manifest_hash=plan["candidate"][
                    "recovery_runtime_manifest_hash"
                ],
            )
            self.testing._match_recovery_inputs(baseline, plan, target, cli)
            mutations = {
                "expected_recovery_plan_hash": self.core._hash_bytes(b"other-plan"),
                "expected_deployment_id": FOLDER_ID,
                "expected_system_name": "ID" + "f" * 32,
                "expected_current_version": "0.1.0",
                "expected_deploy_version": 4,
                "expected_runtime_manifest_hash": self.core._hash_bytes(
                    b"other-runtime"
                ),
            }
            for field, value in mutations.items():
                changed = copy.copy(baseline)
                setattr(changed, field, value)
                with self.subTest(field=field), self.assertRaises(SystemExit):
                    self.testing._match_recovery_inputs(changed, plan, target, cli)

    def test_reconciled_lane_rejects_prior_recovery_receipt_and_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = self.executable(root)
            plan, _ = self.recovery_plan(cli, root)
            plan_path = root / "recovery-plan.json"
            plan_path.write_text("{}\n", encoding="utf-8")
            home = root / "home"
            (home / ".uipath").mkdir(parents=True)
            environment = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
            prior_receipt = self.recovery._receipt_path(plan_path)
            prior_receipt.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "already has a receipt"):
                self.testing._assert_no_prior_recovery_execution(
                    plan_path, plan, environment
                )
            prior_receipt.unlink()
            recovery_claim = (
                home
                / ".uipath"
                / "uipcodedappdeploy-recovery-claims"
                / f"{plan['upgrade_guard']['local_execution_claim_key'].removeprefix('sha256:')}.json"
            )
            recovery_claim.parent.mkdir(parents=True)
            recovery_claim.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "retained recovery claim"):
                self.testing._assert_no_prior_recovery_execution(
                    plan_path, plan, environment
                )

    def test_dist_barrier_revalidates_cli_dist_config_package_and_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = self.executable(root)
            target = self.target(cli)
            dist = root / "copied-dist"
            dist.mkdir()
            (dist / "index.html").write_text("fixture", encoding="utf-8")
            config = root / "uipath.json"
            config.write_text("{}\n", encoding="utf-8")
            package = root / "candidate.nupkg"
            package.write_bytes(b"package")
            candidate = self.candidate(mode="dist", intent="create")
            candidate["dist_digest"] = self.testing._directory_digest(dist)
            candidate["uipath_config_digest"] = self.core._hash_file(
                config, "fixture config"
            )
            candidate["package_content_digest"] = self.core._hash_bytes(
                b"package-content"
            )
            candidate["package_file_digest"] = self.core._hash_bytes(b"package-file")
            inputs = {
                "target": target,
                "node_runtime": {
                    "executable": "/usr/local/bin/node",
                    "executable_sha256": self.testing.SUPPORTED_NODE_RUNTIMES[
                        "24.13.0"
                    ],
                    "version": "24.13.0",
                },
                "workspace": root,
                "copied_dist": dist,
                "config_copy": config,
                "package_path": package,
                "runtime": {},
                "candidate": candidate,
                "environment": {"HOME": str(root), "PATH": "/usr/bin:/bin"},
            }
            package_evidence = (
                candidate["package_content_digest"],
                candidate["package_file_digest"],
            )
            with mock.patch.object(self.testing, "_validate_cli"), mock.patch.object(
                self.testing.core, "_package_evidence", return_value=package_evidence
            ), mock.patch.object(self.testing, "_revalidate_create_runtime"):
                self.testing._revalidate_dist_barrier(**inputs)
            dist.joinpath("index.html").write_text("changed", encoding="utf-8")
            with mock.patch.object(self.testing, "_validate_cli"), mock.patch.object(
                self.testing.core, "_package_evidence", return_value=package_evidence
            ), mock.patch.object(self.testing, "_revalidate_create_runtime"):
                with self.assertRaisesRegex(SystemExit, "dist changed"):
                    self.testing._revalidate_dist_barrier(**inputs)
            candidate["dist_digest"] = self.testing._directory_digest(dist)
            config.write_text('{"changed":true}\n', encoding="utf-8")
            with mock.patch.object(self.testing, "_validate_cli"), mock.patch.object(
                self.testing.core, "_package_evidence", return_value=package_evidence
            ), mock.patch.object(self.testing, "_revalidate_create_runtime"):
                with self.assertRaisesRegex(SystemExit, "uipath.json changed"):
                    self.testing._revalidate_dist_barrier(**inputs)
            candidate["uipath_config_digest"] = self.core._hash_file(config, "fixture")
            with mock.patch.object(self.testing, "_validate_cli"), mock.patch.object(
                self.testing.core,
                "_package_evidence",
                return_value=(self.core._hash_bytes(b"other"), package_evidence[1]),
            ), mock.patch.object(self.testing, "_revalidate_create_runtime"):
                with self.assertRaisesRegex(SystemExit, "package changed"):
                    self.testing._revalidate_dist_barrier(**inputs)
            with mock.patch.object(
                self.testing, "_validate_cli", side_effect=SystemExit("CLI or Node drift")
            ), self.assertRaisesRegex(SystemExit, "CLI or Node drift"):
                self.testing._revalidate_dist_barrier(**inputs)
            with mock.patch.object(self.testing, "_validate_cli"), mock.patch.object(
                self.testing.core, "_package_evidence", return_value=package_evidence
            ), mock.patch.object(
                self.testing,
                "_revalidate_create_runtime",
                side_effect=SystemExit("runtime drift"),
            ), self.assertRaisesRegex(SystemExit, "runtime drift"):
                self.testing._revalidate_dist_barrier(**inputs)

    def test_reconciled_barrier_revalidates_config_cli_and_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = self.executable(root)
            source = root / "source"
            source.mkdir()
            config = source / "uipath.json"
            config.write_text("{}\n", encoding="utf-8")
            candidate = self.candidate()
            candidate["uipath_config_digest"] = self.core._hash_file(config, "config")
            plan = {
                "project_root": str(source),
                "candidate": {"source_cli_executable": str(cli)},
            }
            context = {}
            environment = {"HOME": str(root), "PATH": "/usr/bin:/bin"}
            cli_digest = self.core._hash_file(cli, "fixture CLI")
            with mock.patch.object(
                self.testing, "EXPECTED_CLI_SHA256", cli_digest
            ), mock.patch.object(
                self.testing.recovery, "_revalidate_runtime_barrier"
            ), mock.patch.object(
                self.testing, "_revalidate_reconciled_immutable_runtime"
            ):
                self.testing._revalidate_reconciled_testing_barrier(
                    plan, context, candidate, environment
                )
            config.write_text('{"changed":true}\n', encoding="utf-8")
            with mock.patch.object(
                self.testing, "EXPECTED_CLI_SHA256", cli_digest
            ), mock.patch.object(
                self.testing.recovery, "_revalidate_runtime_barrier"
            ), mock.patch.object(
                self.testing, "_revalidate_reconciled_immutable_runtime"
            ):
                with self.assertRaisesRegex(SystemExit, "uipath.json changed"):
                    self.testing._revalidate_reconciled_testing_barrier(
                        plan, context, candidate, environment
                    )
            candidate["uipath_config_digest"] = self.core._hash_file(config, "config")
            cli.write_bytes(b"mutated-cli")
            with mock.patch.object(
                self.testing, "EXPECTED_CLI_SHA256", cli_digest
            ), mock.patch.object(
                self.testing.recovery, "_revalidate_runtime_barrier"
            ), mock.patch.object(
                self.testing, "_revalidate_reconciled_immutable_runtime"
            ):
                with self.assertRaisesRegex(SystemExit, "supported 1.198.0 build"):
                    self.testing._revalidate_reconciled_testing_barrier(
                        plan, context, candidate, environment
                    )
            mutated_cli_digest = self.core._hash_file(cli, "mutated CLI")
            with mock.patch.object(
                self.testing, "EXPECTED_CLI_SHA256", mutated_cli_digest
            ), mock.patch.object(
                self.testing.recovery,
                "_revalidate_runtime_barrier",
                side_effect=SystemExit("runtime or Node drift"),
            ), mock.patch.object(
                self.testing, "_revalidate_reconciled_immutable_runtime"
            ), self.assertRaisesRegex(SystemExit, "runtime or Node drift"):
                self.testing._revalidate_reconciled_testing_barrier(
                    plan, context, candidate, environment
                )

    def test_immutable_runtime_digest_excludes_only_declared_app_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runtime"
            workspace = root / "workspace"
            config = workspace / self.core.APP_CONFIG_RELATIVE_PATH
            config.parent.mkdir(parents=True)
            config.write_text('{"appVersion":"0.1.1"}\n', encoding="utf-8")
            runtime_file = root / "guarded-cli.js"
            runtime_file.write_text("immutable-v1\n", encoding="utf-8")
            first = self.testing._immutable_runtime_digest(root, [config])
            config.write_text('{"appVersion":"0.1.2"}\n', encoding="utf-8")
            self.assertEqual(
                self.testing._immutable_runtime_digest(root, [config]), first
            )
            runtime_file.write_text("immutable-v2\n", encoding="utf-8")
            self.assertNotEqual(
                self.testing._immutable_runtime_digest(root, [config]), first
            )
            outside = Path(tmp) / "outside.json"
            outside.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "outside the runtime"):
                self.testing._immutable_runtime_digest(root, [outside])

    def test_cli_and_node_build_identity_is_byte_bound_not_self_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = self.executable(root)
            with mock.patch.object(self.testing.subprocess, "run") as run, self.assertRaisesRegex(
                SystemExit, "not the supported UiPath CLI"
            ):
                self.testing._resolve_cli(str(cli))
            run.assert_not_called()
            fixture_digest = self.core._hash_file(cli, "fixture CLI")
            manifest_digest = self.core._hash_file(
                cli.parents[1] / "package.json", "fixture CLI manifest"
            )
            with mock.patch.object(
                self.testing, "EXPECTED_CLI_SHA256", fixture_digest
            ), mock.patch.object(
                self.testing, "EXPECTED_CLI_MANIFEST_SHA256", manifest_digest
            ):
                self.assertEqual(self.testing._resolve_cli(str(cli)), cli)
            package_path = cli.parents[1] / "package.json"
            package = json.loads(package_path.read_text(encoding="utf-8"))
            package["gitHead"] = "f" * 40
            package_path.write_text(json.dumps(package), encoding="utf-8")
            mutated_manifest_digest = self.core._hash_file(
                package_path, "mutated fixture CLI manifest"
            )
            with mock.patch.object(
                self.testing, "EXPECTED_CLI_SHA256", fixture_digest
            ), mock.patch.object(
                self.testing,
                "EXPECTED_CLI_MANIFEST_SHA256",
                mutated_manifest_digest,
            ), self.assertRaisesRegex(SystemExit, "build identity"):
                self.testing._resolve_cli(str(cli))

            node = root / "node-fixture"
            node.write_bytes(b"node-runtime")
            node.chmod(0o755)
            node_digest = self.core._hash_file(node, "node fixture")
            completed = subprocess.CompletedProcess(
                [str(node), "--version"], 0, "v24.13.0\n", ""
            )
            with mock.patch.dict(
                self.testing.SUPPORTED_NODE_RUNTIMES,
                {"24.13.0": node_digest},
                clear=True,
            ), mock.patch.object(self.testing.subprocess, "run", return_value=completed):
                observed = self.testing._resolve_node(str(node), "24.13.0")
            self.assertEqual(observed["executable_sha256"], node_digest)
            node.write_bytes(b"changed-node-runtime")
            with mock.patch.dict(
                self.testing.SUPPORTED_NODE_RUNTIMES,
                {"24.13.0": node_digest},
                clear=True,
            ), mock.patch.object(self.testing.subprocess, "run") as run, self.assertRaisesRegex(
                SystemExit, "bytes do not match"
            ):
                self.testing._resolve_node(str(node), "24.13.0")
            run.assert_not_called()

    def test_cli_commands_use_exact_node_cli_pair_and_profile_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = self.executable(root)
            target = self.target(cli)
            node_runtime = {
                "executable": "/exact/node",
                "executable_sha256": self.core._hash_bytes(b"node"),
                "version": "24.13.0",
            }
            status = json.dumps(
                {
                    "status": "authenticated",
                    "organizationId": ORG_ID,
                    "tenantId": TENANT_ID,
                    "organizationName": "agenticgtm",
                    "tenantName": "Dev",
                    "baseUrl": "https://alpha.uipath.com",
                }
            )
            with mock.patch.object(
                self.testing.core, "_hash_file", side_effect=[
                    target["cli_executable_sha256"],
                    node_runtime["executable_sha256"],
                ]
            ), mock.patch.object(
                self.testing, "_run_read", side_effect=["1.198.0\n", status]
            ) as run:
                self.testing._validate_cli(
                    target, root, {"HOME": str(root)}, node_runtime
                )
            self.assertEqual(run.call_args_list[0].args[0][:2], ["/exact/node", str(cli)])
            self.assertEqual(run.call_args_list[1].args[0][:2], ["/exact/node", str(cli)])
            wrong = json.dumps(
                {
                    "status": "authenticated",
                    "organizationId": FOLDER_ID,
                    "tenantId": TENANT_ID,
                    "organizationName": "agenticgtm",
                    "tenantName": "Dev",
                    "baseUrl": "https://alpha.uipath.com",
                }
            )
            with mock.patch.object(
                self.testing.core, "_hash_file", side_effect=[
                    target["cli_executable_sha256"],
                    node_runtime["executable_sha256"],
                ]
            ), mock.patch.object(
                self.testing, "_run_read", side_effect=["1.198.0\n", wrong]
            ), self.assertRaisesRegex(SystemExit, "organization does not match"):
                self.testing._validate_cli(
                    target, root, {"HOME": str(root)}, node_runtime
                )

    def test_receipt_rejects_nested_secrets_candidate_mutation_and_invalid_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = self.executable(root)
            _, _, _, _, receipt = self.claim_and_receipt(root, cli)
            with mock.patch.object(
                self.testing,
                "EXPECTED_CLI_SHA256",
                receipt["target"]["cli_executable_sha256"],
            ):
                secret_key = copy.deepcopy(receipt)
                secret_key["observations"]["prewrite"] = {
                    "client_secret": "this-value-must-never-enter-the-receipt"
                }
                with self.assertRaisesRegex(SystemExit, "secret-bearing field"):
                    self.testing._validate_receipt(secret_key)
                bearer = copy.deepcopy(receipt)
                bearer["authorization"]["purpose"] = (
                    "Bea" + "rer " + "eyJ" + "abcdefghijk.abcdefghijk.abcdefghijk"
                )
                with self.assertRaisesRegex(SystemExit, "secret-like material"):
                    self.testing._validate_receipt(bearer)
                mutated_candidate = copy.deepcopy(receipt)
                mutated_candidate["candidate"]["version"] = "0.1.3"
                with self.assertRaises(SystemExit):
                    self.testing._validate_receipt(mutated_candidate)
                impossible = copy.deepcopy(receipt)
                impossible["status"] = "succeeded_testing"
                impossible["external_write_started"] = True
                with self.assertRaisesRegex(
                    SystemExit, "external-write state|incomplete stages"
                ):
                    self.testing._validate_receipt(impossible)

    def test_claim_release_is_rejected_in_progress_after_write_and_after_success(self):
        for state in ("in_progress", "deploy_indeterminate", "succeeded_testing"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                cli = self.executable(root)
                _, claim_path, claim, receipt_path, receipt = self.claim_and_receipt(
                    root, cli
                )
                receipt["status"] = state
                if state != "in_progress":
                    receipt["external_write_started"] = True
                    deploy = next(
                        stage for stage in receipt["stages"] if stage["name"] == "deploy"
                    )
                    deploy["status"] = "running" if state == "deploy_indeterminate" else "succeeded"
                    deploy["started_at"] = self.core._utc_now()
                with self.assertRaisesRegex(SystemExit, "only after a handled pre-write failure"):
                    self.testing._release_claim(
                        claim_path, claim, receipt, receipt_path
                    )
                self.assertTrue(claim_path.exists())

    def test_receipt_reservation_is_atomic_under_concurrent_callers(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt_path = Path(tmp) / "testing-receipt.json"
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(self.testing._reserve_receipt, receipt_path)
                    for _ in range(2)
                ]
            outcomes = []
            for future in futures:
                try:
                    outcomes.append(future.result())
                except BaseException as exc:
                    outcomes.append(exc)
            self.assertEqual(sum(isinstance(value, dict) for value in outcomes), 1)
            self.assertEqual(sum(isinstance(value, SystemExit) for value in outcomes), 1)
            self.assertTrue(
                receipt_path.with_name(
                    f".{receipt_path.name}.reservation.json"
                ).is_file()
            )

    def test_keyboard_interrupt_after_write_keeps_indeterminate_receipt_and_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt, claim_path, error, _, deploy, verify, _ = self.run_reconciled(
                Path(tmp), deploy_effect=KeyboardInterrupt()
            )
            self.assertIsInstance(error, KeyboardInterrupt)
            self.assertEqual(receipt["status"], "deploy_indeterminate")
            self.assertTrue(receipt["external_write_started"])
            self.assertTrue(claim_path.exists())
            deploy.assert_called_once()
            verify.assert_not_called()

    def test_source_and_cli_failure_secret_material_never_enters_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            tracked = source / "tracked.js"
            tracked.write_text(
                'const access_token = "this-is-a-sensitive-access-token";',
                encoding="utf-8",
            )
            listing = subprocess.CompletedProcess(
                ["git", "ls-files"], 0, b"tracked.js\0", b""
            )
            with mock.patch.object(
                self.testing.subprocess, "run", return_value=listing
            ), self.assertRaisesRegex(SystemExit, "secret audit failed"):
                self.testing._audit_tracked_source(source, source)
            secret = "Bea" + "rer abcdefghijklmnopqrstuvwxyz.1234567890"
            failure = subprocess.CalledProcessError(
                1,
                ["node", "uip", "codedapp", "publish"],
                output=secret,
                stderr=secret,
            )
            stderr = io.StringIO()
            with mock.patch.object(
                self.testing.subprocess, "run", side_effect=failure
            ), contextlib.redirect_stderr(stderr), self.assertRaises(
                self.testing.TestingCommandError
            ) as caught:
                self.testing._run_write(
                    ["node", "uip", "codedapp", "publish"],
                    root,
                    {"HOME": str(root)},
                    "PUBLISH_INDETERMINATE",
                )
            self.assertEqual(str(caught.exception), "PUBLISH_INDETERMINATE")
            self.assertNotIn(secret, stderr.getvalue())
            self.assertNotIn(secret, repr(caught.exception))

    def test_evidence_must_be_ignored_or_external_and_nonoverlapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            evidence = root / "evidence" / "receipt.json"
            evidence.parent.mkdir()
            not_ignored = subprocess.CompletedProcess(
                ["git", "check-ignore"], 1, "", ""
            )
            with mock.patch.object(
                self.testing.subprocess, "run", return_value=not_ignored
            ), self.assertRaisesRegex(SystemExit, "must be ignored"):
                self.testing._require_ignored_or_external(evidence, root)
            protected = root / "protected"
            protected.mkdir()
            with mock.patch.object(self.testing, "_require_ignored_or_external"):
                with self.assertRaisesRegex(SystemExit, "must not overlap"):
                    self.testing._validate_evidence_isolation(
                        protected / "receipt.json",
                        root,
                        [protected],
                        include_workspace=False,
                    )

    def test_preflight_failure_receipt_is_valid_and_never_claims_release_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = self.executable(root)
            reservation = self.testing._reserve_receipt(root / "receipt.json")
            receipt = self.testing._new_preflight_failure_receipt(
                self.args(cli, root),
                self.target(cli),
                reservation,
                "LOCAL_PREFLIGHT_FAILED",
            )
            with mock.patch.object(
                self.testing,
                "EXPECTED_CLI_SHA256",
                receipt["target"]["cli_executable_sha256"],
            ):
                self.testing._validate_receipt(receipt)
            self.assertEqual(receipt["attempt_phase"], "preflight")
            self.assertIsNone(receipt["candidate"])
            self.assertIsNone(receipt["execution_claim"])
            self.assertFalse(receipt["external_write_started"])
            self.assertFalse(receipt["policy"]["production_eligible"])
            self.assertEqual(
                receipt["verification"]["authentication_certification"],
                "pending_external_acceptance",
            )

    def test_safe_environment_is_allowlisted_and_rejects_release_injection(self):
        with tempfile.TemporaryDirectory() as tmp:
            observed = self.testing._safe_environment(
                {"HOME": tmp, "PATH": "/usr/bin:/bin", "TMPDIR": "/ignored"}
            )
            self.assertEqual(
                set(observed),
                {
                    "HOME", "PATH", "LANG", "LC_ALL", "TERM", "NO_COLOR",
                    "UIPATH_CLI_DISABLE_VERSION_SYNC", "UIPATH_TELEMETRY_DISABLED",
                },
            )
            for name in self.recovery.FORBIDDEN_RECOVERY_ENVIRONMENT:
                with self.subTest(name=name), self.assertRaises(SystemExit):
                    self.testing._safe_environment(
                        {"HOME": tmp, "PATH": "/bin", name: "injected"}
                    )


if __name__ == "__main__":
    unittest.main()
