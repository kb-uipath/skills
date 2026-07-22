#!/usr/bin/env python3
"""Contracts for concise customer portfolio assessments."""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable


PROCESS_MAP_VERSION = "1.0"
SEMANTIC_REVIEW_VERSION = "1.0"
READINESS_ORDER = {
    "exploratory": 0,
    "workshop_ready": 1,
    "pilot_authorizable": 2,
}
CLAIM_TYPES = {
    "inventory_support",
    "strategy_support",
    "process_coherence",
    "agentic_need",
    "capability_fit",
    "value_logic",
    "pilot_realism",
    "customer_language",
}
CRITICAL_WORKSHOP_CLAIMS = {
    "inventory_support",
    "strategy_support",
    "process_coherence",
    "agentic_need",
    "pilot_realism",
    "customer_language",
}
CAPABILITY_KEYS = {
    "maestro": "maestro",
    "agentic": "agentic",
    "genai": "genai",
    "robots": "robot",
    "human_review": "human_review",
}
STAGE_ROLES = {
    "existing_automation",
    "maestro",
    "agentic",
    "genai",
    "robot",
    "human_review",
    "system_of_record",
}
STAGE_PHASES = {
    "current_state": 0,
    "pilot": 1,
    "future_state": 2,
}
PLACEHOLDER_ASSIGNMENTS = {
    "tbd",
    "to be determined",
    "unassigned",
    "unknown",
    "none",
    "n/a",
    "na",
}
PRIORITIZATION_CRITERIA = {
    "strategy_alignment",
    "workload_signal",
    "automation_foundation",
    "process_coherence",
    "delivery_risk",
    "evidence_quality",
}
PILOT_MEASURE_TERMS = {
    "accuracy",
    "agreement",
    "cases",
    "coverage",
    "cycle",
    "errors",
    "precision",
    "recall",
    "sample",
    "time",
}
GENERIC_GATE_PHRASES = {
    "a control fails",
    "agreed sample",
    "every other result",
    "quality conditions pass",
}
GENERIC_PROCESS_PHRASES = {
    "end-to-end process",
    "faster and controlled completion",
    "improve efficiency",
    "responsible system",
    "responsible team",
    "streamline operations",
}
LINKAGE_MECHANIC_PATTERN = re.compile(
    r"\b(?:case|campaign|invoice|request|supplier|transaction)[- ]?(?:id|identifier|key)s?\b|"
    r"\b(?:join|link|match)\w*\b",
    re.I,
)
OBSERVABLE_OUTPUT_PATTERN = re.compile(
    r"\b(?:bundle|classification|comparison|evidence|flag|log|output|report|result|summary)\w*\b",
    re.I,
)
OBSERVATION_CADENCE_PATTERN = re.compile(
    r"\b(?:daily|each case|every case|per case|weekly)\b",
    re.I,
)
SAMPLE_METHOD_PATTERN = re.compile(
    r"\b(?:all|consecutive|completed|historical|random|recent|representative|stratified|across)\b",
    re.I,
)
GROUND_TRUTH_PATTERN = re.compile(
    r"\b(?:approved|confirmed|final|historical|reviewer|system-of-record)\b",
    re.I,
)
RATIO_METRIC_NAMES = {
    "accuracy",
    "agreement",
    "coverage",
    "linkage",
    "precision",
    "recall",
}
RATIO_UNIT_PATTERN = re.compile(
    r"\b(cases?|decisions?|dispositions?|documents?|exceptions?|files?|flags?|"
    r"items?|records?|requests?|routes?|transactions?)\b",
    re.I,
)
MUTATION_TERM = (
    r"(?:approve(?:s|ing)?|approved\s+(?:a|an|the|this|that)\b|"
    r"cancel(?:s|led|ed|ling|ing)?|change(?:s|d|ing)?|"
    r"close(?:s|d|ing)?|create(?:s|d|ing)?|delete(?:s|d|ing)?|deploy(?:s|ed|ing)?|"
    r"disable(?:s|d|ing)?|enable(?:s|d|ing)?|execute(?:s|d|ing)?|grant(?:s|ed|ing)?|"
    r"invoke(?:s|d|ing)?|modify(?:s|d|ing)?|post(?:s|ed|ing)?|"
    r"provision(?:s|ed|ing)?|publish(?:es|ed|ing)?|release(?:s|d|ing)?|"
    r"remove(?:s|d|ing)?|revoke(?:s|d|ing)?|send(?:s|ing)?|sent|"
    r"submit(?:s|ted|ting)?|trigger(?:s|ed|ing)?|update(?:s|d|ing)?|"
    r"upload(?:s|ed|ing)?|write(?:s|ing)?|wrote|written|"
    r"record(?:s|ed|ing)?\s+(?:a|an|the|approved|decision|human-approved|result|status|transaction|update)\b|"
    r"set(?:s|ting)?\s+(?:a|an|the|field|status|value)\b)"
)
WRITE_ACTION_PATTERN = re.compile(rf"\b{MUTATION_TERM}\b", re.I)
NEGATED_MUTATION_PATTERN = re.compile(
    rf"\b(?:can(?:not|'t)|do(?:es)?\s+not|may\s+not|must\s+not|never|should\s+not|"
    rf"will\s+not|without)\b[^.;:\n]{{0,48}}\b{MUTATION_TERM}\b|"
    rf"\bno\s+(?:(?:external|production|source[- ]system|system)\s+)?{MUTATION_TERM}\b",
    re.I,
)
NEGATION_CONTRAST_PATTERN = re.compile(r"\b(?:after|before|but|except|then|unless)\b", re.I)
DECISION_TERM_PATTERN = re.compile(
    r"\b(?:approval|assurance|decision|disposition|eligibility|funding|status)\b",
    re.I,
)
HUMAN_GATED_PATTERN = re.compile(
    r"\b(?:human[- ]approved|human[- ]confirmed|approved by|confirmed by)\b",
    re.I,
)


def has_system_changing_action(value: Any) -> bool:
    """Return true unless every mutation term is explicitly negated in its clause."""

    text = str(value or "")
    for clause in re.split(r"[.;:\n]+", text):
        if not WRITE_ACTION_PATTERN.search(clause):
            continue
        if (
            NEGATED_MUTATION_PATTERN.search(clause)
            and not NEGATION_CONTRAST_PATTERN.search(clause)
        ):
            continue
        return True
    return False


def artifact_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def selected_opportunity_ids(portfolio: dict[str, Any], limit: int = 3) -> list[str]:
    values = portfolio.get("rankings", {}).get("high_impact", [])
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, str)][:limit]


