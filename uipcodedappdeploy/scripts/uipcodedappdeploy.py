#!/usr/bin/env python3
"""Plan and execute a fail-closed UiPath coded app deployment."""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit


PLAN_KIND = "uipcodedappdeploy.plan"
PLAN_SCHEMA_VERSION = "2.0"
RECEIPT_KIND = "uipcodedappdeploy.receipt"
RECEIPT_SCHEMA_VERSION = "2.0"
RESULT_KIND = "uipcodedappdeploy.result"
RESULT_SCHEMA_VERSION = "1.0"
STAGING_CONTROL_PLANE_URL = "https://staging.uipath.com"
PACKAGE_DIGEST_ALGORITHM = "uipath-coded-app-content-v1"
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SOURCE_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
PATH_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CORE_PROPERTIES_RE = re.compile(
    r"^package/services/metadata/core-properties/[^/]+\.psmdcp$"
)
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
    "candidate_package_file_digest",
    "cli_executable",
    "cli_executable_sha256",
    "cli_profile",
    "cli_profile_hash",
    "cli_version",
    "client_id",
    "content_type",
    "control_plane_url",
    "description",
    "dist",
    "dist_digest",
    "folder_key",
    "main_file",
    "org_id",
    "org_name",
    "package_name",
    "package_digest",
    "package_digest_algorithm",
    "package_path",
    "path_name",
    "run_app_build",
    "run_lock",
    "run_tests",
    "source_sha",
    "tags",
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


def _load_uipath_json(path: Path) -> dict[str, Any]:
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


