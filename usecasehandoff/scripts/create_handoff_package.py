#!/usr/bin/env python3
"""Create a deterministic use-case handoff package scaffold."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "templates"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "use-case"


def render_template(name: str, **values: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8").format(**values)


def package_files(title: str, account: str, date: str) -> dict[str, str]:
    values = {"title": title, "account": account, "date": date}
    return {
        "README.md": (
            f"# {title}\n\n"
            f"Account/team: {account}\n"
            f"Prepared: {date}\n\n"
            "Read order:\n"
            "1. `evidence-ledger.md`\n"
            "2. `delivery-plan.md`\n"
            "3. `risk-register.md`\n"
            "4. `cover-message.md`\n"
        ),
        "evidence-ledger.md": render_template("evidence-ledger-template.md", **values),
        "delivery-plan.md": render_template("delivery-plan-template.md", **values),
        "risk-register.md": (
            f"# Risk Register\n\nUse case: {title}\n\n"
            "| Risk | Impact | Mitigation | Owner | Status |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| Evidence gap | Delivery team may rework scope | Fill evidence ledger before routing |  | Open |\n"
        ),
        "cover-message.md": (
            f"# Cover Message\n\n"
            f"Attached is the handoff package for {title} ({account}). "
            "The package separates source-backed facts, assumptions, delivery plan, "
            "risks, and open validation questions.\n"
        ),
    }


def create_package(
    output_dir: Path,
    title: str,
    account: str,
    date: str,
    slug: str | None = None,
    force: bool = False,
) -> Path:
    package_dir = output_dir / f"{date}-{slugify(slug or title)}"
    if package_dir.exists() and not force:
        raise SystemExit(f"Package already exists: {package_dir}. Pass --force to overwrite.")
    package_dir.mkdir(parents=True, exist_ok=True)

    files = package_files(title, account, date)
    for filename, content in files.items():
        (package_dir / filename).write_text(content, encoding="utf-8")

    manifest = {
        "title": title,
        "account": account,
        "date": date,
        "files": sorted(files),
        "safety": "No connector writes, uploads, or external messages are performed by this scaffolder.",
    }
    (package_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return package_dir


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", required=True, help="Use case or automation title")
    parser.add_argument("--account", required=True, help="Customer, agency, or internal team")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"), help="Base output directory")
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="Package date, YYYY-MM-DD")
    parser.add_argument("--slug", help="Optional deterministic directory slug")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing scaffold")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    package_dir = create_package(
        args.output_dir.expanduser(),
        args.title,
        args.account,
        args.date,
        args.slug,
        args.force,
    )
    print(f"Handoff package: {package_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
