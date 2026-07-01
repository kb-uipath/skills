#!/usr/bin/env python3
"""Calculate UiPath Document Understanding unit estimates.

Example:
  python du_estimate.py \
    --case low=150000,1 \
    --case base=197518,1 \
    --case high=240000,1 \
    --ai-rate 1 \
    --platform-rate 0.2
"""

from __future__ import annotations

import argparse
from decimal import Decimal, ROUND_HALF_UP


def decimal_arg(value: str) -> Decimal:
    try:
        return Decimal(value.replace(",", ""))
    except Exception as exc:  # pragma: no cover - argparse displays this text
        raise argparse.ArgumentTypeError(f"invalid decimal: {value}") from exc


def nonnegative_decimal_arg(value: str) -> Decimal:
    parsed = decimal_arg(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError(f"value cannot be negative: {value}")
    return parsed


def parse_case(value: str) -> tuple[str, Decimal, Decimal]:
    try:
        label, rest = value.split("=", 1)
        transactions, pages = rest.rsplit(",", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "case must be label=transactions,pages, for example base=197518,1"
        ) from exc

    label = label.strip()
    if not label:
        raise argparse.ArgumentTypeError("case label cannot be empty")

    transactions_value = nonnegative_decimal_arg(transactions.strip())
    pages_value = nonnegative_decimal_arg(pages.strip())
    return label, transactions_value, pages_value


def fmt(value: Decimal, places: str = "0.1") -> str:
    quantized = value.quantize(Decimal(places), rounding=ROUND_HALF_UP)
    if quantized == quantized.to_integral():
        return f"{int(quantized):,}"
    return f"{quantized:,.1f}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Calculate annual DU AI Unit and Platform Unit estimates."
    )
    parser.add_argument(
        "--case",
        action="append",
        type=parse_case,
        required=True,
        help="Scenario as label=transactions,pages. Repeat for low/base/high.",
    )
    parser.add_argument("--ai-rate", type=nonnegative_decimal_arg, default=Decimal("1"))
    parser.add_argument("--platform-rate", type=nonnegative_decimal_arg, default=Decimal("0.2"))
    parser.add_argument(
        "--extra-ai-rate",
        type=nonnegative_decimal_arg,
        default=Decimal("0"),
        help="Additional AI Units per page, e.g. for verified add-ons.",
    )
    parser.add_argument(
        "--extra-platform-rate",
        type=nonnegative_decimal_arg,
        default=Decimal("0"),
        help="Additional Platform Units per page, e.g. for verified add-ons.",
    )
    args = parser.parse_args()

    total_ai_rate = args.ai_rate + args.extra_ai_rate
    total_platform_rate = args.platform_rate + args.extra_platform_rate

    print("| Scenario | Transactions/year | Pages/transaction | AI Units/year | Platform Units/year |")
    print("|---|---:|---:|---:|---:|")
    for label, transactions, pages in args.case:
        annual_pages = transactions * pages
        ai_units = annual_pages * total_ai_rate
        platform_units = annual_pages * total_platform_rate
        print(
            f"| {label} | {fmt(transactions)} | {fmt(pages)} | "
            f"{fmt(ai_units)} | {fmt(platform_units)} |"
        )

    print()
    print(f"AI rate/page: {fmt(total_ai_rate)}")
    print(f"Platform rate/page: {fmt(total_platform_rate)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
