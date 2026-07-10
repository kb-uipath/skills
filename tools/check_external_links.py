#!/usr/bin/env python3
"""Check public HTTPS links without making the deterministic PR gate network-dependent."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
RAW_URL_RE = re.compile(r"\bhttps://[^\s)>\"'`]+")
TEXT_SUFFIXES = {".md", ".txt", ".yaml", ".yml"}
REACHABLE_AUTH_CODES = {401, 403}
PERMANENT_FAILURE_CODES = {404, 410}


def text_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_dir() or ".git" in path.parts:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name != "LICENSE":
            continue
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        files.append(path)
    return files


def extract_urls(files: list[Path]) -> list[str]:
    urls: set[str] = set()
    for path in files:
        for match in RAW_URL_RE.finditer(path.read_text(encoding="utf-8")):
            url = match.group(0).rstrip(".,;:]}\")")
            host = (urlparse(url).hostname or "").lower()
            if host.endswith((".example", ".invalid", ".example.com", ".example.org")) or host in {
                "example.com",
                "example.org",
            }:
                continue
            urls.add(url)
    return sorted(urls)


def request_url(url: str, method: str, timeout: float) -> int:
    request = Request(
        url,
        method=method,
        headers={"User-Agent": "kb-uipath-skills-link-check/1.0"},
    )
    with urlopen(request, timeout=timeout) as response:
        return int(response.status)


def check_url(url: str, timeout: float = 15.0) -> str | None:
    try:
        status = request_url(url, "HEAD", timeout)
    except HTTPError as exc:
        if exc.code in REACHABLE_AUTH_CODES:
            return None
        # Several documentation hosts reject or misroute HEAD while serving GET.
        # Retry every non-auth HTTP response before declaring the link broken.
        try:
            status = request_url(url, "GET", timeout)
        except HTTPError as get_exc:
            if get_exc.code in REACHABLE_AUTH_CODES:
                return None
            return f"{url}: HTTP {get_exc.code}"
        except URLError as get_exc:
            return f"{url}: {get_exc.reason}"
    except URLError as exc:
        return f"{url}: {exc.reason}"

    if status in PERMANENT_FAILURE_CODES or status >= 500:
        return f"{url}: HTTP {status}"
    return None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--timeout", type=float, default=15.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    urls = extract_urls(text_files(args.root.resolve()))
    failures = [failure for url in urls if (failure := check_url(url, args.timeout))]
    for failure in failures:
        print(f"error: {failure}", file=sys.stderr)
    print(f"Checked {len(urls)} public HTTPS links; {len(failures)} failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