def _validate_hash(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    value = _safe_text(value, label)
    if HASH_RE.fullmatch(value) is None:
        _fail(f"{label} must be a sha256:<64 lowercase hex characters> value.")
    return value


def _validate_source_sha(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    value = _safe_text(value, label).lower()
    if SOURCE_SHA_RE.fullmatch(value) is None:
        _fail(f"{label} must be a full 40- or 64-character lowercase source commit SHA.")
    return value


def _normalize_tags(value: str | None, label: str) -> list[str]:
    if value is None:
        return []
    tags = []
    seen = set()
    for raw in value.split(","):
        tag = raw.strip().lower()
        if not tag or PATH_NAME_RE.fullmatch(tag) is None:
            _fail(f"{label} must be a comma-separated list of lowercase slug values.")
        if tag not in seen:
            tags.append(tag)
            seen.add(tag)
    return sorted(tags)


def _hash_file(path: Path, label: str) -> str:
    if not path.is_file():
        _fail(f"{label} is not a regular file: {path}")
    try:
        return _hash_bytes(path.read_bytes())
    except OSError as exc:
        _fail(f"Could not hash {label} {path}: {exc}")


def _package_evidence(
    path: Path,
    *,
    package_name: str,
    main_file: str,
) -> tuple[str, str]:
    """Return deterministic coded-app content and exact package-file digests."""
    if not path.is_file():
        _fail(f"UiPath candidate package is not a regular file: {path}")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        _fail(f"Could not read UiPath package {path}: {exc}")
    file_digest = _hash_bytes(payload)
    expected_nuspec = f"{package_name}.nuspec"
    expected_main = f"content/{main_file}"
    records: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    envelope_paths: set[str] = set()
    core_property_paths: set[str] = set()
    generated_project_ids: dict[str, str] = {}
    relationships_payload: bytes | None = None
    try:
        with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
            bad_member = archive.testzip()
            if bad_member is not None:
                _fail(f"UiPath package contains a corrupt ZIP member: {bad_member}")
            for member in archive.infolist():
                name = member.filename
                if (
                    not name
                    or "\\" in name
                    or "\x00" in name
                    or PurePosixPath(name).is_absolute()
                    or ".." in PurePosixPath(name).parts
                ):
                    _fail(f"UiPath package contains an unsafe member path: {name!r}")
                if member.is_dir():
                    continue
                if name in seen_paths:
                    _fail(f"UiPath package contains a duplicate member path: {name}")
                seen_paths.add(name)
                unix_mode = (member.external_attr >> 16) & 0o170000
                if unix_mode == stat.S_IFLNK:
                    _fail(f"UiPath package contains an unsupported symbolic link: {name}")
                if member.flag_bits & 0x1:
                    _fail(f"UiPath package contains an encrypted member: {name}")
                member_payload = archive.read(member)
                if name == "[Content_Types].xml":
                    envelope_paths.add(name)
                    records.append(
                        {
                            "path": name,
                            "size": len(member_payload),
                            "sha256": _hash_bytes(member_payload),
                        }
                    )
                    continue
                if name == "_rels/.rels":
                    envelope_paths.add(name)
                    relationships_payload = member_payload
                    continue
                if CORE_PROPERTIES_RE.fullmatch(name):
                    core_property_paths.add(name)
                    records.append(
                        {
                            "path": (
                                "package/services/metadata/core-properties/"
                                "<generated>.psmdcp"
                            ),
                            "size": len(member_payload),
                            "sha256": _hash_bytes(member_payload),
                        }
                    )
                    continue
                if name != expected_nuspec and not name.startswith("content/"):
                    _fail(f"UiPath package contains an unexpected member: {name}")
                digest_payload = member_payload
                if name in {"content/operate.json", "content/webAppManifest.json"}:
                    try:
                        generated_metadata = json.loads(member_payload.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        _fail(f"UiPath package contains invalid generated metadata: {name}")
                    project_id = (
                        generated_metadata.get("projectId")
                        if isinstance(generated_metadata, dict)
                        else None
                    )
                    if (
                        not isinstance(project_id, str)
                        or GUID_RE.fullmatch(project_id) is None
                    ):
                        _fail(f"UiPath package generated metadata lacks a project GUID: {name}")
                    generated_project_ids[name] = project_id.lower()
                    generated_metadata["projectId"] = "<generated-by-uip-cli>"
                    digest_payload = _canonical_json(generated_metadata)
                records.append(
                    {
                        "path": name,
                        "size": len(digest_payload),
                        "sha256": _hash_bytes(digest_payload),
                    }
                )
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        _fail(f"UiPath package is not a readable ZIP archive: {type(exc).__name__}")
    if envelope_paths != {"[Content_Types].xml", "_rels/.rels"}:
        _fail("UiPath package is missing its required NuGet envelope.")
    if len(core_property_paths) != 1:
        _fail("UiPath package must contain exactly one NuGet core-properties record.")
    assert relationships_payload is not None
    core_property_path = next(iter(core_property_paths))
    try:
        relationships_root = ET.fromstring(relationships_payload)
    except ET.ParseError:
        _fail("UiPath package contains invalid NuGet relationship metadata.")
    expected_relationships = {
        (
            "http://schemas.microsoft.com/packaging/2010/07/manifest",
            f"/{expected_nuspec}",
        ),
        (
            "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties",
            f"/{core_property_path}",
        ),
    }
    observed_relationships: set[tuple[str, str]] = set()
    for relationship in relationships_root:
        if relationship.tag.rsplit("}", 1)[-1] != "Relationship":
            _fail("UiPath package contains an unexpected NuGet relationship element.")
        if set(relationship.attrib) != {"Type", "Target", "Id"}:
            _fail("UiPath package contains unsupported NuGet relationship attributes.")
        observed_relationships.add(
            (relationship.attrib["Type"], relationship.attrib["Target"])
        )
    if observed_relationships != expected_relationships:
        _fail("UiPath package NuGet relationships do not match its coded-app payload.")
    normalized_relationships = [
        {
            "type": relationship_type,
            "target": (
                "/package/services/metadata/core-properties/<generated>.psmdcp"
                if relationship_type.endswith("/core-properties")
                else target
            ),
        }
        for relationship_type, target in sorted(observed_relationships)
    ]
    normalized_relationships_payload = _canonical_json(
        {"relationships": normalized_relationships}
    )
    records.append(
        {
            "path": "_rels/.rels",
            "size": len(normalized_relationships_payload),
            "sha256": _hash_bytes(normalized_relationships_payload),
        }
    )
    if set(generated_project_ids) != {
        "content/operate.json",
        "content/webAppManifest.json",
    } or len(set(generated_project_ids.values())) != 1:
        _fail("UiPath package generated project IDs are missing or inconsistent.")
    record_paths = {record["path"] for record in records}
    if expected_nuspec not in record_paths:
        _fail(f"UiPath package is missing its expected manifest: {expected_nuspec}")
    if expected_main not in record_paths:
        _fail(f"UiPath package is missing its expected coded-app entry point: {expected_main}")
    records.sort(key=lambda record: record["path"])
    content_digest = _hash_json(
        {
            "algorithm": PACKAGE_DIGEST_ALGORITHM,
            "files": records,
        }
    )
    return content_digest, file_digest


def _resolve_cli_executable(value: str | None) -> tuple[str | None, str | None]:
    candidate = value or shutil.which("uip")
    if candidate is None:
        return None, None
    path = Path(candidate).expanduser().resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        _fail(f"--cli-executable must resolve to an executable file: {path}")
    return str(path), _hash_file(path, "UiPath CLI executable")


def _directory_digest(root: Path, relative: str) -> str | None:
    directory = root / relative
    if not directory.exists():
        return None
    if not directory.is_dir() or directory.is_symlink():
        _fail(f"Coded app dist must be a real directory, not a symlink: {directory}")
    records: list[dict[str, Any]] = []
    for path in sorted(directory.rglob("*"), key=lambda item: item.relative_to(directory).as_posix()):
        if path.is_symlink():
            _fail(f"Coded app dist may not contain symlinks: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            _fail(f"Coded app dist contains an unsupported filesystem entry: {path}")
        records.append(
            {
                "path": path.relative_to(directory).as_posix(),
                "mode": path.stat().st_mode & 0o777,
                "size": path.stat().st_size,
                "sha256": _hash_file(path, "coded app dist file"),
            }
        )
    if not records:
        _fail(f"Coded app dist contains no files: {directory}")
    return _hash_json({"files": records})


def _package_path(package_name: str, version: str) -> str:
    return f".uipath/{package_name}.{version}.nupkg"


def _remote_auth_flags(
    parameters: dict[str, Any], *, publish: bool, deploy: bool
) -> list[str]:
    flags = [
        "--base-url",
        parameters["control_plane_url"] or "[MISSING_CONTROL_PLANE_URL]",
    ]
    if parameters["org_id"]:
        flags.extend(["--org-id", parameters["org_id"]])
    if deploy and parameters["org_name"]:
        flags.extend(["--org-name", parameters["org_name"]])
    if parameters["tenant_id"]:
        flags.extend(["--tenant-id", parameters["tenant_id"]])
    if publish and parameters["tenant_name"]:
        flags.extend(["--tenant-name", parameters["tenant_name"]])
    flags.extend(
        ["--profile", parameters["cli_profile"] or "[MISSING_CLI_PROFILE]"]
    )
    return flags


def _execution_blockers(parameters: dict[str, Any]) -> list[str]:
    blockers = []
    if parameters["control_plane_url"] != STAGING_CONTROL_PLANE_URL:
        blockers.append(
            f"Explicit --control-plane-url {STAGING_CONTROL_PLANE_URL} is mandatory."
        )
    if not parameters["folder_key"]:
        blockers.append("A valid --folder-key is mandatory before execution.")
    required_release_bindings = (
        ("--org-id", parameters["org_id"]),
        ("--tenant-id", parameters["tenant_id"]),
        ("--path-name", parameters["path_name"]),
        ("--client-id", parameters["client_id"]),
        ("--tags", parameters["tags"]),
        ("--source-sha", parameters["source_sha"]),
        ("--dist-digest or a built dist", parameters["dist_digest"]),
        ("a prepacked candidate package", parameters["candidate_package_file_digest"]),
        ("--package-digest or a prepacked candidate", parameters["package_digest"]),
        (
            "--cli-executable or a resolvable uip",
            parameters["cli_executable"],
        ),
        ("--cli-version", parameters["cli_version"]),
        ("--cli-profile", parameters["cli_profile"]),
    )
    for label, value in required_release_bindings:
        if not value:
            blockers.append(f"{label} is mandatory before execution.")
    return blockers


def _build_stages(project: dict[str, Any], parameters: dict[str, Any]) -> list[dict[str, Any]]:
    cli = parameters["cli_executable"] or "[MISSING_CLI_EXECUTABLE]"
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
                "name": "source",
                "action": "validate_source",
                "effect": "local_read",
            },
            {
                "name": "uip_probe",
                "action": "validate_cli",
                "effect": "local_read",
            },
        ]
    )
    pack_command = [
        cli,
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
    ]
    if parameters["description"]:
        pack_command.extend(["--description", parameters["description"]])
    if parameters["source_sha"]:
        pack_command.extend(["--repository-commit", parameters["source_sha"]])
    publish_command = [
        cli,
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
        *_remote_auth_flags(parameters, publish=True, deploy=False),
    ]
    deploy_command = [
        cli,
        "codedapp",
        "deploy",
        "--name",
        parameters["app_name"],
        "--version",
        project["new_version"],
        "--path-name",
        parameters["path_name"] or "[MISSING_PATH_NAME]",
        "--client-id",
        parameters["client_id"] or "[MISSING_CLIENT_ID]",
        "--tags",
        ",".join(parameters["tags"]),
        *_remote_auth_flags(parameters, publish=False, deploy=True),
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
                "name": "package",
                "action": "validate_package",
                "effect": "local_read",
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
            args.target_url,
            "--target-url is ambiguous and rejected. Migration: pass the CLI control "
            "plane explicitly with --control-plane-url.",
        ),
        (
            args.reuse_client,
            "--reuse-client is unsupported by codedapp pack and is rejected. Migration: "
            "bind the dedicated public OAuth client with --client-id for codedapp deploy.",
        ),
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
    _load_uipath_json(uipath_path)
    metadata = _project_metadata(pyproject)
    old_version = metadata["version"]
    if args.set_version and args.part:
        _fail("Use either --set-version or --part, not both.")
    new_version = args.set_version or _next_version(old_version, args.part or "patch")
    _validate_progression(old_version, new_version)

    raw_dist = args.app_dist or _default_dist(root)
    dist = _project_relative_path(root, raw_dist, "--app-dist")
    main_file = _safe_relative_literal(args.main_file or "index.html", "--main-file")
    control_plane_url = None
    if args.control_plane_url is not None:
        control_plane_url = _validate_url(
            args.control_plane_url,
            "--control-plane-url",
            base_only=True,
        )
        if control_plane_url != STAGING_CONTROL_PLANE_URL:
            _fail(
                f"--control-plane-url must be the explicit staging origin "
                f"{STAGING_CONTROL_PLANE_URL}; alpha and implicit/default targets are rejected."
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
    path_name = (
        _safe_text(args.path_name, "--path-name").lower() if args.path_name else None
    )
    if path_name and PATH_NAME_RE.fullmatch(path_name) is None:
        _fail("--path-name must be a lowercase URL slug.")
    client_id = _safe_text(args.client_id, "--client-id") if args.client_id else None
    if client_id and GUID_RE.fullmatch(client_id) is None:
        _fail("--client-id must be the GUID of a non-confidential UiPath OAuth client.")
    tags = _normalize_tags(args.tags, "--tags")
    source_sha = _validate_source_sha(args.source_sha, "--source-sha")
    for label, value in (("--org-id", args.org_id), ("--tenant-id", args.tenant_id)):
        if value is not None and GUID_RE.fullmatch(value) is None:
            _fail(f"{label} must be an exact UiPath GUID.")
    planned_dist_digest = _validate_hash(args.dist_digest, "--dist-digest")
    observed_dist_digest = _directory_digest(root, dist)
    if (
        planned_dist_digest is not None
        and observed_dist_digest is not None
        and planned_dist_digest != observed_dist_digest
    ):
        _fail("--dist-digest does not match the current coded app dist.")
    dist_digest = planned_dist_digest or observed_dist_digest
    planned_package_digest = _validate_hash(args.package_digest, "--package-digest")
    package_path = _package_path(package_name, new_version)
    candidate_package = root / package_path
    observed_package_digest = None
    candidate_package_file_digest = None
    if candidate_package.exists():
        observed_package_digest, candidate_package_file_digest = _package_evidence(
            candidate_package,
            package_name=package_name,
            main_file=main_file,
        )
    if (
        planned_package_digest is not None
        and observed_package_digest is not None
        and planned_package_digest != observed_package_digest
    ):
        _fail("--package-digest does not match the candidate package content.")
    package_digest = planned_package_digest or observed_package_digest
    cli_executable, cli_executable_sha256 = _resolve_cli_executable(
        args.cli_executable
    )
    cli_version = (
        _safe_text(args.cli_version, "--cli-version") if args.cli_version else None
    )
    if cli_version:
        _parse_semver(cli_version, "--cli-version")
    cli_profile = (
        _safe_text(args.cli_profile, "--cli-profile") if args.cli_profile else None
    )
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
    cli_profile_hash = (
        _hash_json(
            {
                "name": cli_profile,
                "control_plane_url": control_plane_url,
                "org_id": args.org_id,
                "tenant_id": args.tenant_id,
            }
        )
        if cli_profile
        else None
    )
    parameters = {
        "control_plane_url": control_plane_url,
        "tenant_name": args.tenant_name,
        "tenant_id": args.tenant_id,
        "org_id": args.org_id,
        "org_name": args.org_name,
        "folder_key": folder_key,
        "dist": dist,
        "dist_digest": dist_digest,
        "uipath_dir": ".uipath",
        "package_name": package_name,
        "package_path": package_path,
        "package_digest": package_digest,
        "package_digest_algorithm": PACKAGE_DIGEST_ALGORITHM,
        "candidate_package_file_digest": candidate_package_file_digest,
        "app_name": app_name,
        "app_type": args.app_type or "Web",
        "path_name": path_name,
        "client_id": client_id,
        "tags": tags,
        "main_file": main_file,
        "content_type": content_type,
        "author": author,
        "description": description,
        "source_sha": source_sha,
        "cli_executable": cli_executable,
        "cli_executable_sha256": cli_executable_sha256,
        "cli_version": cli_version,
        "cli_profile": cli_profile,
        "cli_profile_hash": cli_profile_hash,
        "run_lock": (root / "uv.lock").is_file(),
        "run_tests": not args.skip_tests,
        "run_app_build": (
            not args.skip_app_build and (root / "app" / "package.json").is_file()
        ),
        "verify_url": verify_url,
        "verify_timeout": verify_timeout,
    }
    deployment_binding = {
        "cli_profile_hash": cli_profile_hash,
        "cli_executable_sha256": cli_executable_sha256,
        "control_plane_url": control_plane_url,
        "org_id": args.org_id,
        "tenant_id": args.tenant_id,
        "path_name": path_name,
        "client_id": client_id,
        "tags": tags,
        "source_sha": source_sha,
        "dist_digest": dist_digest,
        "package_digest": package_digest,
        "package_digest_algorithm": PACKAGE_DIGEST_ALGORITHM,
        "candidate_package_file_digest": candidate_package_file_digest,
    }
    blockers = _execution_blockers(parameters)
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
        "deployment_binding_hash": _hash_json(deployment_binding),
        "stages": _build_stages(project, parameters),
        "execution": {
            "requires_execute": True,
            "requires_plan": True,
            "requires_plan_hash_approval": True,
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
        _fail(f"Plan parameters do not match schema version {PLAN_SCHEMA_VERSION}.")
    control_plane_url = parameters["control_plane_url"]
    if control_plane_url is not None:
        if (
            _validate_url(
                control_plane_url,
                "Plan control_plane_url",
                base_only=True,
            )
            != control_plane_url
        ):
            _fail("Plan control_plane_url is not normalized.")
        if control_plane_url != STAGING_CONTROL_PLANE_URL:
            _fail("Plan control_plane_url is not the supported staging origin.")
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
    for field in (
        "dist_digest",
        "package_digest",
        "candidate_package_file_digest",
        "cli_executable_sha256",
        "cli_profile_hash",
    ):
        if parameters[field] is not None:
            _validate_hash(parameters[field], f"Plan {field}")
    if parameters["uipath_dir"] != ".uipath":
        _fail("Plan uipath_dir must be the project-relative .uipath directory.")
    if parameters["package_digest_algorithm"] != PACKAGE_DIGEST_ALGORITHM:
        _fail("Plan package_digest_algorithm is unsupported.")
    if _safe_relative_literal(parameters["main_file"], "Plan main_file") != parameters[
        "main_file"
    ]:
        _fail("Plan main_file is not normalized.")
    for field in ("package_name", "app_name", "author", "content_type"):
        _safe_text(parameters[field], f"Plan {field}")
    _safe_relative_literal(parameters["package_path"], "Plan package_path")
    _safe_text(parameters["description"], "Plan description", allow_empty=True)
    if parameters["app_type"] not in ("Web", "Action"):
        _fail("Plan app_type must be Web or Action.")
    for field in ("run_lock", "run_tests", "run_app_build"):
        if not isinstance(parameters[field], bool):
            _fail(f"Plan {field} must be a boolean.")
    for field in (
        "path_name",
        "client_id",
        "source_sha",
        "cli_executable",
        "cli_version",
        "cli_profile",
    ):
        value = parameters[field]
        if value is not None:
            _safe_text(value, f"Plan {field}")
    if parameters["path_name"] is not None and PATH_NAME_RE.fullmatch(
        parameters["path_name"]
    ) is None:
        _fail("Plan path_name must be a lowercase URL slug.")
    if parameters["client_id"] is not None and GUID_RE.fullmatch(
        parameters["client_id"]
    ) is None:
        _fail("Plan client_id must be a GUID.")
    for field in ("org_id", "tenant_id"):
        value = parameters[field]
        if value is not None and GUID_RE.fullmatch(value) is None:
            _fail(f"Plan {field} must be an exact UiPath GUID.")
    _validate_source_sha(parameters["source_sha"], "Plan source_sha")
    if parameters["cli_version"] is not None:
        _parse_semver(parameters["cli_version"], "Plan cli_version")
    if parameters["cli_executable"] is not None:
        executable = Path(parameters["cli_executable"])
        if not executable.is_absolute() or executable.resolve() != executable:
            _fail("Plan cli_executable must be a canonical absolute path.")
    tags = parameters["tags"]
    if (
        not isinstance(tags, list)
        or tags != sorted(set(tags))
        or any(not isinstance(tag, str) or PATH_NAME_RE.fullmatch(tag) is None for tag in tags)
    ):
        _fail("Plan tags must be a sorted unique array of lowercase slug values.")
    expected_profile_hash = (
        _hash_json(
            {
                "name": parameters["cli_profile"],
                "control_plane_url": parameters["control_plane_url"],
                "org_id": parameters["org_id"],
                "tenant_id": parameters["tenant_id"],
            }
        )
        if parameters["cli_profile"]
        else None
    )
    if parameters["cli_profile_hash"] != expected_profile_hash:
        _fail("Plan cli_profile_hash does not match its safe profile binding.")
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
        "deployment_binding_hash",
        "stages",
        "execution",
        "plan_hash",
    }
    if not isinstance(plan, dict) or set(plan) != expected_keys:
        _fail(
            f"Deployment plan does not match the version {PLAN_SCHEMA_VERSION} document shape."
        )
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
        _fail(f"Plan project metadata does not match schema version {PLAN_SCHEMA_VERSION}.")
    root = Path(_safe_text(project["root"], "Plan project.root"))
    if not root.is_absolute() or root.resolve() != root:
        _fail("Plan project.root must be a canonical absolute path.")
    if project["manifest"] != "pyproject.toml" or project["uipath_manifest"] != "uipath.json":
        _fail("Plan manifest paths must remain project-relative canonical names.")
    _safe_text(project["name"], "Plan project.name")
    _validate_progression(project["old_version"], project["new_version"])

    inputs = plan["inputs"]
    if not isinstance(inputs, dict) or set(inputs) != {"scope", "initial", "versioned"}:
        _fail(f"Plan inputs do not match schema version {PLAN_SCHEMA_VERSION}.")
    if inputs["scope"] != ["pyproject.toml", "uipath.json"]:
        _fail("Plan input hash scope must be pyproject.toml and uipath.json.")
    _validate_snapshot(inputs["initial"], "Plan inputs.initial")
    _validate_snapshot(inputs["versioned"], "Plan inputs.versioned")
    if inputs["initial"]["files"][1] != inputs["versioned"]["files"][1]:
        _fail("Plan versioning must not alter the uipath.json input hash.")

    _validate_parameters(root, plan["parameters"])
    if plan["parameters"]["package_path"] != _package_path(
        plan["parameters"]["package_name"], project["new_version"]
    ):
        _fail("Plan package_path does not match the package name and version.")
    deployment_binding = {
        "cli_profile_hash": plan["parameters"]["cli_profile_hash"],
        "cli_executable_sha256": plan["parameters"]["cli_executable_sha256"],
        "control_plane_url": plan["parameters"]["control_plane_url"],
        "org_id": plan["parameters"]["org_id"],
        "tenant_id": plan["parameters"]["tenant_id"],
        "path_name": plan["parameters"]["path_name"],
        "client_id": plan["parameters"]["client_id"],
        "tags": plan["parameters"]["tags"],
        "source_sha": plan["parameters"]["source_sha"],
        "dist_digest": plan["parameters"]["dist_digest"],
        "package_digest": plan["parameters"]["package_digest"],
        "package_digest_algorithm": plan["parameters"]["package_digest_algorithm"],
        "candidate_package_file_digest": plan["parameters"][
            "candidate_package_file_digest"
        ],
    }
    if (
        not isinstance(plan["deployment_binding_hash"], str)
        or plan["deployment_binding_hash"] != _hash_json(deployment_binding)
    ):
        _fail("Plan deployment_binding_hash does not match the release provenance.")
    expected_stages = _build_stages(project, plan["parameters"])
    if plan["stages"] != expected_stages:
        _fail("Plan stages do not match the allowlisted command sequence. Regenerate the plan.")
    blockers = _execution_blockers(plan["parameters"])
    expected_execution = {
        "requires_execute": True,
        "requires_plan": True,
        "requires_plan_hash_approval": True,
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
    _load_uipath_json(root / "uipath.json")
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


def _new_receipt(
    plan: dict[str, Any], approved_plan_hash: str | None = None
) -> dict[str, Any]:
    approved_plan_hash = approved_plan_hash or plan["plan_hash"]
    receipt = {
        "kind": RECEIPT_KIND,
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "plan_hash": plan["plan_hash"],
        "approved_plan_hash": approved_plan_hash,
        "input_hash": plan["inputs"]["initial"]["hash"],
        "deployment_binding_hash": plan["deployment_binding_hash"],
        "cli_profile_hash": plan["parameters"]["cli_profile_hash"],
        "cli_executable_sha256": plan["parameters"]["cli_executable_sha256"],
        "source_sha": plan["parameters"]["source_sha"],
        "dist_digest": plan["parameters"]["dist_digest"],
        "package_digest": plan["parameters"]["package_digest"],
        "package_digest_algorithm": plan["parameters"]["package_digest_algorithm"],
        "candidate_package_file_digest": plan["parameters"][
            "candidate_package_file_digest"
        ],
        "package_file_digest": None,
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
        "approved_plan_hash",
        "input_hash",
        "deployment_binding_hash",
        "cli_profile_hash",
        "cli_executable_sha256",
        "source_sha",
        "dist_digest",
        "package_digest",
        "package_digest_algorithm",
        "candidate_package_file_digest",
        "package_file_digest",
        "status",
        "started_at",
        "updated_at",
        "redaction",
        "stages",
        "receipt_hash",
    }
    if not isinstance(receipt, dict) or set(receipt) != expected_keys:
        _fail(
            f"Resume receipt does not match the version {RECEIPT_SCHEMA_VERSION} document shape."
        )
    if receipt["kind"] != RECEIPT_KIND or receipt["schema_version"] != RECEIPT_SCHEMA_VERSION:
        _fail("Unsupported receipt schema. Start from a newly generated plan.")
    if receipt["receipt_hash"] != _document_hash(receipt, "receipt_hash"):
        _fail("Receipt hash mismatch; the receipt was edited or corrupted.")
    if receipt["plan_hash"] != plan["plan_hash"]:
        _fail("Receipt belongs to a different deployment plan.")
    if receipt["approved_plan_hash"] != plan["plan_hash"]:
        _fail("Receipt does not record approval of this exact deployment plan hash.")
    if receipt["input_hash"] != plan["inputs"]["initial"]["hash"]:
        _fail("Receipt input hash does not match the deployment plan.")
    expected_provenance = {
        "deployment_binding_hash": plan["deployment_binding_hash"],
        "cli_profile_hash": plan["parameters"]["cli_profile_hash"],
        "cli_executable_sha256": plan["parameters"]["cli_executable_sha256"],
        "source_sha": plan["parameters"]["source_sha"],
        "dist_digest": plan["parameters"]["dist_digest"],
        "package_digest": plan["parameters"]["package_digest"],
        "package_digest_algorithm": plan["parameters"]["package_digest_algorithm"],
        "candidate_package_file_digest": plan["parameters"][
            "candidate_package_file_digest"
        ],
    }
    for field, expected in expected_provenance.items():
        if receipt[field] != expected:
            _fail(f"Receipt {field} does not match the deployment plan.")
    package_file_digest = receipt["package_file_digest"]
    if package_file_digest is not None:
        _validate_hash(package_file_digest, "Receipt package_file_digest")
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
    package_stage = next(
        stage for stage in receipt["stages"] if stage["name"] == "package"
    )
    if package_stage["status"] == "succeeded" and package_file_digest is None:
        _fail("Receipt is missing the exact package file digest verified before publish.")
    if package_stage["status"] != "succeeded" and package_file_digest is not None:
        _fail("Receipt records a package file digest before package validation succeeded.")
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
        if (
            stage["status"] in ("running", "failed")
            and stage["effect"] == "external_write"
        ):
            _fail(
                f"Cannot resume: external-write stage {stage['name']!r} has an indeterminate "
                "outcome. Reconcile remote state manually before creating a reviewed "
                "recovery plan; blind retry is prohibited."
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
    observed_digest = _directory_digest(root, parameters["dist"])
    if observed_digest != parameters["dist_digest"]:
        _fail(
            "Coded app dist digest changed after plan approval; rebuild, rehash, "
            "and regenerate the deployment plan."
        )


def _run_capture(cmd: list[str], cwd: Path) -> str:
    _log("+ " + shlex.join(cmd))
    try:
        completed = subprocess.run(
            cmd,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        _fail(f"Release preflight command failed: {type(exc).__name__}")
    return completed.stdout


def _validate_source(root: Path, parameters: dict[str, Any]) -> None:
    observed = _run_capture(["git", "-C", str(root), "rev-parse", "HEAD"], root).strip()
    if observed != parameters["source_sha"]:
        _fail("Git source SHA does not match the approved deployment plan.")
    dirty = _run_capture(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
        root,
    ).strip()
    if dirty:
        _fail("Tracked source is dirty; commit and regenerate the deployment plan.")


def _find_mapping_value(value: Any, names: set[str]) -> Any:
    if isinstance(value, dict):
        for key, candidate in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if normalized in names:
                return candidate
        for candidate in value.values():
            found = _find_mapping_value(candidate, names)
            if found is not None:
                return found
    elif isinstance(value, list):
        for candidate in value:
            found = _find_mapping_value(candidate, names)
            if found is not None:
                return found
    return None


def _validate_cli(root: Path, parameters: dict[str, Any]) -> None:
    executable = Path(parameters["cli_executable"])
    if _hash_file(executable, "UiPath CLI executable") != parameters[
        "cli_executable_sha256"
    ]:
        _fail("UiPath CLI executable digest changed after plan approval.")
    version_output = _run_capture([str(executable), "--version"], root)
    match = re.search(r"\b([0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?)\b", version_output)
    if match is None or match.group(1) != parameters["cli_version"]:
        _fail("UiPath CLI version does not match the approved deployment plan.")
    status_output = _run_capture(
        [
            str(executable),
            "login",
            "status",
            "--profile",
            parameters["cli_profile"],
            "--output",
            "json",
        ],
        root,
    )
    try:
        status = json.loads(status_output)
    except json.JSONDecodeError:
        _fail("UiPath CLI profile status did not return valid JSON.")
    login_state = _find_mapping_value(status, {"status"})
    if not isinstance(login_state, str) or login_state.lower() not in {
        "loggedin",
        "logged in",
        "authenticated",
    }:
        _fail("UiPath CLI profile is not logged in.")
    comparisons = (
        ("org_id", {"organizationid", "organizationuid"}),
        ("tenant_id", {"tenantid", "tenantuid"}),
    )
    for field, names in comparisons:
        expected = parameters[field]
        if expected is None:
            continue
        observed = _find_mapping_value(status, names)
        if not isinstance(observed, str) or observed.lower() != expected.lower():
            _fail(f"UiPath CLI profile {field} does not match the deployment plan.")


def _validate_package(
    root: Path,
    parameters: dict[str, Any],
    *,
    expected_file_digest: str | None = None,
) -> str:
    package = root / parameters["package_path"]
    observed_content, observed_file = _package_evidence(
        package,
        package_name=parameters["package_name"],
        main_file=parameters["main_file"],
    )
    if observed_content != parameters["package_digest"]:
        _fail(
            "Packed UiPath package content digest does not match the approved plan; "
            "do not publish or deploy it."
        )
    if expected_file_digest is not None and observed_file != expected_file_digest:
        _fail(
            "The exact packed UiPath package changed after package validation; "
            "do not publish or deploy it."
        )
    return observed_file


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


def _execute_stage(
    stage: dict[str, Any], plan: dict[str, Any], env: dict[str, str]
) -> str | None:
    root = Path(plan["project"]["root"])
    if stage["action"] == "write_version":
        _write_version_atomic(
            root / "pyproject.toml",
            plan["project"]["old_version"],
            plan["project"]["new_version"],
        )
        return None
    if stage["action"] == "command":
        cwd = root if stage["cwd"] == "." else root / stage["cwd"]
        _run(stage["command"], cwd, env)
        return None
    if stage["action"] == "validate_dist":
        _validate_dist(root, plan["parameters"])
        return None
    if stage["action"] == "validate_source":
        _validate_source(root, plan["parameters"])
        return None
    if stage["action"] == "validate_cli":
        _validate_cli(root, plan["parameters"])
        return None
    if stage["action"] == "validate_package":
        return _validate_package(root, plan["parameters"])
    if stage["action"] == "verify_url":
        _verify_url(
            plan["parameters"]["verify_url"],
            plan["parameters"]["verify_timeout"],
        )
        return None
    _fail(f"Unsupported stage action: {stage['action']}")


def _execute_plan(
    plan: dict[str, Any],
    plan_path: Path,
    *,
    resume: bool,
    approved_plan_hash: str | None,
) -> tuple[dict[str, Any], Path]:
    if approved_plan_hash != plan["plan_hash"]:
        _fail(
            "Execution requires --approved-plan-hash with the exact persisted plan hash "
            "that a human approved."
        )
    if not plan["execution"]["executable"]:
        _fail("Execution blocked: " + "; ".join(plan["execution"]["blockers"]))
    root = Path(plan["project"]["root"])
    if not plan["parameters"]["run_app_build"]:
        _validate_dist(root, plan["parameters"])
    if not resume:
        _validate_package(
            root,
            plan["parameters"],
            expected_file_digest=plan["parameters"]["candidate_package_file_digest"],
        )
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
        receipt = _new_receipt(plan, approved_plan_hash)
        _write_receipt(receipt_path, receipt)

    env = os.environ.copy()
    for planned_stage, stage_receipt in zip(plan["stages"], receipt["stages"]):
        if stage_receipt["status"] == "succeeded":
            continue
        if planned_stage["name"] == "publish":
            package_file_digest = receipt["package_file_digest"]
            if package_file_digest is None:
                _fail("Cannot publish before the exact packed package file is audited.")
            _validate_package(
                root,
                plan["parameters"],
                expected_file_digest=package_file_digest,
            )
        stage_receipt["status"] = "running"
        stage_receipt["started_at"] = _utc_now()
        stage_receipt.pop("finished_at", None)
        _write_receipt(receipt_path, receipt)
        try:
            stage_result = _execute_stage(planned_stage, plan, env)
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
            if planned_stage["effect"] == "external_write":
                stage_receipt["recovery"] = (
                    "redacted_indeterminate_external_write; reconcile remote state; "
                    "blind resume prohibited"
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
        if planned_stage["name"] == "package":
            if not isinstance(stage_result, str) or HASH_RE.fullmatch(stage_result) is None:
                _fail("Package validation did not return an exact package file digest.")
            receipt["package_file_digest"] = stage_result
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
        f"Dist digest: {parameters['dist_digest'] or '[MISSING - EXECUTION BLOCKED]'}",
        f"Package content digest ({parameters['package_digest_algorithm']}): "
        f"{parameters['package_digest'] or '[MISSING - EXECUTION BLOCKED]'}",
        f"Candidate package file digest: "
        f"{parameters['candidate_package_file_digest'] or '[MISSING - EXECUTION BLOCKED]'}",
        f"Source SHA: {parameters['source_sha'] or '[MISSING - EXECUTION BLOCKED]'}",
        f"CLI: {parameters['cli_executable'] or '[MISSING]'} @ {parameters['cli_version'] or '[MISSING]'}",
        f"CLI profile hash: {parameters['cli_profile_hash'] or '[MISSING - EXECUTION BLOCKED]'}",
        f"Control plane: {parameters['control_plane_url'] or '[MISSING - EXECUTION BLOCKED]'}",
        f"Organization ID: {parameters['org_id'] or '[MISSING - EXECUTION BLOCKED]'}",
        f"Tenant ID: {parameters['tenant_id'] or '[MISSING - EXECUTION BLOCKED]'}",
        f"Package/app: {parameters['package_name']} / {parameters['app_name']}",
        f"Path name: {parameters['path_name'] or '[MISSING - EXECUTION BLOCKED]'}",
        f"Client ID: {parameters['client_id'] or '[MISSING - EXECUTION BLOCKED]'}",
        f"Tags: {','.join(parameters['tags']) or '[MISSING - EXECUTION BLOCKED]'}",
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
            "Execute only after approval: "
            + shlex.join(
                [
                    sys.executable,
                    __file__,
                    "--plan",
                    str(plan_path),
                    "--execute",
                    "--approved-plan-hash",
                    plan["plan_hash"],
                ]
            )
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
        "control_plane_url": plan["parameters"]["control_plane_url"],
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
    parser.add_argument(
        "--control-plane-url",
        help=f"Explicit UiPath staging CLI origin; must be {STAGING_CONTROL_PLANE_URL}",
    )
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
    parser.add_argument("--path-name", help="Exact lowercase app route slug")
    parser.add_argument("--client-id", help="Dedicated non-confidential OAuth client GUID")
    parser.add_argument("--tags", help="Comma-separated lowercase deployment tags")
    parser.add_argument("--source-sha", help="Exact full source commit SHA")
    parser.add_argument("--dist-digest", help="Expected sha256 digest of the built dist")
    parser.add_argument(
        "--package-digest",
        help=(
            "Expected deterministic coded-app content digest of the candidate .nupkg; "
            "computed automatically when the candidate exists"
        ),
    )
    parser.add_argument("--cli-executable", help="Absolute pinned UiPath CLI executable")
    parser.add_argument("--cli-version", help="Exact pinned UiPath CLI SemVer")
    parser.add_argument("--cli-profile", help="Named authenticated UiPath CLI profile")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-app-build", action="store_true")
    parser.add_argument("--verify-url", help="Optional HTTPS endpoint checked after deploy")
    parser.add_argument("--verify-timeout", type=int, help="Verification timeout in seconds (1-120)")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--plan-output",
        help=f"Atomically persist the generated version {PLAN_SCHEMA_VERSION} JSON plan",
    )
    parser.add_argument(
        "--plan",
        help=f"Load a persisted version {PLAN_SCHEMA_VERSION} JSON plan",
    )
    parser.add_argument("--execute", action="store_true", help="Execute a validated --plan; required for all deploy writes")
    parser.add_argument("--resume", action="store_true", help="Resume from the plan's redacted sibling receipt")
    parser.add_argument(
        "--approved-plan-hash",
        help="Exact sha256 plan hash explicitly approved by a human",
    )

    parser.add_argument("--target-url", help=argparse.SUPPRESS)
    parser.add_argument("--reuse-client", action="store_true", help=argparse.SUPPRESS)
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
        "--control-plane-url": args.control_plane_url,
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
        "--path-name": args.path_name,
        "--client-id": args.client_id,
        "--tags": args.tags,
        "--source-sha": args.source_sha,
        "--dist-digest": args.dist_digest,
        "--package-digest": args.package_digest,
        "--cli-executable": args.cli_executable,
        "--cli-version": args.cli_version,
        "--cli-profile": args.cli_profile,
        "--verify-url": args.verify_url,
        "--verify-timeout": args.verify_timeout,
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
    if args.approved_plan_hash and (not args.plan or not args.execute):
        _fail("--approved-plan-hash is accepted only with --plan <file> --execute.")
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
        _, receipt_path = _execute_plan(
            plan,
            plan_path,
            resume=args.resume,
            approved_plan_hash=args.approved_plan_hash,
        )
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
