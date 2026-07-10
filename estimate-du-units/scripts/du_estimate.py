#!/usr/bin/env python3
"""Calculate provenance-aware UiPath Document Understanding estimates.

The calculator is intentionally read-only: it reads local JSON or CLI values and
writes the estimate to stdout. Rates are never inferred or defaulted.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import urlparse


RATE_PROFILE_VERSION = "estimate-du-units.rate-profile.v1"
INPUT_VERSION = "estimate-du-units.input.v1"
OUTPUT_VERSION = "estimate-du-units.output.v1"
EXPLICIT_RATE_MAX_AGE_DAYS = 30
UNIT_ORDER = ("ai_unit", "platform_unit")
UNIT_LABELS = {
    "ai_unit": "AI Units",
    "platform_unit": "Platform Units",
}
NONNEGATIVE_DECIMAL_RE = re.compile(r"^(0|[1-9][0-9]*)(\.[0-9]+)?$")
CLI_DECIMAL_RE = re.compile(
    r"^[+-]?(?:(?:[0-9]+)|(?:[0-9]{1,3}(?:,[0-9]{3})+))(?:\.[0-9]+)?$"
)


class ContractError(ValueError):
    """Raised when a versioned input or rate contract is unsafe to use."""


class RateComponent(NamedTuple):
    name: str
    unit: str
    rate: Decimal
    source_url: str | None
    accessed_on: date
    effective_on: date | None
    max_age_days: int


class DocumentInput(NamedTuple):
    name: str
    annual_transactions: Decimal
    pages_per_transaction: Decimal


class ScenarioInput(NamedTuple):
    name: str
    documents: tuple[DocumentInput, ...]


class EstimateInput(NamedTuple):
    estimate_id: str
    as_of: date
    applicability: str
    rationale: str
    scenarios: tuple[ScenarioInput, ...]
    input_mode: str


def decimal_arg(value: str) -> Decimal:
    if not CLI_DECIMAL_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(f"invalid decimal: {value}")
    try:
        parsed = Decimal(value.replace(",", ""))
    except (InvalidOperation, ValueError) as exc:
        raise argparse.ArgumentTypeError(f"invalid decimal: {value}") from exc
    if not parsed.is_finite():
        raise argparse.ArgumentTypeError(f"decimal must be finite: {value}")
    return parsed


def nonnegative_decimal_arg(value: str) -> Decimal:
    parsed = decimal_arg(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError(f"value cannot be negative: {value}")
    return parsed


def nonnegative_int_arg(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid integer: {value}") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError(f"value cannot be negative: {value}")
    return parsed


def iso_date_arg(value: str) -> date:
    try:
        return parse_iso_date(value, "date")
    except ContractError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def parse_case(value: str) -> tuple[str, Decimal, Decimal]:
    """Parse the preserved legacy label=transactions,pages syntax."""
    try:
        label, rest = value.split("=", 1)
        transactions, pages = rest.rsplit(",", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "case must be label=transactions,pages, for example base=197518,1"
        ) from exc

    label = label.strip()
    if not label:
        raise argparse.ArgumentTypeError("case label cannot be empty")

    transactions_value = nonnegative_decimal_arg(transactions.strip())
    pages_value = nonnegative_decimal_arg(pages.strip())
    return label, transactions_value, pages_value


def fmt(value: Decimal, places: str = "0.1") -> str:
    """Retain the legacy one-decimal display helper for callers importing it."""
    quantized = value.quantize(Decimal(places), rounding=ROUND_HALF_UP)
    if quantized == quantized.to_integral():
        return f"{int(quantized):,}"
    return f"{quantized:,.1f}"


def decimal_text(value: Decimal) -> str:
    """Return a non-scientific, lossless JSON decimal string."""
    if value == 0:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def rounded_text(value: Decimal) -> str:
    return decimal_text(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def markdown_number(value: str) -> str:
    parsed = Decimal(value)
    canonical = decimal_text(parsed)
    sign = ""
    if canonical.startswith("-"):
        sign, canonical = "-", canonical[1:]
    whole, separator, fraction = canonical.partition(".")
    first_group_length = len(whole) % 3 or 3
    groups = [whole[:first_group_length]]
    groups.extend(
        whole[index : index + 3]
        for index in range(first_group_length, len(whole), 3)
    )
    grouped = ",".join(groups)
    return f"{sign}{grouped}{separator}{fraction}"


def markdown_escape(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def parse_iso_date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise ContractError(f"{field} must be an ISO date string (YYYY-MM-DD)")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError(f"{field} must be an ISO date string (YYYY-MM-DD)") from exc
    if parsed.isoformat() != value:
        raise ContractError(f"{field} must be an ISO date string (YYYY-MM-DD)")
    return parsed


def contract_decimal(value: object, field: str) -> Decimal:
    if not isinstance(value, str) or not NONNEGATIVE_DECIMAL_RE.fullmatch(value):
        raise ContractError(f"{field} must be a non-negative canonical decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ContractError(f"{field} must be a decimal string") from exc
    if not parsed.is_finite():
        raise ContractError(f"{field} must be finite")
    if parsed < 0:
        raise ContractError(f"{field} cannot be negative")
    return parsed


def require_nonempty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    return value.strip()


def require_object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{field} must be a JSON object")
    return value


def require_list(value: object, field: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise ContractError(f"{field} must be a non-empty JSON array")
    return value


def validate_keys(
    value: dict[str, Any],
    required: set[str],
    optional: set[str],
    field: str,
) -> None:
    missing = sorted(required - value.keys())
    unknown = sorted(value.keys() - required - optional)
    if missing:
        raise ContractError(f"{field} is missing required field(s): {', '.join(missing)}")
    if unknown:
        raise ContractError(f"{field} has unsupported field(s): {', '.join(unknown)}")


def unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ContractError(f"JSON contains duplicate object key: {key}")
        value[key] = item
    return value


def reject_json_constant(value: str) -> None:
    raise ContractError(f"JSON contains unsupported numeric constant: {value}")


def load_json_object(path: Path, contract_name: str) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(
                handle,
                object_pairs_hook=unique_json_object,
                parse_constant=reject_json_constant,
            )
    except OSError as exc:
        raise ContractError(f"cannot read {contract_name} {path}: {exc}") from exc
    except UnicodeError as exc:
        raise ContractError(f"cannot decode {contract_name} {path} as UTF-8") from exc
    except RecursionError as exc:
        raise ContractError(f"{contract_name} {path} exceeds the JSON nesting limit") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(
            f"invalid JSON in {contract_name} {path}: line {exc.lineno}, column {exc.colno}"
        ) from exc
    return require_object(payload, contract_name)


def parse_input_contract(payload: dict[str, Any]) -> EstimateInput:
    validate_keys(
        payload,
        {"schema_version", "estimate_id", "as_of", "applicability", "scenarios"},
        set(),
        "input",
    )
    if payload["schema_version"] != INPUT_VERSION:
        raise ContractError(
            f"input.schema_version must be {INPUT_VERSION!r}; migrate the input before retrying"
        )

    estimate_id = require_nonempty_string(payload["estimate_id"], "input.estimate_id")
    as_of = parse_iso_date(payload["as_of"], "input.as_of")

    applicability = require_object(payload["applicability"], "input.applicability")
    validate_keys(applicability, {"status", "rationale"}, set(), "input.applicability")
    status = applicability["status"]
    if not isinstance(status, str) or status not in {"yes", "no", "conditional"}:
        raise ContractError("input.applicability.status must be yes, no, or conditional")
    rationale = require_nonempty_string(
        applicability["rationale"], "input.applicability.rationale"
    )

    scenarios_payload = require_list(payload["scenarios"], "input.scenarios")
    scenarios: list[ScenarioInput] = []
    scenario_names: set[str] = set()
    for scenario_index, raw_scenario in enumerate(scenarios_payload):
        scenario_field = f"input.scenarios[{scenario_index}]"
        scenario = require_object(raw_scenario, scenario_field)
        validate_keys(scenario, {"name", "documents"}, set(), scenario_field)
        name = require_nonempty_string(scenario["name"], f"{scenario_field}.name")
        if name in scenario_names:
            raise ContractError(f"input.scenarios contains duplicate name: {name}")
        scenario_names.add(name)

        documents_payload = require_list(
            scenario["documents"], f"{scenario_field}.documents"
        )
        documents: list[DocumentInput] = []
        document_names: set[str] = set()
        for document_index, raw_document in enumerate(documents_payload):
            document_field = f"{scenario_field}.documents[{document_index}]"
            document = require_object(raw_document, document_field)
            validate_keys(
                document,
                {"name", "annual_transactions", "pages_per_transaction"},
                set(),
                document_field,
            )
            document_name = require_nonempty_string(
                document["name"], f"{document_field}.name"
            )
            if document_name in document_names:
                raise ContractError(
                    f"{scenario_field}.documents contains duplicate name: {document_name}"
                )
            document_names.add(document_name)
            documents.append(
                DocumentInput(
                    document_name,
                    contract_decimal(
                        document["annual_transactions"],
                        f"{document_field}.annual_transactions",
                    ),
                    contract_decimal(
                        document["pages_per_transaction"],
                        f"{document_field}.pages_per_transaction",
                    ),
                )
            )
        scenarios.append(ScenarioInput(name, tuple(documents)))

    return EstimateInput(
        estimate_id,
        as_of,
        status,
        rationale,
        tuple(scenarios),
        "structured",
    )


def parse_rate_profile(
    payload: dict[str, Any],
) -> tuple[str, tuple[RateComponent, ...]]:
    validate_keys(payload, {"schema_version", "profile_id", "rates"}, set(), "rate profile")
    if payload["schema_version"] != RATE_PROFILE_VERSION:
        raise ContractError(
            "rate profile.schema_version must be "
            f"{RATE_PROFILE_VERSION!r}; migrate the profile before retrying"
        )
    profile_id = require_nonempty_string(payload["profile_id"], "rate profile.profile_id")
    rates_payload = require_list(payload["rates"], "rate profile.rates")

    components: list[RateComponent] = []
    names: set[str] = set()
    required = {
        "name",
        "unit",
        "rate",
        "source_url",
        "accessed_on",
        "effective_on",
        "max_age_days",
    }
    for index, raw_rate in enumerate(rates_payload):
        field = f"rate profile.rates[{index}]"
        rate = require_object(raw_rate, field)
        validate_keys(rate, required, set(), field)
        name = require_nonempty_string(rate["name"], f"{field}.name")
        if name in names:
            raise ContractError(f"rate profile.rates contains duplicate name: {name}")
        names.add(name)
        unit = rate["unit"]
        if unit not in UNIT_ORDER:
            raise ContractError(f"{field}.unit must be ai_unit or platform_unit")
        source_url = require_nonempty_string(rate["source_url"], f"{field}.source_url")
        parsed_url = urlparse(source_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ContractError(f"{field}.source_url must be an absolute HTTP(S) URL")
        max_age_days = rate["max_age_days"]
        if isinstance(max_age_days, bool) or not isinstance(max_age_days, int):
            raise ContractError(f"{field}.max_age_days must be a non-negative integer")
        if max_age_days < 0:
            raise ContractError(f"{field}.max_age_days must be a non-negative integer")
        components.append(
            RateComponent(
                name,
                unit,
                contract_decimal(rate["rate"], f"{field}.rate"),
                source_url,
                parse_iso_date(rate["accessed_on"], f"{field}.accessed_on"),
                parse_iso_date(rate["effective_on"], f"{field}.effective_on"),
                max_age_days,
            )
        )
    return profile_id, tuple(components)


def legacy_estimate_input(args: argparse.Namespace) -> EstimateInput:
    if not args.applicability or not args.rationale or not args.rationale.strip():
        raise ContractError(
            "legacy --case requires --applicability yes|no|conditional and a non-empty "
            "--rationale; migrate to --input for the versioned structured contract"
        )
    names: set[str] = set()
    scenarios: list[ScenarioInput] = []
    for label, transactions, pages in args.case:
        if label in names:
            raise ContractError(f"legacy --case contains duplicate label: {label}")
        names.add(label)
        scenarios.append(
            ScenarioInput(
                label,
                (DocumentInput("legacy-case", transactions, pages),),
            )
        )
    return EstimateInput(
        "legacy-cli",
        args.as_of or date.today(),
        args.applicability,
        args.rationale.strip(),
        tuple(scenarios),
        "legacy_case",
    )


def explicit_rate_components(args: argparse.Namespace) -> tuple[RateComponent, ...]:
    if args.extra_ai_rate and args.ai_rate is None:
        raise ContractError("--extra-ai-rate requires an explicit --ai-rate")
    if args.extra_platform_rate and args.platform_rate is None:
        raise ContractError("--extra-platform-rate requires an explicit --platform-rate")
    if args.ai_rate is None and args.platform_rate is None:
        raise ContractError(
            "no rates supplied. Migration: pass --rate-profile PROFILE.json, or pass "
            "--ai-rate and/or --platform-rate with --verified-on YYYY-MM-DD"
        )
    if args.verified_on is None:
        raise ContractError(
            "explicit rates require --verified-on YYYY-MM-DD; rates without a verification "
            "date are rejected"
        )

    max_age_days = (
        args.max_rate_age_days
        if args.max_rate_age_days is not None
        else EXPLICIT_RATE_MAX_AGE_DAYS
    )
    components: list[RateComponent] = []
    for unit, base_rate, extras in (
        ("ai_unit", args.ai_rate, args.extra_ai_rate or []),
        ("platform_unit", args.platform_rate, args.extra_platform_rate or []),
    ):
        if base_rate is None:
            continue
        short_name = "ai" if unit == "ai_unit" else "platform"
        components.append(
            RateComponent(
                f"explicit-{short_name}-base",
                unit,
                base_rate,
                None,
                args.verified_on,
                None,
                max_age_days,
            )
        )
        for index, extra_rate in enumerate(extras, start=1):
            components.append(
                RateComponent(
                    f"explicit-{short_name}-add-on-{index}",
                    unit,
                    extra_rate,
                    None,
                    args.verified_on,
                    None,
                    max_age_days,
                )
            )
    return tuple(components)


def validate_rate_dates(
    components: tuple[RateComponent, ...],
    as_of: date,
    allow_stale: bool,
) -> tuple[set[str], list[str]]:
    stale_names: set[str] = set()
    for component in components:
        if component.accessed_on > as_of:
            raise ContractError(
                f"rate {component.name!r} was accessed after estimate as-of date {as_of.isoformat()}"
            )
        if component.effective_on is not None and component.effective_on > as_of:
            raise ContractError(
                f"rate {component.name!r} is not effective as of {as_of.isoformat()}"
            )
        age_days = (as_of - component.accessed_on).days
        if age_days > component.max_age_days:
            stale_names.add(component.name)

    if stale_names and not allow_stale:
        names = ", ".join(sorted(stale_names))
        raise ContractError(
            f"stale rate component(s) as of {as_of.isoformat()}: {names}. Refresh the "
            "source and accessed_on/--verified-on date, or use --allow-stale-rates to "
            "record an explicit override"
        )

    warnings: list[str] = []
    if stale_names:
        warnings.append(
            "Stale-rate override used for: " + ", ".join(sorted(stale_names)) + "."
        )
    return stale_names, warnings


def calculation_precision(
    estimate: EstimateInput,
    components: tuple[RateComponent, ...],
) -> int:
    decimal_values = [component.rate for component in components]
    for scenario in estimate.scenarios:
        for document in scenario.documents:
            decimal_values.extend(
                [document.annual_transactions, document.pages_per_transaction]
            )
    return max(28, 10 + sum(len(value.as_tuple().digits) for value in decimal_values))


def calculate_estimate(
    estimate: EstimateInput,
    components: tuple[RateComponent, ...],
    rate_mode: str,
    profile_id: str | None,
    allow_stale: bool,
) -> dict[str, Any]:
    with localcontext() as context:
        context.prec = calculation_precision(estimate, components)
        return calculate_estimate_with_context(
            estimate,
            components,
            rate_mode,
            profile_id,
            allow_stale,
        )


def calculate_estimate_with_context(
    estimate: EstimateInput,
    components: tuple[RateComponent, ...],
    rate_mode: str,
    profile_id: str | None,
    allow_stale: bool,
) -> dict[str, Any]:
    stale_names, warnings = validate_rate_dates(components, estimate.as_of, allow_stale)
    rate_totals: dict[str, Decimal] = {}
    for component in components:
        rate_totals[component.unit] = rate_totals.get(component.unit, Decimal("0")) + component.rate
    ordered_units = [unit for unit in UNIT_ORDER if unit in rate_totals]
    calculation_applied = estimate.applicability != "no"

    if estimate.applicability == "conditional":
        warnings.append(
            "Applicability is conditional; totals apply only when the stated condition is met."
        )
    elif not calculation_applied:
        warnings.append("Applicability is no; unit results are forced to zero.")

    scenario_results: list[dict[str, Any]] = []
    for scenario in estimate.scenarios:
        document_results: list[dict[str, Any]] = []
        scenario_pages = Decimal("0")
        scenario_units = {unit: Decimal("0") for unit in ordered_units}
        for document in scenario.documents:
            annual_pages = document.annual_transactions * document.pages_per_transaction
            scenario_pages += annual_pages
            document_units: dict[str, dict[str, str]] = {}
            for unit in ordered_units:
                exact = annual_pages * rate_totals[unit] if calculation_applied else Decimal("0")
                scenario_units[unit] += exact
                document_units[unit] = {
                    "exact": decimal_text(exact),
                    "rounded": rounded_text(exact),
                }
            document_results.append(
                {
                    "name": document.name,
                    "annual_transactions": decimal_text(document.annual_transactions),
                    "pages_per_transaction": decimal_text(document.pages_per_transaction),
                    "annual_pages": decimal_text(annual_pages),
                    "units": document_units,
                }
            )
        scenario_results.append(
            {
                "name": scenario.name,
                "documents": document_results,
                "totals": {
                    "annual_pages": decimal_text(scenario_pages),
                    "units": {
                        unit: {
                            "exact": decimal_text(scenario_units[unit]),
                            "rounded": rounded_text(scenario_units[unit]),
                        }
                        for unit in ordered_units
                    },
                },
            }
        )

    component_results = []
    for component in components:
        age_days = (estimate.as_of - component.accessed_on).days
        component_results.append(
            {
                "name": component.name,
                "unit": component.unit,
                "rate": decimal_text(component.rate),
                "source_url": component.source_url,
                "accessed_on": component.accessed_on.isoformat(),
                "effective_on": (
                    component.effective_on.isoformat()
                    if component.effective_on is not None
                    else None
                ),
                "max_age_days": component.max_age_days,
                "age_days": age_days,
                "is_stale": component.name in stale_names,
            }
        )

    return {
        "schema_version": OUTPUT_VERSION,
        "estimate_id": estimate.estimate_id,
        "input_mode": estimate.input_mode,
        "as_of": estimate.as_of.isoformat(),
        "applicability": {
            "status": estimate.applicability,
            "rationale": estimate.rationale,
        },
        "calculation_applied": calculation_applied,
        "rate_context": {
            "mode": rate_mode,
            "profile_id": profile_id,
            "stale_override_used": bool(stale_names),
            "components": component_results,
            "totals_per_page": {
                unit: decimal_text(rate_totals[unit]) for unit in ordered_units
            },
        },
        "scenarios": scenario_results,
        "warnings": warnings,
        "disclaimer": "Planning estimate only; not a quote or entitlement statement.",
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# DU Unit Estimate",
        "",
        f"- Output contract: `{payload['schema_version']}`",
        f"- Estimate ID: `{markdown_escape(payload['estimate_id'])}`",
        f"- As of: `{payload['as_of']}`",
        f"- Applicability: **{payload['applicability']['status']}**",
        f"- Rationale: {markdown_escape(payload['applicability']['rationale'])}",
        "",
        "## Rate Components",
        "",
        "| Name | Unit | Rate/page | Source | Accessed | Effective | Age/max days | Status |",
        "|---|---|---:|---|---|---|---:|---|",
    ]
    for component in payload["rate_context"]["components"]:
        source = component["source_url"] or "not recorded (explicit CLI mode)"
        effective = component["effective_on"] or "not recorded"
        status = "stale override" if component["is_stale"] else "current"
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_escape(component["name"]),
                    markdown_escape(UNIT_LABELS[component["unit"]]),
                    markdown_number(component["rate"]),
                    markdown_escape(source),
                    component["accessed_on"],
                    effective,
                    f"{component['age_days']}/{component['max_age_days']}",
                    status,
                ]
            )
            + " |"
        )

    lines.extend(["", "Additive totals per page:"])
    for unit, value in payload["rate_context"]["totals_per_page"].items():
        lines.append(f"- {UNIT_LABELS[unit]}: **{markdown_number(value)}**")

    units = list(payload["rate_context"]["totals_per_page"])
    detail_header = [
        "Scenario",
        "Document",
        "Transactions/year",
        "Pages/transaction",
        "Exact pages/year",
    ]
    for unit in units:
        detail_header.extend([f"{UNIT_LABELS[unit]} exact", f"{UNIT_LABELS[unit]} rounded"])
    lines.extend(
        [
            "",
            "## Document Results",
            "",
            "| " + " | ".join(detail_header) + " |",
            "|"
            + "|".join(["---", "---", "---:", "---:", "---:"] + ["---:"] * (2 * len(units)))
            + "|",
        ]
    )
    for scenario in payload["scenarios"]:
        for document in scenario["documents"]:
            cells = [
                markdown_escape(scenario["name"]),
                markdown_escape(document["name"]),
                markdown_number(document["annual_transactions"]),
                markdown_number(document["pages_per_transaction"]),
                markdown_number(document["annual_pages"]),
            ]
            for unit in units:
                cells.extend(
                    [
                        markdown_number(document["units"][unit]["exact"]),
                        markdown_number(document["units"][unit]["rounded"]),
                    ]
                )
            lines.append("| " + " | ".join(cells) + " |")

    total_header = ["Scenario", "Exact pages/year"]
    for unit in units:
        total_header.extend([f"{UNIT_LABELS[unit]} exact", f"{UNIT_LABELS[unit]} rounded"])
    lines.extend(
        [
            "",
            "## Aggregate Scenario Totals",
            "",
            "| " + " | ".join(total_header) + " |",
            "|" + "|".join(["---", "---:"] + ["---:"] * (2 * len(units))) + "|",
        ]
    )
    for scenario in payload["scenarios"]:
        cells = [
            markdown_escape(scenario["name"]),
            markdown_number(scenario["totals"]["annual_pages"]),
        ]
        for unit in units:
            cells.extend(
                [
                    markdown_number(scenario["totals"]["units"][unit]["exact"]),
                    markdown_number(scenario["totals"]["units"][unit]["rounded"]),
                ]
            )
        lines.append("| " + " | ".join(cells) + " |")

    if payload["warnings"]:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {markdown_escape(warning)}" for warning in payload["warnings"])
    lines.extend(["", f"_{payload['disclaimer']}_"])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Calculate annual DU consumption from versioned structured input or the "
            "explicit-rate legacy --case syntax."
        )
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input",
        type=Path,
        help=f"Structured JSON input using {INPUT_VERSION}.",
    )
    input_group.add_argument(
        "--case",
        action="append",
        type=parse_case,
        help=(
            "Legacy scenario as label=transactions,pages. Repeat as needed; explicit "
            "verified rates are mandatory."
        ),
    )
    parser.add_argument(
        "--rate-profile",
        type=Path,
        help=f"Versioned JSON rate profile using {RATE_PROFILE_VERSION}.",
    )
    parser.add_argument("--ai-rate", type=nonnegative_decimal_arg)
    parser.add_argument("--platform-rate", type=nonnegative_decimal_arg)
    parser.add_argument(
        "--extra-ai-rate",
        action="append",
        type=nonnegative_decimal_arg,
        help="Additive AI Units/page component; repeatable and requires --ai-rate.",
    )
    parser.add_argument(
        "--extra-platform-rate",
        action="append",
        type=nonnegative_decimal_arg,
        help="Additive Platform Units/page component; repeatable and requires --platform-rate.",
    )
    parser.add_argument(
        "--verified-on",
        type=iso_date_arg,
        help="Verification date required for explicit CLI rates.",
    )
    parser.add_argument(
        "--max-rate-age-days",
        type=nonnegative_int_arg,
        help=(
            "Freshness limit for explicit rates; defaults to "
            f"{EXPLICIT_RATE_MAX_AGE_DAYS} days and is ignored for profiles."
        ),
    )
    parser.add_argument(
        "--as-of",
        type=iso_date_arg,
        help="Override input as_of, or set legacy estimate date; defaults to today for legacy mode.",
    )
    parser.add_argument(
        "--allow-stale-rates",
        action="store_true",
        help="Acknowledge and record use of rate components older than their max age.",
    )
    parser.add_argument("--applicability", choices=("yes", "no", "conditional"))
    parser.add_argument("--rationale", help="Required applicability rationale in legacy mode.")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    explicit_requested = any(
        (
            args.ai_rate is not None,
            args.platform_rate is not None,
            bool(args.extra_ai_rate),
            bool(args.extra_platform_rate),
        )
    )

    try:
        if args.input:
            if args.applicability is not None or args.rationale is not None:
                raise ContractError(
                    "--applicability and --rationale belong inside the versioned --input JSON"
                )
            estimate = parse_input_contract(load_json_object(args.input, "input"))
            if args.as_of is not None:
                estimate = estimate._replace(as_of=args.as_of)
        else:
            if args.rate_profile is not None:
                raise ContractError(
                    "legacy --case accepts only explicit verified rates. Migrate to --input "
                    "for --rate-profile support, or pass --ai-rate and/or --platform-rate "
                    "with --verified-on"
                )
            estimate = legacy_estimate_input(args)

        if args.rate_profile is not None and explicit_requested:
            raise ContractError("choose --rate-profile or explicit rates, not both")
        if args.rate_profile is not None:
            if args.verified_on is not None or args.max_rate_age_days is not None:
                raise ContractError(
                    "--verified-on and --max-rate-age-days apply only to explicit rates; "
                    "a rate profile carries its own dates and max ages"
                )
            profile_id, components = parse_rate_profile(
                load_json_object(args.rate_profile, "rate profile")
            )
            rate_mode = "rate_profile"
        else:
            components = explicit_rate_components(args)
            profile_id = None
            rate_mode = "explicit_cli"

        payload = calculate_estimate(
            estimate,
            components,
            rate_mode,
            profile_id,
            args.allow_stale_rates,
        )
    except ContractError as exc:
        parser.error(str(exc))

    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=True))
    else:
        print(render_markdown(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
