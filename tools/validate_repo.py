#!/usr/bin/env python3
"""Validate repository-level skill packaging contracts."""

from __future__ import annotations

import argparse
import ipaddress
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
RAW_URL_RE = re.compile(r"\bhttps?://[^\s)>\"]+")
LOCAL_PATH_PATTERNS = (
    re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    re.compile(r"/home/[A-Za-z0-9._-]+/"),
    re.compile(r"[A-Za-z]:\\Users\\[A-Za-z0-9._-]+\\"),
    re.compile(r"/(?:private/)?var/folders/[A-Za-z0-9._/-]+"),
    re.compile(r"/(?:private/)?tmp/[A-Za-z0-9._/-]+"),
    re.compile(r"/Volumes/[A-Za-z0-9._ -]+/[A-Za-z0-9._/-]+"),
)
SECRET_PATTERNS = (
    re.compile(
        r"(?i)\b(api[_-]?key|client[_-]?secret|password|secret|token|private[_-]?key)"
        r"\s*[:=]\s*['\"]?([A-Za-z0-9_./+=-]{16,})"
    ),
    re.compile(r"(?i)\bBearer\s+([A-Za-z0-9._~+/=-]{20,})"),
    re.compile(r"-----BEGIN (?:RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
)
PLACEHOLDER_RE = re.compile(
    r"(?i)(placeholder|example|fake|redacted|changeme|your[_-]?|xxx|dummy|sample|<[^>]+>)"
)
DOC_HEADINGS = ("## Inputs", "## Prompt", "## Safety", "## Validation")
STANDARD_DOC_CONCEPTS = (
    ("runtime and dependencies", re.compile(r"(?im)^## Runtime And Dependencies\s*$")),
    (
        "versioned input/output contract",
        re.compile(
            r"(?is)(?:schema|contract).{0,160}(?:version|v1|@1|1\.0|2\.0)"
            r"|(?:version|v1|@1|1\.0|2\.0).{0,160}(?:schema|contract)"
        ),
    ),
    ("runnable example", re.compile(r"(?im)^## Runnable Example\s*$")),
    ("failure recovery", re.compile(r"(?im)^## .*Recovery\s*$")),
    (
        "classification and retention",
        re.compile(r"(?im)^## .*Classification.*Retention\s*$|^## .*Retention.*Classification\s*$"),
    ),
    ("known limitations", re.compile(r"(?im)^## (?:Known )?Limitations\s*$")),
    ("certification status", re.compile(r"(?im)^## .*Certification.*\s*$|^## Status\s*$")),
    ("last-verified date", re.compile(r"(?is)last verified.{0,50}\d{4}-\d{2}-\d{2}")),
)
ROOT_DOC_SECTIONS = {
    "README.md": (
        "## Runtime And Validation",
        "## Governance",
    ),
    "docs/README.md": (
        "## Documentation Contract",
    ),
    "docs/production-readiness-evaluation.md": (
        "## Readiness Axes",
    ),
    "SECURITY.md": (
        "## Reporting A Vulnerability",
        "private advisory",
    ),
}
ROOT_DOC_LAST_VERIFIED = {
    "README.md",
    "docs/README.md",
    "docs/production-readiness-evaluation.md",
}
LAST_VERIFIED_RE = re.compile(r"(?m)^Last verified: (\d{4}-\d{2}-\d{2})\s*$")
OPENAI_INTERFACE_KEYS = {"display_name", "short_description", "default_prompt", "brand_color"}
SKILL_FRONTMATTER_KEYS = {"name", "description"}
PINNED_ACTION_RE = re.compile(r"^[^@\s]+@[0-9a-fA-F]{40}$")
REQ_PIN_RE = re.compile(
    r"^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?==[A-Za-z0-9][A-Za-z0-9.*+!._-]*$"
)


def text_files(root: Path = ROOT) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if ".git" in path.parts or path.is_dir():
            continue
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        files.append(path)
    return files


def parse_skill_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("missing YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError("unterminated YAML frontmatter")
    try:
        parsed = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML frontmatter: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("frontmatter must be a YAML mapping")
    frontmatter = {str(key): str(value) for key, value in parsed.items()}
    return frontmatter


def parse_openai_interface(path: Path) -> tuple[dict[str, str], set[str]]:
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("YAML root must be a mapping")
    interface = parsed.get("interface")
    if not isinstance(interface, dict):
        raise ValueError("missing interface mapping")
    keys = {str(key) for key in interface}
    fields = {str(key): str(value) for key, value in interface.items()}
    return fields, keys


def validate_skill_dir(skill_dir: Path, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    skill_name = skill_dir.name
    rel = skill_dir.relative_to(root)
    if not SKILL_NAME_RE.match(skill_name):
        errors.append(f"{rel}: skill directory name must be kebab-case")

    skill_md = skill_dir / "SKILL.md"
    try:
        frontmatter = parse_skill_frontmatter(skill_md)
    except ValueError as exc:
        return [f"{skill_md.relative_to(root)}: {exc}"]

    unexpected = set(frontmatter) - SKILL_FRONTMATTER_KEYS
    if unexpected:
        errors.append(
            f"{skill_md.relative_to(root)}: unexpected frontmatter key(s): "
            + ", ".join(sorted(unexpected))
        )
    if frontmatter.get("name") != skill_name:
        errors.append(
            f"{skill_md.relative_to(root)}: name must match directory '{skill_name}'"
        )
    if not frontmatter.get("description"):
        errors.append(f"{skill_md.relative_to(root)}: description is required")

    openai_yaml = skill_dir / "agents" / "openai.yaml"
    if not openai_yaml.exists():
        errors.append(f"{rel}: missing agents/openai.yaml")
    else:
        try:
            fields, keys = parse_openai_interface(openai_yaml)
        except ValueError as exc:
            errors.append(f"{openai_yaml.relative_to(root)}: {exc}")
            fields, keys = {}, set()
        unexpected_interface = keys - OPENAI_INTERFACE_KEYS
        if unexpected_interface:
            errors.append(
                f"{openai_yaml.relative_to(root)}: unexpected interface key(s): "
                + ", ".join(sorted(unexpected_interface))
            )
        for required in ("display_name", "short_description", "default_prompt"):
            if not fields.get(required):
                errors.append(f"{openai_yaml.relative_to(root)}: missing {required}")
        short_description = fields.get("short_description", "")
        if short_description and not (25 <= len(short_description) <= 64):
            errors.append(
                f"{openai_yaml.relative_to(root)}: short_description must be 25-64 chars "
                f"(got {len(short_description)})"
            )
        default_prompt = fields.get("default_prompt", "")
        if default_prompt and f"${skill_name}" not in default_prompt:
            errors.append(
                f"{openai_yaml.relative_to(root)}: default_prompt must explicitly invoke ${skill_name}"
            )

    doc = root / "docs" / f"{skill_name}.md"
    if not doc.exists():
        errors.append(f"docs/{skill_name}.md: missing documentation page")
    else:
        doc_text = doc.read_text(encoding="utf-8")
        for heading in DOC_HEADINGS:
            if heading not in doc_text:
                errors.append(f"{doc.relative_to(root)}: missing heading {heading!r}")
        for concept, pattern in STANDARD_DOC_CONCEPTS:
            if not pattern.search(doc_text):
                errors.append(f"{doc.relative_to(root)}: missing public contract concept {concept!r}")

    return errors


def markdown_anchor(text: str) -> str:
    anchor = text.strip().lower()
    anchor = re.sub(r"`([^`]+)`", r"\1", anchor)
    anchor = re.sub(r"<[^>]+>", "", anchor)
    anchor = re.sub(r"\[[^\]]+\]\([^)]+\)", "", anchor)
    anchor = re.sub(r"[^a-z0-9 _-]", "", anchor)
    anchor = re.sub(r"\s+", "-", anchor.strip())
    return anchor


def markdown_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        base = markdown_anchor(match.group(2))
        if not base:
            continue
        count = seen.get(base, 0)
        seen[base] = count + 1
        anchors.add(base if count == 0 else f"{base}-{count}")
    return anchors


def validate_external_link(path: Path, target: str, root: Path) -> list[str]:
    parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"}:
        return []
    errors: list[str] = []
    rel = path.relative_to(root)
    if parsed.scheme != "https":
        errors.append(f"{rel}: external link must use https: {target}")
    if not parsed.netloc:
        errors.append(f"{rel}: malformed external link: {target}")
        return errors
    host = parsed.hostname or ""
    if host in {"localhost", "127.0.0.1", "::1"}:
        errors.append(f"{rel}: external link must not point to localhost: {target}")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return errors
    if address.is_private or address.is_loopback or address.is_reserved:
        errors.append(f"{rel}: external link must not point to private address: {target}")
    return errors


def validate_links(files: list[Path], root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for path in files:
        if path.suffix.lower() not in {".md", ".yaml", ".yml"}:
            continue
        text = path.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK_RE.finditer(text):
            target = match.group(1).strip()
            if (
                target.startswith(("http://", "https://"))
            ):
                errors.extend(validate_external_link(path, target, root))
                continue
            if (
                target.startswith(("mailto:", "#"))
                or target.startswith("app://")
            ):
                if target.startswith("#") and path.suffix.lower() == ".md":
                    anchor = target[1:]
                    if anchor and anchor not in markdown_anchors(path):
                        errors.append(f"{path.relative_to(root)}: broken anchor: {target}")
                continue
            target_path, _, anchor = target.partition("#")
            target_path = unquote(target_path.strip())
            if not target_path:
                continue
            resolved = (path.parent / target_path).resolve()
            try:
                resolved.relative_to(root)
            except ValueError:
                errors.append(f"{path.relative_to(root)}: link escapes repo: {target}")
                continue
            if not resolved.exists():
                errors.append(f"{path.relative_to(root)}: broken link: {target}")
                continue
            if anchor and resolved.suffix.lower() == ".md":
                if anchor not in markdown_anchors(resolved):
                    errors.append(f"{path.relative_to(root)}: broken anchor: {target}")
    return errors


def validate_online_links(files: list[Path], root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for path in files:
        if path.suffix.lower() not in {".md", ".txt", ".yaml", ".yml"} and path.name not in {"LICENSE"}:
            continue
        text = path.read_text(encoding="utf-8")
        for match in RAW_URL_RE.finditer(text):
            target = match.group(0).rstrip(".,]")
            errors.extend(validate_external_link(path, target, root))
    return errors


def validate_yaml_files(files: list[Path], root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for path in files:
        if path.suffix.lower() not in {".yaml", ".yml"}:
            continue
        try:
            yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            errors.append(f"{path.relative_to(root)}: invalid YAML: {exc}")
    return errors


def validate_no_local_paths(files: list[Path], root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if str(root) in line:
                errors.append(
                    f"{path.relative_to(root)}:{line_number}: local absolute path leak"
                )
                continue
            if any(pattern.search(line) for pattern in LOCAL_PATH_PATTERNS):
                errors.append(
                    f"{path.relative_to(root)}:{line_number}: local absolute path leak"
                )
    return errors


def validate_no_secrets(files: list[Path], root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for pattern in SECRET_PATTERNS:
                match = pattern.search(line)
                if not match:
                    continue
                candidate = match.group(0)
                if PLACEHOLDER_RE.search(candidate):
                    continue
                errors.append(f"{path.relative_to(root)}:{line_number}: possible secret material")
                break
    return errors


def validate_requirements_pinned(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    requirements = root / "requirements-dev.txt"
    if not requirements.exists():
        return ["requirements-dev.txt: missing pinned development dependencies"]
    for line_number, raw_line in enumerate(requirements.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        if not REQ_PIN_RE.match(line):
            errors.append(f"requirements-dev.txt:{line_number}: dependency must use an exact == pin")
    return errors


def validate_workflow_actions_pinned(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    workflow_dir = root / ".github" / "workflows"
    if not workflow_dir.exists():
        return [".github/workflows: missing validation workflows"]
    for workflow in sorted(workflow_dir.glob("*.y*ml")):
        try:
            parsed = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            errors.append(f"{workflow.relative_to(root)}: invalid YAML: {exc}")
            continue
        jobs = parsed.get("jobs", {}) if isinstance(parsed, dict) else {}
        if not isinstance(jobs, dict):
            errors.append(f"{workflow.relative_to(root)}: jobs must be a mapping")
            continue
        for job_name, job in jobs.items():
            steps = job.get("steps", []) if isinstance(job, dict) else []
            if not isinstance(steps, list):
                errors.append(f"{workflow.relative_to(root)}: job {job_name} steps must be a list")
                continue
            for index, step in enumerate(steps, start=1):
                if not isinstance(step, dict) or "uses" not in step:
                    continue
                uses = str(step["uses"])
                if uses.startswith("./") or uses.startswith("docker://"):
                    continue
                if not PINNED_ACTION_RE.match(uses):
                    errors.append(
                        f"{workflow.relative_to(root)}: job {job_name} step {index} uses must be pinned to a 40-char SHA: {uses}"
                    )
    return errors


def validate_governance_files(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    required = ("LICENSE", "CONTRIBUTING.md", "CODEOWNERS", "SUPPORT.md", "SECURITY.md")
    for name in required:
        if not (root / name).exists():
            errors.append(f"{name}: missing root governance file")
    license_path = root / "LICENSE"
    if license_path.exists():
        license_text = license_path.read_text(encoding="utf-8")
        if "Apache License" not in license_text or "Version 2.0" not in license_text:
            errors.append("LICENSE: expected Apache-2.0 license text")
    codeowners = root / "CODEOWNERS"
    if codeowners.exists() and "@kb-uipath" not in codeowners.read_text(encoding="utf-8"):
        errors.append("CODEOWNERS: expected @kb-uipath owner")
    security = root / "SECURITY.md"
    if security.exists():
        security_text = security.read_text(encoding="utf-8")
        if "private advisory" not in security_text.lower():
            errors.append("SECURITY.md: expected private advisory reporting guidance")
    return errors


def validate_root_docs(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for rel_path, required_sections in ROOT_DOC_SECTIONS.items():
        path = root / rel_path
        if not path.exists():
            errors.append(f"{rel_path}: missing root documentation file")
            continue
        text = path.read_text(encoding="utf-8")
        for section in required_sections:
            if section not in text:
                errors.append(f"{rel_path}: missing required section {section!r}")
        if rel_path in ROOT_DOC_LAST_VERIFIED:
            match = LAST_VERIFIED_RE.search(text)
            if match is None:
                errors.append(f"{rel_path}: missing valid ISO last-verified date")
            else:
                try:
                    date.fromisoformat(match.group(1))
                except ValueError:
                    errors.append(f"{rel_path}: missing valid ISO last-verified date")
    return errors


def run_validation(root: Path = ROOT) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    skill_dirs = sorted(path for path in root.iterdir() if (path / "SKILL.md").exists())
    if not skill_dirs:
        errors.append("no skill directories found")

    readme = (root / "README.md").read_text(encoding="utf-8")
    docs_index = (root / "docs" / "README.md").read_text(encoding="utf-8")
    for skill_dir in skill_dirs:
        errors.extend(validate_skill_dir(skill_dir, root))
        skill = skill_dir.name
        if f"./{skill}/SKILL.md" not in readme:
            errors.append(f"README.md: missing skill link for {skill}")
        if f"./docs/{skill}.md" not in readme:
            errors.append(f"README.md: missing docs link for {skill}")
        if f"./{skill}.md" not in docs_index:
            errors.append(f"docs/README.md: missing docs index link for {skill}")

    files = text_files(root)
    errors.extend(validate_yaml_files(files, root))
    errors.extend(validate_links(files, root))
    errors.extend(validate_online_links(files, root))
    errors.extend(validate_no_local_paths(files, root))
    errors.extend(validate_no_secrets(files, root))
    errors.extend(validate_requirements_pinned(root))
    errors.extend(validate_workflow_actions_pinned(root))
    errors.extend(validate_governance_files(root))
    errors.extend(validate_root_docs(root))
    return errors


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--secrets-only",
        action="store_true",
        help="Run only the deterministic plausible-secret scan.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    files = text_files(ROOT)
    errors = validate_no_secrets(files, ROOT) if args.secrets_only else run_validation(ROOT)

    if errors:
        label = "Secret scan" if args.secrets_only else "Repository validation"
        print(f"{label} failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    if args.secrets_only:
        print(f"Secret scan passed for {len(files)} text files.")
    else:
        skill_count = len([path for path in ROOT.iterdir() if (path / "SKILL.md").exists()])
        print(f"Validated {skill_count} skills and {len(files)} text files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
