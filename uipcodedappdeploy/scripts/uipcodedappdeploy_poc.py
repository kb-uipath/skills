#!/usr/bin/env python3
"""Fast, fail-closed UiPath Coded App POC deployments.

This is an additive lane. It does not create governed release evidence and it
does not relax the governed v2.3 or testing-only v1.2 helpers.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import uipcodedappdeploy_recover as recovery
import uipcodedappdeploy_testing as testing

import uipcodedappdeploy as core

CONFIG_KIND = "uipcodedappdeploy.poc-target"
CONFIG_VERSION = "1.0"
RECEIPT_KIND = "uipcodedappdeploy.poc-receipt"
RECEIPT_VERSION = "1.0"
POLICY_VERSION = "1.0"
RUNTIME_KIND = "uipcodedappdeploy.poc-runtime"
RUNTIME_VERSION = "1.0"

CLI_VERSION = "1.199.0"
CLI_GIT_HEAD = "723e6801b77b5926ba75e75b6a756cc38b1b7adc"
CLI_SHA256 = "sha256:e0bc13ac0afd7d750219e74738202cbb63edb7913e3200375afd5149cc326899"
CLI_MANIFEST_SHA256 = "sha256:13133793a3fc709014e1ba84e89b598ac6ceb9bdc696e3bc7f9c3911ddaa27f7"
CODEDAPP_SHA256 = "sha256:a3cccf74eb5e00c0fdff06e8be8323da53c5b6cceb06cbc57a08bb95d2a9b8b9"
CODEDAPP_GUARDED_SHA256 = "sha256:91d344571f3ef438c04ce92ffca80c906e7367227dfd485eebb1630030e14cd0"
CODEDAPP_MANIFEST_SHA256 = "sha256:7b906a462de1e93e91ef2745a28e79f150d4816123fb70e8e747e2e65d403daa"
ORCHESTRATOR_SHA256 = "sha256:673684e60fc6c1165fe5b7f0da69fe30b3230e3f38ba1a9f5046f4a97c7ba96f"
ORCHESTRATOR_MANIFEST_SHA256 = "sha256:2ab846ddca2ed53d43d68c5e5bad0b1c342ca8390c1e7ababc7a02ddcba06d21"

TARGETS = {
    "alpha": {
        "control_plane_url": "https://alpha.uipath.com",
        "api_url": "https://alpha.api.uipath.com",
        "host": lambda org: f"{org}.alpha.uipath.host",
    },
    "staging": {
        "control_plane_url": "https://staging.uipath.com",
        "api_url": "https://staging.api.uipath.com",
        "host": lambda org: f"{org}.staging.uipath.host",
    },
    "production": {
        "control_plane_url": "https://cloud.uipath.com",
        "api_url": "https://api.uipath.com",
        "host": lambda org: f"{org}.uipath.host",
    },
}

PACKAGE_SPECS = (
    f"@uipath/cli@{CLI_VERSION}",
    f"@uipath/codedapp-tool@{CLI_VERSION}",
    f"@uipath/orchestrator-tool@{CLI_VERSION}",
)

CONFIG_FIELDS = {
    "kind", "schema_version", "project_key", "project_root", "environment",
    "control_plane_url", "api_url", "organization_id", "organization_name",
    "tenant_id", "tenant_name", "folder_key", "folder_name", "folder_path",
    "folder_type", "cli_profile", "cli_profile_hash", "app_type", "package_name",
    "app_name", "path_name", "client_id", "tags", "node_executable",
    "node_executable_sha256", "node_version", "runtime_manifest",
    "runtime_manifest_sha256", "configured_at", "config_hash",
}

REDACTION = {
    "commands": "omitted",
    "environment": "omitted",
    "subprocess_output": "omitted",
    "errors": "stable_code_only",
    "secrets": "prohibited",
}

FORBIDDEN_ENVIRONMENT = frozenset(recovery.FORBIDDEN_RECOVERY_ENVIRONMENT)


class PocCommandError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _require_text(value: Any, label: str, *, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        core._fail(f"{label} is required.")
    result = value.strip()
    if len(result) > maximum or any(ord(character) < 32 for character in result):
        core._fail(f"{label} contains unsupported text.")
    return result


def _require_guid(value: Any, label: str) -> str:
    result = _require_text(value, label)
    if core.GUID_RE.fullmatch(result) is None:
        core._fail(f"{label} must be an exact GUID.")
    return result.lower()


def _require_route(value: Any, label: str = "route") -> str:
    result = _require_text(value, label).lower()
    if len(result) > 32 or core.PATH_NAME_RE.fullmatch(result) is None:
        core._fail(f"{label} must be a lowercase route slug of at most 32 characters.")
    return result


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return _require_route(result[:32].rstrip("-"), "derived route")


def _project_root(value: Any) -> Path:
    raw = Path(_require_text(value, "--project-root")).expanduser()
    try:
        root = raw.resolve(strict=True)
    except (OSError, RuntimeError):
        core._fail("--project-root does not resolve to a real directory.")
    if root.is_symlink() or not root.is_dir():
        core._fail("--project-root must be a real non-symlink directory.")
    if any((root / name).exists() for name in ("project.uiproj", "webAppManifest.json")):
        core._fail("POC standalone deployment is prohibited for a solution-managed coded app.")
    return root


def _project_key(root: Path) -> str:
    return hashlib.sha256(str(root).encode("utf-8")).hexdigest()


def _poc_root(home: Path | None = None) -> Path:
    base = (home or Path.home()).expanduser()
    if not base.is_absolute() or base.is_symlink() or not base.is_dir():
        core._fail("POC deployment requires a real absolute home directory.")
    uipath = base / ".uipath"
    if uipath.exists() and (uipath.is_symlink() or not uipath.is_dir()):
        core._fail("~/.uipath must be a real directory.")
    uipath.mkdir(mode=0o700, exist_ok=True)
    root = uipath / "poc-deploy"
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        core._fail("POC deployment root must be a real directory.")
    root.mkdir(mode=0o700, exist_ok=True)
    os.chmod(root, 0o700)
    return root


def _config_path(root: Path, home: Path | None = None) -> Path:
    return _poc_root(home) / "targets" / f"{_project_key(root)}.json"


def _atomic_private_json(path: Path, document: dict[str, Any], *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        core._fail(f"Refusing to overwrite existing file: {path}")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.parent.is_symlink() or not path.parent.is_dir():
        core._fail("Private POC output parent must be a real directory.")
    os.chmod(path.parent, 0o700)
    payload = json.dumps(document, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists() and path.is_symlink():
            core._fail("Private POC output may not replace a symlink.")
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _load_private_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        core._fail(f"{label} must be a regular non-symlink file.")
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        core._fail(f"{label} must have mode 0600.")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        core._fail(f"{label} is not valid UTF-8 JSON.")
    if not isinstance(document, dict):
        core._fail(f"{label} must be a JSON object.")
    return document


def _safe_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    observed = os.environ if source is None else source
    injected = sorted(name for name in FORBIDDEN_ENVIRONMENT if name in observed)
    if injected:
        core._fail("POC runtime environment contains prohibited injection variables: " + ", ".join(injected))
    environment = recovery._recovery_environment(observed)
    environment["UIPATH_CLI_DISABLE_VERSION_SYNC"] = "1"
    environment["UIPATH_CLI_DISABLE_AUTOINSTALL"] = "1"
    environment["UIPATH_TELEMETRY_DISABLED"] = "true"
    return environment


def _build_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    observed = os.environ if source is None else source
    injected = sorted(name for name in FORBIDDEN_ENVIRONMENT if name in observed)
    if injected:
        core._fail("Build environment contains prohibited injection variables: " + ", ".join(injected))
    environment = {
        key: observed[key]
        for key in ("HOME", "PATH", "TMPDIR", "LANG", "LC_ALL")
        if isinstance(observed.get(key), str) and observed[key]
    }
    environment.update({
        "NO_COLOR": "1",
        "UIPATH_CLI_DISABLE_VERSION_SYNC": "1",
        "UIPATH_TELEMETRY_DISABLED": "true",
    })
    return environment


def _run_read(command: list[str], cwd: Path, environment: dict[str, str], code: str) -> str:
    core._log(f"+ poc read: {Path(command[0]).name} {command[1] if len(command) > 1 else ''}")
    try:
        completed = subprocess.run(
            command, cwd=cwd, env=environment, check=True, capture_output=True, text=True
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PocCommandError(code) from exc
    return completed.stdout


def _run_write(command: list[str], cwd: Path, environment: dict[str, str], code: str) -> dict[str, Any]:
    core._log(f"+ poc write: {Path(command[0]).name} {command[1]} {command[2]}")
    try:
        completed = subprocess.run(
            command, cwd=cwd, env=environment, check=True, capture_output=True, text=True
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PocCommandError(code) from exc
    document = testing._extract_json_envelope(completed.stdout, code)
    if document.get("Result") != "Success":
        raise PocCommandError(code)
    return document


def _node_runtime(value: str | None = None) -> dict[str, str]:
    raw = value or shutil.which("node")
    if not raw:
        core._fail("Node.js is required; pass --node-executable during configuration.")
    path = Path(raw).expanduser().resolve(strict=True)
    if path.is_symlink() or not path.is_file() or not os.access(path, os.X_OK):
        core._fail("Node.js executable must be an executable regular file.")
    try:
        completed = subprocess.run(
            [str(path), "--version"], check=True, capture_output=True, text=True,
            env=_safe_environment(),
        )
    except (OSError, subprocess.CalledProcessError):
        core._fail("Could not execute Node.js.")
    version = completed.stdout.strip().removeprefix("v")
    match = re.fullmatch(r"([0-9]+)\.([0-9]+)\.([0-9]+)", version)
    if match is None or int(match.group(1)) < 20:
        core._fail("POC deployment requires Node.js 20 or later.")
    return {
        "executable": str(path),
        "sha256": core._hash_file(path, "POC Node.js executable"),
        "version": version,
    }


def _manifest_contract(path: Path, name: str, digest: str, main_digest: str) -> None:
    if path.is_symlink() or not path.is_file() or core._hash_file(path, name) != digest:
        core._fail(f"{name} is not the pinned 1.199.0 build.")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        core._fail(f"{name} is invalid.")
    if (
        document.get("version") != CLI_VERSION
        or document.get("gitHead") != CLI_GIT_HEAD
        or core._hash_file(path.parent / "dist" / "tool.js", f"{name} tool") != main_digest
    ):
        core._fail(f"{name} package identity is unsupported.")


def _patch_contract_hash() -> str:
    return core._hash_json({
        "algorithm": "uipath-codedapp-tool-1.199.0-poc-guard-v1",
        "source": CODEDAPP_SHA256,
        "edits": [{"source": old, "replacement": new} for old, new in POC_PATCH_EDITS],
    })


def _patched_tool_bytes(source: bytes) -> bytes:
    if core._hash_bytes(source) != CODEDAPP_SHA256:
        core._fail("Coded app tool bytes are not the pinned 1.199.0 build.")
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError:
        core._fail("Coded app tool source is not UTF-8.")
    for old, new in POC_PATCH_EDITS:
        if text.count(old) != 1:
            core._fail("POC guarded runtime patch anchor did not match exactly once.")
        text = text.replace(old, new, 1)
    return text.encode("utf-8")


def _runtime_paths(root: Path) -> dict[str, Path]:
    runtime_root = root / "runtime" / CLI_VERSION
    node_modules = runtime_root / "node_modules"
    return {
        "root": runtime_root,
        "manifest": runtime_root / "poc-runtime.json",
        "cli_manifest": node_modules / "@uipath" / "cli" / "package.json",
        "cli": node_modules / "@uipath" / "cli" / "dist" / "index.js",
        "codedapp_manifest": node_modules / "@uipath" / "codedapp-tool" / "package.json",
        "codedapp": node_modules / "@uipath" / "codedapp-tool" / "dist" / "tool.js",
        "orchestrator_manifest": node_modules / "@uipath" / "orchestrator-tool" / "package.json",
        "orchestrator": node_modules / "@uipath" / "orchestrator-tool" / "dist" / "tool.js",
    }


def _runtime_self_test(paths: dict[str, Path], node: dict[str, str]) -> None:
    environment = _safe_environment()
    try:
        subprocess.run(
            [node["executable"], "--check", str(paths["codedapp"])],
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        blocked = subprocess.run(
            [
                node["executable"],
                str(paths["cli"]),
                "codedapp",
                "deploy",
                "--output",
                "json",
            ],
            cwd=paths["root"],
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise SystemExit("POC guarded runtime self-test could not execute.") from exc
    try:
        document = json.loads(blocked.stdout)
    except json.JSONDecodeError:
        core._fail("POC guarded runtime self-test returned invalid JSON.")
    if (
        blocked.returncode == 0
        or not isinstance(document, dict)
        or document.get("Result") != "Failure"
        or "POC_GUARD_REQUIRED" not in str(document.get("Instructions", ""))
    ):
        core._fail("POC guarded runtime did not block an unguarded deploy before network access.")


def _validate_runtime(root: Path, node: dict[str, str]) -> dict[str, Any]:
    paths = _runtime_paths(root)
    manifest = _load_private_json(paths["manifest"], "POC runtime manifest")
    required = {
        "kind", "schema_version", "cli_version", "git_head", "cli_sha256",
        "cli_manifest_sha256", "codedapp_source_sha256", "codedapp_guarded_sha256",
        "codedapp_manifest_sha256", "orchestrator_sha256",
        "orchestrator_manifest_sha256", "patch_contract_sha256", "created_at",
        "manifest_hash",
    }
    if set(manifest) != required or manifest.get("kind") != RUNTIME_KIND or manifest.get("schema_version") != RUNTIME_VERSION:
        core._fail("POC runtime manifest shape is unsupported.")
    if core._document_hash(manifest, "manifest_hash") != manifest.get("manifest_hash"):
        core._fail("POC runtime manifest hash is invalid.")
    checks = {
        "cli_version": CLI_VERSION,
        "git_head": CLI_GIT_HEAD,
        "cli_sha256": CLI_SHA256,
        "cli_manifest_sha256": CLI_MANIFEST_SHA256,
        "codedapp_source_sha256": CODEDAPP_SHA256,
        "codedapp_guarded_sha256": CODEDAPP_GUARDED_SHA256,
        "codedapp_manifest_sha256": CODEDAPP_MANIFEST_SHA256,
        "orchestrator_sha256": ORCHESTRATOR_SHA256,
        "orchestrator_manifest_sha256": ORCHESTRATOR_MANIFEST_SHA256,
        "patch_contract_sha256": _patch_contract_hash(),
    }
    if any(manifest.get(key) != value for key, value in checks.items()):
        core._fail("POC runtime manifest does not match the pinned contract.")
    if core._hash_file(paths["cli"], "POC CLI") != CLI_SHA256:
        core._fail("POC CLI bytes changed.")
    if core._hash_file(paths["cli_manifest"], "POC CLI manifest") != CLI_MANIFEST_SHA256:
        core._fail("POC CLI manifest changed.")
    if core._hash_file(paths["codedapp_manifest"], "POC coded app manifest") != CODEDAPP_MANIFEST_SHA256:
        core._fail("POC coded app manifest changed.")
    if core._hash_file(paths["orchestrator_manifest"], "POC Orchestrator manifest") != ORCHESTRATOR_MANIFEST_SHA256:
        core._fail("POC Orchestrator manifest changed.")
    if core._hash_file(paths["orchestrator"], "POC Orchestrator tool") != ORCHESTRATOR_SHA256:
        core._fail("POC Orchestrator tool bytes changed.")
    if core._hash_file(paths["codedapp"], "POC guarded coded app tool") != CODEDAPP_GUARDED_SHA256:
        core._fail("POC guarded coded app tool changed.")
    if core._hash_file(Path(node["executable"]), "POC Node.js") != node["sha256"]:
        core._fail("Configured Node.js bytes changed.")
    return {
        "manifest": str(paths["manifest"]),
        "manifest_sha256": core._hash_file(paths["manifest"], "POC runtime manifest"),
        "cli": str(paths["cli"]),
        "cli_sha256": CLI_SHA256,
        "codedapp_guarded_sha256": manifest["codedapp_guarded_sha256"],
        "orchestrator_sha256": ORCHESTRATOR_SHA256,
        "patch_contract_sha256": manifest["patch_contract_sha256"],
    }


def _provision_runtime(root: Path, node: dict[str, str], npm_value: str | None = None) -> dict[str, Any]:
    paths = _runtime_paths(root)
    if paths["manifest"].exists():
        return _validate_runtime(root, node)
    npm_raw = npm_value or shutil.which("npm")
    if not npm_raw:
        core._fail("npm is required once to provision the pinned POC runtime.")
    npm = Path(npm_raw).expanduser().resolve(strict=True)
    if npm.is_symlink() or not npm.is_file() or not os.access(npm, os.X_OK):
        core._fail("npm executable must be an executable regular file.")
    paths["root"].parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if paths["root"].parent.is_symlink():
        core._fail("POC runtime parent may not be a symlink.")
    temporary = Path(tempfile.mkdtemp(prefix=f".{CLI_VERSION}.", dir=paths["root"].parent))
    try:
        package = {"private": True, "name": "uipcodedappdeploy-poc-runtime", "version": "1.0.0"}
        _atomic_private_json(temporary / "package.json", package, overwrite=False)
        environment = _build_environment()
        environment["npm_config_ignore_scripts"] = "true"
        environment["npm_config_audit"] = "false"
        environment["npm_config_fund"] = "false"
        try:
            subprocess.run(
                [str(npm), "install", "--save-exact", "--ignore-scripts", "--no-audit", "--no-fund", *PACKAGE_SPECS],
                cwd=temporary, env=environment, check=True, capture_output=True, text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise SystemExit("POC runtime provisioning failed; no deployment was attempted.") from exc
        temporary_paths = _runtime_paths(root)
        temporary_paths = {key: temporary / value.relative_to(paths["root"]) for key, value in temporary_paths.items()}
        if core._hash_file(temporary_paths["cli"], "downloaded POC CLI") != CLI_SHA256:
            core._fail("Downloaded POC CLI does not match the pinned digest.")
        _manifest_contract(temporary_paths["codedapp_manifest"], "downloaded coded app manifest", CODEDAPP_MANIFEST_SHA256, CODEDAPP_SHA256)
        _manifest_contract(temporary_paths["orchestrator_manifest"], "downloaded Orchestrator manifest", ORCHESTRATOR_MANIFEST_SHA256, ORCHESTRATOR_SHA256)
        if core._hash_file(temporary_paths["cli_manifest"], "downloaded CLI manifest") != CLI_MANIFEST_SHA256:
            core._fail("Downloaded POC CLI manifest does not match the pinned digest.")
        guarded = _patched_tool_bytes(temporary_paths["codedapp"].read_bytes())
        if core._hash_bytes(guarded) != CODEDAPP_GUARDED_SHA256:
            core._fail("Deterministic POC guarded runtime digest changed.")
        temporary_paths["codedapp"].write_bytes(guarded)
        _runtime_self_test(temporary_paths, node)
        document = {
            "kind": RUNTIME_KIND,
            "schema_version": RUNTIME_VERSION,
            "cli_version": CLI_VERSION,
            "git_head": CLI_GIT_HEAD,
            "cli_sha256": CLI_SHA256,
            "cli_manifest_sha256": CLI_MANIFEST_SHA256,
            "codedapp_source_sha256": CODEDAPP_SHA256,
            "codedapp_guarded_sha256": CODEDAPP_GUARDED_SHA256,
            "codedapp_manifest_sha256": CODEDAPP_MANIFEST_SHA256,
            "orchestrator_sha256": ORCHESTRATOR_SHA256,
            "orchestrator_manifest_sha256": ORCHESTRATOR_MANIFEST_SHA256,
            "patch_contract_sha256": _patch_contract_hash(),
            "created_at": core._utc_now(),
        }
        document["manifest_hash"] = core._document_hash(document, "manifest_hash")
        _atomic_private_json(temporary_paths["manifest"], document, overwrite=False)
        if paths["root"].exists():
            core._fail("Concurrent POC runtime provisioning detected.")
        os.replace(temporary, paths["root"])
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return _validate_runtime(root, node)


def _load_project(root: Path, app_type: str) -> dict[str, Any]:
    pyproject, _ = core._load_pyproject(root / "pyproject.toml")
    metadata = core._project_metadata(pyproject)
    package_name = metadata["name"]
    core._parse_semver(metadata["version"], "project version")
    action_path = root / "action-schema.json"
    if app_type == "action":
        if action_path.is_symlink() or not action_path.is_file():
            core._fail("Action POC configuration requires a regular action-schema.json.")
        try:
            action_payload = action_path.read_bytes()
            testing._audit_payload(action_payload)
            action_schema = json.loads(action_payload.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            core._fail("action-schema.json must be valid UTF-8 JSON.")
        if not isinstance(action_schema, dict) or not action_schema:
            core._fail("action-schema.json must be a non-empty object.")
        uipath = None
    else:
        if action_path.exists():
            core._fail("Web POC configuration conflicts with action-schema.json.")
        uipath = core._load_uipath_json(root / "uipath.json")
    return {
        "package_name": package_name,
        "version": metadata["version"],
        "author": metadata["author"],
        "uipath": uipath,
    }


def _profile_status(runtime: dict[str, Any], node: dict[str, str], profile: str, cwd: Path) -> dict[str, Any]:
    output = _run_read(
        [node["executable"], runtime["cli"], "--profile", profile, "login", "status", "--output", "json"],
        cwd, _safe_environment(), "CLI_PROFILE_STATUS_FAILED",
    )
    try:
        document = json.loads(output)
    except json.JSONDecodeError:
        core._fail("UiPath CLI profile status did not return valid JSON.")
    if not isinstance(document, dict):
        core._fail("UiPath CLI profile status must be an object.")
    state = core._find_mapping_value(document, {"status", "loginstatus"})
    if not isinstance(state, str) or state.lower().replace(" ", "") not in {"loggedin", "authenticated"}:
        core._fail("UiPath CLI profile is not logged in.")
    return document


def _status_value(status: dict[str, Any], names: set[str], label: str) -> str:
    value = core._find_mapping_value(status, names)
    return _require_text(value, f"profile {label}")


def _folder_rows(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        rows = document
    elif isinstance(document, dict):
        rows = core._find_mapping_value(document, {"data", "items", "value"})
    else:
        rows = None
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        core._fail("Folder listing returned an unsupported JSON shape.")
    return rows


def _resolve_folder(runtime: dict[str, Any], node: dict[str, str], profile: str, selector: str, cwd: Path) -> dict[str, str]:
    output = _run_read(
        [node["executable"], runtime["cli"], "--profile", profile, "or", "folders", "list", "--output", "json"],
        cwd, _safe_environment(), "FOLDER_LIST_FAILED",
    )
    try:
        rows = _folder_rows(json.loads(output))
    except json.JSONDecodeError:
        core._fail("Folder listing did not return valid JSON.")
    matches = []
    for row in rows:
        key = core._find_mapping_value(row, {"key"})
        name = core._find_mapping_value(row, {"name"})
        path = core._find_mapping_value(row, {"path"})
        if (
            isinstance(key, str)
            and core.GUID_RE.fullmatch(key)
            and (
                key.lower() == selector.lower()
                or (isinstance(name, str) and name == selector)
                or (isinstance(path, str) and path == selector)
            )
        ):
            matches.append(row)
    unique = {str(core._find_mapping_value(row, {"key"})).lower(): row for row in matches}
    if len(unique) != 1:
        core._fail("--folder must resolve to exactly one accessible folder by GUID, Name, or Path.")
    row = next(iter(unique.values()))
    return {
        "folder_key": _require_guid(core._find_mapping_value(row, {"key"}), "folder key"),
        "folder_name": _require_text(core._find_mapping_value(row, {"name"}), "folder name"),
        "folder_path": str(core._find_mapping_value(row, {"path"}) or core._find_mapping_value(row, {"name"})),
        "folder_type": str(core._find_mapping_value(row, {"type"}) or "Unknown"),
    }


def _web_binding(project: dict[str, Any], environment: str, organization_name: str) -> dict[str, str]:
    document = project["uipath"]
    assert isinstance(document, dict)
    client_id = _require_guid(document.get("clientId"), "uipath.json clientId")
    if document.get("baseUrl") != TARGETS[environment]["api_url"]:
        core._fail("uipath.json baseUrl does not match the configured environment.")
    scope = document.get("scope")
    if not isinstance(scope, str) or not {"openid", "profile"}.issubset(set(scope.split())):
        core._fail("uipath.json must request openid and profile.")
    redirect = _require_text(document.get("redirectUri"), "uipath.json redirectUri")
    parsed = urlparse(redirect)
    expected_host = TARGETS[environment]["host"](organization_name)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.scheme != "https" or parsed.hostname != expected_host or len(parts) != 1 or parsed.query or parsed.fragment:
        core._fail("uipath.json redirectUri does not match the exact environment and organization route.")
    route = _require_route(parts[0], "uipath.json route")
    return {"client_id": client_id, "path_name": route}


def _configure(args: argparse.Namespace) -> Path:
    root = _project_root(args.project_root)
    environment_name = _require_text(args.environment, "--environment")
    if environment_name not in TARGETS:
        core._fail("--environment must be alpha, staging, or production.")
    profile = _require_text(args.profile, "--profile")
    if re.fullmatch(r"[A-Za-z0-9._-]+", profile) is None:
        core._fail("--profile contains unsupported characters.")
    node = _node_runtime(args.node_executable)
    poc_root = _poc_root()
    runtime = _provision_runtime(poc_root, node, args.npm_executable)
    status = _profile_status(runtime, node, profile, root)
    control_plane = _status_value(status, {"baseurl"}, "control plane")
    if control_plane.rstrip("/") != TARGETS[environment_name]["control_plane_url"]:
        core._fail("UiPath CLI profile control plane does not match --environment.")
    organization_id = _require_guid(_status_value(status, {"organizationid", "organizationuid"}, "organization ID"), "profile organization ID")
    tenant_id = _require_guid(_status_value(status, {"tenantid", "tenantuid"}, "tenant ID"), "profile tenant ID")
    organization_name = _status_value(status, {"organization", "organizationname", "orgname"}, "organization name").lower()
    tenant_name = _status_value(status, {"tenant", "tenantname"}, "tenant name")
    if re.fullmatch(r"[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?", organization_name) is None:
        core._fail("Profile organization name is not a valid UiPath host segment.")
    folder = _resolve_folder(runtime, node, profile, _require_text(args.folder, "--folder"), root)
    app_type = _require_text(args.app_type, "--app-type")
    project = _load_project(root, app_type)
    app_name = _require_text(args.app_name or project["package_name"], "app name")
    if app_type == "web":
        binding = _web_binding(project, environment_name, organization_name)
        if args.path_name and _require_route(args.path_name, "--path-name") != binding["path_name"]:
            core._fail("--path-name conflicts with uipath.json redirectUri.")
        if args.client_id and _require_guid(args.client_id, "--client-id") != binding["client_id"]:
            core._fail("--client-id conflicts with uipath.json.")
    else:
        binding = {
            "client_id": _require_guid(args.client_id, "--client-id") if args.client_id else None,
            "path_name": _require_route(args.path_name, "--path-name") if args.path_name else _slug(app_name),
        }
    tags = core._normalize_tags(args.tags or "poc,internal", "--tags")
    document = {
        "kind": CONFIG_KIND,
        "schema_version": CONFIG_VERSION,
        "project_key": _project_key(root),
        "project_root": str(root),
        "environment": environment_name,
        "control_plane_url": TARGETS[environment_name]["control_plane_url"],
        "api_url": TARGETS[environment_name]["api_url"],
        "organization_id": organization_id,
        "organization_name": organization_name,
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        **folder,
        "cli_profile": profile,
        "cli_profile_hash": core._hash_json({
            "profile": profile, "environment": environment_name,
            "control_plane_url": control_plane, "organization_id": organization_id,
            "tenant_id": tenant_id,
        }),
        "app_type": app_type,
        "package_name": project["package_name"],
        "app_name": app_name,
        "path_name": binding["path_name"],
        "client_id": binding["client_id"],
        "tags": tags,
        "node_executable": node["executable"],
        "node_executable_sha256": node["sha256"],
        "node_version": node["version"],
        "runtime_manifest": runtime["manifest"],
        "runtime_manifest_sha256": runtime["manifest_sha256"],
        "configured_at": core._utc_now(),
    }
    document["config_hash"] = core._document_hash(document, "config_hash")
    path = _config_path(root)
    _atomic_private_json(path, document, overwrite=args.replace)
    return path


def _load_config(root: Path) -> tuple[Path, dict[str, Any]]:
    path = _config_path(root)
    document = _load_private_json(path, "POC target configuration")
    if set(document) != CONFIG_FIELDS or document.get("kind") != CONFIG_KIND or document.get("schema_version") != CONFIG_VERSION:
        core._fail("POC target configuration shape is unsupported; run configure again.")
    if core._document_hash(document, "config_hash") != document.get("config_hash"):
        core._fail("POC target configuration hash is invalid.")
    if document.get("project_root") != str(root) or document.get("project_key") != _project_key(root):
        core._fail("POC target configuration belongs to a different project path.")
    if document.get("environment") not in TARGETS:
        core._fail("POC target environment is unsupported.")
    return path, document


def _configured_node(config: dict[str, Any]) -> dict[str, str]:
    node = {
        "executable": _require_text(config.get("node_executable"), "configured Node.js"),
        "sha256": _require_text(config.get("node_executable_sha256"), "configured Node.js digest"),
        "version": _require_text(config.get("node_version"), "configured Node.js version"),
    }
    core._validate_hash(node["sha256"], "configured Node.js digest")
    if core._hash_file(Path(node["executable"]), "configured Node.js") != node["sha256"]:
        core._fail("Configured Node.js changed; run configure again.")
    return node


def _revalidate_target(root: Path, config: dict[str, Any], runtime: dict[str, Any], node: dict[str, str]) -> dict[str, Any]:
    if config["control_plane_url"] != TARGETS[config["environment"]]["control_plane_url"] or config["api_url"] != TARGETS[config["environment"]]["api_url"]:
        core._fail("Configured target mapping is invalid.")
    project = _load_project(root, config["app_type"])
    if project["package_name"] != config["package_name"]:
        core._fail("Project package name drifted; run configure again.")
    if config["app_type"] == "web":
        binding = _web_binding(project, config["environment"], config["organization_name"])
        if binding != {"client_id": config["client_id"], "path_name": config["path_name"]}:
            core._fail("Web OAuth or route binding drifted; run configure again.")
    status = _profile_status(runtime, node, config["cli_profile"], root)
    comparisons = (
        (config["control_plane_url"], {"baseurl"}, "control plane"),
        (config["organization_id"], {"organizationid", "organizationuid"}, "organization ID"),
        (config["organization_name"], {"organization", "organizationname", "orgname"}, "organization name"),
        (config["tenant_id"], {"tenantid", "tenantuid"}, "tenant ID"),
        (config["tenant_name"], {"tenant", "tenantname"}, "tenant name"),
    )
    for expected, names, label in comparisons:
        if _status_value(status, names, label).lower().rstrip("/") != expected.lower().rstrip("/"):
            core._fail(f"UiPath CLI profile {label} drifted; run configure again.")
    folder = _resolve_folder(runtime, node, config["cli_profile"], config["folder_key"], root)
    for key in ("folder_key", "folder_name", "folder_path", "folder_type"):
        if folder[key] != config[key]:
            core._fail("Configured folder identity drifted; run configure again.")
    return project


def _authorize(args: argparse.Namespace, environment: str, classification: str) -> dict[str, Any]:
    if not args.execute:
        core._fail("POC deployment requires explicit --execute.")
    if environment == "production" and not args.production_execute:
        core._fail("Production POC deployment requires explicit --production-execute.")
    if classification == "customer" and not args.customer_data_approved:
        core._fail("Customer-data POC deployment requires explicit --customer-data-approved.")
    return {
        "execute": True,
        "production_execute": bool(args.production_execute),
        "customer_data_approved": bool(args.customer_data_approved),
        "data_classification": classification,
        "current_request_only": True,
    }


def _package_manager(root: Path) -> tuple[str, list[str]]:
    candidates = []
    for filename, executable in (
        ("package-lock.json", "npm"), ("npm-shrinkwrap.json", "npm"),
        ("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"),
    ):
        if (root / filename).is_file():
            candidates.append(executable)
    if len(candidates) != 1:
        core._fail("Project must contain exactly one npm, pnpm, or Yarn lockfile.")
    executable = shutil.which(candidates[0])
    if not executable:
        core._fail(f"Configured package manager {candidates[0]} is unavailable.")
    path = Path(executable).resolve(strict=True)
    if path.is_symlink() or not path.is_file() or not os.access(path, os.X_OK):
        core._fail("Package manager must be an executable regular file.")
    return str(path), [str(path), "run", "build"]


def _build(root: Path) -> Path:
    package_path = root / "package.json"
    if package_path.is_symlink() or not package_path.is_file():
        core._fail("POC deployment requires a regular package.json.")
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        core._fail("package.json must be valid UTF-8 JSON.")
    build_script = package.get("scripts", {}).get("build") if isinstance(package, dict) else None
    if not isinstance(build_script, str) or not build_script.strip():
        core._fail("package.json must declare a non-empty build script.")
    if not (root / "node_modules").is_dir():
        core._fail("Build dependencies are missing; install them before POC deployment.")
    _, command = _package_manager(root)
    try:
        subprocess.run(
            command, cwd=root, env=_build_environment(), check=True,
            capture_output=True, text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit("POC app build failed; no UiPath write was attempted.") from exc
    dist = root / "dist"
    if not dist.is_dir() and (root / "app" / "dist").is_dir():
        dist = root / "app" / "dist"
    if dist.is_symlink() or not dist.is_dir() or not (dist / "index.html").is_file():
        core._fail("Fresh build did not produce a regular dist/index.html.")
    testing._audit_dist(dist)
    return dist


def _semver_tuple(value: str) -> tuple[int, int, int, tuple[tuple[int, Any], ...]]:
    parsed = core._parse_semver(value, "remote package version")
    prerelease = getattr(parsed, "prerelease", None)
    identifiers = []
    if prerelease:
        for item in str(prerelease).split("."):
            identifiers.append((0, int(item)) if item.isdigit() else (1, item))
    return (parsed.major, parsed.minor, parsed.patch, tuple(identifiers))


def _semver_greater(left: str, right: str) -> bool:
    left_match = core.SEMVER_RE.fullmatch(left)
    right_match = core.SEMVER_RE.fullmatch(right)
    if left_match is None or right_match is None:
        core._fail("Version comparison requires valid SemVer values.")
    left_core = tuple(int(left_match.group(i)) for i in (1, 2, 3))
    right_core = tuple(int(right_match.group(i)) for i in (1, 2, 3))
    if left_core != right_core:
        return left_core > right_core
    left_pre, right_pre = left_match.group(4), right_match.group(4)
    if left_pre is None:
        return right_pre is not None
    if right_pre is None:
        return False
    left_parts, right_parts = left_pre.split("."), right_pre.split(".")
    for left_part, right_part in zip(left_parts, right_parts):
        if left_part == right_part:
            continue
        if left_part.isdigit() and right_part.isdigit():
            return int(left_part) > int(right_part)
        if left_part.isdigit() != right_part.isdigit():
            return not left_part.isdigit()
        return left_part > right_part
    return len(left_parts) > len(right_parts)


def _next_version(local: str, remote: list[str]) -> str:
    core._parse_semver(local, "local project version")
    for value in remote:
        core._parse_semver(value, "remote package version")
    if local not in remote and all(_semver_greater(local, value) for value in remote):
        return local
    if not remote:
        return local
    highest = remote[0]
    for value in remote[1:]:
        if _semver_greater(value, highest):
            highest = value
    match = core.SEMVER_RE.fullmatch(highest)
    assert match is not None
    major, minor, patch = (int(match.group(i)) for i in (1, 2, 3))
    prerelease = match.group(4)
    if prerelease:
        parts = prerelease.split(".")
        if parts[-1].isdigit():
            parts[-1] = str(int(parts[-1]) + 1)
        else:
            parts.append("1")
        return f"{major}.{minor}.{patch}-" + ".".join(parts)
    return f"{major}.{minor}.{patch + 1}"


def _app_url(config: dict[str, Any]) -> str | None:
    if config["app_type"] == "action":
        return None
    host = TARGETS[config["environment"]]["host"](config["organization_name"])
    return f"https://{host}/{config['path_name']}"


def _guard_config(config: dict[str, Any], version: str) -> dict[str, Any]:
    document: dict[str, Any] = {
        "appName": config["package_name"],
        "displayName": config["app_name"],
        "appVersion": version,
        "appType": "Action" if config["app_type"] == "action" else "Web",
        "personalWorkspace": False,
    }
    app_url = _app_url(config)
    if app_url is not None:
        document["appUrl"] = app_url
    return document


def _write_guard_config(workspace: Path, config: dict[str, Any], version: str) -> Path:
    path = workspace / core.APP_CONFIG_RELATIVE_PATH
    _atomic_private_json(path, _guard_config(config, version), overwrite=True)
    return path


def _base_guard_command(runtime: dict[str, Any], node: dict[str, str], config: dict[str, Any], version: str, mode: str) -> list[str]:
    command = [
        node["executable"], runtime["cli"], "codedapp", "deploy",
        "--version", version,
        "--path-name", config["path_name"],
        "--tags", ",".join(config["tags"]),
        "--base-url", config["control_plane_url"],
        "--org-id", config["organization_id"],
        "--org-name", config["organization_name"],
        "--tenant-id", config["tenant_id"],
        "--folder-key", config["folder_key"],
        "--profile", config["cli_profile"],
        "--poc-mode", mode,
        "--output", "json",
    ]
    if config["app_type"] == "web":
        command[6:6] = ["--client-id", config["client_id"]]
    return command


def _guard_command(runtime: dict[str, Any], node: dict[str, str], config: dict[str, Any], candidate: dict[str, Any], mode: str, published: dict[str, Any] | None = None) -> list[str]:
    command = _base_guard_command(runtime, node, config, candidate["version"], mode)
    output_index = command.index("--output")
    guard = []
    if mode.startswith("upgrade-"):
        guard.extend([
            "--poc-expected-deployment-id", candidate["deployment_id"],
            "--poc-expected-current-version", candidate["version"] if mode == "upgrade-post" else candidate["current_version"],
            "--poc-expected-route-name", config["path_name"],
        ])
    if mode in {"create-post", "upgrade-candidate", "upgrade-execute", "upgrade-post"}:
        if not published:
            core._fail("Guarded deployment requires exact published candidate identity.")
        guard.extend([
            "--poc-expected-system-name", published["system_name"],
            "--poc-expected-deploy-version", str(published["deploy_version"]),
        ])
    if mode == "create-post":
        guard.extend(["--poc-expected-deployment-id", candidate["deployment_id"]])
    command[output_index:output_index] = guard
    return command


def _inspect(runtime: dict[str, Any], node: dict[str, str], config: dict[str, Any], workspace: Path, version: str) -> dict[str, Any]:
    output = _run_read(
        _base_guard_command(runtime, node, config, version, "inspect"),
        workspace, _safe_environment(), "REMOTE_INSPECT_FAILED",
    )
    try:
        document = testing._extract_json_envelope(output, "REMOTE_INSPECT_INVALID_JSON")
    except testing.TestingCommandError:
        core._fail("POC remote inspection returned invalid JSON.")
    data = document.get("Data")
    required = {"Message", "AppType", "AppName", "RouteName", "AppUrl", "RouteAvailable", "Deployment", "PublishedVersions", "Operation"}
    if document.get("Result") != "Success" or document.get("Code") != "DeployCompleted" or not isinstance(data, dict) or set(data) != required:
        core._fail("POC remote inspection returned an unsupported result.")
    if data.get("Operation") != "poc_inspect" or data.get("AppType") != ("Action" if config["app_type"] == "action" else "Web") or data.get("AppName") != config["app_name"] or data.get("RouteName") != config["path_name"] or data.get("AppUrl") != _app_url(config):
        core._fail("POC remote inspection does not match the configured app.")
    deployment = data.get("Deployment")
    if deployment is not None:
        if not isinstance(deployment, dict) or set(deployment) != {"id", "title", "routingName", "semVersion"}:
            core._fail("POC remote deployment observation is invalid.")
        deployment["id"] = _require_guid(deployment["id"], "remote deployment ID")
        core._parse_semver(_require_text(deployment["semVersion"], "remote deployed version"), "remote deployed version")
    versions = data.get("PublishedVersions")
    if not isinstance(versions, list):
        core._fail("POC published version observation is invalid.")
    normalized = []
    seen = set()
    for item in versions:
        if not isinstance(item, dict) or set(item) != {"version", "systemName", "deployVersion"}:
            core._fail("POC published candidate observation is invalid.")
        version_value = _require_text(item["version"], "published version")
        core._parse_semver(version_value, "published version")
        system_name = _require_text(item["systemName"], "published system name")
        if core.APP_SYSTEM_NAME_RE.fullmatch(system_name) is None or not isinstance(item["deployVersion"], int) or item["deployVersion"] < 1:
            core._fail("POC published candidate identity is invalid.")
        key = (version_value, system_name, item["deployVersion"])
        if key in seen:
            continue
        seen.add(key)
        normalized.append({"version": version_value, "system_name": system_name, "deploy_version": item["deployVersion"]})
    return {"route_available": data["RouteAvailable"], "deployment": deployment, "published_versions": normalized}


def _published_for(observation: dict[str, Any], version: str) -> dict[str, Any]:
    matches = [item for item in observation["published_versions"] if item["version"] == version]
    if len(matches) != 1:
        core._fail("Exact published candidate version did not resolve uniquely.")
    return matches[0]


def _receipt_path(root: Path, requested: str | None, suffix: str = "") -> Path:
    if requested:
        path = Path(requested).expanduser().resolve(strict=False)
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = _poc_root() / "receipts" / f"{stamp}-{_project_key(root)[:12]}{suffix}.json"
    if path.exists() or path.is_symlink():
        core._fail("POC receipt output already exists; replay is prohibited.")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def _reserve(path: Path) -> dict[str, str]:
    reservation = path.with_name(f".{path.name}.reservation")
    try:
        descriptor = os.open(reservation, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        core._fail("POC receipt is already reserved.")
    payload = core._hash_json({"receipt": str(path), "created_at": core._utc_now()})
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(payload + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return {"path": str(reservation), "sha256": core._hash_file(reservation, "POC receipt reservation")}


def _claim(config: dict[str, Any], candidate: dict[str, Any], source_hash: str | None = None) -> tuple[Path, dict[str, Any]]:
    key = core._hash_json({
        "environment": config["environment"], "organization_id": config["organization_id"],
        "tenant_id": config["tenant_id"], "folder_key": config["folder_key"],
        "app_name": config["app_name"], "intent": candidate["intent"],
        "version": candidate["version"], "source_hash": source_hash,
    })
    path = _poc_root() / "claims" / f"{key.removeprefix('sha256:')}.json"
    document = {"kind": "uipcodedappdeploy.poc-claim", "schema_version": "1.0", "key": key, "created_at": core._utc_now()}
    document["claim_hash"] = core._document_hash(document, "claim_hash")
    if path.exists():
        core._fail("An exact POC candidate claim already exists; replay is prohibited.")
    _atomic_private_json(path, document, overwrite=False)
    return path, document


def _release_prewrite_claim(path: Path) -> None:
    if path.exists() and not path.is_symlink():
        path.unlink()


def _new_receipt(config: dict[str, Any], authorization: dict[str, Any], candidate: dict[str, Any], runtime: dict[str, Any], receipt_path: Path, reservation: dict[str, str], workspace: Path, claim_path: Path, *, recovery_source: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "kind": RECEIPT_KIND,
        "schema_version": RECEIPT_VERSION,
        "helper_sha256": core._hash_file(Path(__file__), "POC helper"),
        "policy_version": POLICY_VERSION,
        "authorization": authorization,
        "target": {key: copy.deepcopy(config[key]) for key in (
            "environment", "control_plane_url", "api_url", "organization_id", "organization_name",
            "tenant_id", "tenant_name", "folder_key", "folder_name", "folder_path", "folder_type",
            "cli_profile", "cli_profile_hash", "app_type", "package_name", "app_name", "path_name",
            "client_id", "tags", "config_hash",
        )},
        "candidate": copy.deepcopy(candidate),
        "runtime": copy.deepcopy(runtime),
        "evidence": {
            "project_root": config["project_root"],
            "workspace": str(workspace),
            "receipt": str(receipt_path),
        },
        "reservation": reservation,
        "claim": {"path": str(claim_path), "retained": True},
        "recovery_source": recovery_source,
        "status": "in_progress",
        "external_write_started": False,
        "started_at": core._utc_now(),
        "updated_at": core._utc_now(),
        "stages": [],
        "observations": {"prewrite": None, "published_candidate": None, "postwrite": None},
        "verification": {
            "route_verified": None,
            "configuration_verified": False,
            "action_center_rendering": "pending" if config["app_type"] == "action" else None,
            "action_center_submission": "pending" if config["app_type"] == "action" else None,
            "action_center_write_back": "pending" if config["app_type"] == "action" else None,
        },
        "policy": {"production_eligible": False, "release_evidence": False},
        "redaction": copy.deepcopy(REDACTION),
    }


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    if receipt.get("policy") != {
        "production_eligible": False,
        "release_evidence": False,
    }:
        core._fail("POC receipt may not claim production or release evidence.")
    authorization = receipt.get("authorization")
    target = receipt.get("target")
    if not isinstance(authorization, dict) or not isinstance(target, dict):
        core._fail("POC receipt authorization or target is invalid.")
    if target.get("environment") == "production" and authorization.get("production_execute") is not True:
        core._fail("Production POC receipt lacks current-request authorization.")
    if authorization.get("data_classification") == "customer" and authorization.get("customer_data_approved") is not True:
        core._fail("Customer-data POC receipt lacks current-request approval.")
    receipt["updated_at"] = core._utc_now()
    receipt["receipt_hash"] = core._document_hash(receipt, "receipt_hash")
    testing._audit_payload(json.dumps(receipt, sort_keys=True).encode("utf-8"))
    _atomic_private_json(path, receipt, overwrite=path.exists())


def _stage(receipt: dict[str, Any], path: Path, name: str, operation: str, function: Any, *, external_write: bool = False, failure_status: str = "failed_prewrite", failure_code: str = "LOCAL_PREFLIGHT_FAILED") -> Any:
    record = {"name": name, "operation": operation, "status": "running", "started_at": core._utc_now(), "finished_at": None, "error_code": None}
    receipt["stages"].append(record)
    if external_write:
        receipt["external_write_started"] = True
    _write_receipt(path, receipt)
    try:
        result = function()
    except (Exception, SystemExit, KeyboardInterrupt):
        record["status"] = "indeterminate" if external_write else "failed"
        record["finished_at"] = core._utc_now()
        record["error_code"] = failure_code
        receipt["status"] = failure_status
        _write_receipt(path, receipt)
        raise
    record["status"] = "succeeded"
    record["finished_at"] = core._utc_now()
    _write_receipt(path, receipt)
    return result


def _copy_candidate(dist: Path, root: Path, config: dict[str, Any], version: str, receipt_path: Path) -> tuple[Path, Path, dict[str, str]]:
    workspace = receipt_path.parent / f"{receipt_path.stem}.workspace"
    if workspace.exists():
        core._fail("POC evidence workspace already exists; replay is prohibited.")
    workspace.mkdir(mode=0o700)
    copied = workspace / "dist"
    shutil.copytree(dist, copied, symlinks=False)
    if testing._directory_digest(dist) != testing._directory_digest(copied):
        core._fail("Fresh dist changed while creating POC evidence.")
    _write_guard_config(workspace, config, version)
    if config["app_type"] == "web":
        shutil.copy2(root / "uipath.json", workspace / "uipath.json")
    else:
        shutil.copy2(root / "action-schema.json", workspace / "action-schema.json")
    evidence = {
        "dist_sha256": testing._directory_digest(copied),
        "app_config_sha256": core._hash_file(workspace / core.APP_CONFIG_RELATIVE_PATH, "POC guard config"),
    }
    return workspace, copied, evidence


def _pack(runtime: dict[str, Any], node: dict[str, str], config: dict[str, Any], project: dict[str, Any], workspace: Path, dist: Path, version: str) -> tuple[Path, str, str]:
    package_dir = workspace / ".uipath"
    package_dir.mkdir(exist_ok=True)
    command = [
        node["executable"], runtime["cli"], "codedapp", "pack", str(dist),
        "--name", config["package_name"], "--version", version,
        "--output", str(package_dir), "--author", project["author"],
        "--main-file", "index.html", "--content-type", "webapp",
    ]
    _run_write(command, workspace, _safe_environment(), "PACK_FAILED")
    package_path = package_dir / f"{config['package_name']}.{version}.nupkg"
    content_digest, file_digest = core._package_evidence(package_path, package_name=config["package_name"], main_file="index.html")
    testing._audit_package_archive(package_path)
    return package_path, content_digest, file_digest


def _publish(runtime: dict[str, Any], node: dict[str, str], config: dict[str, Any], workspace: Path, version: str) -> dict[str, Any]:
    command = [
        node["executable"], runtime["cli"], "codedapp", "publish",
        "--name", config["package_name"], "--version", version,
        "--type", "Action" if config["app_type"] == "action" else "Web",
        "--uipath-dir", str(workspace / ".uipath"),
        "--base-url", config["control_plane_url"], "--org-id", config["organization_id"],
        "--tenant-id", config["tenant_id"], "--tenant-name", config["tenant_name"],
        "--profile", config["cli_profile"], "--output", "json",
    ]
    document = _run_write(command, workspace, _safe_environment(), "PUBLISH_INDETERMINATE")
    if document.get("Code") != "PublishCompleted":
        raise PocCommandError("PUBLISH_INDETERMINATE")
    data = document.get("Data")
    if not isinstance(data, dict) or data.get("PackageName") != config["package_name"] or data.get("PackageVersion") != version or data.get("AppType") != ("Action" if config["app_type"] == "action" else "Web"):
        raise PocCommandError("PUBLISH_INDETERMINATE")
    return document


def _bind_published_config(workspace: Path, config: dict[str, Any], version: str) -> str:
    expected = core._expected_app_config_binding(
        package_name=config["package_name"],
        app_name=config["app_name"],
        app_version=version,
        app_type="Action" if config["app_type"] == "action" else "Web",
    )
    if expected is not None:
        core._bind_app_config(
            workspace,
            {"new_version": version},
            {
                "package_name": config["package_name"],
                "app_name": config["app_name"],
                "app_type": expected["appType"],
                "app_config_binding_hash": core._hash_json(expected),
            },
        )
    return core._hash_file(
        workspace / core.APP_CONFIG_RELATIVE_PATH,
        "published POC app config",
    )


def _validate_intent(observation: dict[str, Any], config: dict[str, Any], intent: str) -> dict[str, Any]:
    deployment = observation["deployment"]
    if intent == "create":
        if deployment is not None or observation["route_available"] is not True:
            core._fail("Create intent requires an absent app identity and available route.")
        return {"deployment_id": None, "current_version": None}
    if deployment is None:
        core._fail("Upgrade intent requires exactly one existing deployment.")
    if deployment["title"] not in {config["app_name"], config["package_name"]} or deployment["routingName"] != config["path_name"]:
        core._fail("Existing deployment title or route does not match the configured target.")
    return {"deployment_id": deployment["id"], "current_version": deployment["semVersion"]}


def _verify_config(workspace: Path, config: dict[str, Any], candidate: dict[str, Any]) -> str:
    path = workspace / core.APP_CONFIG_RELATIVE_PATH
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        core._fail("Post-deploy app config is invalid.")
    expected_type = "Action" if config["app_type"] == "action" else "Web"
    if document.get("appName") != config["package_name"] or document.get("displayName") != config["app_name"] or document.get("appVersion") != candidate["version"] or document.get("appType") != expected_type or document.get("personalWorkspace") is not False:
        core._fail("Post-deploy app config does not match the exact POC candidate.")
    if config["app_type"] == "web" and document.get("appUrl") != _app_url(config):
        core._fail("Post-deploy Web app config route does not match.")
    if config["app_type"] == "action" and document.get("appUrl") not in {None, ""}:
        core._fail("Post-deploy Action app config must not claim a Web route.")
    return core._hash_file(path, "post-deploy POC app config")


def _execute_deploy(args: argparse.Namespace) -> Path:
    root = _project_root(args.project_root)
    _, config = _load_config(root)
    classification = _require_text(args.data_classification, "--data-classification")
    authorization = _authorize(args, config["environment"], classification)
    node = _configured_node(config)
    runtime = _validate_runtime(_poc_root(), node)
    if (
        runtime["manifest"] != config["runtime_manifest"]
        or runtime["manifest_sha256"] != config["runtime_manifest_sha256"]
    ):
        core._fail("Configured POC runtime binding drifted; run configure again.")
    project = _revalidate_target(root, config, runtime, node)
    dist = _build(root)
    receipt_path = _receipt_path(root, args.receipt_output)
    reservation = _reserve(receipt_path)
    provisional_version = project["version"]
    workspace, copied_dist, evidence = _copy_candidate(dist, root, config, provisional_version, receipt_path)
    initial = _inspect(runtime, node, config, workspace, provisional_version)
    identity = _validate_intent(initial, config, args.intent)
    version = _next_version(project["version"], [item["version"] for item in initial["published_versions"]])
    _write_guard_config(workspace, config, version)
    package_path, content_digest, file_digest = _pack(runtime, node, config, project, workspace, copied_dist, version)
    evidence.update({
        "app_config_sha256": core._hash_file(workspace / core.APP_CONFIG_RELATIVE_PATH, "POC guard config"),
        "package_content_sha256": content_digest,
        "package_file_sha256": file_digest,
    })
    candidate = {
        "intent": args.intent,
        "version": version,
        "local_version": project["version"],
        "deployment_id": identity["deployment_id"],
        "current_version": identity["current_version"],
        "system_name": None,
        "deploy_version": None,
        "evidence": evidence,
        "package_path": str(package_path),
    }
    claim_path, _ = _claim(config, candidate)
    receipt = _new_receipt(config, authorization, candidate, runtime, receipt_path, reservation, workspace, claim_path)
    _write_receipt(receipt_path, receipt)
    try:
        receipt["observations"]["prewrite"] = initial
        _stage(
            receipt, receipt_path, "pre_publish_guard", "external_read",
            lambda: _validate_intent(_inspect(runtime, node, config, workspace, version), config, args.intent),
            failure_code="PRE_PUBLISH_GUARD_FAILED",
        )
        _stage(
            receipt, receipt_path, "publish", "external_write",
            lambda: _publish(runtime, node, config, workspace, version),
            external_write=True, failure_status="publish_indeterminate", failure_code="PUBLISH_INDETERMINATE",
        )
        receipt["status"] = "published_not_deployed"
        _write_receipt(receipt_path, receipt)
        candidate["evidence"]["app_config_sha256"] = _stage(
            receipt, receipt_path, "app_config_bind", "local_write",
            lambda: _bind_published_config(workspace, config, version),
            failure_status="published_not_deployed", failure_code="APP_CONFIG_BIND_FAILED",
        )
        receipt["candidate"] = copy.deepcopy(candidate)
        _write_receipt(receipt_path, receipt)
        post_publish = _stage(
            receipt, receipt_path, "published_candidate_guard", "external_read",
            lambda: _inspect(runtime, node, config, workspace, version),
            failure_status="published_not_deployed", failure_code="PUBLISHED_CANDIDATE_GUARD_FAILED",
        )
        post_identity = _validate_intent(post_publish, config, args.intent)
        if args.intent == "upgrade" and (
            post_identity["deployment_id"] != candidate["deployment_id"]
            or post_identity["current_version"] != candidate["current_version"]
        ):
            core._fail("Existing deployment changed after publication.")
        published = _published_for(post_publish, version)
        receipt["observations"]["published_candidate"] = published
        candidate["system_name"] = published["system_name"]
        candidate["deploy_version"] = published["deploy_version"]
        receipt["candidate"] = copy.deepcopy(candidate)
        _write_receipt(receipt_path, receipt)
        mode = "create-execute" if args.intent == "create" else "upgrade-execute"
        deploy_document = _stage(
            receipt, receipt_path, "deploy", "external_write",
            lambda: _run_write(_guard_command(runtime, node, config, candidate, mode, published), workspace, _safe_environment(), "DEPLOY_INDETERMINATE"),
            external_write=True, failure_status="deploy_indeterminate", failure_code="DEPLOY_INDETERMINATE",
        )
        receipt["status"] = "deployed_unverified"
        _write_receipt(receipt_path, receipt)
        if args.intent == "create":
            data = deploy_document.get("Data")
            if not isinstance(data, dict):
                core._fail("Create deployment returned no exact identity.")
            candidate["deployment_id"] = _require_guid(data.get("DeploymentId"), "created deployment ID")
            receipt["candidate"] = copy.deepcopy(candidate)
        post = _stage(
            receipt, receipt_path, "post_deploy_guard", "external_read",
            lambda: _inspect(runtime, node, config, workspace, version),
            failure_status="deployed_unverified", failure_code="POST_DEPLOY_GUARD_FAILED",
        )
        deployed = post["deployment"]
        if deployed is None or deployed["id"] != candidate["deployment_id"] or deployed["semVersion"] != version:
            core._fail("Post-deploy state does not match the exact POC candidate.")
        receipt["observations"]["postwrite"] = post
        if config["app_type"] == "web":
            _stage(
                receipt, receipt_path, "route_verify", "external_read",
                lambda: core._verify_url(_app_url(config), args.verify_timeout),
                failure_status="deployed_unverified", failure_code="ROUTE_VERIFY_FAILED",
            )
            receipt["verification"]["route_verified"] = True
        receipt["verification"]["post_deploy_app_config_sha256"] = _stage(
            receipt, receipt_path, "config_verify", "local_read",
            lambda: _verify_config(workspace, config, candidate),
            failure_status="deployed_unverified", failure_code="CONFIG_VERIFY_FAILED",
        )
        receipt["verification"]["configuration_verified"] = True
        receipt["status"] = "succeeded_poc_deploy"
        _write_receipt(receipt_path, receipt)
    except (Exception, SystemExit, KeyboardInterrupt):
        if not receipt["external_write_started"]:
            _release_prewrite_claim(claim_path)
            receipt["claim"]["retained"] = False
            _write_receipt(receipt_path, receipt)
        raise
    return receipt_path


def _load_source_receipt(path: Path) -> dict[str, Any]:
    receipt = _load_private_json(path, "source POC receipt")
    required = {
        "kind", "schema_version", "helper_sha256", "policy_version", "authorization",
        "target", "candidate", "runtime", "evidence", "reservation", "claim",
        "recovery_source", "status", "external_write_started", "started_at", "updated_at",
        "stages", "observations", "verification", "policy", "redaction", "receipt_hash",
    }
    if set(receipt) != required or receipt.get("kind") != RECEIPT_KIND or receipt.get("schema_version") != RECEIPT_VERSION:
        core._fail("Source POC receipt shape is unsupported.")
    if core._document_hash(receipt, "receipt_hash") != receipt.get("receipt_hash"):
        core._fail("Source POC receipt hash is invalid.")
    if receipt["recovery_source"] is not None or receipt["status"] not in {"publish_indeterminate", "published_not_deployed"}:
        core._fail("recover-published requires one unrecovered publish-stage POC receipt.")
    return receipt


def _recover_published(args: argparse.Namespace) -> Path:
    source_path = Path(_require_text(args.receipt, "--receipt")).expanduser().resolve(strict=True)
    source = _load_source_receipt(source_path)
    root = _project_root(source["evidence"].get("project_root"))
    _, config = _load_config(root)
    if any(source["target"].get(key) != config.get(key) for key in source["target"]):
        core._fail("Current POC target configuration does not match the source receipt.")
    classification = source["authorization"]["data_classification"]
    authorization = _authorize(args, config["environment"], classification)
    node = _configured_node(config)
    runtime = _validate_runtime(_poc_root(), node)
    if (
        runtime["manifest"] != config["runtime_manifest"]
        or runtime["manifest_sha256"] != config["runtime_manifest_sha256"]
    ):
        core._fail("Configured POC runtime binding drifted; run configure again.")
    _revalidate_target(root, config, runtime, node)
    workspace = Path(source["evidence"]["workspace"])
    if workspace.is_symlink() or not workspace.is_dir():
        core._fail("Retained POC evidence workspace is unavailable.")
    candidate = copy.deepcopy(source["candidate"])
    package_path = Path(candidate["package_path"])
    content_digest, file_digest = core._package_evidence(package_path, package_name=config["package_name"], main_file="index.html")
    if content_digest != candidate["evidence"]["package_content_sha256"] or file_digest != candidate["evidence"]["package_file_sha256"]:
        core._fail("Retained POC package bytes changed.")
    candidate["evidence"]["app_config_sha256"] = _bind_published_config(
        workspace, config, candidate["version"]
    )
    observation = _inspect(runtime, node, config, workspace, candidate["version"])
    published = _published_for(observation, candidate["version"])
    candidate["system_name"] = published["system_name"]
    candidate["deploy_version"] = published["deploy_version"]
    if candidate["intent"] == "create":
        _validate_intent(observation, config, "create")
    else:
        identity = _validate_intent(observation, config, "upgrade")
        if identity["deployment_id"] != candidate["deployment_id"] or identity["current_version"] != candidate["current_version"]:
            core._fail("Existing deployment changed after the source attempt.")
    receipt_path = _receipt_path(root, args.receipt_output, suffix="-recovery")
    reservation = _reserve(receipt_path)
    claim_path, _ = _claim(config, candidate, source["receipt_hash"])
    recovery_source = {
        "path": str(source_path),
        "receipt_hash": source["receipt_hash"],
        "file_sha256": core._hash_file(source_path, "source POC receipt"),
    }
    receipt = _new_receipt(config, authorization, candidate, runtime, receipt_path, reservation, workspace, claim_path, recovery_source=recovery_source)
    receipt["observations"]["prewrite"] = observation
    receipt["observations"]["published_candidate"] = published
    _write_receipt(receipt_path, receipt)
    mode = "create-execute" if candidate["intent"] == "create" else "upgrade-execute"
    try:
        document = _stage(
            receipt, receipt_path, "deploy", "external_write",
            lambda: _run_write(_guard_command(runtime, node, config, candidate, mode, published), workspace, _safe_environment(), "DEPLOY_INDETERMINATE"),
            external_write=True, failure_status="deploy_indeterminate", failure_code="DEPLOY_INDETERMINATE",
        )
        receipt["status"] = "deployed_unverified"
        if candidate["intent"] == "create":
            data = document.get("Data")
            candidate["deployment_id"] = _require_guid(data.get("DeploymentId") if isinstance(data, dict) else None, "created deployment ID")
            receipt["candidate"] = copy.deepcopy(candidate)
        post = _stage(
            receipt, receipt_path, "post_deploy_guard", "external_read",
            lambda: _inspect(runtime, node, config, workspace, candidate["version"]),
            failure_status="deployed_unverified", failure_code="POST_DEPLOY_GUARD_FAILED",
        )
        if post["deployment"] is None or post["deployment"]["id"] != candidate["deployment_id"] or post["deployment"]["semVersion"] != candidate["version"]:
            core._fail("Recovered deployment post-state does not match the candidate.")
        receipt["observations"]["postwrite"] = post
        if config["app_type"] == "web":
            _stage(receipt, receipt_path, "route_verify", "external_read", lambda: core._verify_url(_app_url(config), args.verify_timeout), failure_status="deployed_unverified", failure_code="ROUTE_VERIFY_FAILED")
            receipt["verification"]["route_verified"] = True
        receipt["verification"]["post_deploy_app_config_sha256"] = _stage(receipt, receipt_path, "config_verify", "local_read", lambda: _verify_config(workspace, config, candidate), failure_status="deployed_unverified", failure_code="CONFIG_VERIFY_FAILED")
        receipt["verification"]["configuration_verified"] = True
        receipt["status"] = "succeeded_poc_deploy"
        _write_receipt(receipt_path, receipt)
    except (Exception, SystemExit, KeyboardInterrupt):
        if not receipt["external_write_started"]:
            _release_prewrite_claim(claim_path)
        raise
    return receipt_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Configure and execute fast, non-release UiPath Coded App POC deployments.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    configure = subparsers.add_parser("configure")
    configure.add_argument("--project-root", required=True)
    configure.add_argument("--environment", choices=tuple(TARGETS), required=True)
    configure.add_argument("--profile", required=True)
    configure.add_argument("--folder", required=True)
    configure.add_argument("--app-type", choices=("web", "action"), required=True)
    configure.add_argument("--app-name")
    configure.add_argument("--path-name")
    configure.add_argument("--client-id")
    configure.add_argument("--tags")
    configure.add_argument("--node-executable")
    configure.add_argument("--npm-executable")
    configure.add_argument("--replace", action="store_true")

    deploy = subparsers.add_parser("deploy")
    deploy.add_argument("--project-root", required=True)
    deploy.add_argument("--intent", choices=("create", "upgrade"), required=True)
    deploy.add_argument("--data-classification", choices=("synthetic", "internal", "customer"), required=True)
    deploy.add_argument("--execute", action="store_true")
    deploy.add_argument("--production-execute", action="store_true")
    deploy.add_argument("--customer-data-approved", action="store_true")
    deploy.add_argument("--receipt-output")
    deploy.add_argument("--verify-timeout", type=int, default=15)

    recover_parser = subparsers.add_parser("recover-published")
    recover_parser.add_argument("--receipt", required=True)
    recover_parser.add_argument("--execute", action="store_true")
    recover_parser.add_argument("--production-execute", action="store_true")
    recover_parser.add_argument("--customer-data-approved", action="store_true")
    recover_parser.add_argument("--receipt-output")
    recover_parser.add_argument("--verify-timeout", type=int, default=15)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if getattr(args, "verify_timeout", 15) < 1 or getattr(args, "verify_timeout", 15) > 120:
        core._fail("--verify-timeout must be between 1 and 120 seconds.")
    if args.command == "configure":
        path = _configure(args)
        print(json.dumps({"status": "configured", "target": str(path), "production_eligible": False, "release_evidence": False}, sort_keys=True))
        return 0
    try:
        path = _execute_deploy(args) if args.command == "deploy" else _recover_published(args)
    except (Exception, SystemExit, KeyboardInterrupt) as exc:
        if isinstance(exc, SystemExit):
            raise
        raise SystemExit("POC deployment failed with redacted diagnostics; inspect its receipt when one was created.") from None
    print(json.dumps({"status": "succeeded_poc_deploy", "receipt": str(path), "production_eligible": False, "release_evidence": False}, sort_keys=True))
    return 0


# Exact 1.199.0 patch anchors. The isolated runtime rejects unguarded deploys,
# reports read-only state, blocks fresh-create fallback on upgrades, and omits
# routingName from exact upgrades.
POC_PATCH_EDITS = (
    (
        """    const match = data.value.find((app) => app.title === appName || app.title === displayTitle);
    if (match)
      return match;""",
        """    const exactMatches = data.value.filter((app) => app.title === appName || app.title === displayTitle);
    const distinctMatches = [...new Map(exactMatches.map((app) => [app.id, app])).values()];
    if (distinctMatches.length > 1) throw new Error(\"POC_DEPLOYMENT_IDENTITY_AMBIGUOUS\");
    if (distinctMatches.length === 1)
      return distinctMatches[0];""",
    ),
    (
        """  const matches = data.value.filter((app) => app.title === appName);
  if (matches.length === 0)""",
        """  const matches = data.value.filter((app) => app.title === appName);
  if (new Set(matches.map((app) => app.systemName)).size > 1) throw new Error(\"POC_PUBLISHED_IDENTITY_AMBIGUOUS\");
  if (matches.length === 0)""",
    ),
    (
        """async function executeDeploy(options) {
  const logger3 = options.logger ?? {""",
        """async function executeDeploy(options) {
  const pocMode = options.pocMode;
  const pocUpgradeMode = pocMode?.startsWith(\"upgrade-\");
  if (![\"inspect\", \"create-verify\", \"create-execute\", \"create-post\", \"upgrade-pre\", \"upgrade-candidate\", \"upgrade-execute\", \"upgrade-post\"].includes(pocMode)) {
    throw new Error(\"POC_GUARD_REQUIRED: this isolated runtime cannot mutate apps\");
  }
  const pocExpectedDeploymentId = options.pocExpectedDeploymentId;
  const pocExpectedSystemName = options.pocExpectedSystemName;
  const pocExpectedDeployVersion = options.pocExpectedDeployVersion;
  const pocExpectedCurrentVersion = options.pocExpectedCurrentVersion;
  const pocExpectedRouteName = options.pocExpectedRouteName;
  const logger3 = options.logger ?? {""",
    ),
    (
        """    const deployedApp = await getDeployedApp(appName, displayTitle, envConfig);
    let operationResult;""",
        """    const deployedApp = await getDeployedApp(appName, displayTitle, envConfig);
    const guardConfig = await loadAppConfig(logger3);
    const guardAppType = guardConfig?.appType === \"Action\" ? \"Action\" : \"Web\";
    const guardAppUrl = guardAppType === \"Action\" ? null : buildAppUrl(envConfig.baseUrl, envConfig.orgName, deployedApp?.routingName ?? routingName);
    if (pocMode === \"inspect\") {
      const latestPublished = await getPublishedApp(appName, envConfig);
      const allPublished = latestPublished ? await getAllPublishedVersions(latestPublished.systemName, envConfig) : [];
      const publishedVersions = allPublished.map((app) => ({
        version: app.definition?.codedAppMetadata?.packageVersion,
        systemName: app.systemName,
        deployVersion: app.deployVersion
      })).filter((app) => app.version && app.systemName && app.deployVersion !== undefined);
      const [routeError] = await catchError(checkAppNameUniqueness(routingName, envConfig));
      return {
        appName: displayTitle,
        appUrl: guardAppUrl,
        appType: guardAppType,
        routeName: routingName,
        routeAvailable: !routeError,
        deployment: deployedApp ? { id: deployedApp.id, title: deployedApp.title, routingName: deployedApp.routingName, semVersion: deployedApp.semVersion } : null,
        publishedVersions,
        operation: \"poc_inspect\"
      };
    }
    if (pocUpgradeMode) {
      if (!deployedApp || deployedApp.id !== pocExpectedDeploymentId || deployedApp.routingName !== pocExpectedRouteName || deployedApp.semVersion !== pocExpectedCurrentVersion) {
        throw new Error(\"POC_UPGRADE_TARGET_MISMATCH: fresh deploy prohibited\");
      }
      if (pocMode === \"upgrade-pre\") {
        return { appName: displayTitle, appUrl: guardAppUrl, version: options.version, deploymentId: deployedApp.id, systemName: null, deployVersion: null, currentVersion: deployedApp.semVersion, routeName: deployedApp.routingName, operation: \"poc_upgrade_pre\" };
      }
    }
    if (pocMode === \"create-post\") {
      if (!deployedApp || deployedApp.id !== pocExpectedDeploymentId || deployedApp.routingName !== routingName || deployedApp.semVersion !== options.version) throw new Error(\"POC_CREATE_POST_MISMATCH\");
      const publishedApp = await getPublishedAppWithRetry(appName, envConfig, options.version, () => {});
      if (!publishedApp || publishedApp.systemName !== pocExpectedSystemName || String(publishedApp.deployVersion) !== pocExpectedDeployVersion) throw new Error(\"POC_CREATE_CANDIDATE_MISMATCH\");
      return { appName: displayTitle, appUrl: guardAppUrl, version: options.version, deploymentId: deployedApp.id, systemName: publishedApp.systemName, deployVersion: publishedApp.deployVersion, currentVersion: deployedApp.semVersion, routeName: deployedApp.routingName, operation: \"poc_create_post\" };
    }
    if (deployedApp && !pocUpgradeMode) throw new Error(\"POC_CREATE_DEPLOYMENT_EXISTS\");
    if (!pocUpgradeMode) await checkAppNameUniqueness(routingName, envConfig);
    if (pocMode === \"create-verify\") return { appName: displayTitle, appUrl: guardAppUrl, version: options.version, deploymentId: null, systemName: null, deployVersion: null, currentVersion: null, routeName: routingName, operation: \"poc_create_verify\" };
    let operationResult;""",
    ),
    (
        """      await upgradeApp(deployedApp.id, displayTitle, publishedApp.deployVersion, options.pathName ? routingName : undefined, envConfig, options.tags, options.clientId);""",
        """      if (pocUpgradeMode && (publishedApp.systemName !== pocExpectedSystemName || String(publishedApp.deployVersion) !== pocExpectedDeployVersion)) throw new Error(\"POC_UPGRADE_CANDIDATE_MISMATCH\");
      if (pocMode === \"upgrade-candidate\" || pocMode === \"upgrade-post\") return { appName: displayTitle, appUrl: guardAppUrl, version: publishedApp.definition?.codedAppMetadata?.packageVersion, deploymentId: deployedApp.id, systemName: publishedApp.systemName, deployVersion: publishedApp.deployVersion, currentVersion: deployedApp.semVersion, routeName: deployedApp.routingName, operation: pocMode === \"upgrade-post\" ? \"poc_upgrade_post\" : \"poc_upgrade_candidate\" };
      await upgradeApp(deployedApp.id, displayTitle, publishedApp.deployVersion, pocUpgradeMode ? undefined : options.pathName ? routingName : undefined, envConfig, options.tags, options.clientId);""",
    ),
    (
        """        deployVersion: publishedApp.deployVersion,
        operation: \"upgrade\"""",
        """        deployVersion: publishedApp.deployVersion,
        currentVersion: version2,
        routeName: deployedApp.routingName,
        operation: pocMode === \"upgrade-execute\" ? \"poc_upgrade_execute\" : \"upgrade\"""",
    ),
    (
        """  program2.command(\"deploy\").description(\"Deploy or upgrade app in UiPath\").option(\"-n, --name <name>\", \"App name\").option(\"--path-name <name>\", \"App pathname in the URL (https://<org>.uipath.host/<path-name>)\").option(\"--client-id <id>\", \"OAuth client ID override (non-confidential/public client)\").option(\"-v, --version <version>\", \"Target a specific published version\").option(\"--base-url <url>\", \"UiPath base URL\").option(\"--org-id <id>\", \"Organization ID\").option(\"--org-name <name>\", \"Organization name\").option(\"--tenant-id <id>\", \"Tenant ID\").option(\"--folder-key <key>\", \"Folder key\").option(\"--access-token <token>\", \"Access token\").option(\"--tags <tags>\", \"Comma-separated categorization labels for the deployed app (e.g. governance,insights)\").examples(DEPLOY_EXAMPLES).trackedAction(processContext, async (options) => {""",
        """  program2.command(\"deploy\").description(\"Deploy or upgrade app in UiPath\").option(\"-n, --name <name>\", \"App name\").option(\"--path-name <name>\", \"App pathname in the URL (https://<org>.uipath.host/<path-name>)\").option(\"--client-id <id>\", \"OAuth client ID override (non-confidential/public client)\").option(\"-v, --version <version>\", \"Target a specific published version\").option(\"--base-url <url>\", \"UiPath base URL\").option(\"--org-id <id>\", \"Organization ID\").option(\"--org-name <name>\", \"Organization name\").option(\"--tenant-id <id>\", \"Tenant ID\").option(\"--folder-key <key>\", \"Folder key\").option(\"--access-token <token>\", \"Access token\").option(\"--tags <tags>\", \"Comma-separated categorization labels for the deployed app (e.g. governance,insights)\").option(\"--poc-mode <mode>\", \"Guarded POC mode\").option(\"--poc-expected-deployment-id <id>\", \"Exact deployment ID\").option(\"--poc-expected-system-name <name>\", \"Exact candidate system name\").option(\"--poc-expected-deploy-version <number>\", \"Exact candidate deploy version\").option(\"--poc-expected-current-version <version>\", \"Exact current version\").option(\"--poc-expected-route-name <name>\", \"Exact route\").examples(DEPLOY_EXAMPLES).trackedAction(processContext, async (options) => {""",
    ),
    (
        """      accessToken: options.accessToken,
      tags,
      logger: logger3""",
        """      accessToken: options.accessToken,
      tags,
      pocMode: options.pocMode,
      pocExpectedDeploymentId: options.pocExpectedDeploymentId,
      pocExpectedSystemName: options.pocExpectedSystemName,
      pocExpectedDeployVersion: options.pocExpectedDeployVersion,
      pocExpectedCurrentVersion: options.pocExpectedCurrentVersion,
      pocExpectedRouteName: options.pocExpectedRouteName,
      logger: logger3""",
    ),
    (
        """      Data: { message: \"App deployed successfully.\" }
    });""",
        """      Data: result?.operation === \"poc_inspect\" ? { message: \"POC remote state inspected.\", appType: result.appType, appName: result.appName, routeName: result.routeName, appUrl: result.appUrl, routeAvailable: result.routeAvailable, deployment: result.deployment, publishedVersions: result.publishedVersions, operation: result.operation } : result?.operation?.startsWith(\"poc_\") ? { message: \"POC guarded operation completed.\", deploymentId: result.deploymentId, systemName: result.systemName, deployVersion: result.deployVersion, currentVersion: result.currentVersion, routeName: result.routeName, version: result.version, appName: result.appName, appUrl: result.appUrl, operation: result.operation } : result?.operation === \"deploy\" ? { message: \"POC create completed.\", deploymentId: result.deploymentId, systemName: result.systemName, deployVersion: result.deployVersion, version: result.version, appName: result.appName, appUrl: result.appUrl, operation: result.operation } : { message: \"App deployed successfully.\" }
    });""",
    ),
    (
        """      Data: { message: \"Package published successfully.\" }
    });""",
        """      Data: result ? { message: \"Package published successfully.\", packageName: result.packageName, packageVersion: result.packageVersion, systemName: result.systemName, deployVersion: result.deployVersion, personalWorkspace: result.personalWorkspace, appType: result.appType } : { message: \"Package published successfully.\" }
    });""",
    ),
)


if __name__ == "__main__":
    raise SystemExit(main())
