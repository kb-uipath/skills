#!/usr/bin/env python3
"""Validate a UiPath agentic expansion Markdown brief before DOCX rendering."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a Markdown executive brief before rendering the final DOCX."
    )
    parser.add_argument("markdown", type=Path, help="Markdown brief to validate")
    parser.add_argument("--min-summary-words", type=int, default=45)
    parser.add_argument("--max-summary-words", type=int, default=170)
    parser.add_argument("--min-recommendations", type=int, default=5)
    parser.add_argument("--min-pocs", type=int, default=3)
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

    return failures


def main() -> int:
    args = parse_args()
    if not args.markdown.exists():
        print(f"Markdown does not exist: {args.markdown}", file=sys.stderr)
        return 1

    text = args.markdown.read_text(encoding="utf-8")
    failures = validate(text, args)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    print(f"OK: {args.markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
