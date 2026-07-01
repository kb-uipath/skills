#!/usr/bin/env python3
"""Verify the final UiPath agentic expansion executive DOCX artifact."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT


REQUIRED_HEADINGS = [
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify a rendered agentic expansion executive DOCX brief."
    )
    parser.add_argument("docx", type=Path, help="Rendered DOCX file to inspect")
    parser.add_argument(
        "--allow-landscape",
        action="store_true",
        help="Allow landscape orientation. By default, portrait is required.",
    )
    parser.add_argument(
        "--require-output-dir",
        action="store_true",
        help="Require the DOCX to be inside a directory named outputs.",
    )
    parser.add_argument(
        "--min-proposal-headings",
        type=int,
        default=5,
        help="Minimum level-3 proposal-card headings required after the Top 5 section.",
    )
    parser.add_argument(
        "--min-poc-headings",
        type=int,
        default=3,
        help="Minimum level-3 POC headings required after the Top 3 section.",
    )
    return parser.parse_args()


def section_count(headings: list[tuple[int, str]], start: str, stop_candidates: set[str]) -> int:
    in_section = False
    count = 0
    for level, text in headings:
        if level == 2 and text == start:
            in_section = True
            continue
        if in_section and level == 2 and text in stop_candidates:
            break
        if in_section and level == 3:
            count += 1
    return count


def table_has_rank_header(document: Document) -> bool:
    for table in document.tables:
        if not table.rows:
            continue
        headers = [cell.text.strip().lower() for cell in table.rows[0].cells]
        if len(headers) >= 2 and headers[0] == "rank" and headers[1] == "opportunity":
            return True
    return False


def main() -> int:
    args = parse_args()
    failures: list[str] = []

    if not args.docx.exists():
        failures.append(f"DOCX does not exist: {args.docx}")
        print("\n".join(failures), file=sys.stderr)
        return 1

    if args.require_output_dir and args.docx.parent.name != "outputs":
        failures.append(f"DOCX must be in an outputs directory: {args.docx}")

    document = Document(args.docx)
    paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    headings: list[tuple[int, str]] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style_name = paragraph.style.name if paragraph.style is not None else ""
        if style_name.startswith("Heading"):
            try:
                level = int(style_name.split()[-1])
            except ValueError:
                level = 0
            headings.append((level, text))

    if not paragraphs:
        failures.append("DOCX has no non-empty paragraphs.")
    else:
        title = paragraphs[0]
        if len(title) < 8:
            failures.append(f"DOCX title looks empty or too short: {title!r}")

    if not args.allow_landscape and document.sections[0].orientation != WD_ORIENT.PORTRAIT:
        failures.append("DOCX must be portrait unless landscape was explicitly requested.")

    heading_texts = [text for _, text in headings]
    missing = [heading for heading in REQUIRED_HEADINGS if heading not in heading_texts]
    if missing:
        failures.append("Missing required headings: " + ", ".join(missing))

    if not any("Source Ledger" in text or text.startswith("Appendix") for text in heading_texts):
        failures.append("Missing appendix/source-ledger heading.")

    if len(document.tables) < 3:
        failures.append(f"Expected at least 3 tables; found {len(document.tables)}.")

    if not table_has_rank_header(document):
        failures.append("No prioritized portfolio table with Rank / Opportunity header found.")

    proposal_count = section_count(
        headings,
        "Top 5 High-Impact Recommendations",
        {"Top 3 Low-Friction POC Candidates"},
    )
    if proposal_count < args.min_proposal_headings:
        failures.append(
            f"Expected at least {args.min_proposal_headings} proposal headings; found {proposal_count}."
        )

    poc_count = section_count(
        headings,
        "Top 3 Low-Friction POC Candidates",
        {"Value Framing"},
    )
    if poc_count < args.min_poc_headings:
        failures.append(f"Expected at least {args.min_poc_headings} POC headings; found {poc_count}.")

    first_heading_names = [text for _, text in headings[:6]]
    if any("Source Ledger" in text or text.startswith("Appendix") for text in first_heading_names):
        failures.append("Source ledger appears too early; keep it in the appendix.")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    orientation = (
        "PORTRAIT" if document.sections[0].orientation == WD_ORIENT.PORTRAIT else "LANDSCAPE"
    )
    print(f"OK: {args.docx}")
    print(f"title={paragraphs[0] if paragraphs else ''}")
    print(f"orientation={orientation}")
    print(f"paragraphs={len(document.paragraphs)}")
    print(f"tables={len(document.tables)}")
    print(f"proposal_headings={proposal_count}")
    print(f"poc_headings={poc_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
