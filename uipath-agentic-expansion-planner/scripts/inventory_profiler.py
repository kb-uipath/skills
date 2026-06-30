#!/usr/bin/env python3
"""
Profile a customer automation/use-case inventory for UiPath agentic expansion planning.

Inputs: .csv, .tsv, .xlsx, or .xlsm inventory files.
Outputs: inventory_profile.json and inventory_profile.md in the selected output directory.

This script is intentionally descriptive rather than prescriptive: it identifies inventory
structure, candidate columns, status distribution, owner/department density, value/volume
fields, missingness, duplicate names, and row samples for analyst review. It does not make
final recommendations by itself.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from openpyxl import load_workbook
except Exception:  # pragma: no cover - only needed for xlsx input
    load_workbook = None


COLUMN_KEYWORDS: Dict[str, List[str]] = {
    "use_case_name": [
        "use case",
        "usecase",
        "automation name",
        "process name",
        "opportunity name",
        "idea name",
        "project name",
        "bot name",
        "solution name",
        "title",
        "name",
    ],
    "description": [
        "description",
        "business problem",
        "problem statement",
        "process description",
        "scope",
        "summary",
        "details",
        "manual process",
    ],
    "status": [
        "status",
        "stage",
        "phase",
        "state",
        "lifecycle",
        "deployment status",
        "project status",
    ],
    "department": [
        "department",
        "business unit",
        "agency",
        "division",
        "function",
        "organization",
        "org",
        "area",
        "team",
        "process owner group",
    ],
    "owner": [
        "owner",
        "process owner",
        "business owner",
        "sme",
        "sponsor",
        "requestor",
        "requester",
        "contact",
    ],
    "systems": [
        "application",
        "applications",
        "system",
        "systems",
        "platform",
        "erp",
        "source system",
        "target system",
        "technology",
    ],
    "volume": [
        "volume",
        "annual volume",
        "yearly volume",
        "monthly volume",
        "weekly volume",
        "transactions",
        "transaction count",
        "cases",
        "requests",
        "items",
    ],
    "weekly_volume": [
        "weekly volume",
        "per week",
        "weekly transactions",
        "weekly cases",
        "weekly requests",
    ],
    "annual_volume": [
        "annual volume",
        "yearly volume",
        "annual transactions",
        "annual cases",
        "annual requests",
        "per year",
    ],
    "handling_time": [
        "handling time",
        "average handle time",
        "aht",
        "minutes per transaction",
        "hours per transaction",
        "manual time",
        "processing time",
        "time per case",
    ],
    "hours_saved": [
        "hours saved",
        "annual hours",
        "hours avoided",
        "capacity saved",
        "fte saved",
        "fte",
        "savings hours",
    ],
    "value": [
        "value",
        "savings",
        "cost savings",
        "benefit",
        "annual benefit",
        "roi",
        "return",
        "dollars",
        "usd",
    ],
    "priority": [
        "priority",
        "rank",
        "score",
        "business value",
        "impact",
        "complexity",
        "feasibility",
    ],
    "date": [
        "created",
        "submitted",
        "date",
        "go live",
        "golive",
        "deployment date",
        "last updated",
        "modified",
    ],
}

PRODUCTION_TERMS = [
    "production",
    "prod",
    "live",
    "deployed",
    "implemented",
    "in use",
    "active",
    "complete",
    "completed",
    "operational",
]
PIPELINE_TERMS = [
    "in progress",
    "development",
    "dev",
    "build",
    "testing",
    "uat",
    "pilot",
    "poc",
    "approved",
    "planned",
    "backlog",
    "assessment",
]
IDEA_TERMS = ["idea", "candidate", "intake", "submitted", "requested", "opportunity", "concept"]
EXCLUDED_TERMS = [
    "retired",
    "decommissioned",
    "cancelled",
    "canceled",
    "rejected",
    "duplicate",
    "archived",
    "on hold",
    "not started",
    "withdrawn",
]

STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "into",
    "onto",
    "that",
    "this",
    "use",
    "case",
    "automation",
    "automated",
    "process",
    "bot",
    "robot",
    "rpa",
    "data",
    "report",
    "reports",
    "request",
    "requests",
    "review",
    "update",
    "create",
    "system",
    "manual",
    "task",
    "workflow",
}


def clean_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def normalize_text(value: Any) -> str:
    text = clean_cell(value).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def nonempty(value: Any) -> bool:
    return clean_cell(value) != ""


def score_header(header: str, keywords: Iterable[str]) -> int:
    h = normalize_text(header)
    if not h:
        return 0
    best = 0
    for keyword in keywords:
        k = normalize_text(keyword)
        if not k:
            continue
        if h == k:
            best = max(best, 10)
        elif h.endswith(" " + k) or h.startswith(k + " "):
            best = max(best, 8)
        elif k in h:
            best = max(best, 6)
        elif all(part in h.split() for part in k.split()):
            best = max(best, 4)
    return best


def dedupe_headers(headers: List[str]) -> List[str]:
    seen: Dict[str, int] = defaultdict(int)
    result: List[str] = []
    for index, header in enumerate(headers, start=1):
        base = clean_cell(header) or f"column_{index}"
        seen[base] += 1
        if seen[base] == 1:
            result.append(base)
        else:
            result.append(f"{base}_{seen[base]}")
    return result


def sniff_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        return dialect.delimiter
    except Exception:
        return "\t" if "\t" in sample else ","


def read_csv_inventory(path: Path) -> Dict[str, List[Dict[str, Any]]]:
    encodings = ["utf-8-sig", "utf-8", "latin-1"]
    last_error: Optional[Exception] = None
    for encoding in encodings:
        try:
            sample = path.read_text(encoding=encoding, errors="replace")[:4096]
            delimiter = sniff_delimiter(sample)
            rows: List[Dict[str, Any]] = []
            with path.open("r", encoding=encoding, errors="replace", newline="") as handle:
                reader = csv.reader(handle, delimiter=delimiter)
                raw_rows = list(reader)
            if not raw_rows:
                return {path.stem: []}
            header_index = find_header_row(raw_rows[:25])
            headers = dedupe_headers([clean_cell(x) for x in raw_rows[header_index]])
            for row_number, raw in enumerate(raw_rows[header_index + 1 :], start=header_index + 2):
                if not any(nonempty(x) for x in raw):
                    continue
                padded = raw + [""] * max(0, len(headers) - len(raw))
                row = {headers[i]: clean_cell(padded[i]) if i < len(padded) else "" for i in range(len(headers))}
                row["__row_number"] = row_number
                row["__sheet"] = path.stem
                rows.append(row)
            return {path.stem: rows}
        except Exception as exc:  # pragma: no cover - fallback path
            last_error = exc
    raise RuntimeError(f"could not read csv file: {last_error}")


def find_header_row(raw_rows: List[Iterable[Any]]) -> int:
    best_index = 0
    best_score = -1
    for index, row in enumerate(raw_rows):
        cells = [clean_cell(x) for x in row]
        filled = [x for x in cells if x]
        if len(filled) < 2:
            continue
        keyword_hits = 0
        for cell in filled:
            cell_norm = normalize_text(cell)
            for keywords in COLUMN_KEYWORDS.values():
                if score_header(cell_norm, keywords) >= 6:
                    keyword_hits += 1
                    break
        score = len(filled) + (keyword_hits * 4)
        if score > best_score:
            best_index = index
            best_score = score
    return best_index


def read_xlsx_inventory(path: Path, selected_sheet: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    if load_workbook is None:
        raise RuntimeError("openpyxl is required for .xlsx/.xlsm input but is not installed")
    workbook = load_workbook(filename=path, read_only=True, data_only=True)
    sheet_names = [selected_sheet] if selected_sheet else workbook.sheetnames
    sheets: Dict[str, List[Dict[str, Any]]] = {}
    for sheet_name in sheet_names:
        if sheet_name not in workbook.sheetnames:
            raise RuntimeError(f"sheet not found: {sheet_name}")
        worksheet = workbook[sheet_name]
        raw_rows = []
        for row in worksheet.iter_rows(values_only=True):
            values = [clean_cell(cell) for cell in row]
            if any(values):
                raw_rows.append(values)
        if not raw_rows:
            sheets[sheet_name] = []
            continue
        header_index = find_header_row(raw_rows[:25])
        headers = dedupe_headers(raw_rows[header_index])
        rows: List[Dict[str, Any]] = []
        for absolute_index, raw in enumerate(raw_rows[header_index + 1 :], start=header_index + 2):
            if not any(nonempty(x) for x in raw):
                continue
            padded = raw + [""] * max(0, len(headers) - len(raw))
            row = {headers[i]: clean_cell(padded[i]) if i < len(padded) else "" for i in range(len(headers))}
            row["__row_number"] = absolute_index
            row["__sheet"] = sheet_name
            rows.append(row)
        sheets[sheet_name] = rows
    return sheets


def load_inventory(path: Path, sheet: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv", ".txt"}:
        return read_csv_inventory(path)
    if suffix in {".xlsx", ".xlsm"}:
        return read_xlsx_inventory(path, selected_sheet=sheet)
    raise RuntimeError(f"unsupported file type: {suffix}. use .csv, .tsv, .xlsx, or .xlsm")


def get_headers(rows: List[Dict[str, Any]]) -> List[str]:
    ordered: List[str] = []
    seen = set()
    for row in rows:
        for key in row.keys():
            if key.startswith("__"):
                continue
            if key not in seen:
                seen.add(key)
                ordered.append(key)
    return ordered


def guess_columns(headers: List[str]) -> Dict[str, Dict[str, Any]]:
    guesses: Dict[str, Dict[str, Any]] = {}
    for field_type, keywords in COLUMN_KEYWORDS.items():
        scored = []
        for header in headers:
            score = score_header(header, keywords)
            if score > 0:
                scored.append({"column": header, "score": score})
        scored.sort(key=lambda item: (-item["score"], item["column"].lower()))
        if scored:
            guesses[field_type] = {
                "best": scored[0]["column"],
                "score": scored[0]["score"],
                "alternates": [item["column"] for item in scored[1:5]],
            }
    return guesses


def parse_number(value: Any) -> Optional[float]:
    text = clean_cell(value)
    if not text:
        return None
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
    text = text.replace(",", "")
    text = text.replace("$", "")
    text = text.replace("%", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        number = float(match.group(0))
        return -number if negative else number
    except ValueError:
        return None


def numeric_profile(rows: List[Dict[str, Any]], headers: List[str]) -> Dict[str, Dict[str, Any]]:
    profiles: Dict[str, Dict[str, Any]] = {}
    for header in headers:
        values = [parse_number(row.get(header)) for row in rows if nonempty(row.get(header))]
        values = [value for value in values if value is not None]
        nonblank = sum(1 for row in rows if nonempty(row.get(header)))
        if not values or nonblank == 0:
            continue
        coverage = len(values) / max(nonblank, 1)
        if len(values) >= 3 and coverage >= 0.5:
            sorted_values = sorted(values)
            profiles[header] = {
                "count": len(values),
                "min": sorted_values[0],
                "median": sorted_values[len(sorted_values) // 2],
                "max": sorted_values[-1],
                "sum": round(sum(values), 2),
                "parseable_coverage_of_nonblank": round(coverage, 3),
            }
    return profiles


def classify_status(value: Any) -> str:
    text = normalize_text(value)
    if not text:
        return "unknown"
    if any(term in text for term in EXCLUDED_TERMS):
        return "excluded"
    if any(term in text for term in PRODUCTION_TERMS):
        return "production"
    if any(term in text for term in PIPELINE_TERMS):
        return "pipeline"
    if any(term in text for term in IDEA_TERMS):
        return "idea"
    return "other"


def coverage(rows: List[Dict[str, Any]], column: Optional[str]) -> Dict[str, Any]:
    if not column:
        return {"column": None, "nonblank": 0, "coverage_pct": 0.0}
    nonblank = sum(1 for row in rows if nonempty(row.get(column)))
    return {
        "column": column,
        "nonblank": nonblank,
        "coverage_pct": round((nonblank / len(rows) * 100.0) if rows else 0.0, 1),
    }


def top_counts(rows: List[Dict[str, Any]], column: Optional[str], limit: int = 20) -> List[Dict[str, Any]]:
    if not column:
        return []
    counter = Counter(clean_cell(row.get(column)) or "blank" for row in rows)
    return [{"value": key, "count": value} for key, value in counter.most_common(limit)]


def extract_keywords(rows: List[Dict[str, Any]], columns: List[str], limit: int = 40) -> List[Dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in rows:
        text = " ".join(clean_cell(row.get(col)) for col in columns if col)
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9]{2,}", text.lower()):
            if token not in STOP_WORDS and len(token) > 2:
                counter[token] += 1
    return [{"term": term, "count": count} for term, count in counter.most_common(limit)]


def duplicate_name_groups(rows: List[Dict[str, Any]], name_column: Optional[str], limit: int = 30) -> List[Dict[str, Any]]:
    if not name_column:
        return []
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        raw_name = clean_cell(row.get(name_column))
        key = normalize_text(raw_name)
        if key:
            groups[key].append(row)
    duplicates = []
    for key, group in groups.items():
        if len(group) > 1:
            duplicates.append(
                {
                    "normalized_name": key,
                    "count": len(group),
                    "examples": [
                        {
                            "name": clean_cell(item.get(name_column)),
                            "sheet": item.get("__sheet"),
                            "row_number": item.get("__row_number"),
                        }
                        for item in group[:5]
                    ],
                }
            )
    duplicates.sort(key=lambda item: (-item["count"], item["normalized_name"]))
    return duplicates[:limit]


def compact_row(row: Dict[str, Any], columns: List[str]) -> Dict[str, Any]:
    result = {"sheet": row.get("__sheet"), "row_number": row.get("__row_number")}
    for column in columns:
        if column and column in row:
            value = clean_cell(row.get(column))
            if len(value) > 220:
                value = value[:217] + "..."
            result[column] = value
    return result


def top_rows_by_metric(
    rows: List[Dict[str, Any]],
    metric_columns: List[str],
    context_columns: List[str],
    limit: int = 10,
) -> Dict[str, List[Dict[str, Any]]]:
    output: Dict[str, List[Dict[str, Any]]] = {}
    for column in metric_columns:
        scored = []
        for row in rows:
            number = parse_number(row.get(column))
            if number is None:
                continue
            scored.append((number, row))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        if scored:
            output[column] = [
                {"metric_value": number, **compact_row(row, context_columns)} for number, row in scored[:limit]
            ]
    return output


def build_profile(path: Path, sheets: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    all_rows: List[Dict[str, Any]] = []
    sheet_profiles = []
    for sheet_name, rows in sheets.items():
        headers = get_headers(rows)
        all_rows.extend(rows)
        sheet_profiles.append(
            {
                "sheet": sheet_name,
                "rows": len(rows),
                "columns": headers,
                "column_count": len(headers),
            }
        )

    headers = get_headers(all_rows)
    guesses = guess_columns(headers)
    get_best = lambda key: guesses.get(key, {}).get("best")

    name_col = get_best("use_case_name")
    desc_col = get_best("description")
    status_col = get_best("status")
    dept_col = get_best("department")
    owner_col = get_best("owner")
    systems_col = get_best("systems")
    volume_col = get_best("volume")
    weekly_volume_col = get_best("weekly_volume")
    annual_volume_col = get_best("annual_volume")
    handling_time_col = get_best("handling_time")
    hours_saved_col = get_best("hours_saved")
    value_col = get_best("value")
    priority_col = get_best("priority")

    status_breakdown = Counter(classify_status(row.get(status_col)) for row in all_rows) if status_col else Counter()
    raw_status_breakdown = top_counts(all_rows, status_col, limit=30)

    numeric = numeric_profile(all_rows, headers)
    detected_metric_columns = []
    for candidate in [volume_col, weekly_volume_col, annual_volume_col, handling_time_col, hours_saved_col, value_col, priority_col]:
        if candidate and candidate in numeric and candidate not in detected_metric_columns:
            detected_metric_columns.append(candidate)
    if len(detected_metric_columns) < 5:
        for column in numeric.keys():
            if column not in detected_metric_columns:
                detected_metric_columns.append(column)
            if len(detected_metric_columns) >= 8:
                break

    context_columns = [col for col in [name_col, desc_col, status_col, dept_col, owner_col, systems_col] if col]
    core_fields = {
        "use_case_name": name_col,
        "description": desc_col,
        "status": status_col,
        "department": dept_col,
        "owner": owner_col,
        "systems": systems_col,
        "volume": volume_col,
        "weekly_volume": weekly_volume_col,
        "annual_volume": annual_volume_col,
        "handling_time": handling_time_col,
        "hours_saved": hours_saved_col,
        "value": value_col,
        "priority": priority_col,
    }

    required_for_full_quality = ["use_case_name", "description", "status", "department"]
    missing_core = [field for field in required_for_full_quality if not core_fields.get(field)]
    weak_value_fields = not any(core_fields.get(field) for field in ["volume", "weekly_volume", "annual_volume", "handling_time", "hours_saved", "value"])

    profile = {
        "metadata": {
            "source_file": str(path),
            "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "sheet_count": len(sheets),
            "total_rows": len(all_rows),
            "total_columns": len(headers),
        },
        "sheets": sheet_profiles,
        "detected_columns": guesses,
        "core_field_mapping": core_fields,
        "data_quality": {
            "missing_core_fields_for_full_quality": missing_core,
            "no_value_or_volume_fields_detected": weak_value_fields,
            "field_coverage": {field: coverage(all_rows, column) for field, column in core_fields.items()},
            "duplicate_name_groups": duplicate_name_groups(all_rows, name_col),
        },
        "status_summary": {
            "normalized_status_counts": dict(status_breakdown),
            "raw_status_top_values": raw_status_breakdown,
        },
        "owner_department_summary": {
            "department_top_values": top_counts(all_rows, dept_col),
            "owner_top_values": top_counts(all_rows, owner_col),
        },
        "systems_summary": {
            "systems_top_values": top_counts(all_rows, systems_col),
        },
        "numeric_profiles": numeric,
        "text_patterns": {
            "frequent_terms_from_name_description": extract_keywords(
                all_rows, [col for col in [name_col, desc_col] if col]
            )
        },
        "top_rows_by_detected_metrics": top_rows_by_metric(all_rows, detected_metric_columns, context_columns),
        "representative_rows": [compact_row(row, context_columns) for row in all_rows[:15]],
    }
    return profile


def markdown_table(rows: List[Dict[str, Any]], columns: List[str]) -> str:
    if not rows:
        return "No data detected.\n"
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    lines = [header, separator]
    for row in rows:
        cells = []
        for column in columns:
            value = clean_cell(row.get(column, ""))
            value = value.replace("|", "\\|")
            cells.append(value)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def profile_to_markdown(profile: Dict[str, Any]) -> str:
    meta = profile["metadata"]
    lines = [
        "# Inventory profile",
        "",
        f"Source file: `{meta['source_file']}`",
        f"Generated UTC: `{meta['generated_at_utc']}`",
        f"Sheets: {meta['sheet_count']}",
        f"Rows: {meta['total_rows']}",
        f"Columns: {meta['total_columns']}",
        "",
        "## Sheets",
    ]
    sheet_rows = [
        {"sheet": item["sheet"], "rows": str(item["rows"]), "columns": str(item["column_count"])}
        for item in profile["sheets"]
    ]
    lines.append(markdown_table(sheet_rows, ["sheet", "rows", "columns"]))

    lines.extend(["", "## Detected core field mapping"])
    mapping_rows = []
    for field, column in profile["core_field_mapping"].items():
        coverage_obj = profile["data_quality"]["field_coverage"].get(field, {})
        mapping_rows.append(
            {
                "field": field,
                "detected_column": column or "not detected",
                "coverage_pct": str(coverage_obj.get("coverage_pct", 0.0)),
            }
        )
    lines.append(markdown_table(mapping_rows, ["field", "detected_column", "coverage_pct"]))

    lines.extend(["", "## Data quality flags"])
    dq = profile["data_quality"]
    missing = dq["missing_core_fields_for_full_quality"]
    lines.append(f"- Missing core fields for full-quality output: {', '.join(missing) if missing else 'none detected'}")
    lines.append(f"- No value or volume fields detected: {dq['no_value_or_volume_fields_detected']}")
    lines.append(f"- Duplicate name groups detected: {len(dq['duplicate_name_groups'])}")

    lines.extend(["", "## Normalized status counts"])
    status_rows = [
        {"status_category": key, "count": str(value)}
        for key, value in sorted(profile["status_summary"]["normalized_status_counts"].items())
    ]
    lines.append(markdown_table(status_rows, ["status_category", "count"]))

    lines.extend(["", "## Top departments"])
    dept_rows = [
        {"department": item["value"], "count": str(item["count"])}
        for item in profile["owner_department_summary"]["department_top_values"][:15]
    ]
    lines.append(markdown_table(dept_rows, ["department", "count"]))

    lines.extend(["", "## Numeric fields"])
    numeric_rows = []
    for column, stats in profile["numeric_profiles"].items():
        numeric_rows.append(
            {
                "column": column,
                "count": str(stats["count"]),
                "median": str(stats["median"]),
                "max": str(stats["max"]),
                "sum": str(stats["sum"]),
            }
        )
    lines.append(markdown_table(numeric_rows, ["column", "count", "median", "max", "sum"]))

    lines.extend(["", "## Frequent terms from names and descriptions"])
    term_rows = [
        {"term": item["term"], "count": str(item["count"])}
        for item in profile["text_patterns"]["frequent_terms_from_name_description"][:25]
    ]
    lines.append(markdown_table(term_rows, ["term", "count"]))

    lines.extend(["", "## Representative rows"])
    rep_rows = profile["representative_rows"][:10]
    if rep_rows:
        columns = list(rep_rows[0].keys())
        lines.append(markdown_table(rep_rows, columns))
    else:
        lines.append("No representative rows available.\n")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile a UiPath customer use-case inventory.")
    parser.add_argument("--input", required=True, help="Path to .csv, .tsv, .xlsx, or .xlsm inventory file")
    parser.add_argument("--outdir", required=True, help="Directory where profile outputs should be written")
    parser.add_argument("--sheet", default=None, help="Optional worksheet name for Excel input")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    outdir = Path(args.outdir).expanduser().resolve()
    if not input_path.exists():
        print(f"input file not found: {input_path}", file=sys.stderr)
        return 2
    outdir.mkdir(parents=True, exist_ok=True)

    try:
        sheets = load_inventory(input_path, sheet=args.sheet)
        profile = build_profile(input_path, sheets)
    except Exception as exc:
        print(f"failed to profile inventory: {exc}", file=sys.stderr)
        return 1

    json_path = outdir / "inventory_profile.json"
    md_path = outdir / "inventory_profile.md"
    json_path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(profile_to_markdown(profile), encoding="utf-8")
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
