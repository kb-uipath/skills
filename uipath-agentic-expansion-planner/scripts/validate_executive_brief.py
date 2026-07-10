#!/usr/bin/env python3
"""Validate a UiPath agentic expansion Markdown brief before DOCX rendering."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

from portfolio_contracts import (
    ContractLoadError,
    format_score,
    load_json_object,
    validate_portfolio,
)


REQUIRED_SECTIONS = [
    "Executive Summary",
    "Source and Assumption Note",
    "Current Automation Footprint",
    "Public Strategy Alignment",
    "Prioritized Portfolio",
    "Top 5 High-Impact Recommendations",
    "Top 3 Low-Friction POC Candidates",
    "Value Framing",
    "Deployment and Governance Considerations",
    "Facts, Assumptions, and Validation Questions",
    "Workshop Prep",
    "Recommended Next Steps",
]

REQUIRED_RECOMMENDATION_FIELDS = [
    "Recommendation",
    "Why now",
    "Inventory evidence",
    "Agentic enhancement",
    "UiPath capability fit",
    "Value levers",
    "Feasibility",
    "Governance",
    "Validation questions",
]

REQUIRED_POC_FIELDS = [
    "Pilot objective",
    "Narrow scope",
    "Agent role",
    "Human role",
    "Success metrics",
    "Data needed",
    "Exit criteria",
]

BANNED_TERMS = [
    "revolutionary",
    "game-changing",
    "guaranteed",
    "seamless transformation",
    "unprecedented",
    "world-class",
]

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
        description="Validate a Markdown executive brief before rendering the final DOCX."
    )
    parser.add_argument("markdown", type=Path, help="Markdown brief to validate")
    parser.add_argument("--min-summary-words", type=int, default=45)
    parser.add_argument("--max-summary-words", type=int, default=170)
    parser.add_argument(
        "--max-total-words",
        type=int,
        default=3500,
        help="Maximum executive-brief length before rendering",
    )
    parser.add_argument("--min-recommendations", type=int, default=5)
    parser.add_argument("--min-pocs", type=int, default=3)
    parser.add_argument(
        "--portfolio",
        type=Path,
        default=None,
        help="Optional v1 portfolio.json for strict claim cross-checks",
    )
    parser.add_argument(
        "--evidence-ledger",
        type=Path,
        default=None,
        help="Optional v1 evidence_ledger.json; required with --portfolio",
    )
    parser.add_argument(
        "--inventory-profile",
        type=Path,
        default=None,
        help="Optional v1 inventory_profile.json for inventory ID/name cross-checks",
    )
    parser.add_argument(
        "--max-source-age-days",
        type=int,
        default=None,
        help="Fail when referenced public evidence is older than this at portfolio.as_of_date",
    )
    return parser.parse_args()


def normalize_heading(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().strip("#").strip()).casefold()


def heading_entries(lines: list[str]) -> list[tuple[int, str, int]]:
    entries: list[tuple[int, str, int]] = []
    for index, line in enumerate(lines):
        match = re.match(r"^(#{1,4})\s+(.+?)\s*$", line)
        if match:
            entries.append((len(match.group(1)), match.group(2).strip(), index))
    return entries


def section_text(lines: list[str], entries: list[tuple[int, str, int]], heading: str) -> str:
    target = normalize_heading(heading)
    for pos, (level, title, start) in enumerate(entries):
        if level == 2 and normalize_heading(title) == target:
            end = len(lines)
            for next_level, _next_title, next_start in entries[pos + 1 :]:
                if next_level <= level:
                    end = next_start
                    break
            return "\n".join(lines[start + 1 : end]).strip()
    return ""


def subsection_blocks(
    lines: list[str],
    entries: list[tuple[int, str, int]],
    section: str,
    *,
    level: int = 3,
) -> list[tuple[str, str]]:
    parent = normalize_heading(section)
    blocks: list[tuple[str, str]] = []
    for pos, (entry_level, title, start) in enumerate(entries):
        if entry_level != 2 or normalize_heading(title) != parent:
            continue
        section_end = len(lines)
        for next_level, _next_title, next_start in entries[pos + 1 :]:
            if next_level <= entry_level:
                section_end = next_start
                break
        section_entries = [
            (candidate_level, candidate_title, candidate_start)
            for candidate_level, candidate_title, candidate_start in entries
            if start < candidate_start < section_end and candidate_level == level
        ]
        for sub_pos, (_sub_level, sub_title, sub_start) in enumerate(section_entries):
            sub_end = section_end
            if sub_pos + 1 < len(section_entries):
                sub_end = section_entries[sub_pos + 1][2]
            blocks.append((sub_title, "\n".join(lines[sub_start + 1 : sub_end]).strip()))
        break
    return blocks


def has_field(block: str, field: str) -> bool:
    return bool(re.search(rf"(?im)^\*\*{re.escape(field)}:\*\*", block))


def count_validation_questions(text: str) -> int:
    question_lines = 0
    in_validation = False
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"(?i)^(\*\*)?validation questions:?(\*\*)?$", stripped):
            in_validation = True
            continue
        if in_validation and re.match(r"^#{1,4}\s+", stripped):
            in_validation = False
        if in_validation and (stripped.endswith("?") or re.match(r"^[-*]\s+.+\?$", stripped)):
            question_lines += 1
    return question_lines


def validate(text: str, args: argparse.Namespace) -> list[str]:
    failures: list[str] = []
    lines = text.splitlines()
    entries = heading_entries(lines)
    heading_names = {normalize_heading(title) for _level, title, _start in entries}

    total_word_count = len(re.findall(r"\b[\w-]+\b", text))
    if args.max_total_words < 1:
        failures.append("--max-total-words must be a positive integer.")
    elif total_word_count > args.max_total_words:
        failures.append(
            f"Executive brief must contain no more than {args.max_total_words} words; "
            f"found {total_word_count}."
        )

    for section in REQUIRED_SECTIONS:
        if normalize_heading(section) not in heading_names:
            failures.append(f"Missing required section: {section}")

    if not any("source ledger" in normalize_heading(title) for _level, title, _start in entries):
        failures.append("Missing appendix/source ledger section.")

    summary = section_text(lines, entries, "Executive Summary")
    summary_word_count = len(re.findall(r"\b[\w-]+\b", summary))
    if summary and not (args.min_summary_words <= summary_word_count <= args.max_summary_words):
        failures.append(
            "Executive Summary must be "
            f"{args.min_summary_words}-{args.max_summary_words} words; found {summary_word_count}."
        )
    if summary and not re.search(r"\b(recommend|next step|decision|ask|workshop|pilot)\b", summary, re.I):
        failures.append("Executive Summary must state a decision, ask, pilot, workshop, or next step.")

    for term in BANNED_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", text, re.I):
            failures.append(f"Banned hype term found: {term}")

    recommendation_blocks = subsection_blocks(
        lines, entries, "Top 5 High-Impact Recommendations"
    )
    if len(recommendation_blocks) < args.min_recommendations:
        failures.append(
            f"Expected at least {args.min_recommendations} recommendation cards; "
            f"found {len(recommendation_blocks)}."
        )
    for title, block in recommendation_blocks:
        missing = [field for field in REQUIRED_RECOMMENDATION_FIELDS if not has_field(block, field)]
        if missing:
            failures.append(f"Recommendation '{title}' is missing field(s): {', '.join(missing)}")

    poc_blocks = subsection_blocks(lines, entries, "Top 3 Low-Friction POC Candidates")
    if len(poc_blocks) < args.min_pocs:
        failures.append(f"Expected at least {args.min_pocs} POC cards; found {len(poc_blocks)}.")
    for title, block in poc_blocks:
        missing = [field for field in REQUIRED_POC_FIELDS if not has_field(block, field)]
        if missing:
            failures.append(f"POC '{title}' is missing field(s): {', '.join(missing)}")

    if count_validation_questions(text) < 3:
        failures.append("Expected at least 3 explicit validation questions.")

    if "Inventory evidence" not in text or "Public Strategy Alignment" not in text:
        failures.append("Brief must connect inventory evidence to public strategy alignment.")

    prioritized = section_text(lines, entries, "Prioritized Portfolio")
    if prioritized and "scoring basis" not in prioritized.casefold():
        failures.append("Prioritized Portfolio must show the scoring basis, not only total scores.")

    return failures


def _number_appears(text: str, value: Any) -> bool:
    normalized = text.replace(",", "")
    if isinstance(value, (int, float)):
        candidates = {
            str(value),
            f"{value:.2f}",
            f"{value:.2f}".rstrip("0").rstrip("."),
        }
        return any(candidate in normalized for candidate in candidates)
    return False


def _ordered_opportunities(portfolio: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {item["opportunity_id"]: item for item in portfolio["opportunities"]}
    ordered_ids: list[str] = []
    for key in ("high_impact", "low_friction_poc"):
        for item_id in portfolio["rankings"][key]:
            if item_id not in ordered_ids:
                ordered_ids.append(item_id)
    return [by_id[item_id] for item_id in ordered_ids]


def cross_check_contracts(
    text: str,
    portfolio: dict[str, Any],
    ledger: dict[str, Any],
    *,
    profile: dict[str, Any] | None,
    max_source_age_days: int | None,
) -> list[str]:
    failures = validate_portfolio(portfolio, ledger, profile=profile, require_derived=True)
    if failures:
        return failures

    folded = text.casefold()
    customer_name = ledger["customer"]["name"]
    if customer_name.casefold() not in folded:
        failures.append(f"Brief does not name portfolio customer {customer_name!r}.")

    lines = text.splitlines()
    entries = heading_entries(lines)
    prioritized = section_text(lines, entries, "Prioritized Portfolio")
    prioritized_folded = prioritized.casefold()
    by_id = {item["opportunity_id"]: item for item in portfolio["opportunities"]}
    for item_id in portfolio["rankings"]["high_impact"]:
        item = by_id[item_id]
        if item["name"].casefold() not in prioritized_folded:
            failures.append(f"Prioritized Portfolio does not contain opportunity {item['name']!r}.")
        score = format_score(item["scores"]["high_impact"])
        if not re.search(rf"(?<![\d.]){re.escape(score)}(?![\d.])", prioritized):
            failures.append(
                f"Prioritized Portfolio does not contain score {score} for {item['name']!r}."
            )

    inventory_by_id = {item["inventory_id"]: item for item in ledger["inventory_evidence"]}
    source_by_id = {item["source_id"]: item for item in ledger["public_sources"]}
    referenced_inventory: set[str] = set()
    referenced_sources: set[str] = set()
    referenced_assumptions: set[str] = set()
    for item in _ordered_opportunities(portfolio):
        if item["name"].casefold() not in folded:
            failures.append(f"Brief does not contain ranked opportunity name {item['name']!r}.")
        refs = item["evidence_refs"]
        referenced_inventory.update(refs["inventory_ids"])
        referenced_sources.update(refs["public_source_ids"])
        referenced_assumptions.update(refs["assumption_ids"])
        value_case = item["value_case"]
        if value_case["method"] == "calculated":
            if not _number_appears(text, value_case["annual_hours"]):
                failures.append(
                    f"Brief does not contain calculated annual hours for {item['name']!r}."
                )
            if not _number_appears(text, value_case["annual_value"]):
                failures.append(
                    f"Brief does not contain calculated annual value for {item['name']!r}."
                )

        for fit in item["capability_fit"]:
            capability = fit["capability"]
            capability_pattern = re.escape(capability)
            if fit["claim"] == "likely_fit":
                if not re.search(
                    rf"{capability_pattern}.{{0,100}}likely fit",
                    text,
                    re.IGNORECASE | re.DOTALL,
                ):
                    failures.append(
                        f"Brief must label {capability!r} as likely fit when entitlement is not confirmed."
                    )
                overclaim = re.search(
                    rf"\b(?:owns|has|uses|is licensed for|is entitled to|can deploy|can use|has access to)\s+(?:the\s+)?"
                    rf"{capability_pattern}\b",
                    text,
                    re.IGNORECASE,
                )
                if overclaim:
                    failures.append(
                        f"Brief overclaims unconfirmed entitlement for {capability!r}: "
                        f"{overclaim.group(0)!r}."
                    )
            elif not re.search(
                rf"{capability_pattern}.{{0,100}}confirmed entitlement",
                text,
                re.IGNORECASE | re.DOTALL,
            ):
                failures.append(
                    f"Brief must identify confirmed entitlement evidence for {capability!r}."
                )

    for item_id in sorted(referenced_inventory):
        item = inventory_by_id[item_id]
        if item_id.casefold() not in folded:
            failures.append(f"Brief does not cite inventory ID {item_id}.")
        if item["name"].casefold() not in folded:
            failures.append(f"Brief does not contain profile/ledger inventory name {item['name']!r}.")
    for source_id in sorted(referenced_sources):
        source = source_by_id[source_id]
        if source_id.casefold() not in folded:
            failures.append(f"Brief does not cite public source ID {source_id}.")
        for date_field in ("published_date", "accessed_date"):
            if source[date_field] not in text:
                failures.append(
                    f"Brief does not contain {date_field} {source[date_field]} for {source_id}."
                )
    for assumption_id in sorted(referenced_assumptions):
        if assumption_id.casefold() not in folded:
            failures.append(f"Brief does not cite assumption ID {assumption_id}.")

    source_name = ledger["inventory_profile"]["source_name"]
    if source_name.casefold() not in folded:
        failures.append(f"Brief does not name inventory profile source {source_name!r}.")

    deployment = ledger["customer"]["deployment"]
    deployment_label = DEPLOYMENT_LABELS[deployment["model"]]
    if deployment_label.casefold() not in folded:
        failures.append(f"Brief does not state deployment model {deployment_label!r}.")
    for constraint in deployment["constraints"]:
        if constraint.casefold() not in folded:
            failures.append(f"Brief omits deployment constraint {constraint!r}.")

    if max_source_age_days is not None:
        if max_source_age_days < 0:
            failures.append("--max-source-age-days must be zero or greater.")
        else:
            as_of = date.fromisoformat(portfolio["as_of_date"])
            for source_id in sorted(referenced_sources):
                published = date.fromisoformat(source_by_id[source_id]["published_date"])
                age = (as_of - published).days
                if age > max_source_age_days:
                    failures.append(
                        f"Public source {source_id} is {age} days old at {portfolio['as_of_date']}; "
                        f"maximum is {max_source_age_days}."
                    )
    return failures


def main() -> int:
    args = parse_args()
    if not args.markdown.exists():
        print(f"Markdown does not exist: {args.markdown}", file=sys.stderr)
        return 1

    if bool(args.portfolio) != bool(args.evidence_ledger):
        print(
            "FAIL: --portfolio and --evidence-ledger must be supplied together for strict "
            "cross-checking.",
            file=sys.stderr,
        )
        return 1
    if args.inventory_profile and not args.portfolio:
        print(
            "FAIL: --inventory-profile requires --portfolio and --evidence-ledger.",
            file=sys.stderr,
        )
        return 1
    if args.max_source_age_days is not None and not args.portfolio:
        print(
            "FAIL: --max-source-age-days requires --portfolio and --evidence-ledger.",
            file=sys.stderr,
        )
        return 1

    text = args.markdown.read_text(encoding="utf-8")
    failures = validate(text, args)
    if args.portfolio and args.evidence_ledger:
        try:
            portfolio = load_json_object(args.portfolio, "portfolio")
            ledger = load_json_object(args.evidence_ledger, "evidence_ledger")
            profile = (
                load_json_object(args.inventory_profile, "inventory_profile")
                if args.inventory_profile
                else None
            )
        except ContractLoadError as exc:
            failures.append(str(exc))
        else:
            failures.extend(
                cross_check_contracts(
                    text,
                    portfolio,
                    ledger,
                    profile=profile,
                    max_source_age_days=args.max_source_age_days,
                )
            )
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    print(f"OK: {args.markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
