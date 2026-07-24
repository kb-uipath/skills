from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "tools" / "beads_history.py"
SPEC = importlib.util.spec_from_file_location("beads_history", SCRIPT_PATH)
beads_history = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(beads_history)


def issue(status: str, updated_at: str) -> dict[str, object]:
    return {
        "id": "skills-test",
        "title": "Test issue",
        "status": status,
        "priority": 1,
        "issue_type": "task",
        "created_at": "2026-07-24T12:00:00Z",
        "updated_at": updated_at,
    }


def raw_history(
    commit_hash: str, commit_date: str, snapshot: dict[str, object]
) -> dict[str, object]:
    return {
        "CommitHash": commit_hash,
        "Committer": "Test User",
        "CommitDate": commit_date,
        "Issue": snapshot,
    }


class BeadsHistoryTests(unittest.TestCase):
    def test_parse_timestamp_accepts_dolt_fraction_widths(self) -> None:
        parsed = beads_history.parse_timestamp(
            "2026-07-24T15:03:42.81-04:00", "test timestamp"
        )

        self.assertEqual(810000, parsed.microsecond)

    def test_normalize_orders_and_removes_only_adjacent_unchanged_states(self) -> None:
        open_issue = issue("open", "2026-07-24T12:00:00Z")
        claimed_issue = issue("in_progress", "2026-07-24T12:02:00Z")
        reopened_issue = issue("open", "2026-07-24T12:04:00Z")
        raw = [
            raw_history("dddd", "2026-07-24T12:04:01Z", reopened_issue),
            raw_history("cccc", "2026-07-24T12:03:00Z", claimed_issue),
            raw_history("bbbb", "2026-07-24T12:02:01Z", claimed_issue),
            raw_history("aaaa", "2026-07-24T12:00:01Z", open_issue),
        ]

        normalized = beads_history.normalize_issue_history("skills-test", raw)

        self.assertEqual(
            ["aaaa", "bbbb", "dddd"],
            [record["commit_hash"] for record in normalized],
        )
        self.assertEqual(
            ["open", "in_progress", "open"],
            [record["issue"]["status"] for record in normalized],
        )

    def test_validate_accepts_terminal_subset_of_current_issue(self) -> None:
        current = issue("in_progress", "2026-07-24T12:02:00Z")
        current["labels"] = ["tracking"]
        records = beads_history.normalize_issue_history(
            "skills-test",
            [
                raw_history(
                    "aaaa",
                    "2026-07-24T12:00:01Z",
                    issue("open", "2026-07-24T12:00:00Z"),
                ),
                raw_history("bbbb", "2026-07-24T12:02:01Z", dict(current, labels=None)),
            ],
        )
        records[-1]["issue"].pop("labels")

        beads_history.validate_history_records({"skills-test": current}, records)

    def test_validate_rejects_stale_terminal_state(self) -> None:
        current = issue("closed", "2026-07-24T12:03:00Z")
        records = beads_history.normalize_issue_history(
            "skills-test",
            [
                raw_history(
                    "aaaa",
                    "2026-07-24T12:00:01Z",
                    issue("open", "2026-07-24T12:00:00Z"),
                )
            ],
        )

        with self.assertRaisesRegex(
            beads_history.HistoryValidationError,
            "terminal history snapshot differs",
        ):
            beads_history.validate_history_records({"skills-test": current}, records)

    def test_verify_is_offline_and_does_not_rewrite_files(self) -> None:
        current = issue("open", "2026-07-24T12:00:00Z")
        records = beads_history.normalize_issue_history(
            "skills-test",
            [raw_history("aaaa", "2026-07-24T12:00:01Z", current)],
        )
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            issues_path = root / "issues.jsonl"
            history_path = root / "history.jsonl"
            manifest_path = root / "history-manifest.json"
            current_record = {"_type": "issue", **current}
            issues_path.write_text(
                beads_history.render_jsonl([current_record]), encoding="utf-8"
            )
            history_path.write_text(
                beads_history.render_jsonl(records), encoding="utf-8"
            )
            manifest = beads_history.build_manifest(
                "abc123",
                issues_path,
                history_path,
                issue_records=1,
                history_records=1,
            )
            manifest_path.write_text(
                beads_history.json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            before = history_path.read_bytes()

            result = beads_history.verify_history(
                issues_path, history_path, manifest_path
            )

            self.assertEqual(0, result)
            self.assertEqual(before, history_path.read_bytes())

    def test_validate_manifest_rejects_changed_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            issues_path = root / "issues.jsonl"
            history_path = root / "history.jsonl"
            manifest_path = root / "history-manifest.json"
            issues_path.write_text("{}\n", encoding="utf-8")
            history_path.write_text("{}\n", encoding="utf-8")
            manifest = beads_history.build_manifest(
                "abc123",
                issues_path,
                history_path,
                issue_records=1,
                history_records=1,
            )
            manifest_path.write_text(
                beads_history.json.dumps(manifest), encoding="utf-8"
            )
            history_path.write_text('{"changed":true}\n', encoding="utf-8")

            with self.assertRaisesRegex(
                beads_history.HistoryValidationError,
                "does not match",
            ):
                beads_history.validate_manifest(
                    manifest_path,
                    issues_path,
                    history_path,
                    issue_records=1,
                    history_records=1,
                )

    def test_validate_base_history_rejects_removed_record(self) -> None:
        base_record = {"record": "preserve-me"}
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            history_path = root / ".beads" / "history.jsonl"
            history_path.parent.mkdir(parents=True)
            history_path.write_text(
                beads_history.render_jsonl([base_record]), encoding="utf-8"
            )
            subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.name", "Test User"], cwd=root, check=True
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=root,
                check=True,
            )
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(
                ["git", "commit", "--quiet", "-m", "base history"],
                cwd=root,
                check=True,
            )
            original_root = beads_history.ROOT
            beads_history.ROOT = root
            try:
                beads_history.validate_base_history("HEAD", [base_record])
                with self.assertRaisesRegex(
                    beads_history.HistoryValidationError,
                    "rewrites or removes 1 record",
                ):
                    beads_history.validate_base_history("HEAD", [])
            finally:
                beads_history.ROOT = original_root


if __name__ == "__main__":
    unittest.main()
