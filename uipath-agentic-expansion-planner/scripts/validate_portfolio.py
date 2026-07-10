#!/usr/bin/env python3
"""Validate v1 evidence and portfolio contracts and report outcome utility."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from portfolio_contracts import (
    ContractLoadError,
    evaluate_outcome_rubric,
    load_json_object,
    validate_portfolio,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate evidence references, scores, value math, deployment, and entitlements."
    )
    parser.add_argument("--evidence-ledger", required=True, type=Path)
    parser.add_argument("--portfolio", required=True, type=Path)
    parser.add_argument("--inventory-profile", type=Path, default=None)
    parser.add_argument("--rubric-json", type=Path, default=None)
    parser.add_argument("--min-specificity", type=float, default=0.0)
    parser.add_argument("--min-decision-utility", type=float, default=0.0)
    parser.add_argument("--min-pilot-actionability", type=float, default=0.0)
    return parser.parse_args()


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

    rubric = evaluate_outcome_rubric(portfolio, ledger)
    thresholds = {
        "specificity": args.min_specificity,
        "decision_utility": args.min_decision_utility,
        "pilot_actionability": args.min_pilot_actionability,
    }
    for key, minimum in thresholds.items():
        if not 0 <= minimum <= 100:
            failures.append(f"--min-{key.replace('_', '-')} must be from 0 to 100")
        elif rubric[key] < minimum:
            failures.append(f"outcome rubric {key} is {rubric[key]}, below required {minimum}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    if args.rubric_json:
        args.rubric_json.parent.mkdir(parents=True, exist_ok=True)
        args.rubric_json.write_text(
            json.dumps(rubric, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
    print(f"OK: {args.portfolio}")
    print(f"specificity={rubric['specificity']}")
    print(f"decision_utility={rubric['decision_utility']}")
    print(f"pilot_actionability={rubric['pilot_actionability']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
