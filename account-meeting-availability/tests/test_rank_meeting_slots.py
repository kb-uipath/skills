import copy
import contextlib
import importlib.util
import io
import json
import stat
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "rank_meeting_slots.py"
FIXTURES = ROOT / "tests" / "fixtures"


def load_module():
    spec = importlib.util.spec_from_file_location("rank_meeting_slots", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RankMeetingSlotsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def load_fixture(self, name: str):
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    def test_ranking_is_deterministic_and_prefers_optional_attendance(self):
        request = self.load_fixture("free_busy_rankable_v1.json")

        first = self.module.rank_request(request)
        second = self.module.rank_request(copy.deepcopy(request))

        self.assertEqual(first, second)
        self.assertEqual(first["status"], "ranked")
        self.assertEqual(first["eligible_slot_count"], 7)
        self.assertEqual(
            [slot["start"] for slot in first["ranked_slots"]],
            [
                "2026-07-15T16:00:00Z",
                "2026-07-15T17:00:00Z",
                "2026-07-15T17:30:00Z",
            ],
        )
        self.assertTrue(
            all(slot["optional_available_count"] == 1 for slot in first["ranked_slots"])
        )

    def test_local_times_are_rendered_in_each_iana_time_zone(self):
        result = self.module.rank_request(self.load_fixture("free_busy_rankable_v1.json"))

        local_times = {
            value["participant_id"]: value for value in result["ranked_slots"][0]["local_times"]
        }
        self.assertEqual(local_times["customer-owner"]["start"], "2026-07-15T12:00:00-04:00")
        self.assertEqual(local_times["uipath-owner"]["start"], "2026-07-15T11:00:00-05:00")
        self.assertEqual(
            local_times["optional-specialist"]["start"], "2026-07-15T09:00:00-07:00"
        )

    def test_display_labels_and_exclusion_diagnostics_are_privacy_safe(self):
        request = self.load_fixture("free_busy_rankable_v1.json")
        request["participants"][0]["display_name"] = "Customer Operations Lead"
        request["participants"][1]["display_name"] = "UiPath Account Lead"

        result = self.module.rank_request(request)

        self.assertEqual(
            result["participant_labels"]["customer-owner"], "Customer Operations Lead"
        )
        self.assertEqual(
            result["ranked_slots"][0]["local_times"][0]["display_name"],
            "Customer Operations Lead",
        )
        self.assertEqual(
            result["candidate_diagnostics"]["reason_counts"],
            {"blocking_busy": 2, "blocking_tentative": 1},
        )
        self.assertEqual(result["candidate_diagnostics"]["evaluated_slot_count"], 10)
        self.assertEqual(result["candidate_diagnostics"]["excluded_slot_count"], 3)
        self.assertFalse(result["candidate_diagnostics"]["excluded_slots_truncated"])
        self.assertNotIn("owner@example.gov", json.dumps(result))

    def test_optional_unavailability_has_a_privacy_safe_reason(self):
        request = self.load_fixture("free_busy_rankable_v1.json")
        request["max_results"] = 10
        request["participants"][2]["display_name"] = "Optional Platform Specialist"

        result = self.module.rank_request(request)
        affected = next(
            slot
            for slot in result["ranked_slots"]
            if slot["start"] == "2026-07-15T16:30:00Z"
        )

        self.assertEqual(
            affected["optional_unavailability"],
            [
                {
                    "participant_id": "optional-specialist",
                    "display_name": "Optional Platform Specialist",
                    "reason": "blocking_busy",
                }
            ],
        )
        self.assertNotIn("@", json.dumps(affected))

    def test_exclusion_diagnostics_are_bounded_without_losing_counts(self):
        request = self.load_fixture("free_busy_rankable_v1.json")
        request["window"]["start"] = "2026-07-15T00:00:00Z"
        request["window"]["end"] = "2026-07-20T00:00:00Z"

        result = self.module.rank_request(request)
        diagnostics = result["candidate_diagnostics"]

        self.assertGreater(diagnostics["excluded_slot_count"], 100)
        self.assertEqual(len(diagnostics["excluded_slots"]), 100)
        self.assertTrue(diagnostics["excluded_slots_truncated"])
        self.assertGreaterEqual(
            sum(diagnostics["reason_counts"].values()),
            diagnostics["excluded_slot_count"],
        )

    def test_runtime_preflight_is_explicit(self):
        self.assertIn(
            "requires Python 3.11 or newer",
            self.module.python_runtime_failure((3, 10, 9)),
        )
        self.assertIsNone(self.module.python_runtime_failure((3, 11, 0)))

    def test_no_common_slot_is_an_explicit_successful_outcome(self):
        request = self.load_fixture("free_busy_no_common_slot_v1.json")
        result = self.module.rank_request(request)

        self.assertEqual(result["status"], "no_common_slot")
        self.assertEqual(result["eligible_slot_count"], 0)
        self.assertEqual(result["ranked_slots"], [])
        self.assertIn("No slot satisfies", result["reason"])

    def test_non_read_only_source_and_duplicate_participant_identity_fail_closed(self):
        request = self.load_fixture("free_busy_rankable_v1.json")
        request["source"]["retrieval_mode"] = "read-write"
        with self.assertRaisesRegex(ValueError, "must be 'read-only'"):
            self.module.rank_request(request)

        request = self.load_fixture("free_busy_rankable_v1.json")
        request["participants"][1]["email"] = request["participants"][0]["email"]
        with self.assertRaisesRegex(ValueError, "duplicate participant email"):
            self.module.rank_request(request)

    def test_cli_writes_private_versioned_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "ranked.json"
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = self.module.main(
                    [
                        str(FIXTURES / "free_busy_rankable_v1.json"),
                        "--output",
                        str(output),
                    ]
                )

            self.assertEqual(code, 0, stderr.getvalue())
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["schema_version"], "1.0")
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
