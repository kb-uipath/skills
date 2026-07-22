#!/usr/bin/env python3
"""Strict v1 contracts and deterministic calculations for expansion portfolios."""

from __future__ import annotations

import ipaddress
import json
import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlparse


CONTRACT_VERSION = "1.0"
SCORE_MODEL_VERSION = "1.0"

CRITERIA = (
    "strategic_alignment",
    "inventory_evidence",
    "agentic_suitability",
    "value_potential",
    "feasibility",
    "enterprise_scalability",
    "governance_readiness",
    "time_to_pilot",
)

HIGH_IMPACT_WEIGHTS = {
    "strategic_alignment": 20,
    "inventory_evidence": 20,
    "agentic_suitability": 15,
    "value_potential": 15,
    "feasibility": 10,
    "enterprise_scalability": 10,
    "governance_readiness": 5,
    "time_to_pilot": 5,
}

POC_WEIGHTS = {
    "strategic_alignment": 10,
    "inventory_evidence": 10,
    "agentic_suitability": 15,
    "value_potential": 5,
    "feasibility": 20,
    "enterprise_scalability": 0,
    "governance_readiness": 15,
    "time_to_pilot": 25,
}

DEPLOYMENT_MODELS = {
    "automation_cloud",
    "automation_cloud_public_sector",
    "automation_suite",
    "on_premises",
    "hybrid",
    "unknown",
}

ACTIVE_CATEGORIES = {"scale_now", "validate_next", "pilot_first", "monitor"}
ID_PATTERNS = {
    "ledger_id": re.compile(r"^LEDGER-[A-Z0-9][A-Z0-9._-]*$"),
    "portfolio_id": re.compile(r"^PORTFOLIO-[A-Z0-9][A-Z0-9._-]*$"),
    "inventory_id": re.compile(r"^INV-[A-Z0-9][A-Z0-9._-]*$"),
    "source_id": re.compile(r"^SRC-[A-Z0-9][A-Z0-9._-]*$"),
    "assumption_id": re.compile(r"^ASM-[A-Z0-9][A-Z0-9._-]*$"),
    "opportunity_id": re.compile(r"^OPP-[A-Z0-9][A-Z0-9._-]*$"),
}

PROFILE_CORE_FIELDS = {
    "use_case_name",
    "description",
    "status",
    "department",
    "owner",
    "systems",
    "volume",
    "weekly_volume",
    "annual_volume",
    "handling_time",
    "hours_saved",
    "value",
    "priority",
    "date",
}

EVIDENCE_REF_KEYS = ("inventory_ids", "public_source_ids", "assumption_ids")

PLACEHOLDER_ASSIGNMENTS = {
    "(unassigned)",
    "unassigned",
    "not assigned",
    "to be assigned",
    "tbd",
    "tbc",
    "unknown",
    "none",
    "n/a",
    "na",
}

RESERVED_OFFICIAL_HOSTS = {
    "example.com",
    "example.net",
    "example.org",
}


class ContractLoadError(ValueError):
    """Raised when a contract artifact cannot be loaded safely."""


