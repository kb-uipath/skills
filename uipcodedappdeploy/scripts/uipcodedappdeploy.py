#!/usr/bin/env python3
"""
Increment a UiPath coded app package version, then pack/publish/deploy with
the native UiPath CLI coded app commands.

The script is intentionally conservative:
- defaults to dry-run unless --execute is passed
- only edits pyproject.toml after validation succeeds
- never accepts or prints secrets
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


VERSION_RE = re.compile(r"^version\s*=\s*[\"']([^\"']+)[\"']\s*$", re.MULTILINE)
NAME_RE = re.compile(r"^name\s*=\s*[\"']([^\"']+)[\"']\s*$", re.MULTILINE)
DESCRIPTION_RE = re.compile(
    r"^description\s*=\s*[\"']([^\"']*)[\"']\s*$", re.MULTILINE
)
AUTHOR_RE = re.compile(r"authors\s*=\s*\[\{\s*name\s*=\s*[\"']([^\"']+)[\"']")
GUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _run(
    cmd: list[str],
    cwd: Path,
    env: dict[str, str],
    dry_run: bool,
) -> None:
    print("+ " + " ".join(cmd))
    if dry_run:
        return
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def _capture_json(cmd: list[str], cwd: Path, env: dict[str, str]) -> dict:
    print("+ " + " ".join(cmd))
    completed = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"Expected JSON output from {' '.join(cmd)}, got:\n{completed.stdout}"
        ) from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"Expected JSON object from {' '.join(cmd)}")
    return payload


def _read_version(pyproject: Path) -> str:
    text = pyproject.read_text()
    match = VERSION_RE.search(text)
    if match is None:
        raise SystemExit(f"Could not find project version in {pyproject}")
    return match.group(1)


def _read_field(pyproject: Path, regex: re.Pattern[str], fallback: str) -> str:
    text = pyproject.read_text()
    match = regex.search(text)
    return match.group(1) if match else fallback


def _next_version(version: str, part: str) -> str:
    pieces = version.split(".")
    if len(pieces) != 3 or not all(piece.isdigit() for piece in pieces):
        raise SystemExit(
            f"Version '{version}' is not a simple MAJOR.MINOR.PATCH value. "
            "Pass --set-version explicitly."
        )
    major, minor, patch = (int(piece) for piece in pieces)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def _write_version(pyproject: Path, new_version: str, dry_run: bool) -> None:
    text = pyproject.read_text()
    updated, count = VERSION_RE.subn(f'version = "{new_version}"', text, count=1)
    if count != 1:
        raise SystemExit(f"Could not update project version in {pyproject}")
    print(f"Set {pyproject.name} version to {new_version}")
    if not dry_run:
        pyproject.write_text(updated)


def _default_dist(root: Path) -> Path:
    app_dist = root / "app" / "dist"
    if (root / "app" / "package.json").exists() or app_dist.exists():
        return app_dist
    return root / "dist"


def _auth_flags(args: argparse.Namespace, *, publish: bool, deploy: bool) -> list[str]:
    flags = ["--base-url", args.target_url]
    if args.org_id:
        flags.extend(["--org-id", args.org_id])
    if deploy and args.org_name:
        flags.extend(["--org-name", args.org_name])
    if args.tenant_id:
        flags.extend(["--tenant-id", args.tenant_id])
    if publish and args.tenant_name:
        flags.extend(["--tenant-name", args.tenant_name])
    return flags


def _resolve_folder_key(
    folder: str,
    tenant_name: str | None,
    root: Path,
    env: dict[str, str],
) -> str:
    if GUID_RE.match(folder):
        return folder
    cmd = ["uip", "or", "folders", "get", folder, "--output", "json"]
    if tenant_name:
        cmd.extend(["--tenant", tenant_name])
    payload = _capture_json(cmd, cwd=root, env=env)
    data = payload.get("Data")
    if not isinstance(data, dict) or not isinstance(data.get("Key"), str):
        raise SystemExit(f"Could not resolve folder key for {folder!r}")
    return data["Key"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pack, publish, and deploy a UiPath coded app to alpha."
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="UiPath project root containing pyproject.toml",
    )
    parser.add_argument(
        "--target-url",
        default="https://alpha.uipath.com",
        help="UiPath base URL passed to uip codedapp commands",
    )
    parser.add_argument(
        "--tenant-name",
        help="Tenant name passed to codedapp publish and folder lookup",
    )
    parser.add_argument(
        "--tenant-id",
        help="Tenant ID passed to codedapp commands when required",
    )
    parser.add_argument(
        "--org-id",
        help="Organization ID passed to codedapp commands when required",
    )
    parser.add_argument(
        "--org-name",
        help="Organization name passed to codedapp deploy when required",
    )
    parser.add_argument(
        "--part",
        choices=("patch", "minor", "major"),
        default="patch",
        help="Version component to increment when --set-version is omitted",
    )
    parser.add_argument(
        "--set-version",
        help="Explicit version to write instead of incrementing",
    )
    parser.add_argument(
        "--folder",
        help="Folder path/name resolved to --folder-key for codedapp deploy",
    )
    parser.add_argument(
        "--folder-key",
        help="Folder key passed directly to codedapp deploy",
    )
    parser.add_argument(
        "--app-dist",
        help="Built coded app dist directory. Defaults to app/dist when app/package.json exists, otherwise dist.",
    )
    parser.add_argument(
        "--package-name",
        help="Package/app name. Defaults to [project].name from pyproject.toml.",
    )
    parser.add_argument(
        "--app-name",
        help="App name passed to codedapp deploy. Defaults to --package-name.",
    )
    parser.add_argument(
        "--app-type",
        default="Web",
        help="Coded app type passed to publish --type. Usually Web or Action.",
    )
    parser.add_argument(
        "--main-file",
        default="index.html",
        help="Main file within the dist directory for codedapp pack.",
    )
    parser.add_argument(
        "--content-type",
        default="webapp",
        help="Content type passed to codedapp pack.",
    )
    parser.add_argument(
        "--author",
        help="Package author. Defaults to first pyproject author or UiPath Developer.",
    )
    parser.add_argument(
        "--description",
        help="Package description. Defaults to pyproject description.",
    )
    parser.add_argument(
        "--reuse-client",
        action="store_true",
        help="Pass --reuse-client to codedapp pack to reuse clientId from uipath.json.",
    )
    feed = parser.add_mutually_exclusive_group()
    feed.add_argument(
        "--tenant",
        action="store_true",
        help="Compatibility flag; codedapp publish uses the active or named tenant.",
    )
    feed.add_argument(
        "--my-workspace",
        action="store_true",
        help="Compatibility flag; codedapp deploy requires --folder or --folder-key.",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip uv-run pytest validation before packaging",
    )
    parser.add_argument(
        "--skip-app-build",
        action="store_true",
        help="Skip npm build in app/ when app/package.json exists",
    )
    parser.add_argument(
        "--pack-nolock",
        action="store_true",
        help="Deprecated compatibility flag; codedapp pack has no lock option.",
    )
    parser.add_argument(
        "--use-deploy-command",
        action="store_true",
        help="Deprecated compatibility flag; codedapp deploy always runs after publish.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually edit files and run commands; without this, dry-run only",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Plan commands without probing uip or resolving folder names. Requires --folder-key for non-GUID folders.",
    )
    args = parser.parse_args(argv)

    root = Path(args.project_root).expanduser().resolve()
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        raise SystemExit(f"Missing {pyproject}")

    old_version = _read_version(pyproject)
    new_version = args.set_version or _next_version(old_version, args.part)
    if old_version == new_version:
        raise SystemExit(f"Version is already {new_version}; choose a newer version.")
    if args.folder and args.folder_key:
        raise SystemExit("Use either --folder or --folder-key, not both.")
    if args.my_workspace and not (args.folder or args.folder_key):
        raise SystemExit(
            "--my-workspace has no codedapp equivalent. Pass --folder or --folder-key "
            "for the personal workspace folder."
        )
    if args.offline and args.execute:
        raise SystemExit("--offline cannot be combined with --execute.")
    if args.offline and args.folder and not GUID_RE.match(args.folder):
        raise SystemExit("Offline mode cannot resolve folder names. Pass --folder-key.")

    dry_run = not args.execute
    if dry_run:
        print("Dry-run mode. Re-run with --execute to modify and deploy.")
    if args.offline:
        print("Offline planning mode. Skipping uip probing and folder lookup.")

    env = os.environ.copy()

    if not args.offline:
        _run(["uip", "--version"], cwd=root, env=env, dry_run=False)

    if not args.skip_tests:
        _run(["uv", "run", "python", "-m", "pytest", "-q"], cwd=root, env=env, dry_run=dry_run)

    app_dir = root / "app"
    if not args.skip_app_build and (app_dir / "package.json").exists():
        _run(["npm", "run", "build"], cwd=app_dir, env=env, dry_run=dry_run)

    _write_version(pyproject, new_version, dry_run=dry_run)

    if (root / "uv.lock").exists():
        _run(["uv", "lock"], cwd=root, env=env, dry_run=dry_run)

    package_name = args.package_name or _read_field(pyproject, NAME_RE, root.name)
    app_name = args.app_name or package_name
    author = args.author or _read_field(pyproject, AUTHOR_RE, "UiPath Developer")
    description = args.description or _read_field(pyproject, DESCRIPTION_RE, "")
    dist = Path(args.app_dist).expanduser().resolve() if args.app_dist else _default_dist(root)
    if not dry_run and not dist.exists():
        raise SystemExit(f"Missing coded app dist directory: {dist}")

    folder_key = args.folder_key
    if args.folder:
        folder_key = _resolve_folder_key(args.folder, args.tenant_name, root, env)

    pack_cmd = [
        "uip",
        "codedapp",
        "pack",
        str(dist),
        "--name",
        package_name,
        "--version",
        new_version,
        "--output",
        str(root / ".uipath"),
        "--author",
        author,
        "--main-file",
        args.main_file,
        "--content-type",
        args.content_type,
        *_auth_flags(args, publish=False, deploy=False),
    ]
    if description:
        pack_cmd.extend(["--description", description])
    if args.reuse_client:
        pack_cmd.append("--reuse-client")

    publish_cmd = [
        "uip",
        "codedapp",
        "publish",
        "--name",
        package_name,
        "--version",
        new_version,
        "--type",
        args.app_type,
        "--uipath-dir",
        str(root / ".uipath"),
        *_auth_flags(args, publish=True, deploy=False),
    ]

    deploy_cmd = [
        "uip",
        "codedapp",
        "deploy",
        "--name",
        app_name,
        "--version",
        new_version,
        *_auth_flags(args, publish=False, deploy=True),
    ]
    if folder_key:
        deploy_cmd.extend(["--folder-key", folder_key])

    _run(pack_cmd, cwd=root, env=env, dry_run=dry_run)
    _run(publish_cmd, cwd=root, env=env, dry_run=dry_run)
    _run(deploy_cmd, cwd=root, env=env, dry_run=dry_run)

    print(f"Prepared deployment from {old_version} to {new_version} at {args.target_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
