#!/usr/bin/env python3
"""Governed deploy-only recovery for an already-published UiPath Coded App.

This helper is deliberately narrower than ``uipcodedappdeploy.py``. It exists
for one recovery shape: a package was published, an existing-app upgrade was
attempted with ``--path-name``, and the Apps service rejected the unchanged
route as non-unique. The recovery uses an isolated, hash-bound patch of the
exact CLI runtime. That patch requires an exact deployment match, blocks the
fresh-deploy branch, and omits ``routingName`` only from the guarded PATCH.

The script never packs, publishes, changes a version, or resumes an ambiguous
external write. Planning and execution are separate exact-hash operations.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import uipcodedappdeploy as core  # noqa: E402


PLAN_KIND = "uipcodedappdeploy.upgrade-recovery-plan"
PLAN_SCHEMA_VERSION = "1.2"
RECEIPT_KIND = "uipcodedappdeploy.upgrade-recovery-receipt"
RECEIPT_SCHEMA_VERSION = "1.2"
RECONCILIATION_KIND = "uipcodedappdeploy.remote-reconciliation"
RECONCILIATION_SCHEMA_VERSION = "1.0"
RUNTIME_MANIFEST_KIND = "uipcodedappdeploy.guarded-runtime"
RUNTIME_MANIFEST_SCHEMA_VERSION = "1.1"
PATCH_ALGORITHM = "uipath-codedapp-tool-1.198.0-exact-upgrade-v2"
EXPECTED_CODEDAPP_TOOL_VERSION = "1.198.0"
EXPECTED_CODEDAPP_TOOL_GIT_HEAD = "1fadf03d7a8dd102742571dff569fdac11808afb"
EXPECTED_CODEDAPP_TOOL_SHA256 = (
    "sha256:4338dc130199abd53bbe8b2ce831cf95bdababb206f0f5099a9b5c96408bf52b"
)
ISOLATED_WORKSPACE_RELATIVE = Path(
    "isolated/d01/d02/d03/d04/d05/d06/d07/d08/d09/d10/d11/d12/workspace"
)
FORBIDDEN_RECOVERY_ENVIRONMENT = (
    "NODE_OPTIONS",
    "NODE_PATH",
    "NODE_EXTRA_CA_CERTS",
    "NODE_TLS_REJECT_UNAUTHORIZED",
    "NODE_DEBUG",
    "NODE_DEBUG_NATIVE",
    "ELECTRON_RUN_AS_NODE",
    "PREBUILDS_ONLY",
    "DYLD_INSERT_LIBRARIES",
    "DYLD_LIBRARY_PATH",
    "LD_PRELOAD",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "OPENSSL_CONF",
    "OPENSSL_MODULES",
    "SSLKEYLOGFILE",
    "DEBUG",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
    "UIPATH_ACCESS_TOKEN",
    "UIPATH_BASE_URL",
    "UIPATH_URL",
    "UIPATH_ORG_ID",
    "UIPATH_TENANT_NAME",
    "UIPATH_FOLDER_KEY",
    "UIPATH_PROJECT_ID",
    "UIPATH_CLI_FEEDBACK_ENDPOINT",
)
RECOVERY_ENVIRONMENT_PRESERVE = ("HOME",)
RECOVERY_ENVIRONMENT_OVERRIDES = {
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    "LANG": "C",
    "LC_ALL": "C",
    "TERM": "dumb",
    "NO_COLOR": "1",
    "UIPATH_CLI_DISABLE_VERSION_SYNC": "1",
    "UIPATH_TELEMETRY_DISABLED": "true",
}

RECOVERY_FLAGS = (
    "--expected-deployment-id",
    "--expected-system-name",
    "--expected-deploy-version",
    "--expected-current-version",
    "--expected-route-name",
)

PATCH_EDITS = (
    (
        """async function executeDeploy(options) {
  const logger3 = options.logger ?? {""",
        """async function executeDeploy(options) {
  const recoveryExpectedDeploymentId = options.expectedDeploymentId;
  const recoveryExpectedSystemName = options.expectedSystemName;
  const recoveryExpectedDeployVersion = options.expectedDeployVersion;
  const recoveryExpectedCurrentVersion = options.expectedCurrentVersion;
  const recoveryExpectedRouteName = options.expectedRouteName;
  const recoveryGuardValues = [
    recoveryExpectedDeploymentId,
    recoveryExpectedSystemName,
    recoveryExpectedDeployVersion,
    recoveryExpectedCurrentVersion,
    recoveryExpectedRouteName
  ];
  if (recoveryGuardValues.some((value) => value === undefined)) {
    throw new Error("EXACT_UPGRADE_GUARD_REQUIRED: this isolated runtime cannot perform ordinary deploys");
  }
  const recoveryMode = true;
  if (recoveryMode && !/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(recoveryExpectedDeploymentId)) {
    throw new Error("EXACT_UPGRADE_INVALID_DEPLOYMENT_ID");
  }
  if (recoveryMode && !/^ID[0-9a-fA-F]{32}$/.test(recoveryExpectedSystemName)) {
    throw new Error("EXACT_UPGRADE_INVALID_SYSTEM_NAME");
  }
  if (recoveryMode && !/^[1-9][0-9]*$/.test(recoveryExpectedDeployVersion)) {
    throw new Error("EXACT_UPGRADE_INVALID_DEPLOY_VERSION");
  }
  const logger3 = options.logger ?? {""",
    ),
    (
        """    const deployedApp = await getDeployedApp(appName, displayTitle, envConfig);
    let operationResult;""",
        """    const deployedApp = await getDeployedApp(appName, displayTitle, envConfig);
    if (recoveryMode && (!deployedApp || deployedApp.id !== recoveryExpectedDeploymentId)) {
      throw new Error("EXACT_UPGRADE_TARGET_MISMATCH: fresh deploy prohibited");
    }
    if (recoveryMode && deployedApp.title !== appName && deployedApp.title !== displayTitle) {
      throw new Error("EXACT_UPGRADE_TITLE_MISMATCH");
    }
    if (recoveryMode && deployedApp.routingName !== recoveryExpectedRouteName) {
      throw new Error("EXACT_UPGRADE_ROUTE_MISMATCH");
    }
    if (recoveryMode && deployedApp.semVersion !== recoveryExpectedCurrentVersion) {
      throw new Error("EXACT_UPGRADE_CURRENT_VERSION_MISMATCH");
    }
    let operationResult;""",
    ),
    (
        """      if (publishedApp.deployVersion === undefined) {
        spinner.fail(source_default.red(MESSAGES.ERRORS.DEPLOY_VERSION_NOT_FOUND));
        throw new Error(MESSAGES.ERRORS.DEPLOY_VERSION_NOT_FOUND);
      }
      await upgradeApp(deployedApp.id, displayTitle, publishedApp.deployVersion, options.pathName ? routingName : undefined, envConfig, options.tags, options.clientId);""",
        """      if (publishedApp.deployVersion === undefined) {
        spinner.fail(source_default.red(MESSAGES.ERRORS.DEPLOY_VERSION_NOT_FOUND));
        throw new Error(MESSAGES.ERRORS.DEPLOY_VERSION_NOT_FOUND);
      }
      if (recoveryMode && publishedApp.systemName !== recoveryExpectedSystemName) {
        throw new Error("EXACT_UPGRADE_SYSTEM_NAME_MISMATCH");
      }
      if (recoveryMode && String(publishedApp.deployVersion) !== recoveryExpectedDeployVersion) {
        throw new Error("EXACT_UPGRADE_DEPLOY_VERSION_MISMATCH");
      }
      if (recoveryMode && options.recoveryVerifyOnly) {
        spinner.succeed(source_default.green("Exact upgrade target verified; no mutation performed"));
        return {
          appName: displayTitle,
          appUrl: buildAppUrl(envConfig.baseUrl, envConfig.orgName, recoveryExpectedRouteName),
          version: publishedApp.definition?.codedAppMetadata?.packageVersion,
          deploymentId: deployedApp.id,
          systemName: publishedApp.systemName,
          deployVersion: publishedApp.deployVersion,
          currentVersion: deployedApp.semVersion,
          routeName: deployedApp.routingName,
          operation: "recovery_verify"
        };
      }
      await upgradeApp(deployedApp.id, displayTitle, publishedApp.deployVersion, recoveryMode ? undefined : options.pathName ? routingName : undefined, envConfig, options.tags, options.clientId);""",
    ),
    (
        """  program2.command("deploy").description("Deploy or upgrade app in UiPath").option("-n, --name <name>", "App name").option("--path-name <name>", "App pathname in the URL (https://<org>.uipath.host/<path-name>)").option("--client-id <id>", "OAuth client ID override (non-confidential/public client)").option("-v, --version <version>", "Target a specific published version").option("--base-url <url>", "UiPath base URL").option("--org-id <id>", "Organization ID").option("--org-name <name>", "Organization name").option("--tenant-id <id>", "Tenant ID").option("--folder-key <key>", "Folder key").option("--access-token <token>", "Access token").option("--tags <tags>", "Comma-separated categorization labels for the deployed app (e.g. governance,insights)").examples(DEPLOY_EXAMPLES).trackedAction(processContext, async (options) => {""",
        """  program2.command("deploy").description("Deploy or upgrade app in UiPath").option("-n, --name <name>", "App name").option("--path-name <name>", "App pathname in the URL (https://<org>.uipath.host/<path-name>)").option("--client-id <id>", "OAuth client ID override (non-confidential/public client)").option("-v, --version <version>", "Target a specific published version").option("--base-url <url>", "UiPath base URL").option("--org-id <id>", "Organization ID").option("--org-name <name>", "Organization name").option("--tenant-id <id>", "Tenant ID").option("--folder-key <key>", "Folder key").option("--access-token <token>", "Access token").option("--tags <tags>", "Comma-separated categorization labels for the deployed app (e.g. governance,insights)").option("--expected-deployment-id <id>", "Fail-closed deployment ID for exact upgrade recovery").option("--expected-system-name <name>", "Fail-closed system name for exact upgrade recovery").option("--expected-deploy-version <number>", "Fail-closed published deploy version for exact upgrade recovery").option("--expected-current-version <version>", "Fail-closed current deployed version for exact upgrade recovery").option("--expected-route-name <name>", "Fail-closed current route for exact upgrade recovery").option("--recovery-verify-only", "Verify the exact recovery target without mutation").examples(DEPLOY_EXAMPLES).trackedAction(processContext, async (options) => {""",
    ),
    (
        """      tags,
      logger: logger3""",
        """      tags,
      expectedDeploymentId: options.expectedDeploymentId,
      expectedSystemName: options.expectedSystemName,
      expectedDeployVersion: options.expectedDeployVersion,
      expectedCurrentVersion: options.expectedCurrentVersion,
      expectedRouteName: options.expectedRouteName,
      recoveryVerifyOnly: options.recoveryVerifyOnly,
      logger: logger3""",
    ),
    (
        """      Data: { message: "App deployed successfully." }
    });""",
        """      Data: options.recoveryVerifyOnly && result ? {
        message: "Exact upgrade target verified; no mutation performed.",
        deploymentId: result.deploymentId,
        systemName: result.systemName,
        deployVersion: result.deployVersion,
        currentVersion: result.currentVersion,
        routeName: result.routeName,
        version: result.version,
        appName: result.appName,
        appUrl: result.appUrl,
        operation: result.operation
      } : { message: "App deployed successfully." }
    });""",
    ),
    (
        """    if (result) {
      trackShipSucceeded({
        ship_kind: "deploy",""",
        """    if (result && result.operation !== "recovery_verify") {
      trackShipSucceeded({
        ship_kind: "deploy",""",
    ),
)

EVIDENCE_LABELS = (
    "prior_successful_plan",
    "prior_successful_receipt",
    "prior_successful_app_config",
    "failed_plan",
    "failed_receipt",
    "reconciliation_evidence",
    "recovery_runtime_manifest",
)


def _load_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        core._fail(f"{label} must be a regular non-symlink file: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        core._fail(f"Could not read {label} JSON {path}: {type(exc).__name__}")
    if not isinstance(document, dict):
        core._fail(f"{label} must contain a JSON object.")
    return document


def _evidence_record(path: Path, label: str) -> dict[str, str]:
    expanded = path.expanduser()
    if expanded.is_symlink():
        core._fail(f"{label} must not be a symlink: {expanded}")
    resolved = expanded.resolve()
    if not resolved.is_file():
        core._fail(f"{label} must be a regular non-symlink file: {resolved}")
    return {
        "label": label,
        "path": str(resolved),
        "sha256": core._hash_file(resolved, label),
    }


def _tree_digest(root: Path, label: str) -> str:
    if root.is_symlink() or not root.is_dir():
        core._fail(f"{label} must be a real directory, not a symlink: {root}")
    records: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            core._fail(f"{label} may not contain symlinks: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            core._fail(f"{label} contains an unsupported filesystem entry: {path}")
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "mode": path.stat().st_mode & 0o777,
                "size": path.stat().st_size,
                "sha256": core._hash_file(path, f"{label} file"),
            }
        )
    if not records:
        core._fail(f"{label} contains no files: {root}")
    return core._hash_json({"files": records})


def _paths_overlap(first: Path, second: Path) -> bool:
    """Return whether either normalized path contains the other."""

    try:
        first.relative_to(second)
        return True
    except ValueError:
        pass
    try:
        second.relative_to(first)
        return True
    except ValueError:
        return False


def _recovery_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    """Create the only environment allowed for guarded Node invocations."""

    observed = os.environ if source is None else source
    injected = [name for name in FORBIDDEN_RECOVERY_ENVIRONMENT if name in observed]
    if injected:
        core._fail(
            "Recovery environment contains prohibited Node or dynamic-loader variables: "
            + ", ".join(injected)
            + ". Unset them and regenerate the runtime and plan."
        )
    if not isinstance(observed.get("HOME"), str) or not observed["HOME"]:
        core._fail("Recovery environment requires HOME for the approved CLI profile.")
    home = Path(observed["HOME"]).expanduser()
    if not home.is_absolute() or home.is_symlink() or not home.is_dir():
        core._fail("Recovery HOME must be an absolute real directory.")
    environment = {
        name: str(home.resolve()) if name == "HOME" else str(observed[name])
        for name in RECOVERY_ENVIRONMENT_PRESERVE
        if name in observed
    }
    environment.update(RECOVERY_ENVIRONMENT_OVERRIDES)
    return environment


def _resolve_node_runtime(
    node_executable: Path | str, environment: dict[str, str]
) -> dict[str, str]:
    try:
        unresolved = Path(node_executable).expanduser()
        if not unresolved.is_absolute():
            core._fail("Recovery Node.js executable path must be absolute.")
        executable = unresolved.resolve(strict=True)
    except (OSError, RuntimeError):
        core._fail("Resolved Node.js executable is unavailable.")
    if not executable.is_absolute() or executable.is_symlink() or not executable.is_file():
        core._fail("Resolved Node.js executable must be an absolute regular file.")
    try:
        completed = subprocess.run(
            [str(executable), "--version"],
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        core._fail("Could not execute the resolved Node.js runtime.")
    raw_version = completed.stdout.strip()
    if re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?", raw_version) is None:
        core._fail("Resolved Node.js runtime returned an invalid version.")
    try:
        exec_path_result = subprocess.run(
            [str(executable), "-p", "process.execPath"],
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        process_exec_path = Path(exec_path_result.stdout.strip()).resolve(strict=True)
    except (OSError, RuntimeError, subprocess.CalledProcessError):
        core._fail("Could not verify the Node.js process executable path.")
    if process_exec_path != executable:
        core._fail("Node.js process.execPath does not match the bound executable.")
    return {
        "executable": str(executable),
        "executable_sha256": core._hash_file(executable, "Node.js executable"),
        "version": raw_version[1:],
    }


def _patch_contract_hash() -> str:
    return core._hash_json(
        {
            "algorithm": PATCH_ALGORITHM,
            "expected_version": EXPECTED_CODEDAPP_TOOL_VERSION,
            "expected_git_head": EXPECTED_CODEDAPP_TOOL_GIT_HEAD,
            "expected_tool_sha256": EXPECTED_CODEDAPP_TOOL_SHA256,
            "edits": [
                {"source": source, "replacement": replacement}
                for source, replacement in PATCH_EDITS
            ],
        }
    )


def _patched_tool_bytes(source: bytes) -> bytes:
    if core._hash_bytes(source) != EXPECTED_CODEDAPP_TOOL_SHA256:
        core._fail("Coded app tool bytes are not the approved 1.198.0 recovery source.")
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError:
        core._fail("Coded app tool source is not UTF-8.")
    for old, new in PATCH_EDITS:
        if text.count(old) != 1:
            core._fail("Coded app recovery patch anchor did not match exactly once.")
        text = text.replace(old, new, 1)
    patched = text.encode("utf-8")
    if patched == source:
        core._fail("Coded app recovery patch produced no change.")
    return patched


def _self_test_runtime(
    runtime_cli: Path,
    runtime_tool: Path,
    runtime_workspace: Path,
    node_executable: Path,
    environment: dict[str, str],
) -> dict[str, str]:
    syntax = subprocess.run(
        [str(node_executable), "--check", str(runtime_tool)],
        cwd=runtime_workspace,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if syntax.returncode != 0:
        core._fail("Guarded coded app tool failed the Node.js syntax check.")

    for extra_args, label in (
        ([], "unguarded_deploy"),
        (["--recovery-verify-only"], "verify_only_without_guard"),
    ):
        blocked = subprocess.run(
            [
                str(node_executable),
                str(runtime_cli),
                "codedapp",
                "deploy",
                *extra_args,
                "--output",
                "json",
            ],
            cwd=runtime_workspace,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        try:
            payload = json.loads(blocked.stdout)
        except json.JSONDecodeError:
            core._fail(f"Guarded runtime self-test {label} returned invalid JSON.")
        if (
            blocked.returncode == 0
            or not isinstance(payload, dict)
            or payload.get("Result") != "Failure"
            or "EXACT_UPGRADE_GUARD_REQUIRED" not in payload.get("Instructions", "")
        ):
            core._fail(f"Guarded runtime self-test {label} did not fail closed.")
    return {
        "node_syntax": "passed",
        "dynamic_tool_resolution": "passed",
        "unguarded_deploy": "blocked_before_network",
        "verify_only_without_guard": "blocked_before_network",
    }


def _prepare_runtime(
    source_cli: Path,
    node_executable: Path,
    runtime_output: Path,
    manifest_output: Path,
) -> dict[str, Any]:
    source_cli = source_cli.expanduser().resolve()
    runtime_output = runtime_output.expanduser().resolve()
    manifest_output = manifest_output.expanduser().resolve()
    environment = _recovery_environment()
    node_runtime = _resolve_node_runtime(node_executable, environment)
    if runtime_output.exists() or manifest_output.exists():
        core._fail("Recovery runtime preparation refuses to overwrite existing output.")
    if source_cli.is_symlink() or not source_cli.is_file():
        core._fail("Recovery source CLI must be a regular non-symlink file.")
    try:
        source_relative = source_cli.relative_to(source_cli.parents[3])
    except ValueError:
        core._fail("Recovery source CLI must be inside a node_modules tree.")
    source_node_modules = source_cli.parents[3]
    if source_node_modules.name != "node_modules":
        core._fail("Recovery source CLI must resolve inside node_modules.")
    source_project_root = source_node_modules.parent
    if _paths_overlap(runtime_output, source_project_root):
        core._fail(
            "Recovery runtime output must be outside and disjoint from the source project."
        )
    try:
        manifest_output.relative_to(runtime_output)
    except ValueError:
        pass
    else:
        core._fail("Recovery runtime manifest must be outside the runtime root.")
    try:
        manifest_output.relative_to(source_project_root)
    except ValueError:
        pass
    else:
        core._fail("Recovery runtime manifest must not mutate the source project.")
    source_tool = source_cli.parents[2] / "codedapp-tool" / "dist" / "tool.js"
    source_tool_manifest_path = source_cli.parents[2] / "codedapp-tool" / "package.json"
    source_tool_manifest = _load_object(
        source_tool_manifest_path, "coded app tool source manifest"
    )
    if source_tool_manifest.get("version") != EXPECTED_CODEDAPP_TOOL_VERSION:
        core._fail("Coded app tool source version is not the approved recovery version.")
    if source_tool_manifest.get("gitHead") != EXPECTED_CODEDAPP_TOOL_GIT_HEAD:
        core._fail("Coded app tool source gitHead is not the approved recovery build.")
    if source_tool_manifest.get("main") != "./dist/tool.js":
        core._fail("Coded app tool source manifest main entry is unexpected.")
    source_tool_bytes = source_tool.read_bytes()
    patched_tool = _patched_tool_bytes(source_tool_bytes)

    runtime_node_modules = runtime_output / "node_modules"
    runtime_output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_node_modules, runtime_node_modules, symlinks=False)
    runtime_cli = runtime_node_modules / source_relative
    runtime_tool = runtime_node_modules / "@uipath" / "codedapp-tool" / "dist" / "tool.js"
    runtime_tool_manifest_path = (
        runtime_node_modules / "@uipath" / "codedapp-tool" / "package.json"
    )
    core._atomic_write_bytes(
        runtime_tool, patched_tool, runtime_tool.stat().st_mode & 0o777
    )
    source_app_config = source_project_root / core.APP_CONFIG_RELATIVE_PATH
    if source_app_config.is_symlink() or not source_app_config.is_file():
        core._fail("Recovery source app config must be a regular non-symlink file.")
    runtime_workspace = runtime_output / ISOLATED_WORKSPACE_RELATIVE
    runtime_app_config = runtime_workspace / core.APP_CONFIG_RELATIVE_PATH
    runtime_app_config.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_app_config, runtime_app_config)
    runtime_self_test = _self_test_runtime(
        runtime_cli,
        runtime_tool,
        runtime_workspace,
        Path(node_runtime["executable"]),
        environment,
    )
    manifest = {
        "kind": RUNTIME_MANIFEST_KIND,
        "schema_version": RUNTIME_MANIFEST_SCHEMA_VERSION,
        "created_at": core._utc_now(),
        "preparer_sha256": core._hash_file(Path(__file__), "recovery helper"),
        "patch_algorithm": PATCH_ALGORITHM,
        "patch_contract_sha256": _patch_contract_hash(),
        "source": {
            "node_modules_root": str(source_node_modules),
            "cli_executable": str(source_cli),
            "cli_executable_sha256": core._hash_file(source_cli, "source CLI"),
            "codedapp_tool_file": str(source_tool),
            "codedapp_tool_file_sha256": core._hash_bytes(source_tool_bytes),
            "codedapp_tool_manifest": str(source_tool_manifest_path),
            "codedapp_tool_manifest_sha256": core._hash_file(
                source_tool_manifest_path, "coded app tool source manifest"
            ),
            "codedapp_tool_version": source_tool_manifest["version"],
            "codedapp_tool_git_head": source_tool_manifest["gitHead"],
        },
        "runtime": {
            "root": str(runtime_output),
            "node_modules_root": str(runtime_node_modules),
            "tree_sha256": _tree_digest(runtime_output, "recovery runtime"),
            "workspace": str(runtime_workspace),
            "workspace_app_config": str(runtime_app_config),
            "workspace_app_config_sha256": core._hash_file(
                runtime_app_config, "recovery workspace app config"
            ),
            "self_test": runtime_self_test,
            "node_executable": node_runtime["executable"],
            "node_executable_sha256": node_runtime["executable_sha256"],
            "node_version": node_runtime["version"],
            "cli_executable": str(runtime_cli),
            "cli_executable_sha256": core._hash_file(runtime_cli, "recovery CLI"),
            "codedapp_tool_file": str(runtime_tool),
            "codedapp_tool_file_sha256": core._hash_file(
                runtime_tool, "guarded coded app tool"
            ),
            "codedapp_tool_manifest": str(runtime_tool_manifest_path),
            "codedapp_tool_manifest_sha256": core._hash_file(
                runtime_tool_manifest_path, "guarded coded app tool manifest"
            ),
        },
    }
    manifest["manifest_hash"] = core._document_hash(manifest, "manifest_hash")
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    core._atomic_write_json(manifest_output, manifest)
    return manifest


def _validate_evidence_record(record: Any, expected_label: str) -> Path:
    if not isinstance(record, dict) or set(record) != {"label", "path", "sha256"}:
        core._fail(f"Recovery evidence {expected_label} has an invalid shape.")
    if record["label"] != expected_label:
        core._fail(f"Recovery evidence label mismatch for {expected_label}.")
    if not isinstance(record["path"], str) or not Path(record["path"]).is_absolute():
        core._fail(f"Recovery evidence {expected_label} path must be absolute.")
    core._validate_hash(record["sha256"], f"Recovery evidence {expected_label} hash")
    path = Path(record["path"])
    if path.is_symlink():
        core._fail(f"Recovery evidence became a symlink: {expected_label}.")
    observed = core._hash_file(path, expected_label)
    if observed != record["sha256"]:
        core._fail(f"Recovery evidence changed after plan approval: {expected_label}.")
    return path


def _require_iso8601(value: Any, label: str) -> str:
    if not isinstance(value, str):
        core._fail(f"{label} must be an ISO-8601 timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        core._fail(f"{label} must be an ISO-8601 timestamp.")
    if parsed.tzinfo is None:
        core._fail(f"{label} must include a timezone.")
    return value


def _guarded_upgrade_command(
    command: list[str],
    *,
    node_executable: str,
    runtime_cli: str,
    deployment_id: str,
    system_name: str,
    deploy_version: int,
    current_version: str,
    route_name: str,
) -> list[str]:
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        core._fail("Failed deployment command must be a string array.")
    if len(command) < 3 or command[1:3] != ["codedapp", "deploy"]:
        core._fail("Failed deployment command must be exactly a codedapp deploy command.")
    indexes = [index for index, value in enumerate(command) if value == "--path-name"]
    if len(indexes) != 1:
        core._fail("Failed deployment command must contain exactly one --path-name.")
    index = indexes[0]
    if index + 1 >= len(command) or command[index + 1] != route_name:
        core._fail("Failed deployment command route does not match the existing route.")
    if any(flag in command for flag in (*RECOVERY_FLAGS, "--recovery-verify-only")):
        core._fail("Failed deployment command already contains recovery-only flags.")
    guarded = [node_executable, runtime_cli, *copy.deepcopy(command[1:])]
    guarded.extend(
        [
            "--expected-deployment-id",
            deployment_id,
            "--expected-system-name",
            system_name,
            "--expected-deploy-version",
            str(deploy_version),
            "--expected-current-version",
            current_version,
            "--expected-route-name",
            route_name,
        ]
    )
    for flag in RECOVERY_FLAGS:
        if guarded.count(flag) != 1:
            core._fail(f"Recovery command must contain exactly one {flag}.")
    if guarded.count("--path-name") != 1:
        core._fail("Recovery command must retain exactly one fail-safe --path-name.")
    return guarded


def _replace_flag_value(command: list[str], flag: str, value: str) -> list[str]:
    if command.count(flag) != 1:
        core._fail(f"Recovery command must contain exactly one {flag}.")
    index = command.index(flag)
    if index + 1 >= len(command):
        core._fail(f"Recovery command {flag} has no value.")
    replaced = copy.deepcopy(command)
    replaced[index + 1] = value
    return replaced


def _remote_guard_command(
    command: list[str], *, expected_current_version: str | None = None
) -> list[str]:
    if "--recovery-verify-only" in command:
        core._fail("Recovery deploy command already contains the read-only guard flag.")
    guarded = copy.deepcopy(command)
    if expected_current_version is not None:
        guarded = _replace_flag_value(
            guarded, "--expected-current-version", expected_current_version
        )
    return [*guarded, "--recovery-verify-only", "--output", "json"]


def _execution_claim_key(
    *,
    parameters: dict[str, Any],
    deployment_id: str,
    system_name: str,
    deploy_version: int,
    candidate_version: str,
) -> str:
    return core._hash_json(
        {
            "scope": "home_scoped_exact_candidate_v1",
            "environment": parameters["environment"],
            "organization_id": parameters["org_id"],
            "tenant_id": parameters["tenant_id"],
            "folder_key": parameters["folder_key"],
            "deployment_id": deployment_id,
            "system_name": system_name,
            "deploy_version": deploy_version,
            "candidate_version": candidate_version,
        }
    )


def _one_stage(plan: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [stage for stage in plan["stages"] if stage.get("name") == name]
    if len(matches) != 1:
        core._fail(f"Expected exactly one {name} stage in the v2.3 plan.")
    return matches[0]


def _validate_prior_app_config(
    document: dict[str, Any], prior_plan: dict[str, Any]
) -> dict[str, str]:
    required = {
        "appName",
        "displayName",
        "appVersion",
        "systemName",
        "appUrl",
        "appType",
        "personalWorkspace",
        "deploymentId",
        "deployedAt",
    }
    if not required.issubset(document):
        core._fail("Prior successful app config is missing deployment metadata.")
    parameters = prior_plan["parameters"]
    expected = {
        "appName": parameters["package_name"],
        "displayName": parameters["app_name"],
        "appVersion": prior_plan["project"]["new_version"],
        "appType": parameters["app_type"],
        "personalWorkspace": False,
    }
    for field, value in expected.items():
        if document.get(field) != value:
            core._fail(f"Prior successful app config {field} does not match its plan.")
    if not isinstance(document["systemName"], str) or core.APP_SYSTEM_NAME_RE.fullmatch(
        document["systemName"]
    ) is None:
        core._fail("Prior successful app config systemName is invalid.")
    if not isinstance(document["deploymentId"], str) or core.GUID_RE.fullmatch(
        document["deploymentId"]
    ) is None:
        core._fail("Prior successful app config deploymentId is invalid.")
    app_url = document["appUrl"]
    if not isinstance(app_url, str) or not app_url.startswith("https://"):
        core._fail("Prior successful app config appUrl must be HTTPS.")
    _require_iso8601(document["deployedAt"], "Prior deployedAt")
    return {
        "system_name": document["systemName"],
        "deployment_id": document["deploymentId"],
        "app_url": app_url,
    }


def _validate_runtime_manifest(
    document: dict[str, Any],
    failed_parameters: dict[str, Any],
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    allowed_environment = _recovery_environment(environment)
    expected_top_level = {
        "kind",
        "schema_version",
        "created_at",
        "preparer_sha256",
        "patch_algorithm",
        "patch_contract_sha256",
        "source",
        "runtime",
        "manifest_hash",
    }
    if set(document) != expected_top_level:
        core._fail("Recovery runtime manifest fields are invalid.")
    if document.get("kind") != RUNTIME_MANIFEST_KIND:
        core._fail("Recovery runtime manifest kind is invalid.")
    if document.get("schema_version") != RUNTIME_MANIFEST_SCHEMA_VERSION:
        core._fail("Recovery runtime manifest schema version is invalid.")
    _require_iso8601(document.get("created_at"), "Recovery runtime created_at")
    if document.get("preparer_sha256") != core._hash_file(
        Path(__file__), "recovery helper"
    ):
        core._fail("Recovery runtime preparer bytes changed after runtime creation.")
    if document.get("patch_algorithm") != PATCH_ALGORITHM:
        core._fail("Recovery runtime patch algorithm is invalid.")
    if document.get("patch_contract_sha256") != _patch_contract_hash():
        core._fail("Recovery runtime patch contract changed.")
    if core._document_hash(document, "manifest_hash") != document.get("manifest_hash"):
        core._fail("Recovery runtime manifest hash is invalid.")
    source = document.get("source")
    runtime = document.get("runtime")
    if not isinstance(source, dict) or not isinstance(runtime, dict):
        core._fail("Recovery runtime manifest is missing source or runtime details.")
    if set(source) != {
        "node_modules_root",
        "cli_executable",
        "cli_executable_sha256",
        "codedapp_tool_file",
        "codedapp_tool_file_sha256",
        "codedapp_tool_manifest",
        "codedapp_tool_manifest_sha256",
        "codedapp_tool_version",
        "codedapp_tool_git_head",
    }:
        core._fail("Recovery runtime source fields are invalid.")
    if set(runtime) != {
        "root",
        "node_modules_root",
        "tree_sha256",
        "workspace",
        "workspace_app_config",
        "workspace_app_config_sha256",
        "self_test",
        "node_executable",
        "node_executable_sha256",
        "node_version",
        "cli_executable",
        "cli_executable_sha256",
        "codedapp_tool_file",
        "codedapp_tool_file_sha256",
        "codedapp_tool_manifest",
        "codedapp_tool_manifest_sha256",
    }:
        core._fail("Recovery runtime output fields are invalid.")

    source_cli = Path(source.get("cli_executable", ""))
    if str(source_cli) != failed_parameters["cli_executable"]:
        core._fail("Recovery runtime source CLI does not match the failed plan.")
    if source.get("cli_executable_sha256") != failed_parameters[
        "cli_executable_sha256"
    ]:
        core._fail("Recovery runtime source CLI digest does not match the failed plan.")
    if core._hash_file(source_cli, "recovery source CLI") != source.get(
        "cli_executable_sha256"
    ):
        core._fail("Recovery runtime source CLI bytes changed.")
    if Path(source["node_modules_root"]) != source_cli.parents[3]:
        core._fail("Recovery runtime source node_modules path is invalid.")
    source_tool = Path(source.get("codedapp_tool_file", ""))
    source_tool_manifest_path = Path(source.get("codedapp_tool_manifest", ""))
    if source_tool != source_cli.parents[2] / "codedapp-tool" / "dist" / "tool.js":
        core._fail("Recovery source coded app tool path is invalid.")
    if source_tool_manifest_path != source_cli.parents[2] / "codedapp-tool" / "package.json":
        core._fail("Recovery source coded app tool manifest path is invalid.")
    if source_tool.is_symlink() or source_tool_manifest_path.is_symlink():
        core._fail("Recovery runtime source tool files must not be symlinks.")
    if source.get("codedapp_tool_file_sha256") != EXPECTED_CODEDAPP_TOOL_SHA256:
        core._fail("Recovery runtime source tool digest is invalid.")
    if core._hash_file(source_tool, "recovery source coded app tool") != source.get(
        "codedapp_tool_file_sha256"
    ):
        core._fail("Recovery runtime source tool bytes changed.")
    source_manifest = _load_object(
        source_tool_manifest_path, "recovery source coded app tool manifest"
    )
    if (
        source.get("codedapp_tool_version") != EXPECTED_CODEDAPP_TOOL_VERSION
        or source_manifest.get("version") != EXPECTED_CODEDAPP_TOOL_VERSION
        or source.get("codedapp_tool_git_head") != EXPECTED_CODEDAPP_TOOL_GIT_HEAD
        or source_manifest.get("gitHead") != EXPECTED_CODEDAPP_TOOL_GIT_HEAD
        or source_manifest.get("main") != "./dist/tool.js"
    ):
        core._fail("Recovery source coded app tool identity is invalid.")
    if core._hash_file(
        source_tool_manifest_path, "recovery source coded app tool manifest"
    ) != source.get("codedapp_tool_manifest_sha256"):
        core._fail("Recovery source coded app tool manifest changed.")

    runtime_root = Path(runtime.get("root", ""))
    runtime_node_modules = Path(runtime.get("node_modules_root", ""))
    runtime_cli = Path(runtime.get("cli_executable", ""))
    runtime_tool = Path(runtime.get("codedapp_tool_file", ""))
    runtime_tool_manifest_path = Path(runtime.get("codedapp_tool_manifest", ""))
    runtime_workspace = Path(runtime.get("workspace", ""))
    runtime_app_config = Path(runtime.get("workspace_app_config", ""))
    runtime_node = Path(runtime.get("node_executable", ""))
    observed_node = _resolve_node_runtime(runtime_node, allowed_environment)
    for path, label in (
        (runtime_root, "recovery runtime root"),
        (runtime_node_modules, "recovery runtime node_modules"),
    ):
        if not path.is_absolute() or path.is_symlink() or not path.is_dir():
            core._fail(f"{label} must be an absolute real directory.")
    if runtime_node_modules != runtime_root / "node_modules":
        core._fail("Recovery runtime node_modules path is not rooted as approved.")
    if runtime_cli != runtime_node_modules / "@uipath" / "cli" / "dist" / "index.js":
        core._fail("Recovery runtime CLI path is invalid.")
    if runtime_tool != runtime_node_modules / "@uipath" / "codedapp-tool" / "dist" / "tool.js":
        core._fail("Recovery runtime coded app tool path is invalid.")
    if runtime_tool_manifest_path != runtime_node_modules / "@uipath" / "codedapp-tool" / "package.json":
        core._fail("Recovery runtime coded app tool manifest path is invalid.")
    if runtime_workspace != runtime_root / ISOLATED_WORKSPACE_RELATIVE:
        core._fail("Recovery workspace is not at the isolated approved path.")
    if runtime_workspace.is_symlink() or not runtime_workspace.is_dir():
        core._fail("Recovery workspace must be a real directory.")
    if runtime_app_config != runtime_workspace / core.APP_CONFIG_RELATIVE_PATH:
        core._fail("Recovery workspace app config path is invalid.")
    if (
        str(runtime_node) != observed_node["executable"]
        or runtime.get("node_executable_sha256")
        != observed_node["executable_sha256"]
        or runtime.get("node_version") != observed_node["version"]
    ):
        core._fail("Recovery Node.js runtime changed after approval.")
    if runtime_node.is_symlink() or not runtime_node.is_file():
        core._fail("Recovery Node.js executable must remain a regular non-symlink file.")
    expected_self_test = {
        "node_syntax": "passed",
        "dynamic_tool_resolution": "passed",
        "unguarded_deploy": "blocked_before_network",
        "verify_only_without_guard": "blocked_before_network",
    }
    if runtime.get("self_test") != expected_self_test:
        core._fail("Recovery runtime self-test evidence is invalid.")
    for path, label in (
        (runtime_cli, "recovery runtime CLI"),
        (runtime_tool, "recovery runtime coded app tool"),
        (runtime_tool_manifest_path, "recovery runtime coded app tool manifest"),
        (runtime_app_config, "recovery workspace app config"),
    ):
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            core._fail(f"{label} must be an absolute regular file.")
        try:
            path.relative_to(runtime_root)
        except ValueError:
            core._fail(f"{label} resolves outside the recovery runtime.")
    if core._hash_file(runtime_cli, "recovery runtime CLI") != runtime.get(
        "cli_executable_sha256"
    ):
        core._fail("Recovery runtime CLI bytes changed.")
    if runtime.get("cli_executable_sha256") != failed_parameters[
        "cli_executable_sha256"
    ]:
        core._fail("Recovery runtime CLI differs from the approved pinned executable.")
    expected_patched = _patched_tool_bytes(source_tool.read_bytes())
    if runtime_tool.read_bytes() != expected_patched:
        core._fail("Guarded coded app tool does not match the deterministic patch.")
    if core._hash_file(runtime_tool, "guarded coded app tool") != runtime.get(
        "codedapp_tool_file_sha256"
    ):
        core._fail("Guarded coded app tool digest is invalid.")
    if core._hash_file(
        runtime_tool_manifest_path, "guarded coded app tool manifest"
    ) != runtime.get("codedapp_tool_manifest_sha256"):
        core._fail("Guarded coded app tool manifest changed.")
    if runtime.get("codedapp_tool_manifest_sha256") != source.get(
        "codedapp_tool_manifest_sha256"
    ):
        core._fail("Guarded runtime changed the coded app tool manifest.")
    if core._hash_file(runtime_app_config, "recovery workspace app config") != runtime.get(
        "workspace_app_config_sha256"
    ):
        core._fail("Recovery workspace app config changed after approval.")
    if _tree_digest(runtime_root, "recovery runtime") != runtime.get(
        "tree_sha256"
    ):
        core._fail("Recovery runtime tree changed after approval.")
    return {
        "root": str(runtime_root),
        "node_modules_root": str(runtime_node_modules),
        "tree_sha256": runtime["tree_sha256"],
        "workspace": str(runtime_workspace),
        "workspace_app_config": str(runtime_app_config),
        "workspace_app_config_sha256": runtime["workspace_app_config_sha256"],
        "self_test": runtime["self_test"],
        "node_executable": str(runtime_node),
        "node_executable_sha256": runtime["node_executable_sha256"],
        "node_version": runtime["node_version"],
        "cli_executable": str(runtime_cli),
        "cli_executable_sha256": runtime["cli_executable_sha256"],
        "source_tool_file": str(source_tool),
        "source_tool_file_sha256": source["codedapp_tool_file_sha256"],
        "source_tool_manifest": str(source_tool_manifest_path),
        "source_tool_manifest_sha256": source["codedapp_tool_manifest_sha256"],
        "runtime_tool_file": str(runtime_tool),
        "runtime_tool_file_sha256": runtime["codedapp_tool_file_sha256"],
        "runtime_tool_manifest": str(runtime_tool_manifest_path),
        "runtime_tool_manifest_sha256": runtime["codedapp_tool_manifest_sha256"],
        "version": source["codedapp_tool_version"],
        "git_head": source["codedapp_tool_git_head"],
        "patch_algorithm": document["patch_algorithm"],
        "patch_contract_sha256": document["patch_contract_sha256"],
        "manifest_hash": document["manifest_hash"],
    }


def _validate_reconciliation(
    document: dict[str, Any],
    *,
    prior_plan: dict[str, Any],
    failed_plan: dict[str, Any],
    failed_receipt: dict[str, Any],
    deployment: dict[str, str],
) -> dict[str, Any]:
    if document.get("kind") != RECONCILIATION_KIND:
        core._fail("Reconciliation evidence kind is invalid.")
    if document.get("schemaVersion") != RECONCILIATION_SCHEMA_VERSION:
        core._fail("Reconciliation evidence schemaVersion is invalid.")
    _require_iso8601(document.get("reconciledAt"), "Reconciliation reconciledAt")
    target = document.get("target")
    existing = document.get("existingDeployment")
    candidate = document.get("publishedCandidate")
    failure = document.get("failure")
    root_cause = document.get("rootCause")
    if not all(isinstance(item, dict) for item in (target, existing, candidate, failure, root_cause)):
        core._fail("Reconciliation evidence is missing required sections.")
    parameters = failed_plan["parameters"]
    expected_target = {
        "controlPlaneUrl": parameters["control_plane_url"],
        "organizationName": parameters["org_name"],
        "organizationId": parameters["org_id"],
        "tenantName": parameters["tenant_name"],
        "tenantId": parameters["tenant_id"],
        "folderKey": parameters["folder_key"],
        "oauthClientId": parameters["client_id"],
    }
    for field, value in expected_target.items():
        if target.get(field) != value:
            core._fail(f"Reconciliation target {field} does not match the failed plan.")
    expected_existing = {
        "appName": parameters["app_name"],
        "packageName": parameters["package_name"],
        "systemName": deployment["system_name"],
        "deploymentId": deployment["deployment_id"],
        "routeName": parameters["path_name"],
        "appUrl": deployment["app_url"],
        "deployedVersionBeforeRecovery": prior_plan["project"]["new_version"],
        "priorSuccessfulPlanHash": prior_plan["plan_hash"],
    }
    for field, value in expected_existing.items():
        if existing.get(field) != value:
            core._fail(f"Reconciliation existingDeployment {field} does not match evidence.")
    expected_candidate = {
        "version": failed_plan["project"]["new_version"],
        "systemName": deployment["system_name"],
        "sourceSha": parameters["source_sha"],
        "failedPlanHash": failed_plan["plan_hash"],
        "packageContentSha256": parameters["package_digest"],
        "candidatePackageFileSha256": parameters["candidate_package_file_digest"],
        "executedPackageFileSha256": failed_receipt["package_file_digest"],
    }
    for field, value in expected_candidate.items():
        if candidate.get(field) != value:
            core._fail(f"Reconciliation publishedCandidate {field} does not match evidence.")
    if not isinstance(candidate.get("deployVersion"), int) or candidate["deployVersion"] < 1:
        core._fail("Reconciliation publishedCandidate deployVersion is invalid.")
    _require_iso8601(candidate.get("publishedAt"), "Published candidate publishedAt")
    if failure.get("stage") != "deploy" or failure.get("httpStatus") != 400:
        core._fail("Reconciliation failure must identify the failed HTTP 400 deploy stage.")
    if failure.get("serverMessage") != "routing name must be unique":
        core._fail("Reconciliation failure signature is not the approved route collision.")
    if root_cause.get("cliVersion") != parameters["cli_version"]:
        core._fail("Reconciliation CLI version does not match the failed plan.")
    if root_cause.get("cliExecutableSha256") != parameters["cli_executable_sha256"]:
        core._fail("Reconciliation CLI digest does not match the failed plan.")
    if root_cause.get("codedAppToolFileSha256") != EXPECTED_CODEDAPP_TOOL_SHA256:
        core._fail("Reconciliation coded app tool digest is invalid.")

    observations = document.get("evidence")
    required_observations = {
        "named profile status",
        "package catalog",
        "OAuth client",
        "published package candidate",
        "pre-recovery live route",
        "deployed app recovery probe",
    }
    if not isinstance(observations, list):
        core._fail("Reconciliation evidence observations must be an array.")
    observed_names: set[str] = set()
    observed_paths: dict[str, Path] = {}
    for observation in observations:
        if not isinstance(observation, dict) or set(observation) != {
            "name",
            "path",
            "sha256",
        }:
            core._fail("Reconciliation observation has an invalid shape.")
        name = observation["name"]
        path_value = observation["path"]
        if not isinstance(name, str) or name in observed_names:
            core._fail("Reconciliation observation names must be unique strings.")
        if not isinstance(path_value, str) or not Path(path_value).is_absolute():
            core._fail("Reconciliation observation paths must be absolute.")
        core._validate_hash(observation["sha256"], f"Reconciliation {name} hash")
        path = Path(path_value)
        if path.is_symlink() or not path.is_file():
            core._fail(f"Reconciliation observation is not a regular file: {name}.")
        if core._hash_file(path, f"reconciliation {name}") != observation["sha256"]:
            core._fail(f"Reconciliation observation changed: {name}.")
        observed_names.add(name)
        observed_paths[name] = path
    if not required_observations.issubset(observed_names):
        core._fail("Reconciliation is missing required remote observations.")
    probe = _load_object(
        observed_paths["deployed app recovery probe"],
        "deployed app recovery probe",
    )
    probe_result = probe.get("result")
    probe_data = probe_result.get("Data") if isinstance(probe_result, dict) else None
    if (
        probe.get("kind")
        != "uipcodedappdeploy.exact-upgrade-read-only-probe"
        or probe.get("effects") != "none"
        or not isinstance(probe_result, dict)
        or probe_result.get("Result") != "Success"
        or probe_result.get("Code") != "DeployCompleted"
        or not isinstance(probe_data, dict)
    ):
        core._fail("Deployed app recovery probe is not successful read-only evidence.")
    expected_probe = {
        "DeploymentId": deployment["deployment_id"],
        "SystemName": candidate["systemName"],
        "DeployVersion": candidate["deployVersion"],
        "CurrentVersion": prior_plan["project"]["new_version"],
        "RouteName": parameters["path_name"],
        "Version": failed_plan["project"]["new_version"],
        "AppName": parameters["app_name"],
        "AppUrl": deployment["app_url"],
        "Operation": "recovery_verify",
    }
    for field, value in expected_probe.items():
        if probe_data.get(field) != value:
            core._fail(f"Deployed app recovery probe {field} does not match evidence.")
    package_observation = _load_object(
        observed_paths["published package candidate"],
        "published package candidate",
    )
    package_data = package_observation.get("Data")
    if not isinstance(package_data, dict):
        core._fail("Published package candidate observation is invalid.")
    if (
        package_data.get("Title") != parameters["package_name"]
        or package_data.get("Version") != failed_plan["project"]["new_version"]
        or package_data.get("PackageType") != "WebApp"
    ):
        core._fail("Published package candidate does not match the failed plan.")
    return {
        "candidate_system_name": candidate["systemName"],
        "candidate_deploy_version": candidate["deployVersion"],
    }


def _cross_validate_v23_evidence(
    *,
    prior_plan: dict[str, Any],
    prior_receipt: dict[str, Any],
    prior_app_config: dict[str, Any],
    failed_plan: dict[str, Any],
    failed_receipt: dict[str, Any],
    reconciliation: dict[str, Any],
    runtime_manifest: dict[str, Any],
) -> dict[str, Any]:
    if prior_receipt["status"] != "succeeded":
        core._fail("Prior deployment receipt must be succeeded.")
    if failed_receipt["status"] != "in_progress":
        core._fail("Failed deployment receipt must remain in_progress and indeterminate.")
    deploy_receipt = _one_stage({"stages": failed_receipt["stages"]}, "deploy")
    if deploy_receipt.get("status") != "running" or "blind resume prohibited" not in deploy_receipt.get(
        "recovery", ""
    ):
        core._fail("Failed deploy stage must be indeterminate and prohibit blind resume.")
    for name in ("publish", "app_config"):
        if _one_stage({"stages": failed_receipt["stages"]}, name).get("status") != "succeeded":
            core._fail(f"Failed receipt {name} stage must have succeeded before recovery.")

    prior_parameters = prior_plan["parameters"]
    failed_parameters = failed_plan["parameters"]
    immutable_fields = (
        "environment",
        "control_plane_url",
        "tenant_name",
        "tenant_id",
        "org_id",
        "org_name",
        "folder_key",
        "package_name",
        "app_name",
        "app_type",
        "path_name",
        "client_id",
        "tags",
        "cli_executable_sha256",
        "cli_version",
        "cli_profile",
        "cli_profile_hash",
    )
    for field in immutable_fields:
        if prior_parameters[field] != failed_parameters[field]:
            core._fail(f"Recovery target drifted between deployments: {field}.")
    if prior_plan["project"]["new_version"] == failed_plan["project"]["new_version"]:
        core._fail("Recovery candidate must differ from the prior deployed version.")
    if prior_plan["project"]["root"] == failed_plan["project"]["root"]:
        core._fail("Recovery evidence must use separate immutable release workspaces.")

    deployment = _validate_prior_app_config(prior_app_config, prior_plan)
    expected_url = (
        f"https://{failed_parameters['org_name']}."
        f"{failed_parameters['environment']}.uipath.host/{failed_parameters['path_name']}"
    )
    if deployment["app_url"] != expected_url:
        core._fail("Prior deployment URL does not match the approved environment and route.")
    reconciled = _validate_reconciliation(
        reconciliation,
        prior_plan=prior_plan,
        failed_plan=failed_plan,
        failed_receipt=failed_receipt,
        deployment=deployment,
    )
    runtime = _validate_runtime_manifest(runtime_manifest, failed_parameters)

    deploy_stage = _one_stage(failed_plan, "deploy")
    if deploy_stage.get("action") != "command" or deploy_stage.get("effect") != "external_write":
        core._fail("Failed deploy plan stage is not an external command write.")
    recovery_command = _guarded_upgrade_command(
        deploy_stage.get("command"),
        node_executable=runtime["node_executable"],
        runtime_cli=runtime["cli_executable"],
        deployment_id=deployment["deployment_id"],
        system_name=reconciled["candidate_system_name"],
        deploy_version=reconciled["candidate_deploy_version"],
        current_version=prior_plan["project"]["new_version"],
        route_name=failed_parameters["path_name"],
    )
    if recovery_command[:4] != [
        runtime["node_executable"],
        runtime["cli_executable"],
        "codedapp",
        "deploy",
    ]:
        core._fail("Recovery command does not use the bound Node and guarded CLI executables.")
    forbidden = {"pack", "publish"}
    if forbidden.intersection(recovery_command):
        core._fail("Recovery command contains a forbidden pack or publish argument.")
    if failed_parameters["package_path"] != core._package_path(
        failed_parameters["package_name"], failed_plan["project"]["new_version"]
    ):
        core._fail("Failed plan package path is inconsistent.")
    return {
        "deployment": deployment,
        "recovery_command": recovery_command,
        "remote_guard_command": _remote_guard_command(recovery_command),
        "post_upgrade_guard_command": _remote_guard_command(
            recovery_command,
            expected_current_version=failed_plan["project"]["new_version"],
        ),
        "candidate_system_name": reconciled["candidate_system_name"],
        "candidate_deploy_version": reconciled["candidate_deploy_version"],
        "runtime": runtime,
    }


def _load_bound_evidence(evidence: list[dict[str, str]]) -> dict[str, Any]:
    if not isinstance(evidence, list) or len(evidence) != len(EVIDENCE_LABELS):
        core._fail("Recovery plan evidence set is incomplete.")
    by_label: dict[str, Path] = {}
    for expected, record in zip(EVIDENCE_LABELS, evidence):
        path = _validate_evidence_record(record, expected)
        by_label[expected] = path
    prior_plan = core._load_plan(by_label["prior_successful_plan"])
    prior_receipt = core._load_receipt(by_label["prior_successful_receipt"], prior_plan)
    failed_plan = core._load_plan(by_label["failed_plan"])
    failed_receipt = core._load_receipt(by_label["failed_receipt"], failed_plan)
    prior_app_config = _load_object(by_label["prior_successful_app_config"], "prior app config")
    reconciliation = _load_object(by_label["reconciliation_evidence"], "reconciliation evidence")
    runtime_manifest = _load_object(
        by_label["recovery_runtime_manifest"], "recovery runtime manifest"
    )
    derived = _cross_validate_v23_evidence(
        prior_plan=prior_plan,
        prior_receipt=prior_receipt,
        prior_app_config=prior_app_config,
        failed_plan=failed_plan,
        failed_receipt=failed_receipt,
        reconciliation=reconciliation,
        runtime_manifest=runtime_manifest,
    )
    return {
        "paths": by_label,
        "prior_plan": prior_plan,
        "prior_receipt": prior_receipt,
        "failed_plan": failed_plan,
        "failed_receipt": failed_receipt,
        "prior_app_config": prior_app_config,
        "reconciliation": reconciliation,
        "runtime_manifest": runtime_manifest,
        **derived,
    }


def _expected_projection(context: dict[str, Any]) -> dict[str, Any]:
    failed_plan = context["failed_plan"]
    failed_receipt = context["failed_receipt"]
    parameters = failed_plan["parameters"]
    deployment = context["deployment"]
    return {
        "project_root": failed_plan["project"]["root"],
        "target": {
            "environment": parameters["environment"],
            "control_plane_url": parameters["control_plane_url"],
            "organization_name": parameters["org_name"],
            "organization_id": parameters["org_id"],
            "tenant_name": parameters["tenant_name"],
            "tenant_id": parameters["tenant_id"],
            "folder_key": parameters["folder_key"],
            "client_id": parameters["client_id"],
        },
        "existing_deployment": {
            "app_name": parameters["app_name"],
            "package_name": parameters["package_name"],
            "app_type": parameters["app_type"],
            "system_name": deployment["system_name"],
            "deployment_id": deployment["deployment_id"],
            "route_name": parameters["path_name"],
            "app_url": deployment["app_url"],
            "deployed_version": context["prior_plan"]["project"]["new_version"],
        },
        "candidate": {
            "version": failed_plan["project"]["new_version"],
            "system_name": context["candidate_system_name"],
            "deploy_version": context["candidate_deploy_version"],
            "source_sha": parameters["source_sha"],
            "package_path": parameters["package_path"],
            "package_content_digest": parameters["package_digest"],
            "package_file_digest": failed_receipt["package_file_digest"],
            "candidate_package_file_digest": parameters["candidate_package_file_digest"],
            "source_cli_executable": parameters["cli_executable"],
            "source_cli_executable_sha256": parameters["cli_executable_sha256"],
            "recovery_node_executable": context["runtime"]["node_executable"],
            "recovery_node_executable_sha256": context["runtime"][
                "node_executable_sha256"
            ],
            "recovery_node_version": context["runtime"]["node_version"],
            "recovery_cli_executable": context["runtime"]["cli_executable"],
            "recovery_cli_executable_sha256": context["runtime"][
                "cli_executable_sha256"
            ],
            "cli_version": parameters["cli_version"],
            "cli_profile": parameters["cli_profile"],
            "cli_profile_hash": parameters["cli_profile_hash"],
            "codedapp_tool_source_file": context["runtime"]["source_tool_file"],
            "codedapp_tool_source_file_sha256": context["runtime"][
                "source_tool_file_sha256"
            ],
            "codedapp_tool_source_manifest": context["runtime"][
                "source_tool_manifest"
            ],
            "codedapp_tool_source_manifest_sha256": context["runtime"][
                "source_tool_manifest_sha256"
            ],
            "codedapp_tool_recovery_file": context["runtime"]["runtime_tool_file"],
            "codedapp_tool_recovery_file_sha256": context["runtime"][
                "runtime_tool_file_sha256"
            ],
            "codedapp_tool_recovery_manifest": context["runtime"][
                "runtime_tool_manifest"
            ],
            "codedapp_tool_recovery_manifest_sha256": context["runtime"][
                "runtime_tool_manifest_sha256"
            ],
            "codedapp_tool_version": context["runtime"]["version"],
            "codedapp_tool_git_head": context["runtime"]["git_head"],
            "recovery_runtime_root": context["runtime"]["root"],
            "recovery_runtime_tree_sha256": context["runtime"]["tree_sha256"],
            "recovery_runtime_manifest_hash": context["runtime"]["manifest_hash"],
            "recovery_workspace": context["runtime"]["workspace"],
            "recovery_workspace_app_config_sha256": context["runtime"][
                "workspace_app_config_sha256"
            ],
            "recovery_runtime_self_test": context["runtime"]["self_test"],
            "patch_algorithm": context["runtime"]["patch_algorithm"],
            "patch_contract_sha256": context["runtime"]["patch_contract_sha256"],
            "tags": parameters["tags"],
        },
        "upgrade_guard": {
            "mode": "exact_deployment_fail_closed_v1",
            "deployment_id": deployment["deployment_id"],
            "system_name": context["candidate_system_name"],
            "deploy_version": context["candidate_deploy_version"],
            "current_version": context["prior_plan"]["project"]["new_version"],
            "route_name": parameters["path_name"],
            "fresh_deploy_prohibited": True,
            "routing_name_omitted_from_patch": True,
            "local_execution_claim_scope": "home_scoped_exact_candidate_v1",
            "local_execution_claim_key": _execution_claim_key(
                parameters=parameters,
                deployment_id=deployment["deployment_id"],
                system_name=context["candidate_system_name"],
                deploy_version=context["candidate_deploy_version"],
                candidate_version=failed_plan["project"]["new_version"],
            ),
        },
        "failed_attempt": {
            "plan_hash": failed_plan["plan_hash"],
            "approved_plan_hash": failed_receipt["approved_plan_hash"],
            "deployment_binding_hash": failed_plan["deployment_binding_hash"],
            "receipt_status": failed_receipt["status"],
            "recovery": _one_stage({"stages": failed_receipt["stages"]}, "deploy")["recovery"],
        },
        "stages": [
            {
                "name": "execution_claim",
                "action": "claim_exact_candidate",
                "effect": "local_write",
            },
            {
                "name": "reconcile",
                "action": "validate_recovery",
                "effect": "local_read",
            },
            {
                "name": "pre_upgrade_guard",
                "action": "verify_exact_upgrade_target",
                "effect": "external_read",
                "cwd": context["runtime"]["workspace"],
                "command": context["remote_guard_command"],
            },
            {
                "name": "runtime_barrier",
                "action": "revalidate_guarded_runtime",
                "effect": "local_read",
            },
            {
                "name": "upgrade",
                "action": "command",
                "effect": "external_write",
                "cwd": context["runtime"]["workspace"],
                "command": context["recovery_command"],
            },
            {
                "name": "post_upgrade_guard",
                "action": "verify_exact_upgraded_target",
                "effect": "external_read",
                "cwd": context["runtime"]["workspace"],
                "command": context["post_upgrade_guard_command"],
                "attempts": 3,
                "delays_seconds": [1, 2],
            },
            {
                "name": "verify",
                "action": "verify_existing_url",
                "effect": "external_read",
                "url": deployment["app_url"],
                "timeout_seconds": 30,
            },
            {
                "name": "post_deploy_metadata",
                "action": "inspect_app_config",
                "effect": "local_read",
            },
        ],
        "execution": {
            "executable": True,
            "blockers": [],
            "resume_supported": False,
            "publishes_package": False,
            "changes_route": False,
            "environment_policy": {
                "forbidden": list(FORBIDDEN_RECOVERY_ENVIRONMENT),
                "preserved": list(RECOVERY_ENVIRONMENT_PRESERVE),
                "overrides": RECOVERY_ENVIRONMENT_OVERRIDES,
            },
        },
    }


def _build_plan(args: argparse.Namespace) -> dict[str, Any]:
    evidence = [
        _evidence_record(Path(getattr(args, label)), label) for label in EVIDENCE_LABELS
    ]
    context = _load_bound_evidence(evidence)
    project_root = Path(args.project_root).expanduser().resolve()
    if str(project_root) != context["failed_plan"]["project"]["root"]:
        core._fail("--project-root must match the failed plan project root exactly.")
    plan = {
        "kind": PLAN_KIND,
        "schema_version": PLAN_SCHEMA_VERSION,
        "created_at": core._utc_now(),
        "recovery_helper_sha256": core._hash_file(Path(__file__), "recovery helper"),
        "core_helper_path": str(Path(core.__file__).resolve()),
        "core_helper_sha256": core._hash_file(Path(core.__file__), "core helper"),
        "evidence": evidence,
        **_expected_projection(context),
    }
    plan["evidence_binding_hash"] = core._hash_json(evidence)
    plan["plan_hash"] = core._document_hash(plan, "plan_hash")
    return plan


def _validate_plan(document: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(document, dict):
        core._fail("Recovery plan must be a JSON object.")
    required = {
        "kind",
        "schema_version",
        "created_at",
        "recovery_helper_sha256",
        "core_helper_path",
        "core_helper_sha256",
        "evidence",
        "evidence_binding_hash",
        "project_root",
        "target",
        "existing_deployment",
        "candidate",
        "upgrade_guard",
        "failed_attempt",
        "stages",
        "execution",
        "plan_hash",
    }
    if set(document) != required:
        core._fail(
            f"Recovery plan fields do not match schema {PLAN_SCHEMA_VERSION}."
        )
    if document["kind"] != PLAN_KIND or document["schema_version"] != PLAN_SCHEMA_VERSION:
        core._fail("Recovery plan kind or schema version is invalid.")
    _require_iso8601(document["created_at"], "Recovery plan created_at")
    core._validate_hash(document["recovery_helper_sha256"], "Recovery helper hash")
    if document["recovery_helper_sha256"] != core._hash_file(
        Path(__file__), "recovery helper"
    ):
        core._fail("Recovery helper bytes changed after plan approval.")
    if document["core_helper_path"] != str(Path(core.__file__).resolve()):
        core._fail("Recovery core helper path changed after plan approval.")
    core._validate_hash(document["core_helper_sha256"], "Recovery core helper hash")
    if document["core_helper_sha256"] != core._hash_file(
        Path(core.__file__), "core helper"
    ):
        core._fail("Recovery core helper bytes changed after plan approval.")
    core._validate_hash(document["plan_hash"], "Recovery plan hash")
    if core._document_hash(document, "plan_hash") != document["plan_hash"]:
        core._fail("Recovery plan hash is invalid; regenerate the plan.")
    if core._hash_json(document["evidence"]) != document["evidence_binding_hash"]:
        core._fail("Recovery evidence binding hash is invalid.")
    context = _load_bound_evidence(document["evidence"])
    expected = _expected_projection(context)
    for field, value in expected.items():
        if document[field] != value:
            core._fail(f"Recovery plan {field} does not match bound evidence.")
    return document, context


def _load_plan(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    return _validate_plan(_load_object(path, "recovery plan"))


def _receipt_path(plan_path: Path) -> Path:
    return plan_path.with_name(plan_path.name + ".receipt.json")


def _create_execution_claim(
    plan: dict[str, Any], environment: dict[str, str]
) -> tuple[Path, dict[str, Any]]:
    home = Path(environment["HOME"])
    uipath_root = home / ".uipath"
    if uipath_root.is_symlink() or not uipath_root.is_dir():
        core._fail("Recovery execution claim requires a real HOME/.uipath directory.")
    claim_root = uipath_root / "uipcodedappdeploy-recovery-claims"
    try:
        claim_root.mkdir(mode=0o700, exist_ok=True)
    except OSError as exc:
        core._fail(f"Could not prepare recovery execution claim directory: {type(exc).__name__}")
    if claim_root.is_symlink() or not claim_root.is_dir():
        core._fail("Recovery execution claim directory must be a real directory.")
    claim_key = plan["upgrade_guard"]["local_execution_claim_key"]
    core._validate_hash(claim_key, "Recovery execution claim key")
    claim_path = claim_root / (claim_key.removeprefix("sha256:") + ".json")
    claim = {
        "kind": "uipcodedappdeploy.upgrade-recovery-execution-claim",
        "schema_version": "1.0",
        "created_at": core._utc_now(),
        "plan_hash": plan["plan_hash"],
        "claim_key": claim_key,
        "claim_scope": plan["upgrade_guard"]["local_execution_claim_scope"],
        "deployment_id": plan["existing_deployment"]["deployment_id"],
        "candidate_version": plan["candidate"]["version"],
    }
    claim["claim_hash"] = core._document_hash(claim, "claim_hash")
    payload = json.dumps(claim, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    try:
        descriptor = os.open(
            claim_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        core._fail(
            "An execution claim already exists for this exact deployment candidate. "
            "Do not retry; reconcile remote state before creating a new reviewed plan."
        )
    except OSError as exc:
        core._fail(f"Could not create recovery execution claim: {type(exc).__name__}")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        directory_descriptor = os.open(claim_root, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as exc:
        core._fail(f"Could not persist recovery execution claim: {type(exc).__name__}")
    return claim_path, claim


def _unlink_exact_execution_claim(
    claim_path: Path, claim: dict[str, Any], expected_file_sha256: str
) -> None:
    observed = _load_object(claim_path, "recovery execution claim")
    if observed != claim or observed.get("claim_hash") != core._document_hash(
        observed, "claim_hash"
    ):
        core._fail("Recovery execution claim changed; refusing safe release.")
    if core._hash_file(
        claim_path, "recovery execution claim"
    ) != expected_file_sha256:
        core._fail("Recovery execution claim bytes changed; refusing safe release.")
    try:
        claim_path.unlink()
        directory_descriptor = os.open(claim_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as exc:
        core._fail(f"Could not release safe recovery execution claim: {type(exc).__name__}")


def _release_execution_claim(
    claim_path: Path,
    claim: dict[str, Any],
    receipt: dict[str, Any],
    receipt_path: Path,
) -> None:
    _unlink_exact_execution_claim(
        claim_path,
        claim,
        receipt["execution_claim_sha256"],
    )
    receipt["execution_claim_released"] = True
    _write_receipt(receipt_path, receipt)


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    receipt["updated_at"] = core._utc_now()
    receipt["receipt_hash"] = core._document_hash(receipt, "receipt_hash")
    core._atomic_write_json(path, receipt)


def _new_receipt(
    plan: dict[str, Any],
    approved_hash: str,
    execution_claim_path: Path,
    execution_claim: dict[str, Any],
) -> dict[str, Any]:
    now = core._utc_now()
    receipt = {
        "kind": RECEIPT_KIND,
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "plan_hash": plan["plan_hash"],
        "approved_plan_hash": approved_hash,
        "recovery_helper_sha256": plan["recovery_helper_sha256"],
        "core_helper_path": plan["core_helper_path"],
        "core_helper_sha256": plan["core_helper_sha256"],
        "evidence_binding_hash": plan["evidence_binding_hash"],
        "target": copy.deepcopy(plan["target"]),
        "existing_deployment": copy.deepcopy(plan["existing_deployment"]),
        "candidate": copy.deepcopy(plan["candidate"]),
        "upgrade_guard": copy.deepcopy(plan["upgrade_guard"]),
        "execution_claim_path": str(execution_claim_path),
        "execution_claim_sha256": core._hash_file(
            execution_claim_path, "recovery execution claim"
        ),
        "execution_claim_hash": execution_claim["claim_hash"],
        "execution_claim_released": False,
        "status": "in_progress",
        "started_at": now,
        "updated_at": now,
        "post_deploy_app_config_digest": None,
        "observed_local_app_url": None,
        "local_app_url_matches_verified_route": None,
        "pre_upgrade_guard_observation": None,
        "post_upgrade_guard_observation": None,
        "redaction": {
            "commands": "omitted",
            "environment": "omitted",
            "subprocess_output": "omitted",
            "errors": "generic_message_only",
        },
        "stages": [
            {"name": stage["name"], "effect": stage["effect"], "status": "pending"}
            for stage in plan["stages"]
        ],
    }
    receipt["receipt_hash"] = core._document_hash(receipt, "receipt_hash")
    return receipt


def _mark_running(receipt: dict[str, Any], index: int, path: Path) -> None:
    stage = receipt["stages"][index]
    stage["status"] = "running"
    stage["started_at"] = core._utc_now()
    stage.pop("finished_at", None)
    stage.pop("recovery", None)
    _write_receipt(path, receipt)


def _mark_succeeded(receipt: dict[str, Any], index: int, path: Path) -> None:
    stage = receipt["stages"][index]
    stage["status"] = "succeeded"
    stage["finished_at"] = core._utc_now()
    stage.pop("recovery", None)
    _write_receipt(path, receipt)


def _mark_failure(
    receipt: dict[str, Any],
    index: int,
    path: Path,
    *,
    external_write: bool,
    after_external_write: bool = False,
) -> None:
    stage = receipt["stages"][index]
    if external_write:
        stage["recovery"] = (
            "redacted_indeterminate_external_write; reconcile remote state; "
            "blind retry and republish prohibited"
        )
        receipt["status"] = "in_progress"
    elif after_external_write:
        stage["status"] = "failed"
        stage["finished_at"] = core._utc_now()
        stage["recovery"] = (
            "deployed_unverified; do not redeploy; reconcile the exact remote deployment"
        )
        receipt["status"] = "deployed_unverified"
    else:
        stage["status"] = "failed"
        stage["finished_at"] = core._utc_now()
        stage["recovery"] = "redacted_failure; create a new reviewed recovery plan"
        receipt["status"] = "failed"
    _write_receipt(path, receipt)


def _inspect_post_deploy_config(
    root: Path, plan: dict[str, Any], receipt: dict[str, Any]
) -> None:
    path = root / core.APP_CONFIG_RELATIVE_PATH
    document = _load_object(path, "post-deploy app config")
    expected = plan["existing_deployment"]
    if document.get("systemName") != expected["system_name"]:
        core._fail("Post-deploy app config systemName changed unexpectedly.")
    if document.get("deploymentId") not in (None, expected["deployment_id"]):
        core._fail("Post-deploy app config deploymentId changed unexpectedly.")
    if document.get("appName") != expected["package_name"]:
        core._fail("Post-deploy app config appName changed unexpectedly.")
    if document.get("displayName") != expected["app_name"]:
        core._fail("Post-deploy app config displayName changed unexpectedly.")
    if document.get("appType") != expected["app_type"]:
        core._fail("Post-deploy app config appType changed unexpectedly.")
    if document.get("appVersion") != plan["candidate"]["version"]:
        core._fail("Post-deploy app config does not reference the recovery version.")
    observed_url = document.get("appUrl")
    if observed_url != expected["app_url"]:
        core._fail("Post-deploy app config appUrl is not the preserved route.")
    receipt["post_deploy_app_config_digest"] = core._hash_file(path, "post-deploy app config")
    receipt["observed_local_app_url"] = observed_url
    receipt["local_app_url_matches_verified_route"] = observed_url == expected["app_url"]


def _validate_failed_app_config(root: Path, plan: dict[str, Any]) -> None:
    document = _load_object(
        root / core.APP_CONFIG_RELATIVE_PATH, "failed-release app config"
    )
    expected = plan["existing_deployment"]
    candidate = plan["candidate"]
    comparisons = {
        "appName": expected["package_name"],
        "displayName": expected["app_name"],
        "appType": expected["app_type"],
        "appVersion": candidate["version"],
        "systemName": expected["system_name"],
        "personalWorkspace": False,
    }
    for field, value in comparisons.items():
        if document.get(field) != value:
            core._fail(f"Failed-release app config {field} is not exactly bound.")
    if document.get("deploymentId") not in (None, expected["deployment_id"]):
        core._fail("Failed-release app config deploymentId conflicts with the target.")


def _validate_remote_guard_output(
    output: str,
    plan: dict[str, Any],
    *,
    expected_current_version: str,
) -> dict[str, Any]:
    try:
        document = json.loads(output)
    except json.JSONDecodeError:
        core._fail("Exact-upgrade remote guard did not return valid JSON.")
    if (
        not isinstance(document, dict)
        or set(document) != {"Result", "Code", "Data"}
        or document.get("Result") != "Success"
        or document.get("Code") != "DeployCompleted"
    ):
        core._fail("Exact-upgrade remote guard returned a non-success envelope.")
    data = document["Data"]
    if not isinstance(data, dict):
        core._fail("Exact-upgrade remote guard returned no result data.")
    remote_expected = {
        "DeploymentId": plan["upgrade_guard"]["deployment_id"],
        "SystemName": plan["upgrade_guard"]["system_name"],
        "DeployVersion": plan["upgrade_guard"]["deploy_version"],
        "CurrentVersion": expected_current_version,
        "RouteName": plan["upgrade_guard"]["route_name"],
        "Version": plan["candidate"]["version"],
        "AppName": plan["existing_deployment"]["app_name"],
        "AppUrl": plan["existing_deployment"]["app_url"],
        "Operation": "recovery_verify",
    }
    if set(data) != {"Message", *remote_expected}:
        core._fail("Exact-upgrade remote guard result fields are invalid.")
    if data.get("Message") != "Exact upgrade target verified; no mutation performed.":
        core._fail("Exact-upgrade remote guard message is invalid.")
    for field, value in remote_expected.items():
        if data.get(field) != value:
            core._fail(f"Exact-upgrade remote guard {field} mismatch.")
    return {
        "deploymentId": data["DeploymentId"],
        "systemName": data["SystemName"],
        "deployVersion": data["DeployVersion"],
        "currentVersion": data["CurrentVersion"],
        "routeName": data["RouteName"],
        "version": data["Version"],
        "appName": data["AppName"],
        "appUrl": data["AppUrl"],
        "operation": data["Operation"],
    }


def _run_capture_recovery(
    command: list[str], cwd: Path, environment: dict[str, str]
) -> str:
    core._log("+ " + shlex.join(command))
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        core._fail(f"Recovery read-only command failed: {type(exc).__name__}")
    return completed.stdout


def _validate_cli_with_node(
    root: Path,
    parameters: dict[str, Any],
    *,
    cli_executable: str,
    cli_executable_sha256: str,
    node_executable: str,
    environment: dict[str, str],
) -> None:
    cli = Path(cli_executable)
    if core._hash_file(cli, "UiPath CLI executable") != cli_executable_sha256:
        core._fail("UiPath CLI executable digest changed after plan approval.")
    version_output = _run_capture_recovery(
        [node_executable, str(cli), "--version"], root, environment
    )
    match = re.search(
        r"\b([0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?)\b",
        version_output,
    )
    if match is None or match.group(1) != parameters["cli_version"]:
        core._fail("UiPath CLI version does not match the approved recovery plan.")
    status_output = _run_capture_recovery(
        [
            node_executable,
            str(cli),
            "login",
            "status",
            "--profile",
            parameters["cli_profile"],
            "--output",
            "json",
        ],
        root,
        environment,
    )
    try:
        status = json.loads(status_output)
    except json.JSONDecodeError:
        core._fail("UiPath CLI profile status did not return valid JSON.")
    login_state = core._find_mapping_value(status, {"status"})
    if not isinstance(login_state, str) or login_state.lower() not in {
        "loggedin",
        "logged in",
        "authenticated",
    }:
        core._fail("UiPath CLI profile is not logged in.")
    for field, names in (
        ("org_id", {"organizationid", "organizationuid"}),
        ("tenant_id", {"tenantid", "tenantuid"}),
    ):
        expected = parameters[field]
        if expected is None:
            continue
        observed = core._find_mapping_value(status, names)
        if not isinstance(observed, str) or observed.lower() != expected.lower():
            core._fail(f"UiPath CLI profile {field} does not match the recovery plan.")


def _run_remote_guard(
    stage: dict[str, Any],
    plan: dict[str, Any],
    *,
    expected_current_version: str,
    environment: dict[str, str],
) -> dict[str, Any]:
    attempts = stage.get("attempts", 1)
    delays = stage.get("delays_seconds", [])
    if (
        not isinstance(attempts, int)
        or attempts < 1
        or not isinstance(delays, list)
        or len(delays) != attempts - 1
        or not all(isinstance(delay, int) and 0 <= delay <= 10 for delay in delays)
    ):
        core._fail("Exact-upgrade remote guard retry policy is invalid.")
    last_error: BaseException | None = None
    for attempt in range(attempts):
        try:
            output = _run_capture_recovery(
                stage["command"], Path(stage["cwd"]), environment
            )
            return _validate_remote_guard_output(
                output,
                plan,
                expected_current_version=expected_current_version,
            )
        except (Exception, SystemExit, KeyboardInterrupt) as exc:
            last_error = exc
            if attempt < len(delays):
                time.sleep(delays[attempt])
    if last_error is not None:
        raise last_error
    core._fail("Exact-upgrade remote guard exhausted without a result.")


def _revalidate_runtime_barrier(
    plan: dict[str, Any], context: dict[str, Any], environment: dict[str, str]
) -> None:
    if core._hash_file(Path(__file__), "recovery helper") != plan[
        "recovery_helper_sha256"
    ]:
        core._fail("Recovery helper changed before the upgrade barrier.")
    if core._hash_file(Path(core.__file__), "core helper") != plan[
        "core_helper_sha256"
    ]:
        core._fail("Recovery core helper changed before the upgrade barrier.")
    observed = _validate_runtime_manifest(
        context["runtime_manifest"],
        context["failed_plan"]["parameters"],
        environment,
    )
    expected_fields = {
        "root": plan["candidate"]["recovery_runtime_root"],
        "tree_sha256": plan["candidate"]["recovery_runtime_tree_sha256"],
        "workspace": plan["candidate"]["recovery_workspace"],
        "workspace_app_config_sha256": plan["candidate"][
            "recovery_workspace_app_config_sha256"
        ],
        "self_test": plan["candidate"]["recovery_runtime_self_test"],
        "node_executable": plan["candidate"]["recovery_node_executable"],
        "node_executable_sha256": plan["candidate"][
            "recovery_node_executable_sha256"
        ],
        "node_version": plan["candidate"]["recovery_node_version"],
        "cli_executable": plan["candidate"]["recovery_cli_executable"],
        "cli_executable_sha256": plan["candidate"][
            "recovery_cli_executable_sha256"
        ],
        "runtime_tool_file": plan["candidate"]["codedapp_tool_recovery_file"],
        "runtime_tool_file_sha256": plan["candidate"][
            "codedapp_tool_recovery_file_sha256"
        ],
        "runtime_tool_manifest_sha256": plan["candidate"][
            "codedapp_tool_recovery_manifest_sha256"
        ],
        "patch_contract_sha256": plan["candidate"]["patch_contract_sha256"],
    }
    for field, value in expected_fields.items():
        if observed[field] != value:
            core._fail(f"Recovery runtime barrier mismatch: {field}.")
    _validate_failed_app_config(Path(observed["workspace"]), plan)


def _preflight(
    plan: dict[str, Any], context: dict[str, Any], environment: dict[str, str]
) -> None:
    root = Path(plan["project_root"])
    failed_plan = context["failed_plan"]
    parameters = failed_plan["parameters"]
    core._validate_source(root, failed_plan, expected_input_state="versioned")
    observed_node = _resolve_node_runtime(
        plan["candidate"]["recovery_node_executable"], environment
    )
    if observed_node != {
        "executable": plan["candidate"]["recovery_node_executable"],
        "executable_sha256": plan["candidate"][
            "recovery_node_executable_sha256"
        ],
        "version": plan["candidate"]["recovery_node_version"],
    }:
        core._fail("Recovery Node.js runtime changed after plan approval.")
    node_executable = observed_node["executable"]
    _validate_cli_with_node(
        root,
        parameters,
        cli_executable=parameters["cli_executable"],
        cli_executable_sha256=parameters["cli_executable_sha256"],
        node_executable=node_executable,
        environment=environment,
    )
    _validate_cli_with_node(
        Path(plan["candidate"]["recovery_workspace"]),
        parameters,
        cli_executable=plan["candidate"]["recovery_cli_executable"],
        cli_executable_sha256=plan["candidate"]["recovery_cli_executable_sha256"],
        node_executable=node_executable,
        environment=environment,
    )
    core._validate_package(
        root,
        parameters,
        expected_file_digest=plan["candidate"]["package_file_digest"],
    )
    if parameters["app_config_binding_hash"] is not None:
        core._validate_bound_app_config(
            root,
            failed_plan["project"],
            parameters,
            expected_file_digest=context["failed_receipt"]["app_config_file_digest"],
        )
    _validate_failed_app_config(root, plan)
    workspace = Path(plan["candidate"]["recovery_workspace"])
    workspace_config = workspace / core.APP_CONFIG_RELATIVE_PATH
    if core._hash_file(workspace_config, "recovery workspace app config") != plan[
        "candidate"
    ]["recovery_workspace_app_config_sha256"]:
        core._fail("Recovery workspace app config changed after plan approval.")
    _validate_failed_app_config(workspace, plan)


def _execute(
    plan: dict[str, Any], context: dict[str, Any], plan_path: Path, approved_hash: str | None
) -> Path:
    if approved_hash != plan["plan_hash"]:
        core._fail("Execution requires --approved-plan-hash with the exact recovery plan hash.")
    receipt_path = _receipt_path(plan_path)
    if receipt_path.exists():
        core._fail(
            "Recovery receipt already exists. Blind resume is unsupported; reconcile remote "
            "state and create a new reviewed recovery plan."
        )
    root = Path(plan["project_root"])
    # Complete every read-only preflight before creating a receipt. A stale
    # login or local dependency failure can then be remediated without being
    # mistaken for an attempted external recovery write.
    environment = _recovery_environment()
    _preflight(plan, context, environment)
    execution_claim_path, execution_claim = _create_execution_claim(plan, environment)
    if receipt_path.exists():
        core._fail(
            "Recovery receipt appeared while claiming execution. Do not retry; "
            "reconcile the exact remote deployment."
        )
    receipt = _new_receipt(
        plan,
        approved_hash,
        execution_claim_path,
        execution_claim,
    )
    now = core._utc_now()
    receipt["stages"][0].update(
        {
            "status": "succeeded",
            "started_at": execution_claim["created_at"],
            "finished_at": execution_claim["created_at"],
        }
    )
    receipt["stages"][1].update(
        {"status": "succeeded", "started_at": now, "finished_at": now}
    )
    try:
        _write_receipt(receipt_path, receipt)
    except (Exception, SystemExit, KeyboardInterrupt):
        # No remote recovery operation has started, so this exact local claim
        # can be safely released for a newly reviewed plan.
        if execution_claim_path.exists():
            _unlink_exact_execution_claim(
                execution_claim_path,
                execution_claim,
                receipt["execution_claim_sha256"],
            )
        raise

    _mark_running(receipt, 2, receipt_path)
    try:
        receipt["pre_upgrade_guard_observation"] = _run_remote_guard(
            plan["stages"][2],
            plan,
            expected_current_version=plan["upgrade_guard"]["current_version"],
            environment=environment,
        )
    except (Exception, SystemExit, KeyboardInterrupt):
        _mark_failure(receipt, 2, receipt_path, external_write=False)
        _release_execution_claim(
            execution_claim_path,
            execution_claim,
            receipt,
            receipt_path,
        )
        raise
    _mark_succeeded(receipt, 2, receipt_path)

    _mark_running(receipt, 3, receipt_path)
    try:
        _revalidate_runtime_barrier(plan, context, environment)
    except (Exception, SystemExit, KeyboardInterrupt):
        _mark_failure(receipt, 3, receipt_path, external_write=False)
        _release_execution_claim(
            execution_claim_path,
            execution_claim,
            receipt,
            receipt_path,
        )
        raise
    _mark_succeeded(receipt, 3, receipt_path)

    _mark_running(receipt, 4, receipt_path)
    try:
        core._run(
            plan["stages"][4]["command"],
            Path(plan["stages"][4]["cwd"]),
            environment,
        )
    except (Exception, SystemExit, KeyboardInterrupt):
        _mark_failure(receipt, 4, receipt_path, external_write=True)
        raise
    _mark_succeeded(receipt, 4, receipt_path)

    _mark_running(receipt, 5, receipt_path)
    try:
        receipt["post_upgrade_guard_observation"] = _run_remote_guard(
            plan["stages"][5],
            plan,
            expected_current_version=plan["candidate"]["version"],
            environment=environment,
        )
    except (Exception, SystemExit, KeyboardInterrupt):
        _mark_failure(
            receipt, 5, receipt_path, external_write=False, after_external_write=True
        )
        raise
    _mark_succeeded(receipt, 5, receipt_path)

    _mark_running(receipt, 6, receipt_path)
    try:
        core._verify_url(
            plan["existing_deployment"]["app_url"],
            plan["stages"][6]["timeout_seconds"],
        )
    except (Exception, SystemExit, KeyboardInterrupt):
        _mark_failure(
            receipt, 6, receipt_path, external_write=False, after_external_write=True
        )
        raise
    _mark_succeeded(receipt, 6, receipt_path)

    _mark_running(receipt, 7, receipt_path)
    try:
        _inspect_post_deploy_config(
            Path(plan["candidate"]["recovery_workspace"]), plan, receipt
        )
    except (Exception, SystemExit, KeyboardInterrupt):
        _mark_failure(
            receipt, 7, receipt_path, external_write=False, after_external_write=True
        )
        raise
    _mark_succeeded(receipt, 7, receipt_path)
    receipt["status"] = "succeeded"
    _write_receipt(receipt_path, receipt)
    return receipt_path


def _write_plan(path: Path, plan: dict[str, Any]) -> None:
    resolved = path.expanduser().resolve()
    if resolved.exists():
        core._fail("--plan-output refuses to overwrite an existing file.")
    core._atomic_write_json(resolved, plan)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or execute an exact-hash deploy-only Coded App upgrade recovery."
    )
    parser.add_argument("--project-root")
    parser.add_argument("--prior-successful-plan")
    parser.add_argument("--prior-successful-receipt")
    parser.add_argument("--prior-successful-app-config")
    parser.add_argument("--failed-plan")
    parser.add_argument("--failed-receipt")
    parser.add_argument("--reconciliation-evidence")
    parser.add_argument("--recovery-runtime-manifest")
    parser.add_argument("--plan-output")
    parser.add_argument("--prepare-runtime-from-cli")
    parser.add_argument("--node-executable")
    parser.add_argument("--runtime-output")
    parser.add_argument("--runtime-manifest-output")
    parser.add_argument("--plan")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--approved-plan-hash")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def _planning_args(args: argparse.Namespace) -> bool:
    return any(getattr(args, label) for label in EVIDENCE_LABELS) or bool(
        args.project_root or args.plan_output
    )


def _render(plan: dict[str, Any], plan_path: Path | None) -> str:
    stages = "\n".join(
        "  - "
        + stage["name"]
        + ": "
        + (" ".join(stage["command"]) if "command" in stage else stage["action"])
        for stage in plan["stages"]
    )
    location = str(plan_path) if plan_path else "[not persisted]"
    return (
        "Deploy-only upgrade recovery plan; no pack, publish, version, or route change.\n"
        f"Plan schema: {plan['schema_version']}\n"
        f"Plan hash: {plan['plan_hash']}\n"
        f"Persisted plan: {location}\n"
        f"App: {plan['existing_deployment']['app_name']}\n"
        f"Existing deployment: {plan['existing_deployment']['deployment_id']}\n"
        f"Preserved route: {plan['existing_deployment']['app_url']}\n"
        f"Candidate: {plan['candidate']['package_path']} @ {plan['candidate']['version']}\n"
        f"Node: {plan['candidate']['recovery_node_executable']} @ "
        f"{plan['candidate']['recovery_node_version']}\n"
        f"Failed plan: {plan['failed_attempt']['plan_hash']}\n"
        "Stages:\n"
        f"{stages}\n"
        "Execution requires approval of the exact plan hash."
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    prepare_values = (
        args.prepare_runtime_from_cli,
        args.node_executable,
        args.runtime_output,
        args.runtime_manifest_output,
    )
    if any(prepare_values):
        if not all(prepare_values):
            core._fail(
                "Runtime preparation requires --prepare-runtime-from-cli, "
                "--node-executable, --runtime-output, and --runtime-manifest-output."
            )
        incompatible = (
            args.plan,
            args.execute,
            args.approved_plan_hash,
            args.project_root,
            args.plan_output,
            *(getattr(args, label) for label in EVIDENCE_LABELS),
        )
        if any(incompatible):
            core._fail("Runtime preparation cannot accompany plan or execution arguments.")
        manifest = _prepare_runtime(
            Path(args.prepare_runtime_from_cli),
            Path(args.node_executable),
            Path(args.runtime_output),
            Path(args.runtime_manifest_output),
        )
        print(
            json.dumps(manifest, indent=2, sort_keys=True)
            if args.format == "json"
            else (
                f"Guarded recovery runtime: {manifest['runtime']['root']}\n"
                f"Runtime tree: {manifest['runtime']['tree_sha256']}\n"
                f"Patched tool: {manifest['runtime']['codedapp_tool_file_sha256']}\n"
                f"Manifest hash: {manifest['manifest_hash']}"
            )
        )
        return 0
    if args.plan:
        if _planning_args(args):
            core._fail("Planning arguments cannot accompany an immutable --plan.")
        plan_path = Path(args.plan).expanduser().resolve()
        plan, context = _load_plan(plan_path)
        if args.execute:
            receipt_path = _execute(plan, context, plan_path, args.approved_plan_hash)
            result = {
                "kind": "uipcodedappdeploy.upgrade-recovery-result",
                "schema_version": "1.0",
                "status": "succeeded",
                "plan_hash": plan["plan_hash"],
                "receipt": str(receipt_path),
                "app_url": plan["existing_deployment"]["app_url"],
                "version": plan["candidate"]["version"],
            }
            print(json.dumps(result, indent=2, sort_keys=True) if args.format == "json" else _render(plan, plan_path))
            return 0
        if args.approved_plan_hash:
            core._fail("--approved-plan-hash is accepted only with --execute.")
        print(json.dumps(plan, indent=2, sort_keys=True) if args.format == "json" else _render(plan, plan_path))
        return 0

    if args.execute or args.approved_plan_hash:
        core._fail("Execution requires an immutable --plan and exact approval hash.")
    missing = [
        name
        for name in ("project_root", *EVIDENCE_LABELS, "plan_output")
        if not getattr(args, name)
    ]
    if missing:
        core._fail("Planning requires: " + ", ".join("--" + item.replace("_", "-") for item in missing))
    plan = _build_plan(args)
    plan_path = Path(args.plan_output).expanduser().resolve()
    _write_plan(plan_path, plan)
    print(json.dumps(plan, indent=2, sort_keys=True) if args.format == "json" else _render(plan, plan_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
