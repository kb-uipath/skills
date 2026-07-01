#!/usr/bin/env python3
"""Validate GTM proposal markdown against the skill output contract."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_HEADINGS = (
    "## Confirmed Scope",
    "## Source Ledger",
    "## Budget / Program Areas",
    "## Prioritized Use Cases",
    "## Proposal Cards",
    "## Assumptions and Validation Needed",
)
CITATION_RE = re.compile(r"\[S\d+\]")
MONEY_OR_PERCENT_RE = re.compile(
    r"(\$[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|k|m|bn))?|\b\d+(?:\.\d+)?%)",
    re.IGNORECASE,
)
ESTIMATE_TIERS = ("Documented", "Derived", "Benchmarked", "Assumption")
UNSAFE_CLAIMS = (
    "guaranteed roi",
    "guaranteed savings",
    "will save",
    "will reduce cost",
    "proven to save",
    "no risk",
)


def validate_text(text: str) -> list[str]:
    errors: list[str] = []
    for heading in REQUIRED_HEADINGS:
        if heading not in text:
            errors.append(f"missing required heading: {heading}")

    if "| Source ID |" not in text or "| Publisher |" not in text:
        errors.append("source ledger table must include Source ID and Publisher columns")

    citations = CITATION_RE.findall(text)
    if not citations:
        errors.append("at least one source citation like [S1] is required")

    source_section = section_text(text, "## Source Ledger")
    source_ids = set(CITATION_RE.findall(source_section))
    if citations and not source_ids:
        errors.append("source ledger must define cited source IDs")
    missing_source_ids = sorted(set(citations) - source_ids)
    if missing_source_ids:
        errors.append("citation(s) missing from source ledger: " + ", ".join(missing_source_ids))

    if not any(tier in text for tier in ESTIMATE_TIERS):
        errors.append("at least one estimate tier label is required")

    lowered = text.lower()
    for phrase in UNSAFE_CLAIMS:
        if phrase in lowered:
            errors.append(f"unsupported overclaim phrase: {phrase}")

    proposal_section = text.split("## Proposal Cards", 1)[-1] if "## Proposal Cards" in text else ""
    if proposal_section and "Validation required" not in proposal_section:
        errors.append("proposal cards must include a Validation required line or field")

    for line_number, line in enumerate(text.splitlines(), start=1):
        if MONEY_OR_PERCENT_RE.search(line) and not CITATION_RE.search(line):
            errors.append(f"uncited money or percentage claim on line {line_number}")

    return errors


def section_text(text: str, heading: str) -> str:
    if heading not in text:
        return ""
    tail = text.split(heading, 1)[1]
    next_heading = re.search(r"\n##\s+", tail)
    return tail[: next_heading.start()] if next_heading else tail


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown", type=Path, help="Proposal markdown file to validate")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    errors = validate_text(args.markdown.read_text(encoding="utf-8"))
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print("GTM proposal output contract validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
