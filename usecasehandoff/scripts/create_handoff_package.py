#!/usr/bin/env python3
"""Create, migrate, and validate deterministic use-case handoff packages."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "templates"
PACKAGE_SCHEMA = "usecasehandoff.package"
PACKAGE_SCHEMA_VERSION = "1.0.0"
DEFAULT_CLASSIFICATION = "internal"
DEFAULT_RETENTION = (
    "Retain with customer/account handoff records; remove local working copies "
    "after routing or archival per policy."
)
NO_SEND_SAFETY = (
    "No connector writes, uploads, external messages, permission changes, or live "
    "system updates are performed by this scaffolder."
)
STABLE_PACKAGE_FILES = (
    "README.md",
    "executive-summary.md",
    "analysis.md",
    "evidence-ledger.md",
    "delivery-plan.md",
    "risk-register.md",
    "references.md",
    "cover-message.md",
    "manifest.json",
)
CONTENT_FILES = tuple(path for path in STABLE_PACKAGE_FILES if path != "manifest.json")
LEGACY_PACKAGE_FILES = {
    "README.md",
    "evidence-ledger.md",
    "delivery-plan.md",
    "risk-register.md",
    "cover-message.md",
    "manifest.json",
}
ALLOWED_STATUSES = {"scaffold", "draft", "ready", "routed", "archived"}
ALLOWED_CLASSIFICATIONS = {"public", "internal", "confidential", "restricted"}
DELIVERY_PLAN_HEADINGS = (
    "## Current State",
    "## Target Workflow",
    "## Systems and Integrations",
    "## Delivery Phases",
    "## Test Strategy",
    "## First Sprint Backlog",
    "## Next Action",
)
ANALYSIS_HEADINGS = (
    "## Current State",
    "## Process Pain Points",
    "## Systems And Constraints",
    "## Value Drivers",
    "## Assumptions And Validation Questions",
)
PLACEHOLDER_RE = re.compile(
    r"(\bTODO\b|\bTBD\b|\bPLACEHOLDER\b|\bOWNER NEEDED\b|\[TODO[^\]]*\]|"
    r"Source-backed / Derived / Estimate / Open)",
    re.IGNORECASE,
)
ISO_TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
EVIDENCE_TIERS = {"Source-backed", "Derived", "Estimate", "Open"}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def scaffold_time(date: str) -> str:
    return f"{date}T00:00:00Z"


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
            "Package status is controlled by `manifest.json`. A new scaffold is "
            "not route-ready until the package passes ready validation.\n\n"
            "Read order:\n"
            "1. `executive-summary.md`\n"
            "2. `analysis.md`\n"
            "3. `evidence-ledger.md`\n"
            "4. `delivery-plan.md`\n"
            "5. `risk-register.md`\n"
            "6. `references.md`\n"
            "7. `cover-message.md`\n"
        ),
        "executive-summary.md": (
            f"# Executive Summary\n\nUse case: {title}\nAccount/team: {account}\nPrepared: {date}\n\n"
            "## Business Problem\n\n[TODO: State the operational problem with cited facts.]\n\n"
            "## Operational Impact\n\n[TODO: Quantify the impact or label estimates explicitly.]\n\n"
            "## Solution Workflow\n\n[TODO: Summarize the target workflow in delivery-team language.]\n\n"
            "## Decision Ask\n\n[TODO: Name the decision, owner, and required date.]\n"
        ),
        "analysis.md": (
            f"# Analysis\n\nUse case: {title}\nAccount/team: {account}\nPrepared: {date}\n\n"
            "## Current State\n\n[TODO: Describe the current process and cite evidence IDs.]\n\n"
            "## Process Pain Points\n\n[TODO: Describe verified pain points and affected users.]\n\n"
            "## Systems And Constraints\n\n[TODO: List systems, integrations, policy, data, and deployment constraints.]\n\n"
            "## Value Drivers\n\n[TODO: State measurable value drivers and label estimates.]\n\n"
            "## Assumptions And Validation Questions\n\n"
            "[TODO: Separate assumptions from facts and assign validation questions.]\n"
        ),
        "evidence-ledger.md": render_template("evidence-ledger-template.md", **values),
        "delivery-plan.md": render_template("delivery-plan-template.md", **values),
        "risk-register.md": (
            f"# Risk Register\n\nUse case: {title}\n\n"
            "| Risk | Impact | Mitigation | Owner | Status |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| Evidence gap | Delivery team may rework scope | Fill evidence ledger before routing | OWNER NEEDED | Open |\n"
        ),
        "references.md": (
            f"# References\n\nUse case: {title}\n\n"
            "| Source | Type | Date | Link or path | Claims supported | Owner |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| TODO source | chat/email/file/web/vendor docs | {date} |  |  | OWNER NEEDED |\n"
        ),
        "cover-message.md": (
            f"# Cover Message\n\n"
            f"Attached is the handoff package for {title} ({account}). "
            "The package separates source-backed facts, assumptions, delivery plan, "
            "risks, and open validation questions.\n\n"
            "Next action: [TODO: State exactly who should do what next.]\n"
        ),
    }


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def infer_metadata(package_dir: Path, manifest: dict[str, object] | None = None) -> dict[str, str]:
    manifest = manifest or {}
    title = str(manifest.get("title") or package_dir.name)
    account = str(manifest.get("account") or "Unspecified")
    date = str(manifest.get("package_date") or manifest.get("date") or dt.date.today().isoformat())
    generated_at = str(manifest.get("generated_at") or scaffold_time(date))
    classification = str(manifest.get("classification") or DEFAULT_CLASSIFICATION)
    retention = str(manifest.get("retention") or DEFAULT_RETENTION)
    status = str(manifest.get("status") or "scaffold")
    return {
        "title": title,
        "account": account,
        "date": date,
        "generated_at": generated_at,
        "classification": classification,
        "retention": retention,
        "status": status,
    }


def build_manifest(
    package_dir: Path,
    title: str,
    account: str,
    date: str,
    classification: str,
    retention: str,
    status: str,
    generated_at: str | None = None,
    last_verified_at: str | None = None,
) -> dict[str, object]:
    hashes = {
        filename: file_hash(package_dir / filename)
        for filename in CONTENT_FILES
        if (package_dir / filename).exists()
    }
    return {
        "schema": PACKAGE_SCHEMA,
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "title": title,
        "account": account,
        "package_date": date,
        "status": status,
        "classification": classification,
        "retention": retention,
        "generated_at": generated_at or scaffold_time(date),
        "last_verified_at": last_verified_at,
        "files": list(STABLE_PACKAGE_FILES),
        "hashes": hashes,
        "no_send": True,
        "safety": NO_SEND_SAFETY,
    }


def write_manifest(
    package_dir: Path,
    title: str,
    account: str,
    date: str,
    classification: str,
    retention: str,
    status: str,
    generated_at: str | None = None,
    last_verified_at: str | None = None,
) -> None:
    manifest = build_manifest(
        package_dir,
        title,
        account,
        date,
        classification,
        retention,
        status,
        generated_at,
        last_verified_at,
    )
    (package_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def create_package(
    output_dir: Path,
    title: str,
    account: str,
    date: str,
    slug: str | None = None,
    force: bool = False,
    classification: str = DEFAULT_CLASSIFICATION,
    retention: str = DEFAULT_RETENTION,
    status: str = "scaffold",
) -> Path:
    package_dir = output_dir / f"{date}-{slugify(slug or title)}"
    if package_dir.exists() and not force:
        raise SystemExit(f"Package already exists: {package_dir}. Pass --force to overwrite.")
    package_dir.mkdir(parents=True, exist_ok=True)

    files = package_files(title, account, date)
    for filename, content in files.items():
        (package_dir / filename).write_text(content, encoding="utf-8")

    write_manifest(package_dir, title, account, date, classification, retention, status)
    return package_dir


def load_manifest(path: Path, errors: list[str]) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"manifest.json is invalid JSON: {exc}")
        return None
    if not isinstance(data, dict):
        errors.append("manifest.json must be a JSON object")
        return None
    return data


def is_placeholder(value: str | None) -> bool:
    if value is None:
        return True
    stripped = value.strip()
    return not stripped or bool(PLACEHOLDER_RE.search(stripped))


def section_body(text: str, heading: str) -> str:
    marker = f"{heading}\n"
    start = text.find(marker)
    if start == -1:
        return ""
    start += len(marker)
    next_heading = text.find("\n## ", start)
    if next_heading == -1:
        return text[start:].strip()
    return text[start:next_heading].strip()


def table_rows(text: str) -> list[tuple[list[str], int]]:
    rows: list[tuple[list[str], int]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells):
            continue
        rows.append((cells, line_number))
    return rows


def validate_manifest(package_dir: Path, level: str, errors: list[str]) -> None:
    manifest_path = package_dir / "manifest.json"
    if not manifest_path.exists():
        errors.append("manifest.json missing; run migration before validation")
        return
    manifest = load_manifest(manifest_path, errors)
    if manifest is None:
        return

    if manifest.get("schema") != PACKAGE_SCHEMA:
        errors.append(
            "manifest.json schema mismatch; run --migrate for legacy packages or "
            "--refresh-manifest after editing"
        )
    if manifest.get("schema_version") != PACKAGE_SCHEMA_VERSION:
        errors.append(f"manifest.json schema_version must be {PACKAGE_SCHEMA_VERSION}")

    files = manifest.get("files")
    if files != list(STABLE_PACKAGE_FILES):
        errors.append("manifest.json files must list the stable nine-file contract in order")

    status = str(manifest.get("status") or "")
    if status not in ALLOWED_STATUSES:
        errors.append("manifest.json status must be one of: " + ", ".join(sorted(ALLOWED_STATUSES)))
    if level == "ready" and status != "ready":
        errors.append("manifest.json status must be 'ready' for ready validation")

    classification = str(manifest.get("classification") or "")
    if classification not in ALLOWED_CLASSIFICATIONS:
        errors.append(
            "manifest.json classification must be one of: "
            + ", ".join(sorted(ALLOWED_CLASSIFICATIONS))
        )
    if is_placeholder(str(manifest.get("retention") or "")):
        errors.append("manifest.json retention must be explicit")
    if not ISO_TIME_RE.match(str(manifest.get("generated_at") or "")):
        errors.append("manifest.json generated_at must be UTC ISO time ending in Z")
    if manifest.get("no_send") is not True:
        errors.append("manifest.json no_send must be true")
    safety = str(manifest.get("safety") or "")
    for required in ("No connector writes", "uploads", "external messages"):
        if required not in safety:
            errors.append("manifest.json safety must document no-send/no-upload boundaries")
            break

    hashes = manifest.get("hashes")
    if not isinstance(hashes, dict):
        errors.append("manifest.json hashes must be an object keyed by package file")
        return
    expected_hash_keys = set(CONTENT_FILES)
    actual_hash_keys = {str(key) for key in hashes}
    if actual_hash_keys != expected_hash_keys:
        errors.append("manifest.json hashes must cover every non-manifest stable file")
        return
    for filename in CONTENT_FILES:
        path = package_dir / filename
        if not path.exists():
            continue
        if hashes.get(filename) != file_hash(path):
            errors.append(f"manifest.json hash mismatch for {filename}; run --refresh-manifest")


def validate_scaffold(package_dir: Path) -> list[str]:
    errors: list[str] = []
    if not package_dir.exists() or not package_dir.is_dir():
        return [f"package directory not found: {package_dir}"]

    present = {path.name for path in package_dir.iterdir() if path.is_file()}
    if LEGACY_PACKAGE_FILES <= present and set(STABLE_PACKAGE_FILES) - present:
        errors.append(
            "legacy six-file package detected; run "
            "`python3 usecasehandoff/scripts/create_handoff_package.py --migrate "
            f"{package_dir}` before validating"
        )
    missing = sorted(set(STABLE_PACKAGE_FILES) - present)
    if missing:
        errors.append("missing required file(s): " + ", ".join(missing))
    unexpected = sorted(present - set(STABLE_PACKAGE_FILES))
    if unexpected:
        errors.append("unexpected package file(s): " + ", ".join(unexpected))

    evidence = (package_dir / "evidence-ledger.md")
    if evidence.exists():
        text = evidence.read_text(encoding="utf-8")
        if "| Claim ID |" not in text or "| Evidence tier |" not in text:
            errors.append("evidence-ledger.md must include the evidence ledger table")
        if "## Open Evidence Gaps" not in text:
            errors.append("evidence-ledger.md must include Open Evidence Gaps")

    delivery = (package_dir / "delivery-plan.md")
    if delivery.exists():
        text = delivery.read_text(encoding="utf-8")
        for heading in DELIVERY_PLAN_HEADINGS:
            if heading not in text:
                errors.append(f"delivery-plan.md missing heading: {heading}")

    analysis = package_dir / "analysis.md"
    if analysis.exists():
        text = analysis.read_text(encoding="utf-8")
        for heading in ANALYSIS_HEADINGS:
            if heading not in text:
                errors.append(f"analysis.md missing heading: {heading}")

    for filename in ("executive-summary.md", "analysis.md", "references.md", "cover-message.md"):
        if (package_dir / filename).exists() and not (package_dir / filename).read_text(encoding="utf-8").strip():
            errors.append(f"{filename} must not be empty")

    validate_manifest(package_dir, "scaffold", errors)

    return errors


def validate_ready(package_dir: Path) -> list[str]:
    errors = validate_scaffold(package_dir)
    if errors:
        return errors

    for filename in CONTENT_FILES:
        text = (package_dir / filename).read_text(encoding="utf-8")
        if PLACEHOLDER_RE.search(text):
            errors.append(f"{filename} contains scaffold placeholder text")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if line.strip() == "-":
                errors.append(f"{filename}:{line_number}: blank bullet placeholder")

    validate_manifest(package_dir, "ready", errors)

    evidence_rows = table_rows((package_dir / "evidence-ledger.md").read_text(encoding="utf-8"))
    headers = None
    cited_claims = 0
    for cells, line_number in evidence_rows:
        if "Claim ID" in cells:
            headers = cells
            if "Owner" not in headers:
                errors.append("evidence-ledger.md must include an Owner column for ready validation")
            continue
        if not headers:
            continue
        if len(cells) < len(headers):
            cells.extend([""] * (len(headers) - len(cells)))
        row = dict(zip(headers, cells))
        if not any(row.values()):
            continue
        tier = row.get("Evidence tier", "")
        if tier not in EVIDENCE_TIERS:
            errors.append(f"evidence-ledger.md:{line_number}: invalid evidence tier")
            continue
        if is_placeholder(row.get("Claim or metric")):
            errors.append(f"evidence-ledger.md:{line_number}: claim or metric is empty")
        if is_placeholder(row.get("Owner")):
            errors.append(f"evidence-ledger.md:{line_number}: owner is empty")
        if tier != "Open":
            if is_placeholder(row.get("Source title/link")) or is_placeholder(row.get("Source date")):
                errors.append(f"evidence-ledger.md:{line_number}: non-open claim is uncited")
            else:
                cited_claims += 1
    if cited_claims == 0:
        errors.append("evidence-ledger.md must include at least one cited non-open claim")

    for filename in ("delivery-plan.md", "risk-register.md", "references.md"):
        rows = table_rows((package_dir / filename).read_text(encoding="utf-8"))
        headers = None
        for cells, line_number in rows:
            if "Owner" in cells:
                headers = cells
                continue
            if not headers:
                continue
            if len(cells) < len(headers):
                cells.extend([""] * (len(headers) - len(cells)))
            row = dict(zip(headers, cells))
            if not any(row.values()):
                continue
            owner = row.get("Owner")
            if owner is not None and is_placeholder(owner):
                errors.append(f"{filename}:{line_number}: owner is empty")
            acceptance = row.get("Acceptance criteria")
            if acceptance is not None and is_placeholder(acceptance):
                errors.append(f"{filename}:{line_number}: acceptance criteria is empty")

    delivery_text = (package_dir / "delivery-plan.md").read_text(encoding="utf-8")
    if is_placeholder(section_body(delivery_text, "## Test Strategy")):
        errors.append("delivery-plan.md Test Strategy must be populated")
    if is_placeholder(section_body(delivery_text, "## First Sprint Backlog")):
        errors.append("delivery-plan.md First Sprint Backlog must be populated")
    if is_placeholder(section_body(delivery_text, "## Next Action")):
        errors.append("delivery-plan.md Next Action must be populated")

    cover_text = (package_dir / "cover-message.md").read_text(encoding="utf-8")
    next_action = re.search(r"^Next action:\s*(.+)$", cover_text, re.MULTILINE)
    if not next_action or is_placeholder(next_action.group(1)) or PLACEHOLDER_RE.search(cover_text):
        errors.append("cover-message.md must include a concrete next action")

    return errors


def validate_package(package_dir: Path, level: str = "ready") -> list[str]:
    if level == "scaffold":
        return validate_scaffold(package_dir)
    if level == "ready":
        return validate_ready(package_dir)
    return [f"unknown validation level: {level}"]


def migrate_package(
    package_dir: Path,
    classification: str = DEFAULT_CLASSIFICATION,
    retention: str = DEFAULT_RETENTION,
    status: str = "scaffold",
) -> Path:
    if not package_dir.exists() or not package_dir.is_dir():
        raise SystemExit(f"Package directory not found: {package_dir}")

    old_manifest: dict[str, object] | None = None
    manifest_path = package_dir / "manifest.json"
    if manifest_path.exists():
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                old_manifest = loaded
        except json.JSONDecodeError:
            old_manifest = None
    metadata = infer_metadata(package_dir, old_manifest)
    title = metadata["title"]
    account = metadata["account"]
    date = metadata["date"]

    for filename, content in package_files(title, account, date).items():
        path = package_dir / filename
        if not path.exists():
            path.write_text(content, encoding="utf-8")

    delivery_path = package_dir / "delivery-plan.md"
    delivery_text = delivery_path.read_text(encoding="utf-8")
    for heading in DELIVERY_PLAN_HEADINGS:
        if heading not in delivery_text:
            delivery_text += f"\n\n{heading}\n\n[TODO: Complete this section after migration.]\n"
    delivery_path.write_text(delivery_text, encoding="utf-8")

    evidence_path = package_dir / "evidence-ledger.md"
    evidence_text = evidence_path.read_text(encoding="utf-8")
    if "## Open Evidence Gaps" not in evidence_text:
        evidence_text += "\n\n## Open Evidence Gaps\n\n- TODO gap with owner\n"
    evidence_path.write_text(evidence_text, encoding="utf-8")

    write_manifest(
        package_dir,
        title,
        account,
        date,
        classification or metadata["classification"],
        retention or metadata["retention"],
        status or metadata["status"],
        metadata["generated_at"],
    )
    return package_dir


def refresh_manifest(
    package_dir: Path,
    status: str | None = None,
    classification: str | None = None,
    retention: str | None = None,
) -> Path:
    if not package_dir.exists() or not package_dir.is_dir():
        raise SystemExit(f"Package directory not found: {package_dir}")
    errors = validate_scaffold(package_dir)
    non_hash_errors = [error for error in errors if "hash mismatch" not in error]
    if non_hash_errors:
        raise SystemExit("Cannot refresh manifest until scaffold validation passes:\n" + "\n".join(non_hash_errors))

    manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
    metadata = infer_metadata(package_dir, manifest)
    next_status = status or metadata["status"]
    verified_at = utc_now() if next_status == "ready" else manifest.get("last_verified_at")
    write_manifest(
        package_dir,
        metadata["title"],
        metadata["account"],
        metadata["date"],
        classification or metadata["classification"],
        retention or metadata["retention"],
        next_status,
        metadata["generated_at"],
        str(verified_at) if verified_at else None,
    )
    return package_dir


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", help="Use case or automation title")
    parser.add_argument("--account", help="Customer, agency, or internal team")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"), help="Base output directory")
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="Package date, YYYY-MM-DD")
    parser.add_argument("--slug", help="Optional deterministic directory slug")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing scaffold")
    parser.add_argument("--classification", choices=sorted(ALLOWED_CLASSIFICATIONS))
    parser.add_argument("--retention")
    parser.add_argument("--status", choices=sorted(ALLOWED_STATUSES), help="Manifest status for create, migrate, or refresh")
    parser.add_argument("--validate", type=Path, help="Validate an existing handoff package and exit")
    parser.add_argument(
        "--level",
        choices=("ready", "scaffold"),
        default="ready",
        help="Validation level for --validate. Default: ready",
    )
    parser.add_argument("--migrate", type=Path, help="Migrate a legacy package to the nine-file contract")
    parser.add_argument("--refresh-manifest", type=Path, help="Refresh manifest hashes/status after package edits")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.validate:
        errors = validate_package(args.validate.expanduser(), args.level)
        if errors:
            for error in errors:
                print(f"error: {error}", file=sys.stderr)
            return 1
        print(f"Handoff package validated at {args.level} level: {args.validate}")
        return 0

    if args.migrate:
        package_dir = migrate_package(
            args.migrate.expanduser(),
            args.classification or "",
            args.retention or "",
            args.status or "scaffold",
        )
        print(f"Handoff package migrated: {package_dir}")
        return 0

    if args.refresh_manifest:
        package_dir = refresh_manifest(
            args.refresh_manifest.expanduser(),
            args.status,
            args.classification,
            args.retention,
        )
        print(f"Handoff manifest refreshed: {package_dir / 'manifest.json'}")
        return 0

    if not args.title or not args.account:
        print(
            "error: --title and --account are required unless --validate, --migrate, or "
            "--refresh-manifest is used",
            file=sys.stderr,
        )
        return 1

    package_dir = create_package(
        args.output_dir.expanduser(),
        args.title,
        args.account,
        args.date,
        args.slug,
        args.force,
        args.classification or DEFAULT_CLASSIFICATION,
        args.retention or DEFAULT_RETENTION,
        args.status or "scaffold",
    )
    print(f"Handoff package: {package_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
