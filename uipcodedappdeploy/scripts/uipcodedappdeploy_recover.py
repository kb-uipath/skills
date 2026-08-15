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
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
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
PLAN_SCHEMA_VERSION = "1.3"
LEGACY_RECOVERY_SCHEMA_VERSION = "1.2"
RECEIPT_KIND = "uipcodedappdeploy.upgrade-recovery-receipt"
RECEIPT_SCHEMA_VERSION = "1.3"
RECONCILIATION_KIND = "uipcodedappdeploy.remote-reconciliation"
RECONCILIATION_SCHEMA_VERSION = "1.0"
RUNTIME_MANIFEST_KIND = "uipcodedappdeploy.guarded-runtime"
RUNTIME_MANIFEST_SCHEMA_VERSION = "1.2"
LEGACY_RUNTIME_MANIFEST_SCHEMA_VERSION = "1.1"
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

PREDECESSOR_CLOSURE_ALGORITHM = "canonical-artifact-closure-v1"
PREDECESSOR_TRUST_MODE = "explicit-hash-anchor-v1"
PREDECESSOR_MAX_DEPTH = 8
PREDECESSOR_MAX_FILES = 256
PREDECESSOR_MAX_TOTAL_BYTES = 1024 * 1024 * 1024
PREDECESSOR_MAX_FILE_BYTES = 256 * 1024 * 1024

