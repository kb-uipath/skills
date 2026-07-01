#!/usr/bin/env python3
"""Render LLM Council HTML and Markdown artifacts from a JSON session file."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_ADVISORS = [
    "The Contrarian",
    "The First Principles Thinker",
    "The Expansionist",
    "The Outsider",
    "The Executor",
]
REQUIRED_SESSION_FIELDS = (
    "original_question",
    "framed_question",
    "chairman_verdict",
    "advisors",
)

STANCE_CLASS = {
    "positive": "stance-positive",
    "negative": "stance-negative",
    "mixed": "stance-mixed",
    "neutral": "stance-neutral",
}


def load_session(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc

    validate_session_schema(payload)

    payload["advisors"] = normalize_advisors(payload["advisors"])
    payload["peer_reviews"] = normalize_peer_reviews(payload.get("peer_reviews") or [])

    missing = [
        advisor
        for advisor in REQUIRED_ADVISORS
        if not str(payload["advisors"].get(advisor, "")).strip()
    ]
    if missing:
        raise SystemExit("Missing advisor response(s): " + ", ".join(missing))

    return payload


def validate_session_schema(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise SystemExit("Session JSON must be an object.")

    for field in REQUIRED_SESSION_FIELDS:
        if not payload.get(field):
            raise SystemExit(f"Missing required field: {field}")

    for field in ("original_question", "framed_question", "chairman_verdict"):
        if not isinstance(payload.get(field), str):
            raise SystemExit(f"Field '{field}' must be a string.")


def normalize_advisors(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {str(key): str(value or "") for key, value in raw.items()}

    if isinstance(raw, list):
        advisors: dict[str, str] = {}
        for item in raw:
            if not isinstance(item, dict):
                raise SystemExit("Advisor list entries must be objects.")
            name = item.get("advisor") or item.get("name")
            response = item.get("response") or item.get("text") or item.get("body")
            if not name:
                raise SystemExit("Advisor list entries need an 'advisor' or 'name' field.")
            advisors[str(name)] = str(response or "")
        return advisors

    raise SystemExit("Field 'advisors' must be an object or a list of advisor response objects.")


def normalize_peer_reviews(raw: Any) -> list[dict[str, str]]:
    if isinstance(raw, str):
        return [{"reviewer": "Peer review", "response": raw}]
    if not isinstance(raw, list):
        raise SystemExit("Field 'peer_reviews' must be a string or list when provided.")

    reviews: list[dict[str, str]] = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            reviewer = item.get("reviewer") or item.get("name") or f"Reviewer {index}"
            response = item.get("response") or item.get("text") or item.get("body") or ""
        else:
            reviewer = f"Reviewer {index}"
            response = item
        reviews.append({"reviewer": str(reviewer), "response": str(response or "")})
    return reviews


def slug_timestamp(value: str | None) -> str:
    if value:
        cleaned = re.sub(r"[^0-9A-Za-z_-]+", "-", value.strip()).strip("-")
        if cleaned:
            return cleaned
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def text_to_html(text: Any) -> str:
    escaped = html.escape(str(text or "").strip())
    paragraphs = [part for part in re.split(r"\n{2,}", escaped) if part.strip()]
    if not paragraphs:
        return "<p></p>"
    return "\n".join(f"<p>{part.replace(chr(10), '<br>')}</p>" for part in paragraphs)


def markdown_section(title: str, body: Any) -> str:
    return f"## {title}\n\n{str(body or '').strip()}\n"


def render_positions(payload: dict[str, Any]) -> str:
    positions = payload.get("advisor_positions") or []
    if not isinstance(positions, list) or not positions:
        positions = [
            {
                "advisor": advisor,
                "position": "Full response in advisor section",
                "stance": "neutral",
            }
            for advisor in REQUIRED_ADVISORS
        ]

    cards = []
    for item in positions:
        if not isinstance(item, dict):
            continue
        advisor = html.escape(str(item.get("advisor", "Advisor")))
        position = html.escape(str(item.get("position", "")))
        stance = str(item.get("stance", "neutral")).lower()
        css_class = STANCE_CLASS.get(stance, "stance-neutral")
        label = html.escape(stance.capitalize())
        cards.append(
            f"""
            <div class="position-card {css_class}">
              <div class="position-topline"><strong>{advisor}</strong><span>{label}</span></div>
              <p>{position}</p>
            </div>
            """
        )
    return "\n".join(cards)


def render_peer_reviews(payload: dict[str, Any]) -> str:
    reviews = payload.get("peer_reviews") or []
    output = []
    for index, review in enumerate(reviews, start=1):
        reviewer = review.get("reviewer") or f"Reviewer {index}"
        response = review.get("response") or ""
        output.append(
            f"""
            <details>
              <summary>{html.escape(str(reviewer))}</summary>
              {text_to_html(response)}
            </details>
            """
        )
    return "\n".join(output)


def render_mapping(payload: dict[str, Any]) -> str:
    mapping = payload.get("anonymization_mapping") or {}
    if not isinstance(mapping, dict) or not mapping:
        return "No anonymization mapping provided."
    lines = [f"- {letter}: {advisor}" for letter, advisor in mapping.items()]
    return "\n".join(lines)


def render_html(payload: dict[str, Any], timestamp: str) -> str:
    title = "LLM Council Report"
    advisor_blocks = []
    for advisor in REQUIRED_ADVISORS:
        advisor_blocks.append(
            f"""
            <details class="advisor">
              <summary>{html.escape(advisor)}</summary>
              {text_to_html(payload["advisors"].get(advisor, ""))}
            </details>
            """
        )

    generated_at = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    question = html.escape(str(payload.get("original_question", "")).strip())
    framed = text_to_html(payload.get("framed_question", ""))
    verdict = text_to_html(payload.get("chairman_verdict", ""))
    positions = render_positions(payload)
    peer_reviews = render_peer_reviews(payload)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} - {html.escape(timestamp)}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #162033;
      --muted: #5f6b7a;
      --line: #d7dde7;
      --panel: #f7f9fc;
      --accent: #325f9d;
      --positive: #dff2e4;
      --negative: #f8dfdf;
      --mixed: #fff0cb;
      --neutral: #e8edf5;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: #ffffff;
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.55;
    }}
    main {{
      width: min(1080px, calc(100% - 32px));
      margin: 0 auto;
      padding: 36px 0 44px;
    }}
    header {{
      border-bottom: 1px solid var(--line);
      padding-bottom: 20px;
      margin-bottom: 24px;
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: clamp(28px, 4vw, 44px);
      letter-spacing: 0;
    }}
    h2 {{
      margin: 30px 0 12px;
      font-size: 20px;
      letter-spacing: 0;
    }}
    p {{ margin: 0 0 12px; }}
    .meta {{ color: var(--muted); font-size: 14px; }}
    .question {{
      margin-top: 16px;
      padding: 14px 16px;
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
    }}
    .verdict {{
      border-left: 5px solid var(--accent);
      background: #f4f7fb;
      padding: 18px 20px;
      border-radius: 8px;
    }}
    .positions {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 12px;
    }}
    .position-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 13px 14px;
      min-height: 118px;
    }}
    .position-card p {{ margin: 8px 0 0; color: var(--ink); }}
    .position-topline {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 8px;
      font-size: 14px;
    }}
    .position-topline span {{
      color: var(--muted);
      white-space: nowrap;
    }}
    .stance-positive {{ background: var(--positive); }}
    .stance-negative {{ background: var(--negative); }}
    .stance-mixed {{ background: var(--mixed); }}
    .stance-neutral {{ background: var(--neutral); }}
    details {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px 14px;
      margin-bottom: 10px;
      background: #fff;
    }}
    summary {{
      cursor: pointer;
      font-weight: 700;
    }}
    details p:first-of-type {{ margin-top: 12px; }}
    footer {{
      border-top: 1px solid var(--line);
      color: var(--muted);
      margin-top: 34px;
      padding-top: 16px;
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>LLM Council Report</h1>
      <div class="meta">Generated {html.escape(generated_at)}</div>
      <div class="question"><strong>Question:</strong> {question}</div>
    </header>

    <section>
      <h2>Chairman Verdict</h2>
      <div class="verdict">{verdict}</div>
    </section>

    <section>
      <h2>Agreement / Disagreement</h2>
      <div class="positions">{positions}</div>
    </section>

    <section>
      <h2>Framed Question</h2>
      {framed}
    </section>

    <section>
      <h2>Advisor Responses</h2>
      {''.join(advisor_blocks)}
    </section>

    <section>
      <h2>Peer Review Highlights</h2>
      {peer_reviews}
    </section>

    <footer>
      Timestamp: {html.escape(timestamp)}<br>
      Question counciled: {question}
    </footer>
  </main>
</body>
</html>
"""


