import importlib.util
import hashlib
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render_council_artifacts.py"
SCHEMA = ROOT / "references" / "session-schema-v1.json"


def digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_module():
    spec = importlib.util.spec_from_file_location("render_council_artifacts", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def session_payload() -> dict:
    advisors = {
        "The Contrarian": "This fails if the downside is ignored.",
        "The First Principles Thinker": "Start with the customer job and constraints.",
        "The Expansionist": "The adjacent market could make this bigger.",
        "The Outsider": "A buyer would compare this to doing nothing.",
        "The Executor": "Ship only after owner, budget, and metric are clear.",
    }
    original_question = "Should we launch <now>?"
    framed_question = "Decide whether the launch should proceed this quarter."
    return {
        "schema_version": "llm-council.session.v1",
        "original_question": original_question,
        "framed_question": framed_question,
        "chairman_verdict": "Proceed only with a narrow launch gate.",
        "decision_criteria": ["Revenue impact outweighs delivery risk."],
        "disconfirming_evidence": ["The pilot lacks a named owner or success metric."],
        "review_date": "2026-07-10",
        "confidence": {
            "level": "medium",
            "rationale": "The council has enough launch evidence, but no live customer validation.",
        },
        "execution_mode": "subagents",
        "fallback_reason": "",
        "metadata": {
            "preparer": "codex",
            "preparer_seed": "fixture-seed",
            "run_id": "council-fixture-001",
            "model_ids": ["fixture-model"],
            "advisor_agent_ids": [f"advisor-{index}" for index in range(1, 6)],
            "reviewer_agent_ids": [f"reviewer-{index}" for index in range(1, 6)],
            "input_hashes": {
                "original_question": digest(original_question),
                "framed_question": digest(framed_question),
            },
            "created_at": "2026-07-10T12:00:00Z",
            "sensitivity": "internal",
            "permissions": ["local workspace only"],
            "retention": "Delete when the launch review is superseded.",
        },
        "advisors": advisors,
        "advisor_positions": [
            {
                "advisor": "The Contrarian",
                "position": "Do not launch without proof.",
                "stance": "negative",
            }
        ],
        "peer_reviews": [
            {"reviewer": f"Reviewer {index}", "response": f"Review {index} is specific."}
            for index in range(1, 6)
        ],
        "anonymization_mapping": {
            "Response A": "The Outsider",
            "Response B": "The Contrarian",
            "Response C": "The Executor",
            "Response D": "The Expansionist",
            "Response E": "The First Principles Thinker",
        },
    }


class RenderCouncilArtifactsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_cli_renders_html_and_markdown_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "session.json"
            source.write_text(json.dumps(session_payload()), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(source),
                    "--output-dir",
                    str(tmp_path),
                    "--timestamp",
                    "fixture",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            html_path = tmp_path / "council-report-fixture.html"
            markdown_path = tmp_path / "council-transcript-fixture.md"
            self.assertTrue(html_path.exists())
            self.assertTrue(markdown_path.exists())
            html = html_path.read_text(encoding="utf-8")
            markdown = markdown_path.read_text(encoding="utf-8")
            self.assertIn("LLM Council Report", html)
            self.assertIn("Should we launch &lt;now&gt;?", html)
            self.assertIn("Chairman Verdict", html)
            self.assertIn("Session Metadata", html)
            self.assertIn("sha256:", html)
            self.assertIn("The Contrarian", markdown)
            self.assertIn("## Decision Criteria", markdown)
            self.assertIn("## Anonymization Mapping", markdown)
            self.assertEqual(stat.S_IMODE(html_path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(markdown_path.stat().st_mode), 0o600)

    def test_load_session_rejects_missing_required_advisor(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = session_payload()
            payload["advisors"].pop("The Executor")
            source = Path(tmp) / "session.json"
            source.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "five required names"):
                self.module.load_session(source)

    def test_load_session_rejects_invalid_peer_review_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = session_payload()
            payload["peer_reviews"] = {"reviewer": "not a list"}
            source = Path(tmp) / "session.json"
            source.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "peer_reviews"):
                self.module.load_session(source)

    def test_validate_only_does_not_write_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "session.json"
            outdir = tmp_path / "out"
            source.write_text(json.dumps(session_payload()), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(source),
                    "--output-dir",
                    str(outdir),
                    "--validate-only",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("advisors=5", result.stdout)
            self.assertIn("schema=llm-council.session.v1", result.stdout)
            self.assertIn("session_hash=sha256:", result.stdout)
            self.assertFalse(outdir.exists())

    def test_validate_session_schema_requires_string_core_fields(self):
        payload = session_payload()
        payload["original_question"] = ["not", "string"]
        with self.assertRaisesRegex(SystemExit, "must be a string"):
            self.module.validate_session_schema(payload)

    def test_load_session_rejects_legacy_payload_without_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = {
                "original_question": "Legacy question",
                "framed_question": "Legacy frame",
                "chairman_verdict": "Legacy verdict",
                "advisors": {"The Contrarian": "Only one response"},
            }
            source = Path(tmp) / "session.json"
            source.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "Migration"):
                self.module.load_session(source)

    def test_load_session_rejects_non_bijective_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = session_payload()
            payload["anonymization_mapping"]["Response A"] = "The Contrarian"
            source = Path(tmp) / "session.json"
            source.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "bijectively"):
                self.module.load_session(source)

    def test_load_session_rejects_tampered_input_hash_and_agent_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = session_payload()
            payload["framed_question"] += " Tampered."
            payload["metadata"]["reviewer_agent_ids"] = payload["metadata"][
                "advisor_agent_ids"
            ]
            source = Path(tmp) / "session.json"
            source.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "disjoint"):
                self.module.load_session(source)

            payload["metadata"]["reviewer_agent_ids"] = [
                f"reviewer-{index}" for index in range(1, 6)
            ]
            source.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "input_hashes do not match"):
                self.module.load_session(source)

    def test_cli_prepare_template_is_seeded_and_strict(self):
        first = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--prepare-template",
                "--seed",
                "stable-seed",
                "--original-question",
                "Should we expand?",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        second = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--prepare-template",
                "--seed",
                "stable-seed",
                "--original-question",
                "Should we expand?",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        first_payload = json.loads(first.stdout)
        second_payload = json.loads(second.stdout)
        self.assertEqual(
            first_payload["anonymization_mapping"],
            second_payload["anonymization_mapping"],
        )
        self.assertEqual(set(first_payload["anonymization_mapping"]), {f"Response {letter}" for letter in "ABCDE"})
        self.assertIn("run_id", first_payload["metadata"])
        self.assertIn("input_hashes", first_payload["metadata"])

    def test_cli_refuses_collision_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "session.json"
            source.write_text(json.dumps(session_payload()), encoding="utf-8")
            command = [
                sys.executable,
                str(SCRIPT),
                str(source),
                "--output-dir",
                str(tmp_path),
                "--timestamp",
                "collision",
            ]

            first = subprocess.run(command, capture_output=True, text=True, check=False)
            second = subprocess.run(command, capture_output=True, text=True, check=False)
            overwrite = subprocess.run(command + ["--overwrite"], capture_output=True, text=True, check=False)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("Refusing to overwrite", second.stderr)
            self.assertEqual(overwrite.returncode, 0, overwrite.stderr)

    def test_single_agent_fallback_is_rendered_truthfully(self):
        payload = session_payload()
        payload["execution_mode"] = "single_agent_fallback"
        payload["fallback_reason"] = "Subagent tools were unavailable in this environment."
        payload["metadata"]["advisor_agent_ids"] = []
        payload["metadata"]["reviewer_agent_ids"] = []
        loaded = dict(payload)
        loaded["advisors"] = dict(payload["advisors"])
        loaded["peer_reviews"] = list(payload["peer_reviews"])
        self.module.validate_session_schema(loaded)
        loaded["advisors"] = self.module.normalize_advisors(loaded["advisors"])
        loaded["peer_reviews"] = self.module.normalize_peer_reviews(loaded["peer_reviews"])
        self.module.validate_strict_contract(loaded)
        loaded["metadata"]["hashes"] = self.module.derive_content_hashes(loaded)

        html = self.module.render_html(loaded, "fallback")
        markdown = self.module.render_markdown(loaded, "fallback")

        self.assertIn("Single-agent fallback", html)
        self.assertIn("Single-agent fallback reason", markdown)

    def test_rendering_is_deterministic_and_sensitivity_override_is_hashed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "session.json"
            source.write_text(json.dumps(session_payload()), encoding="utf-8")
            outputs = []
            for name in ("first", "second"):
                outdir = root / name
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        str(source),
                        "--output-dir",
                        str(outdir),
                        "--timestamp",
                        "stable",
                        "--sensitivity",
                        "confidential",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                outputs.append(
                    (
                        (outdir / "council-report-stable.html").read_bytes(),
                        (outdir / "council-transcript-stable.md").read_bytes(),
                    )
                )
            self.assertEqual(outputs[0], outputs[1])
            self.assertIn(b"confidential", outputs[0][0])

    def test_published_schema_requires_operational_metadata(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        metadata_required = set(schema["$defs"]["metadata"]["required"])
        self.assertTrue(
            {
                "run_id",
                "model_ids",
                "advisor_agent_ids",
                "reviewer_agent_ids",
                "input_hashes",
            }.issubset(metadata_required)
        )


if __name__ == "__main__":
    unittest.main()
