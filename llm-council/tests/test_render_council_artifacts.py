import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render_council_artifacts.py"


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
    return {
        "original_question": "Should we launch <now>?",
        "framed_question": "Decide whether the launch should proceed this quarter.",
        "chairman_verdict": "Proceed only with a narrow launch gate.",
        "advisors": advisors,
        "advisor_positions": [
            {
                "advisor": "The Contrarian",
                "position": "Do not launch without proof.",
                "stance": "negative",
            }
        ],
        "peer_reviews": [{"reviewer": "Reviewer A", "response": "Verdict is balanced."}],
        "anonymization_mapping": {"A": "The Contrarian"},
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
            self.assertIn("The Contrarian", markdown)
            self.assertIn("## Anonymization Mapping", markdown)

    def test_load_session_rejects_missing_required_advisor(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = session_payload()
            payload["advisors"].pop("The Executor")
            source = Path(tmp) / "session.json"
            source.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "Missing advisor response"):
                self.module.load_session(source)

    def test_load_session_rejects_invalid_peer_review_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = session_payload()
            payload["peer_reviews"] = {"reviewer": "not a list"}
            source = Path(tmp) / "session.json"
            source.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "peer_reviews"):
                self.module.load_session(source)


if __name__ == "__main__":
    unittest.main()
