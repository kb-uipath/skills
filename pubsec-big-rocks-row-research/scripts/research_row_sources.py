#!/usr/bin/env python3
from __future__ import annotations

import argparse
import calendar
import json
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


DEFAULT_SOURCES = [
    "/private/tmp/migrationMaster.xlsx",
    "/private/tmp/TAC_Account_Tracking.xlsx",
    "/private/tmp/PubSec_Gov_SFDC.xlsx",
    "/private/tmp/Wingman_Active_Organizations.xlsx",
    "/private/tmp/Dans_list_of_Org_Lic.xlsx",
]

MAIN_SHEET = "PUBSEC Big Rocks_FY27"
HEADER_ROW = 7
DATA_START_ROW = 8
DATA_END_ROW = 354

TARGET_HEADERS = {
    11: "Bot/License Utilization",
    12: "Cloud Y/N",
    13: "Consuming AI Units Today: Y/N",
    14: "Agent Units Purchased Y/N",
    15: "Test Status",
    16: "IXP Status",
    17: "Agentic Status",
    18: "Regional Leader Only: Bell Curve Adoption Flag",
    19: "FY27 Big Rocks",
    20: "Tracking Value Realized",
    21: "At Risk/Churn Forecasted: Y/N",
    23: "Notes / Evidence Additions",
}

DATE_FIELD_HINTS = (
    "updated",
    "modified",
    "last activity",
    "last modified",
    "activity date",
    "report date",
    "export date",
)


def norm(value: Any) -> str:
    text = str(value or "").lower().replace("&", " and ")
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(
        r"\b(inc|llc|ltd|corp|corporation|limited|department|dept|office|of|the|and|hq)\b",
        " ",
        text,
    )
    return re.sub(r"\s+", " ", text).strip()


