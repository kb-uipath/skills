#!/usr/bin/env python3
"""Validate concise customer-assessment Markdown for structure and plain language."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_SECTIONS = [
    "Source File Summary",
    "Current Automation Footprint",
    "Top 3 Recommendations",
]
SOURCE_FIELDS = ["Inventory reviewed", "Information available", "Limitations"]
FOOTPRINT_ROWS = [
    "Total reviewed",
    "Lifecycle mix",
    "Process/domain groups",
    "Department concentration",
    "System concentration",
    "Unmapped",
    "Assessment boundary",
]
RECOMMENDATION_FIELDS = [
    "End-to-end process",
    "Why it matters",
    "Existing automation foundation",
    "Pilot path",
    "Roles and controls",
    "Decision gate",
    "Next action",
]
HYPE_TERMS = {
    "ai-powered",
    "game-changing",
    "next-generation",
    "revolutionary",
    "seamless",
    "transformational",
    "best-in-class",
    "world-class",
    "unprecedented",
    "cutting-edge",
}
INTERNAL_TERMS = {
    "artifact hash",
    "claim type",
    "contract version",
    "schema_version",
    "json schema",
    "evidence ledger",
    "evidence reference",
    "reviewer mode",
    "weighted score",
    "criteria_scores",
    "validation receipt",
    "sha-256",
    "deterministic ranking",
}
LOCAL_PATH_PATTERN = re.compile(
    r"(?:^|[\s(])(?:/(?:Users|home|private|tmp|var)/[^\s)]+|[A-Za-z]:\\[^\s)]+)",
    re.I,
)
RAW_SHA256_PATTERN = re.compile(r"\b[0-9a-f]{64}\b", re.I)
INTERNAL_ID_PATTERN = re.compile(
    r"\b(?:INV|SRC|ASM|OPP|PROC|LEDGER|PORTFOLIO|PROCESS-MAP|REVIEW)-[A-Z0-9]",
    re.I,
)
AMBIGUOUS_CONTROL_PHRASES = {
    "record approved disposition",
    "update approved status",
}
CRYPTIC_PHRASES = {
    "customer-language claims",
    "fit to validate",
    "revise: owner",
}


def markdown_word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def validate_customer_assessment(
    text: str,
    *,
    max_words: int = 900,
    min_words: int = 250,
) -> list[str]:
    failures: list[str] = []
    h2 = re.findall(r"^##\s+(.+?)\s*$", text, flags=re.M)
    if h2 != REQUIRED_SECTIONS:
        failures.append(
            "Customer assessment must contain exactly these level-2 sections in order: "
            + ", ".join(REQUIRED_SECTIONS)
        )
    recommendations = re.findall(r"^###\s+(.+?)\s*$", text, flags=re.M)
    if not 1 <= len(recommendations) <= 3:
        failures.append("Customer assessment must contain from one to three recommendations")
    for index, heading in enumerate(recommendations, start=1):
        if not re.match(rf"^{index}\.\s+\S", heading):
            failures.append(
                "Customer recommendations must be numbered consecutively from 1"
            )
            break

    section_parts = re.split(r"^##\s+(.+?)\s*$", text, flags=re.M)
    sections = {
        section_parts[index]: section_parts[index + 1]
        for index in range(1, len(section_parts) - 1, 2)
    }
    source_section = sections.get("Source File Summary", "")
    for field in SOURCE_FIELDS:
        match = re.search(
            rf"(?im)^[-*]\s+\*\*{re.escape(field)}:\*\*\s+(.+)$",
            source_section,
        )
        if not match or not match.group(1).strip():
            failures.append(f"Source File Summary is missing field: {field}")
    footprint_section = sections.get("Current Automation Footprint", "")
    for row in FOOTPRINT_ROWS:
        match = re.search(
            rf"(?im)^\|\s*{re.escape(row)}\s*\|\s*([^|]+)\|",
            footprint_section,
        )
        if not match or not match.group(1).strip():
            failures.append(f"Current Automation Footprint is missing row: {row}")
    controls_match = re.search(
        r"(?im)^\|\s*Assessment boundary\s*\|\s*([^|]+)\|",
        footprint_section,
    )
    if controls_match:
        controls = controls_match.group(1).casefold()
        for term in (
            "read-only",
            "not savings",
            "authorize no writes or decisions",
        ):
            if term not in controls:
                failures.append(
                    f"Assessment boundary must state shared pilot control: {term}"
                )
    process_match = re.search(
        r"(?im)^\|\s*Process/domain groups\s*\|\s*([^|]+)\|",
        footprint_section,
    )
    if process_match and "customer confirmation required" not in process_match.group(1).casefold():
        failures.append(
            "Process groups must distinguish analyst mapping from customer confirmation"
        )

    recommendation_section = sections.get("Top 3 Recommendations", "")
    recommendation_parts = re.split(r"^###\s+(.+?)\s*$", recommendation_section, flags=re.M)
    comparison_rows = re.findall(
        r"(?m)^\|\s*(\d+)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*$",
        recommendation_parts[0] if recommendation_parts else "",
    )
    comparison_preamble = recommendation_parts[0] if recommendation_parts else ""
    comparison_folded = comparison_preamble.casefold()
    if "order basis:" not in comparison_folded or not all(
        term in comparison_folded
        for term in ("strategy fit", "foundation", "evidence", "delivery risk")
    ):
        failures.append(
            "Top 3 Recommendations must state the common customer-facing ranking basis"
        )
    for phrase, label in (
        ("workshop ask:", "the workshop decision ask"),
        ("thresholds from baselines and tolerances", "the threshold-confirmation basis"),
        ("no deployment or investment approval", "the bounded decision scope"),
        ("account team:", "the account-team execution sequence"),
        ("csm", "CSM ownership"),
        ("tam", "TAM ownership"),
        ("ae", "AE ownership"),
        ("delivers agenda/access by each target", "the CSM artifact and timing"),
        (
            "delivers product/tenant control note before each charter",
            "the TAM artifact and timing",
        ),
        (
            "delivers sponsor/funding decision after evidence",
            "the AE artifact and timing",
        ),
        ("failed prerequisites defer", "the account-team escalation path"),
        ("pilot mechanics:", "the shared pilot mechanics"),
        ("data joins frozen exports", "the correlation boundary"),
        ("maestro sequences handoffs", "the Maestro orchestration role"),
        ("robots prepare outputs", "the Robot preparation role"),
        ("humans review", "the human-review role"),
        ("unmatched records pause and rerun", "the exception and recovery path"),
        ("final record systems require validation", "the system-of-record validation"),
    ):
        if phrase not in comparison_folded:
            failures.append(f"Top 3 Recommendations must state {label}")
    if (
        "| Rank | Process | Why this order |" not in comparison_preamble
        or [int(rank) for rank, _process, _reason in comparison_rows]
        != list(range(1, len(recommendations) + 1))
    ):
        failures.append(
            "Top 3 Recommendations must start with a complete rank comparison table"
        )
    comparison_reasons = [
        re.sub(r"\W+", " ", reason.casefold()).strip()
        for _rank, _process, reason in comparison_rows
    ]
    if len(comparison_reasons) != len(set(comparison_reasons)):
        failures.append("Recommendation ranking reasons must be recommendation-specific")
    for rank, _process, reason in comparison_rows:
        if markdown_word_count(reason) < 7:
            failures.append(f"Recommendation rank {rank} has a vague comparison reason")
    field_values: dict[str, list[tuple[str, str]]] = {
        "Why it matters": [],
        "Pilot path": [],
        "Next action": [],
    }
    for index in range(1, len(recommendation_parts) - 1, 2):
        heading = recommendation_parts[index]
        body = recommendation_parts[index + 1]
        for field in RECOMMENDATION_FIELDS:
            match = re.search(
                rf"(?im)^[-*]\s+\*\*{re.escape(field)}:\*\*\s+(.+)$",
                body,
            )
            if not match or not match.group(1).strip():
                failures.append(
                    f"Recommendation {heading!r} is missing field: {field}"
                )
            elif field == "End-to-end process":
                boundary_text = match.group(1).casefold()
                if not all(
                    label in boundary_text
                    for label in ("function:", "start:", "end:", "outcome:")
                ):
                    failures.append(
                        f"Recommendation {heading!r} process boundary must define Function, Start, End, and Outcome"
                    )
            if match and field in field_values:
                normalized = re.sub(r"\W+", " ", match.group(1).casefold()).strip()
                field_values[field].append((heading, normalized))
        pilot_match = re.search(r"(?im)^[-*]\s+\*\*Decision gate:\*\*\s+(.+)$", body)
        if pilot_match:
            pilot_text = pilot_match.group(1).casefold()
            gate_text = pilot_text
            missing_outcomes = [
                outcome
                for outcome in ("proceed when", "adjust when", "stop when")
                if outcome not in gate_text
            ]
            if missing_outcomes:
                failures.append(
                    f"Recommendation {heading!r} must define stop, proceed, and adjust outcomes"
                )
            ordered_phrases = [
                gate_text.find("stop when"),
                gate_text.find("proceed when"),
                gate_text.find("adjust when"),
            ]
            if any(index < 0 for index in ordered_phrases) or ordered_phrases != sorted(
                ordered_phrases
            ):
                failures.append(
                    f"Recommendation {heading!r} pilot decision must use exhaustive stop-first precedence"
                )
            if not any(
                phrase in gate_text
                for phrase in (
                    "does not authorize",
                    "gate only authorizes pilot continuation",
                    "gate permits only a separately approved live test",
                    "pilot continuation only",
                    "separately approved live test only",
                )
            ):
                failures.append(
                    f"Recommendation {heading!r} pilot gate must state the bounded decision it enables"
                )
            if "rerun before proceeding" not in gate_text:
                failures.append(
                    f"Recommendation {heading!r} pilot gate must require correction and rerun before proceeding"
                )
        design_match = re.search(
            r"(?im)^[-*]\s+\*\*Pilot path:\*\*\s+(.+)$",
            body,
        )
        roles_match = re.search(
            r"(?im)^[-*]\s+\*\*Roles and controls:\*\*\s+(.+)$",
            body,
        )
        if design_match and not any(
            marker in design_match.group(1).casefold()
            for marker in ("planning assumption", "proposed")
        ):
            failures.append(
                f"Recommendation {heading!r} must label the proposed pilot path as an assumption"
            )
        if design_match:
            design_text = design_match.group(1).casefold()
            for term, label in (
                ("input:", "a case-level input"),
                ("ground truth:", "the reviewer-owned ground truth"),
                ("ground-truth owner:", "the owner of the reference outcomes"),
                ("reports", "the measurement owner"),
            ):
                if term not in design_text:
                    failures.append(
                        f"Recommendation {heading!r} pilot path must state {label}"
                    )
            if not re.search(r"\b\d[\d,]*\b", design_text) or not re.search(
                r"\b(?:across|completed|historical|random|recent|representative|stratified)\b",
                design_text,
            ):
                failures.append(
                    f"Recommendation {heading!r} pilot path must state a numeric sample and selection method"
                )
            if not re.search(r"\b(?:daily|each case|every case|per case|weekly)\b", design_text):
                failures.append(
                    f"Recommendation {heading!r} pilot path must state the review cadence"
                )
            if not re.search(
                r"\b(?:bundle|classification|comparison|evidence|flag|log|output|report|result|summary)\w*\b",
                design_text,
            ):
                failures.append(
                    f"Recommendation {heading!r} pilot path must name an observable output"
                )
            if "/" not in design_text:
                failures.append(
                    f"Recommendation {heading!r} pilot path must state numerator/denominator formulas"
                )
        if roles_match and "pilot: no writes" not in roles_match.group(1).casefold():
            failures.append(
                f"Recommendation {heading!r} must state the pilot-write control boundary"
            )
        if pilot_match:
            gate_text = pilot_match.group(1).casefold()
            if not re.search(r"\b\d", gate_text):
                failures.append(
                    f"Recommendation {heading!r} decision gate must contain measurable thresholds"
                )
            if "decision owner:" not in gate_text:
                failures.append(
                    f"Recommendation {heading!r} decision gate must name one decision owner"
                )
        next_action_match = re.search(
            r"(?im)^[-*]\s+\*\*Next action:\*\*\s+(.+)$",
            body,
        )
        if next_action_match:
            next_action_text = next_action_match.group(1).casefold()
            if len(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", next_action_text)) < 2:
                failures.append(
                    f"Recommendation {heading!r} next action must anchor kickoff and decision review to dates"
                )
            for term in ("customer:", "uipath:", "output:"):
                if term not in next_action_text:
                    failures.append(
                        f"Recommendation {heading!r} next action must state {term.rstrip(':')}"
                    )
            if re.search(r"\bday[- ]?\d+\b", next_action_text):
                failures.append(
                    f"Recommendation {heading!r} next action must use anchored dates, not relative day numbers"
                )

    for field, values in field_values.items():
        seen: dict[str, str] = {}
        for heading, value in values:
            if value in seen:
                failures.append(
                    f"Recommendations {seen[value]!r} and {heading!r} repeat the same {field.lower()} text"
                )
            else:
                seen[value] = heading

    words = markdown_word_count(text)
    if words < min_words:
        failures.append(f"Customer assessment has {words} words; minimum is {min_words}")
    if words > max_words:
        failures.append(f"Customer assessment has {words} words; maximum is {max_words}")

    if INTERNAL_ID_PATTERN.search(text):
        failures.append("Customer assessment exposes an internal evidence or contract ID")
    if LOCAL_PATH_PATTERN.search(text):
        failures.append("Customer assessment exposes a local filesystem path")
    if RAW_SHA256_PATTERN.search(text):
        failures.append("Customer assessment exposes a raw SHA-256 value")
    folded = text.casefold()
    for term in sorted(HYPE_TERMS):
        if term in folded:
            failures.append(f"Customer assessment contains banned hype term: {term}")
    for term in sorted(INTERNAL_TERMS):
        if term in folded:
            failures.append(f"Customer assessment contains internal terminology: {term}")
    for phrase in sorted(AMBIGUOUS_CONTROL_PHRASES):
        if phrase in folded:
            failures.append(
                f"Customer assessment contains ambiguous decision-write phrase: {phrase}"
            )
    for phrase in sorted(CRYPTIC_PHRASES):
        if phrase in folded:
            failures.append(
                f"Customer assessment contains cryptic internal phrasing: {phrase}"
            )
    if ">=" in text or "<=" in text:
        failures.append(
            "Customer assessment must use plain threshold language instead of >= or <="
        )
    if "analyst-confirmed" in folded:
        failures.append(
            "Customer assessment must not imply that analyst mapping is customer confirmation"
        )
    if "structurally complete" in folded:
        failures.append(
            "Customer assessment must state observed field gaps instead of claiming structural completeness"
        )
    if re.search(r"\b(?:pilot|automation)\s+(?:covers|handles|processes)\s+[\d,]+", folded):
        failures.append(
            "Customer assessment must not imply observed automation or pilot throughput from inventory volume"
        )

    prose_blocks = []
    for block in re.split(r"\n\s*\n", text):
        stripped = block.strip()
        if not stripped or stripped.startswith("|") or stripped.startswith("#"):
            continue
        cleaned = re.sub(r"^[-*]\s+", "", stripped, flags=re.M)
        cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
        prose_blocks.append(cleaned)
        block_words = markdown_word_count(cleaned)
        if block_words > 100:
            failures.append(f"Customer paragraph exceeds 100 words: {cleaned[:60]!r}")

    sentence_lengths: list[int] = []
    for block in prose_blocks:
        for sentence in re.split(r"(?<=[.!?])\s+", block):
            length = markdown_word_count(sentence)
            if length:
                sentence_lengths.append(length)
                if length > 45:
                    failures.append(
                        f"Customer sentence exceeds 45 words ({length}): {sentence[:60]!r}"
                    )
    if sentence_lengths:
        average = sum(sentence_lengths) / len(sentence_lengths)
        if average > 28:
            failures.append(
                f"Average customer sentence length is {average:.1f} words; maximum is 28"
            )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown", type=Path)
    parser.add_argument("--max-words", type=int, default=900)
    parser.add_argument("--min-words", type=int, default=250)
    args = parser.parse_args()
    if not args.markdown.exists():
        print(f"FAIL: Markdown does not exist: {args.markdown}", file=sys.stderr)
        return 1
    text = args.markdown.read_text(encoding="utf-8")
    failures = validate_customer_assessment(
        text, max_words=args.max_words, min_words=args.min_words
    )
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"OK: {args.markdown}")
    print(f"words={markdown_word_count(text)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
