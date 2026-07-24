#!/usr/bin/env python3
"""Export and validate a reviewable projection of Beads issue history."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable


ROOT = Path(__file__).resolve().parents[1]
ISSUES_PATH = ROOT / ".beads" / "issues.jsonl"
HISTORY_PATH = ROOT / ".beads" / "history.jsonl"
MANIFEST_PATH = ROOT / ".beads" / "history-manifest.json"
HISTORY_TYPE = "beads_issue_history"
MANIFEST_TYPE = "beads_history_manifest"
COMMIT_HASH_RE = re.compile(r"^[0-9a-z]+$")
REQUIRED_ISSUE_FIELDS = {
    "id",
    "title",
    "status",
    "priority",
    "issue_type",
    "created_at",
    "updated_at",
}


class HistoryValidationError(ValueError):
    """Raised when a Beads history artifact violates its public contract."""


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load a JSONL file and report its exact failing line."""
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise HistoryValidationError(f"{path}: file does not exist") from exc

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HistoryValidationError(
                f"{path}:{line_number}: invalid JSON: {exc.msg}"
            ) from exc
        if not isinstance(record, dict):
            raise HistoryValidationError(
                f"{path}:{line_number}: each line must be a JSON object"
            )
        records.append(record)
    return records


def load_current_issues(path: Path = ISSUES_PATH) -> dict[str, dict[str, Any]]:
    """Load the current issue snapshot keyed by issue ID."""
    issues: dict[str, dict[str, Any]] = {}
    for record in load_jsonl(path):
        if record.get("_type") != "issue":
            continue
        issue_id = record.get("id")
        if not isinstance(issue_id, str) or not issue_id:
            raise HistoryValidationError(f"{path}: issue record has no valid id")
        if issue_id in issues:
            raise HistoryValidationError(f"{path}: duplicate issue id {issue_id}")
        issues[issue_id] = record
    if not issues:
        raise HistoryValidationError(f"{path}: no issue records found")
    return issues


