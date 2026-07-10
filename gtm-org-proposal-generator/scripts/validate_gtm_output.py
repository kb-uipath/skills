#!/usr/bin/env python3
"""Validate and render canonical GTM proposal contracts."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "gtm-org-proposal-generator/v1"
MIGRATION_GUIDANCE = (
    "legacy free-form Markdown validation is disabled. Create a canonical JSON "
    f"contract with contract_version={CONTRACT_VERSION!r}, then run this script "
    "against the JSON and use --render to produce deterministic Markdown."
)
ESTIMATE_TIERS = {"Documented", "Derived", "Benchmarked", "Assumption"}
CONFIDENCE_LEVELS = {"High", "Medium", "Low"}
CAPABILITY_AVAILABILITY = {"available", "requires-confirmation"}
RESEARCH_SCOPE = "public-authoritative-only"
CLASSIFICATION = "Public"

SOURCE_ID_RE = re.compile(r"^S[1-9]\d*$")
CAPABILITY_ID_RE = re.compile(r"^C[1-9]\d*$")
MONEY_OR_PERCENT_RE = re.compile(
    r"(\$[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|k|m|bn))?|\b\d+(?:\.\d+)?%)",
    re.IGNORECASE,
)
UNSAFE_CLAIMS = (
    "guaranteed roi",
    "guaranteed savings",
    "will save",
    "will reduce cost",
    "proven to save",
    "no risk",
)

REQUIRED_TOP_LEVEL = (
    "contract_version",
    "confirmed_scope",
    "classification",
    "source_ledger",
    "capability_ledger",
    "budget_program_areas",
    "prioritized_use_cases",
    "proposal_cards",
    "executive_close",
    "evidence_gaps",
    "assumptions",
)
REQUIRED_SCOPE = (
    "organization",
    "target_entity",
    "industry_vertical",
    "uipath_deployment_type",
    "research_scope",
    "accessed_date",
)
REQUIRED_CLASSIFICATION = ("data_classification", "retention")
REQUIRED_SOURCE = (
    "source_id",
    "title",
    "publisher",
    "publication_date",
    "url",
    "accessed_date",
    "facts_supported",
)
REQUIRED_CAPABILITY = (
    "capability_id",
    "capability_name",
    "deployment_type",
    "availability",
    "docs_url",
    "docs_checked_date",
    "source_ids",
)
REQUIRED_BUDGET_AREA = (
    "rank",
    "program_area",
    "budget",
    "budget_basis",
    "source_ids",
    "admin_cost",
)
REQUIRED_ADMIN_COST = ("estimate", "tier", "math", "source_ids")
REQUIRED_USE_CASE = (
    "rank",
    "use_case",
    "target_program_area",
    "driver",
    "capability_ids",
    "impact_range",
    "confidence",
    "estimate_tier",
    "source_ids",
    "impact_math",
)
REQUIRED_PROPOSAL_CARD = (
    "rank",
    "use_case",
    "business_challenge",
    "proposed_solution",
    "capability_ids",
    "estimated_impact",
    "estimate_tier",
    "impact_math",
    "confidence",
    "source_ids",
    "validation_required",
    "pilot_owner",
    "target_decision_date",
    "pilot_exit_criteria",
)
REQUIRED_IMPACT_MATH = (
    "baseline",
    "addressable_share",
    "productivity_or_cost_assumption",
    "resulting_range",
    "source_ids",
)
REQUIRED_EVIDENCE_GAP = ("gap", "impact", "resolution_path")
REQUIRED_EXECUTIVE_CLOSE = (
    "decision_ask",
    "portfolio_value_range",
    "aggregation_method",
    "double_counting_caveat",
    "executive_owner",
    "decision_date",
    "source_ids",
    "next_steps",
)
REQUIRED_NEXT_STEP = ("action", "owner", "due_date")
REQUIRED_PORTFOLIO_MATH = (
    "included_card_ranks",
    "lower_adjustment_factor",
    "upper_adjustment_factor",
    "resulting_range",
)

MONEY_AMOUNT_RE = re.compile(
    r"\$\s*([\d,]+(?:\.\d+)?)\s*(thousand|million|billion|k|m|bn|b)?",
    re.IGNORECASE,
)


def validate_text(text: str) -> list[str]:
    """Fail closed for the old Markdown-only contract."""
    try:
        contract = json.loads(text)
    except json.JSONDecodeError:
        return [MIGRATION_GUIDANCE]
    return validate_contract(contract)


def validate_contract(contract: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(contract, dict):
        return ["contract must be a JSON object"]

    require_fields(contract, REQUIRED_TOP_LEVEL, "contract", errors)
    if contract.get("contract_version") != CONTRACT_VERSION:
        errors.append(
            "contract.contract_version must be "
            f"{CONTRACT_VERSION!r}; legacy or unversioned contracts are rejected"
        )

    scope = expect_dict(contract.get("confirmed_scope"), "confirmed_scope", errors)
    require_fields(scope, REQUIRED_SCOPE, "confirmed_scope", errors)
    if scope.get("research_scope") != RESEARCH_SCOPE:
        errors.append(
            f"confirmed_scope.research_scope must be {RESEARCH_SCOPE!r} for this skill"
        )
    scope_accessed_date = parse_date_field(
        scope.get("accessed_date"), "confirmed_scope.accessed_date", errors
    )

    classification = expect_dict(contract.get("classification"), "classification", errors)
    require_fields(classification, REQUIRED_CLASSIFICATION, "classification", errors)
    if classification.get("data_classification") != CLASSIFICATION:
        errors.append("classification.data_classification must be 'Public'")
    if contains_forbidden_confidential_marker(classification.get("retention")):
        errors.append("classification.retention must not authorize confidential data retention")

    source_ids = validate_source_ledger(
        contract.get("source_ledger"), scope_accessed_date, errors
    )
    sources_by_id = {
        source.get("source_id"): source
        for source in contract.get("source_ledger", [])
        if isinstance(source, dict) and isinstance(source.get("source_id"), str)
    }
    capability_ids = validate_capability_ledger(
        contract.get("capability_ledger"),
        scope,
        scope_accessed_date,
        source_ids,
        sources_by_id,
        errors,
    )
    validate_budget_areas(contract.get("budget_program_areas"), source_ids, errors)
    validate_use_cases(
        contract.get("prioritized_use_cases"), source_ids, capability_ids, errors
    )
    validate_cards(
        contract.get("proposal_cards"),
        source_ids,
        capability_ids,
        contract.get("capability_ledger"),
        errors,
    )
    validate_executive_close(
        contract.get("executive_close"),
        source_ids,
        contract.get("proposal_cards"),
        errors,
    )
    validate_evidence_gaps(contract.get("evidence_gaps"), contract.get("proposal_cards"), errors)
    validate_assumptions(contract.get("assumptions"), errors)
    validate_unsafe_claims(contract, errors)

    return errors


def validate_source_ledger(value: Any, scope_accessed_date: date | None, errors: list[str]) -> set[str]:
    sources = expect_list(value, "source_ledger", errors)
    if not sources:
        errors.append("source_ledger must include at least one public authoritative source")
        return set()

    ids: set[str] = set()
    for index, source in enumerate(sources, start=1):
        path = f"source_ledger[{index}]"
        source_dict = expect_dict(source, path, errors)
        require_fields(source_dict, REQUIRED_SOURCE, path, errors)

        source_id = source_dict.get("source_id")
        if not valid_id(source_id, SOURCE_ID_RE):
            errors.append(f"{path}.source_id must look like S1")
        elif source_id in ids:
            errors.append(f"{path}.source_id is duplicated: {source_id}")
        else:
            ids.add(source_id)

        url = source_dict.get("url")
        if not isinstance(url, str) or not url.startswith(("https://", "http://")):
            errors.append(f"{path}.url must be an http(s) URL")

        facts_supported = source_dict.get("facts_supported")
        if not isinstance(facts_supported, list) or not facts_supported:
            errors.append(f"{path}.facts_supported must be a non-empty list")
        elif not all_non_empty_strings(facts_supported):
            errors.append(f"{path}.facts_supported must contain only non-empty strings")

        accessed = parse_date_field(source_dict.get("accessed_date"), f"{path}.accessed_date", errors)
        if accessed and scope_accessed_date and accessed > scope_accessed_date:
            errors.append(f"{path}.accessed_date cannot be after confirmed_scope.accessed_date")

    return ids


def validate_capability_ledger(
    value: Any,
    scope: dict[str, Any],
    scope_accessed_date: date | None,
    source_ids: set[str],
    sources_by_id: dict[str, dict[str, Any]],
    errors: list[str],
) -> set[str]:
    capabilities = expect_list(value, "capability_ledger", errors)
    if not capabilities:
        errors.append("capability_ledger must include current UiPath documentation evidence")
        return set()

    deployment_type = scope.get("uipath_deployment_type")
    ids: set[str] = set()
    for index, capability in enumerate(capabilities, start=1):
        path = f"capability_ledger[{index}]"
        item = expect_dict(capability, path, errors)
        require_fields(item, REQUIRED_CAPABILITY, path, errors)

        capability_id = item.get("capability_id")
        if not valid_id(capability_id, CAPABILITY_ID_RE):
            errors.append(f"{path}.capability_id must look like C1")
        elif capability_id in ids:
            errors.append(f"{path}.capability_id is duplicated: {capability_id}")
        else:
            ids.add(capability_id)

        if item.get("deployment_type") != deployment_type:
            errors.append(
                f"{path}.deployment_type must match confirmed_scope.uipath_deployment_type"
            )

        if item.get("availability") not in CAPABILITY_AVAILABILITY:
            errors.append(
                f"{path}.availability must be one of "
                + ", ".join(sorted(CAPABILITY_AVAILABILITY))
            )

        docs_url = item.get("docs_url")
        if not isinstance(docs_url, str) or "docs.uipath.com" not in docs_url:
            errors.append(f"{path}.docs_url must point to docs.uipath.com")

        checked = parse_date_field(item.get("docs_checked_date"), f"{path}.docs_checked_date", errors)
        if checked and scope_accessed_date and checked > scope_accessed_date:
            errors.append(f"{path}.docs_checked_date cannot be after confirmed_scope.accessed_date")

        validate_source_refs(item.get("source_ids"), source_ids, f"{path}.source_ids", errors)
        cited_sources = [
            sources_by_id[source_id]
            for source_id in item.get("source_ids", [])
            if source_id in sources_by_id
        ]
        if isinstance(docs_url, str) and not any(
            source.get("url") == docs_url and source.get("publisher") == "UiPath"
            for source in cited_sources
        ):
            errors.append(
                f"{path}.source_ids must cite a UiPath source whose url exactly matches docs_url"
            )

    return ids


def validate_budget_areas(value: Any, source_ids: set[str], errors: list[str]) -> None:
    areas = expect_list(value, "budget_program_areas", errors)
    if not areas:
        errors.append("budget_program_areas must include at least one source-backed area")
        return
    if len(areas) > 20:
        errors.append("budget_program_areas must not exceed 20 rows")
    validate_rank_sequence(areas, "budget_program_areas", errors)

    for index, area in enumerate(areas, start=1):
        path = f"budget_program_areas[{index}]"
        item = expect_dict(area, path, errors)
        require_fields(item, REQUIRED_BUDGET_AREA, path, errors)
        validate_source_refs(item.get("source_ids"), source_ids, f"{path}.source_ids", errors)
        require_money_or_percent_sources(item.get("budget"), item, path, errors)

        admin_cost = expect_dict(item.get("admin_cost"), f"{path}.admin_cost", errors)
        require_fields(admin_cost, REQUIRED_ADMIN_COST, f"{path}.admin_cost", errors)
        validate_estimate_tier(admin_cost.get("tier"), f"{path}.admin_cost.tier", errors)
        validate_source_refs(
            admin_cost.get("source_ids"),
            source_ids,
            f"{path}.admin_cost.source_ids",
            errors,
        )
        require_money_or_percent_sources(admin_cost.get("estimate"), admin_cost, f"{path}.admin_cost", errors)
        require_money_or_percent_sources(admin_cost.get("math"), admin_cost, f"{path}.admin_cost", errors)


def validate_use_cases(
    value: Any,
    source_ids: set[str],
    capability_ids: set[str],
    errors: list[str],
) -> None:
    use_cases = expect_list(value, "prioritized_use_cases", errors)
    if not use_cases:
        errors.append("prioritized_use_cases must include at least one complete use case")
        return
    if len(use_cases) > 10:
        errors.append("prioritized_use_cases must not exceed 10 rows")
    validate_rank_sequence(use_cases, "prioritized_use_cases", errors)

    for index, use_case in enumerate(use_cases, start=1):
        path = f"prioritized_use_cases[{index}]"
        item = expect_dict(use_case, path, errors)
        require_fields(item, REQUIRED_USE_CASE, path, errors)
        validate_confidence(item.get("confidence"), f"{path}.confidence", errors)
        validate_estimate_tier(item.get("estimate_tier"), f"{path}.estimate_tier", errors)
        validate_source_refs(item.get("source_ids"), source_ids, f"{path}.source_ids", errors)
        validate_capability_refs(
            item.get("capability_ids"), capability_ids, f"{path}.capability_ids", errors
        )
        validate_impact_math(item.get("impact_math"), source_ids, f"{path}.impact_math", errors)
        validate_impact_alignment(
            item.get("impact_range"), item.get("impact_math"), path, errors
        )
        validate_nested_source_coverage(item, path, errors)
        require_money_or_percent_sources(item.get("impact_range"), item, path, errors)


def validate_cards(
    value: Any,
    source_ids: set[str],
    capability_ids: set[str],
    capability_ledger: Any,
    errors: list[str],
) -> None:
    cards = expect_list(value, "proposal_cards", errors)
    if not cards:
        errors.append("proposal_cards must include at least one complete card")
        return
    if len(cards) > 10:
        errors.append("proposal_cards must not exceed 10 cards")
    validate_rank_sequence(cards, "proposal_cards", errors)

    availability_by_id = {
        item.get("capability_id"): item.get("availability")
        for item in capability_ledger
        if isinstance(item, dict)
    } if isinstance(capability_ledger, list) else {}

    for index, card in enumerate(cards, start=1):
        path = f"proposal_cards[{index}]"
        item = expect_dict(card, path, errors)
        require_fields(item, REQUIRED_PROPOSAL_CARD, path, errors)
        validate_confidence(item.get("confidence"), f"{path}.confidence", errors)
        validate_estimate_tier(item.get("estimate_tier"), f"{path}.estimate_tier", errors)
        validate_source_refs(item.get("source_ids"), source_ids, f"{path}.source_ids", errors)
        validate_capability_refs(
            item.get("capability_ids"), capability_ids, f"{path}.capability_ids", errors
        )
        validate_impact_math(item.get("impact_math"), source_ids, f"{path}.impact_math", errors)
        validate_impact_alignment(
            item.get("estimated_impact"), item.get("impact_math"), path, errors
        )
        validate_nested_source_coverage(item, path, errors)
        require_money_or_percent_sources(item.get("estimated_impact"), item, path, errors)

        validation_required = item.get("validation_required")
        if not isinstance(validation_required, list) or not validation_required:
            errors.append(f"{path}.validation_required must be a non-empty list")
        elif not all_non_empty_strings(validation_required):
            errors.append(f"{path}.validation_required must contain only non-empty strings")

        parse_date_field(item.get("target_decision_date"), f"{path}.target_decision_date", errors)
        exit_criteria = item.get("pilot_exit_criteria")
        if not isinstance(exit_criteria, list) or not exit_criteria:
            errors.append(f"{path}.pilot_exit_criteria must be a non-empty list")
        elif not all_non_empty_strings(exit_criteria):
            errors.append(f"{path}.pilot_exit_criteria must contain only non-empty strings")

        for capability_id in item.get("capability_ids", []):
            if availability_by_id.get(capability_id) == "requires-confirmation":
                validation_text = " ".join(validation_required or []).lower()
                if "deployment" not in validation_text and "availability" not in validation_text:
                    errors.append(
                        f"{path}.validation_required must call out deployment availability "
                        f"for {capability_id}"
                    )


def validate_executive_close(
    value: Any,
    source_ids: set[str],
    cards_value: Any,
    errors: list[str],
) -> None:
    path = "executive_close"
    item = expect_dict(value, path, errors)
    require_fields(item, REQUIRED_EXECUTIVE_CLOSE, path, errors)
    validate_source_refs(item.get("source_ids"), source_ids, f"{path}.source_ids", errors)
    require_money_or_percent_sources(
        item.get("portfolio_value_range"), item, f"{path}.portfolio_value_range", errors
    )
    parse_date_field(item.get("decision_date"), f"{path}.decision_date", errors)

    next_steps = expect_list(item.get("next_steps"), f"{path}.next_steps", errors)
    if not next_steps:
        errors.append(f"{path}.next_steps must include at least one owned action")
    for index, raw_step in enumerate(next_steps, start=1):
        step_path = f"{path}.next_steps[{index}]"
        step = expect_dict(raw_step, step_path, errors)
        require_fields(step, REQUIRED_NEXT_STEP, step_path, errors)
        parse_date_field(step.get("due_date"), f"{step_path}.due_date", errors)

    cards = cards_value if isinstance(cards_value, list) else []
    card_ranges = [
        parse_money_range(card.get("estimated_impact"))
        for card in cards
        if isinstance(card, dict)
    ]
    close_range = parse_money_range(item.get("portfolio_value_range"))
    if close_range and close_range[0] > close_range[1]:
        errors.append(f"{path}.portfolio_value_range lower bound must not exceed upper bound")
    if len(cards) == 1 and card_ranges and card_ranges[0] and close_range != card_ranges[0]:
        errors.append(
            f"{path}.portfolio_value_range must exactly match the single proposal-card range"
        )
    if len(cards) > 1:
        validate_portfolio_math(
            item.get("portfolio_math"),
            cards,
            card_ranges,
            item.get("portfolio_value_range"),
            close_range,
            errors,
        )


def parse_money_range(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, str):
        return None
    amounts: list[float] = []
    multipliers = {
        None: 1,
        "": 1,
        "k": 1_000,
        "thousand": 1_000,
        "m": 1_000_000,
        "million": 1_000_000,
        "b": 1_000_000_000,
        "bn": 1_000_000_000,
        "billion": 1_000_000_000,
    }
    for match in MONEY_AMOUNT_RE.finditer(value):
        number = float(match.group(1).replace(",", ""))
        amounts.append(number * multipliers[(match.group(2) or "").casefold()])
    if not amounts:
        return None
    if len(amounts) == 1:
        return (amounts[0], amounts[0])
    return (amounts[0], amounts[1])


def validate_portfolio_math(
    value: Any,
    cards: list[Any],
    card_ranges: list[tuple[float, float] | None],
    displayed_range: Any,
    close_range: tuple[float, float] | None,
    errors: list[str],
) -> None:
    path = "executive_close.portfolio_math"
    item = expect_dict(value, path, errors)
    require_fields(item, REQUIRED_PORTFOLIO_MATH, path, errors)

    expected_ranks = [
        card.get("rank") for card in cards if isinstance(card, dict) and isinstance(card.get("rank"), int)
    ]
    included_ranks = item.get("included_card_ranks")
    if included_ranks != expected_ranks:
        errors.append(f"{path}.included_card_ranks must include every proposal-card rank in order")

    factors: list[float | None] = []
    for field in ("lower_adjustment_factor", "upper_adjustment_factor"):
        factor = item.get(field)
        if (
            isinstance(factor, bool)
            or not isinstance(factor, (int, float))
            or not 0 < float(factor) <= 1
        ):
            errors.append(f"{path}.{field} must be a number greater than 0 and at most 1")
            factors.append(None)
        else:
            factors.append(float(factor))
    if all(factor is not None for factor in factors) and factors[0] > factors[1]:
        errors.append(f"{path}.lower_adjustment_factor must not exceed upper_adjustment_factor")

    resulting_range = item.get("resulting_range")
    if normalize_claim_text(resulting_range) != normalize_claim_text(displayed_range):
        errors.append(f"{path}.resulting_range must match executive_close.portfolio_value_range")
    if not all(card_range is not None for card_range in card_ranges):
        errors.append(
            f"{path} requires parseable dollar ranges on every included proposal card"
        )
        return
    if close_range is None or not all(factor is not None for factor in factors):
        return
    expected_lower = round(sum(card_range[0] for card_range in card_ranges) * factors[0], 2)
    expected_upper = round(sum(card_range[1] for card_range in card_ranges) * factors[1], 2)
    if not (
        abs(close_range[0] - expected_lower) <= 0.01
        and abs(close_range[1] - expected_upper) <= 0.01
    ):
        errors.append(
            f"{path}.resulting_range does not match recomputed aggregate "
            f"{expected_lower:.2f}-{expected_upper:.2f}"
        )


def validate_evidence_gaps(value: Any, cards_value: Any, errors: list[str]) -> None:
    gaps = expect_list(value, "evidence_gaps", errors)
    card_count = len(cards_value) if isinstance(cards_value, list) else 0
    if card_count < 10 and not gaps:
        errors.append(
            "evidence_gaps must explain why fewer than 10 proposal cards were produced"
        )

    for index, gap in enumerate(gaps, start=1):
        path = f"evidence_gaps[{index}]"
        item = expect_dict(gap, path, errors)
        require_fields(item, REQUIRED_EVIDENCE_GAP, path, errors)


def validate_assumptions(value: Any, errors: list[str]) -> None:
    assumptions = expect_list(value, "assumptions", errors)
    if not assumptions:
        errors.append("assumptions must include at least one validation or planning assumption")
    elif not all_non_empty_strings(assumptions):
        errors.append("assumptions must contain only non-empty strings")


def validate_impact_math(
    value: Any,
    source_ids: set[str],
    path: str,
    errors: list[str],
) -> None:
    impact_math = expect_dict(value, path, errors)
    require_fields(impact_math, REQUIRED_IMPACT_MATH, path, errors)
    validate_source_refs(impact_math.get("source_ids"), source_ids, f"{path}.source_ids", errors)
    for field in REQUIRED_IMPACT_MATH[:-1]:
        require_money_or_percent_sources(impact_math.get(field), impact_math, f"{path}.{field}", errors)
    parsed_range = parse_money_range(impact_math.get("resulting_range"))
    if parsed_range and parsed_range[0] > parsed_range[1]:
        errors.append(f"{path}.resulting_range lower bound must not exceed upper bound")


def validate_impact_alignment(
    displayed_value: Any,
    impact_math_value: Any,
    path: str,
    errors: list[str],
) -> None:
    if not isinstance(displayed_value, str) or not isinstance(impact_math_value, dict):
        return
    resulting_range = impact_math_value.get("resulting_range")
    if not isinstance(resulting_range, str):
        return
    if normalize_claim_text(displayed_value) != normalize_claim_text(resulting_range):
        errors.append(
            f"{path} displayed impact must exactly match impact_math.resulting_range"
        )


def validate_nested_source_coverage(
    item: dict[str, Any],
    path: str,
    errors: list[str],
) -> None:
    item_refs = set(item.get("source_ids") or [])
    impact_math = item.get("impact_math")
    nested_refs = set(impact_math.get("source_ids") or []) if isinstance(impact_math, dict) else set()
    missing = sorted(nested_refs - item_refs)
    if missing:
        errors.append(
            f"{path}.source_ids must include every impact_math source ID: {', '.join(missing)}"
        )


def render_markdown(contract: dict[str, Any]) -> str:
    errors = validate_contract(contract)
    if errors:
        raise ValueError("\n".join(errors))
    canonical = canonicalize_contract(contract)
    scope = canonical["confirmed_scope"]
    classification = canonical["classification"]
    sources = canonical["source_ledger"]
    capabilities = canonical["capability_ledger"]
    areas = canonical["budget_program_areas"]
    use_cases = canonical["prioritized_use_cases"]
    cards = canonical["proposal_cards"]
    executive_close = canonical["executive_close"]
    gaps = canonical["evidence_gaps"]
    assumptions = canonical["assumptions"]

    capability_names = {
        capability["capability_id"]: capability["capability_name"]
        for capability in capabilities
    }

    lines: list[str] = [
        f"# {scope['organization']} GTM Proposal",
        "",
        f"Contract version: `{canonical['contract_version']}`",
        f"Data classification: {classification['data_classification']}",
        f"Retention: {classification['retention']}",
        "",
        "## Confirmed Scope",
        "",
        f"- Organization: {scope['organization']}",
        f"- Target entity: {scope['target_entity']}",
        f"- Industry vertical: {scope['industry_vertical']}",
        f"- UiPath deployment type: {scope['uipath_deployment_type']}",
        f"- Research scope: {scope['research_scope']}",
        f"- Accessed date: {scope['accessed_date']}",
        "",
        "## Source Ledger",
        "",
        "| Source ID | Title | Publisher | Date/FY | URL | Accessed | Facts Supported |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]

    for source in sources:
        lines.append(
            "| "
            + " | ".join(
                markdown_cell(value)
                for value in (
                    f"[{source['source_id']}]",
                    source["title"],
                    source["publisher"],
                    source["publication_date"],
                    source["url"],
                    source["accessed_date"],
                    "; ".join(source["facts_supported"]),
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Capability Ledger",
            "",
            "| Capability ID | Capability | Deployment | Availability | Docs Checked | Docs URL | Sources |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for capability in capabilities:
        lines.append(
            "| "
            + " | ".join(
                markdown_cell(value)
                for value in (
                    capability["capability_id"],
                    capability["capability_name"],
                    capability["deployment_type"],
                    capability["availability"],
                    capability["docs_checked_date"],
                    capability["docs_url"],
                    format_source_ids(capability["source_ids"]),
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Budget / Program Areas",
            "",
            "| Rank | Program / Area | Budget | Budget Basis | Admin Cost | Admin Tier | Admin Math | Sources |",
            "| ---: | --- | ---: | --- | ---: | --- | --- | --- |",
        ]
    )
    for area in areas:
        admin_cost = area["admin_cost"]
        lines.append(
            "| "
            + " | ".join(
                markdown_cell(value)
                for value in (
                    str(area["rank"]),
                    area["program_area"],
                    area["budget"],
                    area["budget_basis"],
                    admin_cost["estimate"],
                    admin_cost["tier"],
                    admin_cost["math"],
                    format_source_ids(area["source_ids"]),
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Prioritized Use Cases",
            "",
            "| Rank | Use Case | Target Program / Area | Evidence-Based Driver | UiPath Capability Fit | Estimated Impact Range | Confidence | Estimate Tier | Sources |",
            "| ---: | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for use_case in use_cases:
        lines.append(
            "| "
            + " | ".join(
                markdown_cell(value)
                for value in (
                    str(use_case["rank"]),
                    use_case["use_case"],
                    use_case["target_program_area"],
                    use_case["driver"],
                    format_capability_names(use_case["capability_ids"], capability_names),
                    use_case["impact_range"],
                    use_case["confidence"],
                    use_case["estimate_tier"],
                    format_source_ids(use_case["source_ids"]),
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Executive Close",
            "",
            f"- Decision ask: {executive_close['decision_ask']}",
            f"- Portfolio value range: {executive_close['portfolio_value_range']}",
            f"- Aggregation method: {executive_close['aggregation_method']}",
            f"- Double-counting caveat: {executive_close['double_counting_caveat']}",
            f"- Executive owner: {executive_close['executive_owner']}",
            f"- Decision date: {executive_close['decision_date']}",
            f"- Sources: {format_source_ids(executive_close['source_ids'])}",
        ]
    )
    portfolio_math = executive_close.get("portfolio_math")
    if isinstance(portfolio_math, dict):
        lines.extend(
            [
                f"- Included card ranks: {', '.join(str(rank) for rank in portfolio_math['included_card_ranks'])}",
                f"- Aggregate adjustment factors: {portfolio_math['lower_adjustment_factor']}-"
                f"{portfolio_math['upper_adjustment_factor']}",
            ]
        )
    lines.extend(["", "### Owned Next Steps", ""])
    for index, step in enumerate(executive_close["next_steps"], start=1):
        lines.append(
            f"{index}. {step['owner']}: {step['action']} (due {step['due_date']})"
        )

    lines.extend(["", "## Proposal Cards", ""])
    for card in cards:
        impact_math = card["impact_math"]
        lines.extend(
            [
                f"### {card['rank']}. {card['use_case']}",
                "",
                f"**Business Challenge**: {card['business_challenge']}",
                "",
                f"**Proposed Solution**: {card['proposed_solution']}",
                "",
                "**Relevant UiPath Capabilities**: "
                + format_capability_names(card["capability_ids"], capability_names),
                "",
                f"**Estimated Impact**: {card['estimated_impact']}",
                "",
                "**Impact Math**: "
                f"Baseline: {impact_math['baseline']}; "
                f"Addressable share: {impact_math['addressable_share']}; "
                "Productivity/cost assumption: "
                f"{impact_math['productivity_or_cost_assumption']}; "
                f"Resulting range: {impact_math['resulting_range']}.",
                "",
                f"**Estimate Tier**: {card['estimate_tier']}",
                f"**Confidence**: {card['confidence']}",
                f"**Sources**: {format_source_ids(card['source_ids'])}",
                f"**Pilot Owner**: {card['pilot_owner']}",
                f"**Target Decision Date**: {card['target_decision_date']}",
                "",
                "**Validation Required**:",
                *[f"- {item}" for item in card["validation_required"]],
                "",
                "**Pilot Exit Criteria**:",
                *[f"- {item}" for item in card["pilot_exit_criteria"]],
                "",
            ]
        )

    lines.extend(["## Evidence Gaps", ""])
    for gap in gaps:
        lines.append(
            f"- {gap['gap']} Impact: {gap['impact']} Resolution: {gap['resolution_path']}"
        )

    lines.extend(["", "## Assumptions and Validation Needed", ""])
    for assumption in assumptions:
        lines.append(f"- {assumption}")

    return "\n".join(lines).rstrip() + "\n"


def canonicalize_contract(contract: dict[str, Any]) -> dict[str, Any]:
    canonical = copy.deepcopy(contract)
    canonical["source_ledger"] = sorted(
        canonical["source_ledger"], key=lambda item: numeric_suffix(item["source_id"])
    )
    canonical["capability_ledger"] = sorted(
        canonical["capability_ledger"], key=lambda item: numeric_suffix(item["capability_id"])
    )
    for key in ("budget_program_areas", "prioritized_use_cases", "proposal_cards"):
        canonical[key] = sorted(canonical[key], key=lambda item: item["rank"])
    return canonical


def require_fields(
    value: dict[str, Any],
    fields: tuple[str, ...],
    path: str,
    errors: list[str],
) -> None:
    for field in fields:
        if field not in value:
            errors.append(f"{path}.{field} is required")
        elif value[field] in ("", None, []):
            errors.append(f"{path}.{field} must not be empty")


def expect_dict(value: Any, path: str, errors: list[str]) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    errors.append(f"{path} must be an object")
    return {}


def expect_list(value: Any, path: str, errors: list[str]) -> list[Any]:
    if isinstance(value, list):
        return value
    errors.append(f"{path} must be a list")
    return []


def valid_id(value: Any, pattern: re.Pattern[str]) -> bool:
    return isinstance(value, str) and bool(pattern.match(value))


def validate_source_refs(
    refs: Any,
    source_ids: set[str],
    path: str,
    errors: list[str],
) -> None:
    if not isinstance(refs, list) or not refs:
        errors.append(f"{path} must be a non-empty list of source IDs")
        return
    for ref in refs:
        if ref not in source_ids:
            errors.append(f"{path} references undefined source ID: {ref}")


def validate_capability_refs(
    refs: Any,
    capability_ids: set[str],
    path: str,
    errors: list[str],
) -> None:
    if not isinstance(refs, list) or not refs:
        errors.append(f"{path} must be a non-empty list of capability IDs")
        return
    for ref in refs:
        if ref not in capability_ids:
            errors.append(f"{path} references undefined capability ID: {ref}")


def validate_estimate_tier(value: Any, path: str, errors: list[str]) -> None:
    if value not in ESTIMATE_TIERS:
        errors.append(f"{path} must be one of " + ", ".join(sorted(ESTIMATE_TIERS)))


def validate_confidence(value: Any, path: str, errors: list[str]) -> None:
    if value not in CONFIDENCE_LEVELS:
        errors.append(f"{path} must be High, Medium, or Low")


def validate_rank_sequence(items: list[Any], path: str, errors: list[str]) -> None:
    ranks = [item.get("rank") for item in items if isinstance(item, dict)]
    expected = list(range(1, len(items) + 1))
    if ranks != expected:
        errors.append(f"{path}.rank values must be consecutive starting at 1")


def validate_unsafe_claims(value: Any, errors: list[str]) -> None:
    for path, text in iter_strings(value):
        lowered = text.lower()
        for phrase in UNSAFE_CLAIMS:
            if phrase in lowered:
                errors.append(f"{path} contains unsupported overclaim phrase: {phrase}")


def require_money_or_percent_sources(
    value: Any,
    container: dict[str, Any],
    path: str,
    errors: list[str],
) -> None:
    if isinstance(value, str) and MONEY_OR_PERCENT_RE.search(value):
        refs = container.get("source_ids")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{path} contains money or percent values without source_ids")


def parse_date_field(value: Any, path: str, errors: list[str]) -> date | None:
    if not isinstance(value, str):
        errors.append(f"{path} must be an ISO date like 2026-07-10")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{path} must be an ISO date like 2026-07-10")
        return None


def contains_forbidden_confidential_marker(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.lower()
    return "confidential" in lowered or "internal-only" in lowered


def all_non_empty_strings(values: list[Any]) -> bool:
    return all(isinstance(value, str) and value.strip() for value in values)


def iter_strings(value: Any, path: str = "contract"):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from iter_strings(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value, start=1):
            yield from iter_strings(child, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


def numeric_suffix(value: str) -> int:
    return int(re.sub(r"^[A-Z]+", "", value))


def markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def normalize_claim_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().rstrip(".").casefold()


def format_source_ids(source_ids: list[str]) -> str:
    return ", ".join(f"[{source_id}]" for source_id in source_ids)


def format_capability_names(capability_ids: list[str], capability_names: dict[str, str]) -> str:
    return ", ".join(f"{capability_names[capability_id]} ({capability_id})" for capability_id in capability_ids)


def load_contract(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".md", ".markdown"}:
        return None, [MIGRATION_GUIDANCE]
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, [f"{path}: invalid JSON: {exc}"]
    if not isinstance(value, dict):
        return None, ["contract must be a JSON object"]
    return value, []


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path, help="Canonical proposal JSON contract")
    parser.add_argument(
        "--render",
        type=Path,
        help="Write deterministic Markdown after validation",
    )
    parser.add_argument(
        "--print-rendered",
        action="store_true",
        help="Print deterministic Markdown to stdout after validation",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    contract, load_errors = load_contract(args.contract)
    errors = load_errors or validate_contract(contract)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1

    assert contract is not None
    rendered = None
    if args.render or args.print_rendered:
        rendered = render_markdown(contract)
    if args.render:
        args.render.write_text(rendered, encoding="utf-8")
    if args.print_rendered:
        print(rendered, end="")
    if not args.print_rendered:
        if args.render:
            print(f"GTM proposal contract validated and rendered to {args.render}.")
        else:
            print("GTM proposal contract validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
