#!/usr/bin/env python3
"""Validate a customer process map against a profile and ranked portfolio."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from assessment_contracts import format_failures, validate_process_map
from portfolio_contracts import ContractLoadError, load_json_object


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-profile", required=True, type=Path)
    parser.add_argument("--portfolio", required=True, type=Path)
    parser.add_argument("--process-map", required=True, type=Path)
    args = parser.parse_args()
    try:
        profile = load_json_object(args.inventory_profile, "inventory_profile")
        portfolio = load_json_object(args.portfolio, "portfolio")
        process_map = load_json_object(args.process_map, "process_map")
    except ContractLoadError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    failures = validate_process_map(process_map, profile, portfolio)
    if failures:
        print(format_failures(failures), file=sys.stderr)
        return 1
    print(f"OK: {args.process_map}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
