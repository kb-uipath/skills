#!/usr/bin/env python3
"""Manage the versioned account meeting contact store."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shlex
import stat
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from email_validation import validate_practical_email


CANONICAL_HEADERS = [
    "account name",
    "record type",
    "customer name",
    "customer role",
    "customer email address",
]

REQUIRED_HEADERS = [
    "account name",
    "customer name",
    "customer role",
    "customer email address",
]

CONTACT_STORE_SCHEMA = "account-meeting-availability/contact-store"
CONTACT_STORE_SCHEMA_VERSION = "2.0"
CONTACT_STORE_STORAGE_FORMAT = "csv"
LEGACY_SCHEMA_VERSION = "legacy-unversioned"
DEFAULT_LOCK_TIMEOUT_SECONDS = 10.0
DEFAULT_LOCK_POLL_SECONDS = 0.05
PRIVATE_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR
PRIVATE_DIRECTORY_MODE = stat.S_IRWXU

RECORD_TYPES = {"customer", "uipath"}
FORMULA_PREFIX_RE = re.compile(r"^[\t\r\n ]*[=+\-@]")

ALIASES = {
    "account": "account name",
    "accountname": "account name",
    "recordtype": "record type",
    "contacttype": "record type",
    "participanttype": "record type",
    "party": "record type",
    "type": "record type",
    "uipathorcustomer": "record type",
    "customer": "customer name",
    "customername": "customer name",
    "contact": "customer name",
    "contactname": "customer name",
    "name": "customer name",
    "role": "customer role",
    "customerrole": "customer role",
    "title": "customer role",
    "customertitle": "customer role",
    "email": "customer email address",
    "emailaddress": "customer email address",
    "customeremail": "customer email address",
    "customeremailaddress": "customer email address",
    "contactemail": "customer email address",
    "contactemailaddress": "customer email address",
}

RECORD_TYPE_ALIASES = {
    "account": "customer",
    "client": "customer",
    "customer": "customer",
    "external": "customer",
    "internal": "uipath",
    "team": "uipath",
    "teammate": "uipath",
    "uipath": "uipath",
    "uipath team": "uipath",
    "uipath teammate": "uipath",
}


class LegacyStoreError(ValueError):
    """Raised when an unversioned store requires explicit migration."""


def default_store_path() -> Path:
    configured = os.environ.get("CUSTOMER_EMAIL_STORE")
    if configured:
        return Path(configured).expanduser()
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    return codex_home / "account-meeting-availability" / "contacts.csv"


def metadata_path(path: Path) -> Path:
    return path.with_name(path.name + ".metadata.json")


def lock_directory_path(path: Path) -> Path:
    return path.with_name(path.name + ".lock")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_header(value: str) -> str:
    compact = re.sub(r"[^a-z0-9]+", "", value.strip().lower())
    spaced = re.sub(r"[^a-z0-9]+", " ", value.strip().lower()).strip()
    return ALIASES.get(compact) or ALIASES.get(spaced) or spaced


def normalize_value(value: str | None) -> str:
    return (value or "").strip()


def safe_csv_value(value: str) -> str:
    if FORMULA_PREFIX_RE.match(value):
        return "'" + value
    return value


def safe_csv_row(row: dict[str, str]) -> dict[str, str]:
    return {header: safe_csv_value(normalize_value(row.get(header))) for header in CANONICAL_HEADERS}


def normalize_record_type(value: str | None, default: str = "customer") -> str:
    raw = normalize_value(value).casefold()
    if not raw:
        return default
    compact = re.sub(r"[^a-z0-9]+", "", raw)
    spaced = re.sub(r"[^a-z0-9]+", " ", raw).strip()
    normalized = RECORD_TYPE_ALIASES.get(compact) or RECORD_TYPE_ALIASES.get(spaced) or spaced
    if normalized not in RECORD_TYPES:
        raise ValueError("record type must be 'customer' or 'uipath'")
    return normalized


def normalize_row(row: dict[str, str], *, context: str = "contact") -> dict[str, str]:
    normalized = {header: normalize_value(row.get(header)) for header in CANONICAL_HEADERS}
    normalized["record type"] = normalize_record_type(row.get("record type"))
    try:
        normalized["customer email address"] = validate_practical_email(
            normalized["customer email address"], allow_blank=True
        )
    except ValueError as exc:
        raise ValueError(f"{context}: {exc}") from exc
    return normalized


def identity_scope(row: dict[str, str]) -> tuple[str, str]:
    return (
        normalize_value(row.get("account name")).casefold(),
        normalize_record_type(row.get("record type")),
    )


def scoped_name_identity(row: dict[str, str]) -> tuple[str, str, str]:
    account, record_type = identity_scope(row)
    return account, record_type, normalize_value(row.get("customer name")).casefold()


def validate_unique_scoped_identities(
    rows: list[dict[str, str]], *, context: str = "contact store"
) -> None:
    seen: dict[tuple[str, str, str], int] = {}
    for index, row in enumerate(rows, start=1):
        key = scoped_name_identity(row)
        if key in seen:
            account, record_type, name = key
            raise ValueError(
                f"{context} has duplicate scoped identity at rows {seen[key]} and {index}: "
                f"account='{account}', record type='{record_type}', name='{name}'. "
                "Resolve the duplicate explicitly before retrying."
            )
        seen[key] = index


def same_contact(left: dict[str, str], right: dict[str, str]) -> bool:
    if identity_scope(left) != identity_scope(right):
        return False

    left_name = normalize_value(left.get("customer name")).casefold()
    right_name = normalize_value(right.get("customer name")).casefold()
    if left_name and right_name and left_name == right_name:
        return True

    left_email = normalize_value(left.get("customer email address")).casefold()
    right_email = normalize_value(right.get("customer email address")).casefold()
    return bool(left_email and right_email and left_email == right_email)


def _ensure_parent(path: Path) -> None:
    parent_existed = path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True, mode=PRIVATE_DIRECTORY_MODE)
    if not parent_existed:
        os.chmod(path.parent, PRIVATE_DIRECTORY_MODE)


def _restrict_file(path: Path) -> None:
    os.chmod(path, PRIVATE_FILE_MODE)


def _atomic_text_write(path: Path, writer, *, newline: str | None = None) -> None:
    _ensure_parent(path)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        os.chmod(temporary_name, PRIVATE_FILE_MODE)
        with os.fdopen(descriptor, "w", newline=newline, encoding="utf-8") as handle:
            writer(handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        _restrict_file(path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def write_rows(
    path: Path, rows: list[dict[str, str]], *, escape_formulas: bool = False
) -> None:
    normalized_rows = [
        normalize_row(row, context=f"contact row {index}")
        for index, row in enumerate(rows, start=1)
    ]
    validate_unique_scoped_identities(normalized_rows)

    def write(handle) -> None:
        writer = csv.DictWriter(handle, fieldnames=CANONICAL_HEADERS)
        writer.writeheader()
        for row in normalized_rows:
            writer.writerow(safe_csv_row(row) if escape_formulas else row)

    _atomic_text_write(path, write, newline="")


def _new_metadata(*, migrated: bool) -> dict[str, object]:
    timestamp = utc_now()
    return {
        "schema": CONTACT_STORE_SCHEMA,
        "schema_version": CONTACT_STORE_SCHEMA_VERSION,
        "storage_format": CONTACT_STORE_STORAGE_FORMAT,
        "created_at": timestamp,
        "migration": (
            {
                "from_schema_version": LEGACY_SCHEMA_VERSION,
                "migrated_at": timestamp,
            }
            if migrated
            else None
        ),
    }


def write_metadata(path: Path, metadata: dict[str, object]) -> None:
    def write(handle) -> None:
        json.dump(metadata, handle, indent=2, sort_keys=True)
        handle.write("\n")

    _atomic_text_write(metadata_path(path), write)


def read_metadata(path: Path) -> dict[str, object]:
    sidecar = metadata_path(path)
    try:
        with sidecar.open(encoding="utf-8") as handle:
            metadata = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Contact store metadata is not valid JSON: {sidecar}") from exc
    if not isinstance(metadata, dict):
        raise ValueError(f"Contact store metadata must be a JSON object: {sidecar}")
    expected_keys = {"schema", "schema_version", "storage_format", "created_at", "migration"}
    if set(metadata) != expected_keys:
        raise ValueError(
            f"Contact store metadata fields do not match schema version "
            f"{CONTACT_STORE_SCHEMA_VERSION}: {sidecar}"
        )
    if metadata.get("schema") != CONTACT_STORE_SCHEMA:
        raise ValueError(
            f"Unsupported contact store schema '{metadata.get('schema')}'. "
            "Restore the matching metadata or use a compatible skill release."
        )
    if metadata.get("schema_version") != CONTACT_STORE_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported contact store schema version '{metadata.get('schema_version')}'; "
            f"this release supports '{CONTACT_STORE_SCHEMA_VERSION}'. "
            "Do not edit the CSV until it has been migrated by a compatible release."
        )
    if metadata.get("storage_format") != CONTACT_STORE_STORAGE_FORMAT:
        raise ValueError("Contact store metadata does not declare CSV storage")
    _validate_metadata_timestamp(metadata.get("created_at"), "created_at")
    migration = metadata.get("migration")
    if migration is not None:
        if not isinstance(migration, dict) or set(migration) != {
            "from_schema_version",
            "migrated_at",
        }:
            raise ValueError("Contact store migration metadata is malformed")
        if migration.get("from_schema_version") != LEGACY_SCHEMA_VERSION:
            raise ValueError("Contact store migration source version is unsupported")
        _validate_metadata_timestamp(migration.get("migrated_at"), "migration.migrated_at")
    return metadata


def _validate_metadata_timestamp(value: object, context: str) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"Contact store metadata {context} must be a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"Contact store metadata {context} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"Contact store metadata {context} must use UTC")


def _legacy_migration_error(path: Path) -> LegacyStoreError:
    quoted_path = shlex.quote(str(path))
    return LegacyStoreError(
        f"Legacy unversioned contact store detected at {path}. Back up this local file, "
        f"then run: python3 scripts/contact_store.py --store {quoted_path} migrate. "
        "No contact data was changed."
    )


def ensure_store(path: Path) -> None:
    sidecar = metadata_path(path)
    if path.exists() and not sidecar.exists():
        raise _legacy_migration_error(path)
    if sidecar.exists() and not path.exists():
        raise ValueError(
            f"Contact store CSV is missing but metadata remains at {sidecar}. "
            "Restore the CSV from a trusted backup or remove both files and run init."
        )
    if not path.exists():
        write_rows(path, [])
        write_metadata(path, _new_metadata(migrated=False))
    read_metadata(path)
    _restrict_file(path)
    _restrict_file(sidecar)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != CANONICAL_HEADERS:
            raise ValueError(
                "Contact store CSV header does not match schema version 2.0. "
                "Do not edit the backing CSV directly; restore the canonical header or a trusted backup."
            )
        rows = []
        for index, row in enumerate(reader, start=1):
            if None in row:
                raise ValueError(f"contact store row {index} contains more values than headers")
            rows.append(normalize_row(row, context=f"contact store row {index}"))
    validate_unique_scoped_identities(rows)
    return rows


def read_import_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("Import CSV has no header row")

        header_map: dict[str, str] = {}
        seen: dict[str, str] = {}
        for header in reader.fieldnames:
            normalized = normalize_header(header)
            if normalized in CANONICAL_HEADERS:
                if normalized in seen:
                    raise ValueError(
                        f"Duplicate logical header for '{normalized}': "
                        f"'{seen[normalized]}' and '{header}'"
                    )
                seen[normalized] = header
                header_map[normalized] = header

        missing = [header for header in REQUIRED_HEADERS if header not in header_map]
        if missing:
            raise ValueError("Import CSV is missing column(s): " + ", ".join(missing))

        rows = []
        for index, row in enumerate(reader, start=1):
            if None in row:
                raise ValueError(f"import row {index} contains more values than headers")
            imported = {
                canonical: normalize_value(row.get(original))
                for canonical, original in header_map.items()
            }
            rows.append(normalize_row(imported, context=f"import row {index}"))
    validate_unique_scoped_identities(rows, context="import CSV")
    return rows


def migrate_store(path: Path) -> str:
    sidecar = metadata_path(path)
    if sidecar.exists():
        if not path.exists():
            raise ValueError(f"Cannot migrate because the contact CSV is missing: {path}")
        read_metadata(path)
        _restrict_file(path)
        _restrict_file(sidecar)
        return f"Contact store already uses schema {CONTACT_STORE_SCHEMA_VERSION}: {path}"
    if not path.exists():
        raise ValueError(f"No legacy contact store exists at {path}; run init instead")

    try:
        rows = read_import_csv(path)
    except Exception as exc:
        raise ValueError(
            f"Legacy migration validation failed: {exc}. Correct a backed-up copy and retry; "
            "the original store was not changed."
        ) from exc

    write_rows(path, rows)
    write_metadata(path, _new_metadata(migrated=True))
    return f"Migrated contact store to schema {CONTACT_STORE_SCHEMA_VERSION}: {path}"


class StoreLock:
    """Coordinate contact-store access with an atomic, cross-platform directory lock."""

    def __init__(
        self,
        store: Path,
        *,
        timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
        poll_seconds: float = DEFAULT_LOCK_POLL_SECONDS,
    ) -> None:
        if timeout_seconds < 0:
            raise ValueError("lock timeout must be zero or greater")
        if poll_seconds <= 0:
            raise ValueError("lock poll interval must be greater than zero")
        self.store = store
        self.path = lock_directory_path(store)
        self.owner_path = self.path / "owner.json"
        self.timeout_seconds = timeout_seconds
        self.poll_seconds = poll_seconds
        self.acquired = False

    def __enter__(self):
        _ensure_parent(self.store)
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                os.mkdir(self.path, PRIVATE_DIRECTORY_MODE)
                os.chmod(self.path, PRIVATE_DIRECTORY_MODE)
                self.acquired = True
                break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Timed out waiting for contact store lock {self.path}. "
                        "If a process crashed, inspect owner.json and remove the lock directory "
                        "only after confirming that process is no longer active."
                    )
                time.sleep(min(self.poll_seconds, max(0.0, deadline - time.monotonic())))

        try:
            def write_owner(handle) -> None:
                json.dump({"pid": os.getpid(), "acquired_at": utc_now()}, handle, sort_keys=True)
                handle.write("\n")

            _atomic_text_write(self.owner_path, write_owner)
        except Exception:
            self._release()
            raise
        return self

    def _release(self) -> None:
        if not self.acquired:
            return
        try:
            try:
                self.owner_path.unlink()
            except FileNotFoundError:
                pass
            os.rmdir(self.path)
        finally:
            self.acquired = False

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._release()


def filter_rows(
    rows: list[dict[str, str]],
    account: str | None = None,
    record_type: str | None = None,
    name: str | None = None,
    email: str | None = None,
) -> list[dict[str, str]]:
    def includes(row_value: str, wanted: str | None) -> bool:
        return not wanted or wanted.casefold() in row_value.casefold()

    normalized_record_type = normalize_record_type(record_type) if record_type else None
    return [
        row
        for row in rows
        if includes(row.get("account name", ""), account)
        and (
            not normalized_record_type
            or normalize_record_type(row.get("record type")) == normalized_record_type
        )
        and includes(row.get("customer name", ""), name)
        and includes(row.get("customer email address", ""), email)
    ]


def upsert_row(rows: list[dict[str, str]], new_row: dict[str, str]) -> tuple[list[dict[str, str]], str]:
    normalized = normalize_row(new_row)
    matches = [index for index, row in enumerate(rows) if same_contact(row, normalized)]
    if len(matches) > 1:
        raise ValueError(
            "contact matches multiple scoped identities; resolve duplicate account/type/name "
            "records before retrying"
        )
    if matches:
        rows[matches[0]] = normalized
        return rows, "updated"
    rows.append(normalized)
    return rows, "added"


def print_rows(rows: list[dict[str, str]], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(rows, indent=2))
        return

    if output_format == "csv":
        writer = csv.DictWriter(sys.stdout, fieldnames=CANONICAL_HEADERS)
        writer.writeheader()
        writer.writerows(safe_csv_row(row) for row in rows)
        return

    if not rows:
        print("No contacts found.")
        return

    widths = {
        header: max(len(header), *(len(row.get(header, "")) for row in rows))
        for header in CANONICAL_HEADERS
    }
    print(" | ".join(header.ljust(widths[header]) for header in CANONICAL_HEADERS))
    print("-+-".join("-" * widths[header] for header in CANONICAL_HEADERS))
    for row in rows:
        print(" | ".join(row.get(header, "").ljust(widths[header]) for header in CANONICAL_HEADERS))


def add_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--store", type=Path, default=default_store_path(), help="Contact store CSV path")
    parser.add_argument(
        "--lock-timeout",
        type=float,
        default=DEFAULT_LOCK_TIMEOUT_SECONDS,
        help="Seconds to wait for the contact store lock (default: 10)",
    )
    parser.add_argument(
        "--lock-poll-interval",
        type=float,
        default=DEFAULT_LOCK_POLL_SECONDS,
        help=argparse.SUPPRESS,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("path", help="Print the contact store path")
    subparsers.add_parser("init", help="Create a versioned contact store if it does not exist")
    subparsers.add_parser("migrate", help="Explicitly migrate an unversioned legacy contact CSV")

    add_parser = subparsers.add_parser("add", help="Add or update a contact")
    add_parser.add_argument("--account", required=True)
    add_parser.add_argument("--record-type", "--type", dest="record_type", default="customer")
    add_parser.add_argument("--name", required=True)
    add_parser.add_argument("--role", default="")
    add_parser.add_argument("--email", required=True)

    edit_parser = subparsers.add_parser("edit", help="Edit exactly one matching contact")
    edit_parser.add_argument("--match-account")
    edit_parser.add_argument("--match-record-type", "--match-type", dest="match_record_type")
    edit_parser.add_argument("--match-name")
    edit_parser.add_argument("--match-email")
    edit_parser.add_argument("--account")
    edit_parser.add_argument("--record-type", "--type", dest="record_type")
    edit_parser.add_argument("--name")
    edit_parser.add_argument("--role")
    edit_parser.add_argument("--email")

    list_parser = subparsers.add_parser("list", help="List contacts")
    list_parser.add_argument("--account")
    list_parser.add_argument("--record-type", "--type", dest="record_type")
    list_parser.add_argument("--name")
    list_parser.add_argument("--email")
    list_parser.add_argument("--format", choices=["table", "csv", "json"], default="table")

    delete_parser = subparsers.add_parser("delete", help="Delete exactly one matching contact")
    delete_parser.add_argument("--match-account")
    delete_parser.add_argument("--match-record-type", "--match-type", dest="match_record_type")
    delete_parser.add_argument("--match-name")
    delete_parser.add_argument("--match-email")

    import_parser = subparsers.add_parser("import", help="Import contacts from a CSV")
    import_parser.add_argument("csv_path", type=Path)
    import_parser.add_argument("--mode", choices=["upsert", "skip-existing"], default="upsert")

    export_parser = subparsers.add_parser("export", help="Export contacts to a guarded CSV")
    export_parser.add_argument("--output", "-o", type=Path, required=True)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Manage account meeting contacts.")
    add_args(parser)
    args = parser.parse_args(argv)
    store = args.store.expanduser()

    try:
        if args.command == "path":
            print(store)
            return 0

        with StoreLock(
            store,
            timeout_seconds=args.lock_timeout,
            poll_seconds=args.lock_poll_interval,
        ):
            if args.command == "migrate":
                print(migrate_store(store))
                return 0

            ensure_store(store)

            if args.command == "init":
                print(f"Contact store: {store}")
                print(f"Metadata: {metadata_path(store)}")
                return 0

            rows = read_rows(store)

            if args.command == "add":
                email = validate_practical_email(args.email)
                row = {
                    "account name": args.account,
                    "record type": normalize_record_type(args.record_type),
                    "customer name": args.name,
                    "customer role": args.role,
                    "customer email address": email,
                }
                rows, action = upsert_row(rows, row)
                write_rows(store, rows)
                print(f"{action}: [{row['record type']}] {args.name} <{email}>")
                return 0

            if args.command == "edit":
                matches = filter_rows(
                    rows,
                    args.match_account,
                    args.match_record_type,
                    args.match_name,
                    args.match_email,
                )
                if len(matches) != 1:
                    raise ValueError(f"edit requires exactly one match; found {len(matches)}")
                for index, row in enumerate(rows):
                    if row is matches[0]:
                        updates = [
                            ("account name", args.account),
                            (
                                "record type",
                                normalize_record_type(args.record_type)
                                if args.record_type is not None
                                else None,
                            ),
                            ("customer name", args.name),
                            ("customer role", args.role),
                            (
                                "customer email address",
                                validate_practical_email(args.email, allow_blank=True)
                                if args.email is not None
                                else None,
                            ),
                        ]
                        for field, value in updates:
                            if value is not None:
                                row[field] = normalize_value(value)
                        rows[index] = normalize_row(row)
                        break
                write_rows(store, rows)
                print("updated contact")
                return 0

            if args.command == "list":
                print_rows(
                    filter_rows(rows, args.account, args.record_type, args.name, args.email),
                    args.format,
                )
                return 0

            if args.command == "delete":
                matches = filter_rows(
                    rows,
                    args.match_account,
                    args.match_record_type,
                    args.match_name,
                    args.match_email,
                )
                if len(matches) != 1:
                    raise ValueError(f"delete requires exactly one match; found {len(matches)}")
                rows = [row for row in rows if row is not matches[0]]
                write_rows(store, rows)
                print("deleted contact")
                return 0

            if args.command == "import":
                incoming = read_import_csv(args.csv_path)
                counts = {"added": 0, "updated": 0, "skipped": 0}
                for row in incoming:
                    if args.mode == "skip-existing" and any(
                        same_contact(existing, row) for existing in rows
                    ):
                        counts["skipped"] += 1
                        continue
                    rows, action = upsert_row(rows, row)
                    counts[action] += 1
                write_rows(store, rows)
                print(
                    f"imported: {counts['added']} added, "
                    f"{counts['updated']} updated, {counts['skipped']} skipped"
                )
                return 0

            if args.command == "export":
                output = args.output.expanduser()
                protected_paths = {store.resolve(), metadata_path(store).resolve()}
                if output.resolve() in protected_paths:
                    raise ValueError("export output must not overwrite the contact store or metadata")
                write_rows(output, rows, escape_formulas=True)
                print(f"Exported contacts: {output}")
                return 0

            raise ValueError(f"unknown command: {args.command}")
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
