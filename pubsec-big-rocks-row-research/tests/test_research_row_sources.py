import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


OPENPYXL_AVAILABLE = importlib.util.find_spec("openpyxl") is not None
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "research_row_sources.py"


def load_module():
    spec = importlib.util.spec_from_file_location("research_row_sources", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(OPENPYXL_AVAILABLE, "openpyxl is not installed")
class ResearchRowSourcesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()
        from openpyxl import Workbook

        cls.Workbook = Workbook

    def write_main_workbook(self, path: Path) -> None:
        wb = self.Workbook()
        ws = wb.active
        ws.title = self.module.MAIN_SHEET
        ws.cell(7, 1).value = "Account"
        for col, header in self.module.TARGET_HEADERS.items():
            ws.cell(7, col).value = header
        ws.cell(8, 1).value = "Department of Fixtures"
        ws.cell(8, 11).value = "•"
        ws.cell(8, 12).value = "-"
        ws.cell(8, 13).value = "No"

        current = wb.create_sheet("Current 2026-06-15")
        current.append(["Account", "Notes", "Last Updated"])
        current.append(
            [
                "Department of Fixtures",
                "Automation Cloud and Document Understanding pilot for intake.",
                "2026-06-20",
            ]
        )

        stale = wb.create_sheet("Old 2025-01-01")
        stale.append(["Account", "Notes", "Last Updated"])
        stale.append(["Department of Fixtures", "Old test status", "2025-01-02"])
        wb.save(path)

    def write_source_workbook(self, path: Path, last_updated: str = "2026-06-20") -> None:
        wb = self.Workbook()
        ws = wb.active
        ws.title = "Accounts"
        ws.append(["Account", "Current Platform", "IXP Status", "Last Updated"])
        ws.append(
            [
                "Department of Fixtures",
                "Automation Cloud",
                "Using DU for permit intake",
                last_updated,
            ]
        )
        wb.save(path)

    def test_cli_json_detects_target_row_sources_stale_rows_and_missing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            workbook = tmp_path / "big-rocks.xlsx"
            current_source = tmp_path / "source-current.xlsx"
            stale_source = tmp_path / "source-stale.xlsx"
            missing_source = tmp_path / "missing.xlsx"
            self.write_main_workbook(workbook)
            self.write_source_workbook(current_source)
            self.write_source_workbook(stale_source, last_updated="2025-01-01")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--workbook",
                    str(workbook),
                    "--account",
                    "Department of Fixtures",
                    "--source",
                    str(current_source),
                    "--source",
                    str(stale_source),
                    "--source",
                    str(missing_source),
                    "--sources-only",
                    "--as-of-date",
                    "2026-07-01",
                    "--format",
                    "json",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["target_row"]["row"], 8)
            blank_cells = {item["cell"] for item in payload["target_row"]["blank_target_fields"]}
            self.assertIn("K8", blank_cells)
            self.assertIn("L8", blank_cells)
            self.assertEqual(payload["source_matches"][0]["matched_name"], "Department of Fixtures")
            self.assertIn("Cloud Y/N", payload["recommendation_leads"])
            self.assertIn("IXP Status", payload["recommendation_leads"])
            self.assertIn(str(missing_source), payload["missing_source_files"])
            excluded_reasons = [item["reason"] for item in payload["excluded_as_stale_or_undated"]]
            self.assertIn("row update/activity date before cutoff", excluded_reasons)
            self.assertIn("sheet name date before cutoff", excluded_reasons)

    def test_markdown_output_contains_do_not_fill_context_sections(self):
        result = {
            "target_row": {
                "row": 8,
                "account": "Department of Fixtures",
                "blank_target_fields": [{"cell": "K8", "header": "Bot/License Utilization"}],
            },
            "recency": {"cutoff_date": "2026-04-01", "as_of_date": "2026-07-01"},
            "source_matches": [],
            "internal_workbook_matches": [],
            "recommendation_leads": {},
            "missing_source_files": ["/tmp/missing.xlsx"],
            "excluded_as_stale_or_undated": [
                {"source_file": "/tmp/source.xlsx", "reason": "row update/activity date before cutoff"}
            ],
        }

        markdown = self.module.render_markdown(result)

        self.assertIn("**Blank / Placeholder Target Fields**", markdown)
        self.assertIn("K8 Bot/License Utilization", markdown)
        self.assertIn("**Do Not Fill Guidance**", markdown)
        self.assertIn("continue SharePoint/Slack/OneNote searches", markdown)
        self.assertIn("**Excluded As Stale Or Undated**", markdown)

    def test_include_stale_keeps_stale_matches_as_discovery_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            workbook = tmp_path / "big-rocks.xlsx"
            stale_source = tmp_path / "source-stale.xlsx"
            self.write_main_workbook(workbook)
            self.write_source_workbook(stale_source, last_updated="2025-01-01")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--workbook",
                    str(workbook),
                    "--account",
                    "Department of Fixtures",
                    "--source",
                    str(stale_source),
                    "--sources-only",
                    "--include-stale",
                    "--as-of-date",
                    "2026-07-01",
                    "--format",
                    "json",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["source_matches"][0]["matched_name"], "Department of Fixtures")
            self.assertEqual(
                payload["source_matches"][0]["stale_row_update_dates"][0]["date"],
                "2025-01-01",
            )
            self.assertEqual(payload["missing_source_files"], [])


if __name__ == "__main__":
    unittest.main()
