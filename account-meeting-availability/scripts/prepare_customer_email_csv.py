#!/usr/bin/env python3
"""Validate and normalize account meeting contact CSV inputs."""

from __future__ import annotations

import argparse
import csv
import re
import sys
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

OUTPUT_HEADERS = [
    "sourced customer email address",
    "sourcing confidence",
    "sourcing evidence",
    "source type",
    "source date",
    "needs review",
]

RECORD_TYPES = {"customer", "uipath"}

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
    "customer title": "customer role",
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


def normalize_header(value: str) -> str:
    compact = re.sub(r"[^a-z0-9]+", "", value.strip().lower())
    spaced = re.sub(r"[^a-z0-9]+", " ", value.strip().lower()).strip()
    return ALIASES.get(compact) or ALIASES.get(spaced) or spaced


def normalize_record_type(value: str | None, default: str = "customer") -> str:
    raw = (value or "").strip().casefold()
    if not raw:
        return default
    compact = re.sub(r"[^a-z0-9]+", "", raw)
    spaced = re.sub(r"[^a-z0-9]+", " ", raw).strip()
    normalized = RECORD_TYPE_ALIASES.get(compact) or RECORD_TYPE_ALIASES.get(spaced) or spaced
    if normalized not in RECORD_TYPES:
        raise ValueError("record type must be 'customer' or 'uipath'")
    return normalized


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")
        rows = list(reader)
    return reader.fieldnames, rows


def build_header_map(headers: list[str]) -> dict[str, str]:
    header_map: dict[str, str] = {}
    seen: dict[str, str] = {}
    for header in headers:
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
        raise ValueError("Missing required column(s): " + ", ".join(missing))
    return header_map


def normalize_rows(rows: list[dict[str, str]], header_map: dict[str, str]) -> list[dict[str, str]]:
    normalized_rows = []
    for row in rows:
        normalized = {
            canonical: (row.get(original, "") or "").strip()
            for canonical, original in header_map.items()
        }
        normalized["record type"] = normalize_record_type(normalized.get("record type"))
        email = normalized.get("customer email address", "")
        normalized.update(
            {
                "sourced customer email address": email,
                "sourcing confidence": "provided" if email else "none",
                "sourcing evidence": "Provided in input CSV." if email else "",
                "source type": "provided-csv" if email else "none",
                "source date": "",
                "needs review": "no" if email else "yes",
            }
        )
        normalized_rows.append(normalized)
    return normalized_rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    headers = CANONICAL_HEADERS + OUTPUT_HEADERS
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_template(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANONICAL_HEADERS)
        writer.writeheader()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and normalize an account meeting contact CSV."
    )
    parser.add_argument("input", nargs="?", help="Input CSV path")
    parser.add_argument("--output", "-o", help="Normalized output CSV path")
    parser.add_argument("--template", help="Write an empty template CSV and exit")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    try:
        if args.template:
            write_template(Path(args.template))
            print(f"Wrote template: {args.template}")
            return 0

        if not args.input:
            raise ValueError("input CSV is required unless --template is used")

        input_path = Path(args.input)
        output_path = Path(args.output) if args.output else input_path.with_name(
            f"{input_path.stem}.normalized{input_path.suffix}"
        )

        headers, rows = read_csv(input_path)
        header_map = build_header_map(headers)
        normalized_rows = normalize_rows(rows, header_map)
        write_csv(output_path, normalized_rows)

        missing_count = sum(
            1 for row in normalized_rows if not row.get("customer email address")
        )
        print(f"Rows processed: {len(normalized_rows)}")
        print(f"Rows needing sourcing: {missing_count}")
        print(f"Normalized CSV: {output_path}")
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
