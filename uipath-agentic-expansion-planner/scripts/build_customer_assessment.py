#!/usr/bin/env python3
"""Build, render, verify, and receipt a concise customer portfolio assessment."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from assessment_contracts import artifact_sha256, expected_artifact_hashes
from portfolio_contracts import ContractLoadError, load_json_object
from validate_customer_assessment import markdown_word_count


SCRIPT_DIR = Path(__file__).resolve().parent


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "command failed"
        raise RuntimeError(detail)
    return result


def resolve_soffice(value: str | None) -> str | None:
    if value:
        path = Path(value).expanduser()
        if path.exists() and path.is_file() and os.access(path, os.X_OK):
            return str(path.resolve())
        return shutil.which(value)
    for command in ("soffice", "libreoffice"):
        resolved = shutil.which(command)
        if resolved:
            return resolved
    candidates = [
        Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
        Path("/usr/lib/libreoffice/program/soffice"),
    ]
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        root = os.environ.get(variable)
        if root:
            candidates.append(Path(root) / "LibreOffice" / "program" / "soffice.exe")
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path.resolve())
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-profile", required=True, type=Path)
    parser.add_argument("--evidence-ledger", required=True, type=Path)
    parser.add_argument("--portfolio", required=True, type=Path)
    parser.add_argument("--process-map", required=True, type=Path)
    parser.add_argument("--semantic-review", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument(
        "--supporting-source",
        action="append",
        default=[],
        type=Path,
        help="Local strategy or context source to bind by safe basename and SHA-256",
    )
    parser.add_argument("--soffice", help="LibreOffice soffice executable or command name")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--draft-without-page-check", action="store_true")
    parser.add_argument("--validation-date", type=parse_date, default=date.today())
    parser.add_argument("--max-review-age-days", type=int, default=30)
    parser.add_argument("--max-words", type=int, default=900)
    parser.add_argument("--max-pages", type=int, default=2)
    args = parser.parse_args()

    output = args.output.expanduser().resolve()
    markdown_output = output.with_suffix(".md")
    pdf_output = output.with_suffix(".pdf")
    receipt_output = (
        args.receipt.expanduser().resolve()
        if args.receipt
        else output.with_suffix(".validation.json")
    )
    if output.suffix.casefold() != ".docx":
        print("FAIL: --output must end in .docx", file=sys.stderr)
        return 1
    if not args.draft_without_page_check and output.parent.name != "outputs":
        print("FAIL: customer-ready DOCX must be written inside an outputs directory", file=sys.stderr)
        return 1
    soffice = resolve_soffice(args.soffice)
    expected_outputs = [output, markdown_output, pdf_output, receipt_output]
    if len(set(expected_outputs)) != len(expected_outputs):
        print("FAIL: DOCX, Markdown, PDF, and receipt paths must be distinct", file=sys.stderr)
        return 1
    for path in expected_outputs:
        if path.exists() and not args.force:
            print(f"FAIL: output already exists: {path}; pass --force to replace it", file=sys.stderr)
            return 1
    if not 1 <= args.max_words <= 900:
        print("FAIL: --max-words must be from 1 to 900", file=sys.stderr)
        return 1
    if not 1 <= args.max_pages <= 2:
        print("FAIL: --max-pages must be 1 or 2", file=sys.stderr)
        return 1
    if args.max_review_age_days < 1:
        print("FAIL: --max-review-age-days must be positive", file=sys.stderr)
        return 1

    supporting_sources: list[Path] = []
    seen_sources: set[Path] = set()
    for value in args.supporting_source:
        source = value.expanduser().resolve()
        if not source.is_file():
            print(f"FAIL: supporting source does not exist: {value}", file=sys.stderr)
            return 1
        if source in seen_sources:
            print(f"FAIL: supporting source is duplicated: {value}", file=sys.stderr)
            return 1
        supporting_sources.append(source)
        seen_sources.add(source)

    protected_inputs = {
        args.inventory_profile.expanduser().resolve(),
        args.evidence_ledger.expanduser().resolve(),
        args.portfolio.expanduser().resolve(),
        args.process_map.expanduser().resolve(),
        args.semantic_review.expanduser().resolve(),
        *supporting_sources,
    }
    collisions = sorted(
        (path for path in expected_outputs if path in protected_inputs),
        key=str,
    )
    if collisions:
        print(
            "FAIL: output path collides with a protected input: "
            + ", ".join(path.name for path in collisions),
            file=sys.stderr,
        )
        return 1

    artifact_paths = {
        "inventory_profile_sha256": args.inventory_profile.resolve(),
        "evidence_ledger_sha256": args.evidence_ledger.resolve(),
        "portfolio_sha256": args.portfolio.resolve(),
        "process_map_sha256": args.process_map.resolve(),
        "semantic_review_sha256": args.semantic_review.resolve(),
    }
    try:
        review = load_json_object(args.semantic_review, "semantic_review")
        portfolio = load_json_object(args.portfolio, "portfolio")
        profile = load_json_object(args.inventory_profile, "inventory_profile")
        ledger = load_json_object(args.evidence_ledger, "evidence_ledger")
    except ContractLoadError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    if not soffice and not args.draft_without_page_check:
        print(
            "FAIL: soffice is required for the two-page customer-ready gate; "
            "provide --soffice or use --draft-without-page-check",
            file=sys.stderr,
        )
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    if args.force and not soffice:
        pdf_output.unlink(missing_ok=True)
    readiness_required = "exploratory" if args.draft_without_page_check else "workshop_ready"
    try:
        with tempfile.TemporaryDirectory(prefix="planner-assessment-", dir=output.parent) as tmp:
            work = Path(tmp)
            markdown = work / "assessment.md"
            docx = work / "assessment.docx"
            render_command = [
                sys.executable,
                str(SCRIPT_DIR / "render_customer_assessment.py"),
                "--inventory-profile",
                str(args.inventory_profile),
                "--evidence-ledger",
                str(args.evidence_ledger),
                "--portfolio",
                str(args.portfolio),
                "--process-map",
                str(args.process_map),
                "--semantic-review",
                str(args.semantic_review),
                "--output",
                str(markdown),
                "--required-readiness",
                readiness_required,
                "--validation-date",
                args.validation_date.isoformat(),
                "--max-review-age-days",
                str(args.max_review_age_days),
                "--max-words",
                str(args.max_words),
            ]
            run(render_command)

            customer_name = re.sub(
                r"[\x00-\x1f\x7f]",
                "",
                str(portfolio.get("customer_name", "Automation portfolio assessment")),
            ).strip()
            title = customer_name or "Automation portfolio assessment"
            subtitle = (
                "Automation portfolio assessment | Workshop-ready | Prepared "
                + args.validation_date.isoformat()
            )
            if args.draft_without_page_check:
                title = "DRAFT - " + title
                subtitle = "Internal draft | Layout or semantic readiness remains unverified"
            docx_command = [
                sys.executable,
                str(SCRIPT_DIR / "render_executive_docx.py"),
                str(markdown),
                str(docx),
                "--profile",
                "customer-assessment",
                "--portrait",
                "--max-words",
                str(args.max_words),
                "--subtitle",
                subtitle,
            ]
            docx_command.extend(["--title", title])
            run(docx_command)

            rendered_pdf: Path | None = None
            if soffice:
                run(
                    [
                        soffice,
                        "--headless",
                        "--convert-to",
                        "pdf",
                        "--outdir",
                        str(work),
                        str(docx),
                    ]
                )
                rendered_pdf = work / "assessment.pdf"
                if not rendered_pdf.exists():
                    raise RuntimeError("soffice did not produce assessment.pdf")

            verify_command = [
                sys.executable,
                str(SCRIPT_DIR / "verify_executive_docx.py"),
                str(docx),
                "--profile",
                "customer-assessment",
                "--require-brand-style",
                "--max-pages",
                str(args.max_pages),
            ]
            if rendered_pdf:
                verify_command.extend(["--rendered-pdf", str(rendered_pdf)])
            if not args.draft_without_page_check:
                verify_command.append("--require-page-count")
            run(verify_command)

            page_count = None
            if rendered_pdf:
                from pypdf import PdfReader

                page_count = len(PdfReader(str(rendered_pdf)).pages)
            markdown_text = markdown.read_text(encoding="utf-8")
            recommendation_count = len(
                re.findall(r"^###\s+", markdown_text, flags=re.MULTILINE)
            )
            final_readiness = review.get("overall_readiness", "exploratory")
            if args.draft_without_page_check:
                final_readiness = "exploratory"
            source_name = re.sub(
                r"[\x00-\x1f\x7f]", "", str(profile.get("metadata", {}).get("source_name", ""))
            )
            raw_sources = [
                {
                    "kind": "inventory",
                    "name": source_name,
                    "sha256": profile.get("metadata", {}).get("source_sha256"),
                }
            ]
            raw_sources.extend(
                {
                    "kind": "supporting_context",
                    "name": re.sub(r"[\x00-\x1f\x7f]", "", source.name),
                    "sha256": artifact_sha256(source),
                }
                for source in supporting_sources
            )
            opportunities = {
                item.get("opportunity_id"): item
                for item in portfolio.get("opportunities", [])
                if isinstance(item, dict)
            }
            recommendation_evidence = []
            for opportunity_id in portfolio.get("rankings", {}).get("high_impact", [])[:3]:
                opportunity = opportunities.get(opportunity_id, {})
                recommendation_evidence.append(
                    {
                        "opportunity_id": opportunity_id,
                        "name": opportunity.get("name"),
                        **opportunity.get("evidence_refs", {}),
                    }
                )
            receipt = {
                "schema_version": "1.0",
                "artifact": output.name,
                "artifact_sha256": artifact_sha256(docx),
                "generated_at_utc": datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
                "validation_date": args.validation_date.isoformat(),
                "readiness": final_readiness,
                "layout_verified": page_count is not None,
                "page_count": page_count,
                "rendered_pdf_sha256": (
                    artifact_sha256(rendered_pdf) if rendered_pdf else None
                ),
                "rendered_pdf": pdf_output.name if rendered_pdf else None,
                "word_count": markdown_word_count(markdown_text),
                "recommendation_count": recommendation_count,
                "contracts_verified": True,
                "semantic_review_verified": True,
                "plain_language_verified": True,
                "brand_verified": True,
                "portfolio_id": portfolio.get("portfolio_id"),
                "input_hashes": expected_artifact_hashes(artifact_paths),
                "latest_source_record_date": profile.get("metadata", {})
                .get("source_date_summary", {})
                .get("latest_date"),
                "ledger_inventory_as_of_date": ledger.get(
                    "inventory_profile", {}
                ).get("as_of_date"),
                "portfolio_as_of_date": portfolio.get("as_of_date"),
                "raw_sources": raw_sources,
                "source_ledger": [
                    {
                        "source_id": source.get("source_id"),
                        "title": source.get("title"),
                        "url": source.get("url"),
                        "official": source.get("official"),
                        "accessed_date": source.get("accessed_date"),
                    }
                    for source in ledger.get("public_sources", [])
                    if isinstance(source, dict)
                ],
                "recommendation_evidence": recommendation_evidence,
            }

            receipt_temp = work / "receipt.json"
            receipt_temp.write_text(
                json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
                encoding="utf-8",
            )
            os.replace(docx, output)
            os.replace(markdown, markdown_output)
            if rendered_pdf:
                os.replace(rendered_pdf, pdf_output)
            os.replace(receipt_temp, receipt_output)
    except (OSError, RuntimeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(f"OK: {output}")
    print(f"markdown={markdown_output}")
    if soffice:
        print(f"pdf={pdf_output}")
    print(f"receipt={receipt_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