def raw_norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def clean(value: Any, limit: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "..."
    return text


def parse_as_of(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    raise SystemExit(f"Invalid --as-of-date {value!r}; use YYYY-MM-DD")


def subtract_months(value: datetime, months: int) -> datetime:
    month = value.month - months
    year = value.year
    while month <= 0:
        month += 12
        year -= 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def file_modified_at(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def format_dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def parse_dateish(value: Any) -> datetime | None:
    if value is None:
        return None
    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    patterns = [
        ("%Y-%m-%d", r"\b\d{4}-\d{1,2}-\d{1,2}\b"),
        ("%m/%d/%Y", r"\b\d{1,2}/\d{1,2}/\d{4}\b"),
        ("%m/%d/%y", r"\b\d{1,2}/\d{1,2}/\d{2}\b"),
        ("%m-%d-%Y", r"\b\d{1,2}-\d{1,2}-\d{4}\b"),
        ("%m-%d-%y", r"\b\d{1,2}-\d{1,2}-\d{2}\b"),
    ]
    for fmt, pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        try:
            return datetime.strptime(match.group(0), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def sheet_date(ws_title: str) -> datetime | None:
    return parse_dateish(ws_title)


def row_update_dates(data: dict[str, Any]) -> list[dict[str, str]]:
    dates = []
    for key, value in data.items():
        key_l = key.lower()
        if any(hint in key_l for hint in DATE_FIELD_HINTS):
            parsed = parse_dateish(value)
            if parsed:
                dates.append({"field": key, "date": parsed.date().isoformat()})
    return dates


def is_recent(dt: datetime | None, cutoff: datetime) -> bool:
    return bool(dt and dt >= cutoff)


def blank_like(value: Any) -> bool:
    text = str(value or "").strip().replace("\r\n", "\n")
    compact = re.sub(r"\s+", "", text)
    return text == "" or compact in {"•", "••", "•••", "-", "--", "---"}


def likely_header_row(ws, max_scan: int = 5) -> int:
    best_row = 1
    best_score = -1
    keywords = {
        "account",
        "account name",
        "accountname",
        "uipath account",
        "customer status",
        "current platform",
        "target platform",
        "notes",
    }
    for row in range(1, min(ws.max_row, max_scan) + 1):
        values = [clean(ws.cell(row, col).value, 120).lower() for col in range(1, ws.max_column + 1)]
        score = sum(1 for value in values if value in keywords or "account" in value)
        if score > best_score:
            best_row = row
            best_score = score
    return best_row


def row_to_dict(ws, header_row: int, row: int) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for col in range(1, ws.max_column + 1):
        header = ws.cell(header_row, col).value
        if header is None:
            continue
        key = clean(header, 120)
        value = ws.cell(row, col).value
        if value is not None and str(value).strip() != "":
            data[key] = value
    return data


def find_name_col(ws, header_row: int) -> int | None:
    candidates = {
        "account",
        "account name",
        "accountname",
        "uipath account",
        "name",
        "customer",
    }
    for col in range(1, ws.max_column + 1):
        value = clean(ws.cell(header_row, col).value, 120).lower()
        if value in candidates:
            return col
    for col in range(1, ws.max_column + 1):
        value = clean(ws.cell(header_row, col).value, 120).lower()
        if "account" in value and "owner" not in value and "id" not in value:
            return col
    return None


def load_main_row(workbook: Path, sheet: str, row: int | None, account: str | None) -> dict[str, Any]:
    wb = load_workbook(workbook, data_only=False, read_only=False)
    if sheet not in wb.sheetnames:
        raise SystemExit(f"Sheet not found: {sheet}. Available: {', '.join(wb.sheetnames)}")
    ws = wb[sheet]

    target_row = row
    if target_row is None:
        if not account:
            raise SystemExit("Provide --row or --account")
        account_norm = norm(account)
        matches = []
        for r in range(DATA_START_ROW, min(ws.max_row, DATA_END_ROW) + 1):
            name = ws.cell(r, 1).value
            if not name:
                continue
            ratio = SequenceMatcher(None, account_norm, norm(name)).ratio()
            if norm(name) == account_norm or raw_norm(name) == raw_norm(account) or ratio >= 0.94:
                matches.append((ratio, r, str(name)))
        if not matches:
            raise SystemExit(f"No row matched account: {account}")
        matches.sort(reverse=True)
        target_row = matches[0][1]

    headers = {col: ws.cell(HEADER_ROW, col).value for col in range(1, ws.max_column + 1)}
    values = {}
    blanks = []
    for col in range(1, ws.max_column + 1):
        header = headers.get(col) or f"Column {col}"
        value = ws.cell(target_row, col).value
        values[str(header)] = value
        if col in TARGET_HEADERS and blank_like(value):
            blanks.append({"cell": ws.cell(target_row, col).coordinate, "header": TARGET_HEADERS[col]})

    return {
        "sheet": sheet,
        "row": target_row,
        "account": ws.cell(target_row, 1).value,
        "headers": headers,
        "values": values,
        "blank_target_fields": blanks,
        "workbook_sheets": wb.sheetnames,
    }


def bounded_max_row(ws, cap: int = 1000) -> int:
    """Avoid accidentally scanning Excel's full row limit when formatting bloats dimensions."""
    return min(ws.max_row or 0, cap)


def match_records(
    source_path: Path,
    account: str,
    cutoff: datetime,
    excluded: list[dict[str, Any]],
    include_stale: bool = False,
    max_rows_per_sheet: int = 12,
) -> list[dict[str, Any]]:
    if not source_path.exists():
        return []

    source_mtime = file_modified_at(source_path)
    if not include_stale and source_mtime and source_mtime < cutoff:
        excluded.append(
            {
                "source_file": str(source_path),
                "reason": "local file modified before cutoff",
                "modified_at": format_dt(source_mtime),
            }
        )
        return []

    account_norm = norm(account)
    account_raw = raw_norm(account)
    account_tokens = {token for token in account_norm.split() if len(token) >= 3}
    records: list[dict[str, Any]] = []
    wb = load_workbook(source_path, data_only=True, read_only=False)

    for ws in wb.worksheets:
        header_row = likely_header_row(ws)
        name_col = find_name_col(ws, header_row)
        if not name_col:
            continue
        ws_date = sheet_date(ws.title)
        if not include_stale and ws_date and ws_date < cutoff:
            excluded.append(
                {
                    "source_file": str(source_path),
                    "sheet": ws.title,
                    "reason": "sheet name date before cutoff",
                    "sheet_date": format_dt(ws_date),
                }
            )
            continue

        sheet_records = []
        for row in range(header_row + 1, bounded_max_row(ws) + 1):
            name = ws.cell(row, name_col).value
            if not name:
                continue
            name_norm = norm(name)
            name_raw = raw_norm(name)
            exact = name_norm == account_norm or name_raw == account_raw
            contains = (
                len(account_norm) > 12
                and len(name_norm) > 12
                and (account_norm in name_norm or name_norm in account_norm)
            )
            if not exact and not contains and account_tokens.isdisjoint(set(name_norm.split())):
                continue
            ratio = SequenceMatcher(None, account_norm, name_norm).ratio() if name_norm else 0
            if exact or contains or ratio >= 0.94:
                data = row_to_dict(ws, header_row, row)
                update_dates = row_update_dates(data)
                current_update_dates = [item for item in update_dates if parse_dateish(item["date"]) and parse_dateish(item["date"]) >= cutoff]
                stale_update_dates = [item for item in update_dates if parse_dateish(item["date"]) and parse_dateish(item["date"]) < cutoff]
                if update_dates and not current_update_dates and not include_stale:
                    excluded.append(
                        {
                            "source_file": str(source_path),
                            "sheet": ws.title,
                            "row": row,
                            "matched_name": str(name),
                            "reason": "row update/activity date before cutoff",
                            "row_dates": update_dates,
                        }
                    )
                    continue
                sheet_records.append(
                    {
                        "source_file": str(source_path),
                        "sheet": ws.title,
                        "row": row,
                        "matched_name": str(name),
                        "match_score": round(1.0 if exact else ratio, 3),
                        "source_modified_at": format_dt(source_mtime),
                        "source_freshness_basis": "local file modified time; verify upstream SharePoint/SFDC metadata before using for cell values",
                        "row_update_dates": update_dates,
                        "stale_row_update_dates": stale_update_dates,
                        "data": data,
                    }
                )
        records.extend(sorted(sheet_records, key=lambda item: item["match_score"], reverse=True)[:max_rows_per_sheet])
    return records


def scan_workbook_tabs(
    workbook: Path,
    account: str,
    main_sheet: str,
    cutoff: datetime,
    excluded: list[dict[str, Any]],
    include_stale: bool = False,
) -> list[dict[str, Any]]:
    wb = load_workbook(workbook, data_only=True, read_only=False)
    source_mtime = file_modified_at(workbook)
    account_norm = norm(account)
    account_raw = raw_norm(account)
    matches = []
    for ws in wb.worksheets:
        if ws.title == main_sheet:
            continue
        ws_date = sheet_date(ws.title)
        if not include_stale and ws_date and ws_date < cutoff:
            excluded.append(
                {
                    "source_file": str(workbook),
                    "sheet": ws.title,
                    "reason": "sheet name date before cutoff",
                    "sheet_date": format_dt(ws_date),
                }
            )
            continue
        header_row = likely_header_row(ws, max_scan=8)
        for row in range(1, bounded_max_row(ws) + 1):
            row_values = [ws.cell(row, col).value for col in range(1, ws.max_column + 1)]
            row_text = " ".join(str(value) for value in row_values if value is not None)
            row_norm = norm(row_text)
            row_raw = raw_norm(row_text)
            if account_norm and (account_norm in row_norm or account_raw in row_raw):
                data = row_to_dict(ws, header_row, row) if row > header_row else {"row_text": clean(row_text)}
                update_dates = row_update_dates(data)
                current_update_dates = [item for item in update_dates if parse_dateish(item["date"]) and parse_dateish(item["date"]) >= cutoff]
                if update_dates and not current_update_dates and not include_stale:
                    excluded.append(
                        {
                            "source_file": str(workbook),
                            "sheet": ws.title,
                            "row": row,
                            "reason": "row update/activity date before cutoff",
                            "row_dates": update_dates,
                        }
                    )
                    continue
                matches.append(
                    {
                        "source_file": str(workbook),
                        "sheet": ws.title,
                        "row": row,
                        "source_modified_at": format_dt(source_mtime),
                        "source_freshness_basis": "workbook modified time; verify upstream workbook metadata before using for cell values",
                        "row_text": clean(row_text, 900),
                        "row_update_dates": update_dates,
                        "data": data,
                    }
                )
    return matches[:30]


def summarize_recommendation_leads(records: list[dict[str, Any]], internal_matches: list[dict[str, Any]]) -> dict[str, list[str]]:
    text_chunks = []
    for rec in records + internal_matches:
        for key, value in rec.get("data", {}).items():
            if value is not None:
                text_chunks.append(f"{key}: {value}")
    text = "\n".join(text_chunks).lower()

    leads: dict[str, list[str]] = {}
    if any(token in text for token in ["automation cloud", "acps", "govcloud", "active public sector cloud"]):
        leads.setdefault("Cloud Y/N", []).append("Cloud/public-sector cloud evidence appears in structured sources; confirm current vs target platform before filling.")
    if any(token in text for token in ["on premise", "on-premise", "msi", "automation suite", "studio only"]):
        leads.setdefault("Cloud Y/N", []).append("On-prem/Automation Suite evidence appears in structured sources; do not mark cloud Y unless current platform is cloud.")
    if any(token in text for token in ["using du", "implementing du", "document understanding", "communications mining", "ixp"]):
        leads.setdefault("IXP Status", []).append("DU/IXP evidence appears; classify as Exploring/PoC/PRD based on stage language.")
    if "using du" in text:
        leads.setdefault("Consuming AI Units Today: Y/N", []).append("Active DU usage may support Y, but telemetry should still be verified.")
    if any(token in text for token in ["agentic", "autopilot", "agents"]):
        leads.setdefault("Agentic Status", []).append("Agentic/Autopilot language appears; classify stage from source wording.")
    if any(token in text for token in ["risk/downsell", "customer status: churn", "ischurn: churn", "program has been put on hold", "high risk"]):
        leads.setdefault("At Risk/Churn Forecasted: Y/N", []).append("Risk/churn language appears; check churn forecast/high-risk source first.")
    if any(token in text for token in ["enterprise", "standard", "level of support: high", "level of support: medium", "level of support: low"]):
        leads.setdefault("Bot/License Utilization", []).append("Utilization/support level evidence appears; map conservatively using the field rules.")
    return leads


def to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def render_markdown(result: dict[str, Any]) -> str:
    row = result["target_row"]
    lines = [
        "**Account**",
        f"Row: {row['row']}",
        f"Account: {row['account']}",
        f"Recency cutoff: {result['recency']['cutoff_date']}",
        f"As of: {result['recency']['as_of_date']}",
        "",
        "**Blank / Placeholder Target Fields**",
    ]
    for blank in row["blank_target_fields"]:
        lines.append(f"- {blank['cell']} {blank['header']}")
    if not row["blank_target_fields"]:
        lines.append("- None")

    lines += ["", "**Structured Source Matches**"]
    for rec in result["source_matches"][:40]:
        lines.append(f"- {Path(rec['source_file']).name} / {rec['sheet']} row {rec['row']} matched `{rec['matched_name']}` score {rec['match_score']}")
        if rec.get("source_modified_at"):
            lines.append(f"  freshness: {rec.get('source_modified_at')} ({rec.get('source_freshness_basis')})")
        if rec.get("row_update_dates"):
            lines.append("  row update dates: " + ", ".join(f"{item['field']}={item['date']}" for item in rec["row_update_dates"]))
        useful = []
        for key, value in rec["data"].items():
            if key and value is not None:
                useful.append(f"{key}={clean(value, 140)}")
        if useful:
            lines.append(f"  {', '.join(useful[:8])}")
    if not result["source_matches"]:
        lines.append("- None")

    lines += ["", "**Internal Workbook Tab Matches**"]
    for rec in result["internal_workbook_matches"][:20]:
        row_text = rec.get("row_text")
        if row_text:
            lines.append(f"- {rec['sheet']} row {rec['row']}: {row_text}")
        else:
            lines.append(f"- {rec['sheet']} row {rec['row']}: " + "; ".join(f"{k}={clean(v, 120)}" for k, v in list(rec["data"].items())[:8]))
        if rec.get("source_modified_at"):
            lines.append(f"  freshness: {rec.get('source_modified_at')} ({rec.get('source_freshness_basis')})")
    if not result["internal_workbook_matches"]:
        lines.append("- None")

    lines += ["", "**Recommendation Leads To Investigate**"]
    for header, leads in result["recommendation_leads"].items():
        for lead in leads:
            lines.append(f"- {header}: {lead}")
    if not result["recommendation_leads"]:
        lines.append("- None from structured sources; continue SharePoint/Slack/OneNote searches.")

    lines += ["", "**Missing Source Files**"]
    if result["missing_source_files"]:
        for path in result["missing_source_files"]:
            lines.append(f"- {path}")
    else:
        lines.append("- None")

    lines += ["", "**Excluded As Stale Or Undated**"]
    if result["excluded_as_stale_or_undated"]:
        for item in result["excluded_as_stale_or_undated"][:40]:
            place = Path(item.get("source_file", "")).name
            if item.get("sheet"):
                place += f" / {item['sheet']}"
            if item.get("row"):
                place += f" row {item['row']}"
            lines.append(f"- {place}: {item.get('reason')}")
    else:
        lines.append("- None")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Research one PubSec Big Rocks workbook row against local structured sources.")
    parser.add_argument("--workbook", required=True, help="Path to the Big Rocks workbook")
    parser.add_argument("--sheet", default=MAIN_SHEET, help="Workbook sheet name")
    parser.add_argument("--row", type=int, help="Target worksheet row")
    parser.add_argument("--account", help="Target account name")
    parser.add_argument("--source", action="append", default=[], help="Additional local .xlsx source path; can repeat")
    parser.add_argument("--months", type=int, default=3, help="Calendar-month recency window; default is the past 3 months")
    parser.add_argument("--max-age-days", type=int, help="Optional day-based recency window override")
    parser.add_argument("--as-of-date", help="Run date for cutoff calculation, YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--include-stale", action="store_true", help="Include stale candidates for discovery only; do not use them for cell values")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args()

    as_of = parse_as_of(args.as_of_date)
    cutoff = as_of - timedelta(days=args.max_age_days) if args.max_age_days is not None else subtract_months(as_of, args.months)

    workbook = Path(args.workbook).expanduser()
    if not workbook.exists():
        raise SystemExit(f"Workbook not found: {workbook}")

    target_row = load_main_row(workbook, args.sheet, args.row, args.account)
    account = str(target_row["account"] or args.account or "")

    source_paths = [Path(path).expanduser() for path in DEFAULT_SOURCES + args.source]
    missing = [str(path) for path in source_paths if not path.exists()]
    records = []
    excluded: list[dict[str, Any]] = []
    for path in source_paths:
        records.extend(match_records(path, account, cutoff, excluded, include_stale=args.include_stale))

    internal_matches = scan_workbook_tabs(workbook, account, args.sheet, cutoff, excluded, include_stale=args.include_stale)
    result = {
        "recency": {
            "as_of_date": as_of.date().isoformat(),
            "cutoff_date": cutoff.date().isoformat(),
            "months": args.months,
            "max_age_days": args.max_age_days,
            "note": "Local file modified time is a weak freshness signal; verify upstream SharePoint/SFDC/Slack/Teams/OneNote timestamps before using candidates for cell values.",
        },
        "target_row": target_row,
        "source_matches": records,
        "internal_workbook_matches": internal_matches,
        "recommendation_leads": summarize_recommendation_leads(records, internal_matches),
        "missing_source_files": missing,
        "excluded_as_stale_or_undated": excluded,
    }
    result = to_jsonable(result)

    if args.format == "markdown":
        print(render_markdown(result))
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
