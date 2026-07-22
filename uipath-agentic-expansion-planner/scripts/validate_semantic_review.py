#!/usr/bin/env python3
"""Validate a freshness-bound semantic review and derived readiness."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from assessment_contracts import (
    expected_artifact_hashes,
    format_failures,
    validate_process_map,
    validate_semantic_review,
)
from portfolio_contracts import ContractLoadError, load_json_object, validate_portfolio


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-profile", required=True, type=Path)
    parser.add_argument("--evidence-ledger", required=True, type=Path)
    parser.add_argument("--portfolio", required=True, type=Path)
    parser.add_argument("--process-map", required=True, type=Path)
    parser.add_argument("--semantic-review", required=True, type=Path)
    parser.add_argument("--required-readiness", default="exploratory")
    parser.add_argument("--max-age-days", type=int, default=30)
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
            max_age_days=args.max_age_days,
            required_readiness=args.required_readiness,
        )
    )
    if failures:
        print(format_failures(failures), file=sys.stderr)
        return 1
    print(f"OK: {args.semantic_review}")
    print(f"readiness={review['overall_readiness']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
