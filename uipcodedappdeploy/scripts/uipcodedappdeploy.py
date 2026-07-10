#!/usr/bin/env python3
"""Plan and execute a fail-closed UiPath coded app deployment."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


PLAN_KIND = "uipcodedappdeploy.plan"
PLAN_SCHEMA_VERSION = "1.0"
RECEIPT_KIND = "uipcodedappdeploy.receipt"
RECEIPT_SCHEMA_VERSION = "1.0"
RESULT_KIND = "uipcodedappdeploy.result"
RESULT_SCHEMA_VERSION = "1.0"
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
GUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
SEMVER_RE = re.compile(
    r"^(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)"
    r"(?:-((?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
PROJECT_HEADER_RE = re.compile(r"^\s*\[\s*project\s*\]\s*(?:#.*)?(?:\r?\n)?$")
TABLE_HEADER_RE = re.compile(r"^\s*\[\[?.+?\]\]?\s*(?:#.*)?(?:\r?\n)?$")
VERSION_ASSIGNMENT_RE = re.compile(
    r"^(?P<prefix>\s*(?:version|\"version\"|'version')\s*=\s*)"
    r"(?P<value>\"(?:\\.|[^\"\\])*\"|'[^']*')"
    r"(?P<suffix>\s*(?:#.*)?)(?P<newline>\r?\n?)$"
)
PARAMETER_KEYS = {
    "app_name",
    "app_type",
    "author",
    "content_type",
    "description",
    "dist",
    "folder_key",
    "main_file",
    "org_id",
    "org_name",
    "package_name",
    "reuse_client",
    "run_app_build",
    "run_lock",
    "run_tests",
    "target_url",
    "tenant_id",
    "tenant_name",
    "uipath_dir",
    "verify_timeout",
    "verify_url",
}
REDACTION_POLICY = {
    "commands": "omitted",
    "environment": "omitted",
    "subprocess_output": "omitted",
    "errors": "generic_message_only",
}


@dataclass(frozen=True)
class SemVer:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] | None

    def compare(self, other: "SemVer") -> int:
        left_core = (self.major, self.minor, self.patch)
        right_core = (other.major, other.minor, other.patch)
        if left_core != right_core:
            return 1 if left_core > right_core else -1
        if self.prerelease is None and other.prerelease is None:
            return 0
        if self.prerelease is None:
            return 1
        if other.prerelease is None:
            return -1
        for left, right in zip(self.prerelease, other.prerelease):
            if left == right:
                continue
            left_numeric = left.isdigit()
            right_numeric = right.isdigit()
            if left_numeric and right_numeric:
                return 1 if int(left) > int(right) else -1
            if left_numeric != right_numeric:
                return -1 if left_numeric else 1
            return 1 if left > right else -1
        if len(self.prerelease) == len(other.prerelease):
            return 0
        return 1 if len(self.prerelease) > len(other.prerelease) else -1


def _fail(message: str) -> None:
    raise SystemExit(message)


def _log(message: str) -> None:
    print(message, file=sys.stderr)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _hash_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _hash_json(value: Any) -> str:
    return _hash_bytes(_canonical_json(value))


def _document_hash(document: dict[str, Any], hash_key: str) -> str:
    unhashed = {key: value for key, value in document.items() if key != hash_key}
    return _hash_json(unhashed)


def _atomic_write_bytes(path: Path, payload: bytes, mode: int) -> None:
    if not path.parent.is_dir():
        _fail(f"Output directory does not exist: {path.parent}")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_write_json(path: Path, document: dict[str, Any]) -> None:
    payload = json.dumps(document, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    _atomic_write_bytes(path, payload, 0o600)


def _parse_semver(value: str, label: str) -> SemVer:
    if not isinstance(value, str):
        _fail(f"{label} must be a SemVer string.")
    match = SEMVER_RE.fullmatch(value)
    if match is None:
        _fail(
            f"{label} {value!r} is not valid SemVer 2.0.0. "
            "Use MAJOR.MINOR.PATCH with an optional prerelease/build suffix."
        )
    prerelease = tuple(match.group(4).split(".")) if match.group(4) else None
    return SemVer(int(match.group(1)), int(match.group(2)), int(match.group(3)), prerelease)


def _next_version(version: str, part: str) -> str:
    parsed = _parse_semver(version, "Current [project].version")
    if part == "major":
        return f"{parsed.major + 1}.0.0"
    if part == "minor":
        return f"{parsed.major}.{parsed.minor + 1}.0"
    return f"{parsed.major}.{parsed.minor}.{parsed.patch + 1}"


def _validate_progression(old_version: str, new_version: str) -> None:
    old = _parse_semver(old_version, "Current [project].version")
    new = _parse_semver(new_version, "Planned version")
    if new.compare(old) <= 0:
        _fail(
            f"Planned version {new_version!r} must have greater SemVer precedence "
            f"than current version {old_version!r}; build metadata alone is not a progression."
        )


def _load_pyproject(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        _fail(f"Missing required project manifest: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        _fail(f"Could not read UTF-8 TOML from {path}: {exc}")
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        _fail(f"Invalid TOML in {path}: {exc}")
    project = document.get("project")
    if not isinstance(project, dict):
        _fail(f"{path} must contain a [project] table.")
    name = project.get("name")
    if not isinstance(name, str) or not name.strip():
        _fail(f"{path} [project].name must be a non-empty string.")
    version = project.get("version")
    if not isinstance(version, str):
        _fail(f"{path} [project].version must be a string; dynamic versions are unsupported.")
    _parse_semver(version, f"{path} [project].version")
    description = project.get("description", "")
    if not isinstance(description, str):
        _fail(f"{path} [project].description must be a string when present.")
    authors = project.get("authors", [])
    if not isinstance(authors, list):
        _fail(f"{path} [project].authors must be an array when present.")
    for index, author in enumerate(authors):
        if not isinstance(author, dict) or not author:
            _fail(f"{path} [project].authors[{index}] must be a non-empty table.")
        for field in ("name", "email"):
            if field in author and (
                not isinstance(author[field], str) or not author[field].strip()
            ):
                _fail(
                    f"{path} [project].authors[{index}].{field} must be a non-empty string."
                )
    return document, text


def _load_uipath_json(path: Path, *, reuse_client: bool = False) -> dict[str, Any]:
    if not path.is_file():
        _fail(f"Missing required coded app manifest: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        _fail(f"Could not read UTF-8 JSON from {path}: {exc}")
    except json.JSONDecodeError as exc:
        _fail(f"Invalid JSON in {path}: {exc}")
    if not isinstance(document, dict) or not document:
        _fail(f"{path} must contain a non-empty JSON object.")
    for field in ("clientId", "projectId"):
        if field in document and (
            not isinstance(document[field], str) or not document[field].strip()
        ):
            _fail(f"{path} field {field!r} must be a non-empty string when present.")
    if reuse_client and not document.get("clientId"):
        _fail(f"--reuse-client requires a non-empty clientId in {path}.")
    return document


def _project_metadata(document: dict[str, Any]) -> dict[str, str]:
    project = document["project"]
    author = "UiPath Developer"
    for candidate in project.get("authors", []):
        if isinstance(candidate.get("name"), str) and candidate["name"].strip():
            author = candidate["name"].strip()
            break
    return {
        "name": project["name"].strip(),
        "version": project["version"],
        "description": project.get("description", ""),
        "author": author,
    }


def _render_version_update(text: str, old_version: str, new_version: str) -> str:
    document = tomllib.loads(text)
    project = document.get("project")
    if not isinstance(project, dict) or project.get("version") != old_version:
        _fail("pyproject.toml changed while preparing the version update; regenerate the plan.")
    lines = text.splitlines(keepends=True)
    headers = [index for index, line in enumerate(lines) if PROJECT_HEADER_RE.match(line)]
    if len(headers) != 1:
        _fail(
            "Atomic version updates require exactly one explicit [project] table in "
            "pyproject.toml; migrate dotted or generated metadata before deploying."
        )
    start = headers[0] + 1
    end = len(lines)
    for index in range(start, len(lines)):
        if TABLE_HEADER_RE.match(lines[index]):
            end = index
            break
    assignments = [
        index
        for index in range(start, end)
        if VERSION_ASSIGNMENT_RE.match(lines[index])
    ]
    if len(assignments) != 1:
        _fail(
            "Atomic version updates require one single-line [project].version assignment; "
            "migrate multiline or generated version metadata before deploying."
        )
    index = assignments[0]
    match = VERSION_ASSIGNMENT_RE.match(lines[index])
    assert match is not None
    lines[index] = (
        match.group("prefix")
        + json.dumps(new_version)
        + match.group("suffix")
        + match.group("newline")
    )
    updated = "".join(lines)
    try:
        updated_document = tomllib.loads(updated)
    except tomllib.TOMLDecodeError as exc:
        _fail(f"Refusing to write an invalid pyproject.toml update: {exc}")
    expected = copy.deepcopy(document)
    expected["project"]["version"] = new_version
    if updated_document != expected:
        _fail("Refusing pyproject.toml update because it changed data beyond [project].version.")
    return updated


def _write_version_atomic(path: Path, old_version: str, new_version: str) -> None:
    _, text = _load_pyproject(path)
    updated = _render_version_update(text, old_version, new_version)
    mode = path.stat().st_mode & 0o777
    _atomic_write_bytes(path, updated.encode("utf-8"), mode)
    _log(f"Set {path.name} [project].version to {new_version}")


def _safe_text(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        _fail(f"{label} must be a string.")
    if not allow_empty and not value.strip():
        _fail(f"{label} must be a non-empty string.")
    if "\x00" in value or "\n" in value or "\r" in value:
        _fail(f"{label} must not contain NUL or newline characters.")
    return value


def _safe_relative_literal(value: str, label: str, *, allow_dot: bool = False) -> str:
    candidate = Path(_safe_text(value, label))
    if candidate.is_absolute() or ".." in candidate.parts:
        _fail(f"{label} must be a project-relative path without '..': {value!r}")
    normalized = Path(os.path.normpath(candidate)).as_posix()
    if normalized == "." and not allow_dot:
        _fail(f"{label} must not resolve to the project root.")
    return normalized


def _project_relative_path(root: Path, value: str, label: str) -> str:
    literal = _safe_relative_literal(value, label)
    resolved = (root / literal).resolve(strict=False)
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        _fail(f"{label} must resolve inside the project root: {value!r}")
    if relative == Path("."):
        _fail(f"{label} must not resolve to the project root.")
    return relative.as_posix()


def _validate_url(value: str, label: str, *, base_only: bool) -> str:
    value = _safe_text(value, label)
    parsed = urlsplit(value)
    try:
        parsed.port
    except ValueError:
        _fail(f"{label} contains an invalid port.")
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        _fail(f"{label} must be an HTTPS URL without embedded credentials.")
    if parsed.fragment:
        _fail(f"{label} must not contain a fragment.")
    if base_only and (parsed.path not in ("", "/") or parsed.query):
        _fail(f"{label} must be an HTTPS origin without a path or query string.")
    if not base_only and parsed.query:
        _fail(f"{label} must not contain a query string because plans are retained artifacts.")
    return value.rstrip("/") if base_only else value


def _default_dist(root: Path) -> str:
    if (root / "app" / "package.json").is_file() or (root / "app" / "dist").exists():
        return "app/dist"
    return "dist"


def _auth_flags(parameters: dict[str, Any], *, publish: bool, deploy: bool) -> list[str]:
    flags = ["--base-url", parameters["target_url"]]
    if parameters["org_id"]:
        flags.extend(["--org-id", parameters["org_id"]])
    if deploy and parameters["org_name"]:
        flags.extend(["--org-name", parameters["org_name"]])
    if parameters["tenant_id"]:
        flags.extend(["--tenant-id", parameters["tenant_id"]])
    if publish and parameters["tenant_name"]:
        flags.extend(["--tenant-name", parameters["tenant_name"]])
    return flags


def _build_stages(project: dict[str, Any], parameters: dict[str, Any]) -> list[dict[str, Any]]:
    stages: list[dict[str, Any]] = [
        {"name": "version", "action": "write_version", "effect": "project_write"}
    ]
    if parameters["run_lock"]:
        stages.append(
            {
                "name": "lock",
                "action": "command",
                "effect": "project_write",
                "cwd": ".",
                "command": ["uv", "lock"],
            }
        )
    if parameters["run_tests"]:
        stages.append(
            {
                "name": "test",
                "action": "command",
                "effect": "local_read",
                "cwd": ".",
                "command": ["uv", "run", "python", "-m", "pytest", "-q"],
            }
        )
    if parameters["run_app_build"]:
        stages.append(
            {
                "name": "build",
                "action": "command",
                "effect": "project_write",
                "cwd": "app",
                "command": ["npm", "run", "build"],
            }
        )
    stages.extend(
        [
            {"name": "dist", "action": "validate_dist", "effect": "local_read"},
            {
                "name": "uip_probe",
                "action": "command",
                "effect": "local_read",
                "cwd": ".",
                "command": ["uip", "--version"],
            },
        ]
    )
    pack_command = [
        "uip",
        "codedapp",
        "pack",
        parameters["dist"],
        "--name",
        parameters["package_name"],
        "--version",
        project["new_version"],
        "--output",
        parameters["uipath_dir"],
        "--author",
        parameters["author"],
        "--main-file",
        parameters["main_file"],
        "--content-type",
        parameters["content_type"],
        *_auth_flags(parameters, publish=False, deploy=False),
    ]
    if parameters["description"]:
        pack_command.extend(["--description", parameters["description"]])
    if parameters["reuse_client"]:
        pack_command.append("--reuse-client")
    publish_command = [
        "uip",
        "codedapp",
        "publish",
        "--name",
        parameters["package_name"],
        "--version",
        project["new_version"],
        "--type",
        parameters["app_type"],
        "--uipath-dir",
        parameters["uipath_dir"],
        *_auth_flags(parameters, publish=True, deploy=False),
    ]
    deploy_command = [
        "uip",
        "codedapp",
        "deploy",
        "--name",
        parameters["app_name"],
        "--version",
        project["new_version"],
        *_auth_flags(parameters, publish=False, deploy=True),
    ]
    if parameters["folder_key"]:
        deploy_command.extend(["--folder-key", parameters["folder_key"]])
    stages.extend(
        [
            {
                "name": "pack",
                "action": "command",
                "effect": "project_write",
                "cwd": ".",
                "command": pack_command,
            },
            {
                "name": "publish",
                "action": "command",
                "effect": "external_write",
                "cwd": ".",
                "command": publish_command,
            },
            {
                "name": "deploy",
                "action": "command",
                "effect": "external_write",
                "cwd": ".",
                "command": deploy_command,
            },
        ]
    )
    if parameters["verify_url"]:
        stages.append(
            {"name": "verify", "action": "verify_url", "effect": "external_read"}
        )
    return stages


def _snapshot_records(root: Path, overrides: dict[str, bytes] | None = None) -> list[dict[str, str]]:
    overrides = overrides or {}
    records = []
    for relative in ("pyproject.toml", "uipath.json"):
        path = root / relative
        if relative in overrides:
            payload = overrides[relative]
        else:
            try:
                payload = path.read_bytes()
            except OSError as exc:
                _fail(f"Could not hash required input {path}: {exc}")
        records.append({"path": relative, "sha256": _hash_bytes(payload)})
    return records


def _snapshot(records: list[dict[str, str]]) -> dict[str, Any]:
    return {"files": records, "hash": _hash_json({"files": records})}


def _current_input_hash(root: Path) -> str:
    return _snapshot(_snapshot_records(root))["hash"]


def _legacy_failure(args: argparse.Namespace) -> None:
    migrations = (
        (
            args.folder,
            "--folder is no longer resolved during deployment planning. Migration: resolve "
            "the folder with a read-only UiPath CLI query, then pass its GUID via --folder-key.",
        ),
        (
            args.tenant,
            "--tenant was an ambiguous compatibility flag and is rejected. Migration: pass "
            "--tenant-name or --tenant-id explicitly.",
        ),
        (
            args.my_workspace,
            "--my-workspace is rejected because it did not identify a deployable folder. "
            "Migration: pass the personal workspace folder GUID via --folder-key.",
        ),
        (
            args.pack_nolock,
            "--pack-nolock was a no-op and is rejected. Migration: omit it; this helper runs "
            "uv lock before tests/build when uv.lock exists.",
        ),
        (
            args.use_deploy_command,
            "--use-deploy-command was a no-op and is rejected. Migration: generate a plan, "
            "then execute it with --plan <file> --execute.",
        ),
        (
            args.offline,
            "--offline is obsolete and is rejected. Migration: omit it; planning never probes "
            "UiPath or runs project commands.",
        ),
    )
    for active, message in migrations:
        if active:
            _fail(message)


def _build_plan(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root or ".").expanduser().resolve()
    if not root.is_dir():
        _fail(f"Project root does not exist or is not a directory: {root}")
    pyproject_path = root / "pyproject.toml"
    uipath_path = root / "uipath.json"
    pyproject, pyproject_text = _load_pyproject(pyproject_path)
    _load_uipath_json(uipath_path, reuse_client=args.reuse_client)
    metadata = _project_metadata(pyproject)
    old_version = metadata["version"]
    if args.set_version and args.part:
        _fail("Use either --set-version or --part, not both.")
    new_version = args.set_version or _next_version(old_version, args.part or "patch")
    _validate_progression(old_version, new_version)

    raw_dist = args.app_dist or _default_dist(root)
    dist = _project_relative_path(root, raw_dist, "--app-dist")
    main_file = _safe_relative_literal(args.main_file or "index.html", "--main-file")
    target_url = _validate_url(
        args.target_url or "https://alpha.uipath.com",
        "--target-url",
        base_only=True,
    )
    if args.verify_timeout is not None and not args.verify_url:
        _fail("--verify-timeout requires --verify-url.")
    verify_url = (
        _validate_url(args.verify_url, "--verify-url", base_only=False)
        if args.verify_url
        else None
    )
    folder_key = args.folder_key
    if folder_key and GUID_RE.fullmatch(folder_key) is None:
        _fail("--folder-key must be a GUID copied from the target UiPath folder.")
    package_name = _safe_text(args.package_name or metadata["name"], "--package-name")
    app_name = _safe_text(args.app_name or package_name, "--app-name")
    author = _safe_text(args.author or metadata["author"], "--author")
    description = _safe_text(
        metadata["description"] if args.description is None else args.description,
        "--description",
        allow_empty=True,
    )
    content_type = _safe_text(args.content_type or "webapp", "--content-type")
    for label, value in (
        ("--tenant-name", args.tenant_name),
        ("--tenant-id", args.tenant_id),
        ("--org-id", args.org_id),
        ("--org-name", args.org_name),
    ):
        if value is not None:
            _safe_text(value, label)
    verify_timeout = args.verify_timeout if args.verify_timeout is not None else 15
    if verify_timeout < 1 or verify_timeout > 120:
        _fail("--verify-timeout must be between 1 and 120 seconds.")

    updated_pyproject = _render_version_update(pyproject_text, old_version, new_version)
    initial = _snapshot(_snapshot_records(root))
    versioned = _snapshot(
        _snapshot_records(
            root,
            overrides={"pyproject.toml": updated_pyproject.encode("utf-8")},
        )
    )
    project = {
        "root": str(root),
        "manifest": "pyproject.toml",
        "uipath_manifest": "uipath.json",
        "name": metadata["name"],
        "old_version": old_version,
        "new_version": new_version,
    }
    parameters = {
        "target_url": target_url,
        "tenant_name": args.tenant_name,
        "tenant_id": args.tenant_id,
        "org_id": args.org_id,
        "org_name": args.org_name,
        "folder_key": folder_key,
        "dist": dist,
        "uipath_dir": ".uipath",
        "package_name": package_name,
        "app_name": app_name,
        "app_type": args.app_type or "Web",
        "main_file": main_file,
        "content_type": content_type,
        "author": author,
        "description": description,
        "reuse_client": bool(args.reuse_client),
        "run_lock": (root / "uv.lock").is_file(),
        "run_tests": not args.skip_tests,
        "run_app_build": (
            not args.skip_app_build and (root / "app" / "package.json").is_file()
        ),
        "verify_url": verify_url,
        "verify_timeout": verify_timeout,
    }
    blockers = []
    if not folder_key:
        blockers.append("A valid --folder-key is mandatory before execution.")
    plan = {
        "kind": PLAN_KIND,
        "schema_version": PLAN_SCHEMA_VERSION,
        "created_at": _utc_now(),
        "project": project,
        "inputs": {
            "scope": ["pyproject.toml", "uipath.json"],
            "initial": initial,
            "versioned": versioned,
        },
        "parameters": parameters,
        "stages": _build_stages(project, parameters),
        "execution": {
            "requires_execute": True,
            "requires_plan": True,
            "executable": not blockers,
            "blockers": blockers,
        },
    }
    plan["plan_hash"] = _document_hash(plan, "plan_hash")
    return plan


def _validate_snapshot(snapshot: Any, label: str) -> None:
    if not isinstance(snapshot, dict) or set(snapshot) != {"files", "hash"}:
        _fail(f"{label} must contain exactly files and hash.")
    files = snapshot["files"]
    if not isinstance(files, list) or [item.get("path") for item in files if isinstance(item, dict)] != [
        "pyproject.toml",
        "uipath.json",
    ]:
        _fail(f"{label}.files must list pyproject.toml and uipath.json in canonical order.")
    for item in files:
        if set(item) != {"path", "sha256"} or not isinstance(item["sha256"], str):
            _fail(f"{label}.files contains an invalid file record.")
        if HASH_RE.fullmatch(item["sha256"]) is None:
            _fail(f"{label}.files contains an invalid SHA-256 hash.")
    if snapshot["hash"] != _hash_json({"files": files}):
        _fail(f"{label}.hash does not match its file records.")


def _validate_parameters(root: Path, parameters: Any) -> None:
    if not isinstance(parameters, dict) or set(parameters) != PARAMETER_KEYS:
        _fail("Plan parameters do not match schema version 1.0.")
    if _validate_url(parameters["target_url"], "Plan target_url", base_only=True) != parameters[
        "target_url"
    ]:
        _fail("Plan target_url is not normalized.")
    if parameters["verify_url"] is not None:
        _validate_url(parameters["verify_url"], "Plan verify_url", base_only=False)
    for field in ("tenant_name", "tenant_id", "org_id", "org_name"):
        if parameters[field] is not None:
            _safe_text(parameters[field], f"Plan {field}")
    folder_key = parameters["folder_key"]
    if folder_key is not None and (
        not isinstance(folder_key, str) or GUID_RE.fullmatch(folder_key) is None
    ):
        _fail("Plan folder_key must be null or a GUID.")
    if _project_relative_path(root, parameters["dist"], "Plan dist") != parameters["dist"]:
        _fail("Plan dist path is not normalized.")
    if parameters["uipath_dir"] != ".uipath":
        _fail("Plan uipath_dir must be the project-relative .uipath directory.")
    if _safe_relative_literal(parameters["main_file"], "Plan main_file") != parameters[
        "main_file"
    ]:
        _fail("Plan main_file is not normalized.")
    for field in ("package_name", "app_name", "author", "content_type"):
        _safe_text(parameters[field], f"Plan {field}")
    _safe_text(parameters["description"], "Plan description", allow_empty=True)
    if parameters["app_type"] not in ("Web", "Action"):
        _fail("Plan app_type must be Web or Action.")
    for field in ("reuse_client", "run_lock", "run_tests", "run_app_build"):
        if not isinstance(parameters[field], bool):
            _fail(f"Plan {field} must be a boolean.")
    if (
        isinstance(parameters["verify_timeout"], bool)
        or not isinstance(parameters["verify_timeout"], int)
        or not 1 <= parameters["verify_timeout"] <= 120
    ):
        _fail("Plan verify_timeout must be an integer from 1 through 120.")


def _validate_plan_document(plan: Any) -> dict[str, Any]:
    expected_keys = {
        "kind",
        "schema_version",
        "created_at",
        "project",
        "inputs",
        "parameters",
        "stages",
        "execution",
        "plan_hash",
    }
    if not isinstance(plan, dict) or set(plan) != expected_keys:
        _fail("Deployment plan does not match the version 1.0 document shape.")
    if plan["kind"] != PLAN_KIND or plan["schema_version"] != PLAN_SCHEMA_VERSION:
        _fail(
            f"Unsupported deployment plan kind/schema; expected {PLAN_KIND} "
            f"version {PLAN_SCHEMA_VERSION}. Regenerate the plan with this helper."
        )
    if not isinstance(plan["created_at"], str):
        _fail("Plan created_at must be a string.")
    if not isinstance(plan["plan_hash"], str) or HASH_RE.fullmatch(plan["plan_hash"]) is None:
        _fail("Plan plan_hash is not a SHA-256 value.")
    if plan["plan_hash"] != _document_hash(plan, "plan_hash"):
        _fail("Plan hash mismatch; the plan was edited or corrupted. Regenerate it.")

    project = plan["project"]
    if not isinstance(project, dict) or set(project) != {
        "root",
        "manifest",
        "uipath_manifest",
        "name",
        "old_version",
        "new_version",
    }:
        _fail("Plan project metadata does not match schema version 1.0.")
    root = Path(_safe_text(project["root"], "Plan project.root"))
    if not root.is_absolute() or root.resolve() != root:
        _fail("Plan project.root must be a canonical absolute path.")
    if project["manifest"] != "pyproject.toml" or project["uipath_manifest"] != "uipath.json":
        _fail("Plan manifest paths must remain project-relative canonical names.")
    _safe_text(project["name"], "Plan project.name")
    _validate_progression(project["old_version"], project["new_version"])

    inputs = plan["inputs"]
    if not isinstance(inputs, dict) or set(inputs) != {"scope", "initial", "versioned"}:
        _fail("Plan inputs do not match schema version 1.0.")
    if inputs["scope"] != ["pyproject.toml", "uipath.json"]:
        _fail("Plan input hash scope must be pyproject.toml and uipath.json.")
    _validate_snapshot(inputs["initial"], "Plan inputs.initial")
    _validate_snapshot(inputs["versioned"], "Plan inputs.versioned")
    if inputs["initial"]["files"][1] != inputs["versioned"]["files"][1]:
        _fail("Plan versioning must not alter the uipath.json input hash.")

    _validate_parameters(root, plan["parameters"])
    expected_stages = _build_stages(project, plan["parameters"])
    if plan["stages"] != expected_stages:
        _fail("Plan stages do not match the allowlisted command sequence. Regenerate the plan.")
    blockers = [] if plan["parameters"]["folder_key"] else [
        "A valid --folder-key is mandatory before execution."
    ]
    expected_execution = {
        "requires_execute": True,
        "requires_plan": True,
        "executable": not blockers,
        "blockers": blockers,
    }
    if plan["execution"] != expected_execution:
        _fail("Plan execution policy is inconsistent with its parameters.")
    return plan


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        _fail(f"Missing {label}: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail(f"Could not load {label} {path}: {exc}")
    if not isinstance(document, dict):
        _fail(f"{label} must contain a JSON object: {path}")
    return document


def _load_plan(path: Path) -> dict[str, Any]:
    return _validate_plan_document(_load_json_object(path, "deployment plan"))


def _validate_current_inputs(plan: dict[str, Any], *, allow_versioned: bool) -> str:
    root = Path(plan["project"]["root"])
    pyproject, _ = _load_pyproject(root / "pyproject.toml")
    _load_uipath_json(root / "uipath.json", reuse_client=plan["parameters"]["reuse_client"])
    current_hash = _current_input_hash(root)
    initial_hash = plan["inputs"]["initial"]["hash"]
    versioned_hash = plan["inputs"]["versioned"]["hash"]
    current_version = pyproject["project"]["version"]
    if current_hash == initial_hash and current_version == plan["project"]["old_version"]:
        return "initial"
    if (
        allow_versioned
        and current_hash == versioned_hash
        and current_version == plan["project"]["new_version"]
    ):
        return "versioned"
    _fail(
        "Deployment input hash mismatch. pyproject.toml or uipath.json changed after "
        "planning; regenerate the plan instead of executing stale inputs."
    )


def _receipt_path(plan_path: Path) -> Path:
    return plan_path.with_suffix(plan_path.suffix + ".receipt.json")


def _new_receipt(plan: dict[str, Any]) -> dict[str, Any]:
    receipt = {
        "kind": RECEIPT_KIND,
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "plan_hash": plan["plan_hash"],
        "input_hash": plan["inputs"]["initial"]["hash"],
        "status": "in_progress",
        "started_at": _utc_now(),
        "updated_at": _utc_now(),
        "redaction": REDACTION_POLICY,
        "stages": [
            {"name": stage["name"], "effect": stage["effect"], "status": "pending"}
            for stage in plan["stages"]
        ],
    }
    receipt["receipt_hash"] = _document_hash(receipt, "receipt_hash")
    return receipt


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    receipt["updated_at"] = _utc_now()
    receipt["receipt_hash"] = _document_hash(receipt, "receipt_hash")
    _atomic_write_json(path, receipt)


def _validate_receipt(receipt: Any, plan: dict[str, Any]) -> dict[str, Any]:
    expected_keys = {
        "kind",
        "schema_version",
        "plan_hash",
        "input_hash",
        "status",
        "started_at",
        "updated_at",
        "redaction",
        "stages",
        "receipt_hash",
    }
    if not isinstance(receipt, dict) or set(receipt) != expected_keys:
        _fail("Resume receipt does not match the version 1.0 document shape.")
    if receipt["kind"] != RECEIPT_KIND or receipt["schema_version"] != RECEIPT_SCHEMA_VERSION:
        _fail("Unsupported receipt schema. Start from a newly generated plan.")
    if receipt["receipt_hash"] != _document_hash(receipt, "receipt_hash"):
        _fail("Receipt hash mismatch; the receipt was edited or corrupted.")
    if receipt["plan_hash"] != plan["plan_hash"]:
        _fail("Receipt belongs to a different deployment plan.")
    if receipt["input_hash"] != plan["inputs"]["initial"]["hash"]:
        _fail("Receipt input hash does not match the deployment plan.")
    if receipt["status"] not in ("in_progress", "failed", "succeeded"):
        _fail("Receipt status is invalid.")
    if receipt["redaction"] != REDACTION_POLICY:
        _fail("Receipt redaction policy is invalid.")
    for field in ("started_at", "updated_at"):
        if not isinstance(receipt[field], str):
            _fail(f"Receipt {field} must be a string.")
    expected_stages = [(stage["name"], stage["effect"]) for stage in plan["stages"]]
    if not isinstance(receipt["stages"], list) or [
        (stage.get("name"), stage.get("effect"))
        for stage in receipt["stages"]
        if isinstance(stage, dict)
    ] != expected_stages:
        _fail("Receipt stages do not match the deployment plan.")
    seen_incomplete = False
    for stage in receipt["stages"]:
        if not set(stage).issubset(
            {"name", "effect", "status", "started_at", "finished_at", "recovery"}
        ):
            _fail("Receipt contains a non-redacted or unknown stage field.")
        if stage.get("status") not in ("pending", "running", "failed", "succeeded"):
            _fail("Receipt contains an invalid stage status.")
        for field in ("started_at", "finished_at", "recovery"):
            if field in stage and not isinstance(stage[field], str):
                _fail(f"Receipt stage {field} must be a string.")
        if stage["status"] == "succeeded":
            if seen_incomplete:
                _fail("Receipt stage success order is inconsistent.")
        else:
            seen_incomplete = True
    statuses = [stage["status"] for stage in receipt["stages"]]
    if receipt["status"] == "succeeded" and any(
        status != "succeeded" for status in statuses
    ):
        _fail("Receipt is marked succeeded but contains an incomplete stage.")
    if receipt["status"] == "failed" and "failed" not in statuses:
        _fail("Receipt is marked failed but contains no failed stage.")
    return receipt


def _load_receipt(path: Path, plan: dict[str, Any]) -> dict[str, Any]:
    return _validate_receipt(_load_json_object(path, "resume receipt"), plan)


def _prepare_resume(
    plan: dict[str, Any], receipt: dict[str, Any], receipt_path: Path
) -> dict[str, Any]:
    version_receipt = receipt["stages"][0]
    input_state = _validate_current_inputs(plan, allow_versioned=True)
    if version_receipt["status"] == "succeeded" and input_state != "versioned":
        _fail("Receipt says versioning succeeded, but current inputs do not match the versioned hash.")
    if version_receipt["status"] != "succeeded" and input_state == "versioned":
        if version_receipt["status"] not in ("running", "failed"):
            _fail("Versioned inputs cannot be reconciled with a pending version receipt.")
        version_receipt["status"] = "succeeded"
        version_receipt["finished_at"] = _utc_now()
        version_receipt["recovery"] = "atomic_version_write_reconciled"
    for stage in receipt["stages"]:
        if stage["status"] == "running" and stage["effect"] == "external_write":
            _fail(
                f"Cannot resume: external-write stage {stage['name']!r} has an indeterminate "
                "outcome. Verify the target manually before creating a recovery plan."
            )
        if stage["status"] in ("running", "failed"):
            stage["status"] = "pending"
            stage.pop("started_at", None)
            stage.pop("finished_at", None)
            stage["recovery"] = "explicit_resume"
    receipt["status"] = "in_progress"
    _write_receipt(receipt_path, receipt)
    return receipt


def _run(cmd: list[str], cwd: Path, env: dict[str, str]) -> None:
    _log("+ " + shlex.join(cmd))
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def _validate_dist(root: Path, parameters: dict[str, Any]) -> None:
    dist = root / parameters["dist"]
    if not dist.is_dir():
        _fail(f"Missing coded app dist directory after build: {dist}")
    main_file = dist / parameters["main_file"]
    if not main_file.is_file():
        _fail(f"Missing coded app main file after build: {main_file}")
    try:
        main_file.resolve().relative_to(dist.resolve())
    except ValueError:
        _fail(f"Coded app main file resolves outside the dist directory: {main_file}")


def _validate_plan_output_path(path: Path, plan: dict[str, Any]) -> None:
    root = Path(plan["project"]["root"])
    reserved = {
        root / "pyproject.toml",
        root / "uipath.json",
        root / "uv.lock",
        root / "package.json",
        root / "app" / "package.json",
    }
    if path in reserved:
        _fail("--plan-output must not overwrite a project manifest or lock file.")
    dist = (root / plan["parameters"]["dist"]).resolve(strict=False)
    try:
        path.relative_to(dist)
    except ValueError:
        pass
    else:
        _fail("--plan-output must not be inside the coded app dist directory.")
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            _fail("--plan-output refuses to replace an existing non-plan file.")
        if not isinstance(existing, dict) or existing.get("kind") != PLAN_KIND:
            _fail("--plan-output refuses to replace an existing non-plan file.")


def _verify_url(url: str, timeout: int) -> None:
    _log(f"Verify HTTPS endpoint: {url}")
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "uipcodedappdeploy/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.getcode()
            final_url = response.geturl()
    except Exception as exc:
        _fail(f"Verification request failed for {url}: {type(exc).__name__}")
    if status < 200 or status >= 400:
        _fail(f"Verification returned HTTP {status} for {url}")
    if urlsplit(final_url).scheme != "https":
        _fail("Verification redirected to a non-HTTPS URL.")


def _execute_stage(stage: dict[str, Any], plan: dict[str, Any], env: dict[str, str]) -> None:
    root = Path(plan["project"]["root"])
    if stage["action"] == "write_version":
        _write_version_atomic(
            root / "pyproject.toml",
            plan["project"]["old_version"],
            plan["project"]["new_version"],
        )
        return
    if stage["action"] == "command":
        cwd = root if stage["cwd"] == "." else root / stage["cwd"]
        _run(stage["command"], cwd, env)
        return
    if stage["action"] == "validate_dist":
        _validate_dist(root, plan["parameters"])
        return
    if stage["action"] == "verify_url":
        _verify_url(
            plan["parameters"]["verify_url"],
            plan["parameters"]["verify_timeout"],
        )
        return
    _fail(f"Unsupported stage action: {stage['action']}")


def _execute_plan(
    plan: dict[str, Any], plan_path: Path, *, resume: bool
) -> tuple[dict[str, Any], Path]:
    if not plan["execution"]["executable"] or not plan["parameters"]["folder_key"]:
        _fail(
            "Execution blocked: the plan has no folder key. Regenerate it with "
            "--folder-key <GUID>; folder names are not resolved during execution."
        )
    root = Path(plan["project"]["root"])
    if not plan["parameters"]["run_app_build"]:
        _validate_dist(root, plan["parameters"])
    receipt_path = _receipt_path(plan_path)
    if resume:
        receipt = _prepare_resume(plan, _load_receipt(receipt_path, plan), receipt_path)
    else:
        _validate_current_inputs(plan, allow_versioned=False)
        if receipt_path.exists():
            _fail(
                f"Receipt already exists: {receipt_path}. Use --resume after reviewing it, "
                "or generate a new plan."
            )
        receipt = _new_receipt(plan)
        _write_receipt(receipt_path, receipt)

    env = os.environ.copy()
    for planned_stage, stage_receipt in zip(plan["stages"], receipt["stages"]):
        if stage_receipt["status"] == "succeeded":
            continue
        stage_receipt["status"] = "running"
        stage_receipt["started_at"] = _utc_now()
        stage_receipt.pop("finished_at", None)
        _write_receipt(receipt_path, receipt)
        try:
            _execute_stage(planned_stage, plan, env)
        except KeyboardInterrupt:
            if planned_stage["effect"] == "external_write":
                stage_receipt["recovery"] = (
                    "redacted_indeterminate_external_write; verify target manually"
                )
                receipt["status"] = "in_progress"
                _write_receipt(receipt_path, receipt)
                raise
            stage_receipt["status"] = "failed"
            stage_receipt["finished_at"] = _utc_now()
            stage_receipt["recovery"] = "redacted_failure; inspect console and use --resume"
            receipt["status"] = "failed"
            _write_receipt(receipt_path, receipt)
            raise
        except (Exception, SystemExit):
            stage_receipt["status"] = "failed"
            stage_receipt["finished_at"] = _utc_now()
            stage_receipt["recovery"] = "redacted_failure; inspect console and use --resume"
            receipt["status"] = "failed"
            _write_receipt(receipt_path, receipt)
            raise
        stage_receipt["status"] = "succeeded"
        stage_receipt["finished_at"] = _utc_now()
        stage_receipt.pop("recovery", None)
        _write_receipt(receipt_path, receipt)
    receipt["status"] = "succeeded"
    _write_receipt(receipt_path, receipt)
    return receipt, receipt_path


def _render_plan_text(plan: dict[str, Any], plan_path: Path | None) -> str:
    project = plan["project"]
    parameters = plan["parameters"]
    lines = [
        "Dry-run deployment plan; no project files or commands were changed.",
        f"Plan schema: {plan['schema_version']}",
        f"Plan hash: {plan['plan_hash']}",
        f"Input hash: {plan['inputs']['initial']['hash']}",
        f"Project: {project['name']} ({project['old_version']} -> {project['new_version']})",
        f"Dist: {parameters['dist']} (project-relative)",
        f"Target: {parameters['target_url']}",
        f"Folder key: {parameters['folder_key'] or '[MISSING - EXECUTION BLOCKED]'}",
        "Stages:",
    ]
    for stage in plan["stages"]:
        detail = shlex.join(stage["command"]) if "command" in stage else stage["action"]
        lines.append(f"  - {stage['name']} [{stage['effect']}]: {detail}")
    if plan["execution"]["blockers"]:
        lines.append("Blockers: " + "; ".join(plan["execution"]["blockers"]))
    if plan_path is None:
        lines.append("Execution requires a persisted plan; regenerate with --plan-output <file>.")
    else:
        lines.append(
            f"Execute only after approval: {shlex.join([sys.executable, __file__, '--plan', str(plan_path), '--execute'])}"
        )
    return "\n".join(lines)


def _emit_plan(plan: dict[str, Any], output_format: str, plan_path: Path | None) -> None:
    if output_format == "json":
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        print(_render_plan_text(plan, plan_path))


def _emit_result(plan: dict[str, Any], receipt_path: Path, output_format: str) -> None:
    result = {
        "kind": RESULT_KIND,
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": "succeeded",
        "plan_hash": plan["plan_hash"],
        "receipt": str(receipt_path),
        "old_version": plan["project"]["old_version"],
        "new_version": plan["project"]["new_version"],
        "target_url": plan["parameters"]["target_url"],
    }
    if output_format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            f"Deployment completed for {plan['project']['name']} "
            f"{plan['project']['new_version']}; redacted receipt: {receipt_path}"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a hashed plan, then pack, publish, and deploy a UiPath coded app."
    )
    parser.add_argument("--project-root", help="Project root containing pyproject.toml and uipath.json")
    parser.add_argument("--target-url", help="UiPath HTTPS origin; defaults to https://alpha.uipath.com")
    parser.add_argument("--tenant-name")
    parser.add_argument("--tenant-id")
    parser.add_argument("--org-id")
    parser.add_argument("--org-name")
    parser.add_argument("--part", choices=("patch", "minor", "major"))
    parser.add_argument("--set-version", help="Explicit SemVer with greater precedence than the current version")
    parser.add_argument("--folder-key", help="Mandatory UiPath folder GUID for executable plans")
    parser.add_argument("--app-dist", help="Project-relative built app directory")
    parser.add_argument("--package-name")
    parser.add_argument("--app-name")
    parser.add_argument("--app-type", choices=("Web", "Action"))
    parser.add_argument("--main-file", help="Project-relative main file inside app dist")
    parser.add_argument("--content-type")
    parser.add_argument("--author")
    parser.add_argument("--description")
    parser.add_argument("--reuse-client", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-app-build", action="store_true")
    parser.add_argument("--verify-url", help="Optional HTTPS endpoint checked after deploy")
    parser.add_argument("--verify-timeout", type=int, help="Verification timeout in seconds (1-120)")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--plan-output", help="Atomically persist the generated version 1.0 JSON plan")
    parser.add_argument("--plan", help="Load a persisted version 1.0 JSON plan")
    parser.add_argument("--execute", action="store_true", help="Execute a validated --plan; required for all deploy writes")
    parser.add_argument("--resume", action="store_true", help="Resume from the plan's redacted sibling receipt")

    parser.add_argument("--folder", help=argparse.SUPPRESS)
    parser.add_argument("--tenant", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--my-workspace", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--pack-nolock", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--use-deploy-command", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--offline", action="store_true", help=argparse.SUPPRESS)
    return parser


def _reject_plan_overrides(args: argparse.Namespace) -> None:
    generation_values = {
        "--project-root": args.project_root,
        "--target-url": args.target_url,
        "--tenant-name": args.tenant_name,
        "--tenant-id": args.tenant_id,
        "--org-id": args.org_id,
        "--org-name": args.org_name,
        "--part": args.part,
        "--set-version": args.set_version,
        "--folder-key": args.folder_key,
        "--app-dist": args.app_dist,
        "--package-name": args.package_name,
        "--app-name": args.app_name,
        "--app-type": args.app_type,
        "--main-file": args.main_file,
        "--content-type": args.content_type,
        "--author": args.author,
        "--description": args.description,
        "--verify-url": args.verify_url,
        "--verify-timeout": args.verify_timeout,
        "--reuse-client": args.reuse_client,
        "--skip-tests": args.skip_tests,
        "--skip-app-build": args.skip_app_build,
        "--plan-output": args.plan_output,
    }
    supplied = [name for name, value in generation_values.items() if value not in (None, False)]
    if supplied:
        _fail(
            "A persisted plan is immutable; these planning options cannot accompany --plan: "
            + ", ".join(supplied)
            + ". Regenerate the plan instead."
        )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _legacy_failure(args)
    if args.resume and (not args.plan or not args.execute):
        _fail("--resume requires both --plan <file> and --execute.")
    if args.execute and not args.plan:
        _fail(
            "Direct --execute is prohibited. Migration: generate a reviewed plan with "
            "--plan-output <file>, then run --plan <file> --execute."
        )

    if args.plan:
        _reject_plan_overrides(args)
        plan_path = Path(args.plan).expanduser().resolve()
        plan = _load_plan(plan_path)
        if not args.execute:
            _validate_current_inputs(plan, allow_versioned=True)
            _emit_plan(plan, args.format, plan_path)
            return 0
        _, receipt_path = _execute_plan(plan, plan_path, resume=args.resume)
        _emit_result(plan, receipt_path, args.format)
        return 0

    if args.resume:
        _fail("--resume requires --plan <file> --execute.")
    plan = _build_plan(args)
    plan_path = None
    if args.plan_output:
        plan_path = Path(args.plan_output).expanduser().resolve()
        _validate_plan_output_path(plan_path, plan)
        _atomic_write_json(plan_path, plan)
        _log(f"Wrote deployment plan: {plan_path}")
    _emit_plan(plan, args.format, plan_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
