#!/usr/bin/env python3
"""Calculate deterministic v1 portfolio scores and rankings."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from portfolio_contracts import (
    ContractLoadError,
    load_json_object,
    score_portfolio,
    validate_portfolio,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calculate v1 high-impact and POC scores into a new portfolio JSON file."
    )
    parser.add_argument("--evidence-ledger", required=True, type=Path)
    parser.add_argument("--portfolio", required=True, type=Path, help="Unscored or stale v1 portfolio")
    parser.add_argument("--output", required=True, type=Path, help="New scored portfolio path")
    parser.add_argument("--inventory-profile", type=Path, default=None)
    parser.add_argument("--force", action="store_true", help="Replace an existing output file")
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

    input_path = args.portfolio.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    if input_path == output_path:
        print(
            "FAIL: refusing to overwrite the input portfolio. Write to a new path, validate it, "
            "then replace the legacy artifact deliberately.",
            file=sys.stderr,
        )
        return 1
    if output_path.exists() and not args.force:
        print(f"FAIL: output already exists: {output_path}; pass --force to replace it", file=sys.stderr)
        return 1

    failures = validate_portfolio(portfolio, ledger, profile=profile, require_derived=False)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    scored = score_portfolio(portfolio)
    failures = validate_portfolio(scored, ledger, profile=profile, require_derived=True)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(scored, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    print(f"OK: wrote deterministic portfolio to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
