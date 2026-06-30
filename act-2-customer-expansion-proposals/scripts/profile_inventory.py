#!/usr/bin/env python3
"""Profile a customer automation/use-case inventory for agentic proposal work.

Outputs compact JSON with sheet/column metadata, status counts, likely field
mappings, and top rows by annualized volume.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd


FIELD_SYNONYMS = {
    "name": [
        "automation name",
        "use case",
        "idea name",
        "idea title",
        "process name",
        "automation title",
        "title",
    ],
    "status": ["status", "lifecycle"],
    "phase": ["phase", "stage"],
    "agency": ["agency", "department", "business unit", "submitter's business unit"],
    "division": ["division", "team", "submitter's department"],
    "annual_volume": [
        "transactions per year",
        "annual volume",
        "requests per year",
        "cases per year",
        "tickets per year",
    ],
    "weekly_volume": [
        "average transaction volume (per week)",
        "weekly volume",
        "requests per week",
        "cases per week",
        "tickets per week",
    ],
    "hours": ["hours per year", "total hours saved", "hours saved/year"],
    "citizen_facing": ["is this a citizen-facing process", "citizen-facing"],
    "shared_service": ["is this process a shared service", "shared service"],
    "systems": ["systems/applications used in process", "applications used", "systems used"],
    "description": [
        "process description",
        "value statement",
        "qualitative benefits",
        "what qualitative benefits",
        "tags",
    ],
}


WEAK_STATUSES = {"archived", "rejected", "cancelled", "canceled", "duplicate", "decommissioned"}


def clean_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower())


def parse_number(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    match = re.search(r"-?\d+(?:,\d{3})*(?:\.\d+)?|-?\d+(?:\.\d+)?", str(value))
    if not match:
        return None
    return float(match.group(0).replace(",", ""))


def load_workbook(path: Path, sheet: str | None) -> tuple[str, pd.DataFrame]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        sep = "\t" if suffix == ".tsv" else ","
        return path.stem, pd.read_csv(path, dtype=str, sep=sep).fillna("")
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        xls = pd.ExcelFile(path)
        sheet_name = sheet or xls.sheet_names[0]
        return str(sheet_name), pd.read_excel(path, sheet_name=sheet_name, dtype=str).fillna("")
    raise SystemExit(f"Unsupported inventory type: {path.suffix}")


def column_match_score(norm: str, synonym: str) -> int:
    if norm == synonym:
        return 100
    if norm.startswith(f"{synonym} "):
        return 85
    if norm.endswith(f" {synonym}"):
        return 80
    if f" {synonym} " in f" {norm} ":
        return 70
    if len(synonym) >= 8 and synonym in norm:
        return 50
    return 0


def find_columns(columns: list[str]) -> dict[str, list[str]]:
    normalized = [(clean_key(col), col) for col in columns]
    found: dict[str, list[str]] = {}
    for field, synonyms in FIELD_SYNONYMS.items():
        scored = []
        for norm, original in normalized:
            score = max(column_match_score(norm, syn) for syn in synonyms)
            if score:
                scored.append((score, original))
        scored.sort(key=lambda item: (-item[0], columns.index(item[1])))
        found[field] = [original for _, original in scored]
    return found


def nonblank_count(df: pd.DataFrame, column: str) -> int:
    return int(df[column].astype(str).str.strip().ne("").sum())


def prefer_populated_candidates(df: pd.DataFrame, fields: dict[str, list[str]]) -> None:
    evidence_fields = {
        "annual_volume",
        "weekly_volume",
        "hours",
        "citizen_facing",
        "shared_service",
        "systems",
        "description",
    }
    for field in evidence_fields:
        candidates = fields.get(field, [])
        candidates.sort(key=lambda col: (-nonblank_count(df, col), list(df.columns).index(col)))


def annualized_volume(row: pd.Series, fields: dict[str, list[str]]) -> tuple[float | None, str]:
    for col in fields.get("annual_volume", []):
        value = parse_number(row.get(col))
        if value is not None and value > 0:
            return value, f"{col}"
    for col in fields.get("weekly_volume", []):
        value = parse_number(row.get(col))
        if value is not None and value > 0:
            return value * 50, f"{col} * 50"
    return None, ""


def first_value(row: pd.Series, fields: dict[str, list[str]], field: str) -> str:
    for col in fields.get(field, []):
        value = str(row.get(col, "")).strip()
        if value:
            return value
    return ""


def profile(path: Path, sheet: str | None, top_n: int) -> dict[str, Any]:
    sheet_name, df = load_workbook(path, sheet)
    fields = find_columns([str(c) for c in df.columns])
    prefer_populated_candidates(df, fields)

    status_col = fields.get("status", [""])[0] if fields.get("status") else ""
    agency_col = fields.get("agency", [""])[0] if fields.get("agency") else ""

    top_rows = []
    for idx, row in df.iterrows():
        vol, source = annualized_volume(row, fields)
        if vol is None:
            continue
        status = first_value(row, fields, "status")
        top_rows.append(
            {
                "row_number": int(idx) + 2,
                "name": first_value(row, fields, "name"),
                "agency": first_value(row, fields, "agency"),
                "division": first_value(row, fields, "division"),
                "phase": first_value(row, fields, "phase"),
                "status": status,
                "annualized_volume": vol,
                "volume_source": source,
                "weak_status": clean_key(status) in WEAK_STATUSES,
                "citizen_facing": first_value(row, fields, "citizen_facing"),
                "shared_service": first_value(row, fields, "shared_service"),
                "systems": first_value(row, fields, "systems"),
            }
        )

    top_rows.sort(key=lambda item: item["annualized_volume"], reverse=True)

    missingness = {}
    for field, cols in fields.items():
        if not cols:
            continue
        col = cols[0]
        blank = df[col].astype(str).str.strip().eq("").sum()
        missingness[col] = {
            "blank_rows": int(blank),
            "blank_pct": round(float(blank) / len(df) * 100, 1) if len(df) else 0,
        }

    result = {
        "input": str(path),
        "sheet": sheet_name,
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "field_candidates": fields,
        "status_counts": df[status_col].value_counts(dropna=False).head(25).to_dict() if status_col else {},
        "agency_counts": df[agency_col].value_counts(dropna=False).head(25).to_dict() if agency_col else {},
        "missingness": missingness,
        "top_volume_rows": top_rows[:top_n],
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path, help="Path to .xlsx, .xls, .xlsm, .csv, or .tsv inventory")
    parser.add_argument("--sheet", help="Worksheet name. Defaults to first sheet for Excel files.")
    parser.add_argument("--top", type=int, default=25, help="Number of top volume rows to include")
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    args = parser.parse_args()

    result = profile(args.inventory, args.sheet, args.top)
    text = json.dumps(result, indent=2, ensure_ascii=True)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