PRIOR_RECOVERY_PLAN_FIELDS_V12 = {
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
PRIOR_RECOVERY_PLAN_FIELDS_V13 = PRIOR_RECOVERY_PLAN_FIELDS_V12 | {"predecessor"}
PRIOR_RECOVERY_RECEIPT_FIELDS_V12 = {
    "kind",
    "schema_version",
    "plan_hash",
    "approved_plan_hash",
    "recovery_helper_sha256",
    "core_helper_path",
    "core_helper_sha256",
    "evidence_binding_hash",
    "target",
    "existing_deployment",
    "candidate",
    "upgrade_guard",
    "execution_claim_path",
    "execution_claim_sha256",
    "execution_claim_hash",
    "execution_claim_released",
    "status",
    "started_at",
    "updated_at",
    "post_deploy_app_config_digest",
    "observed_local_app_url",
    "local_app_url_matches_verified_route",
    "pre_upgrade_guard_observation",
    "post_upgrade_guard_observation",
    "redaction",
    "stages",
    "receipt_hash",
}
PRIOR_RECOVERY_RECEIPT_FIELDS_V13 = PRIOR_RECOVERY_RECEIPT_FIELDS_V12 | {
    "predecessor"
}
PRIOR_RECOVERY_CANDIDATE_FIELDS = {
    "version",
    "system_name",
    "deploy_version",
    "source_sha",
    "package_path",
    "package_content_digest",
    "package_file_digest",
    "candidate_package_file_digest",
    "source_cli_executable",
    "source_cli_executable_sha256",
    "recovery_cli_executable",
    "recovery_cli_executable_sha256",
    "recovery_node_executable",
    "recovery_node_executable_sha256",
    "recovery_node_version",
    "cli_version",
    "cli_profile",
    "cli_profile_hash",
    "codedapp_tool_source_file",
    "codedapp_tool_source_file_sha256",
    "codedapp_tool_source_manifest",
    "codedapp_tool_source_manifest_sha256",
    "codedapp_tool_recovery_file",
    "codedapp_tool_recovery_file_sha256",
    "codedapp_tool_recovery_manifest",
    "codedapp_tool_recovery_manifest_sha256",
    "codedapp_tool_version",
    "codedapp_tool_git_head",
    "recovery_runtime_root",
    "recovery_runtime_tree_sha256",
    "recovery_runtime_manifest_hash",
    "recovery_workspace",
    "recovery_workspace_app_config_sha256",
    "recovery_runtime_self_test",
    "patch_algorithm",
    "patch_contract_sha256",
    "tags",
}
PRIOR_RECOVERY_STAGE_CONTRACT = (
    ("execution_claim", "claim_exact_candidate", "local_write"),
    ("reconcile", "validate_recovery", "local_read"),
    ("pre_upgrade_guard", "verify_exact_upgrade_target", "external_read"),
    ("runtime_barrier", "revalidate_guarded_runtime", "local_read"),
    ("upgrade", "command", "external_write"),
    ("post_upgrade_guard", "verify_exact_upgraded_target", "external_read"),
    ("verify", "verify_existing_url", "external_read"),
    ("post_deploy_metadata", "inspect_app_config", "local_read"),
)
RECOVERY_REDACTION_POLICY = {
    "commands": "omitted",
    "environment": "omitted",
    "subprocess_output": "omitted",
    "errors": "generic_message_only",
}


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


def _assert_no_symlink_ancestors(path: Path, label: str) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            mode = current.lstat().st_mode
        except OSError as exc:
            core._fail(f"Could not inspect {label}: {type(exc).__name__}")
        if stat.S_ISLNK(mode):
            core._fail(f"{label} may not contain a symlink component.")


def _new_closure_state() -> dict[str, Any]:
    return {"records": {}, "identities": {}, "total_bytes": 0}


def _read_bound_file(
    path: Path,
    label: str,
    *,
    state: dict[str, Any] | None = None,
    role: str | None = None,
    expected_sha256: str | None = None,
    capture_payload: bool = True,
) -> tuple[Path, bytes, os.stat_result]:
    if not path.is_absolute() or ".." in path.parts:
        core._fail(f"{label} path must be absolute and canonical.")
    _assert_no_symlink_ancestors(path, label)
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        core._fail(f"Could not resolve {label}: {type(exc).__name__}")
    if resolved != path:
        core._fail(f"{label} path must already be canonical.")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(resolved, flags)
    except OSError as exc:
        core._fail(f"Could not open {label}: {type(exc).__name__}")
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            core._fail(f"{label} must be a regular file.")
        if before.st_nlink != 1:
            core._fail(f"{label} must not have hard-link aliases.")
        if before.st_size > PREDECESSOR_MAX_FILE_BYTES:
            core._fail(f"{label} exceeds the predecessor evidence size limit.")
        chunks: list[bytes] = []
        hasher = hashlib.sha256()
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                core._fail(f"{label} changed while being read.")
            hasher.update(chunk)
            if capture_payload:
                chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            core._fail(f"{label} grew while being read.")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        core._fail(f"{label} changed while being read.")
    payload = b"".join(chunks) if capture_payload else b""
    digest = "sha256:" + hasher.hexdigest()
    if expected_sha256 is not None:
        core._validate_hash(expected_sha256, f"{label} expected hash")
        if digest != expected_sha256:
            core._fail(f"{label} bytes do not match the bound hash.")
    if state is not None:
        if not role:
            core._fail("Predecessor closure records require an evidence role.")
        canonical = str(resolved)
        identity = (before.st_dev, before.st_ino)
        aliased = state["identities"].get(identity)
        if aliased is not None and aliased != canonical:
            core._fail("Predecessor evidence contains a hard-link path alias.")
        state["identities"][identity] = canonical
        record = state["records"].get(canonical)
        if record is None:
            if len(state["records"]) >= PREDECESSOR_MAX_FILES:
                core._fail("Predecessor evidence exceeds the file-count limit.")
            if state["total_bytes"] + before.st_size > PREDECESSOR_MAX_TOTAL_BYTES:
                core._fail("Predecessor evidence exceeds the total-byte limit.")
            record = {
                "path": canonical,
                "sha256": digest,
                "size": before.st_size,
                "roles": [],
            }
            state["records"][canonical] = record
            state["total_bytes"] += before.st_size
        elif record["sha256"] != digest or record["size"] != before.st_size:
            core._fail("Predecessor evidence path has conflicting byte bindings.")
        if role not in record["roles"]:
            record["roles"].append(role)
    return resolved, payload, before


def _read_bound_json(
    path: Path,
    label: str,
    *,
    state: dict[str, Any] | None = None,
    role: str | None = None,
    expected_sha256: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    resolved, payload, _ = _read_bound_file(
        path,
        label,
        state=state,
        role=role,
        expected_sha256=expected_sha256,
    )
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        core._fail(f"Could not parse {label} JSON: {type(exc).__name__}")
    if not isinstance(document, dict):
        core._fail(f"{label} must contain a JSON object.")
    return resolved, document


def _finalize_closure(state: dict[str, Any]) -> dict[str, Any]:
    files = []
    for record in state["records"].values():
        normalized = copy.deepcopy(record)
        normalized["roles"] = sorted(normalized["roles"])
        files.append(normalized)
    files.sort(key=lambda item: item["path"])
    projection = {
        "algorithm": PREDECESSOR_CLOSURE_ALGORITHM,
        "files": files,
        "file_count": len(files),
        "total_bytes": state["total_bytes"],
    }
    projection["sha256"] = core._hash_json(projection)
    return projection


def _closure_file_record(state: dict[str, Any], path: Path) -> dict[str, Any]:
    record = state["records"].get(str(path.resolve(strict=True)))
    if record is None:
        core._fail("Predecessor closure is missing a required artifact.")
    return record


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


def _resolve_runtime_app_config_source(path: Path) -> tuple[Path, Path]:
    """Resolve one explicit candidate app config and its containing project."""

    expanded = path.expanduser()
    if not expanded.is_absolute():
        core._fail("Recovery runtime app-config source path must be absolute.")
    if expanded.is_symlink() or not expanded.is_file():
        core._fail(
            "Recovery runtime app-config source must be a regular non-symlink file."
        )
    resolved = expanded.resolve()
    if resolved.is_symlink() or not resolved.is_file():
        core._fail(
            "Recovery runtime app-config source must resolve to a regular non-symlink file."
        )
    project_root = resolved.parent.parent
    if resolved != project_root / core.APP_CONFIG_RELATIVE_PATH:
        core._fail(
            "Recovery runtime app-config source must be an exact "
            ".uipath/app.config.json project file."
        )
    _load_object(resolved, "recovery runtime app-config source")
    return resolved, project_root


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
    app_config_source: Path,
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
    if _paths_overlap(runtime_output, manifest_output):
        core._fail(
            "Recovery runtime and manifest outputs must be distinct and non-overlapping."
        )
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
    source_app_config, app_config_project_root = _resolve_runtime_app_config_source(
        app_config_source
    )
    if _paths_overlap(runtime_output, source_project_root):
        core._fail(
            "Recovery runtime output must be outside and disjoint from the source project."
        )
    if _paths_overlap(runtime_output, app_config_project_root):
        core._fail(
            "Recovery runtime output must be outside and disjoint from the "
            "app-config source project."
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
    try:
        manifest_output.relative_to(app_config_project_root)
    except ValueError:
        pass
    else:
        core._fail(
            "Recovery runtime manifest must not mutate the app-config source project."
        )
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
    source_app_config_sha256 = core._hash_file(
        source_app_config, "recovery runtime app-config source"
    )
    runtime_workspace = runtime_output / ISOLATED_WORKSPACE_RELATIVE
    runtime_app_config = runtime_workspace / core.APP_CONFIG_RELATIVE_PATH
    runtime_app_config.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_app_config, runtime_app_config)
    if core._hash_file(
        source_app_config, "recovery runtime app-config source"
    ) != source_app_config_sha256:
        core._fail("Recovery runtime app-config source changed while being copied.")
    if core._hash_file(
        runtime_app_config, "recovery workspace app config"
    ) != source_app_config_sha256:
        core._fail("Recovery workspace app config is not an exact source copy.")
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
            "app_config_source": str(source_app_config),
            "app_config_source_sha256": source_app_config_sha256,
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
        core._fail(f"Expected exactly one {name} stage in the bound plan.")
    return matches[0]


def _validate_prior_core_app_config(
    document: dict[str, Any], predecessor: dict[str, Any]
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
    parameters = predecessor["parameters"]
    expected = {
        "appName": parameters["package_name"],
        "displayName": parameters["app_name"],
        "appVersion": predecessor["version"],
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


def _require_absolute_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        core._fail(f"{label} must be an absolute path.")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        core._fail(f"{label} must be an absolute canonical path.")
    return value


def _validate_prior_recovery_target(target: Any) -> dict[str, Any]:
    expected_fields = {
        "environment",
        "control_plane_url",
        "organization_name",
        "organization_id",
        "tenant_name",
        "tenant_id",
        "folder_key",
        "client_id",
    }
    if not isinstance(target, dict) or set(target) != expected_fields:
        core._fail("Prior recovery target fields are invalid.")
    environment = target.get("environment")
    expected_environment = core.TARGET_ENVIRONMENTS.get(environment)
    if (
        expected_environment is None
        or target.get("control_plane_url")
        != expected_environment["control_plane_url"]
    ):
        core._fail("Prior recovery target environment is invalid.")
    for field in ("organization_name", "tenant_name"):
        if not isinstance(target.get(field), str) or not target[field]:
            core._fail(f"Prior recovery target {field} is invalid.")
    for field in ("organization_id", "tenant_id", "folder_key", "client_id"):
        value = target.get(field)
        if not isinstance(value, str) or core.GUID_RE.fullmatch(value) is None:
            core._fail(f"Prior recovery target {field} is invalid.")
    return target


def _validate_prior_recovery_existing(
    existing: Any, target: dict[str, Any]
) -> dict[str, Any]:
    expected_fields = {
        "app_name",
        "package_name",
        "app_type",
        "system_name",
        "deployment_id",
        "route_name",
        "app_url",
        "deployed_version",
    }
    if not isinstance(existing, dict) or set(existing) != expected_fields:
        core._fail("Prior recovery existing deployment fields are invalid.")
    for field in ("app_name", "package_name"):
        if not isinstance(existing.get(field), str) or not existing[field]:
            core._fail(f"Prior recovery existing deployment {field} is invalid.")
    if existing.get("app_type") not in ("Web", "Action"):
        core._fail("Prior recovery existing deployment app_type is invalid.")
    if (
        not isinstance(existing.get("system_name"), str)
        or core.APP_SYSTEM_NAME_RE.fullmatch(existing["system_name"]) is None
    ):
        core._fail("Prior recovery existing deployment system_name is invalid.")
    if (
        not isinstance(existing.get("deployment_id"), str)
        or core.GUID_RE.fullmatch(existing["deployment_id"]) is None
    ):
        core._fail("Prior recovery existing deployment deployment_id is invalid.")
    if (
        not isinstance(existing.get("route_name"), str)
        or core.PATH_NAME_RE.fullmatch(existing["route_name"]) is None
    ):
        core._fail("Prior recovery existing deployment route_name is invalid.")
    core._parse_semver(
        existing.get("deployed_version"),
        "Prior recovery existing deployment version",
    )
    expected_url = (
        f"https://{target['organization_name']}.{target['environment']}.uipath.host/"
        f"{existing['route_name']}"
    )
    if existing.get("app_url") != expected_url:
        core._fail("Prior recovery existing deployment app_url is invalid.")
    return existing


def _prior_recovery_expected_command(
    *,
    target: dict[str, Any],
    existing: dict[str, Any],
    candidate: dict[str, Any],
    guard: dict[str, Any],
) -> list[str]:
    command = [
        candidate["recovery_node_executable"],
        candidate["recovery_cli_executable"],
        "codedapp",
        "deploy",
    ]
    if existing["app_name"] == existing["package_name"]:
        command.extend(["--name", existing["package_name"]])
    command.extend(
        [
            "--version",
            candidate["version"],
            "--path-name",
            existing["route_name"],
            "--client-id",
            target["client_id"],
            "--tags",
            ",".join(candidate["tags"]),
            "--base-url",
            target["control_plane_url"],
            "--org-id",
            target["organization_id"],
            "--org-name",
            target["organization_name"],
            "--tenant-id",
            target["tenant_id"],
            "--profile",
            candidate["cli_profile"],
            "--folder-key",
            target["folder_key"],
            "--expected-deployment-id",
            guard["deployment_id"],
            "--expected-system-name",
            guard["system_name"],
            "--expected-deploy-version",
            str(guard["deploy_version"]),
            "--expected-current-version",
            guard["current_version"],
            "--expected-route-name",
            guard["route_name"],
        ]
    )
    return command


def _validate_prior_recovery_plan(
    document: dict[str, Any], *, schema_version: str
) -> dict[str, Any]:
    expected_fields = (
        PRIOR_RECOVERY_PLAN_FIELDS_V12
        if schema_version == LEGACY_RECOVERY_SCHEMA_VERSION
        else PRIOR_RECOVERY_PLAN_FIELDS_V13
    )
    if set(document) != expected_fields:
        core._fail(
            f"Prior recovery plan fields do not match schema {schema_version}."
        )
    if (
        document.get("kind") != PLAN_KIND
        or document.get("schema_version") != schema_version
    ):
        core._fail("Prior recovery plan kind or schema version is invalid.")
    _require_iso8601(document.get("created_at"), "Prior recovery plan created_at")
    for field in (
        "recovery_helper_sha256",
        "core_helper_sha256",
        "evidence_binding_hash",
        "plan_hash",
    ):
        core._validate_hash(document.get(field), f"Prior recovery plan {field}")
    _require_absolute_path(
        document.get("core_helper_path"), "Prior recovery core helper path"
    )
    if core._document_hash(document, "plan_hash") != document["plan_hash"]:
        core._fail("Prior recovery plan hash is invalid.")

    evidence = document.get("evidence")
    if not isinstance(evidence, list) or len(evidence) != len(EVIDENCE_LABELS):
        core._fail("Prior recovery plan evidence is incomplete.")
    for expected_label, record in zip(EVIDENCE_LABELS, evidence):
        if not isinstance(record, dict) or set(record) != {"label", "path", "sha256"}:
            core._fail("Prior recovery plan evidence record is invalid.")
        if record.get("label") != expected_label:
            core._fail("Prior recovery plan evidence order is invalid.")
        _require_absolute_path(
            record.get("path"), f"Prior recovery {expected_label} path"
        )
        core._validate_hash(
            record.get("sha256"), f"Prior recovery {expected_label} hash"
        )
    if core._hash_json(evidence) != document["evidence_binding_hash"]:
        core._fail("Prior recovery evidence binding hash is invalid.")

    project_root = _require_absolute_path(
        document.get("project_root"), "Prior recovery project root"
    )
    target = _validate_prior_recovery_target(document.get("target"))
    existing = _validate_prior_recovery_existing(
        document.get("existing_deployment"), target
    )

    candidate = document.get("candidate")
    if not isinstance(candidate, dict) or set(candidate) != PRIOR_RECOVERY_CANDIDATE_FIELDS:
        core._fail("Prior recovery candidate fields are invalid.")
    core._parse_semver(candidate.get("version"), "Prior recovery candidate version")
    if (
        not isinstance(candidate.get("system_name"), str)
        or core.APP_SYSTEM_NAME_RE.fullmatch(candidate["system_name"]) is None
    ):
        core._fail("Prior recovery candidate system_name is invalid.")
    if (
        isinstance(candidate.get("deploy_version"), bool)
        or not isinstance(candidate.get("deploy_version"), int)
        or candidate["deploy_version"] < 1
    ):
        core._fail("Prior recovery candidate deploy_version is invalid.")
    if (
        not isinstance(candidate.get("source_sha"), str)
        or core.SOURCE_SHA_RE.fullmatch(candidate["source_sha"]) is None
    ):
        core._fail("Prior recovery candidate source_sha is invalid.")
    if candidate.get("package_path") != core._package_path(
        existing["package_name"], candidate["version"]
    ):
        core._fail("Prior recovery candidate package_path is invalid.")
    hash_fields = (
        "package_content_digest",
        "package_file_digest",
        "candidate_package_file_digest",
        "source_cli_executable_sha256",
        "recovery_cli_executable_sha256",
        "recovery_node_executable_sha256",
        "cli_profile_hash",
        "codedapp_tool_source_file_sha256",
        "codedapp_tool_source_manifest_sha256",
        "codedapp_tool_recovery_file_sha256",
        "codedapp_tool_recovery_manifest_sha256",
        "recovery_runtime_tree_sha256",
        "recovery_runtime_manifest_hash",
        "recovery_workspace_app_config_sha256",
        "patch_contract_sha256",
    )
    for field in hash_fields:
        core._validate_hash(candidate.get(field), f"Prior recovery candidate {field}")
    path_fields = (
        "source_cli_executable",
        "recovery_cli_executable",
        "recovery_node_executable",
        "codedapp_tool_source_file",
        "codedapp_tool_source_manifest",
        "codedapp_tool_recovery_file",
        "codedapp_tool_recovery_manifest",
        "recovery_runtime_root",
        "recovery_workspace",
    )
    for field in path_fields:
        _require_absolute_path(candidate.get(field), f"Prior recovery candidate {field}")
    for field in ("recovery_node_version", "cli_version", "codedapp_tool_version"):
        core._parse_semver(candidate.get(field), f"Prior recovery candidate {field}")
    if candidate["cli_version"] != EXPECTED_CODEDAPP_TOOL_VERSION:
        core._fail("Prior recovery candidate CLI version is unsupported.")
    if not isinstance(candidate.get("cli_profile"), str) or not candidate["cli_profile"]:
        core._fail("Prior recovery candidate cli_profile is invalid.")
    expected_profile_hash = core._hash_json(
        {
            "name": candidate["cli_profile"],
            "environment": target["environment"],
            "control_plane_url": target["control_plane_url"],
            "org_id": target["organization_id"],
            "tenant_id": target["tenant_id"],
        }
    )
    if candidate["cli_profile_hash"] != expected_profile_hash:
        core._fail("Prior recovery candidate CLI profile binding is invalid.")
    if (
        candidate["source_cli_executable_sha256"]
        != candidate["recovery_cli_executable_sha256"]
    ):
        core._fail("Prior recovery source and guarded CLI digests differ.")
    if candidate["codedapp_tool_source_file_sha256"] != EXPECTED_CODEDAPP_TOOL_SHA256:
        core._fail("Prior recovery coded app tool digest is invalid.")
    if (
        candidate["codedapp_tool_source_manifest_sha256"]
        != candidate["codedapp_tool_recovery_manifest_sha256"]
    ):
        core._fail("Prior recovery coded app tool manifest digests differ.")
    if (
        candidate["codedapp_tool_version"] != EXPECTED_CODEDAPP_TOOL_VERSION
        or candidate["codedapp_tool_git_head"] != EXPECTED_CODEDAPP_TOOL_GIT_HEAD
        or candidate["patch_algorithm"] != PATCH_ALGORITHM
        or candidate["recovery_runtime_self_test"]
        != {
            "node_syntax": "passed",
            "dynamic_tool_resolution": "passed",
            "unguarded_deploy": "blocked_before_network",
            "verify_only_without_guard": "blocked_before_network",
        }
    ):
        core._fail("Prior recovery guarded runtime contract is invalid.")
    tags = candidate.get("tags")
    if (
        not isinstance(tags, list)
        or not tags
        or tags != sorted(set(tags))
        or any(
            not isinstance(tag, str) or core.PATH_NAME_RE.fullmatch(tag) is None
            for tag in tags
        )
    ):
        core._fail("Prior recovery candidate tags are invalid.")

    guard = document.get("upgrade_guard")
    expected_guard_fields = {
        "mode",
        "deployment_id",
        "system_name",
        "deploy_version",
        "current_version",
        "route_name",
        "fresh_deploy_prohibited",
        "routing_name_omitted_from_patch",
        "local_execution_claim_scope",
        "local_execution_claim_key",
    }
    if not isinstance(guard, dict) or set(guard) != expected_guard_fields:
        core._fail("Prior recovery upgrade guard fields are invalid.")
    expected_guard_values = {
        "mode": "exact_deployment_fail_closed_v1",
        "deployment_id": existing["deployment_id"],
        "system_name": candidate["system_name"],
        "deploy_version": candidate["deploy_version"],
        "current_version": existing["deployed_version"],
        "route_name": existing["route_name"],
        "fresh_deploy_prohibited": True,
        "routing_name_omitted_from_patch": True,
        "local_execution_claim_scope": "home_scoped_exact_candidate_v1",
    }
    for field, value in expected_guard_values.items():
        if guard.get(field) != value:
            core._fail(f"Prior recovery upgrade guard {field} is invalid.")
    if existing["system_name"] != candidate["system_name"]:
        core._fail("Prior recovery system identity is inconsistent.")
    claim_parameters = {
        "environment": target["environment"],
        "org_id": target["organization_id"],
        "tenant_id": target["tenant_id"],
        "folder_key": target["folder_key"],
    }
    expected_claim_key = _execution_claim_key(
        parameters=claim_parameters,
        deployment_id=existing["deployment_id"],
        system_name=candidate["system_name"],
        deploy_version=candidate["deploy_version"],
        candidate_version=candidate["version"],
    )
    if guard.get("local_execution_claim_key") != expected_claim_key:
        core._fail("Prior recovery execution claim key is invalid.")

    failed_attempt = document.get("failed_attempt")
    if not isinstance(failed_attempt, dict) or set(failed_attempt) != {
        "plan_hash",
        "approved_plan_hash",
        "deployment_binding_hash",
        "receipt_status",
        "recovery",
    }:
        core._fail("Prior recovery failed-attempt binding is invalid.")
    for field in ("plan_hash", "approved_plan_hash", "deployment_binding_hash"):
        core._validate_hash(
            failed_attempt.get(field), f"Prior recovery failed attempt {field}"
        )
    if (
        failed_attempt["approved_plan_hash"] != failed_attempt["plan_hash"]
        or failed_attempt.get("receipt_status") != "in_progress"
        or not isinstance(failed_attempt.get("recovery"), str)
        or "blind" not in failed_attempt["recovery"]
    ):
        core._fail("Prior recovery failed-attempt approval is invalid.")

    upgrade_command = _prior_recovery_expected_command(
        target=target,
        existing=existing,
        candidate=candidate,
        guard=guard,
    )
    expected_stages = [
        {
            "name": "execution_claim",
            "action": "claim_exact_candidate",
            "effect": "local_write",
        },
        {"name": "reconcile", "action": "validate_recovery", "effect": "local_read"},
        {
            "name": "pre_upgrade_guard",
            "action": "verify_exact_upgrade_target",
            "effect": "external_read",
            "cwd": candidate["recovery_workspace"],
            "command": _remote_guard_command(upgrade_command),
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
            "cwd": candidate["recovery_workspace"],
            "command": upgrade_command,
        },
        {
            "name": "post_upgrade_guard",
            "action": "verify_exact_upgraded_target",
            "effect": "external_read",
            "cwd": candidate["recovery_workspace"],
            "command": _remote_guard_command(
                upgrade_command, expected_current_version=candidate["version"]
            ),
            "attempts": 3,
            "delays_seconds": [1, 2],
        },
        {
            "name": "verify",
            "action": "verify_existing_url",
            "effect": "external_read",
            "url": existing["app_url"],
            "timeout_seconds": 30,
        },
        {
            "name": "post_deploy_metadata",
            "action": "inspect_app_config",
            "effect": "local_read",
        },
    ]
    if document.get("stages") != expected_stages:
        core._fail("Prior recovery stages do not match their projected candidate.")
    expected_execution = {
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
    }
    if document.get("execution") != expected_execution:
        core._fail("Prior recovery execution policy is invalid.")

    return {
        "kind": f"recovery_v{schema_version}",
        "schema_version": schema_version,
        "plan": document,
        "plan_hash": document["plan_hash"],
        "project_root": project_root,
        "version": candidate["version"],
        "parameters": {
            "environment": target["environment"],
            "control_plane_url": target["control_plane_url"],
            "tenant_name": target["tenant_name"],
            "tenant_id": target["tenant_id"],
            "org_id": target["organization_id"],
            "org_name": target["organization_name"],
            "folder_key": target["folder_key"],
            "package_name": existing["package_name"],
            "app_name": existing["app_name"],
            "app_type": existing["app_type"],
            "path_name": existing["route_name"],
            "client_id": target["client_id"],
            "tags": candidate["tags"],
            "cli_executable_sha256": candidate["source_cli_executable_sha256"],
            "cli_version": candidate["cli_version"],
            "cli_profile": candidate["cli_profile"],
            "cli_profile_hash": candidate["cli_profile_hash"],
        },
        "expected_deployment": {
            "system_name": candidate["system_name"],
            "deployment_id": existing["deployment_id"],
            "app_url": existing["app_url"],
        },
    }


def _validate_prior_guard_observation(
    observation: Any,
    *,
    plan: dict[str, Any],
    current_version: str,
    label: str,
) -> dict[str, Any]:
    expected = {
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
    if not isinstance(observation, dict) or observation != expected:
        core._fail(f"Prior recovery {label} does not match its exact guard.")
    return observation


def _validate_prior_recovery_receipt(
    document: dict[str, Any], predecessor: dict[str, Any]
) -> dict[str, Any]:
    plan = predecessor["plan"]
    schema_version = predecessor["schema_version"]
    expected_fields = (
        PRIOR_RECOVERY_RECEIPT_FIELDS_V12
        if schema_version == LEGACY_RECOVERY_SCHEMA_VERSION
        else PRIOR_RECOVERY_RECEIPT_FIELDS_V13
    )
    if set(document) != expected_fields:
        core._fail(
            f"Prior recovery receipt fields do not match schema {schema_version}."
        )
    if (
        document.get("kind") != RECEIPT_KIND
        or document.get("schema_version") != schema_version
    ):
        core._fail("Prior recovery receipt kind or schema version is invalid.")
    for field in (
        "plan_hash",
        "approved_plan_hash",
        "recovery_helper_sha256",
        "core_helper_sha256",
        "evidence_binding_hash",
        "execution_claim_sha256",
        "execution_claim_hash",
        "post_deploy_app_config_digest",
        "receipt_hash",
    ):
        core._validate_hash(document.get(field), f"Prior recovery receipt {field}")
    _require_absolute_path(
        document.get("core_helper_path"), "Prior recovery receipt core helper path"
    )
    _require_absolute_path(
        document.get("execution_claim_path"),
        "Prior recovery receipt execution claim path",
    )
    for field in ("started_at", "updated_at"):
        _require_iso8601(document.get(field), f"Prior recovery receipt {field}")
    if core._document_hash(document, "receipt_hash") != document["receipt_hash"]:
        core._fail("Prior recovery receipt hash is invalid.")
    expected_bindings = {
        "plan_hash": plan["plan_hash"],
        "approved_plan_hash": plan["plan_hash"],
        "recovery_helper_sha256": plan["recovery_helper_sha256"],
        "core_helper_path": plan["core_helper_path"],
        "core_helper_sha256": plan["core_helper_sha256"],
        "evidence_binding_hash": plan["evidence_binding_hash"],
        "target": plan["target"],
        "existing_deployment": plan["existing_deployment"],
        "candidate": plan["candidate"],
        "upgrade_guard": plan["upgrade_guard"],
    }
    if schema_version == PLAN_SCHEMA_VERSION:
        expected_bindings["predecessor"] = plan["predecessor"]
    for field, value in expected_bindings.items():
        if document.get(field) != value:
            core._fail(f"Prior recovery receipt {field} does not match its plan.")
    if document.get("status") != "succeeded":
        core._fail("Prior recovery receipt must be succeeded.")
    if document.get("execution_claim_released") is not False:
        core._fail("Prior recovery receipt must retain its exact-candidate claim.")
    claim_path = Path(document["execution_claim_path"])
    if claim_path.is_symlink() or not claim_path.is_file():
        core._fail("Prior recovery execution claim must remain a regular file.")
    if (
        core._hash_file(claim_path, "prior recovery execution claim")
        != document["execution_claim_sha256"]
    ):
        core._fail("Prior recovery execution claim bytes changed.")
    claim = _load_object(claim_path, "prior recovery execution claim")
    expected_claim_fields = {
        "kind",
        "schema_version",
        "created_at",
        "plan_hash",
        "claim_key",
        "claim_scope",
        "deployment_id",
        "candidate_version",
        "claim_hash",
    }
    if set(claim) != expected_claim_fields:
        core._fail("Prior recovery execution claim fields are invalid.")
    _require_iso8601(claim.get("created_at"), "Prior recovery execution claim created_at")
    expected_claim = {
        "kind": "uipcodedappdeploy.upgrade-recovery-execution-claim",
        "schema_version": "1.0",
        "plan_hash": plan["plan_hash"],
        "claim_key": plan["upgrade_guard"]["local_execution_claim_key"],
        "claim_scope": plan["upgrade_guard"]["local_execution_claim_scope"],
        "deployment_id": plan["existing_deployment"]["deployment_id"],
        "candidate_version": plan["candidate"]["version"],
    }
    for field, value in expected_claim.items():
        if claim.get(field) != value:
            core._fail(f"Prior recovery execution claim {field} is invalid.")
    if (
        claim.get("claim_hash") != core._document_hash(claim, "claim_hash")
        or document["execution_claim_hash"] != claim["claim_hash"]
    ):
        core._fail("Prior recovery execution claim self-hash is invalid.")
    if document.get("redaction") != RECOVERY_REDACTION_POLICY:
        core._fail("Prior recovery receipt redaction policy is invalid.")
    if (
        document.get("observed_local_app_url")
        != plan["existing_deployment"]["app_url"]
        or document.get("local_app_url_matches_verified_route") is not True
    ):
        core._fail("Prior recovery receipt local route verification is invalid.")
    _validate_prior_guard_observation(
        document.get("pre_upgrade_guard_observation"),
        plan=plan,
        current_version=plan["upgrade_guard"]["current_version"],
        label="pre-upgrade guard observation",
    )
    _validate_prior_guard_observation(
        document.get("post_upgrade_guard_observation"),
        plan=plan,
        current_version=plan["candidate"]["version"],
        label="post-upgrade guard observation",
    )
    stages = document.get("stages")
    if not isinstance(stages, list) or len(stages) != len(PRIOR_RECOVERY_STAGE_CONTRACT):
        core._fail("Prior recovery receipt stages are incomplete.")
    for stage, planned, contract in zip(stages, plan["stages"], PRIOR_RECOVERY_STAGE_CONTRACT):
        name, _action, effect = contract
        if (
            not isinstance(stage, dict)
            or not set(stage).issubset(
                {"name", "effect", "status", "started_at", "finished_at", "recovery"}
            )
            or stage.get("name") != name
            or stage.get("effect") != effect
            or stage.get("name") != planned.get("name")
            or stage.get("effect") != planned.get("effect")
            or stage.get("status") != "succeeded"
            or "started_at" not in stage
            or "finished_at" not in stage
            or "recovery" in stage
        ):
            core._fail("Prior recovery receipt must show every stage succeeded.")
        _require_iso8601(stage["started_at"], f"Prior recovery {name} started_at")
        _require_iso8601(stage["finished_at"], f"Prior recovery {name} finished_at")
    predecessor["receipt"] = document
    predecessor["post_deploy_app_config_digest"] = document[
        "post_deploy_app_config_digest"
    ]
    predecessor["deployment_identity_independently_bound"] = True
    return predecessor


def _normalize_prior_core_plan(
    plan: dict[str, Any], receipt: dict[str, Any]
) -> dict[str, Any]:
    if receipt.get("status") != "succeeded":
        core._fail("Prior deployment receipt must be succeeded.")
    parameters = plan["parameters"]
    return {
        "kind": "core_v2.3",
        "plan": plan,
        "receipt": receipt,
        "plan_hash": plan["plan_hash"],
        "project_root": plan["project"]["root"],
        "version": plan["project"]["new_version"],
        "parameters": {
            field: parameters[field]
            for field in (
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
        },
        "expected_deployment": None,
        "post_deploy_app_config_digest": None,
        "deployment_identity_independently_bound": False,
    }


def _load_predecessor(
    plan_path: Path,
    receipt_path: Path,
    *,
    trusted_recovery_helper_sha256: str | None = None,
    trusted_core_helper_sha256: str | None = None,
) -> dict[str, Any]:
    raw_plan = _load_object(plan_path, "prior successful plan")
    if (
        raw_plan.get("kind") == core.PLAN_KIND
        and raw_plan.get("schema_version") == core.PLAN_SCHEMA_VERSION
    ):
        if trusted_recovery_helper_sha256 or trusted_core_helper_sha256:
            core._fail(
                "Recovery predecessor trust hashes are invalid for a governed predecessor."
            )
        plan = core._load_plan(plan_path)
        receipt = core._load_receipt(receipt_path, plan)
        return _normalize_prior_core_plan(plan, receipt)
    if (
        raw_plan.get("kind") == PLAN_KIND
        and raw_plan.get("schema_version")
        in (LEGACY_RECOVERY_SCHEMA_VERSION, PLAN_SCHEMA_VERSION)
    ):
        if not trusted_recovery_helper_sha256 or not trusted_core_helper_sha256:
            core._fail(
                "A recovery predecessor requires both explicit trusted prior helper hashes."
            )
        core._validate_hash(
            trusted_recovery_helper_sha256,
            "Trusted prior recovery helper hash",
        )
        core._validate_hash(
            trusted_core_helper_sha256,
            "Trusted prior core helper hash",
        )
        if raw_plan.get("recovery_helper_sha256") != trusted_recovery_helper_sha256:
            core._fail("Prior recovery helper hash does not match the explicit trust anchor.")
        if raw_plan.get("core_helper_sha256") != trusted_core_helper_sha256:
            core._fail("Prior core helper hash does not match the explicit trust anchor.")
        schema_version = raw_plan["schema_version"]
        predecessor = _validate_prior_recovery_plan(
            raw_plan, schema_version=schema_version
        )
        receipt = _load_object(receipt_path, "prior successful recovery receipt")
        predecessor = _validate_prior_recovery_receipt(receipt, predecessor)
        predecessor["trusted_recovery_helper_sha256"] = (
            trusted_recovery_helper_sha256
        )
        predecessor["trusted_core_helper_sha256"] = trusted_core_helper_sha256
        return predecessor
    core._fail(
        "Prior successful evidence must be a governed v2.3 deployment or "
        "a successful schema-1.2 or schema-1.3 exact-upgrade recovery."
    )


def _validate_predecessor_app_config(
    path: Path, document: dict[str, Any], predecessor: dict[str, Any]
) -> dict[str, str]:
    if predecessor["kind"] == "core_v2.3":
        return _validate_prior_core_app_config(document, predecessor)

    expected_digest = predecessor["post_deploy_app_config_digest"]
    observed_digest = core._hash_file(path, "prior recovery post-deploy app config")
    if observed_digest != expected_digest:
        core._fail(
            "Prior recovery app config does not match its receipt post-deploy digest."
        )
    parameters = predecessor["parameters"]
    deployment = predecessor["expected_deployment"]
    expected = {
        "appName": parameters["package_name"],
        "displayName": parameters["app_name"],
        "appVersion": predecessor["version"],
        "systemName": deployment["system_name"],
        "appUrl": deployment["app_url"],
        "appType": parameters["app_type"],
        "personalWorkspace": False,
    }
    for field, value in expected.items():
        if document.get(field) != value:
            core._fail(f"Prior recovery app config {field} does not match its receipt.")
    config_deployment_id = document.get("deploymentId")
    _require_iso8601(document.get("deployedAt"), "Prior recovery app config deployedAt")
    if config_deployment_id is None:
        if not predecessor["deployment_identity_independently_bound"]:
            core._fail("Prior recovery app config is missing an independently bound deployment.")
    elif config_deployment_id != deployment["deployment_id"]:
        core._fail("Prior recovery app config deploymentId does not match its receipt.")
    return copy.deepcopy(deployment)


def _validate_sanctioned_failed_receipt(receipt: dict[str, Any]) -> None:
    if receipt.get("status") != "in_progress":
        core._fail("Nested failed receipt must remain in_progress and indeterminate.")
    deploy = _one_stage({"stages": receipt.get("stages", [])}, "deploy")
    if (
        deploy.get("status") != "running"
        or "blind resume prohibited" not in deploy.get("recovery", "")
    ):
        core._fail("Nested failed deploy stage is not the sanctioned route collision.")
    for name in ("publish", "app_config"):
        if _one_stage({"stages": receipt["stages"]}, name).get("status") != "succeeded":
            core._fail(f"Nested failed receipt {name} stage is incomplete.")


def _validate_recovery_claim(
    predecessor: dict[str, Any],
    *,
    state: dict[str, Any],
    role_prefix: str,
) -> tuple[Path, dict[str, Any]]:
    plan = predecessor["plan"]
    receipt = predecessor["receipt"]
    claim_path = Path(receipt["execution_claim_path"])
    home_value = os.environ.get("HOME")
    if not home_value:
        core._fail("Recovery predecessor claim validation requires HOME.")
    expected_root = (
        Path(home_value).expanduser().resolve()
        / ".uipath"
        / "uipcodedappdeploy-recovery-claims"
    )
    if claim_path.parent != expected_root:
        core._fail("Prior recovery claim is outside the home-scoped claim directory.")
    expected_name = (
        plan["upgrade_guard"]["local_execution_claim_key"].removeprefix("sha256:")
        + ".json"
    )
    if claim_path.name != expected_name:
        core._fail("Prior recovery claim filename does not match its exact candidate key.")
    _, claim = _read_bound_json(
        claim_path,
        "prior recovery execution claim",
        state=state,
        role=f"{role_prefix}.execution_claim",
        expected_sha256=receipt["execution_claim_sha256"],
    )
    expected_fields = {
        "kind",
        "schema_version",
        "created_at",
        "plan_hash",
        "claim_key",
        "claim_scope",
        "deployment_id",
        "candidate_version",
        "claim_hash",
    }
    if set(claim) != expected_fields:
        core._fail("Prior recovery execution claim fields are invalid.")
    expected = {
        "kind": "uipcodedappdeploy.upgrade-recovery-execution-claim",
        "schema_version": "1.0",
        "plan_hash": plan["plan_hash"],
        "claim_key": plan["upgrade_guard"]["local_execution_claim_key"],
        "claim_scope": plan["upgrade_guard"]["local_execution_claim_scope"],
        "deployment_id": plan["existing_deployment"]["deployment_id"],
        "candidate_version": plan["candidate"]["version"],
    }
    for field, value in expected.items():
        if claim.get(field) != value:
            core._fail(f"Prior recovery execution claim {field} is invalid.")
    _require_iso8601(claim.get("created_at"), "Prior recovery claim created_at")
    if (
        claim.get("claim_hash") != core._document_hash(claim, "claim_hash")
        or receipt.get("execution_claim_hash") != claim.get("claim_hash")
        or receipt.get("execution_claim_released") is not False
    ):
        core._fail("Prior recovery execution claim integrity is invalid.")
    return claim_path, claim


def _merge_bound_closure(
    state: dict[str, Any], closure: dict[str, Any], *, role_prefix: str
) -> None:
    if closure.get("algorithm") != PREDECESSOR_CLOSURE_ALGORITHM:
        core._fail("Nested predecessor closure algorithm is invalid.")
    files = closure.get("files")
    if not isinstance(files, list):
        core._fail("Nested predecessor closure files are invalid.")
    for record in files:
        if not isinstance(record, dict) or set(record) != {
            "path",
            "sha256",
            "size",
            "roles",
        }:
            core._fail("Nested predecessor closure record is invalid.")
        _read_bound_file(
            Path(record["path"]),
            "nested predecessor closure artifact",
            state=state,
            role=f"{role_prefix}.closure",
            expected_sha256=record["sha256"],
            capture_payload=False,
        )


def _binding_hash(block: dict[str, Any]) -> str:
    return core._document_hash(block, "binding_hash")


def _build_governed_predecessor_binding(
    predecessor: dict[str, Any],
    *,
    plan_path: Path,
    receipt_path: Path,
    app_config_path: Path,
) -> dict[str, Any]:
    state = _new_closure_state()
    plan_path, plan_document = _read_bound_json(
        plan_path,
        "governed predecessor plan",
        state=state,
        role="predecessor.plan",
    )
    receipt_path, receipt_document = _read_bound_json(
        receipt_path,
        "governed predecessor receipt",
        state=state,
        role="predecessor.receipt",
    )
    app_config_path, app_config_document = _read_bound_json(
        app_config_path,
        "governed predecessor app config",
        state=state,
        role="predecessor.app_config",
    )
    plan = core._validate_plan_document(plan_document)
    receipt = core._validate_receipt(receipt_document, plan)
    normalized = _normalize_prior_core_plan(plan, receipt)
    _validate_predecessor_app_config(app_config_path, app_config_document, normalized)
    closure = _finalize_closure(state)
    block = {
        "type": "governed",
        "trust": {"mode": "validated-core-v2.3"},
        "plan": {
            "kind": plan["kind"],
            "schema_version": plan["schema_version"],
            "plan_hash": plan["plan_hash"],
            "file_sha256": _closure_file_record(state, plan_path)["sha256"],
        },
        "receipt": {
            "kind": receipt["kind"],
            "schema_version": receipt["schema_version"],
            "receipt_hash": receipt["receipt_hash"],
            "approved_plan_hash": receipt["approved_plan_hash"],
            "status": receipt["status"],
            "file_sha256": _closure_file_record(state, receipt_path)["sha256"],
        },
        "app_config": {
            "path": str(app_config_path),
            "sha256": _closure_file_record(state, app_config_path)["sha256"],
        },
        "closure": closure,
    }
    block["binding_hash"] = _binding_hash(block)
    return block


def _normalize_nested_predecessor(
    plan_document: dict[str, Any],
    receipt_document: dict[str, Any],
    *,
    parent_plan: dict[str, Any],
) -> dict[str, Any]:
    if (
        plan_document.get("kind") == core.PLAN_KIND
        and plan_document.get("schema_version") == core.PLAN_SCHEMA_VERSION
    ):
        plan = core._validate_plan_document(plan_document)
        receipt = core._validate_receipt(receipt_document, plan)
        return _normalize_prior_core_plan(plan, receipt)
    if (
        plan_document.get("kind") == PLAN_KIND
        and plan_document.get("schema_version")
        in (LEGACY_RECOVERY_SCHEMA_VERSION, PLAN_SCHEMA_VERSION)
    ):
        if parent_plan.get("schema_version") != PLAN_SCHEMA_VERSION:
            core._fail("Schema-1.2 recovery cannot contain a recovery predecessor.")
        stored = parent_plan.get("predecessor")
        trust = stored.get("trust") if isinstance(stored, dict) else None
        if (
            not isinstance(trust, dict)
            or trust.get("mode") != PREDECESSOR_TRUST_MODE
        ):
            core._fail("Nested recovery predecessor trust block is invalid.")
        helper_hash = trust.get("recovery_helper_sha256")
        core_hash = trust.get("core_helper_sha256")
        core._validate_hash(helper_hash, "Nested trusted recovery helper hash")
        core._validate_hash(core_hash, "Nested trusted core helper hash")
        if (
            plan_document.get("recovery_helper_sha256") != helper_hash
            or plan_document.get("core_helper_sha256") != core_hash
        ):
            core._fail("Nested recovery predecessor does not match its trust anchors.")
        schema_version = plan_document["schema_version"]
        normalized = _validate_prior_recovery_plan(
            plan_document, schema_version=schema_version
        )
        normalized = _validate_prior_recovery_receipt(
            receipt_document, normalized
        )
        normalized["trusted_recovery_helper_sha256"] = helper_hash
        normalized["trusted_core_helper_sha256"] = core_hash
        return normalized
    core._fail("Nested predecessor kind or schema is unsupported.")


def _build_recovery_predecessor_binding(
    predecessor: dict[str, Any],
    *,
    plan_path: Path,
    receipt_path: Path,
    app_config_path: Path,
    depth: int = 0,
) -> dict[str, Any]:
    if depth >= PREDECESSOR_MAX_DEPTH:
        core._fail("Recovery predecessor chain exceeds the depth limit.")
    state = _new_closure_state()
    plan_path, plan_document = _read_bound_json(
        plan_path,
        "recovery predecessor plan",
        state=state,
        role="predecessor.plan",
    )
    receipt_path, receipt_document = _read_bound_json(
        receipt_path,
        "recovery predecessor receipt",
        state=state,
        role="predecessor.receipt",
    )
    app_config_path, app_config_document = _read_bound_json(
        app_config_path,
        "recovery predecessor app config",
        state=state,
        role="predecessor.app_config",
    )
    if plan_document != predecessor["plan"] or receipt_document != predecessor["receipt"]:
        core._fail("Recovery predecessor bytes changed during validation.")
    deployment = _validate_predecessor_app_config(
        app_config_path, app_config_document, predecessor
    )
    claim_path, claim = _validate_recovery_claim(
        predecessor, state=state, role_prefix="predecessor"
    )

    evidence = plan_document.get("evidence")
    if not isinstance(evidence, list) or len(evidence) != len(EVIDENCE_LABELS):
        core._fail("Recovery predecessor evidence set is incomplete.")
    if core._hash_json(evidence) != plan_document.get("evidence_binding_hash"):
        core._fail("Recovery predecessor evidence binding hash is invalid.")
    evidence_paths: dict[str, Path] = {}
    evidence_documents: dict[str, dict[str, Any]] = {}
    seen_paths: set[Path] = set()
    for expected_label, record in zip(EVIDENCE_LABELS, evidence):
        if (
            not isinstance(record, dict)
            or set(record) != {"label", "path", "sha256"}
            or record.get("label") != expected_label
        ):
            core._fail("Recovery predecessor evidence record is invalid.")
        path = Path(record["path"])
        if path in seen_paths:
            core._fail("Recovery predecessor evidence contains a duplicate path.")
        seen_paths.add(path)
        resolved, document = _read_bound_json(
            path,
            f"recovery predecessor {expected_label}",
            state=state,
            role=f"predecessor.evidence.{expected_label}",
            expected_sha256=record["sha256"],
        )
        evidence_paths[expected_label] = resolved
        evidence_documents[expected_label] = document

    nested = _normalize_nested_predecessor(
        evidence_documents["prior_successful_plan"],
        evidence_documents["prior_successful_receipt"],
        parent_plan=plan_document,
    )
    nested_app_config_path = evidence_paths["prior_successful_app_config"]
    if nested["kind"] == "core_v2.3":
        nested_block = _build_governed_predecessor_binding(
            nested,
            plan_path=evidence_paths["prior_successful_plan"],
            receipt_path=evidence_paths["prior_successful_receipt"],
            app_config_path=nested_app_config_path,
        )
    else:
        nested_block = _build_recovery_predecessor_binding(
            nested,
            plan_path=evidence_paths["prior_successful_plan"],
            receipt_path=evidence_paths["prior_successful_receipt"],
            app_config_path=nested_app_config_path,
            depth=depth + 1,
        )
    if plan_document["schema_version"] == PLAN_SCHEMA_VERSION:
        if plan_document.get("predecessor") != nested_block:
            core._fail("Stored recursive predecessor block does not match reopened evidence.")
    elif nested["kind"] != "core_v2.3":
        core._fail("Legacy recovery predecessor chain is not supported.")
    _merge_bound_closure(state, nested_block["closure"], role_prefix="predecessor.nested")

    failed_plan = core._validate_plan_document(evidence_documents["failed_plan"])
    failed_receipt = core._validate_receipt(
        evidence_documents["failed_receipt"], failed_plan
    )
    _validate_sanctioned_failed_receipt(failed_receipt)
    if (
        failed_plan["plan_hash"] != plan_document["failed_attempt"]["plan_hash"]
        or failed_receipt["approved_plan_hash"]
        != plan_document["failed_attempt"]["approved_plan_hash"]
    ):
        core._fail("Recovery predecessor failed-attempt files do not match its plan.")
    _validate_predecessor_release_binding(nested, failed_plan)
    nested_config = evidence_documents["prior_successful_app_config"]
    nested_deployment = _validate_predecessor_app_config(
        nested_app_config_path, nested_config, nested
    )
    reconciliation = _validate_reconciliation(
        evidence_documents["reconciliation_evidence"],
        predecessor=nested,
        failed_plan=failed_plan,
        failed_receipt=failed_receipt,
        deployment=nested_deployment,
        closure_state=state,
        reconciliation_path=evidence_paths["reconciliation_evidence"],
        role_prefix="predecessor.reconciliation",
    )
    historical_runtime = _validate_historical_runtime_manifest(
        evidence_documents["recovery_runtime_manifest"],
        predecessor_plan_schema=plan_document["schema_version"],
        trusted_preparer_sha256=predecessor[
            "trusted_recovery_helper_sha256"
        ],
        receipt=receipt_document,
        failed_plan=failed_plan,
        failed_receipt=failed_receipt,
        state=state,
        role_prefix="predecessor.runtime",
    )
    source_config = Path(historical_runtime["source_app_config"])
    if source_config != Path(failed_plan["project"]["root"]) / core.APP_CONFIG_RELATIVE_PATH:
        core._fail("Historical runtime source config does not match the failed project.")
    if historical_runtime["source_app_config_sha256"] != failed_receipt.get(
        "app_config_file_digest"
    ):
        core._fail("Historical runtime source config does not match the failed receipt.")
    if Path(historical_runtime["workspace_app_config"]) != app_config_path:
        core._fail("Recovery predecessor app config is not its guarded workspace config.")
    validation = {
        "package_name": failed_plan["parameters"]["package_name"],
        "app_name": failed_plan["parameters"]["app_name"],
        "app_type": failed_plan["parameters"]["app_type"],
        "version": failed_plan["project"]["new_version"],
        "system_name": deployment["system_name"],
        "deployment_id": deployment["deployment_id"],
    }
    _validate_candidate_app_config(source_config, **validation, label="Historical source app config")
    _validate_candidate_app_config(app_config_path, **validation, label="Historical post-deploy app config")
    expected_candidate = plan_document["candidate"]
    comparisons = {
        "system_name": reconciliation["candidate_system_name"],
        "deploy_version": reconciliation["candidate_deploy_version"],
        "recovery_runtime_root": historical_runtime["root"],
        "recovery_runtime_tree_sha256": historical_runtime["tree_sha256"],
        "recovery_runtime_manifest_hash": evidence_documents[
            "recovery_runtime_manifest"
        ]["manifest_hash"],
        "recovery_node_executable_sha256": historical_runtime[
            "node_executable_sha256"
        ],
        "recovery_cli_executable_sha256": historical_runtime[
            "cli_executable_sha256"
        ],
    }
    for field, value in comparisons.items():
        if expected_candidate.get(field) != value:
            core._fail(f"Recovery predecessor candidate {field} drifted.")

    closure = _finalize_closure(state)
    runtime_manifest_path = evidence_paths["recovery_runtime_manifest"]
    block = {
        "type": "recovery",
        "trust": {
            "mode": PREDECESSOR_TRUST_MODE,
            "recovery_helper_sha256": predecessor[
                "trusted_recovery_helper_sha256"
            ],
            "core_helper_sha256": predecessor["trusted_core_helper_sha256"],
        },
        "plan": {
            "kind": plan_document["kind"],
            "schema_version": plan_document["schema_version"],
            "plan_hash": plan_document["plan_hash"],
            "file_sha256": _closure_file_record(state, plan_path)["sha256"],
        },
        "receipt": {
            "kind": receipt_document["kind"],
            "schema_version": receipt_document["schema_version"],
            "receipt_hash": receipt_document["receipt_hash"],
            "approved_plan_hash": receipt_document["approved_plan_hash"],
            "status": receipt_document["status"],
            "file_sha256": _closure_file_record(state, receipt_path)["sha256"],
        },
        "app_config": {
            "path": str(app_config_path),
            "sha256": _closure_file_record(state, app_config_path)["sha256"],
        },
        "execution_claim": {
            "path": str(claim_path),
            "claim_hash": claim["claim_hash"],
            "file_sha256": _closure_file_record(state, claim_path)["sha256"],
            "retained": True,
        },
        "runtime_manifest": {
            "path": str(runtime_manifest_path),
            "manifest_hash": evidence_documents["recovery_runtime_manifest"][
                "manifest_hash"
            ],
            "file_sha256": _closure_file_record(state, runtime_manifest_path)[
                "sha256"
            ],
        },
        "closure": closure,
    }
    block["binding_hash"] = _binding_hash(block)
    return block


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
        "app_config_source",
        "app_config_source_sha256",
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
    source_app_config = Path(source.get("app_config_source", ""))
    if (
        not source_app_config.is_absolute()
        or source_app_config != source_app_config.resolve()
        or source_app_config.is_symlink()
        or not source_app_config.is_file()
    ):
        core._fail(
            "Recovery runtime app-config source must remain an absolute regular file."
        )
    app_config_project_root = source_app_config.parent.parent
    if source_app_config != app_config_project_root / core.APP_CONFIG_RELATIVE_PATH:
        core._fail("Recovery runtime app-config source path is invalid.")
    core._validate_hash(
        source.get("app_config_source_sha256"),
        "Recovery runtime app-config source digest",
    )
    if core._hash_file(
        source_app_config, "recovery runtime app-config source"
    ) != source.get("app_config_source_sha256"):
        core._fail("Recovery runtime app-config source changed after preparation.")

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
    source_project_root = Path(source["node_modules_root"]).parent
    if _paths_overlap(runtime_root, source_project_root):
        core._fail("Recovery runtime overlaps its source CLI project.")
    if _paths_overlap(runtime_root, app_config_project_root):
        core._fail("Recovery runtime overlaps its app-config source project.")
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
    if runtime.get("workspace_app_config_sha256") != source.get(
        "app_config_source_sha256"
    ):
        core._fail(
            "Recovery workspace app config does not match its bound source digest."
        )
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
        "source_app_config": str(source_app_config),
        "source_app_config_sha256": source["app_config_source_sha256"],
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


def _tree_digest_with_substitution(
    root: Path,
    *,
    substitute_path: Path,
    substitute_mode: int,
    substitute_size: int,
    substitute_sha256: str,
    label: str,
) -> str:
    if root.is_symlink() or not root.is_dir():
        core._fail(f"{label} must be a real directory, not a symlink.")
    try:
        substitute_path.relative_to(root)
    except ValueError:
        core._fail("Historical runtime substitution path escapes its runtime root.")
    records: list[dict[str, Any]] = []
    found_substitution = False
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            core._fail(f"{label} may not contain symlinks.")
        if path.is_dir():
            continue
        if not path.is_file():
            core._fail(f"{label} contains an unsupported filesystem entry.")
        if path == substitute_path:
            found_substitution = True
            mode = substitute_mode
            size = substitute_size
            digest = substitute_sha256
        else:
            observed = path.stat()
            mode = observed.st_mode & 0o777
            size = observed.st_size
            digest = core._hash_file(path, f"{label} file")
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "mode": mode,
                "size": size,
                "sha256": digest,
            }
        )
    if not found_substitution:
        core._fail("Historical runtime is missing its workspace app config.")
    return core._hash_json({"files": records})


def _validate_historical_runtime_manifest(
    document: dict[str, Any],
    *,
    predecessor_plan_schema: str,
    trusted_preparer_sha256: str,
    receipt: dict[str, Any],
    failed_plan: dict[str, Any],
    failed_receipt: dict[str, Any],
    state: dict[str, Any],
    role_prefix: str,
) -> dict[str, Any]:
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
        core._fail("Historical recovery runtime manifest fields are invalid.")
    schema_version = document.get("schema_version")
    if document.get("kind") != RUNTIME_MANIFEST_KIND or schema_version not in (
        LEGACY_RUNTIME_MANIFEST_SCHEMA_VERSION,
        RUNTIME_MANIFEST_SCHEMA_VERSION,
    ):
        core._fail("Historical recovery runtime manifest contract is invalid.")
    if (
        schema_version == LEGACY_RUNTIME_MANIFEST_SCHEMA_VERSION
        and predecessor_plan_schema != LEGACY_RECOVERY_SCHEMA_VERSION
    ):
        core._fail(
            "Only a schema-1.2 recovery predecessor may use a legacy runtime manifest."
        )
    _require_iso8601(document.get("created_at"), "Historical recovery runtime created_at")
    if document.get("preparer_sha256") != trusted_preparer_sha256:
        core._fail("Historical runtime preparer does not match the trust anchor.")
    if (
        document.get("patch_algorithm") != PATCH_ALGORITHM
        or document.get("patch_contract_sha256") != _patch_contract_hash()
    ):
        core._fail("Historical recovery runtime patch contract is invalid.")
    if core._document_hash(document, "manifest_hash") != document.get("manifest_hash"):
        core._fail("Historical recovery runtime manifest self-hash is invalid.")
    source = document.get("source")
    runtime = document.get("runtime")
    expected_source = {
        "node_modules_root",
        "cli_executable",
        "cli_executable_sha256",
        "codedapp_tool_file",
        "codedapp_tool_file_sha256",
        "codedapp_tool_manifest",
        "codedapp_tool_manifest_sha256",
        "codedapp_tool_version",
        "codedapp_tool_git_head",
    }
    if schema_version == RUNTIME_MANIFEST_SCHEMA_VERSION:
        expected_source |= {"app_config_source", "app_config_source_sha256"}
    expected_runtime = {
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
    }
    if not isinstance(source, dict) or set(source) != expected_source:
        core._fail("Historical recovery runtime source fields are invalid.")
    if not isinstance(runtime, dict) or set(runtime) != expected_runtime:
        core._fail("Historical recovery runtime output fields are invalid.")

    source_node_modules = Path(source["node_modules_root"])
    source_cli = Path(source["cli_executable"])
    source_tool = Path(source["codedapp_tool_file"])
    source_tool_manifest = Path(source["codedapp_tool_manifest"])
    if schema_version == RUNTIME_MANIFEST_SCHEMA_VERSION:
        source_app_config = Path(source["app_config_source"])
        source_app_config_sha256 = source["app_config_source_sha256"]
    else:
        source_app_config = source_node_modules.parent / core.APP_CONFIG_RELATIVE_PATH
        source_app_config_sha256 = failed_receipt.get("app_config_file_digest")
        core._validate_hash(
            source_app_config_sha256,
            "Historical legacy source app-config digest",
        )
    runtime_root = Path(runtime["root"])
    runtime_node_modules = Path(runtime["node_modules_root"])
    runtime_cli = Path(runtime["cli_executable"])
    runtime_tool = Path(runtime["codedapp_tool_file"])
    runtime_tool_manifest = Path(runtime["codedapp_tool_manifest"])
    runtime_workspace = Path(runtime["workspace"])
    runtime_app_config = Path(runtime["workspace_app_config"])
    runtime_node = Path(runtime["node_executable"])

    if source_cli.parents[3] != source_node_modules:
        core._fail("Historical recovery source CLI path is invalid.")
    failed_parameters = failed_plan["parameters"]
    if (
        source_cli != Path(failed_parameters["cli_executable"])
        or source.get("cli_executable_sha256")
        != failed_parameters["cli_executable_sha256"]
    ):
        core._fail("Historical recovery source CLI does not match the failed plan.")
    failed_project_root = Path(failed_plan["project"]["root"])
    if (
        source_node_modules.parent != failed_project_root
        or source_app_config != failed_project_root / core.APP_CONFIG_RELATIVE_PATH
    ):
        core._fail("Historical runtime source root does not match the failed project.")
    if source_tool != source_cli.parents[2] / "codedapp-tool" / "dist" / "tool.js":
        core._fail("Historical recovery source tool path is invalid.")
    if source_tool_manifest != source_cli.parents[2] / "codedapp-tool" / "package.json":
        core._fail("Historical recovery source tool manifest path is invalid.")
    if runtime_node_modules != runtime_root / "node_modules":
        core._fail("Historical recovery runtime node_modules path is invalid.")
    if runtime_cli != runtime_node_modules / "@uipath" / "cli" / "dist" / "index.js":
        core._fail("Historical recovery runtime CLI path is invalid.")
    if runtime_tool != runtime_node_modules / "@uipath" / "codedapp-tool" / "dist" / "tool.js":
        core._fail("Historical recovery runtime tool path is invalid.")
    if runtime_tool_manifest != runtime_node_modules / "@uipath" / "codedapp-tool" / "package.json":
        core._fail("Historical recovery runtime tool manifest path is invalid.")
    if runtime_workspace != runtime_root / ISOLATED_WORKSPACE_RELATIVE:
        core._fail("Historical recovery workspace path is invalid.")
    if runtime_app_config != runtime_workspace / core.APP_CONFIG_RELATIVE_PATH:
        core._fail("Historical recovery workspace app-config path is invalid.")

    _, source_cli_bytes, _ = _read_bound_file(
        source_cli,
        "historical recovery source CLI",
        state=state,
        role=f"{role_prefix}.source_cli",
        expected_sha256=source["cli_executable_sha256"],
    )
    _, runtime_cli_bytes, _ = _read_bound_file(
        runtime_cli,
        "historical recovery runtime CLI",
        state=state,
        role=f"{role_prefix}.runtime_cli",
        expected_sha256=runtime["cli_executable_sha256"],
    )
    if source_cli_bytes != runtime_cli_bytes:
        core._fail("Historical recovery source and runtime CLI bytes differ.")
    _, source_tool_bytes, _ = _read_bound_file(
        source_tool,
        "historical recovery source tool",
        state=state,
        role=f"{role_prefix}.source_tool",
        expected_sha256=source["codedapp_tool_file_sha256"],
    )
    if source["codedapp_tool_file_sha256"] != EXPECTED_CODEDAPP_TOOL_SHA256:
        core._fail("Historical recovery source tool digest is unsupported.")
    _, runtime_tool_bytes, _ = _read_bound_file(
        runtime_tool,
        "historical recovery runtime tool",
        state=state,
        role=f"{role_prefix}.runtime_tool",
        expected_sha256=runtime["codedapp_tool_file_sha256"],
    )
    if runtime_tool_bytes != _patched_tool_bytes(source_tool_bytes):
        core._fail("Historical guarded tool bytes do not match the deterministic patch.")
    _, source_manifest_document = _read_bound_json(
        source_tool_manifest,
        "historical recovery source tool manifest",
        state=state,
        role=f"{role_prefix}.source_tool_manifest",
        expected_sha256=source["codedapp_tool_manifest_sha256"],
    )
    _, runtime_manifest_document = _read_bound_json(
        runtime_tool_manifest,
        "historical recovery runtime tool manifest",
        state=state,
        role=f"{role_prefix}.runtime_tool_manifest",
        expected_sha256=runtime["codedapp_tool_manifest_sha256"],
    )
    if source_manifest_document != runtime_manifest_document:
        core._fail("Historical recovery tool manifests differ.")
    if (
        source_manifest_document.get("version") != EXPECTED_CODEDAPP_TOOL_VERSION
        or source_manifest_document.get("gitHead") != EXPECTED_CODEDAPP_TOOL_GIT_HEAD
        or source_manifest_document.get("main") != "./dist/tool.js"
        or source.get("codedapp_tool_version") != EXPECTED_CODEDAPP_TOOL_VERSION
        or source.get("codedapp_tool_git_head") != EXPECTED_CODEDAPP_TOOL_GIT_HEAD
    ):
        core._fail("Historical recovery tool identity is invalid.")
    _, _, source_app_config_stat = _read_bound_file(
        source_app_config,
        "historical recovery source app config",
        state=state,
        role=f"{role_prefix}.source_app_config",
        expected_sha256=source_app_config_sha256,
    )
    if runtime.get("workspace_app_config_sha256") != source_app_config_sha256:
        core._fail("Historical runtime pre-upgrade app-config binding is invalid.")
    _, _, _ = _read_bound_file(
        runtime_node,
        "historical recovery Node executable",
        state=state,
        role=f"{role_prefix}.node_executable",
        expected_sha256=runtime["node_executable_sha256"],
        capture_payload=False,
    )
    core._parse_semver(runtime.get("node_version"), "Historical recovery Node version")
    expected_self_test = {
        "node_syntax": "passed",
        "dynamic_tool_resolution": "passed",
        "unguarded_deploy": "blocked_before_network",
        "verify_only_without_guard": "blocked_before_network",
    }
    if runtime.get("self_test") != expected_self_test:
        core._fail("Historical recovery runtime self-test is invalid.")
    post_config_digest = receipt.get("post_deploy_app_config_digest")
    core._validate_hash(post_config_digest, "Historical post-deploy app-config digest")
    _read_bound_file(
        runtime_app_config,
        "historical recovery post-deploy app config",
        state=state,
        role=f"{role_prefix}.post_deploy_app_config",
        expected_sha256=post_config_digest,
    )
    reconstructed = _tree_digest_with_substitution(
        runtime_root,
        substitute_path=runtime_app_config,
        substitute_mode=source_app_config_stat.st_mode & 0o777,
        substitute_size=source_app_config_stat.st_size,
        substitute_sha256=source_app_config_sha256,
        label="historical recovery runtime",
    )
    if reconstructed != runtime.get("tree_sha256"):
        core._fail("Historical recovery runtime drifted outside the approved config mutation.")
    return {
        "root": str(runtime_root),
        "tree_sha256": runtime["tree_sha256"],
        "workspace": str(runtime_workspace),
        "workspace_app_config": str(runtime_app_config),
        "workspace_app_config_sha256": post_config_digest,
        "source_app_config": str(source_app_config),
        "source_app_config_sha256": source_app_config_sha256,
        "node_executable": str(runtime_node),
        "node_executable_sha256": runtime["node_executable_sha256"],
        "node_version": runtime["node_version"],
        "cli_executable": str(runtime_cli),
        "cli_executable_sha256": runtime["cli_executable_sha256"],
        "manifest_hash": document["manifest_hash"],
    }


def _validate_runtime_app_config_binding(
    runtime: dict[str, Any],
    *,
    failed_plan: dict[str, Any],
    failed_receipt: dict[str, Any],
    deployment: dict[str, str],
) -> None:
    """Bind the isolated runtime to the failed candidate's exact app config."""

    failed_root = Path(failed_plan["project"]["root"])
    expected_source = failed_root / core.APP_CONFIG_RELATIVE_PATH
    source_path = Path(runtime["source_app_config"])
    if source_path != expected_source:
        core._fail(
            "Recovery runtime app-config source does not match the failed project config."
        )
    if expected_source.is_symlink() or not expected_source.is_file():
        core._fail(
            "Failed-project app config must remain a regular non-symlink file."
        )
    source_digest = core._hash_file(
        expected_source, "failed-project runtime app-config source"
    )
    if source_digest != runtime["source_app_config_sha256"]:
        core._fail("Failed-project app config changed after runtime preparation.")
    receipt_digest = failed_receipt.get("app_config_file_digest")
    core._validate_hash(receipt_digest, "Failed receipt app-config file digest")
    if source_digest != receipt_digest:
        core._fail(
            "Recovery runtime app-config source does not match the failed receipt."
        )
    if runtime["workspace_app_config_sha256"] != source_digest:
        core._fail(
            "Recovery workspace app config does not match the failed candidate config."
        )

    parameters = failed_plan["parameters"]
    validation = {
        "package_name": parameters["package_name"],
        "app_name": parameters["app_name"],
        "app_type": parameters["app_type"],
        "version": failed_plan["project"]["new_version"],
        "system_name": deployment["system_name"],
        "deployment_id": deployment["deployment_id"],
    }
    _validate_candidate_app_config(
        expected_source,
        **validation,
        label="Runtime app-config source",
    )
    _validate_candidate_app_config(
        Path(runtime["workspace_app_config"]),
        **validation,
        label="Recovery workspace app config",
    )


def _validate_reconciliation(
    document: dict[str, Any],
    *,
    predecessor: dict[str, Any],
    failed_plan: dict[str, Any],
    failed_receipt: dict[str, Any],
    deployment: dict[str, str],
    closure_state: dict[str, Any] | None = None,
    reconciliation_path: Path | None = None,
    role_prefix: str = "reconciliation",
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
        "deployedVersionBeforeRecovery": predecessor["version"],
        "priorSuccessfulPlanHash": predecessor["plan_hash"],
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
    observed_documents: dict[str, dict[str, Any]] = {}
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
        if closure_state is None:
            if path.is_symlink() or not path.is_file():
                core._fail(f"Reconciliation observation is not a regular file: {name}.")
            if core._hash_file(path, f"reconciliation {name}") != observation["sha256"]:
                core._fail(f"Reconciliation observation changed: {name}.")
        else:
            if reconciliation_path is None:
                core._fail("Recursive reconciliation validation requires its source path.")
            try:
                path.relative_to(reconciliation_path.parent)
            except ValueError:
                core._fail("Reconciliation observation escapes its evidence directory.")
            _, observed_documents[name] = _read_bound_json(
                path,
                f"reconciliation {name}",
                state=closure_state,
                role=f"{role_prefix}.observation.{name}",
                expected_sha256=observation["sha256"],
            )
        observed_names.add(name)
        observed_paths[name] = path
    if not required_observations.issubset(observed_names):
        core._fail("Reconciliation is missing required remote observations.")
    probe = observed_documents.get("deployed app recovery probe") or _load_object(
        observed_paths["deployed app recovery probe"], "deployed app recovery probe"
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
        "CurrentVersion": predecessor["version"],
        "RouteName": parameters["path_name"],
        "Version": failed_plan["project"]["new_version"],
        "AppName": parameters["app_name"],
        "AppUrl": deployment["app_url"],
        "Operation": "recovery_verify",
    }
    for field, value in expected_probe.items():
        if probe_data.get(field) != value:
            core._fail(f"Deployed app recovery probe {field} does not match evidence.")
    package_observation = observed_documents.get(
        "published package candidate"
    ) or _load_object(
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


def _validate_predecessor_release_binding(
    predecessor: dict[str, Any], failed_plan: dict[str, Any]
) -> None:
    prior_parameters = predecessor["parameters"]
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
        "cli_executable_sha256",
        "cli_version",
        "cli_profile",
        "cli_profile_hash",
    )
    for field in immutable_fields:
        if prior_parameters[field] != failed_parameters[field]:
            core._fail(f"Recovery target drifted between deployments: {field}.")
    if predecessor["version"] == failed_plan["project"]["new_version"]:
        core._fail("Recovery candidate must differ from the prior deployed version.")
    if predecessor["project_root"] == failed_plan["project"]["root"]:
        core._fail("Recovery evidence must use separate immutable release workspaces.")


def _cross_validate_evidence(
    *,
    predecessor: dict[str, Any],
    prior_plan_path: Path,
    prior_receipt_path: Path,
    prior_app_config_path: Path,
    prior_app_config: dict[str, Any],
    failed_plan: dict[str, Any],
    failed_receipt: dict[str, Any],
    reconciliation: dict[str, Any],
    runtime_manifest: dict[str, Any],
) -> dict[str, Any]:
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

    _validate_predecessor_release_binding(predecessor, failed_plan)
    failed_parameters = failed_plan["parameters"]

    deployment = _validate_predecessor_app_config(
        prior_app_config_path, prior_app_config, predecessor
    )
    if predecessor["kind"] == "core_v2.3":
        predecessor_binding = _build_governed_predecessor_binding(
            predecessor,
            plan_path=prior_plan_path,
            receipt_path=prior_receipt_path,
            app_config_path=prior_app_config_path,
        )
    else:
        predecessor_binding = _build_recovery_predecessor_binding(
            predecessor,
            plan_path=prior_plan_path,
            receipt_path=prior_receipt_path,
            app_config_path=prior_app_config_path,
        )
    expected_url = (
        f"https://{failed_parameters['org_name']}."
        f"{failed_parameters['environment']}.uipath.host/{failed_parameters['path_name']}"
    )
    if deployment["app_url"] != expected_url:
        core._fail("Prior deployment URL does not match the approved environment and route.")
    reconciled = _validate_reconciliation(
        reconciliation,
        predecessor=predecessor,
        failed_plan=failed_plan,
        failed_receipt=failed_receipt,
        deployment=deployment,
    )
    runtime = _validate_runtime_manifest(runtime_manifest, failed_parameters)
    _validate_runtime_app_config_binding(
        runtime,
        failed_plan=failed_plan,
        failed_receipt=failed_receipt,
        deployment=deployment,
    )

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
        current_version=predecessor["version"],
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
        "predecessor_version": predecessor["version"],
        "predecessor_binding": predecessor_binding,
        "runtime": runtime,
    }


def _load_bound_evidence(
    evidence: list[dict[str, str]],
    *,
    trusted_recovery_helper_sha256: str | None = None,
    trusted_core_helper_sha256: str | None = None,
) -> dict[str, Any]:
    if not isinstance(evidence, list) or len(evidence) != len(EVIDENCE_LABELS):
        core._fail("Recovery plan evidence set is incomplete.")
    by_label: dict[str, Path] = {}
    for expected, record in zip(EVIDENCE_LABELS, evidence):
        path = _validate_evidence_record(record, expected)
        by_label[expected] = path
    predecessor = _load_predecessor(
        by_label["prior_successful_plan"],
        by_label["prior_successful_receipt"],
        trusted_recovery_helper_sha256=trusted_recovery_helper_sha256,
        trusted_core_helper_sha256=trusted_core_helper_sha256,
    )
    failed_plan = core._load_plan(by_label["failed_plan"])
    failed_receipt = core._load_receipt(by_label["failed_receipt"], failed_plan)
    prior_app_config = _load_object(by_label["prior_successful_app_config"], "prior app config")
    reconciliation = _load_object(by_label["reconciliation_evidence"], "reconciliation evidence")
    runtime_manifest = _load_object(
        by_label["recovery_runtime_manifest"], "recovery runtime manifest"
    )
    derived = _cross_validate_evidence(
        predecessor=predecessor,
        prior_plan_path=by_label["prior_successful_plan"],
        prior_receipt_path=by_label["prior_successful_receipt"],
        prior_app_config_path=by_label["prior_successful_app_config"],
        prior_app_config=prior_app_config,
        failed_plan=failed_plan,
        failed_receipt=failed_receipt,
        reconciliation=reconciliation,
        runtime_manifest=runtime_manifest,
    )
    return {
        "paths": by_label,
        "predecessor": predecessor,
        "prior_plan": predecessor["plan"],
        "prior_receipt": predecessor["receipt"],
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
        "predecessor": copy.deepcopy(context["predecessor_binding"]),
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
            "deployed_version": context["predecessor_version"],
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
            "current_version": context["predecessor_version"],
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
    context = _load_bound_evidence(
        evidence,
        trusted_recovery_helper_sha256=getattr(
            args, "trusted_prior_recovery_helper_sha256", None
        ),
        trusted_core_helper_sha256=getattr(
            args, "trusted_prior_core_helper_sha256", None
        ),
    )
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
        "predecessor",
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
    predecessor = document.get("predecessor")
    trust = predecessor.get("trust") if isinstance(predecessor, dict) else None
    context = _load_bound_evidence(
        document["evidence"],
        trusted_recovery_helper_sha256=(
            trust.get("recovery_helper_sha256") if isinstance(trust, dict) else None
        ),
        trusted_core_helper_sha256=(
            trust.get("core_helper_sha256") if isinstance(trust, dict) else None
        ),
    )
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
        "schema_version": plan["schema_version"],
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
    if plan["schema_version"] == PLAN_SCHEMA_VERSION:
        receipt["predecessor"] = copy.deepcopy(plan["predecessor"])
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


def _validate_candidate_app_config(
    path: Path,
    *,
    package_name: str,
    app_name: str,
    app_type: str,
    version: str,
    system_name: str,
    deployment_id: str,
    label: str,
) -> None:
    document = _load_object(path, label)
    comparisons = {
        "appName": package_name,
        "displayName": app_name,
        "appType": app_type,
        "appVersion": version,
        "systemName": system_name,
        "personalWorkspace": False,
    }
    for field, value in comparisons.items():
        if document.get(field) != value:
            core._fail(f"{label} {field} is not exactly bound to the candidate.")
    if document.get("deploymentId") not in (None, deployment_id):
        core._fail(f"{label} deploymentId conflicts with the recovery target.")


def _validate_failed_app_config(root: Path, plan: dict[str, Any]) -> None:
    expected = plan["existing_deployment"]
    candidate = plan["candidate"]
    _validate_candidate_app_config(
        root / core.APP_CONFIG_RELATIVE_PATH,
        package_name=expected["package_name"],
        app_name=expected["app_name"],
        app_type=expected["app_type"],
        version=candidate["version"],
        system_name=expected["system_name"],
        deployment_id=expected["deployment_id"],
        label="Failed-release app config",
    )


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
    trust = plan["predecessor"]["trust"]
    reopened = _load_bound_evidence(
        plan["evidence"],
        trusted_recovery_helper_sha256=trust.get(
            "recovery_helper_sha256"
        ),
        trusted_core_helper_sha256=trust.get("core_helper_sha256"),
    )
    if reopened["predecessor_binding"] != plan["predecessor"]:
        core._fail("Recovery predecessor closure changed before the upgrade barrier.")
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
    parser.add_argument("--trusted-prior-recovery-helper-sha256")
    parser.add_argument("--trusted-prior-core-helper-sha256")
    parser.add_argument("--failed-plan")
    parser.add_argument("--failed-receipt")
    parser.add_argument("--reconciliation-evidence")
    parser.add_argument("--recovery-runtime-manifest")
    parser.add_argument("--plan-output")
    parser.add_argument("--prepare-runtime-from-cli")
    parser.add_argument("--node-executable")
    parser.add_argument("--runtime-app-config-source")
    parser.add_argument("--runtime-output")
    parser.add_argument("--runtime-manifest-output")
    parser.add_argument("--plan")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--approved-plan-hash")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def _planning_args(args: argparse.Namespace) -> bool:
    return any(getattr(args, label) for label in EVIDENCE_LABELS) or bool(
        args.project_root
        or args.plan_output
        or args.trusted_prior_recovery_helper_sha256
        or args.trusted_prior_core_helper_sha256
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
        args.runtime_app_config_source,
        args.runtime_output,
        args.runtime_manifest_output,
    )
    if any(prepare_values):
        if not all(prepare_values):
            core._fail(
                "Runtime preparation requires --prepare-runtime-from-cli, "
                "--node-executable, --runtime-app-config-source, --runtime-output, "
                "and --runtime-manifest-output."
            )
        incompatible = (
            args.plan,
            args.execute,
            args.approved_plan_hash,
            args.project_root,
            args.plan_output,
            args.trusted_prior_recovery_helper_sha256,
            args.trusted_prior_core_helper_sha256,
            *(getattr(args, label) for label in EVIDENCE_LABELS),
        )
        if any(incompatible):
            core._fail("Runtime preparation cannot accompany plan or execution arguments.")
        manifest = _prepare_runtime(
            Path(args.prepare_runtime_from_cli),
            Path(args.node_executable),
            Path(args.runtime_app_config_source),
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
