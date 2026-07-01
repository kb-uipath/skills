#!/usr/bin/env python3
"""Manage the persistent account meeting contact store."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path


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


def default_store_path() -> Path:
    configured = os.environ.get("CUSTOMER_EMAIL_STORE")
    if configured:
        return Path(configured).expanduser()
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    return codex_home / "account-meeting-availability" / "contacts.csv"


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


def normalize_row(row: dict[str, str]) -> dict[str, str]:
    normalized = {header: normalize_value(row.get(header)) for header in CANONICAL_HEADERS}
    normalized["record type"] = normalize_record_type(row.get("record type"))
    return normalized


def same_contact(left: dict[str, str], right: dict[str, str]) -> bool:
    left_email = normalize_value(left.get("customer email address")).casefold()
    right_email = normalize_value(right.get("customer email address")).casefold()
    if left_email and right_email and left_email == right_email:
        return True

    left_account = normalize_value(left.get("account name")).casefold()
    right_account = normalize_value(right.get("account name")).casefold()
    left_type = normalize_record_type(left.get("record type"))
    right_type = normalize_record_type(right.get("record type"))
    left_name = normalize_value(left.get("customer name")).casefold()
    right_name = normalize_value(right.get("customer name")).casefold()
    return bool(left_account and right_account and left_name and right_name) and (
        left_account,
        left_type,
        left_name,
    ) == (right_account, right_type, right_name)


def ensure_store(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        write_rows(path, [])


def read_rows(path: Path) -> list[dict[str, str]]:
    ensure_store(path)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return []
        missing = [header for header in REQUIRED_HEADERS if header not in reader.fieldnames]
        if missing:
            raise ValueError(f"Contact store is missing column(s): {', '.join(missing)}")
        return [normalize_row(row) for row in reader]


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".contacts.", suffix=".csv", dir=path.parent)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CANONICAL_HEADERS)
            writer.writeheader()
            for row in rows:
                writer.writerow(safe_csv_row(normalize_row(row)))
        shutil.move(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


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
        for row in reader:
            imported = {
                canonical: normalize_value(row.get(original))
                for canonical, original in header_map.items()
            }
            rows.append(normalize_row(imported))
        return rows


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
    for index, row in enumerate(rows):
        if same_contact(row, new_row):
            rows[index] = normalize_row(new_row)
            return rows, "updated"
    rows.append(normalize_row(new_row))
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
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("path", help="Print the contact store path")
    subparsers.add_parser("init", help="Create the contact store if it does not exist")

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

    export_parser = subparsers.add_parser("export", help="Export contacts to a CSV")
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

        ensure_store(store)

        if args.command == "init":
            print(f"Contact store: {store}")
            return 0

        rows = read_rows(store)

        if args.command == "add":
            row = {
                "account name": args.account,
                "record type": normalize_record_type(args.record_type),
                "customer name": args.name,
                "customer role": args.role,
                "customer email address": args.email,
            }
            rows, action = upsert_row(rows, row)
            write_rows(store, rows)
            print(f"{action}: [{row['record type']}] {args.name} <{args.email}>")
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
                        ("customer email address", args.email),
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
                if args.mode == "skip-existing" and any(same_contact(existing, row) for existing in rows):
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
            write_rows(args.output.expanduser(), rows)
            print(f"Exported contacts: {args.output}")
            return 0

        raise ValueError(f"unknown command: {args.command}")
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
