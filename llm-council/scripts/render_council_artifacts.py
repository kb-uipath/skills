#!/usr/bin/env python3
"""Render LLM Council HTML and Markdown artifacts from a JSON session file."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import random
import re
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "llm-council.session.v1"
REQUIRED_ADVISORS = [
    "The Contrarian",
    "The First Principles Thinker",
    "The Expansionist",
    "The Outsider",
    "The Executor",
]
RESPONSE_LABELS = [f"Response {letter}" for letter in "ABCDE"]
REQUIRED_SESSION_FIELDS = (
    "schema_version",
    "original_question",
    "framed_question",
    "chairman_verdict",
    "advisors",
    "peer_reviews",
    "anonymization_mapping",
    "decision_criteria",
    "disconfirming_evidence",
    "review_date",
    "confidence",
    "execution_mode",
    "metadata",
)
CONFIDENCE_LEVELS = {"low", "medium", "high"}
EXECUTION_MODES = {"subagents", "single_agent_fallback"}
SENSITIVITY_CLASSES = {"public", "internal", "confidential", "restricted"}

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
    validate_strict_contract(payload)
    payload["metadata"]["hashes"] = derive_content_hashes(payload)

    return payload


def validate_session_schema(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise SystemExit("Session JSON must be an object.")

    if payload.get("schema_version") != SCHEMA_VERSION:
        raise SystemExit(
            "Missing or unsupported schema_version. "
            f"Use '{SCHEMA_VERSION}'. Migration: render only strict sessions with "
            "five named advisors, five peer reviews, Response A-E mapping, metadata, "
            "decision criteria, disconfirming evidence, review date, and confidence."
        )

    for field in REQUIRED_SESSION_FIELDS:
        if field not in payload or payload.get(field) in (None, ""):
            raise SystemExit(f"Missing required field: {field}")

    for field in ("original_question", "framed_question", "chairman_verdict"):
        if not isinstance(payload.get(field), str):
            raise SystemExit(f"Field '{field}' must be a string.")


def normalize_advisors(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {str(key): str(value or "") for key, value in raw.items()}

    raise SystemExit(
        "Field 'advisors' must be an object keyed by the five required advisor names. "
        "Migration: convert legacy advisor arrays into a strict advisor response object."
    )


def normalize_peer_reviews(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        raise SystemExit(
            "Field 'peer_reviews' must be a list of exactly five reviewer response objects. "
            "Migration: split legacy peer review text into Reviewer 1 through Reviewer 5."
        )

    reviews: list[dict[str, str]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise SystemExit("Peer review entries must be objects with reviewer and response fields.")
        reviewer = item.get("reviewer") or item.get("name") or f"Reviewer {index}"
        response = item.get("response") or item.get("text") or item.get("body") or ""
        reviews.append({"reviewer": str(reviewer), "response": str(response or "")})
    return reviews


def validate_strict_contract(payload: dict[str, Any]) -> None:
    advisor_keys = set(payload["advisors"])
    required_advisors = set(REQUIRED_ADVISORS)
    missing = required_advisors - advisor_keys
    extra = advisor_keys - required_advisors
    if missing or extra:
        details = []
        if missing:
            details.append("missing: " + ", ".join(sorted(missing)))
        if extra:
            details.append("unexpected: " + ", ".join(sorted(extra)))
        raise SystemExit("Advisors must be exactly the five required names (" + "; ".join(details) + ").")
    for advisor, response in payload["advisors"].items():
        if not isinstance(response, str) or not response.strip():
            raise SystemExit(f"Advisor response for '{advisor}' must be a non-empty string.")

    reviews = payload["peer_reviews"]
    if len(reviews) != 5:
        raise SystemExit("peer_reviews must contain exactly five reviews.")
    seen_reviewers: set[str] = set()
    for index, review in enumerate(reviews, start=1):
        reviewer = str(review.get("reviewer", "")).strip()
        response = review.get("response")
        if not reviewer:
            raise SystemExit(f"Peer review {index} needs a reviewer name.")
        if reviewer in seen_reviewers:
            raise SystemExit(f"Duplicate peer reviewer name: {reviewer}.")
        seen_reviewers.add(reviewer)
        if not isinstance(response, str) or not response.strip():
            raise SystemExit(f"Peer review {index} must include a non-empty response string.")

    validate_mapping(payload.get("anonymization_mapping"))
    validate_string_list(payload.get("decision_criteria"), "decision_criteria")
    validate_string_list(payload.get("disconfirming_evidence"), "disconfirming_evidence")
    validate_review_date(payload.get("review_date"))
    validate_confidence(payload.get("confidence"))
    validate_metadata(payload.get("metadata"))
    validate_execution_mode(payload)
    validate_advisor_positions(payload.get("advisor_positions"))


def validate_mapping(raw: Any) -> None:
    if not isinstance(raw, dict):
        raise SystemExit("anonymization_mapping must be an object with keys Response A through Response E.")
    keys = set(str(key) for key in raw)
    expected = set(RESPONSE_LABELS)
    if keys != expected:
        raise SystemExit(
            "anonymization_mapping must use exactly Response A through Response E. "
            "Migration: replace legacy A-E keys with Response A-E keys."
        )
    mapped = [str(raw[label]) for label in RESPONSE_LABELS]
    if set(mapped) != set(REQUIRED_ADVISORS) or len(mapped) != len(set(mapped)):
        raise SystemExit("anonymization_mapping must bijectively map Response A-E to the five advisors.")


def validate_string_list(raw: Any, field: str) -> None:
    if not isinstance(raw, list) or not raw:
        raise SystemExit(f"{field} must be a non-empty list of strings.")
    for index, value in enumerate(raw, start=1):
        if not isinstance(value, str) or not value.strip():
            raise SystemExit(f"{field}[{index}] must be a non-empty string.")


def validate_review_date(raw: Any) -> None:
    if not isinstance(raw, str):
        raise SystemExit("review_date must be an ISO date string in YYYY-MM-DD format.")
    try:
        dt.date.fromisoformat(raw)
    except ValueError as exc:
        raise SystemExit("review_date must be an ISO date string in YYYY-MM-DD format.") from exc


def validate_confidence(raw: Any) -> None:
    if not isinstance(raw, dict):
        raise SystemExit("confidence must be an object with level and rationale fields.")
    level = str(raw.get("level", "")).lower()
    if level not in CONFIDENCE_LEVELS:
        raise SystemExit("confidence.level must be one of: low, medium, high.")
    rationale = raw.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise SystemExit("confidence.rationale must be a non-empty string.")


def validate_metadata(raw: Any) -> None:
    if not isinstance(raw, dict):
        raise SystemExit("metadata must be an object.")
    for field in ("preparer", "preparer_seed", "created_at", "sensitivity", "permissions", "retention"):
        if field not in raw or raw.get(field) in (None, ""):
            raise SystemExit(f"metadata.{field} is required.")
    if str(raw.get("sensitivity")).lower() not in SENSITIVITY_CLASSES:
        raise SystemExit("metadata.sensitivity must be one of: public, internal, confidential, restricted.")
    if not isinstance(raw.get("permissions"), list) or not raw.get("permissions"):
        raise SystemExit("metadata.permissions must be a non-empty list.")
    for index, permission in enumerate(raw["permissions"], start=1):
        if not isinstance(permission, str) or not permission.strip():
            raise SystemExit(f"metadata.permissions[{index}] must be a non-empty string.")
    if not isinstance(raw.get("retention"), str) or not raw["retention"].strip():
        raise SystemExit("metadata.retention must be a non-empty string.")
    created_at = str(raw.get("created_at"))
    try:
        dt.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit("metadata.created_at must be an ISO timestamp.") from exc


def validate_execution_mode(payload: dict[str, Any]) -> None:
    mode = str(payload.get("execution_mode", ""))
    if mode not in EXECUTION_MODES:
        raise SystemExit("execution_mode must be 'subagents' or 'single_agent_fallback'.")
    fallback_reason = payload.get("fallback_reason")
    if mode == "single_agent_fallback" and (
        not isinstance(fallback_reason, str) or not fallback_reason.strip()
    ):
        raise SystemExit("single_agent_fallback requires a non-empty fallback_reason.")


def validate_advisor_positions(raw: Any) -> None:
    if raw in (None, ""):
        return
    if not isinstance(raw, list):
        raise SystemExit("advisor_positions must be a list when provided.")
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise SystemExit(f"advisor_positions[{index}] must be an object.")
        advisor = str(item.get("advisor", "")).strip()
        if advisor not in REQUIRED_ADVISORS:
            raise SystemExit(f"advisor_positions[{index}].advisor must be one of the required advisors.")
        stance = str(item.get("stance", "neutral")).lower()
        if stance not in STANCE_CLASS:
            raise SystemExit(f"advisor_positions[{index}].stance is not supported.")


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def derive_content_hashes(payload: dict[str, Any]) -> dict[str, Any]:
    canonical_payload = json.loads(json.dumps(payload, sort_keys=True, ensure_ascii=True))
    metadata = dict(canonical_payload.get("metadata") or {})
    metadata.pop("hashes", None)
    canonical_payload["metadata"] = metadata
    canonical = json.dumps(canonical_payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return {
        "canonical_session": sha256_text(canonical),
        "advisors": {
            advisor: sha256_text(payload["advisors"][advisor].strip())
            for advisor in REQUIRED_ADVISORS
        },
        "peer_reviews": {
            review["reviewer"]: sha256_text(review["response"].strip())
            for review in payload["peer_reviews"]
        },
    }


def prepare_session_template(
    seed: str,
    original_question: str = "",
    framed_question: str = "",
    preparer: str = "codex",
) -> dict[str, Any]:
    if not seed:
        raise SystemExit("--seed is required with --prepare-template.")
    shuffled = random.Random(seed).sample(REQUIRED_ADVISORS, len(REQUIRED_ADVISORS))
    mapping = {label: advisor for label, advisor in zip(RESPONSE_LABELS, shuffled)}
    created_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "schema_version": SCHEMA_VERSION,
        "original_question": original_question or "Replace with the user's raw decision question.",
        "framed_question": framed_question or "Replace with the neutral question sent to advisors.",
        "chairman_verdict": "Replace with the COUNCIL VERDICT synthesis.",
        "decision_criteria": ["Replace with the main decision criterion."],
        "disconfirming_evidence": ["Replace with evidence that would weaken or overturn the recommendation."],
        "review_date": dt.date.today().isoformat(),
        "confidence": {
            "level": "medium",
            "rationale": "Replace with why this confidence level is justified.",
        },
        "execution_mode": "subagents",
        "fallback_reason": "",
        "metadata": {
            "preparer": preparer,
            "preparer_seed": seed,
            "created_at": created_at,
            "sensitivity": "internal",
            "permissions": ["local workspace only"],
            "retention": "User-managed local artifacts; delete when no longer needed.",
        },
        "advisors": {advisor: f"Replace with {advisor} response." for advisor in REQUIRED_ADVISORS},
        "peer_reviews": [
            {"reviewer": f"Reviewer {index}", "response": "Replace with peer review response."}
            for index in range(1, 6)
        ],
        "anonymization_mapping": mapping,
        "advisor_positions": [
            {
                "advisor": advisor,
                "position": "Replace with concise position.",
                "stance": "neutral",
            }
            for advisor in REQUIRED_ADVISORS
        ],
    }


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


def list_to_html(items: Any) -> str:
    if not isinstance(items, list) or not items:
        return "<p></p>"
    return "<ul>" + "".join(f"<li>{html.escape(str(item))}</li>" for item in items) + "</ul>"


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


def render_metadata_html(payload: dict[str, Any]) -> str:
    metadata = payload.get("metadata") or {}
    hashes = metadata.get("hashes") or {}
    confidence = payload.get("confidence") or {}
    permissions = ", ".join(str(item) for item in metadata.get("permissions") or [])
    fallback = ""
    if payload.get("execution_mode") == "single_agent_fallback":
        fallback = (
            "<p><strong>Single-agent fallback:</strong> "
            + html.escape(str(payload.get("fallback_reason", "")))
            + "</p>"
        )
    rows = [
        ("Schema", payload.get("schema_version", "")),
        ("Execution mode", payload.get("execution_mode", "")),
        ("Review date", payload.get("review_date", "")),
        ("Confidence", f"{confidence.get('level', '')}: {confidence.get('rationale', '')}"),
        ("Sensitivity", metadata.get("sensitivity", "")),
        ("Permissions", permissions),
        ("Retention", metadata.get("retention", "")),
        ("Session hash", hashes.get("canonical_session", "")),
    ]
    body = "\n".join(
        f"<tr><th>{html.escape(label)}</th><td>{html.escape(str(value))}</td></tr>"
        for label, value in rows
    )
    return f"{fallback}<table class=\"metadata\"><tbody>{body}</tbody></table>"


def render_metadata_markdown(payload: dict[str, Any]) -> str:
    metadata = payload.get("metadata") or {}
    hashes = metadata.get("hashes") or {}
    confidence = payload.get("confidence") or {}
    permissions = ", ".join(str(item) for item in metadata.get("permissions") or [])
    lines = [
        f"- Schema: {payload.get('schema_version', '')}",
        f"- Execution mode: {payload.get('execution_mode', '')}",
        f"- Review date: {payload.get('review_date', '')}",
        f"- Confidence: {confidence.get('level', '')} - {confidence.get('rationale', '')}",
        f"- Sensitivity: {metadata.get('sensitivity', '')}",
        f"- Permissions: {permissions}",
        f"- Retention: {metadata.get('retention', '')}",
        f"- Session hash: {hashes.get('canonical_session', '')}",
    ]
    if payload.get("execution_mode") == "single_agent_fallback":
        lines.append(f"- Single-agent fallback reason: {payload.get('fallback_reason', '')}")
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
    metadata = render_metadata_html(payload)
    criteria = list_to_html(payload.get("decision_criteria"))
    disconfirming = list_to_html(payload.get("disconfirming_evidence"))

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
    table.metadata {{
      width: 100%;
      border-collapse: collapse;
      border: 1px solid var(--line);
      background: #fff;
    }}
    table.metadata th,
    table.metadata td {{
      border-bottom: 1px solid var(--line);
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }}
    table.metadata th {{
      width: 180px;
      background: var(--panel);
    }}
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
      <h2>Session Metadata</h2>
      {metadata}
    </section>

    <section>
      <h2>Agreement / Disagreement</h2>
      <div class="positions">{positions}</div>
    </section>

    <section>
      <h2>Decision Criteria</h2>
      {criteria}
    </section>

    <section>
      <h2>Disconfirming Evidence</h2>
      {disconfirming}
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
        markdown_section("Session Metadata", render_metadata_markdown(payload)),
        markdown_section("Decision Criteria", "\n".join(f"- {item}" for item in payload.get("decision_criteria", []))),
        markdown_section(
            "Disconfirming Evidence",
            "\n".join(f"- {item}" for item in payload.get("disconfirming_evidence", [])),
        ),
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_json", nargs="?", help="Path to council session JSON.")
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
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the session JSON and exit without writing report artifacts.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing report/transcript files for the resolved timestamp.",
    )
    parser.add_argument(
        "--prepare-template",
        action="store_true",
        help="Print a strict session JSON template with a deterministic Response A-E mapping.",
    )
    parser.add_argument("--seed", default=None, help="Seed used with --prepare-template.")
    parser.add_argument("--preparer", default="codex", help="Preparer name for --prepare-template.")
    parser.add_argument("--original-question", default="", help="Original question for --prepare-template.")
    parser.add_argument("--framed-question", default="", help="Framed question for --prepare-template.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.prepare_template:
        template = prepare_session_template(
            seed=args.seed or "",
            original_question=args.original_question,
            framed_question=args.framed_question,
            preparer=args.preparer,
        )
        print(json.dumps(template, indent=2, sort_keys=True))
        return 0

    if not args.session_json:
        raise SystemExit("session_json is required unless --prepare-template is used.")

    session_path = Path(args.session_json).expanduser().resolve()
    payload = load_session(session_path)
    if args.validate_only:
        print(f"OK: {session_path}")
        print(f"schema={payload.get('schema_version')}")
        print(f"advisors={len(REQUIRED_ADVISORS)}")
        print(f"peer_reviews={len(payload.get('peer_reviews') or [])}")
        print(f"session_hash={payload['metadata']['hashes']['canonical_session']}")
        return 0

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = slug_timestamp(args.timestamp or payload.get("timestamp"))

    html_path = output_dir / f"council-report-{timestamp}.html"
    markdown_path = output_dir / f"council-transcript-{timestamp}.md"
    existing = [str(path) for path in (html_path, markdown_path) if path.exists()]
    if existing and not args.overwrite:
        raise SystemExit(
            "Refusing to overwrite existing artifact(s): "
            + ", ".join(existing)
            + ". Use --overwrite after confirming the collision is intentional."
        )

    html_path.write_text(render_html(payload, timestamp), encoding="utf-8")
    markdown_path.write_text(render_markdown(payload, timestamp), encoding="utf-8")

    print(f"HTML report: {html_path}")
    print(f"Markdown transcript: {markdown_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
