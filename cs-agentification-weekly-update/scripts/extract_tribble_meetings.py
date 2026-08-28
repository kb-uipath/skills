#!/usr/bin/env python3
"""Read-only extraction of Tribble Scribe meeting data for CS Agentification updates.

Tribble Scribe (a macOS meeting recorder) stores everything unencrypted in a local
SQLite database. This script never opens that live file directly: it copies the
database plus its WAL/SHM sidecars into a temporary directory, opens the copy
read-only, runs the query, and deletes the copy. The live app is never touched.

Safety reminder (see references/tribble-safety-and-method.md for the full policy):
Tribble Scribe is not an approved TAM tool. Treat every summary and transcript as
confidential. Never commit this output to any repository. Before using a meeting
that includes anyone outside the internal team, confirm current consent/approval
status first -- this script only prints participant names, it cannot tell you
whether someone is a customer contact.
"""

from __future__ import annotations

import argparse
import itertools
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

DEFAULT_DB_PATH = Path.home() / "Library" / "Application Support" / "Tribble Desktop" / "tribble.db"

SAFETY_BANNER = (
    "Tribble Scribe is not an approved TAM tool. Treat this output as confidential.\n"
    "Do not commit it to any repository. If any participant below is an external\n"
    "customer contact, confirm current consent/approval status before using this\n"
    "meeting's summary or transcript.\n"
)


def resolve_db_path(cli_value: str | None) -> Path:
    import os

    candidate = cli_value or os.environ.get("TRIBBLE_DB_PATH") or str(DEFAULT_DB_PATH)
    return Path(candidate).expanduser()


class Snapshot:
    """Copies tribble.db (+ -wal/-shm) into a temp dir and opens it read-only."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._tmpdir: tempfile.TemporaryDirectory | None = None
        self.conn: sqlite3.Connection | None = None

    def __enter__(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"Tribble database not found at {self.db_path}. Open Tribble Scribe "
                "and let it sync, or pass --db / set TRIBBLE_DB_PATH."
            )
        self._tmpdir = tempfile.TemporaryDirectory(prefix="tribble-snapshot-")
        snapshot_path = Path(self._tmpdir.name) / "tribble.db"
        shutil.copyfile(self.db_path, snapshot_path)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(self.db_path) + suffix)
            if sidecar.exists():
                shutil.copyfile(sidecar, Path(str(snapshot_path) + suffix))
        self.conn = sqlite3.connect(f"file:{snapshot_path}?mode=ro", uri=True)
        self.conn.row_factory = sqlite3.Row
        return self.conn

    def __exit__(self, *exc_info) -> None:
        if self.conn is not None:
            self.conn.close()
        if self._tmpdir is not None:
            self._tmpdir.cleanup()


QUERY_MEETING_LIST = """
    SELECT m.id, m.title, m.date, m.platform,
           COALESCE(d.content, d.summary_text, '') AS summary,
           m.participants_json
    FROM meetings m
    LEFT JOIN meeting_details d ON d.meeting_id = m.id
    WHERE COALESCE(d.content, d.summary_text, '') <> ''
       OR EXISTS (SELECT 1 FROM transcript_entries t WHERE t.meeting_id = m.id)
    ORDER BY m.date DESC
"""

QUERY_MEETING_BY_ID = """
    SELECT m.id, m.title, m.date, m.platform,
           d.content AS summary, m.participants_json
    FROM meetings m
    LEFT JOIN meeting_details d ON d.meeting_id = m.id
    WHERE m.id = ?
"""

QUERY_TRANSCRIPT = """
    SELECT seq, ts, speaker, text
    FROM transcript_entries
    WHERE meeting_id = ?
    ORDER BY seq
"""


def participant_names(participants_json: str | None) -> list[str]:
    if not participants_json:
        return []
    try:
        people = json.loads(participants_json)
    except (ValueError, TypeError):
        return []
    return [p.get("name", "?") for p in people if isinstance(p, dict)]


def merge_transcript(rows: list[sqlite3.Row]) -> str:
    """Merge consecutive same-speaker rows into paragraphs (recorder emits a row every few seconds)."""
    paragraphs = []
    for speaker, group in itertools.groupby(rows, key=lambda r: r["speaker"]):
        text = " ".join(r["text"] for r in group)
        paragraphs.append(f"{speaker}: {text}")
    return "\n\n".join(paragraphs)


def cmd_list(args: argparse.Namespace) -> int:
    db_path = resolve_db_path(args.db)
    with Snapshot(db_path) as conn:
        rows = conn.execute(QUERY_MEETING_LIST).fetchall()

    query_lower = (args.query or "").lower()
    results = []
    for row in rows:
        if query_lower and query_lower not in row["title"].lower():
            continue
        results.append(
            {
                "id": row["id"],
                "title": row["title"].strip(),
                "date": row["date"],
                "platform": row["platform"],
                "participants": participant_names(row["participants_json"]),
                "has_summary": bool(row["summary"]),
            }
        )
        if len(results) >= args.limit:
            break

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(SAFETY_BANNER, file=sys.stderr)
        for m in results:
            people = ", ".join(m["participants"]) or "(no participant data)"
            print(f"{m['id']}\t{m['date']}\t{m['title']}\n  participants: {people}\n")
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    db_path = resolve_db_path(args.db)
    with Snapshot(db_path) as conn:
        meeting = conn.execute(QUERY_MEETING_BY_ID, (args.meeting_id,)).fetchone()
        if meeting is None:
            print(f"No meeting found with id {args.meeting_id!r}", file=sys.stderr)
            return 1
        transcript_md = None
        if args.transcript:
            rows = conn.execute(QUERY_TRANSCRIPT, (args.meeting_id,)).fetchall()
            transcript_md = merge_transcript(rows)

    result = {
        "id": meeting["id"],
        "title": meeting["title"].strip(),
        "date": meeting["date"],
        "platform": meeting["platform"],
        "participants": participant_names(meeting["participants_json"]),
        "summary_markdown": meeting["summary"],
        "transcript_markdown": transcript_md,
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(SAFETY_BANNER, file=sys.stderr)
        print(f"# {result['title']}")
        print(f"Date: {result['date']} | Platform: {result['platform']}")
        print(f"Participants: {', '.join(result['participants']) or '(no participant data)'}")
        print()
        if result["summary_markdown"]:
            print(result["summary_markdown"])
        if transcript_md:
            print("\n---\n## Transcript\n")
            print(transcript_md)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Path to tribble.db (default: $TRIBBLE_DB_PATH or the standard macOS location)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List recent recorded meetings (metadata + participants only)")
    p_list.add_argument("--query", help="Case-insensitive substring filter on meeting title")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_get = sub.add_parser("get", help="Get one meeting's AI summary (and optionally transcript)")
    p_get.add_argument("meeting_id")
    p_get.add_argument("--transcript", action="store_true", help="Include the full speaker-merged transcript")
    p_get.add_argument("--json", action="store_true")
    p_get.set_defaults(func=cmd_get)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
