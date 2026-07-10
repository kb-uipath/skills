#!/usr/bin/env python3
"""Render a validated v1 portfolio into deterministic executive Markdown."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from portfolio_contracts import (
    ContractLoadError,
    format_score,
    load_json_object,
    validate_portfolio,
)


DEPLOYMENT_LABELS = {
    "automation_cloud": "Automation Cloud",
    "automation_cloud_public_sector": "Automation Cloud Public Sector",
    "automation_suite": "Automation Suite",
    "on_premises": "On-premises",
    "hybrid": "Hybrid",
    "unknown": "Unknown deployment",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a validated evidence-backed portfolio as executive Markdown."
    )
    parser.add_argument("--evidence-ledger", required=True, type=Path)
    parser.add_argument("--portfolio", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--inventory-profile", type=Path, default=None)
    parser.add_argument("--force", action="store_true", help="Replace an existing Markdown output")
    return parser.parse_args()


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def cell(value: Any) -> str:
    return clean(value).replace("|", "\\|")


def sentence(value: Any) -> str:
    text = clean(value)
    if not text:
        return ""
    return text if text.endswith((".", "?", "!")) else text + "."


def join_items(values: Iterable[Any]) -> str:
    return "; ".join(clean(value) for value in values if clean(value))


def table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(cell(value) for value in row) + " |" for row in rows)
    return lines


def opportunity_index(portfolio: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["opportunity_id"]: item for item in portfolio["opportunities"]}


def evidence_label(opportunity: dict[str, Any], ledger: dict[str, Any]) -> str:
    inventory = {
        item["inventory_id"]: item for item in ledger["inventory_evidence"]
    }
    values = []
    for item_id in opportunity["evidence_refs"]["inventory_ids"]:
        item = inventory[item_id]
        values.append(f"{item_id} {item['name']} ({item['status']}, {item['department']})")
    return join_items(values)


def capability_label(opportunity: dict[str, Any]) -> str:
    values = []
    for item in opportunity["capability_fit"]:
        if item["claim"] == "confirmed_entitlement":
            claim = "confirmed entitlement"
        else:
            claim = "likely fit; entitlement not confirmed"
        values.append(f"{item['capability']} ({claim})")
    return join_items(values)


def value_label(value_case: dict[str, Any]) -> str:
    if value_case["method"] == "calculated":
        return (
            f"{value_case['label'].title()} planning estimate: "
            f"{value_case['currency']} {value_case['annual_value']:,.2f} annually and "
            f"{value_case['annual_hours']:,.2f} hours; {value_case['basis']}"
        )
    return f"{value_case['label'].title()}: {value_case['basis']}"


def render(ledger: dict[str, Any], portfolio: dict[str, Any]) -> str:
    customer = ledger["customer"]
    deployment = customer["deployment"]
    deployment_label = DEPLOYMENT_LABELS[deployment["model"]]
    inventory = ledger["inventory_evidence"]
    sources = ledger["public_sources"]
    assumptions = ledger["assumptions"]
    opportunities = opportunity_index(portfolio)
    high_ids = portfolio["rankings"]["high_impact"]
    poc_ids = portfolio["rankings"]["low_friction_poc"]
    primary = opportunities[high_ids[0]]
    status_counts = Counter(item["status"] for item in inventory)
    departments = sorted({item["department"] for item in inventory if item["department"]})
    systems = sorted({system for item in inventory for system in item["systems"]})
    constraints = deployment["constraints"] or ["No deployment constraints were supplied"]

    summary = (
        f"{customer['name']} has enough documented signal to make a bounded agentic expansion "
        f"decision, while the evidence gaps remain explicit. The portfolio uses {len(inventory)} "
        f"inventory record(s) and {len(sources)} dated public source(s); {primary['name']} ranks "
        f"first at {format_score(primary['scores']['high_impact'])} with "
        f"{primary['confidence']} confidence. {sentence(primary['decision_ask'])} The deployment "
        f"baseline is {deployment_label}, so every pilot must honor the listed controls and avoid "
        "assuming unconfirmed entitlements. The recommended next step is a focused evidence and "
        "pilot-boundary workshop before any implementation commitment."
    )

    lines = [
        f"# UiPath agentic expansion proposal for {customer['name']}",
        "",
        "## Executive Summary",
        "",
        summary,
        "",
        "## Source and Assumption Note",
        "",
        f"- Inventory source: `{ledger['inventory_profile']['source_name']}` as of "
        f"{ledger['inventory_profile']['as_of_date']}; IDs "
        f"{join_items(ledger['inventory_profile']['inventory_ids'])}.",
        f"- Public strategy sources: {len(sources)} dated source(s), accessed no later than "
        f"{portfolio['as_of_date']}.",
        f"- Data limitations: {len(assumptions)} explicit assumption(s); unvalidated assumptions "
        "remain validation requirements, not facts.",
        "- Value assumptions: calculated values use only versioned formula IDs; qualitative values "
        "are directional.",
        "",
        "## Current Automation Footprint",
        "",
    ]
    lines.extend(
        table(
            ["Dimension", "Finding", "Implication"],
            [
                [
                    "Status mix",
                    join_items(f"{key}: {value}" for key, value in sorted(status_counts.items())),
                    "Production is strongest evidence; excluded and unknown rows cannot imply scale.",
                ],
                [
                    "Departments",
                    join_items(departments) or "Not supplied",
                    "Named owners must validate pilot boundaries.",
                ],
                [
                    "Systems",
                    join_items(systems) or "Not supplied",
                    "Access and integration constraints remain part of pilot design.",
                ],
            ],
        )
    )
    lines.extend(["", "## Public Strategy Alignment", ""])
    lines.extend(
        table(
            ["Source ID", "Public priority", "Published", "Automation relevance"],
            [
                [source["source_id"], source["title"], source["published_date"], source["evidence_summary"]]
                for source in sources
            ],
        )
    )
    lines.extend(["", "## Prioritized Portfolio", ""])
    lines.extend(
        table(
            ["Rank", "Opportunity", "Category", "Score", "Confidence", "Why it matters"],
            [
                [
                    rank,
                    opportunities[item_id]["name"],
                    opportunities[item_id]["category"].replace("_", " ").title(),
                    format_score(opportunities[item_id]["scores"]["high_impact"]),
                    opportunities[item_id]["confidence"].title(),
                    opportunities[item_id]["why_now"],
                ]
                for rank, item_id in enumerate(high_ids, start=1)
            ],
        )
    )

    lines.extend(["", "## Top 5 High-Impact Recommendations", ""])
    for item_id in high_ids:
        item = opportunities[item_id]
        refs = item["evidence_refs"]
        lines.extend(
            [
                f"### {item['name']}",
                "",
                f"**Recommendation:** {sentence(item['business_problem'])} "
                f"Decision: {sentence(item['decision_ask'])}",
                "",
                f"**Why now:** {sentence(item['why_now'])} Public evidence: "
                f"{join_items(refs['public_source_ids'])}.",
                "",
                f"**Inventory evidence:** {evidence_label(item, ledger)}.",
                "",
                f"**Agentic enhancement:** {sentence(item['agentic_enhancement'])}",
                "",
                f"**UiPath capability fit:** {capability_label(item)}.",
                "",
                f"**Value levers:** {join_items(item['value_levers'])}. "
                f"{sentence(value_label(item['value_case']))}",
                "",
                f"**Feasibility:** {sentence(item['feasibility'])}",
                "",
                f"**Governance:** {sentence(item['governance'])} Deployment status: "
                f"{item['deployment']['status'].replace('_', ' ')}; controls: "
                f"{join_items(item['deployment']['controls'])}.",
                "",
                "**Validation questions:**",
                "",
            ]
        )
        lines.extend(f"- {question}" for question in item["validation_questions"])
        lines.append(
            f"- Has {deployment_label} capability availability and entitlement been validated?"
        )
        lines.extend(
            [
                "",
                f"**Evidence IDs:** Inventory {join_items(refs['inventory_ids'])}; public sources "
                f"{join_items(refs['public_source_ids'])}; assumptions "
                f"{join_items(refs['assumption_ids']) or 'none'}.",
                "",
            ]
        )

    lines.extend(["## Top 3 Low-Friction POC Candidates", ""])
    for item_id in poc_ids:
        item = opportunities[item_id]
        pilot = item["pilot"]
        lines.extend(
            [
                f"### {item['name']} POC",
                "",
                f"**Pilot objective:** {sentence(pilot['objective'])}",
                "",
                f"**Narrow scope:** {sentence(pilot['narrow_scope'])} Owner: {pilot['owner']}; "
                f"target window: {pilot['timeline_days']} days.",
                "",
                f"**Agent role:** {sentence(pilot['agent_role'])}",
                "",
                f"**Human role:** {sentence(pilot['human_role'])}",
                "",
                f"**Success metrics:** {join_items(pilot['success_metrics'])}.",
                "",
                f"**Data needed:** {join_items(pilot['data_needed'])}.",
                "",
                f"**Exit criteria:** {join_items(pilot['exit_criteria'])}. First step: "
                f"{sentence(pilot['first_step'])}",
                "",
            ]
        )

    lines.extend(["## Value Framing", ""])
    lines.extend(
        table(
            ["Opportunity", "Primary value levers", "Sizing basis", "Confidence", "Validation needed"],
            [
                [
                    opportunities[item_id]["name"],
                    join_items(opportunities[item_id]["value_levers"]),
                    value_label(opportunities[item_id]["value_case"]),
                    opportunities[item_id]["confidence"].title(),
                    opportunities[item_id]["validation_questions"][0],
                ]
                for item_id in high_ids
            ],
        )
    )
    lines.extend(["", "## Deployment and Governance Considerations", ""])
    lines.extend(
        table(
            ["Consideration", "Implication", "Recommended control"],
            [
                ["Deployment model", deployment_label, "Validate capability availability in this environment"],
                ["Data classification", deployment["data_classification"].title(), "Apply least privilege and retention controls"],
                ["GenAI policy", deployment["genai_policy"].title(), "Stop if policy does not permit the bounded use case"],
                *[
                    [constraint, "Hard deployment constraint", "Address explicitly before pilot approval"]
                    for constraint in constraints
                ],
            ],
        )
    )
    lines.extend(["", "## Facts, Assumptions, and Validation Questions", "", "### Facts", ""])
    for item in inventory:
        lines.append(
            f"- {item['inventory_id']} {item['name']}: {join_items(item['facts'])} "
            f"(status: {item['status']}; department: {item['department']})."
        )
    lines.extend(["", "### Assumptions", ""])
    if assumptions:
        for assumption in assumptions:
            lines.append(
                f"- {assumption['assumption_id']} [{assumption['status']}]: "
                f"{sentence(assumption['statement'])}"
            )
    else:
        lines.append("- No planning assumptions were recorded.")
    lines.extend(["", "### Validation questions", ""])
    questions: list[str] = []
    for item_id in high_ids:
        for question in opportunities[item_id]["validation_questions"]:
            if question not in questions:
                questions.append(question)
    for index, question in enumerate(questions[:10], start=1):
        lines.append(f"{index}. {question}")

    lines.extend(
        [
            "",
            "## Workshop Prep",
            "",
            *table(
                ["Segment", "Time", "Purpose", "Output"],
                [
                    ["Evidence review", "20 min", "Confirm IDs, dates, and assumptions", "Accepted evidence ledger"],
                    ["Portfolio decision", "25 min", "Confirm rank and decision asks", "Approved shortlist"],
                    ["Pilot boundary", "30 min", "Confirm owner, scope, controls, and measures", "Draft pilot charter"],
                    ["Close", "15 min", "Assign validation work", "Named owners and dates"],
                ],
            ),
            "",
            "## Recommended Next Steps",
            "",
            f"1. {primary['decision_ask']}",
            f"2. Complete the first pilot step: {primary['pilot']['first_step']}",
            "3. Revalidate the evidence ledger, portfolio, Markdown, and DOCX before customer use.",
            "",
            "## Appendix: Source Ledger",
            "",
            *table(
                ["Source ID", "Source", "Publisher", "Published", "Accessed", "Official", "Relevant priority"],
                [
                    [
                        source["source_id"],
                        source["title"],
                        source["publisher"],
                        source["published_date"],
                        source["accessed_date"],
                        str(source["official"]),
                        source["evidence_summary"],
                    ]
                    for source in sources
                ],
            ),
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    try:
        ledger = load_json_object(args.evidence_ledger, "evidence_ledger")
        portfolio = load_json_object(args.portfolio, "portfolio")
        profile = (
            load_json_object(args.inventory_profile, "inventory_profile")
            if args.inventory_profile
            else None
        )
    except ContractLoadError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    failures = validate_portfolio(portfolio, ledger, profile=profile, require_derived=True)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    if args.output.exists() and not args.force:
        print(f"FAIL: output already exists: {args.output}; pass --force to replace it", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(ledger, portfolio), encoding="utf-8")
    print(f"OK: wrote deterministic Markdown to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
