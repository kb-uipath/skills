#!/usr/bin/env python3
"""Execute an explicitly authorized, synthetic-only Coded App test deployment.

This helper is intentionally separate from the governed v2.3 planner and the
v1.2 exact-upgrade recovery helper. It has no planning or resume mode. A direct
``--testing-only --execute`` invocation creates an automatic redacted receipt
before any external write. The receipt is never production release evidence.

The supported candidate matrix is deliberately narrow:

* ``dist`` + ``create`` copies and binds exact distribution bytes, proves that
  the deployment and route are absent, then packs, publishes, and deploys.
* ``dist`` + ``upgrade`` additionally binds an exact existing deployment,
  proves its route and current version before publication, reconciles the
  newly published candidate, and performs one guarded in-place upgrade whose
  PATCH cannot carry ``routingName``.
* ``reconciled`` + ``upgrade`` validates an existing v1.2 recovery plan and
  guarded runtime, then performs only its exact in-place deploy operation.
* ``published-recovery`` + ``upgrade`` consumes one exact retained testing
  receipt whose publish outcome was indeterminate, proves the already-
  published candidate without publishing again, then performs one guarded
  in-place upgrade.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import uipcodedappdeploy as core  # noqa: E402
import uipcodedappdeploy_recover as recovery  # noqa: E402


RECEIPT_KIND = "uipcodedappdeploy.testing-receipt"
RECEIPT_SCHEMA_VERSION = "1.2"
POLICY_VERSION = "1.2"
PUBLISH_RECOVERY_SOURCE_SCHEMA_VERSIONS = frozenset(("1.1", "1.2"))
EXPECTED_CLI_VERSION = "1.198.0"
EXPECTED_CLI_GIT_HEAD = "1fadf03d7a8dd102742571dff569fdac11808afb"
EXPECTED_CLI_SHA256 = (
    "sha256:688c4d3b3c02fbfdf060792fc7bd750b438cbbb2930bde85f0bad270d50df0d6"
)
EXPECTED_CLI_MANIFEST_SHA256 = (
    "sha256:3f9c65c51f4f24a921335916383de0cc75681afe64d261901eb95c2c3ca86484"
)
EXPECTED_CODEDAPP_TOOL_MANIFEST_SHA256 = (
    "sha256:064075bdb71dabee4379c1ddf96ead3dadbb051bde0932d49e00c7b3b8cfb03f"
)
SUPPORTED_NODE_RUNTIMES = {
    "24.13.0": "sha256:aed3321cf1a2ad333514339e8f7fc58a01ed9b6ac0d1325cd052260004928287",
}
CREATE_GUARD_PATCH_ALGORITHM = "uipath-codedapp-tool-1.198.0-testing-deploy-guard-v2"
CREATE_GUARD_RUNTIME_KIND = "uipcodedappdeploy.testing-create-guard-runtime"
CREATE_GUARD_RUNTIME_VERSION = "1.1"

WAIVED_GATES = [
    "clean_git_release_provenance",
    "independent_release_approval",
    "protected_release_environment",
    "signed_release_receipt",
    "second_plan_hash_approval",
    "full_build_and_test_rerun_for_exact_candidate",
    "production_services_absent_from_mockup",
]

NONWAIVABLE_CONTROLS = [
    "alpha_or_staging_only",
    "synthetic_data_only",
    "internal_authenticated_acceptance_required",
    "exact_target_cli_profile_and_artifact",
    "explicit_create_or_upgrade",
    "no_route_mutation_or_recreation",
    "no_blind_retry_or_resume",
    "host_local_atomic_candidate_claim",
    "redacted_automatic_receipt",
    "post_deploy_verification",
]

# These full-line hashes bind six reviewed, non-secret security-test fixtures
# to their exact repository-relative paths.  One is a lexical false positive
# from a synthetic token-provider call; five are deliberate rejection
# sentinels.  Matching only the regex finding would permit suffix smuggling, so
# the complete raw line and exact path are committed here.  Package, dist,
# configuration, and command audits never use these source-only commitments.
KNOWN_SYNTHETIC_SOURCE_LINES = {
    "apps/frontend/src/uipath/commandGateway.v0.test.ts": frozenset(
        {"sha256:6f6f174c1fa885d37799853a1664f622fba5b394edd28c9dea55fae0749f2d78"}
    ),
    "release/certification/test/certification.test.mjs": frozenset(
        {"sha256:9f7e96fd5cfa451d4e8ebb679c36d38ce0bd475084c9a92c25329bffca69c3ae"}
    ),
    "release/config/validate-release-profile.test.mjs": frozenset(
        {
            "sha256:f55bde8c5ca374ddc0badcc3f44e3e6292bcd4bfa1fb60992d0d9b507283794e",
            "sha256:79e195a7cec16c008ab335d6440173d88125493733e4a2eeaf676b0aadd3547f",
        }
    ),
    "release/test/package-inspection.test.mjs": frozenset(
        {
            "sha256:8b7f7fb824aaff6fc06460533233d72adef959741ddb7af7e0d060ff3e8fdb1b",
            "sha256:59fa57a9330fa68e54e1a2bf26a772bb75e87f601d9634255b785c0d08a54b2a",
        }
    ),
}

REDACTION = {
    "commands": "omitted",
    "environment": "omitted",
    "subprocess_output": "omitted",
    "errors": "stable_code_only",
    "secrets": "prohibited",
}

DIST_STAGE_CONTRACT = [
    ("local_preflight", "local_read"),
    ("dist_copy", "local_write"),
    ("pack", "local_write"),
    ("package_audit", "local_read"),
    ("runtime_prepare", "local_write"),
    ("pre_guard_barrier", "local_read"),
    ("create_absence_guard", "external_read"),
    ("pre_publish_barrier", "local_read"),
    ("publish", "external_write"),
    ("app_config_bind", "local_write"),
    ("pre_deploy_barrier", "local_read"),
    ("deploy", "external_write"),
    ("post_create_guard", "external_read"),
    ("route_verify", "external_read"),
    ("config_verify", "local_read"),
]

DIST_UPGRADE_STAGE_CONTRACT = [
    ("local_preflight", "local_read"),
    ("dist_copy", "local_write"),
    ("pack", "local_write"),
    ("package_audit", "local_read"),
    ("runtime_prepare", "local_write"),
    ("pre_guard_barrier", "local_read"),
    ("upgrade_pre_guard", "external_read"),
    ("pre_publish_barrier", "local_read"),
    ("publish", "external_write"),
    ("app_config_bind", "local_write"),
    ("published_candidate_guard", "external_read"),
    ("pre_deploy_barrier", "local_read"),
    ("deploy", "external_write"),
    ("upgrade_post_guard", "external_read"),
    ("route_verify", "external_read"),
    ("config_verify", "local_read"),
]

RECONCILED_STAGE_CONTRACT = [
    ("local_preflight", "local_read"),
    ("remote_pre_guard", "external_read"),
    ("runtime_barrier", "local_read"),
    ("deploy", "external_write"),
    ("remote_post_guard", "external_read"),
    ("route_verify", "external_read"),
    ("config_verify", "local_read"),
]

PUBLISHED_RECOVERY_STAGE_CONTRACT = [
    ("local_preflight", "local_read"),
    ("claim_transition", "local_write"),
    ("profile_guard", "external_read"),
    ("remote_candidate_guard", "external_read"),
    ("pre_deploy_barrier", "local_read"),
    ("deploy", "external_write"),
    ("remote_post_guard", "external_read"),
    ("route_verify", "external_read"),
    ("config_verify", "local_read"),
]

CREATE_GUARD_PATCH_EDITS = (
    (
        """async function executeDeploy(options) {
  const logger3 = options.logger ?? {""",
        """async function executeDeploy(options) {
  const testingCreateMode = options.testingCreateMode;
  const testingUpgradeMode = testingCreateMode?.startsWith(\"upgrade-\");
  if (![\"verify\", \"execute\", \"post\", \"upgrade-pre\", \"upgrade-candidate\", \"upgrade-execute\", \"upgrade-post\"].includes(testingCreateMode)) {
    throw new Error(\"TESTING_CREATE_GUARD_REQUIRED: this isolated runtime cannot mutate apps\");
  }
  const testingExpectedDeploymentId = options.testingExpectedDeploymentId;
  const testingExpectedSystemName = options.testingExpectedSystemName;
  const testingExpectedDeployVersion = options.testingExpectedDeployVersion;
  const testingExpectedCurrentVersion = options.testingExpectedCurrentVersion;
  const testingExpectedRouteName = options.testingExpectedRouteName;
  if (testingCreateMode === \"post\" && (!/^[0-9a-fA-F-]{36}$/.test(testingExpectedDeploymentId ?? \"\") || !/^ID[0-9a-fA-F]{32}$/.test(testingExpectedSystemName ?? \"\") || !/^[1-9][0-9]*$/.test(testingExpectedDeployVersion ?? \"\"))) {
    throw new Error(\"TESTING_CREATE_POST_GUARD_REQUIRED\");
  }
  if (testingUpgradeMode && (!/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(testingExpectedDeploymentId ?? \"\") || !testingExpectedCurrentVersion || !testingExpectedRouteName)) {
    throw new Error(\"TESTING_UPGRADE_TARGET_GUARD_REQUIRED\");
  }
  if (testingUpgradeMode && testingCreateMode !== \"upgrade-pre\" && (!/^ID[0-9a-fA-F]{32}$/.test(testingExpectedSystemName ?? \"\") || !/^[1-9][0-9]*$/.test(testingExpectedDeployVersion ?? \"\"))) {
    throw new Error(\"TESTING_UPGRADE_CANDIDATE_GUARD_REQUIRED\");
  }
  const logger3 = options.logger ?? {""",
    ),
    (
        """    const deployedApp = await getDeployedApp(appName, displayTitle, envConfig);
    let operationResult;""",
        """    const deployedApp = await getDeployedApp(appName, displayTitle, envConfig);
    if (testingUpgradeMode) {
      if (!deployedApp || deployedApp.id !== testingExpectedDeploymentId) {
        throw new Error(\"TESTING_UPGRADE_TARGET_MISMATCH: fresh deploy prohibited\");
      }
      if (deployedApp.title !== appName && deployedApp.title !== displayTitle) {
        throw new Error(\"TESTING_UPGRADE_TITLE_MISMATCH\");
      }
      if (deployedApp.routingName !== testingExpectedRouteName || deployedApp.semVersion !== testingExpectedCurrentVersion) {
        throw new Error(\"TESTING_UPGRADE_ROUTE_OR_VERSION_MISMATCH\");
      }
      if (testingCreateMode === \"upgrade-pre\") {
        return {
          appName: displayTitle,
          appUrl: buildAppUrl(envConfig.baseUrl, envConfig.orgName, deployedApp.routingName),
          version: options.version,
          deploymentId: deployedApp.id,
          systemName: null,
          deployVersion: null,
          currentVersion: deployedApp.semVersion,
          routeName: deployedApp.routingName,
          operation: \"testing_upgrade_pre\"
        };
      }
    }
    if (testingCreateMode === \"post\") {
      if (!deployedApp || deployedApp.id !== testingExpectedDeploymentId) {
        throw new Error(\"TESTING_CREATE_POST_DEPLOYMENT_MISMATCH\");
      }
      if (deployedApp.routingName !== routingName || deployedApp.semVersion !== options.version) {
        throw new Error(\"TESTING_CREATE_POST_ROUTE_OR_VERSION_MISMATCH\");
      }
      const publishedApp = await getPublishedAppWithRetry(appName, envConfig, options.version, () => {});
      if (!publishedApp || publishedApp.systemName !== testingExpectedSystemName || String(publishedApp.deployVersion) !== testingExpectedDeployVersion) {
        throw new Error(\"TESTING_CREATE_POST_CANDIDATE_MISMATCH\");
      }
      return {
        appName: displayTitle,
        appUrl: buildAppUrl(envConfig.baseUrl, envConfig.orgName, routingName),
        version: options.version,
        deploymentId: deployedApp.id,
        systemName: publishedApp.systemName,
        deployVersion: publishedApp.deployVersion,
        currentVersion: deployedApp.semVersion,
        routeName: deployedApp.routingName,
        operation: \"testing_create_post\"
      };
    }
    if (deployedApp && !testingUpgradeMode) {
      throw new Error(\"TESTING_CREATE_DEPLOYMENT_EXISTS\");
    }
    if (!testingUpgradeMode) {
      await checkAppNameUniqueness(routingName, envConfig);
    }
    if (testingCreateMode === \"verify\") {
      return {
        appName: displayTitle,
        appUrl: buildAppUrl(envConfig.baseUrl, envConfig.orgName, routingName),
        version: options.version ?? null,
        deploymentId: null,
        systemName: null,
        deployVersion: null,
        currentVersion: null,
        routeName: routingName,
        operation: \"testing_create_verify\"
      };
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
      if (testingUpgradeMode && (publishedApp.systemName !== testingExpectedSystemName || String(publishedApp.deployVersion) !== testingExpectedDeployVersion)) {
        throw new Error(\"TESTING_UPGRADE_CANDIDATE_MISMATCH\");
      }
      if (testingCreateMode === \"upgrade-candidate\" || testingCreateMode === \"upgrade-post\") {
        return {
          appName: displayTitle,
          appUrl: buildAppUrl(envConfig.baseUrl, envConfig.orgName, deployedApp.routingName),
          version: publishedApp.definition?.codedAppMetadata?.packageVersion,
          deploymentId: deployedApp.id,
          systemName: publishedApp.systemName,
          deployVersion: publishedApp.deployVersion,
          currentVersion: deployedApp.semVersion,
          routeName: deployedApp.routingName,
          operation: testingCreateMode === \"upgrade-post\" ? \"testing_upgrade_post\" : \"testing_upgrade_candidate\"
        };
      }
      await upgradeApp(deployedApp.id, displayTitle, publishedApp.deployVersion, testingUpgradeMode ? undefined : options.pathName ? routingName : undefined, envConfig, options.tags, options.clientId);""",
    ),
    (
        """        deployVersion: publishedApp.deployVersion,
        operation: \"upgrade\"""",
        """        deployVersion: publishedApp.deployVersion,
        currentVersion: version2,
        routeName: deployedApp.routingName,
        operation: testingCreateMode === \"upgrade-execute\" ? \"testing_upgrade_execute\" : \"upgrade\"""",
    ),
    (
        """  program2.command(\"deploy\").description(\"Deploy or upgrade app in UiPath\").option(\"-n, --name <name>\", \"App name\").option(\"--path-name <name>\", \"App pathname in the URL (https://<org>.uipath.host/<path-name>)\").option(\"--client-id <id>\", \"OAuth client ID override (non-confidential/public client)\").option(\"-v, --version <version>\", \"Target a specific published version\").option(\"--base-url <url>\", \"UiPath base URL\").option(\"--org-id <id>\", \"Organization ID\").option(\"--org-name <name>\", \"Organization name\").option(\"--tenant-id <id>\", \"Tenant ID\").option(\"--folder-key <key>\", \"Folder key\").option(\"--access-token <token>\", \"Access token\").option(\"--tags <tags>\", \"Comma-separated categorization labels for the deployed app (e.g. governance,insights)\").examples(DEPLOY_EXAMPLES).trackedAction(processContext, async (options) => {""",
        """  program2.command(\"deploy\").description(\"Deploy or upgrade app in UiPath\").option(\"-n, --name <name>\", \"App name\").option(\"--path-name <name>\", \"App pathname in the URL (https://<org>.uipath.host/<path-name>)\").option(\"--client-id <id>\", \"OAuth client ID override (non-confidential/public client)\").option(\"-v, --version <version>\", \"Target a specific published version\").option(\"--base-url <url>\", \"UiPath base URL\").option(\"--org-id <id>\", \"Organization ID\").option(\"--org-name <name>\", \"Organization name\").option(\"--tenant-id <id>\", \"Tenant ID\").option(\"--folder-key <key>\", \"Folder key\").option(\"--access-token <token>\", \"Access token\").option(\"--tags <tags>\", \"Comma-separated categorization labels for the deployed app (e.g. governance,insights)\").option(\"--testing-create-mode <mode>\", \"Testing-only guarded deployment mode\").option(\"--testing-expected-deployment-id <id>\", \"Exact deployment ID\").option(\"--testing-expected-system-name <name>\", \"Exact candidate system name\").option(\"--testing-expected-deploy-version <number>\", \"Exact candidate deploy version\").option(\"--testing-expected-current-version <version>\", \"Exact current deployed version\").option(\"--testing-expected-route-name <name>\", \"Exact existing route\").examples(DEPLOY_EXAMPLES).trackedAction(processContext, async (options) => {""",
    ),
    (
        """      accessToken: options.accessToken,
      tags,
      logger: logger3""",
        """      accessToken: options.accessToken,
      tags,
      testingCreateMode: options.testingCreateMode,
      testingExpectedDeploymentId: options.testingExpectedDeploymentId,
      testingExpectedSystemName: options.testingExpectedSystemName,
      testingExpectedDeployVersion: options.testingExpectedDeployVersion,
      testingExpectedCurrentVersion: options.testingExpectedCurrentVersion,
      testingExpectedRouteName: options.testingExpectedRouteName,
      logger: logger3""",
    ),
    (
        """      Data: { message: \"App deployed successfully.\" }
    });""",
        """      Data: [\"testing_create_verify\", \"testing_create_post\", \"testing_upgrade_pre\", \"testing_upgrade_candidate\", \"testing_upgrade_execute\", \"testing_upgrade_post\"].includes(result?.operation) ? {
        message: result.operation === \"testing_create_post\" ? \"Testing create post-state verified.\" : result.operation === \"testing_create_verify\" ? \"Testing create target verified absent; no mutation performed.\" : result.operation === \"testing_upgrade_pre\" ? \"Testing upgrade target verified; no mutation performed.\" : result.operation === \"testing_upgrade_candidate\" ? \"Testing upgrade candidate verified; no mutation performed.\" : result.operation === \"testing_upgrade_post\" ? \"Testing upgrade post-state verified.\" : \"Testing upgrade completed.\",
        deploymentId: result.deploymentId,
        systemName: result.systemName,
        deployVersion: result.deployVersion,
        currentVersion: result.currentVersion,
        routeName: result.routeName,
        version: result.version,
        appName: result.appName,
        appUrl: result.appUrl,
        operation: result.operation
      } : result?.operation === \"deploy\" ? {
        message: \"Testing create completed.\",
        deploymentId: result.deploymentId,
        systemName: result.systemName,
        deployVersion: result.deployVersion,
        version: result.version,
        appName: result.appName,
        appUrl: result.appUrl,
        operation: result.operation
      } : { message: \"App deployed successfully.\" }
    });""",
    ),
    (
        """    if (result) {
      trackShipSucceeded({
        ship_kind: \"deploy\",""",
        """    if (result && ![\"testing_create_verify\", \"testing_create_post\", \"testing_upgrade_pre\", \"testing_upgrade_candidate\", \"testing_upgrade_post\"].includes(result.operation)) {
      trackShipSucceeded({
        ship_kind: \"deploy\",""",
    ),
    (
        """      Data: { message: \"Package published successfully.\" }
    });""",
        """      Data: result ? {
        message: \"Package published successfully.\",
        packageName: result.packageName,
        packageVersion: result.packageVersion,
        systemName: result.systemName,
        deployVersion: result.deployVersion,
        personalWorkspace: result.personalWorkspace,
        appType: result.appType
      } : { message: \"Package published successfully.\" }
    });""",
    ),
)


class TestingCommandError(RuntimeError):
    """A redacted command failure with a stable receipt-safe code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _safe_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    return recovery._recovery_environment(os.environ if source is None else source)


def _require_guid(value: str | None, label: str) -> str:
    if not value or core.GUID_RE.fullmatch(value) is None:
        core._fail(f"{label} must be an exact GUID.")
    return value.lower()


def _require_hash(value: str | None, label: str) -> str:
    if value is None:
        core._fail(f"{label} is required.")
    core._validate_hash(value, label)
    return value


def _require_text(value: str | None, label: str, *, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        core._fail(f"{label} is required.")
    result = value.strip()
    if len(result) > maximum or any(ord(character) < 32 for character in result):
        core._fail(f"{label} contains unsupported text.")
    return result


def _require_path_name(value: str | None) -> str:
    result = _require_text(value, "--path-name").lower()
    if core.PATH_NAME_RE.fullmatch(result) is None or len(result) > 32:
        core._fail("--path-name must be a lowercase route slug of at most 32 characters.")
    return result


def _target(args: argparse.Namespace, cli: Path) -> dict[str, Any]:
    environment = _require_text(args.environment, "--environment")
    control_plane = _require_text(args.control_plane_url, "--control-plane-url")
    core._validate_target_binding(
        environment,
        control_plane,
        None,
        label_prefix="Testing deployment",
    )
    if args.cli_version != EXPECTED_CLI_VERSION:
        core._fail(f"--cli-version must be exactly {EXPECTED_CLI_VERSION} for this testing adapter.")
    profile = _require_text(args.cli_profile, "--cli-profile")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", profile):
        core._fail("--cli-profile contains unsupported characters.")
    org_id = _require_guid(args.org_id, "--org-id")
    tenant_id = _require_guid(args.tenant_id, "--tenant-id")
    organization_name = _require_text(args.org_name, "--org-name")
    if re.fullmatch(r"[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?", organization_name) is None:
        core._fail("--org-name must be the exact lowercase UiPath organization host segment.")
    result = {
        "environment": environment,
        "control_plane_url": control_plane,
        "organization_name": organization_name,
        "organization_id": org_id,
        "tenant_name": _require_text(args.tenant_name, "--tenant-name"),
        "tenant_id": tenant_id,
        "folder_key": _require_guid(args.folder_key, "--folder-key"),
        "client_id": _require_guid(args.client_id, "--client-id"),
        "cli_profile": profile,
        "cli_profile_hash": core._hash_json(
            {
                "name": profile,
                "environment": environment,
                "control_plane_url": control_plane,
                "org_id": org_id,
                "tenant_id": tenant_id,
            }
        ),
        "cli_executable": str(cli),
        "cli_executable_sha256": core._hash_file(cli, "testing UiPath CLI executable"),
        "cli_version": args.cli_version,
    }
    return result


def _resolve_cli(value: str | None) -> Path:
    if not value:
        core._fail("--cli-executable is required for testing deployment.")
    path = Path(value).expanduser().resolve(strict=True)
    if path.is_symlink() or not path.is_file() or not os.access(path, os.X_OK):
        core._fail("--cli-executable must resolve to an executable regular file.")
    if core._hash_file(path, "testing UiPath CLI executable") != EXPECTED_CLI_SHA256:
        core._fail("--cli-executable is not the supported UiPath CLI 1.198.0 build.")
    package_path = path.parents[1] / "package.json"
    if package_path.is_symlink() or not package_path.is_file():
        core._fail("UiPath CLI package metadata must be a regular non-symlink file.")
    if core._hash_file(package_path, "UiPath CLI package metadata") != EXPECTED_CLI_MANIFEST_SHA256:
        core._fail("UiPath CLI package metadata is not the supported exact build.")
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        core._fail("UiPath CLI package metadata is missing or invalid.")
    if not isinstance(package, dict) or package.get("version") != EXPECTED_CLI_VERSION:
        core._fail("UiPath CLI package version is unsupported.")
    if package.get("gitHead") != EXPECTED_CLI_GIT_HEAD:
        core._fail("UiPath CLI package build identity is unsupported.")
    if package.get("bin") != {"uip": "./dist/index.js"} or package.get("main") != "./dist/index.js":
        core._fail("UiPath CLI package executable mapping is unsupported.")
    return path


def _resolve_node(executable_value: str | None, version_value: str | None) -> dict[str, str]:
    if not executable_value:
        core._fail("--node-executable is required for dist testing mode.")
    if not version_value:
        core._fail("--node-version is required for dist testing mode.")
    executable = Path(executable_value).expanduser().resolve(strict=True)
    if executable.is_symlink() or not executable.is_file() or not os.access(executable, os.X_OK):
        core._fail("--node-executable must resolve to an executable regular file.")
    expected_digest = SUPPORTED_NODE_RUNTIMES.get(version_value)
    if expected_digest is None:
        core._fail("--node-version is not supported by testing schema 1.2.")
    observed_digest = core._hash_file(executable, "testing Node.js executable")
    if observed_digest != expected_digest:
        core._fail("--node-executable bytes do not match the supported Node.js runtime.")
    environment = _safe_environment()
    try:
        completed = subprocess.run(
            [str(executable), "--version"],
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        core._fail("Could not execute the testing Node.js runtime.")
    if completed.stdout.strip() != f"v{version_value}":
        core._fail("Node.js runtime version does not match its testing binding.")
    return {
        "executable": str(executable),
        "executable_sha256": observed_digest,
        "version": version_value,
    }


def _validate_cli(
    target: dict[str, Any],
    cwd: Path,
    environment: dict[str, str],
    node_runtime: dict[str, str],
) -> None:
    cli = Path(target["cli_executable"])
    if core._hash_file(cli, "testing UiPath CLI executable") != target["cli_executable_sha256"]:
        core._fail("UiPath CLI bytes changed during testing preflight.")
    node = Path(node_runtime["executable"])
    if core._hash_file(node, "testing Node.js executable") != node_runtime["executable_sha256"]:
        core._fail("Node.js bytes changed during testing preflight.")
    version = _run_read(
        [str(node), str(cli), "--version"], cwd, environment, "CLI_VERSION_FAILED"
    )
    match = re.search(r"\b([0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?)\b", version)
    if match is None or match.group(1) != target["cli_version"]:
        core._fail("UiPath CLI version does not match the testing adapter.")
    status_text = _run_read(
        [
            str(node), str(cli), "login", "status", "--profile",
            target["cli_profile"], "--output", "json",
        ],
        cwd,
        environment,
        "CLI_PROFILE_STATUS_FAILED",
    )
    try:
        status = json.loads(status_text)
    except json.JSONDecodeError:
        core._fail("UiPath CLI profile status did not return valid JSON.")
    login_state = core._find_mapping_value(status, {"status"})
    if not isinstance(login_state, str) or login_state.lower() not in {
        "loggedin",
        "logged in",
        "authenticated",
    }:
        core._fail("UiPath CLI profile is not logged in.")
    comparisons = (
        (target["organization_id"], {"organizationid", "organizationuid"}, "organization"),
        (target["tenant_id"], {"tenantid", "tenantuid"}, "tenant"),
        (target["organization_name"], {"organization", "organizationname", "orgname"}, "organization name"),
        (target["tenant_name"], {"tenant", "tenantname"}, "tenant name"),
        (target["control_plane_url"], {"baseurl"}, "control plane"),
    )
    for expected, names, label in comparisons:
        observed = core._find_mapping_value(status, names)
        if not isinstance(observed, str) or observed.lower() != expected.lower():
            core._fail(f"UiPath CLI profile {label} does not match the testing target.")


def _run_read(
    command: list[str],
    cwd: Path,
    environment: dict[str, str],
    error_code: str,
) -> str:
    core._log(f"+ testing read: {Path(command[0]).name} {command[1] if len(command) > 1 else ''}")
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
        raise TestingCommandError(error_code) from exc
    return completed.stdout


def _run_write(
    command: list[str],
    cwd: Path,
    environment: dict[str, str],
    error_code: str,
) -> dict[str, Any]:
    core._log(f"+ testing write: {Path(command[0]).name} {command[1]} {command[2]}")
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
        raise TestingCommandError(error_code) from exc
    document = _extract_json_envelope(completed.stdout, error_code)
    if not isinstance(document, dict) or document.get("Result") != "Success":
        raise TestingCommandError(error_code)
    return document


def _extract_json_envelope(output: str, error_code: str) -> dict[str, Any]:
    """Extract the final CLI JSON envelope without retaining preceding console text."""

    for match in reversed(list(re.finditer(r"(?m)^\{", output))):
        candidate = output[match.start() :].strip()
        try:
            document = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(document, dict):
            return document
    raise TestingCommandError(error_code)


def _git_state(root: Path) -> tuple[str | None, str, str | None]:
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip().lower()
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit("--project-root must be inside a readable Git worktree.") from exc
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        core._fail("Git HEAD is not a full SHA-1 object ID.")
    return head, core._hash_bytes(status), head


def _directory_digest(path: Path) -> str:
    if path.is_symlink() or not path.is_dir():
        core._fail(f"Testing dist must be a real directory: {path}")
    records: list[dict[str, Any]] = []
    for item in sorted(path.rglob("*"), key=lambda candidate: candidate.relative_to(path).as_posix()):
        if item.is_symlink():
            core._fail(f"Testing dist may not contain symlinks: {item}")
        if item.is_dir():
            continue
        if not item.is_file():
            core._fail(f"Testing dist contains an unsupported entry: {item}")
        records.append(
            {
                "path": item.relative_to(path).as_posix(),
                "mode": item.stat().st_mode & 0o777,
                "size": item.stat().st_size,
                "sha256": core._hash_file(item, "testing dist file"),
            }
        )
    if not records:
        core._fail("Testing dist contains no files.")
    return core._hash_json({"files": records})


def _immutable_runtime_digest(root: Path, mutable_files: list[Path]) -> str:
    if root.is_symlink() or not root.is_dir():
        core._fail("Testing runtime must be a real directory.")
    excluded: set[str] = set()
    for mutable in mutable_files:
        if mutable.is_symlink() or not mutable.is_file():
            core._fail("Testing runtime mutable file must be a regular non-symlink file.")
        try:
            relative = mutable.relative_to(root).as_posix()
        except ValueError:
            core._fail("Testing runtime mutable file resolves outside the runtime.")
        excluded.add(relative)
    records: list[dict[str, Any]] = []
    for item in sorted(root.rglob("*"), key=lambda value: value.relative_to(root).as_posix()):
        relative = item.relative_to(root).as_posix()
        if relative in excluded:
            continue
        if item.is_symlink():
            core._fail(f"Testing runtime may not contain symlinks: {item}")
        if item.is_dir():
            continue
        if not item.is_file():
            core._fail(f"Testing runtime contains an unsupported entry: {item}")
        records.append(
            {
                "path": relative,
                "mode": item.stat().st_mode & 0o777,
                "size": item.stat().st_size,
                "sha256": core._hash_file(item, "testing immutable runtime file"),
            }
        )
    if not records:
        core._fail("Testing runtime contains no immutable files.")
    return core._hash_json({"excluded": sorted(excluded), "files": records})


def _secret_like_matches(payload: bytes) -> Iterator[tuple[int, int, bytes]]:
    forbidden = (
        b"-----BEGIN " + b"PRIVATE KEY-----",
        b"UIPATH_" + b"ACCESS_TOKEN=",
        b"UIPATH_" + b"CLIENT_SECRET=",
        b"authorization: " + b"bearer eyJ",
    )
    lowered = payload.lower()
    for marker in forbidden:
        lowered_marker = marker.lower()
        offset = 0
        while (index := lowered.find(lowered_marker, offset)) >= 0:
            yield (
                index,
                index + len(marker),
                payload[index : index + len(marker)],
            )
            offset = index + len(marker)
    assignment = re.compile(
        rb"(?i)\b(?:api[_-]?key|client[_-]?secret|password|access[_-]?token|private[_-]?key)"
        rb"\s*[:=]\s*[\"']?[A-Za-z0-9_./+=-]{16,}"
    )
    bearer = re.compile(rb"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{20,}")
    jwt = re.compile(rb"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
    private_key = re.compile(
        rb"-----BEGIN (?:RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----"
    )
    for pattern in (assignment, bearer, jwt, private_key):
        for match in pattern.finditer(payload):
            yield match.start(), match.end(), match.group(0)


def _audit_payload(payload: bytes) -> None:
    if next(_secret_like_matches(payload), None) is not None:
        core._fail("Testing artifact secret audit failed; candidate bytes are prohibited.")


def _audit_tracked_source_payload(relative: Path, payload: bytes) -> None:
    allowed_lines = KNOWN_SYNTHETIC_SOURCE_LINES.get(
        relative.as_posix(), frozenset()
    )
    for start, end, _ in _secret_like_matches(payload):
        line_start = payload.rfind(b"\n", 0, start) + 1
        line_end = payload.find(b"\n", end)
        if line_end < 0:
            line_end = len(payload)
        if core._hash_bytes(payload[line_start:line_end]) not in allowed_lines:
            core._fail(
                "Testing artifact secret audit failed; candidate bytes are prohibited."
            )


def _audit_dist(path: Path) -> None:
    for item in path.rglob("*"):
        if not item.is_file():
            continue
        _audit_payload(item.read_bytes())


def _audit_package_archive(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        core._fail("Testing package secret audit requires a regular package file.")
    try:
        with zipfile.ZipFile(path) as archive:
            total_size = 0
            for member in archive.infolist():
                if member.is_dir():
                    continue
                total_size += member.file_size
                if member.flag_bits & 0x1:
                    core._fail("Testing package may not contain encrypted entries.")
                if member.file_size > 64 * 1024 * 1024 or total_size > 512 * 1024 * 1024:
                    core._fail("Testing package exceeds the bounded secret-audit size.")
                _audit_payload(archive.read(member))
    except (OSError, zipfile.BadZipFile, RuntimeError):
        core._fail("Testing package secret audit could not inspect the exact archive.")


def _resolve_reconciled_package(
    project_root: Path,
    plan: dict[str, Any],
    context: dict[str, Any],
) -> Path:
    raw_value = plan.get("candidate", {}).get("package_path")
    if not isinstance(raw_value, str) or not raw_value:
        core._fail("Reconciled package path is missing or invalid.")
    relative = Path(raw_value)
    if relative.is_absolute() or ".." in relative.parts:
        core._fail("Reconciled package path must be a project-relative path.")
    cursor = project_root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            core._fail("Reconciled package path may not traverse a symbolic link.")
    try:
        package_path = (project_root / relative).resolve(strict=True)
    except (OSError, RuntimeError):
        core._fail("Reconciled package is missing or inaccessible.")
    if not _is_within(package_path, project_root) or not package_path.is_file():
        core._fail("Reconciled package must be a regular file inside the project root.")
    failed_parameters = context.get("failed_plan", {}).get("parameters", {})
    main_file = failed_parameters.get("main_file")
    if not isinstance(main_file, str) or not main_file:
        core._fail("Reconciled package main-file binding is missing.")
    package_name = plan.get("existing_deployment", {}).get("package_name")
    if not isinstance(package_name, str) or not package_name:
        core._fail("Reconciled package-name binding is missing.")
    content_digest, file_digest = core._package_evidence(
        package_path,
        package_name=package_name,
        main_file=main_file,
    )
    candidate = plan["candidate"]
    if (
        content_digest != candidate.get("package_content_digest")
        or file_digest != candidate.get("package_file_digest")
    ):
        core._fail("Reconciled package bytes do not match the exact recovery candidate.")
    _audit_package_archive(package_path)
    return package_path


def _audit_tracked_source(project_root: Path, source_root: Path) -> None:
    try:
        relative_root = source_root.resolve(strict=True).relative_to(project_root.resolve(strict=True))
    except (ValueError, OSError, RuntimeError):
        core._fail("Testing source root must be inside the exact project root.")
    completed = subprocess.run(
        [
            "git", "-C", str(project_root), "ls-files", "-z",
            "--cached", "--others", "--exclude-standard", "--", relative_root.as_posix(),
        ],
        check=True,
        capture_output=True,
    )
    for raw_relative in completed.stdout.split(b"\0"):
        if not raw_relative:
            continue
        relative = Path(os.fsdecode(raw_relative))
        if relative.name.startswith(".env") and relative.name != ".env.example":
            core._fail("Tracked environment files are prohibited for testing deployment.")
        path = project_root / relative
        if path.is_symlink() or not path.is_file():
            core._fail("Testing source contains a non-regular tracked file.")
        _audit_tracked_source_payload(relative, path.read_bytes())


def _workspace_for(receipt_path: Path) -> Path:
    return receipt_path.parent / f"{receipt_path.stem}.workspace"


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=True))
        return True
    except (ValueError, OSError, RuntimeError):
        return False


def _require_ignored_or_external(path: Path, project_root: Path) -> None:
    if not _is_within(path, project_root):
        return
    completed = subprocess.run(
        ["git", "-C", str(project_root), "check-ignore", "--quiet", "--no-index", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode == 1:
        core._fail("Testing evidence inside the project must be ignored by Git.")
    if completed.returncode != 0:
        core._fail("Could not prove that the testing evidence path is ignored by Git.")


def _validate_evidence_isolation(
    receipt_path: Path,
    project_root: Path,
    protected_paths: list[Path],
    *,
    include_workspace: bool,
) -> None:
    _require_ignored_or_external(receipt_path, project_root)
    evidence_paths = [receipt_path]
    if include_workspace:
        workspace = _workspace_for(receipt_path)
        _require_ignored_or_external(workspace, project_root)
        evidence_paths.append(workspace)
    for evidence in evidence_paths:
        for protected in protected_paths:
            if recovery._paths_overlap(evidence.resolve(strict=False), protected.resolve(strict=False)):
                core._fail("Testing evidence paths must not overlap source, runtime, or CLI inputs.")


def _copy_exact_dist(source: Path, workspace: Path) -> tuple[Path, str]:
    if workspace.exists():
        core._fail("Testing evidence workspace already exists; blind replay is prohibited.")
    workspace.mkdir(mode=0o700)
    destination = workspace / "dist"
    shutil.copytree(source, destination, symlinks=False)
    source_digest = _directory_digest(source)
    destination_digest = _directory_digest(destination)
    if source_digest != destination_digest:
        core._fail("Testing dist changed while copying into the evidence workspace.")
    _audit_dist(destination)
    return destination, destination_digest


def _create_guard_patch_hash() -> str:
    return core._hash_json(
        {
            "algorithm": CREATE_GUARD_PATCH_ALGORITHM,
            "expected_version": recovery.EXPECTED_CODEDAPP_TOOL_VERSION,
            "expected_git_head": recovery.EXPECTED_CODEDAPP_TOOL_GIT_HEAD,
            "expected_tool_sha256": recovery.EXPECTED_CODEDAPP_TOOL_SHA256,
            "edits": [
                {"source": source, "replacement": replacement}
                for source, replacement in CREATE_GUARD_PATCH_EDITS
            ],
        }
    )


def _patched_create_guard_bytes(source: bytes) -> bytes:
    if core._hash_bytes(source) != recovery.EXPECTED_CODEDAPP_TOOL_SHA256:
        core._fail("Coded app tool bytes are not the supported 1.198.0 testing source.")
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError:
        core._fail("Coded app tool source is not UTF-8.")
    for old, new in CREATE_GUARD_PATCH_EDITS:
        if text.count(old) != 1:
            core._fail("Testing create-guard patch anchor did not match exactly once.")
        text = text.replace(old, new, 1)
    return text.encode("utf-8")


def _validate_exact_package_manifest(
    path_value: Any,
    *,
    expected_digest: str,
    package_kind: str,
    label: str,
) -> Path:
    if not isinstance(path_value, str):
        core._fail(f"Testing {label} path is invalid.")
    path = Path(path_value)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        core._fail(f"Testing {label} must be an absolute regular non-symlink file.")
    if core._hash_file(path, f"testing {label}") != expected_digest:
        core._fail(f"Testing {label} is not the supported exact build.")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        core._fail(f"Testing {label} is missing or invalid.")
    if not isinstance(document, dict):
        core._fail(f"Testing {label} must be a JSON object.")
    if package_kind == "cli":
        expected_fields = {
            "version": EXPECTED_CLI_VERSION,
            "gitHead": EXPECTED_CLI_GIT_HEAD,
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
    elif package_kind == "codedapp-tool":
        expected_fields = {
            "version": recovery.EXPECTED_CODEDAPP_TOOL_VERSION,
            "gitHead": recovery.EXPECTED_CODEDAPP_TOOL_GIT_HEAD,
            "main": "./dist/tool.js",
            "exports": {".": "./dist/tool.js"},
            "bin": {"codedapp-tool": "./dist/index.js"},
        }
    else:
        core._fail("Testing package manifest kind is unsupported.")
    if any(document.get(field) != expected for field, expected in expected_fields.items()):
        core._fail(f"Testing {label} package identity or entrypoints are unsupported.")
    return path


def _validate_create_runtime_manifests(manifest: dict[str, Any]) -> None:
    contracts = (
        (
            "source_cli_manifest",
            "source_cli_manifest_sha256",
            EXPECTED_CLI_MANIFEST_SHA256,
            "cli",
            "source CLI manifest",
        ),
        (
            "runtime_cli_manifest",
            "runtime_cli_manifest_sha256",
            EXPECTED_CLI_MANIFEST_SHA256,
            "cli",
            "runtime CLI manifest",
        ),
        (
            "source_tool_manifest",
            "source_tool_manifest_sha256",
            EXPECTED_CODEDAPP_TOOL_MANIFEST_SHA256,
            "codedapp-tool",
            "source coded app tool manifest",
        ),
        (
            "runtime_tool_manifest",
            "runtime_tool_manifest_sha256",
            EXPECTED_CODEDAPP_TOOL_MANIFEST_SHA256,
            "codedapp-tool",
            "runtime coded app tool manifest",
        ),
    )
    for path_field, digest_field, expected_digest, package_kind, label in contracts:
        if manifest.get(digest_field) != expected_digest:
            core._fail(f"Testing {label} digest binding changed.")
        _validate_exact_package_manifest(
            manifest.get(path_field),
            expected_digest=expected_digest,
            package_kind=package_kind,
            label=label,
        )


def _prepare_create_guard_runtime(
    cli: Path,
    node_runtime: dict[str, str],
    workspace: Path,
    app_config: dict[str, Any],
    environment: dict[str, str],
) -> dict[str, Any]:
    source_node_modules = cli.parents[3]
    if source_node_modules.name != "node_modules":
        core._fail("Testing CLI must resolve inside a node_modules tree.")
    source_relative = cli.relative_to(source_node_modules)
    source_tool = source_node_modules / "@uipath" / "codedapp-tool" / "dist" / "tool.js"
    source_manifest_path = source_node_modules / "@uipath" / "codedapp-tool" / "package.json"
    source_cli_manifest_path = source_node_modules / "@uipath" / "cli" / "package.json"
    for path, expected_digest, label in (
        (source_tool, recovery.EXPECTED_CODEDAPP_TOOL_SHA256, "source coded app tool"),
        (
            source_manifest_path,
            EXPECTED_CODEDAPP_TOOL_MANIFEST_SHA256,
            "source coded app tool manifest",
        ),
        (source_cli_manifest_path, EXPECTED_CLI_MANIFEST_SHA256, "source CLI manifest"),
    ):
        if path.is_symlink() or not path.is_file():
            core._fail(f"Testing {label} must be a regular non-symlink file.")
        if core._hash_file(path, f"testing {label}") != expected_digest:
            core._fail(f"Testing {label} is not the supported exact build.")
    _validate_exact_package_manifest(
        str(source_cli_manifest_path),
        expected_digest=EXPECTED_CLI_MANIFEST_SHA256,
        package_kind="cli",
        label="source CLI manifest",
    )
    _validate_exact_package_manifest(
        str(source_manifest_path),
        expected_digest=EXPECTED_CODEDAPP_TOOL_MANIFEST_SHA256,
        package_kind="codedapp-tool",
        label="source coded app tool manifest",
    )
    runtime_root = workspace / "create-guard-runtime"
    if runtime_root.exists():
        core._fail("Testing create-guard runtime already exists.")
    runtime_node_modules = runtime_root / "node_modules"
    shutil.copytree(source_node_modules, runtime_node_modules, symlinks=False)
    runtime_cli = runtime_node_modules / source_relative
    runtime_tool = runtime_node_modules / "@uipath" / "codedapp-tool" / "dist" / "tool.js"
    runtime_cli_manifest_path = runtime_node_modules / "@uipath" / "cli" / "package.json"
    runtime_tool_manifest_path = runtime_node_modules / "@uipath" / "codedapp-tool" / "package.json"
    if core._hash_file(runtime_cli, "testing copied guard CLI") != EXPECTED_CLI_SHA256:
        core._fail("Testing create-guard CLI changed while copying the runtime.")
    if core._hash_file(
        runtime_cli_manifest_path, "testing copied CLI manifest"
    ) != EXPECTED_CLI_MANIFEST_SHA256:
        core._fail("Testing create-guard CLI manifest changed while copying the runtime.")
    if core._hash_file(
        runtime_tool_manifest_path, "testing copied tool manifest"
    ) != EXPECTED_CODEDAPP_TOOL_MANIFEST_SHA256:
        core._fail("Testing create-guard tool manifest changed while copying the runtime.")
    patched = _patched_create_guard_bytes(source_tool.read_bytes())
    core._atomic_write_bytes(runtime_tool, patched, runtime_tool.stat().st_mode & 0o777)
    if runtime_tool.read_bytes() != patched:
        core._fail("Testing create-guard tool does not match the deterministic patch.")
    runtime_workspace = runtime_root / "workspace"
    config_path = runtime_workspace / core.APP_CONFIG_RELATIVE_PATH
    config_path.parent.mkdir(parents=True)
    core._atomic_write_json(config_path, app_config)
    node_path = Path(node_runtime["executable"])
    if core._hash_file(node_path, "testing create-guard Node.js") != node_runtime[
        "executable_sha256"
    ]:
        core._fail("Testing create-guard Node.js bytes changed before runtime preparation.")
    syntax = subprocess.run(
        [str(node_path), "--check", str(runtime_tool)],
        cwd=runtime_workspace,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if syntax.returncode != 0:
        core._fail("Testing create-guard runtime failed syntax validation.")
    blocked = subprocess.run(
        [str(node_path), str(runtime_cli), "codedapp", "deploy", "--output", "json"],
        cwd=runtime_workspace,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if blocked.returncode == 0 or "TESTING_CREATE_GUARD_REQUIRED" not in blocked.stdout:
        core._fail("Testing create-guard runtime did not block ordinary deployment.")
    manifest = {
        "kind": CREATE_GUARD_RUNTIME_KIND,
        "schema_version": CREATE_GUARD_RUNTIME_VERSION,
        "created_at": core._utc_now(),
        "helper_sha256": core._hash_file(Path(__file__), "testing helper"),
        "patch_algorithm": CREATE_GUARD_PATCH_ALGORITHM,
        "patch_contract_sha256": _create_guard_patch_hash(),
        "source_cli": str(cli),
        "source_cli_sha256": core._hash_file(cli, "testing source CLI"),
        "source_cli_manifest": str(source_cli_manifest_path),
        "source_cli_manifest_sha256": core._hash_file(
            source_cli_manifest_path, "testing source CLI manifest"
        ),
        "source_tool": str(source_tool),
        "source_tool_sha256": core._hash_file(source_tool, "testing source coded app tool"),
        "source_tool_manifest": str(source_manifest_path),
        "source_tool_manifest_sha256": core._hash_file(
            source_manifest_path, "testing source coded app tool manifest"
        ),
        "runtime_cli": str(runtime_cli),
        "runtime_root": str(runtime_root),
        "runtime_cli_sha256": core._hash_file(runtime_cli, "testing guard CLI"),
        "runtime_cli_manifest": str(runtime_cli_manifest_path),
        "runtime_cli_manifest_sha256": core._hash_file(
            runtime_cli_manifest_path, "testing guard CLI manifest"
        ),
        "runtime_tool": str(runtime_tool),
        "runtime_tool_sha256": core._hash_file(runtime_tool, "testing guard tool"),
        "runtime_tool_manifest": str(runtime_tool_manifest_path),
        "runtime_tool_manifest_sha256": core._hash_file(
            runtime_tool_manifest_path, "testing guard tool manifest"
        ),
        "runtime_workspace": str(runtime_workspace),
        "runtime_app_config_sha256": core._hash_file(config_path, "testing guard app config"),
        "node_executable": str(node_path),
        "node_executable_sha256": core._hash_file(node_path, "testing guard Node.js"),
        "node_version": node_runtime["version"],
        "runtime_tree_sha256": recovery._tree_digest(runtime_root, "testing create-guard runtime"),
        "runtime_immutable_sha256": _immutable_runtime_digest(
            runtime_root, [config_path]
        ),
        "self_test": {
            "node_syntax": "passed",
            "ordinary_deploy": "blocked_before_network",
        },
    }
    manifest["manifest_hash"] = core._document_hash(manifest, "manifest_hash")
    manifest_path = workspace / "create-guard-runtime.manifest.json"
    core._atomic_write_json(manifest_path, manifest)
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def _revalidate_create_runtime(runtime: dict[str, Any], candidate: dict[str, Any]) -> None:
    manifest_path = Path(runtime["manifest_path"])
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        core._fail("Testing create-guard runtime manifest is missing or invalid.")
    if not isinstance(manifest, dict) or core._document_hash(manifest, "manifest_hash") != manifest.get(
        "manifest_hash"
    ):
        core._fail("Testing create-guard runtime manifest hash is invalid.")
    if manifest["manifest_hash"] != candidate["runtime_manifest_hash"]:
        core._fail("Testing create-guard runtime manifest changed after candidate claim.")
    _validate_create_runtime_manifests(manifest)
    source_cli = Path(manifest.get("source_cli", ""))
    if (
        not source_cli.is_absolute()
        or source_cli.is_symlink()
        or not source_cli.is_file()
        or core._hash_file(source_cli, "testing source CLI") != EXPECTED_CLI_SHA256
        or manifest.get("source_cli_sha256") != EXPECTED_CLI_SHA256
    ):
        core._fail("Testing source CLI changed after candidate claim.")
    source_tool = Path(manifest.get("source_tool", ""))
    if (
        not source_tool.is_absolute()
        or source_tool.is_symlink()
        or not source_tool.is_file()
        or core._hash_file(source_tool, "testing source coded app tool")
        != recovery.EXPECTED_CODEDAPP_TOOL_SHA256
    ):
        core._fail("Testing source coded app tool changed after candidate claim.")
    expected_runtime_tool = _patched_create_guard_bytes(source_tool.read_bytes())
    expected_hashes = {
        "source_cli_sha256": EXPECTED_CLI_SHA256,
        "runtime_cli_sha256": core._hash_file(
            Path(manifest["runtime_cli"]), "testing runtime CLI"
        ),
        "runtime_tool_sha256": core._hash_file(
            Path(manifest["runtime_tool"]), "testing runtime coded app tool"
        ),
        "runtime_app_config_sha256": core._hash_file(
            Path(manifest["runtime_workspace"]) / core.APP_CONFIG_RELATIVE_PATH,
            "testing runtime app config",
        ),
        "node_executable_sha256": core._hash_file(
            Path(manifest["node_executable"]), "testing runtime Node.js"
        ),
    }
    for field, observed in expected_hashes.items():
        if manifest.get(field) != observed:
            core._fail(f"Testing create-guard runtime changed: {field}.")
    if manifest.get("runtime_cli_sha256") != EXPECTED_CLI_SHA256:
        core._fail("Testing create-guard runtime CLI is not the supported exact build.")
    runtime_tool = Path(manifest["runtime_tool"])
    if runtime_tool.is_symlink() or not runtime_tool.is_file():
        core._fail("Testing create-guard tool must be a regular non-symlink file.")
    if runtime_tool.read_bytes() != expected_runtime_tool:
        core._fail("Testing create-guard tool is not the deterministic patch.")
    if manifest.get("node_version") != candidate["node_version"]:
        core._fail("Testing create-guard Node.js version changed.")
    if manifest.get("patch_contract_sha256") != _create_guard_patch_hash():
        core._fail("Testing create-guard patch contract changed.")
    if recovery._tree_digest(Path(runtime["runtime_root"]), "testing create runtime") != manifest.get(
        "runtime_tree_sha256"
    ):
        core._fail("Testing create-guard runtime tree changed after candidate claim.")
    if _immutable_runtime_digest(
        Path(runtime["runtime_root"]),
        [Path(manifest["runtime_workspace"]) / core.APP_CONFIG_RELATIVE_PATH],
    ) != candidate["runtime_immutable_digest"]:
        core._fail("Testing create-guard immutable runtime changed after candidate claim.")


def _revalidate_create_runtime_immutable(
    runtime: dict[str, Any], candidate: dict[str, Any]
) -> None:
    manifest_path = Path(runtime["manifest_path"])
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        core._fail("Testing create-guard runtime manifest is missing or invalid.")
    if (
        not isinstance(manifest, dict)
        or core._document_hash(manifest, "manifest_hash") != manifest.get("manifest_hash")
        or manifest.get("manifest_hash") != candidate["runtime_manifest_hash"]
    ):
        core._fail("Testing create-guard runtime manifest changed after candidate claim.")
    _validate_create_runtime_manifests(manifest)
    source_cli = Path(manifest.get("source_cli", ""))
    if (
        not source_cli.is_absolute()
        or source_cli.is_symlink()
        or not source_cli.is_file()
        or core._hash_file(source_cli, "testing immutable source CLI")
        != EXPECTED_CLI_SHA256
        or manifest.get("source_cli_sha256") != EXPECTED_CLI_SHA256
    ):
        core._fail("Testing source CLI changed after candidate claim.")
    source_tool = Path(manifest.get("source_tool", ""))
    if (
        not source_tool.is_absolute()
        or source_tool.is_symlink()
        or not source_tool.is_file()
        or core._hash_file(source_tool, "testing source coded app tool")
        != recovery.EXPECTED_CODEDAPP_TOOL_SHA256
    ):
        core._fail("Testing source coded app tool changed after candidate claim.")
    if manifest.get("runtime_cli_sha256") != EXPECTED_CLI_SHA256 or core._hash_file(
        Path(manifest["runtime_cli"]), "testing immutable runtime CLI"
    ) != EXPECTED_CLI_SHA256:
        core._fail("Testing create-guard runtime CLI is not the supported exact build.")
    expected_tool = _patched_create_guard_bytes(source_tool.read_bytes())
    runtime_tool = Path(manifest["runtime_tool"])
    if runtime_tool.is_symlink() or not runtime_tool.is_file():
        core._fail("Testing create-guard tool must be a regular non-symlink file.")
    if runtime_tool.read_bytes() != expected_tool:
        core._fail("Testing create-guard tool is not the deterministic patch.")
    if core._hash_file(
        Path(manifest["node_executable"]), "testing immutable runtime Node.js"
    ) != candidate["node_executable_sha256"]:
        core._fail("Testing create-guard Node.js bytes changed.")
    if manifest.get("node_version") != candidate["node_version"]:
        core._fail("Testing create-guard Node.js version changed.")
    if _immutable_runtime_digest(
        Path(runtime["runtime_root"]),
        [Path(manifest["runtime_workspace"]) / core.APP_CONFIG_RELATIVE_PATH],
    ) != candidate["runtime_immutable_digest"]:
        core._fail("Testing create-guard immutable runtime changed after candidate claim.")


def _revalidate_dist_barrier(
    *,
    target: dict[str, Any],
    node_runtime: dict[str, str],
    workspace: Path,
    copied_dist: Path,
    config_copy: Path,
    package_path: Path,
    runtime: dict[str, Any],
    candidate: dict[str, Any],
    environment: dict[str, str],
) -> None:
    if core._hash_file(Path(__file__), "testing helper") != candidate["helper_sha256"]:
        core._fail("Testing helper bytes changed after candidate claim.")
    _validate_cli(target, workspace, environment, node_runtime)
    if _directory_digest(copied_dist) != candidate["dist_digest"]:
        core._fail("Testing dist changed after candidate claim.")
    if core._hash_file(config_copy, "testing uipath.json") != candidate[
        "uipath_config_digest"
    ]:
        core._fail("Testing uipath.json changed after candidate claim.")
    content_digest, file_digest = core._package_evidence(
        package_path,
        package_name=candidate["package_name"],
        main_file=candidate["main_file"],
    )
    if content_digest != candidate["package_content_digest"] or file_digest != candidate[
        "package_file_digest"
    ]:
        core._fail("Testing package changed after candidate claim.")
    _revalidate_create_runtime(runtime, candidate)


def _create_guard_command(
    runtime: dict[str, Any],
    target: dict[str, Any],
    candidate: dict[str, Any],
) -> list[str]:
    return [
        runtime["node_executable"],
        runtime["runtime_cli"],
        "codedapp",
        "deploy",
        "--version",
        candidate["version"],
        "--path-name",
        candidate["path_name"],
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
        "--folder-key",
        target["folder_key"],
        "--profile",
        target["cli_profile"],
        "--testing-create-mode",
        "verify",
        "--output",
        "json",
    ]


def _create_execute_command(
    runtime: dict[str, Any],
    target: dict[str, Any],
    candidate: dict[str, Any],
) -> list[str]:
    command = _create_guard_command(runtime, target, candidate)
    mode_index = command.index("--testing-create-mode") + 1
    command[mode_index] = "execute"
    return command


def _create_post_command(
    runtime: dict[str, Any],
    target: dict[str, Any],
    candidate: dict[str, Any],
    deployed: dict[str, Any],
) -> list[str]:
    command = _create_guard_command(runtime, target, candidate)
    command[command.index("--testing-create-mode") + 1] = "post"
    output_index = command.index("--output")
    command[output_index:output_index] = [
        "--testing-expected-deployment-id", deployed["deploymentId"],
        "--testing-expected-system-name", deployed["systemName"],
        "--testing-expected-deploy-version", str(deployed["deployVersion"]),
    ]
    return command


def _upgrade_guard_command(
    runtime: dict[str, Any],
    target: dict[str, Any],
    candidate: dict[str, Any],
    mode: str,
    *,
    published: dict[str, Any] | None = None,
) -> list[str]:
    if mode not in {"upgrade-pre", "upgrade-candidate", "upgrade-execute", "upgrade-post"}:
        core._fail("Testing upgrade guard mode is invalid.")
    command = _create_guard_command(runtime, target, candidate)
    command[command.index("--testing-create-mode") + 1] = mode
    output_index = command.index("--output")
    expected_current = (
        candidate["version"] if mode == "upgrade-post" else candidate["current_version"]
    )
    guard_values = [
        "--testing-expected-deployment-id", candidate["deployment_id"],
        "--testing-expected-current-version", expected_current,
        "--testing-expected-route-name", candidate["path_name"],
    ]
    if mode != "upgrade-pre":
        if not isinstance(published, dict):
            core._fail("Testing upgrade candidate identity is required.")
        guard_values.extend(
            [
                "--testing-expected-system-name", published["systemName"],
                "--testing-expected-deploy-version", str(published["deployVersion"]),
            ]
        )
    command[output_index:output_index] = guard_values
    return command


def _validate_published_candidate(
    document: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    if document.get("Result") != "Success" or document.get("Code") != "PublishCompleted":
        raise TestingCommandError("PUBLISH_INDETERMINATE")
    data = document.get("Data")
    required = {
        "Message", "PackageName", "PackageVersion", "SystemName",
        "PersonalWorkspace", "AppType",
    }
    if (
        not isinstance(data, dict)
        or frozenset(data) not in {
            frozenset(required),
            frozenset((*required, "DeployVersion")),
        }
    ):
        raise TestingCommandError("PUBLISH_INDETERMINATE")
    system_name = data.get("SystemName")
    acknowledged_deploy_version = data.get("DeployVersion")
    if (
        data.get("Message") != "Package published successfully."
        or data.get("PackageName") != candidate["package_name"]
        or data.get("PackageVersion") != candidate["version"]
        or data.get("PersonalWorkspace") is not False
        or data.get("AppType") != "Web"
        or not isinstance(system_name, str)
        or core.APP_SYSTEM_NAME_RE.fullmatch(system_name) is None
        or system_name != candidate["system_name"]
        or (
            "DeployVersion" in data
            and (
                not isinstance(acknowledged_deploy_version, int)
                or acknowledged_deploy_version < 1
                or acknowledged_deploy_version != candidate["deploy_version"]
            )
        )
    ):
        raise TestingCommandError("PUBLISH_INDETERMINATE")
    # UiPath registration acknowledgement can omit DeployVersion while the
    # candidate becomes query-visible. The expected deploy version is already
    # bound into the claimed candidate; the subsequent read-only candidate
    # guard remains authoritative and must pass before deploy.
    return {
        "systemName": system_name,
        "deployVersion": candidate["deploy_version"],
    }


def _dist_guard_config(
    package_name: str,
    app_name: str,
    version: str,
    target: dict[str, Any],
    path_name: str,
    intent: str,
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "appName": package_name,
        "displayName": app_name,
        "appVersion": version,
        "appType": "Web",
        "personalWorkspace": False,
    }
    if intent == "upgrade":
        document["appUrl"] = _route_url(target, _require_path_name(path_name))
    elif intent != "create":
        core._fail("Testing dist guard config intent is invalid.")
    return document


def _validate_upgrade_guard_output(
    output: str | dict[str, Any],
    target: dict[str, Any],
    candidate: dict[str, Any],
    mode: str,
    *,
    published: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        document = (
            output
            if isinstance(output, dict)
            else _extract_json_envelope(output, "UPGRADE_GUARD_INVALID_JSON")
        )
    except TestingCommandError:
        core._fail("Testing upgrade guard returned invalid JSON.")
    if document.get("Result") != "Success" or document.get("Code") != "DeployCompleted":
        core._fail("Testing upgrade guard did not succeed.")
    data = document.get("Data")
    required = {
        "Message", "DeploymentId", "SystemName", "DeployVersion", "CurrentVersion",
        "RouteName", "Version", "AppName", "AppUrl", "Operation",
    }
    messages = {
        "upgrade-pre": "Testing upgrade target verified; no mutation performed.",
        "upgrade-candidate": "Testing upgrade candidate verified; no mutation performed.",
        "upgrade-execute": "Testing upgrade completed.",
        "upgrade-post": "Testing upgrade post-state verified.",
    }
    operations = {key: key.replace("-", "_").replace("upgrade_", "testing_upgrade_") for key in messages}
    expected_current = candidate["version"] if mode in {"upgrade-execute", "upgrade-post"} else candidate["current_version"]
    expected_system = None if mode == "upgrade-pre" else published["systemName"]
    expected_deploy = None if mode == "upgrade-pre" else published["deployVersion"]
    expected = {
        "Message": messages[mode],
        "DeploymentId": candidate["deployment_id"],
        "SystemName": expected_system,
        "DeployVersion": expected_deploy,
        "CurrentVersion": expected_current,
        "RouteName": candidate["path_name"],
        "Version": candidate["version"],
        "AppName": candidate["app_name"],
        "AppUrl": _route_url(target, candidate["path_name"]),
        "Operation": operations[mode],
    }
    if not isinstance(data, dict) or set(data) != required or data != expected:
        core._fail("Testing upgrade guard did not match the exact target and candidate.")
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


def _validate_create_guard_output(output: str, target: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    try:
        document = _extract_json_envelope(output, "CREATE_ABSENCE_GUARD_INVALID_JSON")
    except TestingCommandError:
        core._fail("Testing create guard returned invalid JSON.")
    if document.get("Result") != "Success" or document.get("Code") != "DeployCompleted":
        core._fail("Testing create guard did not prove absence.")
    data = document.get("Data")
    if not isinstance(data, dict):
        core._fail("Testing create guard returned no observation.")
    expected_url = _route_url(target, candidate["path_name"])
    expected = {
        "Message": "Testing create target verified absent; no mutation performed.",
        "DeploymentId": None,
        "SystemName": None,
        "DeployVersion": None,
        "CurrentVersion": None,
        "RouteName": candidate["path_name"],
        "Version": candidate["version"],
        "AppName": candidate["app_name"],
        "AppUrl": expected_url,
        "Operation": "testing_create_verify",
    }
    if set(data) != set(expected):
        core._fail("Testing create guard result fields are invalid.")
    for field, value in expected.items():
        if data.get(field) != value:
            core._fail(f"Testing create guard {field} mismatch.")
    return {
        "deploymentId": None,
        "systemName": None,
        "deployVersion": None,
        "currentVersion": None,
        "routeName": candidate["path_name"],
        "version": candidate["version"],
        "appName": candidate["app_name"],
        "appUrl": expected_url,
        "operation": "testing_create_verify",
    }


def _validate_create_execute_output(
    document: dict[str, Any],
    target: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    if document.get("Result") != "Success" or document.get("Code") != "DeployCompleted":
        raise TestingCommandError("CREATE_DEPLOY_INVALID_RESULT")
    data = document.get("Data")
    required = {
        "Message", "DeploymentId", "SystemName", "DeployVersion", "Version",
        "AppName", "AppUrl", "Operation",
    }
    if not isinstance(data, dict) or set(data) != required:
        raise TestingCommandError("CREATE_DEPLOY_INVALID_RESULT")
    if data.get("Message") != "Testing create completed." or data.get("Operation") != "deploy":
        raise TestingCommandError("CREATE_DEPLOY_INVALID_RESULT")
    deployment_id = data.get("DeploymentId")
    system_name = data.get("SystemName")
    deploy_version = data.get("DeployVersion")
    if not isinstance(deployment_id, str) or core.GUID_RE.fullmatch(deployment_id) is None:
        raise TestingCommandError("CREATE_DEPLOY_INVALID_RESULT")
    if not isinstance(system_name, str) or core.APP_SYSTEM_NAME_RE.fullmatch(system_name) is None:
        raise TestingCommandError("CREATE_DEPLOY_INVALID_RESULT")
    if not isinstance(deploy_version, int) or deploy_version < 1:
        raise TestingCommandError("CREATE_DEPLOY_INVALID_RESULT")
    expected = {
        "Version": candidate["version"],
        "AppName": candidate["app_name"],
        "AppUrl": _route_url(target, candidate["path_name"]),
    }
    for field, value in expected.items():
        if data.get(field) != value:
            raise TestingCommandError("CREATE_DEPLOY_INVALID_RESULT")
    return {
        "deploymentId": deployment_id.lower(),
        "systemName": system_name,
        "deployVersion": deploy_version,
        "currentVersion": candidate["version"],
        "version": candidate["version"],
        "routeName": candidate["path_name"],
        "appName": candidate["app_name"],
        "appUrl": expected["AppUrl"],
        "operation": "deploy",
    }


def _validate_create_post_output(
    output: str,
    target: dict[str, Any],
    candidate: dict[str, Any],
    deployed: dict[str, Any],
) -> dict[str, Any]:
    try:
        document = _extract_json_envelope(output, "CREATE_POST_INVALID_JSON")
    except TestingCommandError:
        core._fail("Testing create post-state guard returned invalid JSON.")
    if document.get("Result") != "Success" or document.get("Code") != "DeployCompleted":
        core._fail("Testing create post-state guard did not succeed.")
    data = document.get("Data")
    required = {
        "Message", "DeploymentId", "SystemName", "DeployVersion", "CurrentVersion",
        "RouteName", "Version", "AppName", "AppUrl", "Operation",
    }
    if not isinstance(data, dict) or set(data) != required:
        core._fail("Testing create post-state guard result fields are invalid.")
    expected = {
        "Message": "Testing create post-state verified.",
        "DeploymentId": deployed["deploymentId"],
        "SystemName": deployed["systemName"],
        "DeployVersion": deployed["deployVersion"],
        "CurrentVersion": candidate["version"],
        "RouteName": candidate["path_name"],
        "Version": candidate["version"],
        "AppName": candidate["app_name"],
        "AppUrl": _route_url(target, candidate["path_name"]),
        "Operation": "testing_create_post",
    }
    if data != expected:
        core._fail("Testing create post-state guard did not match the exact deployment.")
    return {
        "deploymentId": deployed["deploymentId"],
        "systemName": deployed["systemName"],
        "deployVersion": deployed["deployVersion"],
        "currentVersion": candidate["version"],
        "routeName": candidate["path_name"],
        "version": candidate["version"],
        "appName": candidate["app_name"],
        "appUrl": expected["AppUrl"],
        "operation": "testing_create_post",
    }


def _route_url(target: dict[str, Any], route: str) -> str:
    return f"https://{target['organization_name']}.{target['environment']}.uipath.host/{route}"


def _validate_internal_config(
    document: dict[str, Any],
    target: dict[str, Any],
    route: str,
) -> None:
    if document.get("clientId") != target["client_id"]:
        core._fail("uipath.json clientId does not match the exact testing OAuth client.")
    scope = document.get("scope")
    if not isinstance(scope, str) or not {"openid", "profile"}.issubset(set(scope.split())):
        core._fail("uipath.json must request openid and profile for internal authentication.")
    expected_api = f"https://{target['environment']}.api.uipath.com"
    if document.get("baseUrl") != expected_api:
        core._fail("uipath.json SDK API origin does not match the testing environment.")
    if document.get("redirectUri") != _route_url(target, route):
        core._fail("uipath.json redirectUri does not match the exact testing route.")
    for key, value in document.items():
        normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
        if normalized in {"public", "anonymous", "allowanonymous"} and value not in (False, None):
            core._fail("uipath.json enables a public or anonymous mode prohibited for testing.")


def _load_and_audit_uipath_config(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        core._fail(f"{label} requires a regular project-root uipath.json.")
    try:
        payload = path.read_bytes()
    except OSError:
        core._fail(f"{label} uipath.json is inaccessible.")
    _audit_payload(payload)
    if any(
        marker in payload.lower()
        for marker in (b"client_secret", b"access_token", b"private_key")
    ):
        core._fail(f"{label} uipath.json contains a prohibited secret-like field.")
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        core._fail(f"{label} requires a valid UTF-8 JSON uipath.json.")
    if not isinstance(document, dict):
        core._fail(f"{label} uipath.json must be a JSON object.")
    return document, payload


def _claim_key(target: dict[str, Any], candidate: dict[str, Any]) -> str:
    if candidate["intent"] == "upgrade":
        return core._hash_json(
            {
                "scope": "home_scoped_exact_candidate_v1",
                "environment": target["environment"],
                "organization_id": target["organization_id"],
                "tenant_id": target["tenant_id"],
                "folder_key": target["folder_key"],
                "deployment_id": candidate["deployment_id"],
                "system_name": candidate["system_name"],
                "deploy_version": candidate["deploy_version"],
                "candidate_version": candidate["version"],
            }
        )
    return core._hash_json(
        {
            "scope": "testing_create_remote_operation_v1",
            "environment": target["environment"],
            "organization_id": target["organization_id"],
            "tenant_id": target["tenant_id"],
            "folder_key": target["folder_key"],
            "package_name": candidate["package_name"],
            "version": candidate["version"],
            "path_name": candidate["path_name"],
        }
    )


def _create_claim(
    target: dict[str, Any],
    candidate: dict[str, Any],
    environment: dict[str, str],
) -> tuple[Path, dict[str, Any]]:
    uipath_root = Path(environment["HOME"]) / ".uipath"
    if uipath_root.is_symlink() or not uipath_root.is_dir():
        core._fail("Testing claim requires a real HOME/.uipath directory.")
    is_upgrade = candidate["intent"] == "upgrade"
    root_name = (
        "uipcodedappdeploy-recovery-claims"
        if is_upgrade
        else "uipcodedappdeploy-testing-claims"
    )
    root = uipath_root / root_name
    root.mkdir(mode=0o700, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        core._fail("Testing claim directory must be a real directory.")
    key = _claim_key(target, candidate)
    path = root / f"{key.removeprefix('sha256:')}.json"
    claim = {
        "kind": (
            "uipcodedappdeploy.testing-cross-lane-execution-claim"
            if is_upgrade
            else "uipcodedappdeploy.testing-execution-claim"
        ),
        "schema_version": "1.0",
        "created_at": core._utc_now(),
        "key": key,
        "target_fingerprint": core._hash_json(target),
        "candidate_fingerprint": core._hash_json(candidate),
    }
    claim["claim_hash"] = core._document_hash(claim, "claim_hash")
    payload = json.dumps(claim, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        core._fail(
            "An execution claim already exists for this exact testing candidate. "
            "Do not retry; reconcile remote state and obtain a fresh testing request."
        )
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    directory_descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)
    return path, claim


def _release_claim(path: Path, claim: dict[str, Any], receipt: dict[str, Any], receipt_path: Path) -> None:
    if receipt.get("status") != "failed_prewrite" or receipt.get("external_write_started") is not False:
        core._fail("Testing claims may be released only after a handled pre-write failure.")
    for stage in receipt.get("stages", []):
        if stage.get("effect") == "external_write" and (
            stage.get("status") != "pending" or "started_at" in stage
        ):
            core._fail("Testing claim release is prohibited after an external-write stage starts.")
    observed = json.loads(path.read_text(encoding="utf-8"))
    if observed != claim or observed.get("claim_hash") != core._document_hash(observed, "claim_hash"):
        core._fail("Testing execution claim changed; refusing safe release.")
    if core._hash_file(path, "testing execution claim") != receipt["execution_claim"]["file_sha256"]:
        core._fail("Testing execution claim bytes changed; refusing safe release.")
    path.unlink()
    directory_descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)
    receipt["execution_claim"]["released"] = True
    _write_receipt(receipt_path, receipt)


def _release_unstarted_claim(path: Path, claim: dict[str, Any]) -> None:
    observed = json.loads(path.read_text(encoding="utf-8"))
    if observed != claim or observed.get("claim_hash") != core._document_hash(
        observed, "claim_hash"
    ):
        core._fail("Unstarted testing claim changed; refusing safe release.")
    path.unlink()
    directory_descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)


def _stages(
    names: list[tuple[str, str]],
    completed: set[str] | dict[str, tuple[str, str]],
) -> list[dict[str, Any]]:
    now = core._utc_now()
    result = []
    for name, effect in names:
        stage: dict[str, Any] = {"name": name, "effect": effect, "status": "pending"}
        if name in completed:
            started_at, finished_at = (
                completed[name] if isinstance(completed, dict) else (now, now)
            )
            stage.update(
                {
                    "status": "succeeded",
                    "started_at": started_at,
                    "finished_at": finished_at,
                }
            )
        result.append(stage)
    return result


def _new_receipt(
    args: argparse.Namespace,
    target: dict[str, Any],
    candidate: dict[str, Any],
    claim_path: Path,
    claim: dict[str, Any],
    reservation: dict[str, Any],
    stages: list[dict[str, Any]],
    recovery_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = core._utc_now()
    receipt = {
        "kind": RECEIPT_KIND,
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "helper_sha256": core._hash_file(Path(__file__), "testing helper"),
        "attempt_phase": "claimed",
        "preflight_error_code": None,
        "authorization": {
            "mode": "explicit_testing_request",
            "testing_only": True,
            "execute": True,
            "purpose": _require_text(args.testing_purpose, "--testing-purpose"),
        },
        "target": copy.deepcopy(target),
        "candidate": copy.deepcopy(candidate),
        "policy": {
            "policy_version": POLICY_VERSION,
            "data_classification": "synthetic_only",
            "internal_authenticated_required": True,
            "production_eligible": False,
            "release_evidence": False,
            "waived_gates": copy.deepcopy(WAIVED_GATES),
            "nonwaivable_controls": copy.deepcopy(NONWAIVABLE_CONTROLS),
        },
        "execution_claim": {
            "path": str(claim_path),
            "key": claim["key"],
            "file_sha256": core._hash_file(claim_path, "testing execution claim"),
            "claim_hash": claim["claim_hash"],
            "released": False,
        },
        "recovery_source": copy.deepcopy(recovery_source),
        "receipt_reservation": copy.deepcopy(reservation),
        "status": "in_progress",
        "external_write_started": False,
        "started_at": now,
        "updated_at": now,
        "redaction": copy.deepcopy(REDACTION),
        "stages": stages,
        "observations": {"prewrite": None, "published_candidate": None, "postwrite": None},
        "verification": {
            "route_url": _route_url(target, candidate["path_name"]),
            "route_verified": None,
            "configuration_verified": None,
            "pre_deploy_app_config_digest": candidate["runtime_app_config_digest"],
            "post_deploy_app_config_digest": None,
            "authentication_certification": "pending_external_acceptance",
        },
    }
    receipt["receipt_hash"] = core._document_hash(receipt, "receipt_hash")
    return receipt


def _new_preflight_failure_receipt(
    args: argparse.Namespace,
    target: dict[str, Any],
    reservation: dict[str, Any],
    error_code: str,
) -> dict[str, Any]:
    now = core._utc_now()
    receipt = {
        "kind": RECEIPT_KIND,
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "helper_sha256": core._hash_file(Path(__file__), "testing helper"),
        "attempt_phase": "preflight",
        "preflight_error_code": error_code,
        "authorization": {
            "mode": "explicit_testing_request",
            "testing_only": True,
            "execute": True,
            "purpose": _require_text(args.testing_purpose, "--testing-purpose"),
        },
        "target": copy.deepcopy(target),
        "candidate": None,
        "policy": {
            "policy_version": POLICY_VERSION,
            "data_classification": "synthetic_only",
            "internal_authenticated_required": True,
            "production_eligible": False,
            "release_evidence": False,
            "waived_gates": copy.deepcopy(WAIVED_GATES),
            "nonwaivable_controls": copy.deepcopy(NONWAIVABLE_CONTROLS),
        },
        "execution_claim": None,
        "recovery_source": None,
        "receipt_reservation": copy.deepcopy(reservation),
        "status": "failed_prewrite",
        "external_write_started": False,
        "started_at": now,
        "updated_at": now,
        "redaction": copy.deepcopy(REDACTION),
        "stages": [
            {
                "name": "local_preflight",
                "effect": "local_read",
                "status": "failed",
                "started_at": now,
                "finished_at": now,
                "error_code": error_code,
                "recovery": "safe_prewrite_failure; correct inputs and submit a fresh testing request",
            }
        ],
        "observations": {"prewrite": None, "published_candidate": None, "postwrite": None},
        "verification": {
            "route_url": _route_url(target, _require_path_name(args.path_name)),
            "route_verified": None,
            "configuration_verified": None,
            "pre_deploy_app_config_digest": None,
            "post_deploy_app_config_digest": None,
            "authentication_certification": "pending_external_acceptance",
        },
    }
    receipt["receipt_hash"] = core._document_hash(receipt, "receipt_hash")
    return receipt


def _assert_receipt_redacted(value: Any, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if normalized in {
                "accesstoken", "clientsecret", "password", "privatekey",
            } or (normalized == "authorization" and path):
                core._fail("Testing receipt contains a prohibited secret-bearing field.")
            _assert_receipt_redacted(child, (*path, str(key)))
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _assert_receipt_redacted(child, (*path, str(index)))
        return
    if not isinstance(value, str):
        return
    secret_patterns = (
        r"-----BEGIN (?:RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----",
        r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{20,}",
        r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
        r"\b(?:sk-|gh[pousr]_)[A-Za-z0-9_-]{20,}\b",
    )
    if any(re.search(pattern, value) for pattern in secret_patterns):
        core._fail("Testing receipt contains prohibited secret-like material.")


def _validate_observation(value: Any, label: str) -> None:
    if value is None:
        return
    required = {
        "deploymentId", "systemName", "deployVersion", "currentVersion",
        "routeName", "version", "appName", "appUrl", "operation",
    }
    if not isinstance(value, dict) or set(value) != required:
        core._fail(f"Testing receipt {label} observation has an invalid shape.")
    if value["deploymentId"] is not None and (
        not isinstance(value["deploymentId"], str)
        or core.GUID_RE.fullmatch(value["deploymentId"]) is None
    ):
        core._fail(f"Testing receipt {label} deploymentId is invalid.")
    if value["systemName"] is not None and (
        not isinstance(value["systemName"], str)
        or core.APP_SYSTEM_NAME_RE.fullmatch(value["systemName"]) is None
    ):
        core._fail(f"Testing receipt {label} systemName is invalid.")
    if value["deployVersion"] is not None and (
        not isinstance(value["deployVersion"], int) or value["deployVersion"] < 1
    ):
        core._fail(f"Testing receipt {label} deployVersion is invalid.")
    for field in ("currentVersion", "version"):
        if value[field] is not None:
            if not isinstance(value[field], str):
                core._fail(f"Testing receipt {label} {field} is invalid.")
            core._parse_semver(value[field], f"Testing receipt {label} {field}")
    for field in ("routeName", "appName", "appUrl", "operation"):
        if not isinstance(value[field], str) or not value[field]:
            core._fail(f"Testing receipt {label} {field} is invalid.")
    if value["operation"] not in {
        "testing_create_verify", "testing_create_post", "testing_upgrade_pre",
        "testing_upgrade_candidate", "testing_upgrade_execute", "testing_upgrade_post",
        "deploy", "recovery_verify",
    }:
        core._fail(f"Testing receipt {label} operation is invalid.")


def _validate_observation_binding(
    value: Any,
    label: str,
    target: dict[str, Any],
    candidate: dict[str, Any],
) -> None:
    if value is None:
        return
    expected = {
        "routeName": candidate["path_name"],
        "version": candidate["version"],
        "appName": candidate["app_name"],
        "appUrl": _route_url(target, candidate["path_name"]),
    }
    for field, expected_value in expected.items():
        if value[field] != expected_value:
            core._fail(f"Testing receipt {label} {field} is not candidate-bound.")
    if candidate["mode"] == "dist" and candidate["intent"] == "create":
        if label == "prewrite" and (
            value["operation"] != "testing_create_verify"
            or any(value[field] is not None for field in (
                "deploymentId", "systemName", "deployVersion", "currentVersion",
            ))
        ):
            core._fail("Testing receipt create prewrite observation is invalid.")
        if label == "postwrite" and value["operation"] not in {
            "deploy", "testing_create_post",
        }:
            core._fail("Testing receipt create postwrite observation is invalid.")
    elif candidate["mode"] == "dist":
        identity = {"deploymentId": candidate["deployment_id"]}
        for field, expected_value in identity.items():
            if value[field] != expected_value:
                core._fail(f"Testing receipt dist upgrade {label} {field} is not candidate-bound.")
        if label == "prewrite":
            if (
                value["operation"] != "testing_upgrade_pre"
                or value["currentVersion"] != candidate["current_version"]
                or value["systemName"] is not None
                or value["deployVersion"] is not None
            ):
                core._fail("Testing receipt dist upgrade prewrite observation is invalid.")
        elif label == "published_candidate":
            if (
                value["operation"] != "testing_upgrade_candidate"
                or value["currentVersion"] != candidate["current_version"]
                or value["systemName"] != candidate["system_name"]
                or value["deployVersion"] != candidate["deploy_version"]
            ):
                core._fail("Testing receipt published candidate observation is invalid.")
        elif (
            value["operation"] != "testing_upgrade_post"
            or value["currentVersion"] != candidate["version"]
            or value["systemName"] != candidate["system_name"]
            or value["deployVersion"] != candidate["deploy_version"]
        ):
            core._fail("Testing receipt dist upgrade postwrite observation is invalid.")
    elif candidate["mode"] == "reconciled":
        if value["operation"] != "recovery_verify":
            core._fail("Testing receipt upgrade observation is invalid.")
        identity = {
            "deploymentId": candidate["deployment_id"],
            "systemName": candidate["system_name"],
            "deployVersion": candidate["deploy_version"],
        }
        for field, expected_value in identity.items():
            if value[field] != expected_value:
                core._fail(f"Testing receipt upgrade {label} {field} is not candidate-bound.")
        expected_current = (
            candidate["current_version"] if label == "prewrite" else candidate["version"]
        )
        if value["currentVersion"] != expected_current:
            core._fail(
                f"Testing receipt upgrade {label} currentVersion is not candidate-bound."
            )
    else:
        identity = {
            "deploymentId": candidate["deployment_id"],
            "systemName": candidate["system_name"],
            "deployVersion": candidate["deploy_version"],
        }
        for field, expected_value in identity.items():
            if value[field] != expected_value:
                core._fail(
                    f"Testing receipt publish recovery {label} {field} is not candidate-bound."
                )
        if label in {"prewrite", "published_candidate"}:
            if (
                value["operation"] != "testing_upgrade_candidate"
                or value["currentVersion"] != candidate["current_version"]
            ):
                core._fail(
                    "Testing receipt publish recovery candidate observation is invalid."
                )
        elif (
            value["operation"] != "testing_upgrade_post"
            or value["currentVersion"] != candidate["version"]
        ):
            core._fail("Testing receipt publish recovery postwrite observation is invalid.")


def _validate_stage(stage: Any) -> None:
    if not isinstance(stage, dict):
        core._fail("Testing receipt stages must be objects.")
    allowed = {"name", "effect", "status", "started_at", "finished_at", "error_code", "recovery"}
    if not {"name", "effect", "status"}.issubset(stage) or not set(stage).issubset(allowed):
        core._fail("Testing receipt stage fields are invalid.")
    if not isinstance(stage["name"], str) or not stage["name"]:
        core._fail("Testing receipt stage name is invalid.")
    if stage["effect"] not in {"local_read", "local_write", "external_read", "external_write"}:
        core._fail("Testing receipt stage effect is invalid.")
    if stage["status"] not in {"pending", "running", "failed", "succeeded"}:
        core._fail("Testing receipt stage status is invalid.")
    for field in ("started_at", "finished_at"):
        if field in stage:
            recovery._require_iso8601(stage[field], f"Testing receipt stage {field}")
    if "error_code" in stage and (
        not isinstance(stage["error_code"], str)
        or re.fullmatch(r"[A-Z0-9_]+", stage["error_code"]) is None
    ):
        core._fail("Testing receipt stage error code is invalid.")
    if "recovery" in stage and (
        not isinstance(stage["recovery"], str) or not stage["recovery"]
    ):
        core._fail("Testing receipt stage recovery text is invalid.")
    status = stage["status"]
    has_started = "started_at" in stage
    has_finished = "finished_at" in stage
    has_failure = "error_code" in stage or "recovery" in stage
    if status == "pending" and (has_started or has_finished or has_failure):
        core._fail("Pending testing receipt stage contains execution state.")
    if status == "running" and (not has_started or has_finished or has_failure):
        core._fail("Running testing receipt stage state is invalid.")
    if status == "succeeded" and (not has_started or not has_finished or has_failure):
        core._fail("Successful testing receipt stage state is invalid.")
    if status == "failed" and (
        not has_started
        or not has_finished
        or "error_code" not in stage
        or "recovery" not in stage
    ):
        core._fail("Failed testing receipt stage state is invalid.")
    if has_started and has_finished:
        started = datetime.fromisoformat(stage["started_at"].replace("Z", "+00:00"))
        finished = datetime.fromisoformat(stage["finished_at"].replace("Z", "+00:00"))
        if finished < started:
            core._fail("Testing receipt stage finished before it started.")


def _validate_candidate_record(candidate: Any) -> None:
    candidate_fields = {
        "mode", "intent", "package_name", "app_name", "version", "path_name", "tags",
        "git_head", "git_status_digest", "source_sha", "dist_digest",
        "uipath_config_digest", "package_content_digest", "package_file_digest",
        "recovery_plan_hash", "deployment_id", "system_name", "deploy_version",
        "current_version", "runtime_manifest_hash", "node_executable",
        "node_executable_sha256", "node_version", "runtime_app_config_digest",
        "runtime_immutable_digest",
        "helper_sha256", "main_file", "content_type",
    }
    if not isinstance(candidate, dict) or set(candidate) != candidate_fields:
        core._fail("Testing receipt candidate fields are invalid.")
    _assert_common_candidate(candidate)
    if (candidate["mode"], candidate["intent"]) not in {
        ("dist", "create"),
        ("dist", "upgrade"),
        ("reconciled", "upgrade"),
        ("published-recovery", "upgrade"),
    }:
        core._fail("Testing receipt candidate mode and intent are invalid.")
    if not isinstance(candidate["node_executable"], str) or not Path(
        candidate["node_executable"]
    ).is_absolute():
        core._fail("Testing receipt Node.js path is invalid.")
    if not isinstance(candidate["node_version"], str) or not candidate["node_version"]:
        core._fail("Testing receipt Node.js version is invalid.")
    if SUPPORTED_NODE_RUNTIMES.get(candidate["node_version"]) != candidate[
        "node_executable_sha256"
    ]:
        core._fail("Testing receipt Node.js runtime is not an allowed exact build.")


def _validate_claim_record(claim: Any) -> None:
    claim_fields = {"path", "key", "file_sha256", "claim_hash", "released"}
    if not isinstance(claim, dict) or set(claim) != claim_fields:
        core._fail("Testing receipt claim fields are invalid.")
    if not isinstance(claim["path"], str) or not Path(claim["path"]).is_absolute():
        core._fail("Testing receipt claim path is invalid.")
    for field in ("key", "file_sha256", "claim_hash"):
        core._validate_hash(claim[field], f"Testing receipt claim {field}")
    if not isinstance(claim["released"], bool):
        core._fail("Testing receipt claim release state is invalid.")


def _validate_publish_recovery_source_record(
    source: Any,
    target: dict[str, Any],
    candidate: dict[str, Any],
) -> None:
    fields = {
        "failed_receipt_path",
        "failed_receipt_file_sha256",
        "failed_receipt_hash",
        "failed_candidate_hash",
        "failed_helper_sha256",
        "retained_execution_claim",
        "workspace_path",
        "package_path",
        "runtime_manifest_path",
        "runtime_manifest_file_sha256",
        "pre_recovery_app_config_digest",
    }
    if not isinstance(source, dict) or set(source) != fields:
        core._fail("Testing publish recovery source evidence is invalid.")
    for field in (
        "failed_receipt_file_sha256",
        "failed_receipt_hash",
        "failed_candidate_hash",
        "failed_helper_sha256",
        "runtime_manifest_file_sha256",
        "pre_recovery_app_config_digest",
    ):
        core._validate_hash(source[field], f"Testing publish recovery {field}")
    for field in (
        "failed_receipt_path",
        "workspace_path",
        "package_path",
        "runtime_manifest_path",
    ):
        path = Path(source[field])
        if not path.is_absolute():
            core._fail(f"Testing publish recovery {field} must be absolute.")
    receipt_path = Path(source["failed_receipt_path"])
    if receipt_path.is_symlink() or not receipt_path.is_file():
        core._fail("Testing publish recovery source receipt is missing.")
    if core._hash_file(receipt_path, "publish recovery source receipt") != source[
        "failed_receipt_file_sha256"
    ]:
        core._fail("Testing publish recovery source receipt bytes changed.")
    try:
        failed_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        core._fail("Testing publish recovery source receipt is unreadable.")
    if (
        not isinstance(failed_receipt, dict)
        or failed_receipt.get("receipt_hash") != source["failed_receipt_hash"]
        or core._document_hash(failed_receipt, "receipt_hash")
        != source["failed_receipt_hash"]
        or core._hash_json(failed_receipt.get("candidate"))
        != source["failed_candidate_hash"]
        or failed_receipt.get("helper_sha256") != source["failed_helper_sha256"]
        or failed_receipt.get("target") != target
    ):
        core._fail("Testing publish recovery source receipt binding is invalid.")
    failed_candidate = failed_receipt.get("candidate")
    invariant_fields = {
        "intent",
        "package_name",
        "app_name",
        "version",
        "path_name",
        "tags",
        "git_head",
        "git_status_digest",
        "source_sha",
        "dist_digest",
        "uipath_config_digest",
        "package_content_digest",
        "package_file_digest",
        "recovery_plan_hash",
        "deployment_id",
        "system_name",
        "deploy_version",
        "current_version",
        "runtime_manifest_hash",
        "node_executable",
        "node_executable_sha256",
        "node_version",
        "runtime_immutable_digest",
        "main_file",
        "content_type",
    }
    if not isinstance(failed_candidate, dict) or any(
        failed_candidate.get(field) != candidate.get(field)
        for field in invariant_fields
    ):
        core._fail("Testing publish recovery candidate diverges from its failed receipt.")
    retained = source["retained_execution_claim"]
    _validate_claim_record(retained)
    if retained["released"]:
        core._fail("Testing publish recovery requires the original retained claim.")
    retained_path = Path(retained["path"])
    if retained_path.is_symlink() or not retained_path.is_file():
        core._fail("Testing publish recovery original retained claim is missing.")
    if core._hash_file(retained_path, "publish recovery original claim") != retained[
        "file_sha256"
    ]:
        core._fail("Testing publish recovery original claim bytes changed.")
    if retained != failed_receipt.get("execution_claim"):
        core._fail("Testing publish recovery original claim is not receipt-bound.")
    workspace = Path(source["workspace_path"])
    if workspace.is_symlink() or not workspace.is_dir():
        core._fail("Testing publish recovery workspace is missing.")
    for field in ("package_path", "runtime_manifest_path"):
        try:
            Path(source[field]).resolve(strict=True).relative_to(workspace.resolve(strict=True))
        except (OSError, ValueError):
            core._fail(f"Testing publish recovery {field} escapes its workspace.")
    package_path = Path(source["package_path"])
    if package_path.is_symlink() or not package_path.is_file():
        core._fail("Testing publish recovery package is missing.")
    if core._hash_file(package_path, "publish recovery package") != candidate[
        "package_file_digest"
    ]:
        core._fail("Testing publish recovery package bytes changed.")
    runtime_manifest_path = Path(source["runtime_manifest_path"])
    if runtime_manifest_path.is_symlink() or not runtime_manifest_path.is_file():
        core._fail("Testing publish recovery runtime manifest is missing.")
    if core._hash_file(runtime_manifest_path, "publish recovery runtime manifest") != source[
        "runtime_manifest_file_sha256"
    ]:
        core._fail("Testing publish recovery runtime manifest bytes changed.")


def _validate_receipt(receipt: dict[str, Any]) -> None:
    _assert_receipt_redacted(receipt)
    required = {
        "kind", "schema_version", "helper_sha256", "attempt_phase",
        "preflight_error_code", "authorization", "target",
        "candidate", "policy", "execution_claim", "status", "external_write_started",
        "started_at", "updated_at", "redaction", "stages", "observations",
        "verification", "receipt_reservation", "recovery_source", "receipt_hash",
    }
    if set(receipt) != required:
        core._fail("Testing receipt fields do not match schema 1.2.")
    if receipt["kind"] != RECEIPT_KIND or receipt["schema_version"] != RECEIPT_SCHEMA_VERSION:
        core._fail("Testing receipt kind or schema version is invalid.")
    core._validate_hash(receipt["helper_sha256"], "Testing receipt helper hash")
    if receipt["attempt_phase"] not in {"preflight", "claimed"}:
        core._fail("Testing receipt attempt phase is invalid.")
    if receipt["preflight_error_code"] is not None and (
        not isinstance(receipt["preflight_error_code"], str)
        or re.fullmatch(r"[A-Z0-9_]+", receipt["preflight_error_code"]) is None
    ):
        core._fail("Testing receipt preflight error code is invalid.")
    authorization = receipt["authorization"]
    if not isinstance(authorization, dict) or authorization != {
        "mode": "explicit_testing_request",
        "testing_only": True,
        "execute": True,
        "purpose": authorization.get("purpose") if isinstance(authorization, dict) else None,
    }:
        core._fail("Testing receipt authorization is invalid.")
    _require_text(authorization["purpose"], "Testing receipt purpose")
    target = receipt["target"]
    target_fields = {
        "environment", "control_plane_url", "organization_name", "organization_id",
        "tenant_name", "tenant_id", "folder_key", "client_id", "cli_profile",
        "cli_profile_hash", "cli_executable", "cli_executable_sha256", "cli_version",
    }
    if not isinstance(target, dict) or set(target) != target_fields:
        core._fail("Testing receipt target fields are invalid.")
    core._validate_target_binding(
        target["environment"], target["control_plane_url"], None,
        label_prefix="Testing receipt",
    )
    for field in ("organization_id", "tenant_id", "folder_key", "client_id"):
        _require_guid(target[field], f"Testing receipt target {field}")
    if re.fullmatch(
        r"[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?", target["organization_name"]
    ) is None:
        core._fail("Testing receipt organization name is invalid.")
    _require_text(target["tenant_name"], "Testing receipt tenant name")
    if not isinstance(target["cli_profile"], str) or re.fullmatch(
        r"[A-Za-z0-9._-]+", target["cli_profile"]
    ) is None:
        core._fail("Testing receipt CLI profile name is invalid.")
    for field in ("cli_profile_hash", "cli_executable_sha256"):
        core._validate_hash(target[field], f"Testing receipt target {field}")
    expected_profile_hash = core._hash_json(
        {
            "name": target["cli_profile"],
            "environment": target["environment"],
            "control_plane_url": target["control_plane_url"],
            "org_id": target["organization_id"],
            "tenant_id": target["tenant_id"],
        }
    )
    if target["cli_profile_hash"] != expected_profile_hash:
        core._fail("Testing receipt CLI profile binding is invalid.")
    if target["cli_version"] != EXPECTED_CLI_VERSION:
        core._fail("Testing receipt CLI version is invalid.")
    if not isinstance(target["cli_executable"], str) or not Path(target["cli_executable"]).is_absolute():
        core._fail("Testing receipt CLI path is invalid.")
    if target["cli_executable_sha256"] != EXPECTED_CLI_SHA256:
        core._fail("Testing receipt CLI is not the supported exact build.")
    candidate = receipt["candidate"]
    if receipt["attempt_phase"] == "preflight":
        if candidate is not None or receipt["preflight_error_code"] is None:
            core._fail("Preflight testing receipts may not claim a candidate.")
    else:
        if receipt["preflight_error_code"] is not None:
            core._fail("Claimed testing receipts may not contain a preflight error code.")
        _validate_candidate_record(candidate)
        if candidate["helper_sha256"] != receipt["helper_sha256"]:
            core._fail("Testing receipt helper binding is inconsistent.")
    if receipt["policy"] != {
        "policy_version": POLICY_VERSION,
        "data_classification": "synthetic_only",
        "internal_authenticated_required": True,
        "production_eligible": False,
        "release_evidence": False,
        "waived_gates": WAIVED_GATES,
        "nonwaivable_controls": NONWAIVABLE_CONTROLS,
    }:
        core._fail("Testing receipt policy was weakened.")
    claim = receipt["execution_claim"]
    if receipt["attempt_phase"] == "preflight":
        if claim is not None:
            core._fail("Preflight testing receipts may not claim an execution candidate.")
    else:
        _validate_claim_record(claim)
        if claim["key"] != _claim_key(target, candidate):
            core._fail("Testing receipt claim does not bind the exact candidate.")
        claim_path = Path(claim["path"])
        if claim["released"]:
            if receipt["status"] != "failed_prewrite" or claim_path.exists():
                core._fail("Testing receipt claim release state is inconsistent.")
        else:
            if claim_path.is_symlink() or not claim_path.is_file():
                core._fail("Testing receipt retained claim is missing.")
            if core._hash_file(claim_path, "testing receipt retained claim") != claim[
                "file_sha256"
            ]:
                core._fail("Testing receipt retained claim bytes changed.")
    recovery_source = receipt["recovery_source"]
    if candidate is not None and candidate["mode"] == "published-recovery":
        _validate_publish_recovery_source_record(recovery_source, target, candidate)
    elif recovery_source is not None:
        core._fail("Only published-recovery receipts may contain recovery source evidence.")
    reservation = receipt["receipt_reservation"]
    if not isinstance(reservation, dict) or set(reservation) != {
        "path", "file_sha256", "reservation_hash",
    }:
        core._fail("Testing receipt reservation fields are invalid.")
    if not isinstance(reservation["path"], str) or not Path(reservation["path"]).is_absolute():
        core._fail("Testing receipt reservation path is invalid.")
    for field in ("file_sha256", "reservation_hash"):
        core._validate_hash(reservation[field], f"Testing receipt reservation {field}")
    statuses = {
        "in_progress", "failed_prewrite", "publish_indeterminate",
        "published_not_deployed", "deploy_indeterminate", "deployed_unverified",
        "succeeded_testing",
    }
    if receipt["status"] not in statuses or not isinstance(receipt["external_write_started"], bool):
        core._fail("Testing receipt status is invalid.")
    recovery._require_iso8601(receipt["started_at"], "Testing receipt started_at")
    recovery._require_iso8601(receipt["updated_at"], "Testing receipt updated_at")
    if receipt["redaction"] != REDACTION:
        core._fail("Testing receipt redaction policy is invalid.")
    if not isinstance(receipt["stages"], list) or not receipt["stages"]:
        core._fail("Testing receipt stages are invalid.")
    for stage in receipt["stages"]:
        _validate_stage(stage)
    names = [stage["name"] for stage in receipt["stages"]]
    if len(names) != len(set(names)):
        core._fail("Testing receipt stage names must be unique.")
    if receipt["attempt_phase"] == "preflight":
        expected_stages = [("local_preflight", "local_read")]
    elif candidate["mode"] == "dist":
        expected_stages = (
            DIST_UPGRADE_STAGE_CONTRACT
            if candidate["intent"] == "upgrade"
            else DIST_STAGE_CONTRACT
        )
    elif candidate["mode"] == "published-recovery":
        expected_stages = PUBLISHED_RECOVERY_STAGE_CONTRACT
    else:
        expected_stages = RECONCILED_STAGE_CONTRACT
    observed_stages = [(stage["name"], stage["effect"]) for stage in receipt["stages"]]
    if observed_stages != expected_stages:
        core._fail("Testing receipt stages do not match the exact candidate contract.")
    if not isinstance(receipt["observations"], dict) or set(receipt["observations"]) != {
        "prewrite", "published_candidate", "postwrite",
    }:
        core._fail("Testing receipt observations are invalid.")
    _validate_observation(receipt["observations"]["prewrite"], "prewrite")
    _validate_observation(receipt["observations"]["published_candidate"], "published_candidate")
    _validate_observation(receipt["observations"]["postwrite"], "postwrite")
    if candidate is not None:
        _validate_observation_binding(
            receipt["observations"]["prewrite"], "prewrite", target, candidate
        )
        _validate_observation_binding(
            receipt["observations"]["published_candidate"], "published_candidate", target, candidate
        )
        _validate_observation_binding(
            receipt["observations"]["postwrite"], "postwrite", target, candidate
        )
    verification = receipt["verification"]
    if not isinstance(verification, dict) or set(verification) != {
        "route_url", "route_verified", "configuration_verified",
        "pre_deploy_app_config_digest", "post_deploy_app_config_digest",
        "authentication_certification",
    }:
        core._fail("Testing receipt verification fields are invalid.")
    if not isinstance(verification["route_url"], str) or not verification["route_url"].startswith("https://"):
        core._fail("Testing receipt route URL is invalid.")
    if candidate is not None and verification["route_url"] != _route_url(
        target, candidate["path_name"]
    ):
        core._fail("Testing receipt route URL is not target-bound.")
    for field in ("route_verified", "configuration_verified"):
        if verification[field] not in (None, True, False):
            core._fail("Testing receipt verification state is invalid.")
    if receipt["attempt_phase"] == "preflight":
        if verification["pre_deploy_app_config_digest"] is not None:
            core._fail("Preflight testing receipt cannot claim an app config digest.")
    else:
        core._validate_hash(
            verification["pre_deploy_app_config_digest"],
            "Testing receipt pre-deploy app config digest",
        )
    if verification["post_deploy_app_config_digest"] is not None:
        core._validate_hash(
            verification["post_deploy_app_config_digest"],
            "Testing receipt post-deploy app config digest",
        )
    if verification["authentication_certification"] != "pending_external_acceptance":
        core._fail("Testing receipt may not claim authentication certification automatically.")
    external_stages = [stage for stage in receipt["stages"] if stage["effect"] == "external_write"]
    external_started = any(
        stage["status"] != "pending" or "started_at" in stage for stage in external_stages
    )
    if receipt["external_write_started"] != external_started:
        core._fail("Testing receipt external-write state is inconsistent.")
    if receipt["status"] == "failed_prewrite" and external_started:
        core._fail("Testing receipt cannot report failed_prewrite after a write starts.")
    if receipt["status"] == "in_progress" and external_started:
        core._fail("Testing receipt cannot remain in_progress after a write starts.")
    if receipt["attempt_phase"] == "preflight" and (
        receipt["status"] != "failed_prewrite"
        or receipt["external_write_started"]
        or receipt["observations"] != {"prewrite": None, "published_candidate": None, "postwrite": None}
        or any(stage["effect"] == "external_write" for stage in receipt["stages"])
    ):
        core._fail("Preflight testing receipt state is inconsistent.")
    stage_map = {stage["name"]: stage for stage in receipt["stages"]}
    publish_stage = stage_map.get("publish")
    deploy_stage = stage_map.get("deploy")
    if receipt["status"] == "publish_indeterminate" and (
        publish_stage is None or publish_stage["status"] not in {"running", "failed"}
    ):
        core._fail("Testing receipt publish-indeterminate state is inconsistent.")
    if receipt["status"] == "published_not_deployed" and (
        publish_stage is None
        or publish_stage["status"] != "succeeded"
        or deploy_stage is None
        or deploy_stage["status"] != "pending"
    ):
        core._fail("Testing receipt published-not-deployed state is inconsistent.")
    if receipt["status"] == "deploy_indeterminate" and (
        deploy_stage is None or deploy_stage["status"] not in {"running", "failed"}
    ):
        core._fail("Testing receipt deploy-indeterminate state is inconsistent.")
    if receipt["status"] == "deployed_unverified" and (
        deploy_stage is None or deploy_stage["status"] != "succeeded"
    ):
        core._fail("Testing receipt deployed-unverified state is inconsistent.")
    if receipt["status"] == "succeeded_testing" and (
        not external_stages
        or any(stage["status"] != "succeeded" for stage in receipt["stages"])
        or receipt["observations"]["postwrite"] is None
        or (
            candidate is not None
            and candidate["mode"] in {"dist", "published-recovery"}
            and candidate["intent"] == "upgrade"
            and receipt["observations"]["published_candidate"] is None
        )
        or verification["route_verified"] is not True
        or verification["configuration_verified"] is not True
        or verification["post_deploy_app_config_digest"] is None
    ):
        core._fail("Successful testing receipt has incomplete stages.")
    core._validate_hash(receipt["receipt_hash"], "Testing receipt hash")
    if core._document_hash(receipt, "receipt_hash") != receipt["receipt_hash"]:
        core._fail("Testing receipt hash is invalid.")


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    reservation_path = Path(receipt["receipt_reservation"]["path"])
    expected_reservation_path = path.with_name(f".{path.name}.reservation.json")
    if reservation_path != expected_reservation_path:
        core._fail("Testing receipt reservation does not bind the exact receipt path.")
    if not reservation_path.is_file() or reservation_path.is_symlink():
        core._fail("Testing receipt reservation is missing or invalid.")
    if core._hash_file(reservation_path, "testing receipt reservation") != receipt[
        "receipt_reservation"
    ]["file_sha256"]:
        core._fail("Testing receipt reservation changed; refusing concurrent overwrite.")
    try:
        reservation = json.loads(reservation_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        core._fail("Testing receipt reservation is unreadable.")
    if (
        not isinstance(reservation, dict)
        or reservation.get("reservation_hash")
        != receipt["receipt_reservation"]["reservation_hash"]
        or reservation.get("receipt_path_sha256")
        != core._hash_json({"receipt_path": str(path)})
        or core._document_hash(reservation, "reservation_hash")
        != reservation.get("reservation_hash")
    ):
        core._fail("Testing receipt reservation binding is invalid.")
    receipt["updated_at"] = core._utc_now()
    receipt["receipt_hash"] = core._document_hash(receipt, "receipt_hash")
    _validate_receipt(receipt)
    core._atomic_write_json(path, receipt)


def _stage(receipt: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [stage for stage in receipt["stages"] if stage["name"] == name]
    if len(matches) != 1:
        core._fail(f"Testing receipt stage is not unique: {name}")
    return matches[0]


def _start_stage(receipt: dict[str, Any], path: Path, name: str, *, external_write: bool = False) -> None:
    stage = _stage(receipt, name)
    stage["status"] = "running"
    stage["started_at"] = core._utc_now()
    stage.pop("finished_at", None)
    stage.pop("error_code", None)
    stage.pop("recovery", None)
    if external_write:
        receipt["external_write_started"] = True
        if name == "publish":
            receipt["status"] = "publish_indeterminate"
        else:
            receipt["status"] = "deploy_indeterminate"
    _write_receipt(path, receipt)


def _finish_stage(
    receipt: dict[str, Any],
    path: Path,
    name: str,
    *,
    receipt_status: str | None = None,
) -> None:
    stage = _stage(receipt, name)
    stage["status"] = "succeeded"
    stage["finished_at"] = core._utc_now()
    if receipt_status is not None:
        receipt["status"] = receipt_status
    _write_receipt(path, receipt)


def _fail_stage(
    receipt: dict[str, Any],
    path: Path,
    name: str,
    *,
    status: str,
    error_code: str,
    recovery_text: str,
) -> None:
    stage = _stage(receipt, name)
    stage["status"] = "failed"
    stage["finished_at"] = core._utc_now()
    stage["error_code"] = error_code
    stage["recovery"] = recovery_text
    receipt["status"] = status
    _write_receipt(path, receipt)


def _receipt_path(value: str | None) -> Path:
    if not value:
        core._fail("--receipt-output is required.")
    path = Path(value).expanduser().resolve(strict=False)
    if not path.is_absolute() or not path.parent.is_dir() or path.parent.is_symlink():
        core._fail("--receipt-output must be a new file in an existing real directory.")
    if path.exists():
        core._fail("--receipt-output refuses to overwrite; blind replay is prohibited.")
    repository = subprocess.run(
        ["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if repository.returncode == 0:
        root = Path(repository.stdout.strip()).resolve(strict=True)
        _require_ignored_or_external(path, root)
        _require_ignored_or_external(
            path.with_name(f".{path.name}.reservation.json"), root
        )
    return path


def _reserve_receipt(path: Path) -> dict[str, Any]:
    reservation_path = path.with_name(f".{path.name}.reservation.json")
    document = {
        "kind": "uipcodedappdeploy.testing-receipt-reservation",
        "schema_version": "1.0",
        "created_at": core._utc_now(),
        "receipt_path_sha256": core._hash_json({"receipt_path": str(path)}),
    }
    document["reservation_hash"] = core._document_hash(document, "reservation_hash")
    payload = json.dumps(document, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    try:
        descriptor = os.open(
            reservation_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        core._fail("Testing receipt path is already reserved; blind or concurrent replay is prohibited.")
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    directory_descriptor = os.open(reservation_path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)
    return {
        "path": str(reservation_path),
        "file_sha256": core._hash_file(reservation_path, "testing receipt reservation"),
        "reservation_hash": document["reservation_hash"],
    }


def _base_candidate(
    args: argparse.Namespace,
    *,
    git_head: str | None,
    git_status_digest: str,
    source_sha: str | None,
    dist_digest: str | None,
    uipath_config_digest: str,
    package_content_digest: str,
    package_file_digest: str,
    recovery_plan_hash: str | None,
    deployment_id: str | None,
    system_name: str | None,
    deploy_version: int | None,
    current_version: str | None,
    runtime_manifest_hash: str | None,
    node_executable: str,
    node_executable_sha256: str,
    node_version: str,
    runtime_app_config_digest: str,
    runtime_immutable_digest: str,
    main_file: str,
    content_type: str,
) -> dict[str, Any]:
    version = _require_text(args.version, "--version")
    core._parse_semver(version, "--version")
    return {
        "mode": args.candidate_mode,
        "intent": args.intent,
        "package_name": _require_text(args.package_name, "--package-name"),
        "app_name": _require_text(args.app_name, "--app-name"),
        "version": version,
        "path_name": _require_path_name(args.path_name),
        "tags": core._normalize_tags(args.tags, "--tags"),
        "git_head": git_head,
        "git_status_digest": git_status_digest,
        "source_sha": source_sha,
        "dist_digest": dist_digest,
        "uipath_config_digest": uipath_config_digest,
        "package_content_digest": package_content_digest,
        "package_file_digest": package_file_digest,
        "recovery_plan_hash": recovery_plan_hash,
        "deployment_id": deployment_id,
        "system_name": system_name,
        "deploy_version": deploy_version,
        "current_version": current_version,
        "runtime_manifest_hash": runtime_manifest_hash,
        "node_executable": node_executable,
        "node_executable_sha256": node_executable_sha256,
        "node_version": node_version,
        "runtime_app_config_digest": runtime_app_config_digest,
        "runtime_immutable_digest": runtime_immutable_digest,
        "helper_sha256": core._hash_file(Path(__file__), "testing helper"),
        "main_file": main_file,
        "content_type": content_type,
    }


def _assert_common_candidate(candidate: dict[str, Any]) -> None:
    if not isinstance(candidate["tags"], list) or not candidate["tags"] or any(
        not isinstance(tag, str) or re.fullmatch(r"[a-z0-9][a-z0-9-]*", tag) is None
        for tag in candidate["tags"]
    ) or len(set(candidate["tags"])) != len(candidate["tags"]):
        core._fail("--tags must contain at least one testing tag.")
    for field in ("package_name", "app_name"):
        if not isinstance(candidate[field], str) or not candidate[field]:
            core._fail(f"Testing candidate {field} is invalid.")
    if not isinstance(candidate["version"], str):
        core._fail("Testing candidate version is invalid.")
    core._parse_semver(candidate["version"], "Testing candidate version")
    if _require_path_name(candidate["path_name"]) != candidate["path_name"]:
        core._fail("Testing candidate route is invalid.")
    for digest_field in (
        "git_status_digest",
        "uipath_config_digest",
        "package_content_digest",
        "package_file_digest",
        "node_executable_sha256",
        "runtime_app_config_digest",
        "runtime_immutable_digest",
        "helper_sha256",
    ):
        core._validate_hash(candidate[digest_field], f"Testing candidate {digest_field}")
    if candidate["mode"] in {"dist", "published-recovery"} and candidate["dist_digest"] is None:
        core._fail("Dist-derived testing candidate requires an exact dist digest.")
    if candidate["mode"] == "reconciled" and candidate["recovery_plan_hash"] is None:
        core._fail("Reconciled testing candidate requires a recovery plan hash input.")
    if candidate["mode"] == "dist" and candidate["intent"] == "create" and any(
        candidate[field] is not None
        for field in ("recovery_plan_hash", "deployment_id", "system_name", "deploy_version", "current_version")
    ):
        core._fail("Dist create candidate may not claim an existing deployment.")
    if candidate["mode"] == "dist" and candidate["intent"] == "upgrade" and (
        candidate["recovery_plan_hash"] is not None
        or candidate["system_name"] is None
        or candidate["deploy_version"] is None
        or candidate["deployment_id"] is None
        or candidate["current_version"] is None
    ):
        core._fail("Dist upgrade candidate requires the exact deployment, candidate identity, deploy version, and current version before publication.")
    if candidate["mode"] == "reconciled" and (
        candidate["dist_digest"] is not None
        or any(
            candidate[field] is None
            for field in ("deployment_id", "system_name", "deploy_version", "current_version")
        )
    ):
        core._fail("Reconciled candidate deployment identity is incomplete.")
    if candidate["mode"] == "published-recovery" and (
        candidate["recovery_plan_hash"] is not None
        or any(
            candidate[field] is None
            for field in ("deployment_id", "system_name", "deploy_version", "current_version")
        )
    ):
        core._fail("Publish recovery candidate identity is incomplete.")
    if not isinstance(candidate["main_file"], str) or not candidate["main_file"]:
        core._fail("Testing candidate main file is invalid.")
    if Path(candidate["main_file"]).is_absolute() or ".." in Path(candidate["main_file"]).parts:
        core._fail("Testing candidate main file must be relative.")
    if not isinstance(candidate["content_type"], str) or not candidate["content_type"]:
        core._fail("Testing candidate content type is invalid.")
    for optional_hash in ("dist_digest", "recovery_plan_hash", "runtime_manifest_hash"):
        if candidate[optional_hash] is not None:
            core._validate_hash(candidate[optional_hash], f"Testing candidate {optional_hash}")
    if candidate["git_head"] is not None and (
        not isinstance(candidate["git_head"], str)
        or re.fullmatch(r"[0-9a-f]{40}", candidate["git_head"]) is None
    ):
        core._fail("Testing candidate Git HEAD is invalid.")
    if candidate["source_sha"] is not None and (
        not isinstance(candidate["source_sha"], str)
        or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", candidate["source_sha"]) is None
    ):
        core._fail("Testing candidate source SHA is invalid.")
    if candidate["deployment_id"] is not None and (
        not isinstance(candidate["deployment_id"], str)
        or core.GUID_RE.fullmatch(candidate["deployment_id"]) is None
    ):
        core._fail("Testing candidate deployment ID is invalid.")
    if candidate["system_name"] is not None and (
        not isinstance(candidate["system_name"], str)
        or core.APP_SYSTEM_NAME_RE.fullmatch(candidate["system_name"]) is None
    ):
        core._fail("Testing candidate system name is invalid.")
    if candidate["deploy_version"] is not None and (
        not isinstance(candidate["deploy_version"], int) or candidate["deploy_version"] < 1
    ):
        core._fail("Testing candidate deploy version is invalid.")
    if candidate["current_version"] is not None:
        if not isinstance(candidate["current_version"], str):
            core._fail("Testing candidate current version is invalid.")
        core._parse_semver(candidate["current_version"], "Testing candidate current version")
    if candidate["intent"] == "upgrade":
        candidate_version = core._parse_semver(
            candidate["version"], "Testing candidate version"
        )
        current_version = core._parse_semver(
            candidate["current_version"], "Testing candidate current version"
        )
        if candidate_version.compare(current_version) <= 0:
            core._fail("Testing upgrade candidate version must be strictly newer than the current version.")


def _dist_create(
    args: argparse.Namespace,
    target: dict[str, Any],
    cli: Path,
    environment: dict[str, str],
    receipt_path: Path,
    reservation: dict[str, Any],
) -> Path:
    preflight_started = core._utc_now()
    local_times: dict[str, tuple[str, str]] = {}
    if args.intent not in {"create", "upgrade"}:
        core._fail("candidate mode dist supports only explicit create or upgrade intent.")
    expected_deployment_id = None
    expected_system_name = None
    expected_deploy_version = None
    expected_current_version = None
    if args.intent == "upgrade":
        expected_deployment_id = _require_guid(
            args.expected_deployment_id, "--expected-deployment-id"
        )
        expected_current_version = _require_text(
            args.expected_current_version, "--expected-current-version"
        )
        core._parse_semver(expected_current_version, "--expected-current-version")
        expected_system_name = _require_text(
            args.expected_system_name, "--expected-system-name"
        )
        if core.APP_SYSTEM_NAME_RE.fullmatch(expected_system_name) is None:
            core._fail("--expected-system-name must be an exact UiPath app system name.")
        if not isinstance(args.expected_deploy_version, int) or args.expected_deploy_version < 1:
            core._fail("--expected-deploy-version must be a positive integer.")
        expected_deploy_version = args.expected_deploy_version
    if not args.project_root:
        core._fail("--project-root is required for dist mode.")
    node_runtime = _resolve_node(args.node_executable, args.node_version)
    project_root = Path(args.project_root).expanduser().resolve(strict=True)
    if not project_root.is_dir() or project_root.is_symlink():
        core._fail("--project-root must be a real directory.")
    raw_dist = args.app_dist or ("app/dist" if (project_root / "app/dist").is_dir() else "dist")
    dist_source = Path(raw_dist).expanduser()
    if not dist_source.is_absolute():
        dist_source = project_root / dist_source
    dist_source = dist_source.resolve(strict=True)
    main_file = args.main_file or "index.html"
    if Path(main_file).is_absolute() or ".." in Path(main_file).parts:
        core._fail("--main-file must be relative to the dist.")
    if not (dist_source / main_file).is_file():
        core._fail("Testing dist does not contain the requested main file.")
    _audit_tracked_source(project_root, project_root)
    _audit_dist(dist_source)
    config_source = project_root / "uipath.json"
    config_document, config_payload = _load_and_audit_uipath_config(
        config_source, "Dist testing"
    )
    _validate_internal_config(config_document, target, _require_path_name(args.path_name))
    uipath_config_digest = core._hash_bytes(config_payload)
    protected_paths = [dist_source, config_source, cli.parents[3]]
    for manifest_name in ("package.json", "package-lock.json", "pyproject.toml"):
        manifest = project_root / manifest_name
        if manifest.exists():
            protected_paths.append(manifest)
    _validate_evidence_isolation(
        receipt_path,
        project_root,
        protected_paths,
        include_workspace=True,
    )
    git_head, git_status_digest, source_sha = _git_state(project_root)
    _validate_cli(target, project_root, environment, node_runtime)
    local_times["local_preflight"] = (preflight_started, core._utc_now())
    workspace = _workspace_for(receipt_path)
    stage_started = core._utc_now()
    copied_dist, dist_digest = _copy_exact_dist(dist_source, workspace)
    config_copy = workspace / "uipath.json"
    shutil.copy2(config_source, config_copy)
    if core._hash_file(config_copy, "testing workspace uipath.json") != uipath_config_digest:
        core._fail("uipath.json changed while copying into the testing workspace.")
    local_times["dist_copy"] = (stage_started, core._utc_now())
    package_name = _require_text(args.package_name, "--package-name")
    version = _require_text(args.version, "--version")
    core._parse_semver(version, "--version")
    package_dir = workspace / ".uipath"
    package_dir.mkdir()
    pack_command = [
        node_runtime["executable"], str(cli), "codedapp", "pack", str(copied_dist),
        "--name", package_name,
        "--version", version,
        "--output", str(package_dir),
        "--author", args.author or "UiPath testing",
        "--main-file", main_file,
        "--content-type", args.content_type or "webapp",
    ]
    stage_started = core._utc_now()
    try:
        _run_write(pack_command, workspace, environment, "PACK_FAILED")
    except TestingCommandError as exc:
        raise SystemExit(exc.code) from exc
    local_times["pack"] = (stage_started, core._utc_now())
    package_path = package_dir / f"{package_name}.{version}.nupkg"
    stage_started = core._utc_now()
    package_content_digest, package_file_digest = core._package_evidence(
        package_path,
        package_name=package_name,
        main_file=main_file,
    )
    _audit_package_archive(package_path)
    local_times["package_audit"] = (stage_started, core._utc_now())
    guard_config = _dist_guard_config(
        package_name,
        _require_text(args.app_name, "--app-name"),
        version,
        target,
        _require_path_name(args.path_name),
        args.intent,
    )
    stage_started = core._utc_now()
    runtime = _prepare_create_guard_runtime(
        cli, node_runtime, workspace, guard_config, environment
    )
    local_times["runtime_prepare"] = (stage_started, core._utc_now())
    candidate = _base_candidate(
        args,
        git_head=git_head,
        git_status_digest=git_status_digest,
        source_sha=source_sha,
        dist_digest=dist_digest,
        uipath_config_digest=uipath_config_digest,
        package_content_digest=package_content_digest,
        package_file_digest=package_file_digest,
        recovery_plan_hash=None,
        deployment_id=expected_deployment_id,
        system_name=expected_system_name,
        deploy_version=expected_deploy_version,
        current_version=expected_current_version,
        runtime_manifest_hash=runtime["manifest_hash"],
        node_executable=node_runtime["executable"],
        node_executable_sha256=node_runtime["executable_sha256"],
        node_version=node_runtime["version"],
        runtime_app_config_digest=runtime["runtime_app_config_sha256"],
        runtime_immutable_digest=runtime["runtime_immutable_sha256"],
        main_file=main_file,
        content_type=args.content_type or "webapp",
    )
    _assert_common_candidate(candidate)
    claim_path, claim = _create_claim(target, candidate, environment)
    stage_contract = (
        DIST_UPGRADE_STAGE_CONTRACT if args.intent == "upgrade" else DIST_STAGE_CONTRACT
    )
    stages = _stages(stage_contract, local_times)
    receipt = _new_receipt(
        args, target, candidate, claim_path, claim, reservation, stages
    )
    try:
        _write_receipt(receipt_path, receipt)
    except (Exception, SystemExit, KeyboardInterrupt):
        _release_unstarted_claim(claim_path, claim)
        raise
    barrier_inputs = {
        "target": target,
        "node_runtime": node_runtime,
        "workspace": workspace,
        "copied_dist": copied_dist,
        "config_copy": config_copy,
        "package_path": package_path,
        "runtime": runtime,
        "candidate": candidate,
        "environment": environment,
    }
    _start_stage(receipt, receipt_path, "pre_guard_barrier")
    try:
        _revalidate_dist_barrier(**barrier_inputs)
    except (Exception, SystemExit, KeyboardInterrupt):
        _fail_stage(
            receipt, receipt_path, "pre_guard_barrier",
            status="failed_prewrite",
            error_code="PRE_GUARD_BARRIER_FAILED",
            recovery_text="safe_prewrite_failure; rebuild exact evidence and submit a fresh testing request",
        )
        _release_claim(claim_path, claim, receipt, receipt_path)
        raise
    _finish_stage(receipt, receipt_path, "pre_guard_barrier")
    guard_stage = (
        "upgrade_pre_guard" if candidate["intent"] == "upgrade" else "create_absence_guard"
    )
    _start_stage(receipt, receipt_path, guard_stage)
    try:
        guard_command = (
            _upgrade_guard_command(runtime, target, candidate, "upgrade-pre")
            if candidate["intent"] == "upgrade"
            else _create_guard_command(runtime, target, candidate)
        )
        output = _run_read(
            guard_command,
            Path(runtime["runtime_workspace"]),
            environment,
            "UPGRADE_PRE_GUARD_FAILED" if candidate["intent"] == "upgrade" else "CREATE_ABSENCE_GUARD_FAILED",
        )
        receipt["observations"]["prewrite"] = (
            _validate_upgrade_guard_output(output, target, candidate, "upgrade-pre")
            if candidate["intent"] == "upgrade"
            else _validate_create_guard_output(output, target, candidate)
        )
    except (Exception, SystemExit, KeyboardInterrupt) as exc:
        _fail_stage(
            receipt, receipt_path, guard_stage,
            status="failed_prewrite",
            error_code="UPGRADE_PRE_GUARD_FAILED" if candidate["intent"] == "upgrade" else "CREATE_ABSENCE_GUARD_FAILED",
            recovery_text="safe_prewrite_failure; correct target state and submit a fresh testing request",
        )
        _release_claim(claim_path, claim, receipt, receipt_path)
        raise
    _finish_stage(receipt, receipt_path, guard_stage)
    _start_stage(receipt, receipt_path, "pre_publish_barrier")
    try:
        _revalidate_dist_barrier(**barrier_inputs)
    except (Exception, SystemExit, KeyboardInterrupt):
        _fail_stage(
            receipt, receipt_path, "pre_publish_barrier",
            status="failed_prewrite",
            error_code="PRE_PUBLISH_BARRIER_FAILED",
            recovery_text="safe_prewrite_failure; rebuild exact evidence and submit a fresh testing request",
        )
        _release_claim(claim_path, claim, receipt, receipt_path)
        raise
    _finish_stage(receipt, receipt_path, "pre_publish_barrier")
    publish_cli = runtime["runtime_cli"] if candidate["intent"] == "upgrade" else str(cli)
    publish_cwd = workspace
    publish_package_dir = package_dir
    publish_command = [
        node_runtime["executable"], publish_cli, "codedapp", "publish",
        "--name", candidate["package_name"],
        "--version", candidate["version"],
        "--type", "Web",
        "--uipath-dir", str(publish_package_dir),
        "--base-url", target["control_plane_url"],
        "--org-id", target["organization_id"],
        "--tenant-id", target["tenant_id"],
        "--tenant-name", target["tenant_name"],
        "--profile", target["cli_profile"],
        "--output", "json",
    ]
    _start_stage(receipt, receipt_path, "publish", external_write=True)
    try:
        _revalidate_dist_barrier(**barrier_inputs)
        publish_result = _run_write(
            publish_command, publish_cwd, environment, "PUBLISH_INDETERMINATE"
        )
        published = (
            _validate_published_candidate(publish_result, candidate)
            if candidate["intent"] == "upgrade"
            else None
        )
        # The publish acknowledgement is not authoritative candidate evidence:
        # DeployVersion can be absent while registration becomes visible. Keep
        # the receipt observation empty until the read-only candidate guard
        # resolves and proves the exact system/deploy identity.
    except (Exception, SystemExit, KeyboardInterrupt):
        _fail_stage(
            receipt, receipt_path, "publish",
            status="publish_indeterminate",
            error_code="PUBLISH_INDETERMINATE",
            recovery_text="reconcile remote package state; blind retry and republish prohibited",
        )
        raise
    _finish_stage(
        receipt,
        receipt_path,
        "publish",
        receipt_status="published_not_deployed",
    )
    _start_stage(receipt, receipt_path, "app_config_bind")
    try:
        expected_binding = core._expected_app_config_binding(
            package_name=candidate["package_name"],
            app_name=candidate["app_name"],
            app_version=candidate["version"],
            app_type="Web",
        )
        if expected_binding is not None:
            core._bind_app_config(
                workspace,
                {"new_version": candidate["version"]},
                {
                    "package_name": candidate["package_name"],
                    "app_name": candidate["app_name"],
                    "app_type": "Web",
                    "app_config_binding_hash": core._hash_json(expected_binding),
                },
            )
    except (Exception, SystemExit, KeyboardInterrupt):
        _fail_stage(
            receipt, receipt_path, "app_config_bind",
            status="published_not_deployed",
            error_code="APP_CONFIG_BIND_FAILED",
            recovery_text="package published but deployment not started; reconcile before a fresh request",
        )
        raise
    _finish_stage(receipt, receipt_path, "app_config_bind")
    if candidate["intent"] == "upgrade":
        _start_stage(receipt, receipt_path, "published_candidate_guard")
        try:
            _revalidate_dist_barrier(**barrier_inputs)
            candidate_output = _run_read(
                _upgrade_guard_command(
                    runtime, target, candidate, "upgrade-candidate", published=published
                ),
                Path(runtime["runtime_workspace"]),
                environment,
                "PUBLISHED_CANDIDATE_GUARD_FAILED",
            )
            receipt["observations"]["published_candidate"] = (
                _validate_upgrade_guard_output(
                    candidate_output,
                    target,
                    candidate,
                    "upgrade-candidate",
                    published=published,
                )
            )
        except (Exception, SystemExit, KeyboardInterrupt):
            _fail_stage(
                receipt,
                receipt_path,
                "published_candidate_guard",
                status="published_not_deployed",
                error_code="PUBLISHED_CANDIDATE_GUARD_FAILED",
                recovery_text="package was published; reconcile exact candidate identity before a fresh request",
            )
            raise
        _finish_stage(receipt, receipt_path, "published_candidate_guard")
    _start_stage(receipt, receipt_path, "pre_deploy_barrier")
    try:
        _revalidate_dist_barrier(**barrier_inputs)
    except (Exception, SystemExit, KeyboardInterrupt):
        _fail_stage(
            receipt, receipt_path, "pre_deploy_barrier",
            status="published_not_deployed",
            error_code="PRE_DEPLOY_BARRIER_FAILED",
            recovery_text="package was published; reconcile it before a fresh testing request",
        )
        raise
    _finish_stage(receipt, receipt_path, "pre_deploy_barrier")
    deploy_command = (
        _upgrade_guard_command(
            runtime, target, candidate, "upgrade-execute", published=published
        )
        if candidate["intent"] == "upgrade"
        else _create_execute_command(runtime, target, candidate)
    )
    _start_stage(receipt, receipt_path, "deploy", external_write=True)
    try:
        _revalidate_dist_barrier(**barrier_inputs)
        deploy_result = _run_write(
            deploy_command,
            Path(runtime["runtime_workspace"]),
            environment,
            "DEPLOY_INDETERMINATE",
        )
        deployed = (
            _validate_upgrade_guard_output(
                deploy_result,
                target,
                candidate,
                "upgrade-execute",
                published=published,
            )
            if candidate["intent"] == "upgrade"
            else _validate_create_execute_output(deploy_result, target, candidate)
        )
    except (Exception, SystemExit, KeyboardInterrupt):
        _fail_stage(
            receipt, receipt_path, "deploy",
            status="deploy_indeterminate",
            error_code="DEPLOY_INDETERMINATE",
            recovery_text="reconcile exact deployment and route; blind retry and fresh-app fallback prohibited",
        )
        raise
    if candidate["intent"] == "create":
        receipt["observations"]["postwrite"] = deployed
    _finish_stage(
        receipt,
        receipt_path,
        "deploy",
        receipt_status="deployed_unverified",
    )
    post_guard_stage = (
        "upgrade_post_guard" if candidate["intent"] == "upgrade" else "post_create_guard"
    )
    post_guard_error = (
        "UPGRADE_POST_GUARD_FAILED"
        if candidate["intent"] == "upgrade"
        else "CREATE_POST_GUARD_FAILED"
    )
    _start_stage(receipt, receipt_path, post_guard_stage)
    try:
        if core._hash_file(Path(__file__), "testing helper") != candidate["helper_sha256"]:
            core._fail("Testing helper changed before the guarded post-state read.")
        _revalidate_create_runtime_immutable(runtime, candidate)
        post_command = (
            _upgrade_guard_command(
                runtime, target, candidate, "upgrade-post", published=published
            )
            if candidate["intent"] == "upgrade"
            else _create_post_command(runtime, target, candidate, deployed)
        )
        post_output = _run_read(
            post_command,
            Path(runtime["runtime_workspace"]),
            environment,
            post_guard_error,
        )
        receipt["observations"]["postwrite"] = (
            _validate_upgrade_guard_output(
                post_output,
                target,
                candidate,
                "upgrade-post",
                published=published,
            )
            if candidate["intent"] == "upgrade"
            else _validate_create_post_output(post_output, target, candidate, deployed)
        )
    except (Exception, SystemExit, KeyboardInterrupt):
        _fail_stage(
            receipt, receipt_path, post_guard_stage,
            status="deployed_unverified",
            error_code=post_guard_error,
            recovery_text="deployment may have succeeded; reconcile exact post-state before any new request",
        )
        raise
    _finish_stage(receipt, receipt_path, post_guard_stage)
    _start_stage(receipt, receipt_path, "route_verify")
    try:
        core._verify_url(_route_url(target, candidate["path_name"]), args.verify_timeout)
        receipt["verification"]["route_verified"] = True
    except (Exception, SystemExit, KeyboardInterrupt):
        _fail_stage(
            receipt, receipt_path, "route_verify",
            status="deployed_unverified",
            error_code="ROUTE_VERIFY_FAILED",
            recovery_text="deployment may exist; inspect exact route and assets before any new request",
        )
        raise
    _finish_stage(receipt, receipt_path, "route_verify")
    _start_stage(receipt, receipt_path, "config_verify")
    try:
        config_path = Path(runtime["runtime_workspace"]) / core.APP_CONFIG_RELATIVE_PATH
        document = json.loads(config_path.read_text(encoding="utf-8"))
        if document.get("appVersion") != candidate["version"]:
            core._fail("Post-deploy app config version mismatch.")
        if document.get("appUrl") != _route_url(target, candidate["path_name"]):
            core._fail("Post-deploy app config route mismatch.")
        deployment_id = document.get("deploymentId")
        if candidate["intent"] == "create":
            if core.GUID_RE.fullmatch(str(deployment_id)) is None:
                core._fail("Post-deploy app config has no exact deployment ID.")
            if deployment_id.lower() != deployed["deploymentId"]:
                core._fail("Post-deploy app config deployment ID mismatch.")
        elif deployment_id is not None:
            core._fail("Guarded upgrade runtime may not fabricate deployment metadata.")
        if document.get("appName") != candidate["package_name"]:
            core._fail("Post-deploy app config package mismatch.")
        if document.get("displayName") != candidate["app_name"]:
            core._fail("Post-deploy app config display name mismatch.")
        if document.get("appType") != "Web" or document.get("personalWorkspace") is not False:
            core._fail("Post-deploy app config type or workspace mismatch.")
        receipt["verification"]["post_deploy_app_config_digest"] = core._hash_file(
            config_path, "post-deploy app config"
        )
        receipt["verification"]["configuration_verified"] = True
    except (Exception, SystemExit, KeyboardInterrupt):
        _fail_stage(
            receipt, receipt_path, "config_verify",
            status="deployed_unverified",
            error_code="CONFIG_VERIFY_FAILED",
            recovery_text="deployment may exist; reconcile exact app configuration before any new request",
        )
        raise
    _finish_stage(receipt, receipt_path, "config_verify")
    receipt["status"] = "succeeded_testing"
    _write_receipt(receipt_path, receipt)
    return receipt_path


def _load_publish_recovery_receipt(
    path: Path,
    *,
    expected_receipt_hash: str,
    expected_file_sha256: str,
) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        core._fail("Publish recovery requires a regular failed testing receipt.")
    if core._hash_file(path, "failed testing receipt") != expected_file_sha256:
        core._fail("Failed testing receipt file hash does not match explicit authority.")
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        core._fail("Failed testing receipt is not valid UTF-8 JSON.")
    legacy_fields = {
        "kind", "schema_version", "helper_sha256", "attempt_phase",
        "preflight_error_code", "authorization", "target", "candidate", "policy",
        "execution_claim", "receipt_reservation", "status", "external_write_started",
        "started_at", "updated_at", "redaction", "stages", "observations",
        "verification", "receipt_hash",
    }
    current_fields = {*legacy_fields, "recovery_source"}
    if not isinstance(receipt, dict):
        core._fail("Failed testing receipt is not an exact supported source shape.")
    source_schema_version = receipt.get("schema_version")
    expected_fields = {
        "1.1": legacy_fields,
        "1.2": current_fields,
    }.get(source_schema_version)
    if expected_fields is None or set(receipt) != expected_fields:
        core._fail("Failed testing receipt is not an exact supported source shape.")
    if source_schema_version == "1.2" and receipt["recovery_source"] is not None:
        core._fail("Failed testing source receipt already contains recovery evidence.")
    if (
        receipt.get("kind") != RECEIPT_KIND
        or source_schema_version not in PUBLISH_RECOVERY_SOURCE_SCHEMA_VERSIONS
        or receipt.get("receipt_hash") != expected_receipt_hash
        or core._document_hash(receipt, "receipt_hash") != expected_receipt_hash
        or receipt.get("status") != "publish_indeterminate"
        or receipt.get("attempt_phase") != "claimed"
        or receipt.get("external_write_started") is not True
    ):
        core._fail("Failed testing receipt is not an exact publish-indeterminate source.")
    _assert_receipt_redacted(receipt)
    candidate = receipt.get("candidate")
    _validate_candidate_record(candidate)
    if (
        candidate["mode"] != "dist"
        or candidate["intent"] != "upgrade"
        or candidate["helper_sha256"] != receipt.get("helper_sha256")
        or receipt.get("policy")
        != {
            "policy_version": source_schema_version,
            "data_classification": "synthetic_only",
            "internal_authenticated_required": True,
            "production_eligible": False,
            "release_evidence": False,
            "waived_gates": WAIVED_GATES,
            "nonwaivable_controls": NONWAIVABLE_CONTROLS,
        }
    ):
        core._fail("Failed testing receipt candidate or policy is not recoverable.")
    target = receipt.get("target")
    if not isinstance(target, dict) or target.get("cli_executable_sha256") != EXPECTED_CLI_SHA256:
        core._fail("Failed testing receipt target is not supported.")
    claim = receipt.get("execution_claim")
    _validate_claim_record(claim)
    if claim["released"] or claim["key"] != _claim_key(target, candidate):
        core._fail("Failed testing receipt does not retain its exact candidate claim.")
    claim_path = Path(claim["path"])
    expected_claim_name = f"{claim['key'].removeprefix('sha256:')}.json"
    if (
        claim_path.name != expected_claim_name
        or claim_path.parent.name != "uipcodedappdeploy-recovery-claims"
    ):
        core._fail("Failed testing receipt retained claim path is not key-derived.")
    if claim_path.is_symlink() or not claim_path.is_file() or core._hash_file(
        claim_path, "failed testing retained claim"
    ) != claim["file_sha256"]:
        core._fail("Failed testing receipt retained claim is missing or changed.")
    try:
        claim_document = json.loads(claim_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        core._fail("Failed testing receipt retained claim is unreadable.")
    if (
        claim_document.get("claim_hash") != claim["claim_hash"]
        or core._document_hash(claim_document, "claim_hash") != claim["claim_hash"]
        or claim_document.get("key") != claim["key"]
        or claim_document.get("target_fingerprint") != core._hash_json(target)
        or claim_document.get("candidate_fingerprint") != core._hash_json(candidate)
    ):
        core._fail("Failed testing receipt retained claim binding is invalid.")
    reservation = receipt.get("receipt_reservation")
    if not isinstance(reservation, dict) or set(reservation) != {
        "path", "file_sha256", "reservation_hash",
    }:
        core._fail("Failed testing receipt reservation is invalid.")
    reservation_path = Path(reservation["path"])
    if reservation_path.is_symlink() or not reservation_path.is_file() or core._hash_file(
        reservation_path, "failed testing receipt reservation"
    ) != reservation["file_sha256"]:
        core._fail("Failed testing receipt reservation is missing or changed.")
    try:
        reservation_document = json.loads(
            reservation_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        core._fail("Failed testing receipt reservation is unreadable.")
    reservation_name = reservation_path.name
    if not reservation_name.startswith(".") or not reservation_name.endswith(
        ".reservation.json"
    ):
        core._fail("Failed testing receipt reservation name is invalid.")
    reserved_receipt_path = reservation_path.with_name(
        reservation_name[1 : -len(".reservation.json")]
    )
    if reserved_receipt_path.resolve(strict=True) != path.resolve(strict=True):
        core._fail("Failed testing receipt reservation path does not identify the source receipt.")
    if (
        not isinstance(reservation_document, dict)
        or reservation_document.get("kind")
        != "uipcodedappdeploy.testing-receipt-reservation"
        or reservation_document.get("schema_version") != "1.0"
        or reservation_document.get("reservation_hash")
        != reservation["reservation_hash"]
        or core._document_hash(reservation_document, "reservation_hash")
        != reservation["reservation_hash"]
        or reservation_document.get("receipt_path_sha256")
        != core._hash_json({"receipt_path": str(reserved_receipt_path)})
    ):
        core._fail("Failed testing receipt reservation binding is invalid.")
    authorization = receipt.get("authorization")
    verification = receipt.get("verification")
    if (
        not isinstance(authorization, dict)
        or authorization.get("mode") != "explicit_testing_request"
        or authorization.get("testing_only") is not True
        or authorization.get("execute") is not True
        or not isinstance(authorization.get("purpose"), str)
        or not authorization["purpose"]
        or receipt.get("redaction") != REDACTION
        or not isinstance(verification, dict)
        or verification.get("route_url")
        != _route_url(target, candidate["path_name"])
        or verification.get("route_verified") is not None
        or verification.get("configuration_verified") is not None
        or verification.get("pre_deploy_app_config_digest")
        != candidate["runtime_app_config_digest"]
        or verification.get("post_deploy_app_config_digest") is not None
        or verification.get("authentication_certification")
        != "pending_external_acceptance"
    ):
        core._fail("Failed testing receipt authorization or verification is invalid.")
    stages = receipt.get("stages")
    if (
        not isinstance(stages, list)
        or [(stage.get("name"), stage.get("effect")) for stage in stages]
        != DIST_UPGRADE_STAGE_CONTRACT
        or any(stage.get("status") != "succeeded" for stage in stages[:8])
        or not (
            (
                stages[8].get("status") == "failed"
                and stages[8].get("error_code") == "PUBLISH_INDETERMINATE"
            )
            or stages[8].get("status") == "running"
        )
        or any(stage.get("status") != "pending" for stage in stages[9:])
    ):
        core._fail("Failed testing receipt stage history is not recoverable.")
    for stage in stages:
        _validate_stage(stage)
    observations = receipt.get("observations")
    if (
        not isinstance(observations, dict)
        or observations.get("published_candidate") is not None
        or observations.get("postwrite") is not None
    ):
        core._fail("Failed testing receipt contains unsupported later observations.")
    _validate_observation(observations.get("prewrite"), "prewrite")
    _validate_observation_binding(observations.get("prewrite"), "prewrite", target, candidate)
    return receipt


def _publish_recovery_paths(
    receipt_path: Path,
    candidate: dict[str, Any],
) -> dict[str, Path]:
    workspace = _workspace_for(receipt_path)
    paths = {
        "workspace": workspace,
        "dist": workspace / "dist",
        "config": workspace / "uipath.json",
        "package": workspace / ".uipath" / f"{candidate['package_name']}.{candidate['version']}.nupkg",
        "runtime_manifest": workspace / "create-guard-runtime.manifest.json",
    }
    if workspace.is_symlink() or not workspace.is_dir():
        core._fail("Publish recovery workspace is missing.")
    return paths


def _load_publish_recovery_runtime(
    manifest_path: Path,
    source_receipt: dict[str, Any],
) -> dict[str, Any]:
    if manifest_path.is_symlink() or not manifest_path.is_file():
        core._fail("Publish recovery runtime manifest is missing.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        core._fail("Publish recovery runtime manifest is unreadable.")
    candidate = source_receipt["candidate"]
    if (
        not isinstance(manifest, dict)
        or manifest.get("manifest_hash") != candidate["runtime_manifest_hash"]
        or core._document_hash(manifest, "manifest_hash") != candidate["runtime_manifest_hash"]
        or manifest.get("helper_sha256") != source_receipt["helper_sha256"]
        or manifest.get("node_executable") != candidate["node_executable"]
        or manifest.get("node_executable_sha256") != candidate["node_executable_sha256"]
        or manifest.get("node_version") != candidate["node_version"]
        or manifest.get("runtime_immutable_sha256") != candidate["runtime_immutable_digest"]
    ):
        core._fail("Publish recovery runtime manifest is not source-receipt-bound.")
    return {
        **manifest,
        "manifest_path": str(manifest_path),
        "runtime_root": manifest["runtime_root"],
    }


def _publish_recovery_runtime_workspace(
    paths: dict[str, Path],
    runtime: dict[str, Any],
) -> Path:
    expected_root = paths["workspace"] / "create-guard-runtime"
    expected_workspace = expected_root / "workspace"
    runtime_root = Path(runtime["runtime_root"])
    runtime_workspace = Path(runtime["runtime_workspace"])
    if (
        runtime_root.resolve(strict=True) != expected_root.resolve(strict=True)
        or runtime_workspace.resolve(strict=True) != expected_workspace.resolve(strict=True)
    ):
        core._fail("Publish recovery runtime is not deterministically located.")
    for path, label in (
        (runtime_root, "runtime root"),
        (runtime_workspace, "runtime workspace"),
    ):
        if path.is_symlink() or not path.is_dir():
            core._fail(f"Publish recovery {label} must be a real directory.")
    return runtime_workspace


def _publish_recovery_bound_config(
    config_path: Path,
    candidate: dict[str, Any],
    target: dict[str, Any],
) -> tuple[str, dict[str, Any], str]:
    if config_path.is_symlink() or not config_path.is_file():
        core._fail("Publish recovery app config is missing.")
    try:
        document = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        core._fail("Publish recovery app config is unreadable.")
    expected_fields = {
        "appName", "displayName", "appVersion", "appUrl", "appType",
        "personalWorkspace",
    }
    before = core._hash_file(config_path, "publish recovery pre-deploy app config")
    if (
        not isinstance(document, dict)
        or set(document) != expected_fields
        or before != candidate["runtime_app_config_digest"]
        or document.get("appName") != candidate["package_name"]
        or document.get("displayName") != candidate["app_name"]
        or document.get("appVersion") != candidate["version"]
        or document.get("appUrl") != _route_url(target, candidate["path_name"])
        or document.get("appType") != "Web"
        or document.get("personalWorkspace") is not False
    ):
        core._fail("Publish recovery app config is not the exact retained guard state.")
    return before, copy.deepcopy(document), before


def _create_publish_recovery_transition_claim(
    source_path: Path,
    source_receipt: dict[str, Any],
    candidate: dict[str, Any],
    reservation: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    predecessor = source_receipt["execution_claim"]
    predecessor_path = Path(predecessor["path"])
    expected_predecessor_name = f"{predecessor['key'].removeprefix('sha256:')}.json"
    if predecessor_path.name != expected_predecessor_name:
        core._fail("Publish recovery predecessor claim path is not key-derived.")
    path = predecessor_path.with_name(
        f"{predecessor['key'].removeprefix('sha256:')}.publish-recovery.json"
    )
    claim = {
        "kind": "uipcodedappdeploy.testing-publish-recovery-transition-claim",
        "schema_version": "1.0",
        "created_at": core._utc_now(),
        "key": predecessor["key"],
        "predecessor_claim_hash": predecessor["claim_hash"],
        "predecessor_claim_file_sha256": predecessor["file_sha256"],
        "failed_receipt_hash": source_receipt["receipt_hash"],
        "failed_receipt_file_sha256": core._hash_file(
            source_path, "failed testing receipt"
        ),
        "receipt_reservation_hash": reservation["reservation_hash"],
        "target_fingerprint": core._hash_json(source_receipt["target"]),
        "candidate_fingerprint": core._hash_json(candidate),
    }
    claim["claim_hash"] = core._document_hash(claim, "claim_hash")
    payload = json.dumps(claim, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        core._fail(
            "A publish recovery transition already exists for this exact candidate; do not retry."
        )
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    directory_descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)
    return path, claim


def _publish_recovery_source_record(
    source_path: Path,
    source_receipt: dict[str, Any],
    paths: dict[str, Path],
    pre_config_digest: str,
) -> dict[str, Any]:
    return {
        "failed_receipt_path": str(source_path),
        "failed_receipt_file_sha256": core._hash_file(source_path, "failed testing receipt"),
        "failed_receipt_hash": source_receipt["receipt_hash"],
        "failed_candidate_hash": core._hash_json(source_receipt["candidate"]),
        "failed_helper_sha256": source_receipt["helper_sha256"],
        "retained_execution_claim": copy.deepcopy(source_receipt["execution_claim"]),
        "workspace_path": str(paths["workspace"]),
        "package_path": str(paths["package"]),
        "runtime_manifest_path": str(paths["runtime_manifest"]),
        "runtime_manifest_file_sha256": core._hash_file(
            paths["runtime_manifest"], "publish recovery runtime manifest"
        ),
        "pre_recovery_app_config_digest": pre_config_digest,
    }


def _match_publish_recovery_inputs(
    args: argparse.Namespace,
    target: dict[str, Any],
    source_receipt: dict[str, Any],
) -> None:
    if source_receipt["target"] != target:
        core._fail("Publish recovery target differs from the failed testing receipt.")
    candidate = source_receipt["candidate"]
    comparisons = {
        "package_name": args.package_name,
        "app_name": args.app_name,
        "path_name": args.path_name,
        "version": args.version,
        "deployment_id": args.expected_deployment_id,
        "system_name": args.expected_system_name,
        "current_version": args.expected_current_version,
        "deploy_version": args.expected_deploy_version,
    }
    for field, observed in comparisons.items():
        if observed != candidate[field]:
            core._fail(f"Publish recovery {field} does not match the failed receipt.")
    if core._normalize_tags(args.tags, "--tags") != candidate["tags"]:
        core._fail("Publish recovery tags do not match the failed receipt.")
    expected_hashes = {
        "helper_sha256": args.expected_source_helper_sha256,
        "package_file_digest": args.expected_package_file_sha256,
        "runtime_manifest_hash": args.expected_runtime_manifest_hash,
    }
    for field, observed in expected_hashes.items():
        if _require_hash(observed, f"--expected-{field.replace('_', '-')}") != candidate[field]:
            core._fail(f"Publish recovery {field} does not match the failed receipt.")


def _revalidate_publish_recovery_barrier(
    source_record: dict[str, Any],
    target: dict[str, Any],
    candidate: dict[str, Any],
    runtime: dict[str, Any],
    transition_path: Path,
    transition_claim: dict[str, Any],
    *,
    require_bound_config: bool,
) -> None:
    if core._hash_file(Path(__file__), "testing helper") != candidate["helper_sha256"]:
        core._fail("Testing helper changed after publish recovery claim transition.")
    _validate_publish_recovery_source_record(source_record, target, candidate)
    if transition_path.is_symlink() or not transition_path.is_file() or core._hash_file(
        transition_path, "publish recovery transition claim"
    ) != core._hash_bytes(
        json.dumps(transition_claim, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    ):
        core._fail("Publish recovery transition claim changed.")
    workspace = Path(source_record["workspace_path"])
    if _directory_digest(workspace / "dist") != candidate["dist_digest"]:
        core._fail("Publish recovery dist changed.")
    config_copy = workspace / "uipath.json"
    if core._hash_file(config_copy, "publish recovery uipath.json") != candidate[
        "uipath_config_digest"
    ]:
        core._fail("Publish recovery uipath.json changed.")
    content_digest, file_digest = core._package_evidence(
        Path(source_record["package_path"]),
        package_name=candidate["package_name"],
        main_file=candidate["main_file"],
    )
    if (
        content_digest != candidate["package_content_digest"]
        or file_digest != candidate["package_file_digest"]
    ):
        core._fail("Publish recovery package changed.")
    _audit_package_archive(Path(source_record["package_path"]))
    _revalidate_create_runtime_immutable(runtime, candidate)
    if require_bound_config:
        config_path = Path(runtime["runtime_workspace"]) / core.APP_CONFIG_RELATIVE_PATH
        if core._hash_file(config_path, "publish recovery bound app config") != candidate[
            "runtime_app_config_digest"
        ]:
            core._fail("Publish recovery bound app config changed.")


def _match_recovery_inputs(
    args: argparse.Namespace,
    plan: dict[str, Any],
    target: dict[str, Any],
    cli: Path,
) -> None:
    expected_plan_hash = _require_hash(
        args.expected_recovery_plan_hash, "--expected-recovery-plan-hash"
    )
    if expected_plan_hash != plan["plan_hash"]:
        core._fail("--expected-recovery-plan-hash does not match the loaded recovery plan.")
    expected_deployment_id = _require_guid(
        args.expected_deployment_id, "--expected-deployment-id"
    )
    if expected_deployment_id != plan["existing_deployment"]["deployment_id"].lower():
        core._fail("--expected-deployment-id does not match the recovery plan.")
    expected_system_name = _require_text(args.expected_system_name, "--expected-system-name")
    if core.APP_SYSTEM_NAME_RE.fullmatch(expected_system_name) is None:
        core._fail("--expected-system-name is invalid.")
    if expected_system_name != plan["candidate"]["system_name"]:
        core._fail("--expected-system-name does not match the recovery plan.")
    expected_current_version = _require_text(
        args.expected_current_version, "--expected-current-version"
    )
    core._parse_semver(expected_current_version, "--expected-current-version")
    if expected_current_version != plan["existing_deployment"]["deployed_version"]:
        core._fail("--expected-current-version does not match the recovery plan.")
    if not isinstance(args.expected_deploy_version, int) or args.expected_deploy_version < 1:
        core._fail("--expected-deploy-version must be a positive integer.")
    if args.expected_deploy_version != plan["candidate"]["deploy_version"]:
        core._fail("--expected-deploy-version does not match the recovery plan.")
    expected_runtime_hash = _require_hash(
        args.expected_runtime_manifest_hash, "--expected-runtime-manifest-hash"
    )
    if expected_runtime_hash != plan["candidate"]["recovery_runtime_manifest_hash"]:
        core._fail("--expected-runtime-manifest-hash does not match the recovery plan.")
    derived_cross_lane_key = core._hash_json(
        {
            "scope": "home_scoped_exact_candidate_v1",
            "environment": target["environment"],
            "organization_id": target["organization_id"],
            "tenant_id": target["tenant_id"],
            "folder_key": target["folder_key"],
            "deployment_id": expected_deployment_id,
            "system_name": expected_system_name,
            "deploy_version": args.expected_deploy_version,
            "candidate_version": plan["candidate"]["version"],
        }
    )
    if derived_cross_lane_key != plan["upgrade_guard"]["local_execution_claim_key"]:
        core._fail("Recovery plan cross-lane execution claim binding is invalid.")
    expected_target = plan["target"]
    comparisons = {
        "environment": target["environment"],
        "control_plane_url": target["control_plane_url"],
        "organization_name": target["organization_name"],
        "organization_id": target["organization_id"],
        "tenant_name": target["tenant_name"],
        "tenant_id": target["tenant_id"],
        "folder_key": target["folder_key"],
        "client_id": target["client_id"],
    }
    if expected_target != comparisons:
        core._fail("Testing target does not match the reconciled recovery target.")
    expected = plan["existing_deployment"]
    candidate = plan["candidate"]
    if args.package_name != expected["package_name"]:
        core._fail("--package-name does not match the reconciled deployment.")
    if args.app_name != expected["app_name"]:
        core._fail("--app-name does not match the reconciled deployment.")
    if args.path_name != expected["route_name"]:
        core._fail("--path-name does not match the reconciled deployment route.")
    if args.version != candidate["version"]:
        core._fail("--version does not match the reconciled candidate.")
    if core._normalize_tags(args.tags, "--tags") != candidate["tags"]:
        core._fail("--tags do not match the reconciled candidate.")
    if str(cli) != candidate["source_cli_executable"]:
        core._fail("--cli-executable does not match the reconciled source CLI.")
    if target["cli_executable_sha256"] != candidate["source_cli_executable_sha256"]:
        core._fail("Testing CLI digest does not match the reconciled source CLI.")
    if target["cli_version"] != candidate["cli_version"]:
        core._fail("Testing CLI version does not match the reconciled candidate.")
    if target["cli_profile"] != candidate["cli_profile"]:
        core._fail("Testing CLI profile does not match the reconciled candidate.")
    if target["cli_profile_hash"] != candidate["cli_profile_hash"]:
        core._fail("Testing CLI profile binding does not match the reconciled candidate.")
    if args.project_root and str(Path(args.project_root).expanduser().resolve()) != plan["project_root"]:
        core._fail("--project-root does not match the reconciled source root.")


def _assert_no_prior_recovery_execution(
    recovery_plan_path: Path,
    plan: dict[str, Any],
    environment: dict[str, str],
) -> None:
    prior_receipt = recovery._receipt_path(recovery_plan_path)
    if prior_receipt.exists():
        core._fail(
            "The reconciled recovery plan already has a receipt. Remote reconciliation and "
            "a fresh explicit testing request are required."
        )
    claim_key = plan["upgrade_guard"]["local_execution_claim_key"]
    core._validate_hash(claim_key, "Recovery execution claim key")
    recovery_claim = (
        Path(environment["HOME"])
        / ".uipath"
        / "uipcodedappdeploy-recovery-claims"
        / f"{claim_key.removeprefix('sha256:')}.json"
    )
    if recovery_claim.exists():
        core._fail(
            "The reconciled candidate has a retained recovery claim. Blind cross-lane retry is prohibited."
        )


def _revalidate_reconciled_testing_barrier(
    plan: dict[str, Any],
    context: dict[str, Any],
    candidate: dict[str, Any],
    environment: dict[str, str],
) -> None:
    if core._hash_file(Path(__file__), "testing helper") != candidate["helper_sha256"]:
        core._fail("Testing helper bytes changed after the reconciled candidate claim.")
    if core._hash_file(
        Path(plan["project_root"]) / "uipath.json", "reconciled uipath.json"
    ) != candidate["uipath_config_digest"]:
        core._fail("Reconciled uipath.json changed after the candidate claim.")
    if core._hash_file(
        Path(plan["candidate"]["source_cli_executable"]), "reconciled source CLI"
    ) != EXPECTED_CLI_SHA256:
        core._fail("Reconciled source CLI is not the supported 1.198.0 build.")
    recovery._revalidate_runtime_barrier(plan, context, environment)
    _revalidate_reconciled_immutable_runtime(plan, candidate)


def _revalidate_reconciled_immutable_runtime(
    plan: dict[str, Any], candidate: dict[str, Any]
) -> None:
    if core._hash_file(Path(__file__), "testing helper") != candidate["helper_sha256"]:
        core._fail("Testing helper bytes changed after the reconciled candidate claim.")
    exact_files = (
        (
            Path(plan["candidate"]["source_cli_executable"]),
            EXPECTED_CLI_SHA256,
            "reconciled source CLI",
        ),
        (
            Path(plan["candidate"]["recovery_cli_executable"]),
            EXPECTED_CLI_SHA256,
            "reconciled guarded CLI",
        ),
        (
            Path(plan["candidate"]["codedapp_tool_recovery_file"]),
            plan["candidate"]["codedapp_tool_recovery_file_sha256"],
            "reconciled guarded coded app tool",
        ),
        (
            Path(plan["candidate"]["codedapp_tool_recovery_manifest"]),
            plan["candidate"]["codedapp_tool_recovery_manifest_sha256"],
            "reconciled guarded tool manifest",
        ),
        (
            Path(plan["candidate"]["recovery_node_executable"]),
            candidate["node_executable_sha256"],
            "reconciled Node.js runtime",
        ),
    )
    for path, expected_digest, label in exact_files:
        if path.is_symlink() or not path.is_file():
            core._fail(f"Testing {label} is not a regular file.")
        if core._hash_file(path, label) != expected_digest:
            core._fail(f"Testing {label} changed after the candidate claim.")
    runtime_root = Path(plan["candidate"]["recovery_runtime_root"])
    app_config = (
        Path(plan["candidate"]["recovery_workspace"])
        / core.APP_CONFIG_RELATIVE_PATH
    )
    if _immutable_runtime_digest(runtime_root, [app_config]) != candidate[
        "runtime_immutable_digest"
    ]:
        core._fail("Reconciled immutable runtime changed after the candidate claim.")


def _reconciled_runtime_manifest_path(
    supplied_value: str | None,
    context: dict[str, Any],
) -> Path:
    paths = context.get("paths")
    bound = paths.get("recovery_runtime_manifest") if isinstance(paths, dict) else None
    if not isinstance(bound, Path) or not bound.is_absolute():
        core._fail("Recovery evidence lacks an exact runtime-manifest path binding.")
    if bound.is_symlink() or not bound.is_file():
        core._fail("Recovery runtime-manifest evidence must be a regular non-symlink file.")
    canonical_bound = bound.resolve(strict=True)
    if supplied_value:
        supplied = Path(supplied_value).expanduser().resolve(strict=True)
        if supplied != canonical_bound:
            core._fail("--recovery-runtime-manifest does not match recovery evidence.")
    return canonical_bound


def _reconciled_upgrade(
    args: argparse.Namespace,
    target: dict[str, Any],
    cli: Path,
    environment: dict[str, str],
    receipt_path: Path,
    reservation: dict[str, Any],
) -> Path:
    preflight_started = core._utc_now()
    if args.intent != "upgrade":
        core._fail("candidate mode reconciled supports only --intent upgrade.")
    if not args.recovery_plan:
        core._fail("--recovery-plan is required for reconciled mode.")
    recovery_plan_path = Path(args.recovery_plan).expanduser().resolve(strict=True)
    plan, context = recovery._load_plan(recovery_plan_path)
    # Reconciled execution must use the exact constrained environment defined by
    # the reviewed recovery lane. In particular, do not inherit the caller's
    # PATH when validating or invoking the pinned Node/CLI runtime.
    recovery_environment = recovery._recovery_environment(environment)
    _match_recovery_inputs(args, plan, target, cli)
    _assert_no_prior_recovery_execution(recovery_plan_path, plan, recovery_environment)
    runtime_manifest_path = _reconciled_runtime_manifest_path(
        args.recovery_runtime_manifest, context
    )
    project_root = Path(plan["project_root"])
    _audit_tracked_source(project_root, project_root)
    _resolve_reconciled_package(project_root, plan, context)
    config_path = project_root / "uipath.json"
    config_document, config_payload = _load_and_audit_uipath_config(
        config_path, "Reconciled source"
    )
    _validate_evidence_isolation(
        receipt_path,
        project_root,
        [
            config_path,
            Path(plan["candidate"]["source_cli_executable"]).parents[3],
            Path(plan["candidate"]["recovery_runtime_root"]),
            runtime_manifest_path,
        ],
        include_workspace=False,
    )
    git_head, git_status_digest, source_sha = _git_state(project_root)
    _validate_internal_config(config_document, target, plan["existing_deployment"]["route_name"])
    recovery._preflight(plan, context, recovery_environment)
    local_times = {"local_preflight": (preflight_started, core._utc_now())}
    candidate = _base_candidate(
        args,
        git_head=git_head,
        git_status_digest=git_status_digest,
        source_sha=source_sha,
        dist_digest=None,
        uipath_config_digest=core._hash_bytes(config_payload),
        package_content_digest=plan["candidate"]["package_content_digest"],
        package_file_digest=plan["candidate"]["package_file_digest"],
        recovery_plan_hash=plan["plan_hash"],
        deployment_id=plan["existing_deployment"]["deployment_id"],
        system_name=plan["candidate"]["system_name"],
        deploy_version=plan["candidate"]["deploy_version"],
        current_version=plan["existing_deployment"]["deployed_version"],
        runtime_manifest_hash=plan["candidate"]["recovery_runtime_manifest_hash"],
        node_executable=plan["candidate"]["recovery_node_executable"],
        node_executable_sha256=plan["candidate"]["recovery_node_executable_sha256"],
        node_version=plan["candidate"]["recovery_node_version"],
        runtime_app_config_digest=plan["candidate"]["recovery_workspace_app_config_sha256"],
        runtime_immutable_digest=_immutable_runtime_digest(
            Path(plan["candidate"]["recovery_runtime_root"]),
            [
                Path(plan["candidate"]["recovery_workspace"])
                / core.APP_CONFIG_RELATIVE_PATH
            ],
        ),
        main_file=context["failed_plan"]["parameters"]["main_file"],
        content_type=context["failed_plan"]["parameters"]["content_type"],
    )
    _assert_common_candidate(candidate)
    claim_path, claim = _create_claim(target, candidate, recovery_environment)
    stages = _stages(RECONCILED_STAGE_CONTRACT, local_times)
    receipt = _new_receipt(
        args, target, candidate, claim_path, claim, reservation, stages
    )
    try:
        _write_receipt(receipt_path, receipt)
    except (Exception, SystemExit, KeyboardInterrupt):
        _release_unstarted_claim(claim_path, claim)
        raise
    _start_stage(receipt, receipt_path, "remote_pre_guard")
    try:
        receipt["observations"]["prewrite"] = recovery._run_remote_guard(
            plan["stages"][2],
            plan,
            expected_current_version=plan["upgrade_guard"]["current_version"],
            environment=recovery_environment,
        )
    except (Exception, SystemExit, KeyboardInterrupt):
        _fail_stage(
            receipt, receipt_path, "remote_pre_guard",
            status="failed_prewrite",
            error_code="REMOTE_PRE_GUARD_FAILED",
            recovery_text="safe_prewrite_failure; reconcile target and submit a fresh testing request",
        )
        _release_claim(claim_path, claim, receipt, receipt_path)
        raise
    _finish_stage(receipt, receipt_path, "remote_pre_guard")
    _start_stage(receipt, receipt_path, "runtime_barrier")
    try:
        _revalidate_reconciled_testing_barrier(
            plan, context, candidate, recovery_environment
        )
    except (Exception, SystemExit, KeyboardInterrupt):
        _fail_stage(
            receipt, receipt_path, "runtime_barrier",
            status="failed_prewrite",
            error_code="RUNTIME_BARRIER_FAILED",
            recovery_text="safe_prewrite_failure; rebuild evidence and submit a fresh testing request",
        )
        _release_claim(claim_path, claim, receipt, receipt_path)
        raise
    _finish_stage(receipt, receipt_path, "runtime_barrier")
    _start_stage(receipt, receipt_path, "deploy", external_write=True)
    try:
        _revalidate_reconciled_testing_barrier(
            plan, context, candidate, recovery_environment
        )
        _run_write(
            plan["stages"][4]["command"],
            Path(plan["stages"][4]["cwd"]),
            recovery_environment,
            "DEPLOY_INDETERMINATE",
        )
    except (Exception, SystemExit, KeyboardInterrupt):
        _fail_stage(
            receipt, receipt_path, "deploy",
            status="deploy_indeterminate",
            error_code="DEPLOY_INDETERMINATE",
            recovery_text="reconcile exact deployment; blind retry and fresh-app fallback prohibited",
        )
        raise
    _finish_stage(
        receipt,
        receipt_path,
        "deploy",
        receipt_status="deployed_unverified",
    )
    _start_stage(receipt, receipt_path, "remote_post_guard")
    try:
        _revalidate_reconciled_immutable_runtime(plan, candidate)
        receipt["observations"]["postwrite"] = recovery._run_remote_guard(
            plan["stages"][5],
            plan,
            expected_current_version=plan["candidate"]["version"],
            environment=recovery_environment,
        )
    except (Exception, SystemExit, KeyboardInterrupt):
        _fail_stage(
            receipt, receipt_path, "remote_post_guard",
            status="deployed_unverified",
            error_code="REMOTE_POST_GUARD_FAILED",
            recovery_text="deployment may have succeeded; reconcile exact remote state before any new request",
        )
        raise
    _finish_stage(receipt, receipt_path, "remote_post_guard")
    _start_stage(receipt, receipt_path, "route_verify")
    try:
        core._verify_url(plan["existing_deployment"]["app_url"], args.verify_timeout)
        receipt["verification"]["route_verified"] = True
    except (Exception, SystemExit, KeyboardInterrupt):
        _fail_stage(
            receipt, receipt_path, "route_verify",
            status="deployed_unverified",
            error_code="ROUTE_VERIFY_FAILED",
            recovery_text="deployment may have succeeded; inspect exact route and assets",
        )
        raise
    _finish_stage(receipt, receipt_path, "route_verify")
    _start_stage(receipt, receipt_path, "config_verify")
    try:
        recovery._inspect_post_deploy_config(
            Path(plan["candidate"]["recovery_workspace"]),
            plan,
            {
                "post_deploy_app_config_digest": None,
                "observed_local_app_url": None,
                "local_app_url_matches_verified_route": None,
            },
        )
        receipt["verification"]["post_deploy_app_config_digest"] = core._hash_file(
            Path(plan["candidate"]["recovery_workspace"]) / core.APP_CONFIG_RELATIVE_PATH,
            "reconciled post-deploy app config",
        )
        receipt["verification"]["configuration_verified"] = True
    except (Exception, SystemExit, KeyboardInterrupt):
        _fail_stage(
            receipt, receipt_path, "config_verify",
            status="deployed_unverified",
            error_code="CONFIG_VERIFY_FAILED",
            recovery_text="deployment may have succeeded; reconcile exact app configuration",
        )
        raise
    _finish_stage(receipt, receipt_path, "config_verify")
    receipt["status"] = "succeeded_testing"
    _write_receipt(receipt_path, receipt)
    return receipt_path


def _published_recovery_upgrade(
    args: argparse.Namespace,
    target: dict[str, Any],
    cli: Path,
    environment: dict[str, str],
    receipt_path: Path,
    reservation: dict[str, Any],
) -> Path:
    preflight_started = core._utc_now()
    if args.intent != "upgrade" or args.candidate_mode != "published-recovery":
        core._fail("Published recovery supports only --intent upgrade.")
    if not args.failed_testing_receipt:
        core._fail("--failed-testing-receipt is required for published recovery.")
    source_path = Path(args.failed_testing_receipt).expanduser().resolve(strict=True)
    expected_receipt_hash = _require_hash(
        args.expected_failed_receipt_hash,
        "--expected-failed-receipt-hash",
    )
    expected_receipt_file = _require_hash(
        args.expected_failed_receipt_file_sha256,
        "--expected-failed-receipt-file-sha256",
    )
    source_receipt = _load_publish_recovery_receipt(
        source_path,
        expected_receipt_hash=expected_receipt_hash,
        expected_file_sha256=expected_receipt_file,
    )
    _match_publish_recovery_inputs(args, target, source_receipt)
    retained = source_receipt["execution_claim"]
    if _require_hash(
        args.expected_retained_claim_hash,
        "--expected-retained-claim-hash",
    ) != retained["claim_hash"]:
        core._fail("Retained claim hash does not match explicit recovery authority.")
    if _require_hash(
        args.expected_retained_claim_file_sha256,
        "--expected-retained-claim-file-sha256",
    ) != retained["file_sha256"]:
        core._fail("Retained claim file hash does not match explicit recovery authority.")
    paths = _publish_recovery_paths(source_path, source_receipt["candidate"])
    if args.recovery_runtime_manifest and Path(
        args.recovery_runtime_manifest
    ).expanduser().resolve(strict=True) != paths["runtime_manifest"].resolve(strict=True):
        core._fail("--recovery-runtime-manifest does not match the failed receipt workspace.")
    runtime = _load_publish_recovery_runtime(
        paths["runtime_manifest"], source_receipt
    )
    source_candidate = source_receipt["candidate"]
    runtime_workspace = _publish_recovery_runtime_workspace(paths, runtime)
    # Validate the immutable runtime before creating the transition claim. The
    # retained app config is the sole declared mutable runtime file and must
    # already have the exact six-field guarded-upgrade shape; recovery never
    # rewrites it before the remote candidate proof.
    _revalidate_create_runtime_immutable(runtime, source_candidate)
    pre_config_digest, bound_config, bound_config_digest = _publish_recovery_bound_config(
        runtime_workspace / core.APP_CONFIG_RELATIVE_PATH,
        source_candidate,
        target,
    )
    candidate = copy.deepcopy(source_candidate)
    candidate["mode"] = "published-recovery"
    candidate["helper_sha256"] = core._hash_file(Path(__file__), "testing helper")
    candidate["runtime_app_config_digest"] = bound_config_digest
    _validate_candidate_record(candidate)
    source_record = _publish_recovery_source_record(
        source_path,
        source_receipt,
        paths,
        pre_config_digest,
    )
    local_times = {"local_preflight": (preflight_started, core._utc_now())}
    transition_path, transition_claim = _create_publish_recovery_transition_claim(
        source_path,
        source_receipt,
        candidate,
        reservation,
    )
    stages = _stages(PUBLISHED_RECOVERY_STAGE_CONTRACT, local_times)
    try:
        receipt = _new_receipt(
            args,
            target,
            candidate,
            transition_path,
            transition_claim,
            reservation,
            stages,
            recovery_source=source_record,
        )
        _write_receipt(receipt_path, receipt)
    except (Exception, SystemExit, KeyboardInterrupt):
        _release_unstarted_claim(transition_path, transition_claim)
        raise

    _start_stage(receipt, receipt_path, "claim_transition")
    try:
        _publish_recovery_runtime_workspace(paths, runtime)
        observed_digest, observed_config, _ = _publish_recovery_bound_config(
            runtime_workspace / core.APP_CONFIG_RELATIVE_PATH,
            source_candidate,
            target,
        )
        if observed_digest != bound_config_digest or observed_config != bound_config:
            core._fail("Publish recovery app config binding changed.")
    except (Exception, SystemExit, KeyboardInterrupt):
        _fail_stage(
            receipt,
            receipt_path,
            "claim_transition",
            status="failed_prewrite",
            error_code="RECOVERY_CLAIM_TRANSITION_FAILED",
            recovery_text="safe_prewrite_failure; original claim retained; reconcile local config and submit a fresh testing request",
        )
        _release_claim(transition_path, transition_claim, receipt, receipt_path)
        raise
    _finish_stage(receipt, receipt_path, "claim_transition")

    node_runtime = {
        "executable": candidate["node_executable"],
        "executable_sha256": candidate["node_executable_sha256"],
        "version": candidate["node_version"],
    }
    _start_stage(receipt, receipt_path, "profile_guard")
    try:
        _validate_cli(target, runtime_workspace, environment, node_runtime)
    except (Exception, SystemExit, KeyboardInterrupt):
        _fail_stage(
            receipt,
            receipt_path,
            "profile_guard",
            status="failed_prewrite",
            error_code="RECOVERY_PROFILE_GUARD_FAILED",
            recovery_text="safe_prewrite_failure; authenticate the exact profile and submit a fresh testing request",
        )
        _release_claim(transition_path, transition_claim, receipt, receipt_path)
        raise
    _finish_stage(receipt, receipt_path, "profile_guard")

    published = {
        "systemName": candidate["system_name"],
        "deployVersion": candidate["deploy_version"],
    }
    _start_stage(receipt, receipt_path, "remote_candidate_guard")
    try:
        # The patched runtime performs a nominally read-only candidate lookup,
        # but it is still executable code. Prove every source/runtime/package
        # byte before the first invocation; a manifest-only check is not a
        # sufficient trust boundary for recovery.
        _revalidate_publish_recovery_barrier(
            source_record,
            target,
            candidate,
            runtime,
            transition_path,
            transition_claim,
            require_bound_config=True,
        )
        output = _run_read(
            _upgrade_guard_command(
                runtime,
                target,
                candidate,
                "upgrade-candidate",
                published=published,
            ),
            runtime_workspace,
            environment,
            "RECOVERY_CANDIDATE_GUARD_FAILED",
        )
        observation = _validate_upgrade_guard_output(
            output,
            target,
            candidate,
            "upgrade-candidate",
            published=published,
        )
        receipt["observations"]["prewrite"] = copy.deepcopy(observation)
        receipt["observations"]["published_candidate"] = copy.deepcopy(observation)
    except (Exception, SystemExit, KeyboardInterrupt):
        _fail_stage(
            receipt,
            receipt_path,
            "remote_candidate_guard",
            status="failed_prewrite",
            error_code="RECOVERY_CANDIDATE_GUARD_FAILED",
            recovery_text="safe_prewrite_failure; reconcile exact remote candidate and submit a fresh testing request",
        )
        _release_claim(transition_path, transition_claim, receipt, receipt_path)
        raise
    _finish_stage(receipt, receipt_path, "remote_candidate_guard")

    _start_stage(receipt, receipt_path, "pre_deploy_barrier")
    try:
        _revalidate_publish_recovery_barrier(
            source_record,
            target,
            candidate,
            runtime,
            transition_path,
            transition_claim,
            require_bound_config=True,
        )
    except (Exception, SystemExit, KeyboardInterrupt):
        _fail_stage(
            receipt,
            receipt_path,
            "pre_deploy_barrier",
            status="failed_prewrite",
            error_code="RECOVERY_PRE_DEPLOY_BARRIER_FAILED",
            recovery_text="safe_prewrite_failure; exact recovery evidence changed; submit a fresh testing request",
        )
        _release_claim(transition_path, transition_claim, receipt, receipt_path)
        raise
    _finish_stage(receipt, receipt_path, "pre_deploy_barrier")

    _start_stage(receipt, receipt_path, "deploy", external_write=True)
    try:
        _revalidate_publish_recovery_barrier(
            source_record,
            target,
            candidate,
            runtime,
            transition_path,
            transition_claim,
            require_bound_config=True,
        )
        deploy_result = _run_write(
            _upgrade_guard_command(
                runtime,
                target,
                candidate,
                "upgrade-execute",
                published=published,
            ),
            runtime_workspace,
            environment,
            "DEPLOY_INDETERMINATE",
        )
        _validate_upgrade_guard_output(
            deploy_result,
            target,
            candidate,
            "upgrade-execute",
            published=published,
        )
    except (Exception, SystemExit, KeyboardInterrupt):
        _fail_stage(
            receipt,
            receipt_path,
            "deploy",
            status="deploy_indeterminate",
            error_code="DEPLOY_INDETERMINATE",
            recovery_text="reconcile exact deployment; both claims remain retained and blind retry is prohibited",
        )
        raise
    _finish_stage(
        receipt,
        receipt_path,
        "deploy",
        receipt_status="deployed_unverified",
    )

    _start_stage(receipt, receipt_path, "remote_post_guard")
    try:
        _revalidate_publish_recovery_barrier(
            source_record,
            target,
            candidate,
            runtime,
            transition_path,
            transition_claim,
            require_bound_config=False,
        )
        output = _run_read(
            _upgrade_guard_command(
                runtime,
                target,
                candidate,
                "upgrade-post",
                published=published,
            ),
            runtime_workspace,
            environment,
            "RECOVERY_POST_GUARD_FAILED",
        )
        receipt["observations"]["postwrite"] = _validate_upgrade_guard_output(
            output,
            target,
            candidate,
            "upgrade-post",
            published=published,
        )
    except (Exception, SystemExit, KeyboardInterrupt):
        _fail_stage(
            receipt,
            receipt_path,
            "remote_post_guard",
            status="deployed_unverified",
            error_code="RECOVERY_POST_GUARD_FAILED",
            recovery_text="deployment may have succeeded; reconcile exact post-state before any new request",
        )
        raise
    _finish_stage(receipt, receipt_path, "remote_post_guard")

    _start_stage(receipt, receipt_path, "route_verify")
    try:
        core._verify_url(_route_url(target, candidate["path_name"]), args.verify_timeout)
        receipt["verification"]["route_verified"] = True
    except (Exception, SystemExit, KeyboardInterrupt):
        _fail_stage(
            receipt,
            receipt_path,
            "route_verify",
            status="deployed_unverified",
            error_code="ROUTE_VERIFY_FAILED",
            recovery_text="deployment may have succeeded; inspect exact route and assets",
        )
        raise
    _finish_stage(receipt, receipt_path, "route_verify")

    _start_stage(receipt, receipt_path, "config_verify")
    try:
        config_path = runtime_workspace / core.APP_CONFIG_RELATIVE_PATH
        document = json.loads(config_path.read_text(encoding="utf-8"))
        expected_fields = {
            "appName", "displayName", "appVersion", "appUrl", "deployedAt",
            "appType", "personalWorkspace",
        }
        if (
            not isinstance(document, dict)
            or set(document) != expected_fields
            or document.get("appName") != candidate["package_name"]
            or document.get("displayName") != candidate["app_name"]
            or document.get("appVersion") != candidate["version"]
            or document.get("appUrl") != _route_url(target, candidate["path_name"])
            or document.get("appType") != "Web"
            or document.get("personalWorkspace") is not False
        ):
            core._fail("Publish recovery post-deploy app config is invalid.")
        recovery._require_iso8601(document["deployedAt"], "Publish recovery deployedAt")
        receipt["verification"]["post_deploy_app_config_digest"] = core._hash_file(
            config_path,
            "publish recovery post-deploy app config",
        )
        receipt["verification"]["configuration_verified"] = True
    except (Exception, SystemExit, KeyboardInterrupt):
        _fail_stage(
            receipt,
            receipt_path,
            "config_verify",
            status="deployed_unverified",
            error_code="CONFIG_VERIFY_FAILED",
            recovery_text="deployment may have succeeded; reconcile exact app configuration",
        )
        raise
    _finish_stage(receipt, receipt_path, "config_verify")
    receipt["status"] = "succeeded_testing"
    _write_receipt(receipt_path, receipt)
    return receipt_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute one explicit synthetic-only Alpha or Staging Coded App test deployment."
    )
    parser.add_argument("--testing-only", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--intent", choices=("create", "upgrade"))
    parser.add_argument(
        "--candidate-mode",
        choices=("dist", "reconciled", "published-recovery"),
    )
    parser.add_argument("--environment", choices=("alpha", "staging"))
    parser.add_argument("--control-plane-url")
    parser.add_argument("--org-id")
    parser.add_argument("--org-name")
    parser.add_argument("--tenant-id")
    parser.add_argument("--tenant-name")
    parser.add_argument("--folder-key")
    parser.add_argument("--package-name")
    parser.add_argument("--app-name")
    parser.add_argument("--path-name")
    parser.add_argument("--client-id")
    parser.add_argument("--version")
    parser.add_argument("--tags")
    parser.add_argument("--cli-executable")
    parser.add_argument("--cli-version")
    parser.add_argument("--cli-profile")
    parser.add_argument("--node-executable")
    parser.add_argument("--node-version")
    parser.add_argument("--testing-purpose")
    parser.add_argument("--receipt-output")
    parser.add_argument("--project-root")
    parser.add_argument("--app-dist")
    parser.add_argument("--main-file")
    parser.add_argument("--content-type")
    parser.add_argument("--author")
    parser.add_argument("--recovery-plan")
    parser.add_argument("--recovery-runtime-manifest")
    parser.add_argument("--expected-recovery-plan-hash")
    parser.add_argument("--expected-deployment-id")
    parser.add_argument("--expected-system-name")
    parser.add_argument("--expected-current-version")
    parser.add_argument("--expected-deploy-version", type=int)
    parser.add_argument("--expected-runtime-manifest-hash")
    parser.add_argument("--failed-testing-receipt")
    parser.add_argument("--expected-failed-receipt-hash")
    parser.add_argument("--expected-failed-receipt-file-sha256")
    parser.add_argument("--expected-retained-claim-hash")
    parser.add_argument("--expected-retained-claim-file-sha256")
    parser.add_argument("--expected-package-file-sha256")
    parser.add_argument("--expected-source-helper-sha256")
    parser.add_argument("--verify-timeout", type=int, default=15)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.testing_only or not args.execute:
        core._fail("Testing execution requires both --testing-only and --execute.")
    if args.intent is None or args.candidate_mode is None:
        core._fail("Testing execution requires explicit --intent and --candidate-mode.")
    if args.verify_timeout < 1 or args.verify_timeout > 120:
        core._fail("--verify-timeout must be between 1 and 120 seconds.")
    testing_purpose = _require_text(args.testing_purpose, "--testing-purpose")
    _audit_payload(
        json.dumps(vars(args), sort_keys=True, default=str).encode("utf-8")
    )
    _require_path_name(args.path_name)
    receipt_path = _receipt_path(args.receipt_output)
    cli = _resolve_cli(args.cli_executable)
    target = _target(args, cli)
    reservation = _reserve_receipt(receipt_path)
    try:
        environment = _safe_environment()
        if args.candidate_mode == "dist":
            result = _dist_create(
                args, target, cli, environment, receipt_path, reservation
            )
        elif args.candidate_mode == "reconciled":
            result = _reconciled_upgrade(
                args, target, cli, environment, receipt_path, reservation
            )
        else:
            result = _published_recovery_upgrade(
                args, target, cli, environment, receipt_path, reservation
            )
    except (Exception, SystemExit, KeyboardInterrupt) as exc:
        if not receipt_path.exists():
            preflight = _new_preflight_failure_receipt(
                args, target, reservation, "LOCAL_PREFLIGHT_FAILED"
            )
            _write_receipt(receipt_path, preflight)
        if isinstance(exc, SystemExit):
            raise
        raise SystemExit(
            "Testing deployment failed with redacted local diagnostics; inspect the automatic receipt."
        ) from None
    print(
        json.dumps(
            {
                "status": "succeeded_testing",
                "receipt": str(result),
                "production_eligible": False,
                "release_evidence": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