def render_markdown(payload: dict[str, Any], timestamp: str) -> str:
    chunks = [
        f"# LLM Council Transcript - {timestamp}\n",
        markdown_section("Original Question", payload.get("original_question", "")),
        markdown_section("Framed Question", payload.get("framed_question", "")),
        markdown_section("Chairman Synthesis", payload.get("chairman_verdict", "")),
        "## Advisor Responses\n",
    ]
    for advisor in REQUIRED_ADVISORS:
        chunks.append(f"### {advisor}\n\n{payload['advisors'].get(advisor, '').strip()}\n")

    chunks.append("## Peer Reviews\n")
    reviews = payload.get("peer_reviews") or []
    for index, review in enumerate(reviews, start=1):
        reviewer = review.get("reviewer") or f"Reviewer {index}"
        response = review.get("response") or ""
        chunks.append(f"### {reviewer}\n\n{str(response).strip()}\n")

    chunks.append(markdown_section("Anonymization Mapping", render_mapping(payload)))
    return "\n".join(chunks)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_json", help="Path to council session JSON.")
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory where report and transcript files should be written.",
    )
    parser.add_argument(
        "--timestamp",
        default=None,
        help="Optional timestamp slug for deterministic filenames.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session_path = Path(args.session_json).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = load_session(session_path)
    timestamp = slug_timestamp(args.timestamp or payload.get("timestamp"))

    html_path = output_dir / f"council-report-{timestamp}.html"
    markdown_path = output_dir / f"council-transcript-{timestamp}.md"

    html_path.write_text(render_html(payload, timestamp), encoding="utf-8")
    markdown_path.write_text(render_markdown(payload, timestamp), encoding="utf-8")

    print(f"HTML report: {html_path}")
    print(f"Markdown transcript: {markdown_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