def _unknown_fields(value: Any, allowed: set[str], path: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return
    unknown = sorted(set(value) - allowed)
    if unknown:
        errors.append(f"{path} has unknown field(s): {', '.join(unknown)}")


def _required(value: Any, required: set[str], path: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        return
    missing = sorted(field for field in required if field not in value)
    if missing:
        errors.append(f"{path} is missing required field(s): {', '.join(missing)}")


def _string(value: Any, path: str, errors: list[str], *, min_words: int = 1) -> bool:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path} must be a non-empty string")
        return False
    if len(value.split()) < min_words:
        errors.append(f"{path} must contain at least {min_words} words")
        return False
    return True


def _id(value: Any, prefix: str, path: str, errors: list[str]) -> bool:
    if not isinstance(value, str) or not re.fullmatch(
        rf"{re.escape(prefix)}-[A-Z0-9][A-Z0-9._-]*", value
    ):
        errors.append(f"{path} must be a valid {prefix}-* ID")
        return False
    return True


def _iso_date(value: Any, path: str, errors: list[str]) -> date | None:
    if not isinstance(value, str):
        errors.append(f"{path} must be an ISO date")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{path} must be an ISO date")
        return None


def _string_list(
    value: Any,
    path: str,
    errors: list[str],
    *,
    min_items: int = 0,
) -> bool:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        errors.append(f"{path} must be an array of non-empty strings")
        return False
    if len(value) < min_items:
        errors.append(f"{path} must contain at least {min_items} item(s)")
        return False
    if len(value) != len(set(value)):
        errors.append(f"{path} must not contain duplicates")
        return False
    return True


def _is_placeholder(value: Any) -> bool:
    return not isinstance(value, str) or value.strip().casefold() in PLACEHOLDER_ASSIGNMENTS


def _pilot_gate_parts(value: Any) -> tuple[str, str, str] | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(
        r"\s*Stop(?:\s+if|:)\s*(.+?)\.\s*"
        r"Go(?:\s+if|:)\s*(.+?)\.\s*"
        r"Revise(?:\s+if|:)\s*(.+?)\.?\s*",
        value,
        flags=re.I,
    )
    return tuple(item.strip() for item in match.groups()) if match else None


def _validate_pilot_gate(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path} must define a stop-first pilot gate")
        return
    parts = _pilot_gate_parts(value)
    if parts is None:
        errors.append(
            f"{path} must use 'Stop if ... . Go if ... . Revise if ... .' in that order"
        )
        return
    stop, go, revise = parts
    for label, condition in (("stop", stop), ("go", go), ("revise", revise)):
        if len(condition.split()) < 5:
            errors.append(f"{path} {label} condition is too vague")
        folded = condition.casefold()
        for phrase in sorted(GENERIC_GATE_PHRASES):
            if phrase in folded:
                errors.append(f"{path} {label} condition contains generic phrase: {phrase}")
    go_folded = go.casefold()
    if not re.search(r"\d", go) or not any(term in go_folded for term in PILOT_MEASURE_TERMS):
        errors.append(f"{path} go condition must name a quantitative sample or quality measure")
    revise_folded = revise.casefold()
    if not any(term in revise_folded for term in PILOT_MEASURE_TERMS | {"scope", "control", "linkage"}):
        errors.append(f"{path} revise condition must name the result that triggers revision")
    if re.search(r"\d", go) and re.search(r"\d", revise) and not re.search(r"\d", stop):
        errors.append(
            f"{path} stop condition must define the quantitative failure range left by go and revise"
        )


def _validate_measurement_plan(
    value: Any,
    path: str,
    errors: list[str],
    *,
    pilot_gate: Any,
    expected_owner: Any,
) -> None:
    fields = {
        "sample_method",
        "ground_truth",
        "ground_truth_owner",
        "metrics",
        "cadence",
        "owner",
        "mixed_result_action",
    }
    _unknown_fields(value, fields, path, errors)
    _required(value, fields, path, errors)
    if not isinstance(value, dict):
        return

    sample_method = value.get("sample_method")
    if _string(sample_method, f"{path}.sample_method", errors, min_words=6):
        if not re.search(r"\b\d[\d,]*\b", sample_method):
            errors.append(f"{path}.sample_method must state a numeric sample")
        if not SAMPLE_METHOD_PATTERN.search(sample_method):
            errors.append(f"{path}.sample_method must state how cases are selected")
        gate_parts = _pilot_gate_parts(pilot_gate)
        gate_numbers = (
            set(re.findall(r"\b\d[\d,]*\b", gate_parts[1])) if gate_parts else set()
        )
        sample_numbers = set(re.findall(r"\b\d[\d,]*\b", sample_method))
        if gate_numbers and not sample_numbers.intersection(gate_numbers):
            errors.append(
                f"{path}.sample_method must use the numeric sample in the proceed gate"
            )

    ground_truth = value.get("ground_truth")
    if _string(ground_truth, f"{path}.ground_truth", errors, min_words=5):
        if not GROUND_TRUTH_PATTERN.search(ground_truth):
            errors.append(
                f"{path}.ground_truth must name the approved, final, historical, or reviewer-owned reference outcome"
            )
    ground_truth_owner = value.get("ground_truth_owner")
    _string(ground_truth_owner, f"{path}.ground_truth_owner", errors)
    if _is_placeholder(ground_truth_owner):
        errors.append(
            f"{path}.ground_truth_owner must identify the role accountable for the reference outcomes"
        )

    metrics = value.get("metrics")
    metric_names: set[str] = set()
    if not isinstance(metrics, list) or len(metrics) < 2:
        errors.append(f"{path}.metrics must contain at least two metric formulas")
        metrics = []
    for index, metric in enumerate(metrics):
        metric_path = f"{path}.metrics[{index}]"
        _unknown_fields(metric, {"name", "formula"}, metric_path, errors)
        _required(metric, {"name", "formula"}, metric_path, errors)
        if not isinstance(metric, dict):
            continue
        name = metric.get("name")
        if _string(name, f"{metric_path}.name", errors):
            normalized_name = str(name).strip().casefold()
            if normalized_name in metric_names:
                errors.append(f"{path}.metrics must use unique metric names")
            metric_names.add(normalized_name)
        formula = metric.get("formula")
        if _string(formula, f"{metric_path}.formula", errors, min_words=3):
            formula_text = str(formula)
            if "/" not in formula_text and "divided by" not in formula_text.casefold():
                errors.append(
                    f"{metric_path}.formula must state a numerator and denominator"
                )
            elif str(name).strip().casefold() in RATIO_METRIC_NAMES:
                sides = re.split(r"/|\bdivided by\b", formula_text, maxsplit=1, flags=re.I)
                if len(sides) == 2:
                    unit_sets = []
                    for side in sides:
                        units = {
                            match.group(1).casefold().rstrip("s")
                            for match in RATIO_UNIT_PATTERN.finditer(side)
                        }
                        unit_sets.append(units)
                    if not unit_sets[0] or not unit_sets[1] or not (
                        unit_sets[0] & unit_sets[1]
                    ):
                        errors.append(
                            f"{metric_path}.formula must use comparable numerator and denominator units"
                        )

    cadence = value.get("cadence")
    if cadence not in {"daily", "weekly", "per_case"}:
        errors.append(f"{path}.cadence must be daily, weekly, or per_case")
    owner = value.get("owner")
    _string(owner, f"{path}.owner", errors)
    if _is_placeholder(owner):
        errors.append(f"{path}.owner must be an accountable role or person")
    if (
        isinstance(owner, str)
        and isinstance(expected_owner, str)
        and owner.strip().casefold() != expected_owner.strip().casefold()
    ):
        errors.append(f"{path}.owner must match the pilot decision owner")

    mixed_action = value.get("mixed_result_action")
    if _string(mixed_action, f"{path}.mixed_result_action", errors, min_words=8):
        folded = str(mixed_action).casefold()
        if "rerun" not in folded:
            errors.append(f"{path}.mixed_result_action must require a rerun")
        if not re.search(
            r"\b(?:do not|must not|cannot) proceed\b|\bbefore proceeding\b",
            folded,
        ):
            errors.append(
                f"{path}.mixed_result_action must prohibit proceeding until all gates pass"
            )


def validate_process_map(
    process_map: dict[str, Any],
    profile: dict[str, Any],
    portfolio: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    fields = {
        "schema_version",
        "process_map_id",
        "customer_name",
        "profile_source_sha256",
        "confirmation_status",
        "confirmed_by",
        "confirmed_on",
        "prioritization",
        "processes",
        "unmapped_inventory",
        "orchestrations",
    }
    _unknown_fields(process_map, fields, "process_map", errors)
    _required(process_map, fields, "process_map", errors)
    if process_map.get("schema_version") != PROCESS_MAP_VERSION:
        errors.append(f"process_map.schema_version must be {PROCESS_MAP_VERSION!r}")
    _id(process_map.get("process_map_id"), "PROCESS-MAP", "process_map.process_map_id", errors)
    if process_map.get("customer_name") != portfolio.get("customer_name"):
        errors.append("process_map.customer_name must match portfolio.customer_name")

    if profile.get("schema_version") != "1.1":
        errors.append(
            "customer assessment requires inventory_profile schema 1.1; regenerate the profile"
        )
    metadata = profile.get("metadata", {})
    expected_source_hash = metadata.get("source_sha256") if isinstance(metadata, dict) else None
    if process_map.get("profile_source_sha256") != expected_source_hash:
        errors.append("process_map.profile_source_sha256 does not match inventory profile")
    source_date_summary = (
        metadata.get("source_date_summary") if isinstance(metadata, dict) else None
    )
    if not isinstance(source_date_summary, dict):
        errors.append(
            "customer assessment requires profile 1.1 source_date_summary; regenerate the profile"
        )
    if process_map.get("confirmation_status") not in {"suggested", "analyst_confirmed"}:
        errors.append(
            "process_map.confirmation_status must be suggested or analyst_confirmed"
        )
    _string(process_map.get("confirmed_by"), "process_map.confirmed_by", errors)
    if (
        process_map.get("confirmation_status") == "analyst_confirmed"
        and _is_placeholder(process_map.get("confirmed_by"))
    ):
        errors.append(
            "process_map.confirmed_by must identify the confirming analyst or role"
        )
    _iso_date(process_map.get("confirmed_on"), "process_map.confirmed_on", errors)

    profile_items = {
        item.get("inventory_id"): item
        for item in profile.get("inventory_items", [])
        if isinstance(item, dict) and isinstance(item.get("inventory_id"), str)
    }
    profile_ids = set(profile_items)
    process_ids: set[str] = set()
    assigned: dict[str, str] = {}
    processes = process_map.get("processes")
    if not isinstance(processes, list) or not processes:
        errors.append("process_map.processes must contain at least one process")
        processes = []
    for index, process in enumerate(processes):
        path = f"process_map.processes[{index}]"
        process_fields = {
            "process_id",
            "name",
            "business_function",
            "boundary",
            "inventory_ids",
            "membership_rationale",
            "linkage",
        }
        _unknown_fields(process, process_fields, path, errors)
        _required(process, process_fields, path, errors)
        if not isinstance(process, dict):
            continue
        process_id = process.get("process_id")
        if _id(process_id, "PROC", f"{path}.process_id", errors):
            if process_id in process_ids:
                errors.append(f"{path}.process_id is duplicated: {process_id}")
            process_ids.add(process_id)
        _string(process.get("name"), f"{path}.name", errors, min_words=2)
        _string(
            process.get("business_function"),
            f"{path}.business_function",
            errors,
            min_words=2,
        )
        _string(
            process.get("membership_rationale"),
            f"{path}.membership_rationale",
            errors,
            min_words=5,
        )
        boundary = process.get("boundary")
        boundary_fields = {"starts_when", "ends_when", "business_outcome"}
        _unknown_fields(boundary, boundary_fields, f"{path}.boundary", errors)
        _required(boundary, boundary_fields, f"{path}.boundary", errors)
        if isinstance(boundary, dict):
            for field in sorted(boundary_fields):
                _string(boundary.get(field), f"{path}.boundary.{field}", errors, min_words=4)
                boundary_text = str(boundary.get(field, "")).casefold()
                for phrase in sorted(GENERIC_PROCESS_PHRASES):
                    if phrase in boundary_text:
                        errors.append(
                            f"{path}.boundary.{field} contains generic placeholder language: "
                            f"{phrase}"
                        )
        inventory_ids = process.get("inventory_ids")
        if _string_list(inventory_ids, f"{path}.inventory_ids", errors, min_items=1):
            for inventory_id in inventory_ids:
                if inventory_id not in profile_ids:
                    errors.append(f"{path}.inventory_ids contains unknown ID {inventory_id}")
                if inventory_id in assigned:
                    errors.append(
                        f"inventory ID {inventory_id} is assigned more than once: "
                        f"{assigned[inventory_id]} and {process_id}"
                    )
                assigned[inventory_id] = str(process_id)
        linkage = process.get("linkage")
        linkage_fields = {"status", "rationale", "validation_step"}
        _unknown_fields(linkage, linkage_fields, f"{path}.linkage", errors)
        _required(linkage, linkage_fields, f"{path}.linkage", errors)
        if isinstance(linkage, dict):
            linkage_status = linkage.get("status")
            if linkage_status not in {
                "confirmed",
                "validation_required",
                "not_applicable",
            }:
                errors.append(f"{path}.linkage.status is invalid")
            _string(linkage.get("rationale"), f"{path}.linkage.rationale", errors, min_words=5)
            _string(
                linkage.get("validation_step"),
                f"{path}.linkage.validation_step",
                errors,
                min_words=5,
            )
            if isinstance(inventory_ids, list):
                if len(inventory_ids) > 1 and linkage_status == "not_applicable":
                    errors.append(
                        f"{path}.linkage.status cannot be not_applicable for a multi-automation process"
                    )
                if len(inventory_ids) == 1 and linkage_status != "not_applicable":
                    errors.append(
                        f"{path}.linkage.status must be not_applicable for a single-automation process"
                    )

    unmapped = process_map.get("unmapped_inventory")
    if not isinstance(unmapped, list):
        errors.append("process_map.unmapped_inventory must be an array")
        unmapped = []
    unmapped_ids: set[str] = set()
    for index, item in enumerate(unmapped):
        path = f"process_map.unmapped_inventory[{index}]"
        _unknown_fields(item, {"inventory_id", "reason"}, path, errors)
        _required(item, {"inventory_id", "reason"}, path, errors)
        if not isinstance(item, dict):
            continue
        inventory_id = item.get("inventory_id")
        if not isinstance(inventory_id, str) or inventory_id not in profile_ids:
            errors.append(f"{path}.inventory_id must reference a profile inventory ID")
        elif inventory_id in unmapped_ids or inventory_id in assigned:
            errors.append(f"inventory ID {inventory_id} is mapped more than once")
        else:
            unmapped_ids.add(inventory_id)
        _string(item.get("reason"), f"{path}.reason", errors, min_words=4)

    covered = set(assigned) | unmapped_ids
    missing = sorted(profile_ids - covered)
    extra = sorted(covered - profile_ids)
    if missing:
        errors.append("process map does not cover inventory ID(s): " + ", ".join(missing))
    if extra:
        errors.append("process map contains unknown inventory ID(s): " + ", ".join(extra))

    prioritization = process_map.get("prioritization")
    prioritization_fields = {"method", "criteria", "decisions"}
    _unknown_fields(
        prioritization,
        prioritization_fields,
        "process_map.prioritization",
        errors,
    )
    _required(
        prioritization,
        prioritization_fields,
        "process_map.prioritization",
        errors,
    )
    process_decisions: dict[str, dict[str, Any]] = {}
    ranked_decisions: dict[int, str] = {}
    if isinstance(prioritization, dict):
        _string(
            prioritization.get("method"),
            "process_map.prioritization.method",
            errors,
            min_words=8,
        )
        criteria = prioritization.get("criteria")
        if _string_list(
            criteria,
            "process_map.prioritization.criteria",
            errors,
            min_items=3,
        ):
            invalid_criteria = sorted(set(criteria) - PRIORITIZATION_CRITERIA)
            if invalid_criteria:
                errors.append(
                    "process_map.prioritization.criteria contains invalid value(s): "
                    + ", ".join(invalid_criteria)
                )
        decisions = prioritization.get("decisions")
        if not isinstance(decisions, list) or not decisions:
            errors.append("process_map.prioritization.decisions must contain at least one decision")
            decisions = []
        for index, decision in enumerate(decisions):
            path = f"process_map.prioritization.decisions[{index}]"
            decision_fields = {
                "process_id",
                "status",
                "rank",
                "strategy_alignment",
                "rationale",
                "observed_evidence",
                "validation_needed",
            }
            _unknown_fields(decision, decision_fields, path, errors)
            _required(decision, decision_fields, path, errors)
            if not isinstance(decision, dict):
                continue
            process_id = decision.get("process_id")
            if process_id not in process_ids:
                errors.append(f"{path}.process_id must reference a defined process")
            elif process_id in process_decisions:
                errors.append(f"{path}.process_id is duplicated: {process_id}")
            else:
                process_decisions[process_id] = decision
            status = decision.get("status")
            if status not in {"selected", "deferred", "not_prioritized"}:
                errors.append(f"{path}.status is invalid")
            strategy_alignment = decision.get("strategy_alignment")
            if strategy_alignment not in {
                "confirmed",
                "validation_required",
                "not_identified",
            }:
                errors.append(f"{path}.strategy_alignment is invalid")
            _string(decision.get("rationale"), f"{path}.rationale", errors, min_words=8)
            rationale = str(decision.get("rationale", "")).casefold()
            if len(str(decision.get("rationale", "")).split()) > 28:
                errors.append(f"{path}.rationale must contain no more than 28 words")
            observed_evidence = decision.get("observed_evidence")
            if _string_list(
                observed_evidence,
                f"{path}.observed_evidence",
                errors,
                min_items=1,
            ):
                for evidence_index, evidence in enumerate(observed_evidence):
                    _string(
                        evidence,
                        f"{path}.observed_evidence[{evidence_index}]",
                        errors,
                        min_words=3,
                    )
                    if re.search(
                        r"\b(?:confirm|validate|assum|unknown|unconfirmed|proposed|"
                        r"needs? to|requires? validation)\b",
                        evidence,
                        flags=re.I,
                    ):
                        errors.append(
                            f"{path}.observed_evidence[{evidence_index}] mixes observed facts "
                            "with validation or assumption language"
                        )
            validation_needed = decision.get("validation_needed")
            if _string_list(
                validation_needed,
                f"{path}.validation_needed",
                errors,
            ):
                for validation_index, validation_item in enumerate(validation_needed):
                    _string(
                        validation_item,
                        f"{path}.validation_needed[{validation_index}]",
                        errors,
                        min_words=3,
                    )
            if (
                status in {"selected", "deferred"}
                and strategy_alignment == "validation_required"
                and isinstance(validation_needed, list)
                and not validation_needed
            ):
                errors.append(
                    f"{path}.validation_needed must name what would confirm the planning priority"
                )
            if status == "selected" and not (
                "selected" in rationale
                and any(term in rationale for term in ("because", "ahead of", "higher", "lower"))
            ):
                errors.append(
                    f"{path}.rationale must explain why the process was selected over alternatives"
                )
            if (
                status == "deferred"
                and (
                    "defer" not in rationale
                    or not any(term in rationale for term in ("because", "until", "while"))
                )
            ):
                errors.append(
                    f"{path}.rationale must explain why and until when the process is deferred"
                )
            rank = decision.get("rank")
            if status in {"selected", "deferred"}:
                if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
                    errors.append(f"{path}.rank must be a positive integer")
                elif rank in ranked_decisions:
                    errors.append(
                        f"{path}.rank duplicates rank {rank} from {ranked_decisions[rank]}"
                    )
                else:
                    ranked_decisions[rank] = str(process_id)
            elif rank is not None:
                errors.append(f"{path}.rank must be null when status is not_prioritized")
        missing_decisions = sorted(process_ids - set(process_decisions))
        extra_decisions = sorted(set(process_decisions) - process_ids)
        if missing_decisions:
            errors.append(
                "process prioritization does not cover process ID(s): "
                + ", ".join(missing_decisions)
            )
        if extra_decisions:
            errors.append(
                "process prioritization contains unknown process ID(s): "
                + ", ".join(extra_decisions)
            )
        if ranked_decisions and sorted(ranked_decisions) != list(
            range(1, len(ranked_decisions) + 1)
        ):
            errors.append("process prioritization ranks must be consecutive from 1")

    opportunities = {
        item.get("opportunity_id"): item
        for item in portfolio.get("opportunities", [])
        if isinstance(item, dict) and isinstance(item.get("opportunity_id"), str)
    }
    processes_by_id = {
        item.get("process_id"): item
        for item in processes
        if isinstance(item, dict) and isinstance(item.get("process_id"), str)
    }
    selected_ids = set(selected_opportunity_ids(portfolio))
    orchestration_ids: set[str] = set()
    orchestrations = process_map.get("orchestrations")
    if not isinstance(orchestrations, list):
        errors.append("process_map.orchestrations must be an array")
        orchestrations = []
    for index, orchestration in enumerate(orchestrations):
        path = f"process_map.orchestrations[{index}]"
        orchestration_fields = {
            "opportunity_id",
            "process_id",
            "pattern",
            "existing_automation_ids",
            "stages",
            "capability_roles",
            "measurement_plan",
            "next_step",
        }
        _unknown_fields(orchestration, orchestration_fields, path, errors)
        _required(orchestration, orchestration_fields, path, errors)
        if not isinstance(orchestration, dict):
            continue
        opportunity_id = orchestration.get("opportunity_id")
        if not isinstance(opportunity_id, str) or opportunity_id not in opportunities:
            errors.append(f"{path}.opportunity_id must reference a portfolio opportunity")
            opportunity = {}
        else:
            opportunity = opportunities[opportunity_id]
            if opportunity_id in orchestration_ids:
                errors.append(f"{path}.opportunity_id is duplicated: {opportunity_id}")
            orchestration_ids.add(opportunity_id)
        process_id = orchestration.get("process_id")
        if process_id not in process_ids:
            errors.append(f"{path}.process_id must reference a defined process")
        process_inventory = {
            item_id for item_id, assigned_process in assigned.items() if assigned_process == process_id
        }
        existing_ids = orchestration.get("existing_automation_ids")
        existing_valid = _string_list(
            existing_ids, f"{path}.existing_automation_ids", errors
        )
        if existing_valid:
            unknown_existing = sorted(set(existing_ids) - process_inventory)
            if unknown_existing:
                errors.append(
                    f"{path}.existing_automation_ids must belong to {process_id}: "
                    + ", ".join(unknown_existing)
                )
            evidence_ids = set(
                opportunity.get("evidence_refs", {}).get("inventory_ids", [])
                if isinstance(opportunity, dict)
                else []
            )
            outside_evidence = sorted(set(existing_ids) - evidence_ids)
            if outside_evidence:
                errors.append(
                    f"{path}.existing_automation_ids must also be opportunity evidence: "
                    + ", ".join(outside_evidence)
                )
        pattern = orchestration.get("pattern")
        if pattern not in {"stitch_existing", "extend_single", "net_new"}:
            errors.append(f"{path}.pattern is invalid")
        elif existing_valid:
            if pattern == "stitch_existing" and len(existing_ids) < 2:
                errors.append(f"{path}.stitch_existing requires at least two automations")
            if pattern == "extend_single" and len(existing_ids) != 1:
                errors.append(f"{path}.extend_single requires exactly one automation")
            if pattern == "net_new" and existing_ids:
                errors.append(f"{path}.net_new must not list existing automations")

        stages = orchestration.get("stages")
        if not isinstance(stages, list) or not stages:
            errors.append(f"{path}.stages must contain at least one stage")
            stages = []
        seen_sequences: list[int] = []
        stage_inventory: set[str] = set()
        stage_roles: set[str] = set()
        for stage_index, stage in enumerate(stages):
            stage_path = f"{path}.stages[{stage_index}]"
            stage_fields = {
                "sequence",
                "phase",
                "name",
                "role",
                "inventory_ids",
                "action",
                "human_control",
            }
            _unknown_fields(stage, stage_fields, stage_path, errors)
            _required(stage, stage_fields, stage_path, errors)
            if not isinstance(stage, dict):
                continue
            sequence = stage.get("sequence")
            if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
                errors.append(f"{stage_path}.sequence must be a positive integer")
            else:
                seen_sequences.append(sequence)
            role = stage.get("role")
            if role not in STAGE_ROLES:
                errors.append(f"{stage_path}.role is invalid")
            else:
                stage_roles.add(role)
            phase = stage.get("phase")
            if phase not in STAGE_PHASES:
                errors.append(f"{stage_path}.phase is invalid")
            if role == "existing_automation" and phase != "current_state":
                errors.append(
                    f"{stage_path}.phase must be current_state for existing automation"
                )
            _string(stage.get("name"), f"{stage_path}.name", errors, min_words=2)
            _string(stage.get("action"), f"{stage_path}.action", errors, min_words=4)
            _string(
                stage.get("human_control"),
                f"{stage_path}.human_control",
                errors,
                min_words=3,
            )
            stage_ids = stage.get("inventory_ids")
            if _string_list(stage_ids, f"{stage_path}.inventory_ids", errors):
                unknown_stage_ids = sorted(set(stage_ids) - process_inventory)
                if unknown_stage_ids:
                    errors.append(
                        f"{stage_path}.inventory_ids must belong to {process_id}: "
                        + ", ".join(unknown_stage_ids)
                    )
                stage_inventory.update(stage_ids)
        if seen_sequences and seen_sequences != list(range(1, len(stages) + 1)):
            errors.append(f"{path}.stages sequences must be consecutive and ordered from 1")
        phase_order = [
            STAGE_PHASES[stage["phase"]]
            for stage in stages
            if isinstance(stage, dict) and stage.get("phase") in STAGE_PHASES
        ]
        if phase_order != sorted(phase_order):
            errors.append(f"{path}.stages phases must progress from current_state to pilot to future_state")
        if not any(
            isinstance(stage, dict) and stage.get("phase") == "pilot" for stage in stages
        ):
            errors.append(f"{path}.stages must define at least one pilot phase")
        if existing_valid and not set(existing_ids).issubset(stage_inventory):
            errors.append(f"{path}.stages must include every existing automation ID")
        prior_human_review = False
        for stage_index, stage in enumerate(stages):
            if not isinstance(stage, dict):
                continue
            role = stage.get("role")
            if role == "human_review":
                prior_human_review = True
                continue
            if role in {"existing_automation", "human_review"} or role not in STAGE_ROLES:
                continue
            action_text = " ".join(
                str(stage.get(field, "")) for field in ("name", "action")
            )
            if not has_system_changing_action(action_text):
                continue
            control_text = " ".join(
                str(stage.get(field, "")) for field in ("action", "human_control")
            )
            stage_path = f"{path}.stages[{stage_index}]"
            if stage.get("phase") != "future_state":
                errors.append(
                    f"{stage_path} system-changing action must be future_state, outside the shadow pilot"
                )
            if not prior_human_review:
                errors.append(
                    f"{stage_path} performs a system-changing action before a human-review stage"
                )
            if DECISION_TERM_PATTERN.search(action_text) and not HUMAN_GATED_PATTERN.search(
                control_text
            ):
                errors.append(
                    f"{stage_path} must describe decision-sensitive writes as human-confirmed or human-approved"
                )

        pilot = opportunity.get("pilot") if isinstance(opportunity, dict) else None
        exit_criteria = pilot.get("exit_criteria") if isinstance(pilot, dict) else None
        measurement_plan = orchestration.get("measurement_plan")
        _validate_measurement_plan(
            measurement_plan,
            f"{path}.measurement_plan",
            errors,
            pilot_gate=(exit_criteria[0] if isinstance(exit_criteria, list) and exit_criteria else None),
            expected_owner=(pilot.get("owner") if isinstance(pilot, dict) else None),
        )
        if opportunity_id in selected_ids:
            if not isinstance(exit_criteria, list) or not exit_criteria:
                errors.append(f"{path} selected opportunity must define a pilot exit criterion")
            else:
                _validate_pilot_gate(
                    exit_criteria[0],
                    f"{path}.pilot.exit_criteria[0]",
                    errors,
                )
                scope = str(pilot.get("narrow_scope", "")).casefold()
                criterion = str(exit_criteria[0]).casefold()
                read_only_shadow = (
                    "read-only" in scope
                    or "read only" in scope
                    or "historical" in scope
                )
                cycle_reduction = (
                    ("cycle time" in criterion or "cycle-time" in criterion)
                    and any(
                        term in criterion
                        for term in ("lower", "reduce", "reduction", "improve", "improvement")
                    )
                )
                if read_only_shadow and cycle_reduction:
                    errors.append(
                        f"{path}.pilot.exit_criteria[0] cannot measure live cycle-time reduction in a historical read-only shadow"
                    )
                gate_parts = _pilot_gate_parts(exit_criteria[0])
                data_needed = pilot.get("data_needed")
                first_input = (
                    data_needed[0]
                    if isinstance(data_needed, list)
                    and data_needed
                    and isinstance(data_needed[0], str)
                    else ""
                )
                input_numbers = set(re.findall(r"\b\d[\d,]*\b", first_input))
                proceed_numbers = (
                    set(re.findall(r"\b\d[\d,]*\b", gate_parts[1]))
                    if gate_parts
                    else set()
                )
                if not input_numbers or not input_numbers.intersection(proceed_numbers):
                    errors.append(
                        f"{path}.pilot.data_needed[0] must state the numeric sample used by the proceed gate"
                    )

            pilot_stage_text = " ".join(
                str(stage.get("action", ""))
                for stage in stages
                if isinstance(stage, dict) and stage.get("phase") == "pilot"
            )
            if not OBSERVABLE_OUTPUT_PATTERN.search(pilot_stage_text):
                errors.append(
                    f"{path}.stages pilot mechanics must name an observable output or evidence artifact"
                )
            if not OBSERVATION_CADENCE_PATTERN.search(pilot_stage_text):
                errors.append(
                    f"{path}.stages pilot mechanics must define a daily, weekly, or per-case observation cadence"
                )
            cadence = (
                measurement_plan.get("cadence")
                if isinstance(measurement_plan, dict)
                else None
            )
            cadence_pattern = {
                "daily": r"\bdaily\b",
                "weekly": r"\bweekly\b",
                "per_case": r"\b(?:each case|every case|per case)\b",
            }.get(cadence)
            if cadence_pattern and not re.search(cadence_pattern, pilot_stage_text, flags=re.I):
                errors.append(
                    f"{path}.stages pilot review cadence must match measurement_plan.cadence"
                )
            process_linkage = processes_by_id.get(process_id, {}).get("linkage", {})
            if (
                isinstance(process_linkage, dict)
                and process_linkage.get("status") == "validation_required"
                and not LINKAGE_MECHANIC_PATTERN.search(pilot_stage_text)
            ):
                errors.append(
                    f"{path}.stages pilot mechanics must name the join key or linkage test"
                )

        capability_roles = orchestration.get("capability_roles")
        _unknown_fields(capability_roles, set(CAPABILITY_KEYS), f"{path}.capability_roles", errors)
        _required(capability_roles, set(CAPABILITY_KEYS), f"{path}.capability_roles", errors)
        if isinstance(capability_roles, dict):
            for capability, stage_role in CAPABILITY_KEYS.items():
                role_path = f"{path}.capability_roles.{capability}"
                role_value = capability_roles.get(capability)
                _unknown_fields(role_value, {"applicability", "role"}, role_path, errors)
                _required(role_value, {"applicability", "role"}, role_path, errors)
                if not isinstance(role_value, dict):
                    continue
                applicability = role_value.get("applicability")
                if applicability not in {"applies", "not_needed", "validation_required"}:
                    errors.append(f"{role_path}.applicability is invalid")
                _string(role_value.get("role"), f"{role_path}.role", errors, min_words=4)
                if len(str(role_value.get("role", "")).split()) > 24:
                    errors.append(f"{role_path}.role must contain no more than 24 words")
                if applicability == "applies" and stage_role not in stage_roles:
                    errors.append(
                        f"{role_path} says applies but no {stage_role} stage is defined"
                    )
                if applicability == "not_needed" and stage_role in stage_roles:
                    errors.append(
                        f"{role_path} says not_needed but a {stage_role} stage is defined"
                    )

        next_step = orchestration.get("next_step")
        next_fields = {
            "owner",
            "account_team_owner",
            "action",
            "deliverable",
            "target_days",
        }
        _unknown_fields(next_step, next_fields, f"{path}.next_step", errors)
        _required(next_step, next_fields, f"{path}.next_step", errors)
        if isinstance(next_step, dict):
            _string(next_step.get("owner"), f"{path}.next_step.owner", errors)
            if _is_placeholder(next_step.get("owner")):
                errors.append(f"{path}.next_step.owner must be an accountable role or person")
            measurement_owner = (
                measurement_plan.get("owner")
                if isinstance(measurement_plan, dict)
                else None
            )
            if (
                isinstance(measurement_owner, str)
                and isinstance(next_step.get("owner"), str)
                and measurement_owner.strip().casefold()
                != next_step["owner"].strip().casefold()
            ):
                errors.append(
                    f"{path}.measurement_plan.owner must match next_step.owner"
                )
            _string(
                next_step.get("account_team_owner"),
                f"{path}.next_step.account_team_owner",
                errors,
            )
            if _is_placeholder(next_step.get("account_team_owner")):
                errors.append(
                    f"{path}.next_step.account_team_owner must be an accountable role or person"
                )
            pilot_owner = pilot.get("owner") if isinstance(pilot, dict) else None
            if (
                opportunity_id in selected_ids
                and isinstance(pilot_owner, str)
                and isinstance(next_step.get("owner"), str)
                and pilot_owner.strip().casefold()
                != next_step["owner"].strip().casefold()
            ):
                errors.append(
                    f"{path}.next_step.owner must match the pilot decision owner"
                )
            _string(next_step.get("action"), f"{path}.next_step.action", errors, min_words=5)
            process_linkage = processes_by_id.get(process_id, {}).get("linkage", {})
            if (
                opportunity_id in selected_ids
                and isinstance(process_linkage, dict)
                and process_linkage.get("status") == "validation_required"
                and not re.search(
                    r"\b(?:link\w*|identifiers?|keys?|ids?)\b",
                    str(next_step.get("action", "")),
                    flags=re.I,
                )
            ):
                errors.append(
                    f"{path}.next_step.action must include linkage or identifier confirmation"
                )
            _string(
                next_step.get("deliverable"),
                f"{path}.next_step.deliverable",
                errors,
                min_words=3,
            )
            target_days = next_step.get("target_days")
            if (
                isinstance(target_days, bool)
                or not isinstance(target_days, int)
                or not 1 <= target_days <= 30
            ):
                errors.append(f"{path}.next_step.target_days must be from 1 to 30")

    missing_orchestrations = sorted(selected_ids - orchestration_ids)
    if missing_orchestrations:
        errors.append(
            "process map is missing orchestration for selected opportunity ID(s): "
            + ", ".join(missing_orchestrations)
        )
    orchestration_by_opportunity = {
        item.get("opportunity_id"): item
        for item in orchestrations
        if isinstance(item, dict) and isinstance(item.get("opportunity_id"), str)
    }
    selected_processes = [
        orchestration_by_opportunity[opportunity_id].get("process_id")
        for opportunity_id in selected_opportunity_ids(portfolio)
        if opportunity_id in orchestration_by_opportunity
    ]
    if len(selected_processes) != len(set(selected_processes)):
        errors.append("selected recommendations must map to distinct process IDs")
    selected_decisions = [
        process_id
        for _, process_id in sorted(ranked_decisions.items())
        if process_decisions.get(process_id, {}).get("status") == "selected"
    ]
    selected_ranks = [
        rank
        for rank, process_id in sorted(ranked_decisions.items())
        if process_decisions.get(process_id, {}).get("status") == "selected"
    ]
    if selected_ranks != list(range(1, len(selected_processes) + 1)):
        errors.append("selected process prioritization ranks must be consecutive from 1")
    if selected_decisions != selected_processes:
        errors.append(
            "selected process prioritization ranks must match portfolio recommendation order"
        )
    selected_count = len(selected_processes)
    for rank, process_id in ranked_decisions.items():
        decision = process_decisions.get(process_id, {})
        if decision.get("status") == "deferred" and rank <= selected_count:
            errors.append("deferred process ranks must follow all selected process ranks")
    return errors


def _review_dates(
    review: dict[str, Any],
    ledger: dict[str, Any],
    profile: dict[str, Any],
    portfolio: dict[str, Any],
    process_map: dict[str, Any],
    errors: list[str],
    *,
    today: date,
    max_age_days: int,
) -> date | None:
    reviewed_at = _iso_date(review.get("reviewed_at"), "semantic_review.reviewed_at", errors)
    if reviewed_at is None:
        return None
    bound_dates: list[date] = []
    for value, path in (
        (portfolio.get("as_of_date"), "portfolio.as_of_date"),
        (process_map.get("confirmed_on"), "process_map.confirmed_on"),
        (
            ledger.get("inventory_profile", {}).get("as_of_date"),
            "evidence_ledger.inventory_profile.as_of_date",
        ),
    ):
        try:
            bound_dates.append(date.fromisoformat(str(value)))
        except ValueError:
            errors.append(f"{path} must be an ISO date")
    for index, source in enumerate(ledger.get("public_sources", [])):
        if not isinstance(source, dict):
            continue
        accessed_date = source.get("accessed_date")
        try:
            bound_dates.append(date.fromisoformat(str(accessed_date)))
        except ValueError:
            errors.append(
                f"evidence_ledger.public_sources[{index}].accessed_date must be an ISO date"
            )
    generated = profile.get("metadata", {}).get("generated_at_utc")
    if isinstance(generated, str):
        try:
            datetime.fromisoformat(generated.replace("Z", "+00:00"))
        except ValueError:
            errors.append("inventory_profile.metadata.generated_at_utc must be ISO-8601")
    # The review contract records a date, while generation uses a UTC instant.
    # Artifact hashes provide exact binding; comparing their calendar dates would
    # reject valid same-day reviews when local midnight differs from UTC midnight.
    if bound_dates and reviewed_at < max(bound_dates):
        errors.append("semantic review predates a bound artifact")
    age = (today - reviewed_at).days
    if age < 0:
        errors.append("semantic review date cannot be in the future")
    elif age > max_age_days:
        errors.append(
            f"semantic review is {age} days old; maximum is {max_age_days} days"
        )
    return reviewed_at


def derive_readiness(
    review: dict[str, Any],
    ledger: dict[str, Any],
    portfolio: dict[str, Any],
    process_map: dict[str, Any],
) -> str:
    selected_ids = selected_opportunity_ids(portfolio)
    review_by_id = {
        item.get("opportunity_id"): item
        for item in review.get("opportunity_reviews", [])
        if isinstance(item, dict)
    }
    orchestration_by_id = {
        item.get("opportunity_id"): item
        for item in process_map.get("orchestrations", [])
        if isinstance(item, dict)
    }
    reviewer_mode = review.get("reviewer", {}).get("mode")
    if (
        not selected_ids
        or reviewer_mode not in {"human", "independent_agent"}
        or process_map.get("confirmation_status") != "analyst_confirmed"
    ):
        return "exploratory"

    for opportunity_id in selected_ids:
        item = review_by_id.get(opportunity_id)
        orchestration = orchestration_by_id.get(opportunity_id)
        if not isinstance(item, dict) or not isinstance(orchestration, dict):
            return "exploratory"
        if item.get("blocking_findings"):
            return "exploratory"
        judgments = {
            claim.get("claim_type"): claim.get("judgment")
            for claim in item.get("claim_reviews", [])
            if isinstance(claim, dict)
        }
        if any(judgments.get(claim) != "pass" for claim in CRITICAL_WORKSHOP_CLAIMS):
            return "exploratory"
        if any(value == "fail" for value in judgments.values()):
            return "exploratory"
        if not orchestration.get("existing_automation_ids") or orchestration.get("pattern") == "net_new":
            return "exploratory"

    opportunities = {
        item.get("opportunity_id"): item
        for item in portfolio.get("opportunities", [])
        if isinstance(item, dict)
    }
    assumptions = {
        item.get("assumption_id"): item
        for item in ledger.get("assumptions", [])
        if isinstance(item, dict)
    }
    pilot_ready = True
    for opportunity_id in selected_ids:
        opportunity = opportunities.get(opportunity_id, {})
        review_item = review_by_id[opportunity_id]
        orchestration = orchestration_by_id.get(opportunity_id, {})
        judgments = {
            claim.get("claim_type"): claim.get("judgment")
            for claim in review_item.get("claim_reviews", [])
            if isinstance(claim, dict)
        }
        if set(judgments) != CLAIM_TYPES or any(value != "pass" for value in judgments.values()):
            pilot_ready = False
        if opportunity.get("deployment", {}).get("status") != "compatible":
            pilot_ready = False
        deployment_controls = opportunity.get("deployment", {}).get("controls", [])
        if not isinstance(deployment_controls, list) or not deployment_controls:
            pilot_ready = False
        if any(
            fit.get("claim") != "confirmed_entitlement"
            for fit in opportunity.get("capability_fit", [])
            if isinstance(fit, dict)
        ):
            pilot_ready = False
        capability_roles = orchestration.get("capability_roles", {})
        if not isinstance(capability_roles, dict) or any(
            isinstance(role_value, dict)
            and role_value.get("applicability") == "validation_required"
            for role_value in capability_roles.values()
        ):
            pilot_ready = False
        pilot = opportunity.get("pilot", {})
        if not isinstance(pilot, dict):
            pilot_ready = False
            pilot = {}
        if _is_placeholder(pilot.get("owner")):
            pilot_ready = False
        for field in (
            "objective",
            "narrow_scope",
            "agent_role",
            "human_role",
            "first_step",
        ):
            if not isinstance(pilot.get(field), str) or not pilot[field].strip():
                pilot_ready = False
        for field, minimum in (
            ("success_metrics", 2),
            ("data_needed", 1),
            ("exit_criteria", 1),
        ):
            values = pilot.get(field)
            if not isinstance(values, list) or len(values) < minimum:
                pilot_ready = False
        for assumption_id in opportunity.get("evidence_refs", {}).get("assumption_ids", []):
            if assumptions.get(assumption_id, {}).get("status") != "validated":
                pilot_ready = False
    deployment_model = ledger.get("customer", {}).get("deployment", {}).get("model")
    if deployment_model == "unknown":
        pilot_ready = False
    return "pilot_authorizable" if pilot_ready else "workshop_ready"


def validate_semantic_review(
    review: dict[str, Any],
    ledger: dict[str, Any],
    portfolio: dict[str, Any],
    process_map: dict[str, Any],
    profile: dict[str, Any],
    *,
    expected_hashes: dict[str, str] | None = None,
    today: date | None = None,
    max_age_days: int = 30,
    required_readiness: str = "exploratory",
) -> list[str]:
    errors: list[str] = []
    fields = {
        "schema_version",
        "review_id",
        "portfolio_id",
        "process_map_id",
        "reviewed_at",
        "reviewer",
        "artifact_hashes",
        "opportunity_reviews",
        "overall_readiness",
    }
    _unknown_fields(review, fields, "semantic_review", errors)
    _required(review, fields, "semantic_review", errors)
    if review.get("schema_version") != SEMANTIC_REVIEW_VERSION:
        errors.append(
            f"semantic_review.schema_version must be {SEMANTIC_REVIEW_VERSION!r}"
        )
    _id(review.get("review_id"), "REVIEW", "semantic_review.review_id", errors)
    if review.get("portfolio_id") != portfolio.get("portfolio_id"):
        errors.append("semantic_review.portfolio_id must match portfolio")
    if review.get("process_map_id") != process_map.get("process_map_id"):
        errors.append("semantic_review.process_map_id must match process map")
    if max_age_days < 1:
        errors.append("max_age_days must be positive")
    _review_dates(
        review,
        ledger,
        profile,
        portfolio,
        process_map,
        errors,
        today=today or date.today(),
        max_age_days=max_age_days,
    )

    reviewer = review.get("reviewer")
    _unknown_fields(reviewer, {"mode", "id"}, "semantic_review.reviewer", errors)
    _required(reviewer, {"mode", "id"}, "semantic_review.reviewer", errors)
    if isinstance(reviewer, dict):
        if reviewer.get("mode") not in {"human", "independent_agent", "single_agent_fallback"}:
            errors.append("semantic_review.reviewer.mode is invalid")
        _string(reviewer.get("id"), "semantic_review.reviewer.id", errors)
        if _is_placeholder(reviewer.get("id")):
            errors.append("semantic_review.reviewer.id must identify the reviewer")

    hash_fields = {
        "inventory_profile_sha256",
        "evidence_ledger_sha256",
        "portfolio_sha256",
        "process_map_sha256",
    }
    artifact_hashes = review.get("artifact_hashes")
    _unknown_fields(artifact_hashes, hash_fields, "semantic_review.artifact_hashes", errors)
    _required(artifact_hashes, hash_fields, "semantic_review.artifact_hashes", errors)
    if isinstance(artifact_hashes, dict):
        for key in sorted(hash_fields):
            value = artifact_hashes.get(key)
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                errors.append(f"semantic_review.artifact_hashes.{key} must be SHA-256")
            if expected_hashes is not None and value != expected_hashes.get(key):
                errors.append(f"semantic_review artifact hash mismatch: {key}")

    known_refs = {
        item.get("inventory_id")
        for item in ledger.get("inventory_evidence", [])
        if isinstance(item, dict)
    } | {
        item.get("source_id")
        for item in ledger.get("public_sources", [])
        if isinstance(item, dict)
    } | {
        item.get("assumption_id")
        for item in ledger.get("assumptions", [])
        if isinstance(item, dict)
    } | {
        item.get("process_id")
        for item in process_map.get("processes", [])
        if isinstance(item, dict)
    }
    known_refs.discard(None)
    selected_ids = set(selected_opportunity_ids(portfolio))
    opportunity_index = {
        item.get("opportunity_id"): item
        for item in portfolio.get("opportunities", [])
        if isinstance(item, dict) and isinstance(item.get("opportunity_id"), str)
    }
    orchestration_index = {
        item.get("opportunity_id"): item
        for item in process_map.get("orchestrations", [])
        if isinstance(item, dict) and isinstance(item.get("opportunity_id"), str)
    }
    review_ids: set[str] = set()
    opportunity_reviews = review.get("opportunity_reviews")
    if not isinstance(opportunity_reviews, list):
        errors.append("semantic_review.opportunity_reviews must be an array")
        opportunity_reviews = []
    for index, item in enumerate(opportunity_reviews):
        path = f"semantic_review.opportunity_reviews[{index}]"
        _unknown_fields(
            item,
            {"opportunity_id", "claim_reviews", "blocking_findings"},
            path,
            errors,
        )
        _required(
            item,
            {"opportunity_id", "claim_reviews", "blocking_findings"},
            path,
            errors,
        )
        if not isinstance(item, dict):
            continue
        opportunity_id = item.get("opportunity_id")
        if not isinstance(opportunity_id, str) or opportunity_id not in selected_ids:
            errors.append(f"{path}.opportunity_id must be one of the selected top opportunities")
        elif opportunity_id in review_ids:
            errors.append(f"{path}.opportunity_id is duplicated")
        else:
            review_ids.add(opportunity_id)
        opportunity = opportunity_index.get(opportunity_id, {})
        orchestration = orchestration_index.get(opportunity_id, {})
        evidence = opportunity.get("evidence_refs", {}) if isinstance(opportunity, dict) else {}
        expected_inventory_refs = set(evidence.get("inventory_ids", []))
        expected_source_refs = set(evidence.get("public_source_ids", []))
        expected_assumption_refs = set(evidence.get("assumption_ids", []))
        expected_process_ref = orchestration.get("process_id")
        claims = item.get("claim_reviews")
        if not isinstance(claims, list):
            errors.append(f"{path}.claim_reviews must be an array")
            claims = []
        seen_claims: set[str] = set()
        for claim_index, claim in enumerate(claims):
            claim_path = f"{path}.claim_reviews[{claim_index}]"
            claim_fields = {"claim_type", "judgment", "evidence_refs", "rationale"}
            _unknown_fields(claim, claim_fields, claim_path, errors)
            _required(claim, claim_fields, claim_path, errors)
            if not isinstance(claim, dict):
                continue
            claim_type = claim.get("claim_type")
            if claim_type not in CLAIM_TYPES:
                errors.append(f"{claim_path}.claim_type is invalid")
            elif claim_type in seen_claims:
                errors.append(f"{claim_path}.claim_type is duplicated")
            else:
                seen_claims.add(claim_type)
            if claim.get("judgment") not in {"pass", "needs_validation", "fail"}:
                errors.append(f"{claim_path}.judgment is invalid")
            evidence_refs = claim.get("evidence_refs")
            minimum = 0 if claim_type == "customer_language" else 1
            if _string_list(
                evidence_refs, f"{claim_path}.evidence_refs", errors, min_items=minimum
            ):
                unknown = sorted(set(evidence_refs) - known_refs)
                if unknown:
                    errors.append(
                        f"{claim_path}.evidence_refs contains unknown ID(s): "
                        + ", ".join(unknown)
                    )
                supplied = set(evidence_refs)
                if claim_type == "inventory_support":
                    inventory_refs = {item for item in supplied if item.startswith("INV-")}
                    if not inventory_refs:
                        errors.append(
                            f"{claim_path}.evidence_refs must cite recommendation inventory evidence"
                        )
                    unrelated = sorted(inventory_refs - expected_inventory_refs)
                    if unrelated:
                        errors.append(
                            f"{claim_path}.evidence_refs cites inventory outside the recommendation: "
                            + ", ".join(unrelated)
                        )
                elif claim_type == "strategy_support":
                    source_refs = {item for item in supplied if item.startswith("SRC-")}
                    if not source_refs:
                        errors.append(
                            f"{claim_path}.evidence_refs must cite recommendation strategy evidence"
                        )
                    unrelated = sorted(source_refs - expected_source_refs)
                    if unrelated:
                        errors.append(
                            f"{claim_path}.evidence_refs cites strategy outside the recommendation: "
                            + ", ".join(unrelated)
                        )
                elif claim_type in {
                    "process_coherence",
                    "capability_fit",
                    "pilot_realism",
                } and expected_process_ref not in supplied:
                    errors.append(
                        f"{claim_path}.evidence_refs must cite mapped process {expected_process_ref}"
                    )
                elif claim_type == "agentic_need" and not supplied.intersection(
                    expected_inventory_refs | {expected_process_ref}
                ):
                    errors.append(
                        f"{claim_path}.evidence_refs must cite recommendation inventory or process evidence"
                    )
                elif claim_type == "value_logic" and not supplied.intersection(
                    expected_inventory_refs
                    | expected_assumption_refs
                    | ({expected_process_ref} if expected_process_ref else set())
                ):
                    errors.append(
                        f"{claim_path}.evidence_refs must cite recommendation value evidence"
                    )
            _string(claim.get("rationale"), f"{claim_path}.rationale", errors, min_words=5)
        missing_claims = sorted(CLAIM_TYPES - seen_claims)
        extra_claims = sorted(seen_claims - CLAIM_TYPES)
        if missing_claims:
            errors.append(f"{path} is missing claim review(s): {', '.join(missing_claims)}")
        if extra_claims:
            errors.append(f"{path} has unknown claim review(s): {', '.join(extra_claims)}")
        _string_list(item.get("blocking_findings"), f"{path}.blocking_findings", errors)

    missing_reviews = sorted(selected_ids - review_ids)
    if missing_reviews:
        errors.append(
            "semantic review is missing selected opportunity ID(s): "
            + ", ".join(missing_reviews)
        )
    extra_reviews = sorted(review_ids - selected_ids)
    if extra_reviews:
        errors.append(
            "semantic review contains unselected opportunity ID(s): "
            + ", ".join(extra_reviews)
        )

    derived = derive_readiness(review, ledger, portfolio, process_map)
    declared = review.get("overall_readiness")
    if declared not in READINESS_ORDER:
        errors.append("semantic_review.overall_readiness is invalid")
    elif declared != derived:
        errors.append(
            f"semantic_review.overall_readiness must equal derived readiness {derived!r}"
        )
    if required_readiness not in READINESS_ORDER:
        errors.append(f"unknown required readiness: {required_readiness}")
    elif declared in READINESS_ORDER and (
        READINESS_ORDER[declared] < READINESS_ORDER[required_readiness]
    ):
        errors.append(
            f"semantic review readiness {declared!r} is below required {required_readiness!r}"
        )
    return errors


def expected_artifact_hashes(paths: dict[str, Path]) -> dict[str, str]:
    return {key: artifact_sha256(path) for key, path in paths.items()}


def format_failures(failures: Iterable[str]) -> str:
    return "\n".join(f"FAIL: {failure}" for failure in failures)