def parse_timestamp(value: Any, label: str) -> datetime:
    """Parse a timezone-aware ISO 8601 timestamp."""
    if not isinstance(value, str) or not value:
        raise HistoryValidationError(f"{label}: expected a non-empty timestamp")
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    fractional = re.fullmatch(
        r"(.+T\d{2}:\d{2}:\d{2})\.(\d+)([+-]\d{2}:\d{2})", normalized
    )
    if fractional:
        microseconds = (fractional.group(2) + "000000")[:6]
        normalized = (
            f"{fractional.group(1)}.{microseconds}{fractional.group(3)}"
        )
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise HistoryValidationError(f"{label}: invalid ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise HistoryValidationError(f"{label}: timestamp must include a timezone")
    return parsed


def issue_fingerprint(issue: dict[str, Any]) -> str:
    """Return a stable comparison representation for an issue snapshot."""
    return json.dumps(issue, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def history_sort_key(record: dict[str, Any]) -> tuple[datetime, str, str]:
    """Sort history globally by instant, issue ID, then Dolt commit hash."""
    return (
        parse_timestamp(record.get("commit_date"), "history commit_date"),
        str(record.get("issue_id", "")),
        str(record.get("commit_hash", "")),
    )


def normalize_issue_history(
    issue_id: str, raw_entries: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Normalize `bd history --json` output and remove unchanged snapshots."""
    normalized: list[dict[str, Any]] = []
    for index, raw_entry in enumerate(raw_entries, start=1):
        if not isinstance(raw_entry, dict):
            raise HistoryValidationError(
                f"{issue_id} history entry {index}: expected an object"
            )
        issue = raw_entry.get("Issue")
        commit_hash = raw_entry.get("CommitHash")
        commit_date = raw_entry.get("CommitDate")
        if not isinstance(issue, dict) or issue.get("id") != issue_id:
            raise HistoryValidationError(
                f"{issue_id} history entry {index}: issue snapshot ID mismatch"
            )
        if not isinstance(commit_hash, str) or not COMMIT_HASH_RE.fullmatch(commit_hash):
            raise HistoryValidationError(
                f"{issue_id} history entry {index}: invalid Dolt commit hash"
            )
        parse_timestamp(commit_date, f"{issue_id} history entry {index} commit date")
        normalized.append(
            {
                "_type": HISTORY_TYPE,
                "commit_date": commit_date,
                "commit_hash": commit_hash,
                "issue": issue,
                "issue_id": issue_id,
            }
        )

    normalized.sort(key=history_sort_key)
    deduplicated: list[dict[str, Any]] = []
    previous_fingerprint: str | None = None
    for entry in normalized:
        fingerprint = issue_fingerprint(entry["issue"])
        if fingerprint == previous_fingerprint:
            continue
        deduplicated.append(entry)
        previous_fingerprint = fingerprint
    return deduplicated


def read_bd_history(issue_id: str) -> list[dict[str, Any]]:
    """Read native issue-table history from the authoritative local Beads DB."""
    try:
        result = subprocess.run(
            ["bd", "history", issue_id, "--json"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise HistoryValidationError("bd is required to export history") from exc
    except subprocess.TimeoutExpired as exc:
        raise HistoryValidationError(
            f"bd history timed out for {issue_id}"
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout).strip()
        raise HistoryValidationError(
            f"bd history failed for {issue_id}: {detail or 'unknown error'}"
        ) from exc
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise HistoryValidationError(
            f"bd history returned invalid JSON for {issue_id}"
        ) from exc
    if not isinstance(parsed, list):
        raise HistoryValidationError(
            f"bd history returned a non-list value for {issue_id}"
        )
    return parsed


def build_history(
    issue_ids: Iterable[str],
    history_reader: Callable[[str], list[dict[str, Any]]] = read_bd_history,
) -> list[dict[str, Any]]:
    """Build a deterministic, globally chronological history projection."""
    records: list[dict[str, Any]] = []
    for issue_id in sorted(set(issue_ids)):
        records.extend(normalize_issue_history(issue_id, history_reader(issue_id)))
    records.sort(key=history_sort_key)
    return records


def render_jsonl(records: Iterable[dict[str, Any]]) -> str:
    """Render stable one-object-per-line JSON."""
    lines = [
        json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        for record in records
    ]
    return "".join(f"{line}\n" for line in lines)


def validate_history_records(
    current_issues: dict[str, dict[str, Any]],
    records: list[dict[str, Any]],
) -> None:
    """Validate shape, chronology, deduplication, coverage, and terminal state."""
    if not records:
        raise HistoryValidationError("history artifact has no records")
    if records != sorted(records, key=history_sort_key):
        raise HistoryValidationError("history records are not in deterministic order")

    seen_commits: set[tuple[str, str]] = set()
    last_fingerprint: dict[str, str] = {}
    latest: dict[str, dict[str, Any]] = {}
    expected_keys = {
        "_type",
        "commit_date",
        "commit_hash",
        "issue",
        "issue_id",
    }
    for index, record in enumerate(records, start=1):
        if set(record) != expected_keys or record.get("_type") != HISTORY_TYPE:
            raise HistoryValidationError(
                f"history line {index}: unexpected record shape or type"
            )
        issue_id = record.get("issue_id")
        issue = record.get("issue")
        commit_hash = record.get("commit_hash")
        if not isinstance(issue_id, str) or not issue_id:
            raise HistoryValidationError(f"history line {index}: invalid issue_id")
        if not isinstance(issue, dict) or issue.get("id") != issue_id:
            raise HistoryValidationError(
                f"history line {index}: issue snapshot ID mismatch"
            )
        missing = REQUIRED_ISSUE_FIELDS - set(issue)
        if missing:
            raise HistoryValidationError(
                f"history line {index}: issue snapshot missing {', '.join(sorted(missing))}"
            )
        if not isinstance(commit_hash, str) or not COMMIT_HASH_RE.fullmatch(commit_hash):
            raise HistoryValidationError(
                f"history line {index}: invalid Dolt commit hash"
            )
        parse_timestamp(record.get("commit_date"), f"history line {index} commit_date")
        commit_key = (issue_id, commit_hash)
        if commit_key in seen_commits:
            raise HistoryValidationError(
                f"history line {index}: duplicate issue/commit pair"
            )
        seen_commits.add(commit_key)
        fingerprint = issue_fingerprint(issue)
        if last_fingerprint.get(issue_id) == fingerprint:
            raise HistoryValidationError(
                f"history line {index}: redundant unchanged issue snapshot"
            )
        last_fingerprint[issue_id] = fingerprint
        latest[issue_id] = issue

    missing_history = sorted(set(current_issues) - set(latest))
    if missing_history:
        raise HistoryValidationError(
            f"current issues missing from history: {', '.join(missing_history)}"
        )
    for issue_id, current in current_issues.items():
        terminal = latest[issue_id]
        mismatches = [
            key
            for key, value in terminal.items()
            if key not in current or current[key] != value
        ]
        if mismatches:
            raise HistoryValidationError(
                f"{issue_id}: terminal history snapshot differs from current state "
                f"for {', '.join(sorted(mismatches))}"
            )


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file's exact bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_manifest(
    dolt_head: str,
    issues_path: Path,
    history_path: Path,
    issue_records: int,
    history_records: int,
) -> dict[str, Any]:
    """Build a deterministic manifest anchoring public files to native Dolt HEAD."""
    if not COMMIT_HASH_RE.fullmatch(dolt_head):
        raise HistoryValidationError("cannot manifest an invalid Dolt HEAD")
    return {
        "_type": MANIFEST_TYPE,
        "artifacts": {
            ".beads/history.jsonl": {
                "records": history_records,
                "sha256": sha256_file(history_path),
            },
            ".beads/issues.jsonl": {
                "records": issue_records,
                "sha256": sha256_file(issues_path),
            },
        },
        "dolt_head": dolt_head,
        "dolt_ref": "refs/dolt/data",
        "projection": (
            "Deduplicated issue-table snapshots for GitHub review; "
            "the Dolt ref is the complete recovery source."
        ),
        "schema_version": 1,
    }


def validate_manifest(
    manifest_path: Path,
    issues_path: Path,
    history_path: Path,
    issue_records: int,
    history_records: int,
) -> dict[str, Any]:
    """Verify the manifest schema and exact artifact hashes."""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HistoryValidationError(f"{manifest_path}: file does not exist") from exc
    except json.JSONDecodeError as exc:
        raise HistoryValidationError(
            f"{manifest_path}: invalid JSON: {exc.msg}"
        ) from exc
    expected_keys = {
        "_type",
        "artifacts",
        "dolt_head",
        "dolt_ref",
        "projection",
        "schema_version",
    }
    if not isinstance(manifest, dict) or set(manifest) != expected_keys:
        raise HistoryValidationError("history manifest has an unexpected shape")
    if (
        manifest.get("_type") != MANIFEST_TYPE
        or manifest.get("schema_version") != 1
        or manifest.get("dolt_ref") != "refs/dolt/data"
        or not isinstance(manifest.get("projection"), str)
        or not manifest["projection"]
    ):
        raise HistoryValidationError("history manifest metadata is invalid")
    dolt_head = manifest.get("dolt_head")
    if not isinstance(dolt_head, str) or not COMMIT_HASH_RE.fullmatch(dolt_head):
        raise HistoryValidationError("history manifest has an invalid Dolt HEAD")

    expected_artifacts = {
        ".beads/history.jsonl": {
            "records": history_records,
            "sha256": sha256_file(history_path),
        },
        ".beads/issues.jsonl": {
            "records": issue_records,
            "sha256": sha256_file(issues_path),
        },
    }
    if manifest.get("artifacts") != expected_artifacts:
        raise HistoryValidationError(
            "history manifest does not match the tracked artifact bytes"
        )
    return manifest


def git_file_at_ref(base_ref: str, relative_path: str) -> str | None:
    """Read a file from a Git ref, returning None when the file is absent."""
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{base_ref}:{relative_path}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode == 0:
        return result.stdout
    missing_markers = ("does not exist", "exists on disk, but not in", "invalid object name")
    if any(marker in result.stderr for marker in missing_markers):
        return None
    raise HistoryValidationError(
        f"could not inspect {relative_path} at {base_ref}: {result.stderr.strip()}"
    )


def validate_base_history(base_ref: str, records: list[dict[str, Any]]) -> None:
    """Require every history record on the base ref to remain byte-equivalent."""
    base_text = git_file_at_ref(base_ref, ".beads/history.jsonl")
    if base_text is None:
        return
    base_records: list[dict[str, Any]] = []
    for line_number, line in enumerate(base_text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HistoryValidationError(
                f"{base_ref} history line {line_number}: invalid JSON"
            ) from exc
        if not isinstance(record, dict):
            raise HistoryValidationError(
                f"{base_ref} history line {line_number}: expected an object"
            )
        base_records.append(record)
    current_fingerprints = {issue_fingerprint(record) for record in records}
    removed = [
        record
        for record in base_records
        if issue_fingerprint(record) not in current_fingerprints
    ]
    if removed:
        raise HistoryValidationError(
            f"history rewrites or removes {len(removed)} record(s) from {base_ref}"
        )


def export_history(
    issues_path: Path = ISSUES_PATH,
    history_path: Path = HISTORY_PATH,
    manifest_path: Path = MANIFEST_PATH,
) -> int:
    """Export current authoritative history without bootstrapping or importing."""
    current_issues = load_current_issues(issues_path)
    issue_ids = set(current_issues)
    if history_path.exists():
        for record in load_jsonl(history_path):
            prior_id = record.get("issue_id")
            if isinstance(prior_id, str) and prior_id:
                issue_ids.add(prior_id)

    raw_by_issue: dict[str, list[dict[str, Any]]] = {}

    def cached_reader(issue_id: str) -> list[dict[str, Any]]:
        raw_by_issue[issue_id] = read_bd_history(issue_id)
        return raw_by_issue[issue_id]

    records = build_history(issue_ids, cached_reader)
    validate_history_records(current_issues, records)
    head_candidates = {
        max(
            entries,
            key=lambda entry: parse_timestamp(
                entry.get("CommitDate"), f"{issue_id} source commit date"
            ),
        ).get("CommitHash")
        for issue_id, entries in raw_by_issue.items()
        if issue_id in current_issues and entries
    }
    if len(head_candidates) != 1:
        raise HistoryValidationError(
            "current issues do not agree on one authoritative Dolt HEAD"
        )
    dolt_head = next(iter(head_candidates))
    if not isinstance(dolt_head, str):
        raise HistoryValidationError("authoritative Dolt HEAD is invalid")
    rendered = render_jsonl(records)
    history_changed = (
        not history_path.exists()
        or history_path.read_text(encoding="utf-8") != rendered
    )
    if history_changed:
        history_path.write_text(rendered, encoding="utf-8")
    manifest = build_manifest(
        dolt_head,
        issues_path,
        history_path,
        len(load_jsonl(issues_path)),
        len(records),
    )
    manifest_text = (
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    manifest_changed = (
        not manifest_path.exists()
        or manifest_path.read_text(encoding="utf-8") != manifest_text
    )
    if manifest_changed:
        manifest_path.write_text(manifest_text, encoding="utf-8")
    if not history_changed and not manifest_changed:
        print("Beads history projection and manifest are already current.")
        return 0
    print(
        f"Exported {len(records)} issue-state transitions to "
        f"{history_path.relative_to(ROOT)} at Dolt HEAD {dolt_head}."
    )
    return 0


def verify_history(
    issues_path: Path = ISSUES_PATH,
    history_path: Path = HISTORY_PATH,
    manifest_path: Path = MANIFEST_PATH,
    base_ref: str | None = None,
) -> int:
    """Validate tracked artifacts without requiring Beads or a local database."""
    current_issues = load_current_issues(issues_path)
    records = load_jsonl(history_path)
    validate_history_records(current_issues, records)
    manifest = validate_manifest(
        manifest_path,
        issues_path,
        history_path,
        len(load_jsonl(issues_path)),
        len(records),
    )
    if base_ref:
        validate_base_history(base_ref, records)
    print(
        f"Validated {len(records)} Beads issue-state transitions for "
        f"{len(current_issues)} current issues at Dolt HEAD {manifest['dolt_head']}."
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "export",
        help="Regenerate history.jsonl from the authoritative local Beads database.",
    )
    verify_parser = subparsers.add_parser(
        "verify",
        help="Validate tracked JSONL artifacts without accessing a Beads database.",
    )
    verify_parser.add_argument(
        "--base-ref",
        help="Also reject deletion or rewriting of history records from this Git ref.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return (
            export_history()
            if args.command == "export"
            else verify_history(base_ref=args.base_ref)
        )
    except HistoryValidationError as exc:
        print(f"Beads history validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
