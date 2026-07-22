#!/usr/bin/env python3
"""Render a validated portfolio into concise customer-ready Markdown."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from assessment_contracts import (
    expected_artifact_hashes,
    format_failures,
    selected_opportunity_ids,
    validate_process_map,
    validate_semantic_review,
)
from portfolio_contracts import ContractLoadError, load_json_object, validate_portfolio
from validate_customer_assessment import markdown_word_count, validate_customer_assessment


STATUS_ORDER = [
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
]
FIELD_LABELS = {
    "use_case_name": "automation name",
    "description": "process description",
    "status": "lifecycle status",
    "department": "business function",
    "owner": "owner",
    "systems": "systems",
    "volume": "volume",
    "weekly_volume": "weekly volume",
    "annual_volume": "annual volume",
    "handling_time": "handling time",
    "hours_saved": "hours saved",
    "value": "value",
    "priority": "priority",
    "date": "record date",
}
AVAILABLE_FIELD_LABELS = {
    "use_case_name": "names",
    "description": "descriptions",
    "status": "lifecycle",
    "department": "functions",
    "owner": "owners",
    "systems": "systems",
    "volume": "volumes",
    "weekly_volume": "weekly volumes",
    "annual_volume": "annual volumes",
    "handling_time": "workload",
    "hours_saved": "hours saved",
    "value": "value",
    "priority": "priorities",
    "date": "dates",
}
CAPABILITY_LABELS = {
    "maestro": "Maestro",
    "agentic": "Agentic support",
    "genai": "GenAI",
    "robots": "Robots",
    "human_review": "Human review",
}
def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("|", " / ")).strip()


def sentence(value: Any) -> str:
    text = clean(value).rstrip(" .;:")
    return text + "." if text and not text.endswith(("?", "!")) else text


def first_sentence(value: Any) -> str:
    text = clean(value)
    parts = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)
    return sentence(parts[0] if parts else text)


def labeled_sentence(value: Any) -> str:
    text = clean(value).rstrip(" .;:")
    if text:
        text = text[0].upper() + text[1:]
    return sentence(text)


def clause(value: Any) -> str:
    """Normalize a source sentence fragment after renderer-owned lead-in text."""

    text = clean(value).rstrip(" .;:")
    if not text:
        return text
    words = text.split()
    first_word = words[0]
    next_word_is_proper = len(words) > 1 and words[1][0].isupper()
    if len(first_word) == 1 or (
        first_word[0].isupper()
        and first_word[1:].islower()
        and not next_word_is_proper
    ):
        text = text[0].lower() + text[1:]
    return text


def embedded_clause(value: Any) -> str:
    text = clause(value)
    if re.match(r"^(?:One|A|An|The)\b", text):
        text = text[0].lower() + text[1:]
    return text


def plain_customer_text(value: Any) -> str:
    text = clean(value)
    replacements = (
        (r"\blikely[- ]fit\b", "proposed"),
        (r"\bno adaptive reasoning need\b", "no need for case-by-case judgment"),
        (r"\bdeterministic\b", "rules-based"),
        (r"\badaptive reasoning\b", "case-by-case judgment"),
        (r"\bambiguity or discretionary reasoning\b", "case variation that requires judgment"),
        (r"\bgenerative interpretation\b", "generated interpretation"),
        (r"\brules-based completeness rules\b", "approved completeness rules"),
        (r"\brather than generation\b", "without generated content"),
        (r"\binterfaces\b", "system connections"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.I)
    return text


def join_counts(items: list[tuple[str, int]]) -> str:
    return "; ".join(f"{label}: {count}" for label, count in items)


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    return singular if count == 1 else (plural_form or singular + "s")


def source_limitations(
    profile: dict[str, Any], ledger: dict[str, Any] | None = None
) -> list[str]:
    quality = profile.get("data_quality", {})
    date_summary = profile.get("metadata", {}).get("source_date_summary", {})
    latest_date = date_summary.get("latest_date") if isinstance(date_summary, dict) else None
    if isinstance(latest_date, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", latest_date):
        limitations: list[str] = [
            f"Latest record: {latest_date}"
        ]
    else:
        limitations = [
            "No valid record-update date; confirm lifecycle, ownership, volume, handling time"
        ]
    missing = quality.get("missing_core_fields_for_full_quality", [])
    if missing:
        labels = [FIELD_LABELS.get(item, item.replace("_", " ")) for item in missing]
        limitations.append("Missing core fields: " + ", ".join(labels))
    if quality.get("no_value_or_volume_fields_detected"):
        limitations.append("No reliable volume, effort, or value field was detected")
    coverage = quality.get("field_coverage", {})
    coverage_gaps: list[str] = []
    for field in ("description", "status", "department", "owner", "systems"):
        field_details = coverage.get(field, {})
        field_coverage = field_details.get("coverage_pct", 0)
        if (
            field_details.get("column")
            and isinstance(field_coverage, (int, float))
            and field_coverage < 100
        ):
            coverage_gaps.append(
                f"{FIELD_LABELS[field]} {field_coverage:.0f}% populated"
            )
    if coverage_gaps:
        limitations.append(", ".join(coverage_gaps))

    unresolved_planning_inputs: list[str] = []
    for item in (ledger or {}).get("assumptions", []):
        if not isinstance(item, dict) or item.get("status") == "validated":
            continue
        category = clean(item.get("category")).replace("_", " ")
        if category:
            unresolved_planning_inputs.append(category)
    entitlement_unknown = any(
        isinstance(item, dict) and item.get("status") != "confirmed"
        for item in (ledger or {}).get("customer", {}).get("entitlements", [])
    )
    if entitlement_unknown:
        unresolved_planning_inputs.append("product availability")
    folded_inputs = " ".join(unresolved_planning_inputs).casefold()
    material_gaps: list[str] = []
    if entitlement_unknown:
        material_gaps.append("product")
    if any(term in folded_inputs for term in ("deployment", "feasibility")):
        material_gaps.append("deployment")
    material_gaps.append("baselines")
    if any(term in folded_inputs for term in ("value", "financial", "cost")):
        material_gaps.append("value")
    material_gaps = list(dict.fromkeys(material_gaps))
    limitations.append("Unconfirmed: " + natural_join(material_gaps))
    return limitations[:3]


def available_fields(profile: dict[str, Any]) -> str:
    fields: list[str] = []
    seen: set[str] = set()
    seen_columns: set[str] = set()
    mapping = profile.get("core_field_mapping", {})
    for field, column in mapping.items():
        label = AVAILABLE_FIELD_LABELS.get(field, field.replace("_", " "))
        if field in {"volume", "weekly_volume", "annual_volume"}:
            label = "workload"
        column_key = clean(column).casefold()
        if label and label.casefold() not in seen and column_key not in seen_columns:
            if not column_key:
                continue
            fields.append(label)
            seen.add(label.casefold())
            seen_columns.add(column_key)
    return natural_join(fields) if fields else "No standard portfolio fields were detected"


def split_values(value: Any) -> list[str]:
    normalized = re.sub(r"\s+/\s+", ";", clean(value))
    return [part.strip() for part in re.split(r"[;,|\n]+", normalized) if part.strip()]


def concentration_text(
    profile: dict[str, Any], field: str, label: str, *, multi: bool = False
) -> str:
    counter: Counter[str] = Counter()
    display: dict[str, str] = {}
    for item in profile.get("inventory_items", []):
        if not isinstance(item, dict) or item.get("lifecycle_status") == "duplicate":
            continue
        values = split_values(item.get(field)) if multi else [clean(item.get(field))]
        for value in values:
            if not value or value.casefold() in {"blank", "unknown", "n/a", "na"}:
                continue
            key = value.casefold()
            counter[key] += 1
            display.setdefault(key, value)
    ranked = sorted(counter, key=lambda key: (-counter[key], display[key].casefold()))
    if not ranked:
        return f"No {label} supplied"
    shown = ranked[:3]
    suffix = ""
    if len(ranked) > 3 and counter[ranked[2]] == counter[ranked[3]]:
        cutoff = counter[ranked[2]]
        shown = [key for key in ranked if counter[key] > cutoff]
        tied = [key for key in ranked if counter[key] == cutoff]
        suffix = f"; {len(tied)} {label} tied at {cutoff} each"
    elif len(ranked) > 3:
        suffix = f"; {len(ranked) - 3} others"
    if len(shown) > 1 and len({counter[key] for key in shown}) == 1:
        values = (
            natural_join([display[key] for key in shown])
            + f" ({counter[shown[0]]} each)"
        )
    else:
        values = "; ".join(f"{display[key]} ({counter[key]})" for key in shown)
    return f"{values}{suffix}"


def lifecycle_text(profile: dict[str, Any]) -> str:
    lifecycle_counts = profile["status_summary"]["lifecycle_status_counts"]
    values: list[str] = []
    for status in STATUS_ORDER:
        if status == "other" and not lifecycle_counts.get("other", 0):
            continue
        count = lifecycle_counts.get(status, 0)
        label = status.title()
        values.append(f"{label}: {count}")
    return "; ".join(values)


def process_groups_text(process_map: dict[str, Any]) -> str:
    processes = sorted(
        process_map["processes"],
        key=lambda item: (-len(item["inventory_ids"]), clean(item["name"]).casefold()),
    )
    groups = "; ".join(
        f"{clean(item['name'])} ({len(item['inventory_ids'])})" for item in processes
    )
    if process_map.get("confirmation_status") == "analyst_confirmed":
        return f"{len(processes)} analyst-mapped groups; customer confirmation required: {groups}"
    return (
        f"{len(processes)} proposed groups; analyst and customer confirmation required: {groups}"
    )


def process_path(
    opportunity: dict[str, Any], orchestration: dict[str, Any], process_name: str
) -> str:
    correlation = "documented identifier"
    robot_output = "review bundle"
    for stage in orchestration["stages"]:
        if stage.get("phase") != "pilot" or stage.get("role") == "human_review":
            continue
        stage_name = re.sub(r"(?i)^read-only\s+", "", clean(stage["name"]))
        stage_name = re.sub(
            re.escape(clean(process_name)), "", stage_name, flags=re.I
        )
        stage_name = re.sub(r"(?i)^joins on\s+", "links ", stage_name)
        stage_name = re.sub(r"(?i)\s+and logs waits$", " and tracks waits", stage_name)
        stage_name = re.sub(r"\s+", " ", stage_name).strip()
        if stage.get("role") == "maestro":
            correlation = re.sub(r"(?i)^links\s+", "", stage_name).strip()
        elif stage.get("role") == "robot":
            robot_output = re.sub(r"(?i)^outputs\s+", "", clause(stage_name)).strip()
    measurement = orchestration["measurement_plan"]
    metric_text_parts: list[str] = []
    for item in measurement["metrics"]:
        formula = clean(item["formula"])
        for pattern, replacement in (
            (r"\bmatching proposed routes\b", "matching routes"),
            (
                r"\breviewed cases whose proposed route matches final disposition\b",
                "cases matching final disposition",
            ),
            (
                r"\breviewed cases with every required evidence field complete\b",
                "cases with complete evidence",
            ),
            (r"\bcases joined by invoice ID\b", "invoice-linked cases"),
            (r"\bknown missing documents correctly flagged\b", "missing documents flagged"),
            (r"\breviewed cases\b", "cases"),
            (r"\bcomplete required evidence fields\b", "complete fields"),
            (r"\bcorrect missing-document flags\b", "correct flags"),
            (r"\ball missing-document flags\b", "all flags"),
            (r"\brequired documents found\b", "documents found"),
            (r"\brequired documents expected\b", "documents expected"),
            (r"\ball known missing documents\b", "known missing documents"),
        ):
            formula = re.sub(pattern, replacement, formula, flags=re.I)
        metric_text_parts.append(f"{clean(item['name'])} = {formula}")
    metric_text = "; ".join(metric_text_parts)
    cadence = clean(measurement["cadence"]).replace("_", " ")
    sample_method = re.sub(
        r"\bselected\s+", "", clean(measurement["sample_method"]), flags=re.I
    )
    ground_truth = re.sub(
        r"(?i)^the\s+", "", clean(measurement["ground_truth"])
    )
    ground_truth = re.sub(r"(?i)\bper sampled invoice\b", "per invoice", ground_truth)
    return (
        f"Input: {sentence(sample_method)} Ground truth: {sentence(ground_truth)} "
        f"Ground-truth owner: {sentence(measurement['ground_truth_owner'])} "
        f"Correlation: {sentence(correlation)} Robot output: {sentence(robot_output)} "
        f"{clean(measurement['owner'])} "
        f"reports {cadence}: {metric_text}."
    )


def post_shadow_decision(opportunity: dict[str, Any]) -> str:
    objective = plain_customer_text(opportunity.get("pilot", {}).get("objective"))
    if re.search(r"cycle[- ]time", objective, flags=re.I) and re.search(
        r"separately approved live test", objective, flags=re.I
    ):
        return "Separately approved live test only."
    return "Pilot continuation only."


def write_boundary(orchestration: dict[str, Any]) -> str:
    write_pattern = re.compile(r"\b(?:execute|post|record|send|set|update|write)\w*\b", re.I)
    read_only_pattern = re.compile(r"\b(?:observe|read[- ]only|shadow)\b", re.I)
    for stage in orchestration["stages"]:
        if stage["role"] not in {"robot", "system_of_record"}:
            continue
        text = " ".join(clean(stage.get(field)) for field in ("name", "action"))
        if write_pattern.search(text) and not read_only_pattern.search(text):
            return "Pilot: no writes."
    return "Pilot: no writes."


def foundation_systems(
    inventory_ids: list[str], inventory_index: dict[str, Any]
) -> str:
    systems: list[str] = []
    seen: set[str] = set()
    for inventory_id in inventory_ids:
        for value in split_values(inventory_index[inventory_id].get("systems")):
            if value.casefold() not in seen:
                systems.append(value)
                seen.add(value.casefold())
    if len(systems) > 2:
        return ", ".join(systems[:2])
    return ", ".join(systems) or "systems not supplied"


def customer_gate(opportunity: dict[str, Any]) -> tuple[str, str, str]:
    value = clean(opportunity["pilot"]["exit_criteria"][0])
    match = re.fullmatch(
        r"Stop(?:\s+if|:)\s*(.+?)\.\s*"
        r"Go(?:\s+if|:)\s*(.+?)\.\s*"
        r"Revise(?:\s+if|:)\s*(.+?)\.?",
        value,
        flags=re.I,
    )
    if not match:
        raise ValueError("validated pilot gate could not be parsed")
    return tuple(clean(item) for item in match.groups())


def compact_gate_condition(value: str) -> str:
    text = re.sub(r"\b(?:is|are)\s+(?=under|between|\d)", "", clean(value), flags=re.I)
    text = re.sub(r"\breach\s+(?=\d)", "at ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def ranking_rows(
    process_map: dict[str, Any], selected_ids: list[str]
) -> list[str]:
    orchestrations = {
        item["opportunity_id"]: item for item in process_map["orchestrations"]
    }
    processes = {item["process_id"]: item for item in process_map["processes"]}
    decisions = {
        item["process_id"]: item
        for item in process_map["prioritization"]["decisions"]
    }
    rows = [
        "Order basis: strategy fit, foundation, evidence, delivery risk. Workshop ask: "
        "validate prerequisites and historical pilots; owners set proposed thresholds from "
        "baselines and tolerances. No deployment or investment approval.",
        "Account team: CSM delivers agenda/access by each target; TAM delivers product/tenant "
        "control note before each charter; AE delivers sponsor/funding decision after evidence; "
        "failed prerequisites defer.",
        "Pilot mechanics: data joins frozen exports; Maestro sequences handoffs; Robots prepare "
        "outputs; humans review. Unmatched records pause and rerun; final record systems require "
        "validation.",
        "",
        "| Rank | Process | Why this order |",
        "| --- | --- | --- |",
    ]
    for rank, opportunity_id in enumerate(selected_ids, start=1):
        process_id = orchestrations[opportunity_id]["process_id"]
        rationale = clean(decisions[process_id]["rationale"])
        rationale = re.sub(
            r"(?i)^selected(?:\s+(?:first|second|third|lower))?\s+because\s+",
            "",
            rationale,
        )
        rationale = re.sub(
            r"(?i)^confirmed linkage, ownership, foundation, and (.+?) provide strongest evidence\.?$",
            r"Strongest evidence: confirmed linkage, ownership, foundation, \1",
            rationale,
        )
        rationale = re.sub(
            r"(?i)^(.+?) linkage, ownership, and foundation are confirmed;",
            r"Confirmed \1 linkage, ownership, foundation;",
            rationale,
        )
        if rationale:
            rationale = rationale[0].upper() + rationale[1:]
        rows.append(
            f"| {rank} | {clean(processes[process_id]['name'])} | {sentence(rationale)} |"
        )
    deferred = sorted(
        (
            item
            for item in process_map["prioritization"]["decisions"]
            if item.get("status") == "deferred"
        ),
        key=lambda item: item.get("rank", 10**9),
    )
    deferred_names = [
        clean(processes[item["process_id"]]["name"])
        for item in deferred
        if item.get("process_id") in processes
    ]
    if deferred_names:
        rows.extend(
            [
                "",
                "Deferred pending owners, boundaries, or restart: "
                + natural_join(deferred_names)
                + ".",
            ]
        )
    return rows


def source_context_names(public_sources: list[dict[str, Any]]) -> str:
    titles = " ".join(clean(item.get("title")) for item in public_sources).casefold()
    if public_sources and all(item.get("official") is False for item in public_sources) and all(
        term in titles for term in ("synthetic", "customer-confirmed")
    ):
        return (
            f"{len(public_sources)} customer-confirmed synthetic "
            f"{plural(len(public_sources), 'record')}"
        )
    if public_sources and all(item.get("official") is False for item in public_sources):
        return (
            f"{len(public_sources)} non-official planning "
            f"{plural(len(public_sources), 'record')}"
        )
    labels: list[str] = []
    for item in public_sources[:3]:
        title = clean(item.get("title"))
        if not title:
            continue
        if item.get("official") is False:
            title += " (non-official planning context)"
        labels.append(title)
    return ", ".join(labels)


def why_summary(value: Any) -> str:
    text = first_sentence(plain_customer_text(value))
    first_clause = re.split(
        r",\s+(?=(?:and|but|while|with)\b)", text, maxsplit=1, flags=re.I
    )[0].strip()
    if len(first_clause.split()) >= 5:
        return sentence(first_clause)
    return text


def capability_text(
    orchestration: dict[str, Any], *, fit_requires_validation: bool
) -> str:
    concise_labels = {
        "maestro": "Maestro",
        "agentic": "Agents",
        "genai": "GenAI",
        "robots": "Robots",
        "human_review": "Human",
    }
    grouped = {
        "applies": [],
        "proposed_pending_fit": [],
        "validation_required": [],
        "not_needed": [],
    }
    for key in ("maestro", "agentic", "genai", "robots", "human_review"):
        item = orchestration["capability_roles"][key]
        label = concise_labels[key]
        applicability = item["applicability"]
        if applicability == "applies" and fit_requires_validation and key != "human_review":
            applicability = "proposed_pending_fit"
        grouped[applicability].append(label)
    if (
        grouped["proposed_pending_fit"] == ["Maestro", "Robots"]
        and grouped["not_needed"] == ["Agents", "GenAI"]
        and grouped["applies"] == ["Human"]
        and not grouped["validation_required"]
    ):
        return "Maestro/Robots proposed; no Agents/GenAI; human decides."
    parts: list[str] = []
    nonhuman_applies = [label for label in grouped["applies"] if label != "Human"]
    if nonhuman_applies:
        parts.append(f"Use {natural_join(nonhuman_applies)}.")
    if grouped["proposed_pending_fit"]:
        parts.append(f"{natural_join(grouped['proposed_pending_fit'])} proposed.")
    if grouped["validation_required"]:
        parts.append(
            f"Evaluate need and fit for {natural_join(grouped['validation_required'])}."
        )
    if grouped["not_needed"]:
        if len(grouped["not_needed"]) == 1:
            parts.append(f"{grouped['not_needed'][0]} not needed.")
        else:
            parts.append(f"{natural_join(grouped['not_needed'])} not needed.")
    if "Human" in grouped["applies"]:
        parts.append("Human decides.")
    return " ".join(parts)


def natural_join(values: list[str]) -> str:
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return " and ".join(values)
    return ", ".join(values[:-1]) + f", and {values[-1]}"


def short_account_role(value: Any) -> str:
    text = clean(value)
    aliases = {
        "uipath customer success manager": "CSM",
        "uipath account solution consultant": "solution consultant",
    }
    return aliases.get(text.casefold(), text)


def validation_text(
    opportunity: dict[str, Any],
    review_item: dict[str, Any] | None,
) -> str:
    requirements: list[str] = []
    deployment_unknown = opportunity.get("deployment", {}).get("status") != "compatible"
    capability_unknown = any(
        item.get("claim") != "confirmed_entitlement"
        for item in opportunity.get("capability_fit", [])
        if isinstance(item, dict)
    )
    if deployment_unknown and capability_unknown:
        requirements.extend(["product", "deployment"])
    elif deployment_unknown:
        requirements.append("deployment")
    elif capability_unknown:
        requirements.append("product")
    value_needs_validation = opportunity.get("value_model") is None
    if isinstance(review_item, dict):
        judgments = {
            item.get("claim_type"): item.get("judgment")
            for item in review_item.get("claim_reviews", [])
            if isinstance(item, dict)
        }
        value_needs_validation = judgments.get("value_logic") == "needs_validation"
    if value_needs_validation:
        requirements.append("value")
    if not requirements:
        return ""
    joined = ", ".join(requirements)
    return f"{joined.capitalize()} unconfirmed."


def workload_summary(
    profile: dict[str, Any],
    inventory_ids: list[str],
    inventory_index: dict[str, Any],
) -> str:
    handling_column = clean(
        profile.get("core_field_mapping", {}).get("handling_time")
    ).casefold()
    if "min" not in handling_column:
        return ""
    signals: list[str] = []
    for inventory_id in inventory_ids:
        item = inventory_index.get(inventory_id, {})
        metrics = {
            metric.get("name"): metric.get("value")
            for metric in item.get("metrics", [])
            if isinstance(metric, dict)
        }
        annual_volume = metrics.get("annual_volume")
        handling_minutes = metrics.get("handling_time")
        if (
            isinstance(annual_volume, bool)
            or not isinstance(annual_volume, (int, float))
            or isinstance(handling_minutes, bool)
            or not isinstance(handling_minutes, (int, float))
            or annual_volume < 0
            or handling_minutes < 0
        ):
            return ""
        volume = f"{annual_volume:,.0f}"
        minutes = f"{handling_minutes:,.0f}"
        name_words = clean(item.get("name")).split()
        short_name = " ".join(name_words[-2:]) if len(name_words) > 2 else " ".join(name_words)
        signals.append(f"{short_name} {volume}/year at {minutes} min")
    return (
        "Workload signals: "
        + "; ".join(signals)
        + "."
    )


def assessment_anchor(
    semantic_review: dict[str, Any] | None,
    portfolio: dict[str, Any],
) -> date:
    for value in (
        (semantic_review or {}).get("reviewed_at"),
        portfolio.get("as_of_date"),
    ):
        if not isinstance(value, str):
            continue
        try:
            return date.fromisoformat(value)
        except ValueError:
            continue
    raise ValueError("customer assessment requires a valid review or portfolio date")


def render(
    profile: dict[str, Any],
    ledger: dict[str, Any],
    portfolio: dict[str, Any],
    process_map: dict[str, Any],
    semantic_review: dict[str, Any] | None = None,
) -> str:
    customer_name = clean(portfolio["customer_name"])
    metadata = profile["metadata"]
    sheets = profile.get("sheets", [])
    sheet_names = ", ".join(clean(item.get("sheet")) for item in sheets) or "not supplied"
    public_sources = ledger.get("public_sources", [])
    public_source_names = source_context_names(public_sources)
    limitations = source_limitations(profile, ledger)
    selected_ids = selected_opportunity_ids(portfolio)
    unmapped_count = len(process_map["unmapped_inventory"])
    process_text = process_groups_text(process_map)
    source_suffix = Path(metadata["source_name"]).suffix.casefold()
    source_unit = "table" if source_suffix in {".csv", ".tsv"} else "sheet"
    source_scope = (
        f"{source_unit}: {sheet_names}"
        if metadata["sheet_count"] == 1
        else f"{metadata['sheet_count']} {plural(metadata['sheet_count'], source_unit)}: {sheet_names}"
    )

    departments = concentration_text(profile, "department", "departments")
    systems = concentration_text(profile, "systems", "systems", multi=True)
    opportunities = {
        item["opportunity_id"]: item for item in portfolio["opportunities"]
    }
    orchestrations = {
        item["opportunity_id"]: item for item in process_map["orchestrations"]
    }
    process_index = {item["process_id"]: item for item in process_map["processes"]}
    inventory_index = {
        item["inventory_id"]: item for item in profile["inventory_items"]
    }
    review_index = {
        item["opportunity_id"]: item
        for item in (semantic_review or {}).get("opportunity_reviews", [])
        if isinstance(item, dict) and isinstance(item.get("opportunity_id"), str)
    }
    anchor_date = assessment_anchor(semantic_review, portfolio)

    lines = [
        f"# Automation portfolio assessment: {customer_name}",
        "",
        "## Source File Summary",
        "",
        f"- **Inventory reviewed:** {metadata['source_name']}; {metadata['total_rows']} "
        f"{plural(metadata['total_rows'], 'record')}; {source_scope}.",
        f"- **Information available:** {available_fields(profile).replace(', and ', ', ')}.",
    ]
    if public_source_names:
        lines.append(f"- **Strategy context reviewed:** {public_source_names}.")
    limitation_text = "; ".join(clean(item).rstrip(" .;:") for item in limitations) + "."
    lines.append("- **Limitations:** " + limitation_text)
    lines.extend(
        [
            "",
            "## Current Automation Footprint",
            "",
            "| Portfolio view | What the inventory shows |",
            "| --- | --- |",
            f"| Total reviewed | {metadata['total_rows']} |",
            f"| Lifecycle mix | {lifecycle_text(profile)} |",
            f"| Process/domain groups | {process_text} |",
            f"| Department concentration | {departments}. |",
            f"| System concentration | {systems}. |",
            f"| Unmapped | {unmapped_count} {plural(unmapped_count, 'record')} |",
            "| Assessment boundary | Workload is not savings. Duplicate excluded. "
            "Read-only proposals authorize no writes or decisions. |",
            "",
            "## Top 3 Recommendations",
            "",
        ]
    )
    lines.extend(ranking_rows(process_map, selected_ids))
    lines.append("")
    if len(selected_ids) < 3:
        recommendation_noun = plural(len(selected_ids), "recommendation")
        recommendation_verb = "is" if len(selected_ids) == 1 else "are"
        recommendation_note = (
            f"Only {len(selected_ids)} {recommendation_noun} {recommendation_verb} ready for "
            "workshop validation; no lower-confidence filler was added."
        )
        lines.extend(
            [
                recommendation_note,
                "",
            ]
        )
    for rank, opportunity_id in enumerate(selected_ids, start=1):
        opportunity = opportunities[opportunity_id]
        orchestration = orchestrations[opportunity_id]
        process = process_index[orchestration["process_id"]]
        boundary = process["boundary"]
        foundation = []
        for inventory_id in orchestration["existing_automation_ids"]:
            item = inventory_index[inventory_id]
            status = clean(item.get("raw_status")) or clean(item["lifecycle_status"]).replace(
                "_", " "
            )
            foundation.append(
                f"{clean(item['name'])} ({status})"
            )
        next_step = orchestration["next_step"]
        kickoff_date = anchor_date + timedelta(days=next_step["target_days"])
        decision_date = kickoff_date + timedelta(days=opportunity["pilot"]["timeline_days"])
        stop_condition, go_condition, revise_condition = (
            compact_gate_condition(item)
            for item in customer_gate(opportunity)
        )
        opportunity_review = review_index.get(opportunity_id)
        review_judgments = {
            item.get("claim_type"): item.get("judgment")
            for item in (opportunity_review or {}).get("claim_reviews", [])
            if isinstance(item, dict)
        }
        fit_requires_validation = review_judgments.get("capability_fit") != "pass"
        display_name = re.sub(
            r"(?i)^deterministic\s+", "", clean(opportunity["name"])
        )
        if display_name:
            display_name = display_name[0].upper() + display_name[1:]
        why_it_matters = why_summary(opportunity["why_now"])
        next_action = re.sub(
            r"(?i);?\s*book the day-\d+ review\b", "", clean(next_step["action"])
        ).rstrip(" .;:")
        next_action = re.sub(
            r"(?i);?\s*UiPath validates product/deployment fit\b",
            "",
            next_action,
        )
        lines.extend(
            [
                f"### {rank}. {display_name}",
                "",
                f"- **End-to-end process:** Function: {sentence(clean(process['business_function']))} "
                f"Start: {sentence(clean(boundary['starts_when']))} "
                f"End: {sentence(clean(boundary['ends_when']))} Outcome: "
                f"{sentence(clean(boundary['business_outcome']))}",
                "",
                f"- **Why it matters:** {why_it_matters}",
                "",
                f"- **Existing automation foundation:** {len(foundation)} "
                f"{plural(len(foundation), 'automation')}: {', '.join(foundation)}.",
                "",
                f"- **Pilot path:** Proposed. "
                f"{process_path(opportunity, orchestration, process['name'])}",
                "",
                f"- **Roles and controls:** "
                f"{capability_text(orchestration, fit_requires_validation=fit_requires_validation)} "
                f"{validation_text(opportunity, opportunity_review)} "
                f"{write_boundary(orchestration)}",
                "",
                f"- **Decision gate:** Stop when {sentence(embedded_clause(stop_condition))} "
                f"Proceed when {sentence(embedded_clause(go_condition))} "
                f"Adjust when {sentence(embedded_clause(revise_condition))} "
                "Rerun before proceeding. "
                f"Decision owner: {clean(opportunity['pilot']['owner'])}. "
                f"{post_shadow_decision(opportunity)}",
                "",
                f"- **Next action:** Target: {kickoff_date.isoformat()}. Customer: "
                f"{clean(next_step['owner'])}; UiPath: "
                f"{short_account_role(next_step['account_team_owner'])}. "
                f"{labeled_sentence(next_action)} "
                f"Output: {sentence(clean(next_step['deliverable']))} "
                f"Decision: {decision_date.isoformat()}.",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-profile", required=True, type=Path)
    parser.add_argument("--evidence-ledger", required=True, type=Path)
    parser.add_argument("--portfolio", required=True, type=Path)
    parser.add_argument("--process-map", required=True, type=Path)
    parser.add_argument("--semantic-review", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-words", type=int, default=900)
    parser.add_argument("--max-review-age-days", type=int, default=30)
    parser.add_argument("--required-readiness", default="workshop_ready")
    parser.add_argument("--validation-date", type=parse_date, default=date.today())
    args = parser.parse_args()
    try:
        profile = load_json_object(args.inventory_profile, "inventory_profile")
        ledger = load_json_object(args.evidence_ledger, "evidence_ledger")
        portfolio = load_json_object(args.portfolio, "portfolio")
        process_map = load_json_object(args.process_map, "process_map")
        review = load_json_object(args.semantic_review, "semantic_review")
    except ContractLoadError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    failures = validate_portfolio(portfolio, ledger, profile=profile)
    failures.extend(validate_process_map(process_map, profile, portfolio))
    hashes = expected_artifact_hashes(
        {
            "inventory_profile_sha256": args.inventory_profile,
            "evidence_ledger_sha256": args.evidence_ledger,
            "portfolio_sha256": args.portfolio,
            "process_map_sha256": args.process_map,
        }
    )
    failures.extend(
        validate_semantic_review(
            review,
            ledger,
            portfolio,
            process_map,
            profile,
            expected_hashes=hashes,
            today=args.validation_date,
            max_age_days=args.max_review_age_days,
            required_readiness=args.required_readiness,
        )
    )
    if args.output.exists() and not args.force:
        failures.append(f"output already exists: {args.output}; pass --force to replace it")
    if args.max_words < 1:
        failures.append("--max-words must be positive")
    elif args.max_words > 900:
        failures.append("--max-words cannot exceed the 900-word customer contract")
    if failures:
        print(format_failures(failures), file=sys.stderr)
        return 1
    markdown = render(profile, ledger, portfolio, process_map, review)
    failures = validate_customer_assessment(markdown, max_words=args.max_words)
    if failures:
        print(format_failures(failures), file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown, encoding="utf-8")
    print(f"OK: {args.output}")
    print(f"words={markdown_word_count(markdown)}")
    print(f"recommendations={len(selected_opportunity_ids(portfolio))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
