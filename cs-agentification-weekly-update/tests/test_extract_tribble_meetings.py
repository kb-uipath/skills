import json
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import extract_tribble_meetings as mod  # noqa: E402


def build_fixture_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE meetings (
            id TEXT PRIMARY KEY, title TEXT, date TEXT, platform TEXT, participants_json TEXT
        );
        CREATE TABLE meeting_details (
            meeting_id TEXT, content TEXT, summary_text TEXT, user_notes_content TEXT
        );
        CREATE TABLE transcript_entries (
            meeting_id TEXT, seq INTEGER, ts INTEGER, speaker TEXT, text TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO meetings VALUES (?, ?, ?, ?, ?)",
        (
            "meeting-1",
            "CS Agentification Weekly Strategy Sync",
            "2026-08-28T15:00:00.000Z",
            "Microsoft Teams",
            json.dumps([{"name": "Keith Born"}, {"name": "Claudio Chaves"}]),
        ),
    )
    conn.execute(
        "INSERT INTO meeting_details VALUES (?, ?, ?, ?)",
        ("meeting-1", "## Call Overview\nTest summary.", None, None),
    )
    rows = [
        ("meeting-1", 0, 0, "Keith Born", "Let's"),
        ("meeting-1", 1, 1, "Keith Born", "start."),
        ("meeting-1", 2, 2, "Claudio Chaves", "Sounds good."),
    ]
    conn.executemany("INSERT INTO transcript_entries VALUES (?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()


class TestMergeTranscript(unittest.TestCase):
    def test_merges_consecutive_same_speaker_rows(self):
        rows = [
            {"speaker": "A", "text": "hello"},
            {"speaker": "A", "text": "world"},
            {"speaker": "B", "text": "hi"},
        ]
        merged = mod.merge_transcript(rows)
        self.assertEqual(merged, "A: hello world\n\nB: hi")

    def test_does_not_merge_non_adjacent_repeats(self):
        rows = [
            {"speaker": "A", "text": "one"},
            {"speaker": "B", "text": "two"},
            {"speaker": "A", "text": "three"},
        ]
        merged = mod.merge_transcript(rows)
        self.assertEqual(merged, "A: one\n\nB: two\n\nA: three")


class TestParticipantNames(unittest.TestCase):
    def test_extracts_names_from_json(self):
        names = mod.participant_names(json.dumps([{"name": "Keith Born"}, {"name": "Claudio Chaves"}]))
        self.assertEqual(names, ["Keith Born", "Claudio Chaves"])

    def test_handles_missing_or_malformed_json(self):
        self.assertEqual(mod.participant_names(None), [])
        self.assertEqual(mod.participant_names("not json"), [])


class TestSnapshotAndQueries(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "tribble.db"
        build_fixture_db(self.db_path)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_list_finds_the_fixture_meeting(self):
        with mod.Snapshot(self.db_path) as conn:
            rows = conn.execute(mod.QUERY_MEETING_LIST).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "CS Agentification Weekly Strategy Sync")

    def test_get_returns_summary_and_transcript(self):
        with mod.Snapshot(self.db_path) as conn:
            meeting = conn.execute(mod.QUERY_MEETING_BY_ID, ("meeting-1",)).fetchone()
            transcript_rows = conn.execute(mod.QUERY_TRANSCRIPT, ("meeting-1",)).fetchall()
        self.assertIn("Test summary.", meeting["summary"])
        merged = mod.merge_transcript(transcript_rows)
        self.assertEqual(merged, "Keith Born: Let's start.\n\nClaudio Chaves: Sounds good.")

    def test_snapshot_leaves_the_live_db_untouched(self):
        original_bytes = self.db_path.read_bytes()
        with mod.Snapshot(self.db_path) as conn:
            conn.execute("SELECT 1")
        self.assertEqual(self.db_path.read_bytes(), original_bytes)

    def test_missing_db_raises_clear_error(self):
        with self.assertRaises(FileNotFoundError):
            with mod.Snapshot(Path(self.tmpdir.name) / "does-not-exist.db"):
                pass


if __name__ == "__main__":
    unittest.main()
