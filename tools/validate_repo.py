#!/usr/bin/env python3
"""Validate repository-level skill packaging contracts."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
LOCAL_PATH_RE = re.compile(r"/Users/[A-Za-z0-9._-]+/")
DOC_HEADINGS = ("## Inputs", "## Prompt", "## Safety", "## Validation")
OPENAI_INTERFACE_KEYS = {"display_name", "short_description", "default_prompt", "brand_color"}
SKILL_FRONTMATTER_KEYS = {"name", "description"}


def text_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
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
    frontmatter: dict[str, str] = {}
    for raw_line in text[4:end].splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ":" not in line:
            raise ValueError(f"invalid frontmatter line: {raw_line!r}")
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = value.strip().strip('"').strip("'")
    return frontmatter


def parse_openai_interface(path: Path) -> tuple[dict[str, str], set[str]]:
    fields: dict[str, str] = {}
    keys: set[str] = set()
    in_interface = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if raw_line.startswith("interface:"):
            in_interface = True
            continue
        if in_interface and raw_line and not raw_line.startswith((" ", "\t")):
            break
        if not in_interface or ":" not in raw_line:
            continue
        key, value = raw_line.strip().split(":", 1)
        keys.add(key.strip())
        fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields, keys


def validate_skill_dir(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    skill_name = skill_dir.name
    rel = skill_dir.relative_to(ROOT)
    if not SKILL_NAME_RE.match(skill_name):
        errors.append(f"{rel}: skill directory name must be kebab-case")

    skill_md = skill_dir / "SKILL.md"
    try:
        frontmatter = parse_skill_frontmatter(skill_md)
    except ValueError as exc:
        return [f"{skill_md.relative_to(ROOT)}: {exc}"]

    unexpected = set(frontmatter) - SKILL_FRONTMATTER_KEYS
    if unexpected:
        errors.append(
            f"{skill_md.relative_to(ROOT)}: unexpected frontmatter key(s): "
            + ", ".join(sorted(unexpected))
        )
    if frontmatter.get("name") != skill_name:
        errors.append(
            f"{skill_md.relative_to(ROOT)}: name must match directory '{skill_name}'"
        )
    if not frontmatter.get("description"):
        errors.append(f"{skill_md.relative_to(ROOT)}: description is required")

    openai_yaml = skill_dir / "agents" / "openai.yaml"
    if not openai_yaml.exists():
        errors.append(f"{rel}: missing agents/openai.yaml")
    else:
        fields, keys = parse_openai_interface(openai_yaml)
        unexpected_interface = keys - OPENAI_INTERFACE_KEYS
        if unexpected_interface:
            errors.append(
                f"{openai_yaml.relative_to(ROOT)}: unexpected interface key(s): "
                + ", ".join(sorted(unexpected_interface))
            )
        for required in ("display_name", "short_description", "default_prompt"):
            if not fields.get(required):
                errors.append(f"{openai_yaml.relative_to(ROOT)}: missing {required}")
        short_description = fields.get("short_description", "")
        if short_description and not (25 <= len(short_description) <= 64):
            errors.append(
                f"{openai_yaml.relative_to(ROOT)}: short_description must be 25-64 chars "
                f"(got {len(short_description)})"
            )
        default_prompt = fields.get("default_prompt", "")
        if default_prompt and f"${skill_name}" not in default_prompt:
            errors.append(
                f"{openai_yaml.relative_to(ROOT)}: default_prompt must explicitly invoke ${skill_name}"
            )

    doc = ROOT / "docs" / f"{skill_name}.md"
    if not doc.exists():
        errors.append(f"docs/{skill_name}.md: missing documentation page")
    else:
        doc_text = doc.read_text(encoding="utf-8")
        for heading in DOC_HEADINGS:
            if heading not in doc_text:
                errors.append(f"{doc.relative_to(ROOT)}: missing heading {heading!r}")

    return errors


def validate_links(files: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in files:
        if path.suffix.lower() not in {".md", ".yaml", ".yml"}:
            continue
        text = path.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK_RE.finditer(text):
            target = match.group(1).strip()
            if (
                target.startswith(("http://", "https://", "mailto:", "#"))
                or target.startswith("app://")
            ):
                continue
            target_path = target.split("#", 1)[0].strip()
            if not target_path:
                continue
            resolved = (path.parent / target_path).resolve()
            try:
                resolved.relative_to(ROOT)
            except ValueError:
                errors.append(f"{path.relative_to(ROOT)}: link escapes repo: {target}")
                continue
            if not resolved.exists():
                errors.append(f"{path.relative_to(ROOT)}: broken link: {target}")
    return errors


def validate_no_local_paths(files: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if LOCAL_PATH_RE.search(line):
                errors.append(
                    f"{path.relative_to(ROOT)}:{line_number}: local absolute path leak"
                )
    return errors


def main() -> int:
    errors: list[str] = []
    skill_dirs = sorted(path for path in ROOT.iterdir() if (path / "SKILL.md").exists())
    if not skill_dirs:
        errors.append("no skill directories found")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    docs_index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    for skill_dir in skill_dirs:
        errors.extend(validate_skill_dir(skill_dir))
        skill = skill_dir.name
        if f"./{skill}/SKILL.md" not in readme:
            errors.append(f"README.md: missing skill link for {skill}")
        if f"./docs/{skill}.md" not in readme:
            errors.append(f"README.md: missing docs link for {skill}")
        if f"./{skill}.md" not in docs_index:
            errors.append(f"docs/README.md: missing docs index link for {skill}")

    files = text_files()
    errors.extend(validate_links(files))
    errors.extend(validate_no_local_paths(files))

    if errors:
        print("Repository validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Validated {len(skill_dirs)} skills and {len(files)} text files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