def load_json_object(path: Path, artifact_name: str) -> dict[str, Any]:
    if not path.exists():
        raise ContractLoadError(f"{artifact_name} does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractLoadError(f"could not read {artifact_name}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractLoadError(f"{artifact_name} must contain a JSON object")
    return value


def version_failure(data: dict[str, Any], artifact_name: str) -> Optional[str]:
    version = data.get("schema_version")
    if version is None:
        return (
            f"{artifact_name}.schema_version is required. Unversioned legacy artifacts are unsafe; "
            "migrate to schema_version '1.0' using references/data_contracts.md."
        )
    if version != CONTRACT_VERSION:
        return (
            f"{artifact_name}.schema_version {version!r} is unsupported; expected "
            f"{CONTRACT_VERSION!r}. Migrate with references/data_contracts.md before retrying."
        )
    return None


def _reject_unknown(value: Any, allowed: Iterable[str], path: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        errors.append(f"{path} has unsupported field(s): {', '.join(unknown)}")


def _required(value: Any, fields: Iterable[str], path: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        return
    missing = [field for field in fields if field not in value]
    if missing:
        errors.append(f"{path} is missing required field(s): {', '.join(missing)}")


def _string(value: Any, path: str, errors: list[str], *, allow_empty: bool = False) -> bool:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        suffix = "a string" if allow_empty else "a non-empty string"
        errors.append(f"{path} must be {suffix}")
        return False
    return True


def _bounded_string(
    value: Any,
    path: str,
    errors: list[str],
    *,
    max_words: int,
) -> bool:
    if not _string(value, path, errors):
        return False
    word_count = len(re.findall(r"\b[\w-]+\b", value))
    if word_count > max_words:
        errors.append(
            f"{path} must contain no more than {max_words} words; found {word_count}"
        )
        return False
    return True


def _is_placeholder_assignment(value: Any) -> bool:
    if not isinstance(value, str):
        return True
    normalized = re.sub(r"\s+", " ", value.strip().casefold())
    return normalized in PLACEHOLDER_ASSIGNMENTS or bool(
        re.search(
            r"\b(?:tbd|tbc|unassigned|unknown|pending assignment|not yet assigned|"
            r"(?:owner|lead|sponsor) (?:needed|to be assigned))\b",
            normalized,
        )
    )


def _public_url_failure(url: str, *, official: bool) -> Optional[str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
        return "must be an absolute public HTTP(S) URL"
    if parsed.username or parsed.password:
        return "must not contain embedded credentials"
    host = parsed.hostname.casefold().rstrip(".")
    if (
        host == "localhost"
        or host.endswith((".localhost", ".local", ".internal", ".invalid"))
    ):
        return "must use a publicly resolvable host"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        return "must not use a private, loopback, link-local, or reserved IP address"
    if official:
        if parsed.scheme != "https":
            return "must use HTTPS when official is true"
        if (
            host in RESERVED_OFFICIAL_HOSTS
            or host in {"test", "example"}
            or host.endswith((".example", ".test"))
        ):
            return "cannot use a reserved test/example host when official is true"
    return None


def _systems_from_profile(value: Any) -> set[str]:
    if not isinstance(value, str) or not value.strip():
        return set()
    return {
        item.strip().casefold()
        for item in re.split(r"[;,|]", value)
        if item.strip()
    }


def _string_list(value: Any, path: str, errors: list[str], *, min_items: int = 0) -> bool:
    if not isinstance(value, list):
        errors.append(f"{path} must be an array")
        return False
    valid = True
    for index, item in enumerate(value):
        if not _string(item, f"{path}[{index}]", errors):
            valid = False
    if len(value) < min_items:
        errors.append(f"{path} must contain at least {min_items} item(s)")
        valid = False
    if all(isinstance(item, str) for item in value) and len(value) != len(set(value)):
        errors.append(f"{path} must not contain duplicates")
        valid = False
    return valid


def _enum(value: Any, allowed: set[str], path: str, errors: list[str]) -> bool:
    if not isinstance(value, str) or value not in allowed:
        errors.append(f"{path} must be one of: {', '.join(sorted(allowed))}")
        return False
    return True


def _number(value: Any, path: str, errors: list[str], *, minimum: float = 0) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        errors.append(f"{path} must be a finite number")
        return False
    if value < minimum:
        errors.append(f"{path} must be at least {minimum}")
        return False
    return True


def _date(value: Any, path: str, errors: list[str]) -> Optional[date]:
    if not _string(value, path, errors):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{path} must use ISO date format YYYY-MM-DD")
        return None


def _id(value: Any, kind: str, path: str, errors: list[str]) -> bool:
    if not _string(value, path, errors):
        return False
    if not ID_PATTERNS[kind].fullmatch(value):
        errors.append(f"{path} must match {ID_PATTERNS[kind].pattern}")
        return False
    return True


def _unique_ids(items: Any, key: str, kind: str, path: str, errors: list[str]) -> set[str]:
    if not isinstance(items, list):
        errors.append(f"{path} must be an array")
        return set()
    ids: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"{path}[{index}] must be an object")
            continue
        item_id = item.get(key)
        if _id(item_id, kind, f"{path}[{index}].{key}", errors):
            ids.append(item_id)
    duplicates = sorted({item_id for item_id in ids if ids.count(item_id) > 1})
    if duplicates:
        errors.append(f"{path} contains duplicate ID(s): {', '.join(duplicates)}")
    return set(ids)


def _validate_evidence_refs(value: Any, path: str, errors: list[str]) -> None:
    allowed = set(EVIDENCE_REF_KEYS)
    _reject_unknown(value, allowed, path, errors)
    _required(value, allowed, path, errors)
    if not isinstance(value, dict):
        return
    for key in EVIDENCE_REF_KEYS:
        _string_list(value.get(key), f"{path}.{key}", errors)


def calculate_weighted_score(criteria_scores: dict[str, Any], weights: dict[str, int]) -> float:
    """Return the documented 0-100 weighted score with stable rounding."""

    return round(sum(float(criteria_scores[key]) * weights[key] for key in CRITERIA) / 5.0, 2)


def score_portfolio(portfolio: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-copied portfolio with deterministic scores and rankings."""

    result = json.loads(json.dumps(portfolio))
    for opportunity in result.get("opportunities", []):
        criteria = opportunity["criteria_scores"]
        opportunity["scores"] = {
            "high_impact": calculate_weighted_score(criteria, HIGH_IMPACT_WEIGHTS),
            "poc": calculate_weighted_score(criteria, POC_WEIGHTS),
        }

    active = [
        opportunity
        for opportunity in result.get("opportunities", [])
        if opportunity.get("category") != "reject"
        and opportunity.get("deployment", {}).get("status") != "incompatible"
    ]
    high_limit = result["ranking_limits"]["high_impact"]
    poc_limit = result["ranking_limits"]["low_friction_poc"]
    high_ranked = sorted(
        active,
        key=lambda item: (-item["scores"]["high_impact"], item["opportunity_id"]),
    )
    poc_ranked = sorted(
        active,
        key=lambda item: (-item["scores"]["poc"], item["opportunity_id"]),
    )
    result["rankings"] = {
        "high_impact": [item["opportunity_id"] for item in high_ranked[:high_limit]],
        "low_friction_poc": [item["opportunity_id"] for item in poc_ranked[:poc_limit]],
    }
    return result


def _validate_inventory_profile(
    profile: dict[str, Any], ledger: dict[str, Any], errors: list[str]
) -> None:
    version = profile.get("schema_version")
    if version not in {"1.0", "1.1"}:
        errors.append(
            "inventory_profile.schema_version must be '1.0' or '1.1'; regenerate it with "
            "scripts/inventory_profiler.py before cross-checking."
        )
        return
    items = profile.get("inventory_items")
    if not isinstance(items, list):
        errors.append(
            "inventory_profile.inventory_items is required; regenerate the legacy profile with "
            "scripts/inventory_profiler.py."
        )
        return
    profile_items: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"inventory_profile.inventory_items[{index}] must be an object")
            continue
        item_id = item.get("inventory_id")
        if not isinstance(item_id, str) or not ID_PATTERNS["inventory_id"].fullmatch(item_id):
            if version == "1.1":
                errors.append(
                    f"inventory_profile.inventory_items[{index}].inventory_id must match "
                    f"{ID_PATTERNS['inventory_id'].pattern}"
                )
            continue
        if item_id in profile_items:
            errors.append(f"inventory_profile.inventory_items has duplicate ID {item_id}")
        profile_items[item_id] = item
    ledger_items = {
        item.get("inventory_id"): item
        for item in ledger.get("inventory_evidence", [])
        if isinstance(item, dict)
    }
    for item_id, ledger_item in ledger_items.items():
        profile_item = profile_items.get(item_id)
        if profile_item is None:
            errors.append(f"inventory profile does not contain ledger inventory ID {item_id}")
            continue
        if profile_item.get("name") != ledger_item.get("name"):
            errors.append(
                f"inventory name mismatch for {item_id}: profile={profile_item.get('name')!r}, "
                f"ledger={ledger_item.get('name')!r}"
            )
        profile_description = str(profile_item.get("description", "")).rstrip(" .")
        ledger_description = str(ledger_item.get("description", "")).rstrip(" .")
        if "description" in profile_item and profile_description != ledger_description:
            errors.append(
                f"inventory description mismatch for {item_id}: "
                f"profile={profile_item.get('description')!r}, "
                f"ledger={ledger_item.get('description')!r}"
            )
        for field in ("status", "department", "owner"):
            if field in profile_item and profile_item.get(field) != ledger_item.get(field):
                errors.append(
                    f"inventory {field} mismatch for {item_id}: "
                    f"profile={profile_item.get(field)!r}, ledger={ledger_item.get(field)!r}"
                )
        profile_systems = _systems_from_profile(profile_item.get("systems"))
        ledger_systems = {
            item.strip().casefold()
            for item in ledger_item.get("systems", [])
            if isinstance(item, str) and item.strip()
        }
        if profile_systems != ledger_systems:
            errors.append(
                f"inventory systems mismatch for {item_id}: "
                f"profile={sorted(profile_systems)!r}, ledger={sorted(ledger_systems)!r}"
            )
        source = ledger_item.get("source", {})
        if profile_item.get("sheet") != source.get("sheet"):
            errors.append(f"inventory source sheet mismatch for {item_id}")
        if profile_item.get("row_number") != source.get("row_number"):
            errors.append(f"inventory source row mismatch for {item_id}")
        profile_metrics = {
            metric.get("name"): metric.get("value")
            for metric in profile_item.get("metrics", [])
            if isinstance(metric, dict) and isinstance(metric.get("name"), str)
        }
        ledger_metrics = {
            metric.get("name"): metric.get("value")
            for metric in ledger_item.get("metrics", [])
            if isinstance(metric, dict) and isinstance(metric.get("name"), str)
        }
        for metric_name, profile_value in profile_metrics.items():
            ledger_value = ledger_metrics.get(metric_name)
            if (
                isinstance(profile_value, (int, float))
                and not isinstance(profile_value, bool)
                and isinstance(ledger_value, (int, float))
                and not isinstance(ledger_value, bool)
                and math.isclose(
                    float(profile_value), float(ledger_value), rel_tol=0, abs_tol=1e-9
                )
            ):
                continue
            errors.append(
                f"inventory metric mismatch for {item_id}.{metric_name}: "
                f"profile={profile_value!r}, ledger={ledger_value!r}"
            )
    metadata = profile.get("metadata")
    if not isinstance(metadata, dict):
        errors.append("inventory_profile.metadata must be an object")
        return
    source_file = metadata.get("source_file")
    source_name = metadata.get("source_name")
    expected_name = ledger.get("inventory_profile", {}).get("source_name")
    actual_name = source_name if isinstance(source_name, str) else (
        Path(source_file).name if isinstance(source_file, str) else None
    )
    if actual_name and expected_name and actual_name != expected_name:
        errors.append(
            f"inventory profile source name {actual_name!r} does not match "
            f"ledger source_name {expected_name!r}"
        )
    if version == "1.1":
        generated_at = metadata.get("generated_at_utc")
        if not isinstance(generated_at, str):
            errors.append(
                "inventory_profile.metadata.generated_at_utc is required for profile 1.1"
            )
        else:
            try:
                parsed_generated = datetime.fromisoformat(
                    generated_at.replace("Z", "+00:00")
                )
                if parsed_generated.utcoffset() is None:
                    raise ValueError
            except ValueError:
                errors.append(
                    "inventory_profile.metadata.generated_at_utc must be ISO-8601"
                )
        source_sha256 = metadata.get("source_sha256")
        source_file = metadata.get("source_file")
        if not isinstance(source_name, str) or not source_name.strip():
            errors.append("inventory_profile.metadata.source_name is required for profile 1.1")
        elif (
            source_name != Path(source_name).name
            or "\\" in source_name
            or re.search(r"[<>:\"|?*`]", source_name)
            or re.search(r"[\x00-\x1f\x7f]", source_name)
        ):
            errors.append(
                "inventory_profile.metadata.source_name must be a display-safe basename"
            )
        if (
            not isinstance(source_file, str)
            or not source_file.strip()
            or source_file != Path(source_file).name
            or "\\" in source_file
            or re.search(r"[<>:\"|?*`]", source_file)
            or re.search(r"[\x00-\x1f\x7f]", source_file)
        ):
            errors.append(
                "inventory_profile.metadata.source_file must be a display-safe basename for profile 1.1"
            )
        elif isinstance(source_name, str) and source_file != source_name:
            errors.append(
                "inventory_profile.metadata.source_file must equal source_name for profile 1.1"
            )
        if not isinstance(source_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
            errors.append(
                "inventory_profile.metadata.source_sha256 must be a lowercase SHA-256 for profile 1.1"
            )
        source_date_summary = metadata.get("source_date_summary")
        source_date_fields = {
            "columns",
            "nonblank_count",
            "valid_count",
            "invalid_count",
            "earliest_date",
            "latest_date",
        }
        if source_date_summary is not None:
            _reject_unknown(
                source_date_summary,
                source_date_fields,
                "inventory_profile.metadata.source_date_summary",
                errors,
            )
            _required(
                source_date_summary,
                source_date_fields,
                "inventory_profile.metadata.source_date_summary",
                errors,
            )
            if isinstance(source_date_summary, dict):
                _string_list(
                    source_date_summary.get("columns"),
                    "inventory_profile.metadata.source_date_summary.columns",
                    errors,
                )
                source_date_counts: dict[str, int] = {}
                for field in ("nonblank_count", "valid_count", "invalid_count"):
                    value = source_date_summary.get(field)
                    if (
                        isinstance(value, bool)
                        or not isinstance(value, int)
                        or not 0 <= value <= len(items)
                    ):
                        errors.append(
                            "inventory_profile.metadata.source_date_summary."
                            f"{field} must be from 0 to total rows"
                        )
                    else:
                        source_date_counts[field] = value
                if (
                    len(source_date_counts) == 3
                    and source_date_counts["nonblank_count"]
                    != source_date_counts["valid_count"]
                    + source_date_counts["invalid_count"]
                ):
                    errors.append(
                        "inventory_profile.metadata.source_date_summary.nonblank_count "
                        "must equal valid_count plus invalid_count"
                    )
                parsed_summary_dates: dict[str, date | None] = {}
                for field in ("earliest_date", "latest_date"):
                    value = source_date_summary.get(field)
                    if value is None:
                        parsed_summary_dates[field] = None
                    else:
                        parsed_summary_dates[field] = _date(
                            value,
                            f"inventory_profile.metadata.source_date_summary.{field}",
                            errors,
                        )
                if source_date_counts.get("valid_count", 0) == 0:
                    if any(value is not None for value in parsed_summary_dates.values()):
                        errors.append(
                            "inventory_profile source date bounds must be null when no valid dates exist"
                        )
                elif any(value is None for value in parsed_summary_dates.values()):
                    errors.append(
                        "inventory_profile source date bounds are required when valid dates exist"
                    )
                elif parsed_summary_dates["earliest_date"] > parsed_summary_dates["latest_date"]:
                    errors.append(
                        "inventory_profile source date earliest_date cannot follow latest_date"
                    )
                latest_date = source_date_summary.get("latest_date")
                ledger_as_of = ledger.get("inventory_profile", {}).get("as_of_date")
                if isinstance(latest_date, str) and ledger_as_of != latest_date:
                    errors.append(
                        "evidence_ledger.inventory_profile.as_of_date must equal the latest "
                        "valid source record date"
                    )
        total_rows = metadata.get("total_rows")
        if isinstance(total_rows, bool) or not isinstance(total_rows, int) or total_rows != len(items):
            errors.append(
                "inventory_profile.metadata.total_rows must equal inventory_items length"
            )
        total_columns = metadata.get("total_columns")
        if (
            isinstance(total_columns, bool)
            or not isinstance(total_columns, int)
            or total_columns < 0
        ):
            errors.append(
                "inventory_profile.metadata.total_columns must be a non-negative integer"
            )
        sheets = profile.get("sheets")
        sheet_names: set[str] = set()
        sheet_columns: dict[str, set[str]] = {}
        if not isinstance(sheets, list):
            errors.append("inventory_profile.sheets must be an array for profile 1.1")
        else:
            sheet_rows = []
            for index, sheet in enumerate(sheets):
                if not isinstance(sheet, dict):
                    errors.append(f"inventory_profile.sheets[{index}] must be an object")
                    continue
                sheet_name = sheet.get("sheet")
                if not isinstance(sheet_name, str) or not sheet_name.strip():
                    errors.append(
                        f"inventory_profile.sheets[{index}].sheet must be a non-empty string"
                    )
                elif sheet_name in sheet_names:
                    errors.append(
                        f"inventory_profile.sheets has duplicate sheet name {sheet_name!r}"
                    )
                else:
                    sheet_names.add(sheet_name)
                rows = sheet.get("rows") if isinstance(sheet, dict) else None
                if isinstance(rows, bool) or not isinstance(rows, int) or rows < 0:
                    errors.append(
                        f"inventory_profile.sheets[{index}].rows must be a non-negative integer"
                    )
                else:
                    sheet_rows.append(rows)
                columns = sheet.get("columns")
                if (
                    not isinstance(columns, list)
                    or any(not isinstance(column, str) or not column.strip() for column in columns)
                    or len(columns) != len(set(columns))
                ):
                    errors.append(
                        f"inventory_profile.sheets[{index}].columns must be an array of unique non-empty strings"
                    )
                else:
                    if isinstance(sheet_name, str) and sheet_name.strip():
                        sheet_columns[sheet_name] = set(columns)
                    if sheet.get("column_count") != len(columns):
                        errors.append(
                            f"inventory_profile.sheets[{index}].column_count must equal columns length"
                        )
            if metadata.get("sheet_count") != len(sheets):
                errors.append(
                    "inventory_profile.metadata.sheet_count must equal sheets length"
                )
            if len(sheet_rows) == len(sheets) and sum(sheet_rows) != len(items):
                errors.append(
                    "inventory_profile sheet row counts must equal inventory_items length"
                )
            if isinstance(total_columns, int) and not isinstance(total_columns, bool):
                union_columns = set().union(*sheet_columns.values()) if sheet_columns else set()
                if total_columns != len(union_columns):
                    errors.append(
                        "inventory_profile.metadata.total_columns must equal unique sheet columns"
                    )

        core_mapping = profile.get("core_field_mapping")
        if not isinstance(core_mapping, dict):
            errors.append(
                "inventory_profile.core_field_mapping must be an object for profile 1.1"
            )
        else:
            missing_fields = sorted(PROFILE_CORE_FIELDS - set(core_mapping))
            if missing_fields:
                errors.append(
                    "inventory_profile.core_field_mapping is missing field(s): "
                    + ", ".join(missing_fields)
                )
            for field, column in core_mapping.items():
                if field in PROFILE_CORE_FIELDS and column is not None and (
                    not isinstance(column, str) or not column.strip()
                ):
                    errors.append(
                        f"inventory_profile.core_field_mapping.{field} must be a string or null"
                    )

        sheet_mappings = profile.get("sheet_field_mappings")
        if not isinstance(sheet_mappings, dict):
            errors.append(
                "inventory_profile.sheet_field_mappings must be an object for profile 1.1"
            )
        else:
            if set(sheet_mappings) != sheet_names:
                errors.append(
                    "inventory_profile.sheet_field_mappings keys must exactly match sheet names"
                )
            for sheet_name, mapping in sheet_mappings.items():
                if not isinstance(mapping, dict):
                    errors.append(
                        f"inventory_profile.sheet_field_mappings.{sheet_name} must be an object"
                    )
                    continue
                missing_fields = sorted(PROFILE_CORE_FIELDS - set(mapping))
                if missing_fields:
                    errors.append(
                        f"inventory_profile.sheet_field_mappings.{sheet_name} is missing field(s): "
                        + ", ".join(missing_fields)
                    )
                for field, column in mapping.items():
                    if field not in PROFILE_CORE_FIELDS or column is None:
                        continue
                    if not isinstance(column, str) or column not in sheet_columns.get(sheet_name, set()):
                        errors.append(
                            f"inventory_profile.sheet_field_mappings.{sheet_name}.{field} "
                            "must reference a column on that sheet or be null"
                        )

        data_quality = profile.get("data_quality")
        field_coverage = (
            data_quality.get("field_coverage") if isinstance(data_quality, dict) else None
        )
        if not isinstance(field_coverage, dict):
            errors.append(
                "inventory_profile.data_quality.field_coverage must be an object for profile 1.1"
            )
        else:
            missing_fields = sorted(PROFILE_CORE_FIELDS - set(field_coverage))
            if missing_fields:
                errors.append(
                    "inventory_profile.data_quality.field_coverage is missing field(s): "
                    + ", ".join(missing_fields)
                )
            for field in PROFILE_CORE_FIELDS:
                details = field_coverage.get(field)
                path = f"inventory_profile.data_quality.field_coverage.{field}"
                if not isinstance(details, dict):
                    if field in field_coverage:
                        errors.append(f"{path} must be an object")
                    continue
                if set(details) != {"column", "nonblank", "coverage_pct"}:
                    errors.append(
                        f"{path} must contain column, nonblank, and coverage_pct"
                    )
                column = details.get("column")
                if column is not None and (not isinstance(column, str) or not column.strip()):
                    errors.append(f"{path}.column must be a string or null")
                nonblank = details.get("nonblank")
                if (
                    isinstance(nonblank, bool)
                    or not isinstance(nonblank, int)
                    or not 0 <= nonblank <= len(items)
                ):
                    errors.append(f"{path}.nonblank must be from 0 to total rows")
                coverage_pct = details.get("coverage_pct")
                if (
                    isinstance(coverage_pct, bool)
                    or not isinstance(coverage_pct, (int, float))
                    or not 0 <= float(coverage_pct) <= 100
                ):
                    errors.append(f"{path}.coverage_pct must be from 0 to 100")
                elif isinstance(nonblank, int) and not isinstance(nonblank, bool):
                    expected_pct = round(
                        (nonblank / len(items) * 100.0) if items else 0.0, 1
                    )
                    if not math.isclose(
                        float(coverage_pct), expected_pct, rel_tol=0, abs_tol=0.05
                    ):
                        errors.append(
                            f"{path}.coverage_pct must match nonblank and total rows"
                        )
                if isinstance(core_mapping, dict) and field in core_mapping:
                    if column != core_mapping.get(field):
                        errors.append(
                            f"{path}.column must match core_field_mapping.{field}"
                        )

        lifecycle_counts = profile.get("status_summary", {}).get("lifecycle_status_counts")
        if not isinstance(lifecycle_counts, dict):
            errors.append(
                "inventory_profile.status_summary.lifecycle_status_counts is required for profile 1.1"
            )
        expected_lifecycle_counts: dict[str, int] = {}
        actual_sheet_rows: dict[str, int] = {}
        normalized_source_dates: list[str] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            if not isinstance(item.get("raw_status"), str):
                errors.append(f"inventory_profile.inventory_items[{index}].raw_status is required")
            if source_date_summary is not None:
                source_date_value = item.get("source_date")
                if source_date_value is not None:
                    parsed_source_date = _date(
                        source_date_value,
                        f"inventory_profile.inventory_items[{index}].source_date",
                        errors,
                    )
                    if parsed_source_date is not None:
                        normalized_source_dates.append(parsed_source_date.isoformat())
            sheet_name = item.get("sheet")
            if not isinstance(sheet_name, str) or sheet_name not in sheet_names:
                errors.append(
                    f"inventory_profile.inventory_items[{index}].sheet must reference a defined sheet"
                )
            else:
                actual_sheet_rows[sheet_name] = actual_sheet_rows.get(sheet_name, 0) + 1
            row_number = item.get("row_number")
            if (
                isinstance(row_number, bool)
                or not isinstance(row_number, int)
                or row_number < 2
            ):
                errors.append(
                    f"inventory_profile.inventory_items[{index}].row_number must be an integer of 2 or greater"
                )
            if item.get("lifecycle_status") not in {
                "deployed",
                "pipeline",
                "paused",
                "retired",
                "cancelled",
                "rejected",
                "duplicate",
                "idea",
                "unknown",
                "other",
            }:
                errors.append(
                    f"inventory_profile.inventory_items[{index}].lifecycle_status is invalid"
                )
            else:
                lifecycle_status = item["lifecycle_status"]
                expected_lifecycle_counts[lifecycle_status] = (
                    expected_lifecycle_counts.get(lifecycle_status, 0) + 1
                )
        if isinstance(lifecycle_counts, dict) and lifecycle_counts != expected_lifecycle_counts:
            errors.append(
                "inventory_profile lifecycle_status_counts must exactly match inventory_items"
            )
        if isinstance(source_date_summary, dict):
            if source_date_summary.get("valid_count") != len(normalized_source_dates):
                errors.append(
                    "inventory_profile source_date_summary.valid_count must match inventory_items"
                )
            if normalized_source_dates:
                if source_date_summary.get("earliest_date") != min(normalized_source_dates):
                    errors.append(
                        "inventory_profile source_date_summary.earliest_date must match inventory_items"
                    )
                if source_date_summary.get("latest_date") != max(normalized_source_dates):
                    errors.append(
                        "inventory_profile source_date_summary.latest_date must match inventory_items"
                    )
        if isinstance(sheets, list):
            for index, sheet in enumerate(sheets):
                if not isinstance(sheet, dict) or not isinstance(sheet.get("sheet"), str):
                    continue
                if sheet.get("rows") != actual_sheet_rows.get(sheet["sheet"], 0):
                    errors.append(
                        f"inventory_profile.sheets[{index}].rows must match inventory item sheet membership"
                    )


def validate_evidence_ledger(
    ledger: dict[str, Any], *, profile: Optional[dict[str, Any]] = None
) -> list[str]:
    errors: list[str] = []
    failure = version_failure(ledger, "evidence_ledger")
    if failure:
        return [failure]

    top_fields = {
        "schema_version",
        "ledger_id",
        "customer",
        "inventory_profile",
        "inventory_evidence",
        "public_sources",
        "assumptions",
    }
    _reject_unknown(ledger, top_fields, "evidence_ledger", errors)
    _required(ledger, top_fields, "evidence_ledger", errors)
    _id(ledger.get("ledger_id"), "ledger_id", "evidence_ledger.ledger_id", errors)

    customer = ledger.get("customer")
    customer_fields = {"name", "sector", "deployment", "entitlements"}
    _reject_unknown(customer, customer_fields, "evidence_ledger.customer", errors)
    _required(customer, customer_fields, "evidence_ledger.customer", errors)
    if isinstance(customer, dict):
        _string(customer.get("name"), "evidence_ledger.customer.name", errors)
        _string(customer.get("sector"), "evidence_ledger.customer.sector", errors)

    deployment = customer.get("deployment") if isinstance(customer, dict) else None
    deployment_fields = {
        "model",
        "constraints",
        "genai_policy",
        "data_classification",
        "human_approval_required",
    }
    _reject_unknown(deployment, deployment_fields, "evidence_ledger.customer.deployment", errors)
    _required(deployment, deployment_fields, "evidence_ledger.customer.deployment", errors)
    if isinstance(deployment, dict):
        _enum(
            deployment.get("model"),
            DEPLOYMENT_MODELS,
            "evidence_ledger.customer.deployment.model",
            errors,
        )
        _string_list(
            deployment.get("constraints"),
            "evidence_ledger.customer.deployment.constraints",
            errors,
        )
        _enum(
            deployment.get("genai_policy"),
            {"allowed", "restricted", "prohibited", "unknown"},
            "evidence_ledger.customer.deployment.genai_policy",
            errors,
        )
        _enum(
            deployment.get("data_classification"),
            {"public", "internal", "confidential", "restricted", "mixed", "unknown"},
            "evidence_ledger.customer.deployment.data_classification",
            errors,
        )
        if not isinstance(deployment.get("human_approval_required"), bool):
            errors.append(
                "evidence_ledger.customer.deployment.human_approval_required must be boolean"
            )

    inventory_profile = ledger.get("inventory_profile")
    profile_fields = {"source_name", "as_of_date", "inventory_ids"}
    _reject_unknown(inventory_profile, profile_fields, "evidence_ledger.inventory_profile", errors)
    _required(inventory_profile, profile_fields, "evidence_ledger.inventory_profile", errors)
    if isinstance(inventory_profile, dict):
        _string(inventory_profile.get("source_name"), "evidence_ledger.inventory_profile.source_name", errors)
        _date(inventory_profile.get("as_of_date"), "evidence_ledger.inventory_profile.as_of_date", errors)
        _string_list(
            inventory_profile.get("inventory_ids"),
            "evidence_ledger.inventory_profile.inventory_ids",
            errors,
            min_items=1,
        )

    inventory = ledger.get("inventory_evidence")
    inventory_ids = _unique_ids(
        inventory, "inventory_id", "inventory_id", "evidence_ledger.inventory_evidence", errors
    )
    inventory_fields = {
        "inventory_id",
        "name",
        "description",
        "status",
        "department",
        "owner",
        "systems",
        "source",
        "facts",
        "metrics",
    }
    if isinstance(inventory, list):
        if not inventory:
            errors.append("evidence_ledger.inventory_evidence must contain at least one item")
        for index, item in enumerate(inventory):
            path = f"evidence_ledger.inventory_evidence[{index}]"
            _reject_unknown(item, inventory_fields, path, errors)
            _required(item, inventory_fields, path, errors)
            if not isinstance(item, dict):
                continue
            for field in ("name", "description", "department"):
                _string(item.get(field), f"{path}.{field}", errors)
            _string(item.get("owner"), f"{path}.owner", errors, allow_empty=True)
            _enum(
                item.get("status"),
                {"production", "pipeline", "idea", "unknown", "other", "excluded"},
                f"{path}.status",
                errors,
            )
            _string_list(item.get("systems"), f"{path}.systems", errors)
            _string_list(item.get("facts"), f"{path}.facts", errors, min_items=1)
            source = item.get("source")
            _reject_unknown(source, {"sheet", "row_number"}, f"{path}.source", errors)
            _required(source, {"sheet", "row_number"}, f"{path}.source", errors)
            if isinstance(source, dict):
                _string(source.get("sheet"), f"{path}.source.sheet", errors)
                row_number = source.get("row_number")
                if isinstance(row_number, bool) or not isinstance(row_number, int) or row_number < 1:
                    errors.append(f"{path}.source.row_number must be a positive integer")
            metrics = item.get("metrics")
            if not isinstance(metrics, list):
                errors.append(f"{path}.metrics must be an array")
            else:
                metric_names: list[str] = []
                for metric_index, metric in enumerate(metrics):
                    metric_path = f"{path}.metrics[{metric_index}]"
                    _reject_unknown(metric, {"name", "value", "unit"}, metric_path, errors)
                    _required(metric, {"name", "value", "unit"}, metric_path, errors)
                    if isinstance(metric, dict):
                        if _string(metric.get("name"), f"{metric_path}.name", errors):
                            metric_names.append(metric["name"])
                        _number(metric.get("value"), f"{metric_path}.value", errors)
                        _string(metric.get("unit"), f"{metric_path}.unit", errors)
                if len(metric_names) != len(set(metric_names)):
                    errors.append(f"{path}.metrics must not repeat metric names")

    declared_inventory_ids = (
        set(inventory_profile.get("inventory_ids", []))
        if isinstance(inventory_profile, dict)
        and isinstance(inventory_profile.get("inventory_ids"), list)
        and all(isinstance(item, str) for item in inventory_profile["inventory_ids"])
        else set()
    )
    if declared_inventory_ids != inventory_ids:
        errors.append(
            "evidence_ledger.inventory_profile.inventory_ids must exactly match inventory_evidence IDs"
        )

    public_sources = ledger.get("public_sources")
    source_ids = _unique_ids(
        public_sources, "source_id", "source_id", "evidence_ledger.public_sources", errors
    )
    source_fields = {
        "source_id",
        "title",
        "publisher",
        "url",
        "published_date",
        "accessed_date",
        "official",
        "evidence_summary",
    }
    if isinstance(public_sources, list):
        if not public_sources:
            errors.append("evidence_ledger.public_sources must contain at least one source")
        for index, source in enumerate(public_sources):
            path = f"evidence_ledger.public_sources[{index}]"
            _reject_unknown(source, source_fields, path, errors)
            _required(source, source_fields, path, errors)
            if not isinstance(source, dict):
                continue
            for field in ("title", "publisher", "evidence_summary"):
                _string(source.get(field), f"{path}.{field}", errors)
            if _string(source.get("url"), f"{path}.url", errors):
                failure = _public_url_failure(
                    source["url"], official=source.get("official") is True
                )
                if failure:
                    errors.append(f"{path}.url {failure}")
            published = _date(source.get("published_date"), f"{path}.published_date", errors)
            accessed = _date(source.get("accessed_date"), f"{path}.accessed_date", errors)
            if published and accessed and published > accessed:
                errors.append(f"{path}.published_date must not be after accessed_date")
            if not isinstance(source.get("official"), bool):
                errors.append(f"{path}.official must be boolean")

    assumptions = ledger.get("assumptions")
    assumption_ids = _unique_ids(
        assumptions, "assumption_id", "assumption_id", "evidence_ledger.assumptions", errors
    )
    assumption_fields = {"assumption_id", "statement", "category", "status", "value", "unit"}
    if isinstance(assumptions, list):
        for index, assumption in enumerate(assumptions):
            path = f"evidence_ledger.assumptions[{index}]"
            _reject_unknown(assumption, assumption_fields, path, errors)
            _required(assumption, {"assumption_id", "statement", "category", "status"}, path, errors)
            if not isinstance(assumption, dict):
                continue
            _string(assumption.get("statement"), f"{path}.statement", errors)
            _enum(
                assumption.get("category"),
                {"value", "deployment", "entitlement", "feasibility", "other"},
                f"{path}.category",
                errors,
            )
            _enum(
                assumption.get("status"),
                {"unvalidated", "validated", "rejected"},
                f"{path}.status",
                errors,
            )
            has_value = "value" in assumption or "unit" in assumption
            if has_value:
                _required(assumption, {"value", "unit"}, path, errors)
                _number(assumption.get("value"), f"{path}.value", errors)
                _string(assumption.get("unit"), f"{path}.unit", errors)

    entitlements = customer.get("entitlements") if isinstance(customer, dict) else None
    if not isinstance(entitlements, list):
        errors.append("evidence_ledger.customer.entitlements must be an array")
    else:
        capabilities: list[str] = []
        known_refs = source_ids | assumption_ids
        assumptions_by_id = {
            item.get("assumption_id"): item
            for item in (assumptions if isinstance(assumptions, list) else [])
            if isinstance(item, dict) and isinstance(item.get("assumption_id"), str)
        }
        for index, entitlement in enumerate(entitlements):
            path = f"evidence_ledger.customer.entitlements[{index}]"
            _reject_unknown(entitlement, {"capability", "status", "evidence_refs"}, path, errors)
            _required(entitlement, {"capability", "status", "evidence_refs"}, path, errors)
            if not isinstance(entitlement, dict):
                continue
            if _string(entitlement.get("capability"), f"{path}.capability", errors):
                capabilities.append(entitlement["capability"].casefold())
            status = entitlement.get("status")
            _enum(status, {"confirmed", "not_entitled", "unknown"}, f"{path}.status", errors)
            refs = entitlement.get("evidence_refs")
            if _string_list(refs, f"{path}.evidence_refs", errors):
                unknown = sorted(set(refs) - known_refs)
                if unknown:
                    errors.append(f"{path}.evidence_refs contains unknown ID(s): {', '.join(unknown)}")
                if status == "confirmed" and not refs:
                    errors.append(f"{path}.evidence_refs is required for confirmed entitlement")
                invalid_assumption_refs = sorted(
                    ref
                    for ref in refs
                    if ref in assumptions_by_id
                    and assumptions_by_id[ref].get("status") != "validated"
                )
                if status == "confirmed" and invalid_assumption_refs:
                    errors.append(
                        f"{path}.evidence_refs uses unvalidated entitlement assumption(s): "
                        + ", ".join(invalid_assumption_refs)
                    )
        if len(capabilities) != len(set(capabilities)):
            errors.append("evidence_ledger.customer.entitlements must not repeat capabilities")

    if profile is not None:
        _validate_inventory_profile(profile, ledger, errors)
    return errors


def _known_evidence(ledger: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    inventory = {
        item["inventory_id"]
        for item in ledger.get("inventory_evidence", [])
        if isinstance(item, dict) and isinstance(item.get("inventory_id"), str)
    }
    sources = {
        item["source_id"]
        for item in ledger.get("public_sources", [])
        if isinstance(item, dict) and isinstance(item.get("source_id"), str)
    }
    assumptions = {
        item["assumption_id"]
        for item in ledger.get("assumptions", [])
        if isinstance(item, dict) and isinstance(item.get("assumption_id"), str)
    }
    return inventory, sources, assumptions


def _validate_value_case(
    opportunity: dict[str, Any], ledger: dict[str, Any], path: str, errors: list[str]
) -> None:
    value_case = opportunity.get("value_case")
    fields = {
        "method",
        "label",
        "basis",
        "formula_id",
        "inputs",
        "annual_hours",
        "annual_value",
        "currency",
    }
    _reject_unknown(value_case, fields, f"{path}.value_case", errors)
    _required(value_case, {"method", "label", "basis"}, f"{path}.value_case", errors)
    if not isinstance(value_case, dict):
        return
    method = value_case.get("method")
    _enum(method, {"qualitative", "calculated"}, f"{path}.value_case.method", errors)
    _enum(
        value_case.get("label"),
        {"low", "medium", "high", "not_sized"},
        f"{path}.value_case.label",
        errors,
    )
    _string(value_case.get("basis"), f"{path}.value_case.basis", errors)
    if method != "calculated":
        unexpected = sorted(
            set(value_case) & {"formula_id", "inputs", "annual_hours", "annual_value", "currency"}
        )
        if unexpected:
            errors.append(
                f"{path}.value_case qualitative method cannot include: {', '.join(unexpected)}"
            )
        return

    _required(
        value_case,
        {"formula_id", "inputs", "annual_hours", "annual_value", "currency"},
        f"{path}.value_case",
        errors,
    )
    formula_id = value_case.get("formula_id")
    _enum(
        formula_id,
        {"volume_minutes_rate_v1", "hours_rate_v1"},
        f"{path}.value_case.formula_id",
        errors,
    )
    _string(value_case.get("currency"), f"{path}.value_case.currency", errors)
    _number(value_case.get("annual_hours"), f"{path}.value_case.annual_hours", errors)
    _number(value_case.get("annual_value"), f"{path}.value_case.annual_value", errors)

    inputs = value_case.get("inputs")
    if not isinstance(inputs, list):
        errors.append(f"{path}.value_case.inputs must be an array")
        return
    input_map: dict[str, dict[str, Any]] = {}
    inventory_ids, _source_ids, assumption_ids = _known_evidence(ledger)
    for index, item in enumerate(inputs):
        item_path = f"{path}.value_case.inputs[{index}]"
        _reject_unknown(item, {"name", "value", "unit", "evidence_ref"}, item_path, errors)
        _required(item, {"name", "value", "unit", "evidence_ref"}, item_path, errors)
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if _string(name, f"{item_path}.name", errors):
            if name in input_map:
                errors.append(f"{path}.value_case.inputs repeats input name {name!r}")
            input_map[name] = item
        _number(item.get("value"), f"{item_path}.value", errors)
        _string(item.get("unit"), f"{item_path}.unit", errors)
        ref = item.get("evidence_ref")
        if _string(ref, f"{item_path}.evidence_ref", errors) and ref not in inventory_ids | assumption_ids:
            errors.append(
                f"{item_path}.evidence_ref must be a known inventory or assumption ID; got {ref!r}"
            )

    required_inputs = {
        "volume_minutes_rate_v1": {"annual_volume", "minutes_saved_per_case", "loaded_hourly_rate"},
        "hours_rate_v1": {"annual_hours", "loaded_hourly_rate"},
    }.get(formula_id) if isinstance(formula_id, str) else None
    if required_inputs is None or set(input_map) != required_inputs:
        if required_inputs is not None:
            errors.append(
                f"{path}.value_case.inputs must exactly contain: {', '.join(sorted(required_inputs))}"
            )
        return

    if not all(
        isinstance(input_map[name].get("value"), (int, float))
        and not isinstance(input_map[name].get("value"), bool)
        and math.isfinite(input_map[name]["value"])
        for name in required_inputs
    ):
        return

    if formula_id == "volume_minutes_rate_v1":
        calculated_hours = round(
            input_map["annual_volume"]["value"]
            * input_map["minutes_saved_per_case"]["value"]
            / 60.0,
            2,
        )
    else:
        calculated_hours = round(input_map["annual_hours"]["value"], 2)
    calculated_value = round(calculated_hours * input_map["loaded_hourly_rate"]["value"], 2)
    if value_case.get("annual_hours") != calculated_hours:
        errors.append(
            f"{path}.value_case.annual_hours must equal deterministic result {calculated_hours}"
        )
    if value_case.get("annual_value") != calculated_value:
        errors.append(
            f"{path}.value_case.annual_value must equal deterministic result {calculated_value}"
        )

    inventory_by_id = {
        item.get("inventory_id"): item
        for item in ledger.get("inventory_evidence", [])
        if isinstance(item, dict)
    }
    assumptions_by_id = {
        item.get("assumption_id"): item
        for item in ledger.get("assumptions", [])
        if isinstance(item, dict)
    }
    for name, item in input_map.items():
        evidence_ref = item.get("evidence_ref")
        if not isinstance(evidence_ref, str):
            continue
        if evidence_ref in inventory_by_id:
            metrics = inventory_by_id[evidence_ref].get("metrics", [])
            matches = [metric for metric in metrics if metric.get("name") == name]
            if (
                not matches
                or matches[0].get("value") != item.get("value")
                or matches[0].get("unit") != item.get("unit")
            ):
                errors.append(
                    f"{path}.value_case input {name!r} does not match metric on {evidence_ref}"
                )
        if evidence_ref in assumptions_by_id:
            assumption = assumptions_by_id[evidence_ref]
            if assumption.get("value") != item.get("value") or assumption.get("unit") != item.get("unit"):
                errors.append(
                    f"{path}.value_case input {name!r} does not match assumption {evidence_ref}"
                )
        refs = opportunity.get("evidence_refs", {})
        if not isinstance(refs, dict):
            refs = {}
        allowed_input_refs = {
            ref
            for key in ("inventory_ids", "assumption_ids")
            for ref in (refs.get(key, []) if isinstance(refs.get(key), list) else [])
            if isinstance(ref, str)
        }
        if evidence_ref not in allowed_input_refs:
            errors.append(
                f"{path}.value_case input {name!r} evidence_ref must also appear in opportunity evidence_refs"
            )

    unvalidated_inputs = sorted(
        item.get("evidence_ref")
        for item in input_map.values()
        if isinstance(item.get("evidence_ref"), str)
        and item.get("evidence_ref") in assumptions_by_id
        and assumptions_by_id[item["evidence_ref"]].get("status") == "unvalidated"
    )
    basis = value_case.get("basis")
    if unvalidated_inputs and (
        not isinstance(basis, str) or "validation required" not in basis.casefold()
    ):
        errors.append(
            f"{path}.value_case.basis must say 'validation required' for unvalidated input(s): "
            + ", ".join(unvalidated_inputs)
        )


def validate_portfolio(
    portfolio: dict[str, Any],
    ledger: dict[str, Any],
    *,
    profile: Optional[dict[str, Any]] = None,
    require_derived: bool = True,
) -> list[str]:
    errors = validate_evidence_ledger(ledger, profile=profile)
    if errors:
        return errors
    failure = version_failure(portfolio, "portfolio")
    if failure:
        return [failure]

    fields = {
        "schema_version",
        "portfolio_id",
        "customer_name",
        "ledger_id",
        "as_of_date",
        "score_model_version",
        "ranking_limits",
        "opportunities",
        "rankings",
    }
    required = fields if require_derived else fields - {"rankings"}
    _reject_unknown(portfolio, fields, "portfolio", errors)
    _required(portfolio, required, "portfolio", errors)
    _id(portfolio.get("portfolio_id"), "portfolio_id", "portfolio.portfolio_id", errors)
    _string(portfolio.get("customer_name"), "portfolio.customer_name", errors)
    _id(portfolio.get("ledger_id"), "ledger_id", "portfolio.ledger_id", errors)
    as_of = _date(portfolio.get("as_of_date"), "portfolio.as_of_date", errors)
    if portfolio.get("score_model_version") != SCORE_MODEL_VERSION:
        errors.append(
            f"portfolio.score_model_version must be {SCORE_MODEL_VERSION!r}; rerun score_portfolio.py"
        )
    customer = ledger.get("customer", {})
    if portfolio.get("customer_name") != customer.get("name"):
        errors.append("portfolio.customer_name must exactly match evidence_ledger.customer.name")
    if portfolio.get("ledger_id") != ledger.get("ledger_id"):
        errors.append("portfolio.ledger_id must exactly match evidence_ledger.ledger_id")

    limits = portfolio.get("ranking_limits")
    _reject_unknown(limits, {"high_impact", "low_friction_poc"}, "portfolio.ranking_limits", errors)
    _required(limits, {"high_impact", "low_friction_poc"}, "portfolio.ranking_limits", errors)
    if isinstance(limits, dict):
        for key in ("high_impact", "low_friction_poc"):
            limit = limits.get(key)
            if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
                errors.append(f"portfolio.ranking_limits.{key} must be a positive integer")

    inventory_ids, source_ids, assumption_ids = _known_evidence(ledger)
    inventory_by_id = {
        item.get("inventory_id"): item
        for item in ledger.get("inventory_evidence", [])
        if isinstance(item, dict)
    }
    assumptions_by_id = {
        item.get("assumption_id"): item
        for item in ledger.get("assumptions", [])
        if isinstance(item, dict)
    }
    entitlement_by_capability = {
        item.get("capability", "").casefold(): item
        for item in customer.get("entitlements", [])
        if isinstance(item, dict)
    }
    deployment = customer.get("deployment", {})
    constraints = set(deployment.get("constraints", []))
    active_addressed_constraints: set[str] = set()
    active_opportunity_count = 0

    opportunities = portfolio.get("opportunities")
    opportunity_ids = _unique_ids(
        opportunities, "opportunity_id", "opportunity_id", "portfolio.opportunities", errors
    )
    opportunity_fields = {
        "opportunity_id",
        "name",
        "category",
        "confidence",
        "why_now",
        "decision_ask",
        "business_problem",
        "agentic_enhancement",
        "evidence_refs",
        "criteria_scores",
        "scores",
        "capability_fit",
        "deployment",
        "value_case",
        "value_levers",
        "feasibility",
        "governance",
        "validation_questions",
        "pilot",
    }
    required_opportunity_fields = opportunity_fields if require_derived else opportunity_fields - {"scores"}
    if isinstance(opportunities, list):
        if not opportunities:
            errors.append("portfolio.opportunities must contain at least one opportunity")
        names: list[str] = []
        for index, opportunity in enumerate(opportunities):
            path = f"portfolio.opportunities[{index}]"
            _reject_unknown(opportunity, opportunity_fields, path, errors)
            _required(opportunity, required_opportunity_fields, path, errors)
            if not isinstance(opportunity, dict):
                continue
            if _string(opportunity.get("name"), f"{path}.name", errors):
                names.append(opportunity["name"].casefold())
            for field in (
                "why_now",
                "decision_ask",
                "business_problem",
                "agentic_enhancement",
                "feasibility",
                "governance",
            ):
                max_words = {
                    "why_now": 60,
                    "decision_ask": 45,
                    "business_problem": 80,
                    "agentic_enhancement": 90,
                    "feasibility": 60,
                    "governance": 60,
                }[field]
                _bounded_string(
                    opportunity.get(field),
                    f"{path}.{field}",
                    errors,
                    max_words=max_words,
                )
            category = opportunity.get("category")
            category_is_active = isinstance(category, str) and category in ACTIVE_CATEGORIES
            if category_is_active:
                active_opportunity_count += 1
            _enum(
                category,
                ACTIVE_CATEGORIES | {"reject"},
                f"{path}.category",
                errors,
            )
            _enum(
                opportunity.get("confidence"),
                {"high", "medium", "low"},
                f"{path}.confidence",
                errors,
            )
            _string_list(opportunity.get("value_levers"), f"{path}.value_levers", errors, min_items=1)
            _string_list(
                opportunity.get("validation_questions"),
                f"{path}.validation_questions",
                errors,
                min_items=2,
            )

            refs = opportunity.get("evidence_refs")
            _validate_evidence_refs(refs, f"{path}.evidence_refs", errors)
            refs_are_safe = isinstance(refs, dict) and all(
                isinstance(refs.get(key), list)
                and all(isinstance(item, str) for item in refs[key])
                for key in EVIDENCE_REF_KEYS
            )
            if refs_are_safe:
                unknown_inventory = sorted(set(refs.get("inventory_ids", [])) - inventory_ids)
                unknown_sources = sorted(set(refs.get("public_source_ids", [])) - source_ids)
                unknown_assumptions = sorted(set(refs.get("assumption_ids", [])) - assumption_ids)
                for label, unknown in (
                    ("inventory", unknown_inventory),
                    ("public source", unknown_sources),
                    ("assumption", unknown_assumptions),
                ):
                    if unknown:
                        errors.append(
                            f"{path}.evidence_refs contains unknown {label} ID(s): {', '.join(unknown)}"
                        )
                if category_is_active:
                    if not refs.get("inventory_ids"):
                        errors.append(f"{path} must reference inventory evidence")
                    if not refs.get("public_source_ids"):
                        errors.append(f"{path} must reference public strategy evidence")
                excluded = sorted(
                    item_id
                    for item_id in refs.get("inventory_ids", [])
                    if inventory_by_id.get(item_id, {}).get("status") == "excluded"
                )
                if excluded and category != "reject":
                    errors.append(
                        f"{path} cannot use excluded inventory as recommendation evidence: "
                        + ", ".join(excluded)
                    )
                rejected_assumptions = sorted(
                    item_id
                    for item_id in refs.get("assumption_ids", [])
                    if assumptions_by_id.get(item_id, {}).get("status") == "rejected"
                )
                if rejected_assumptions:
                    errors.append(
                        f"{path} references rejected assumption ID(s): {', '.join(rejected_assumptions)}"
                    )

            criteria_scores = opportunity.get("criteria_scores")
            _reject_unknown(criteria_scores, set(CRITERIA), f"{path}.criteria_scores", errors)
            _required(criteria_scores, set(CRITERIA), f"{path}.criteria_scores", errors)
            if isinstance(criteria_scores, dict):
                for criterion in CRITERIA:
                    score = criteria_scores.get(criterion)
                    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 5:
                        errors.append(f"{path}.criteria_scores.{criterion} must be an integer from 0 to 5")

            scores = opportunity.get("scores")
            if require_derived:
                _reject_unknown(scores, {"high_impact", "poc"}, f"{path}.scores", errors)
                _required(scores, {"high_impact", "poc"}, f"{path}.scores", errors)
                if isinstance(scores, dict) and isinstance(criteria_scores, dict) and all(
                    isinstance(criteria_scores.get(key), int) for key in CRITERIA
                ):
                    expected_high = calculate_weighted_score(criteria_scores, HIGH_IMPACT_WEIGHTS)
                    expected_poc = calculate_weighted_score(criteria_scores, POC_WEIGHTS)
                    if scores.get("high_impact") != expected_high:
                        errors.append(f"{path}.scores.high_impact must equal {expected_high}")
                    if scores.get("poc") != expected_poc:
                        errors.append(f"{path}.scores.poc must equal {expected_poc}")

            capability_fit = opportunity.get("capability_fit")
            if not isinstance(capability_fit, list) or not capability_fit:
                errors.append(f"{path}.capability_fit must contain at least one item")
            else:
                capabilities: list[str] = []
                for capability_index, fit in enumerate(capability_fit):
                    fit_path = f"{path}.capability_fit[{capability_index}]"
                    _reject_unknown(
                        fit,
                        {"capability", "claim", "entitlement_evidence_refs"},
                        fit_path,
                        errors,
                    )
                    _required(
                        fit,
                        {"capability", "claim", "entitlement_evidence_refs"},
                        fit_path,
                        errors,
                    )
                    if not isinstance(fit, dict):
                        continue
                    capability = fit.get("capability")
                    if _string(capability, f"{fit_path}.capability", errors):
                        capabilities.append(capability.casefold())
                    claim = fit.get("claim")
                    _enum(
                        claim,
                        {"likely_fit", "confirmed_entitlement"},
                        f"{fit_path}.claim",
                        errors,
                    )
                    fit_refs = fit.get("entitlement_evidence_refs")
                    if _string_list(fit_refs, f"{fit_path}.entitlement_evidence_refs", errors):
                        entitlement = entitlement_by_capability.get(str(capability).casefold())
                        if claim == "confirmed_entitlement":
                            if entitlement is None or entitlement.get("status") != "confirmed":
                                errors.append(
                                    f"{fit_path} claims confirmed entitlement without confirmed ledger evidence"
                                )
                            elif not fit_refs or not set(fit_refs).issubset(
                                set(entitlement.get("evidence_refs", []))
                            ):
                                errors.append(
                                    f"{fit_path}.entitlement_evidence_refs must cite confirmed ledger evidence"
                                )
                        elif fit_refs:
                            errors.append(
                                f"{fit_path}.entitlement_evidence_refs must be empty for likely_fit claims"
                            )
                if len(capabilities) != len(set(capabilities)):
                    errors.append(f"{path}.capability_fit must not repeat capabilities")

            opportunity_deployment = opportunity.get("deployment")
            deployment_fields = {"status", "constraints_addressed", "controls", "notes"}
            _reject_unknown(opportunity_deployment, deployment_fields, f"{path}.deployment", errors)
            _required(opportunity_deployment, deployment_fields, f"{path}.deployment", errors)
            if isinstance(opportunity_deployment, dict):
                deployment_status = opportunity_deployment.get("status")
                _enum(
                    deployment_status,
                    {"compatible", "requires_validation", "incompatible"},
                    f"{path}.deployment.status",
                    errors,
                )
                addressed = opportunity_deployment.get("constraints_addressed")
                _string_list(addressed, f"{path}.deployment.constraints_addressed", errors)
                _string_list(opportunity_deployment.get("controls"), f"{path}.deployment.controls", errors)
                _string(opportunity_deployment.get("notes"), f"{path}.deployment.notes", errors)
                if isinstance(addressed, list) and all(
                    isinstance(item, str) for item in addressed
                ):
                    unknown_constraints = sorted(set(addressed) - constraints)
                    if unknown_constraints:
                        errors.append(
                            f"{path}.deployment.constraints_addressed contains unknown constraint(s): "
                            + ", ".join(unknown_constraints)
                        )
                    if category_is_active and constraints and not addressed:
                        errors.append(
                            f"{path}.deployment.constraints_addressed must include each constraint "
                            "that materially applies to this opportunity"
                        )
                    if category_is_active:
                        active_addressed_constraints.update(set(addressed) & constraints)
                controls = opportunity_deployment.get("controls", [])
                if deployment.get("human_approval_required") and category_is_active:
                    if not isinstance(controls, list) or not any(
                        isinstance(item, str)
                        and re.search(r"\b(human|approval|review)\b", item, re.I)
                        for item in controls
                    ):
                        errors.append(f"{path}.deployment.controls must preserve required human approval")
                if deployment.get("genai_policy") == "prohibited" and deployment_status != "incompatible":
                    errors.append(f"{path}.deployment.status must be incompatible when GenAI is prohibited")

            _validate_value_case(opportunity, ledger, path, errors)

            pilot = opportunity.get("pilot")
            pilot_fields = {
                "objective",
                "narrow_scope",
                "owner",
                "agent_role",
                "human_role",
                "success_metrics",
                "data_needed",
                "exit_criteria",
                "first_step",
                "timeline_days",
            }
            _reject_unknown(pilot, pilot_fields, f"{path}.pilot", errors)
            _required(pilot, pilot_fields, f"{path}.pilot", errors)
            if isinstance(pilot, dict):
                for field in (
                    "objective",
                    "narrow_scope",
                    "owner",
                    "agent_role",
                    "human_role",
                    "first_step",
                ):
                    _bounded_string(
                        pilot.get(field),
                        f"{path}.pilot.{field}",
                        errors,
                        max_words=50,
                    )
                if category_is_active and _is_placeholder_assignment(pilot.get("owner")):
                    errors.append(
                        f"{path}.pilot.owner must name an accountable role or person; "
                        "placeholder assignments such as 'unassigned' or 'TBD' are not actionable"
                    )
                _string_list(
                    pilot.get("success_metrics"),
                    f"{path}.pilot.success_metrics",
                    errors,
                    min_items=2,
                )
                _string_list(pilot.get("data_needed"), f"{path}.pilot.data_needed", errors, min_items=1)
                _string_list(pilot.get("exit_criteria"), f"{path}.pilot.exit_criteria", errors, min_items=1)
                timeline = pilot.get("timeline_days")
                if isinstance(timeline, bool) or not isinstance(timeline, int) or not 1 <= timeline <= 180:
                    errors.append(f"{path}.pilot.timeline_days must be an integer from 1 to 180")
        if len(names) != len(set(names)):
            errors.append("portfolio.opportunities must not repeat opportunity names")
        if active_opportunity_count and constraints:
            missing_constraints = sorted(constraints - active_addressed_constraints)
            if missing_constraints:
                errors.append(
                    "active portfolio opportunities must collectively cover every ledger constraint; "
                    "missing: " + ", ".join(missing_constraints)
                )

    if as_of:
        for index, source in enumerate(ledger.get("public_sources", [])):
            if not isinstance(source, dict):
                continue
            accessed = _date(source.get("accessed_date"), f"evidence_ledger.public_sources[{index}].accessed_date", [])
            if accessed and accessed > as_of:
                errors.append(
                    f"evidence_ledger.public_sources[{index}].accessed_date is after portfolio.as_of_date"
                )

    valid_limits = isinstance(limits, dict) and all(
        isinstance(limits.get(key), int)
        and not isinstance(limits.get(key), bool)
        and limits[key] > 0
        for key in ("high_impact", "low_friction_poc")
    )
    if require_derived and valid_limits and opportunity_ids and not errors:
        expected = score_portfolio(portfolio).get("rankings")
        rankings = portfolio.get("rankings")
        _reject_unknown(rankings, {"high_impact", "low_friction_poc"}, "portfolio.rankings", errors)
        _required(rankings, {"high_impact", "low_friction_poc"}, "portfolio.rankings", errors)
        if isinstance(rankings, dict):
            for key in ("high_impact", "low_friction_poc"):
                ranked_ids = rankings.get(key)
                ranked_ids_are_safe = _string_list(
                    ranked_ids, f"portfolio.rankings.{key}", errors, min_items=1
                )
                unknown = (
                    sorted(set(ranked_ids) - opportunity_ids)
                    if ranked_ids_are_safe
                    else []
                )
                if unknown:
                    errors.append(f"portfolio.rankings.{key} has unknown ID(s): {', '.join(unknown)}")
                if expected and rankings.get(key) != expected.get(key):
                    errors.append(
                        f"portfolio.rankings.{key} is stale; expected deterministic order "
                        f"{expected.get(key)}"
                    )
    return errors


def evaluate_outcome_rubric(
    portfolio: dict[str, Any], ledger: dict[str, Any]
) -> dict[str, Any]:
    """Evaluate deterministic outcome signals without replacing contract validation."""

    inventory_by_id = {
        item.get("inventory_id"): item
        for item in ledger.get("inventory_evidence", [])
        if isinstance(item, dict)
    }
    source_by_id = {
        item.get("source_id"): item
        for item in ledger.get("public_sources", [])
        if isinstance(item, dict)
    }
    assumption_by_id = {
        item.get("assumption_id"): item
        for item in ledger.get("assumptions", [])
        if isinstance(item, dict)
    }
    rows: list[dict[str, Any]] = []
    for opportunity in portfolio.get("opportunities", []):
        refs = opportunity.get("evidence_refs", {})
        referenced_inventory = [
            inventory_by_id[item_id]
            for item_id in refs.get("inventory_ids", [])
            if item_id in inventory_by_id
        ]
        referenced_sources = [
            source_by_id[item_id]
            for item_id in refs.get("public_source_ids", [])
            if item_id in source_by_id
        ]
        referenced_assumptions = [
            assumption_by_id[item_id]
            for item_id in refs.get("assumption_ids", [])
            if item_id in assumption_by_id
        ]
        specificity_checks = {
            "named_workflow": len(opportunity.get("name", "").split()) >= 2,
            "concrete_problem": len(opportunity.get("business_problem", "").split()) >= 10,
            "multiple_inventory_signals": len(referenced_inventory) >= 2,
            "public_strategy_signal": bool(refs.get("public_source_ids")),
            "department_context": any(item.get("department") for item in referenced_inventory),
            "system_context": any(item.get("systems") for item in referenced_inventory),
            "quantified_inventory_signal": any(
                item.get("metrics") for item in referenced_inventory
            ),
            "official_public_evidence": any(
                item.get("official") is True for item in referenced_sources
            ),
        }
        decision_checks = {
            "explicit_decision_ask": len(opportunity.get("decision_ask", "").split()) >= 6,
            "category_and_confidence": bool(opportunity.get("category") and opportunity.get("confidence")),
            "deterministic_scores": set(opportunity.get("scores", {})) == {"high_impact", "poc"},
            "score_tradeoffs": len(set(opportunity.get("criteria_scores", {}).values())) >= 2,
            "value_basis": bool(opportunity.get("value_case", {}).get("basis")),
            "validation_questions": len(opportunity.get("validation_questions", [])) >= 2,
            "deployment_disposition": bool(opportunity.get("deployment", {}).get("status")),
            "validated_assumptions": not any(
                item.get("status") == "unvalidated" for item in referenced_assumptions
            ),
        }
        pilot = opportunity.get("pilot", {})
        pilot_checks = {
            "objective": bool(pilot.get("objective")),
            "narrow_scope": bool(pilot.get("narrow_scope")),
            "agent_role": bool(pilot.get("agent_role")),
            "human_role": bool(pilot.get("human_role")),
            "accountable_owner": not _is_placeholder_assignment(pilot.get("owner")),
            "measures": len(pilot.get("success_metrics", [])) >= 2,
            "data_needed": bool(pilot.get("data_needed")),
            "exit_criteria": bool(pilot.get("exit_criteria")),
            "first_step": bool(pilot.get("first_step")),
            "bounded_timeline": isinstance(pilot.get("timeline_days"), int)
            and 1 <= pilot["timeline_days"] <= 90,
        }

        def percentage(checks: dict[str, bool]) -> float:
            return round(sum(checks.values()) / len(checks) * 100.0, 2)

        rows.append(
            {
                "opportunity_id": opportunity.get("opportunity_id"),
                "specificity": percentage(specificity_checks),
                "decision_utility": percentage(decision_checks),
                "pilot_actionability": percentage(pilot_checks),
                "checks": {
                    "specificity": specificity_checks,
                    "decision_utility": decision_checks,
                    "pilot_actionability": pilot_checks,
                },
            }
        )

    def average(key: str) -> float:
        if not rows:
            return 0.0
        return round(sum(row[key] for row in rows) / len(rows), 2)

    return {
        "rubric_version": "1.2",
        "portfolio_id": portfolio.get("portfolio_id"),
        "specificity": average("specificity"),
        "decision_utility": average("decision_utility"),
        "pilot_actionability": average("pilot_actionability"),
        "opportunities": rows,
    }


def format_score(value: Any) -> str:
    if isinstance(value, (int, float)) and float(value).is_integer():
        return str(int(value))
    if isinstance(value, (int, float)):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)
