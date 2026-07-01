import importlib.util
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATE_SCRIPT = ROOT / "scripts" / "validate_executive_brief.py"
RENDER_SCRIPT = ROOT / "scripts" / "render_executive_docx.py"
VERIFY_SCRIPT = ROOT / "scripts" / "verify_executive_docx.py"


def has_python_docx() -> bool:
    return importlib.util.find_spec("docx") is not None


def recommendation(name: str, process: str) -> str:
    return f"""### {name}

**Recommendation:** Expand {process} with an agent-assisted triage pattern.

**Why now:** The inventory shows active demand, and public strategy signals a need to reduce cycle time for residents.

**Inventory evidence:** Production and pipeline rows reference {process}, case routing, exception review, and measurable backlog pressure.

**Agentic enhancement:** An agent summarizes case context, retrieves policy guidance, recommends next actions, and routes exceptions for human review.

**UiPath capability fit:** Likely fit for agentic orchestration, robots for system updates, Integration Service, and Action Center for approvals.

**Value levers:** Cycle time, manual effort, quality, auditability, and repeatable capacity across related teams.

**Feasibility:** Start with a bounded queue, one owner group, sampled historical cases, and read-only knowledge retrieval before write-back.

**Governance:** Keep human approval for adverse or high-risk decisions, log recommendations, and validate model outputs against policy.

**Validation questions:**

- Which owner approves the first pilot boundary?
- What sample cases can validate accuracy and exception handling?
- Which system actions require human approval before scale?
"""


def poc(name: str, process: str) -> str:
    return f"""### {name}

**Pilot objective:** Prove that {process} can reduce manual review time without removing human control.

**Narrow scope:** One intake queue, one document or case type, and one owner group.

**Agent role:** Summarize input, retrieve relevant policy, propose routing, and draft the next action.

**Human role:** Review recommendations, approve exceptions, and confirm pilot success criteria.

**Success metrics:** Cycle time, recommendation acceptance, rework rate, backlog reduction, and user feedback.

**Data needed:** Recent cases, policy sources, queue metadata, and sample outcomes.

**Exit criteria:** Scale only if accuracy, handling time, and governance controls meet agreed thresholds.
"""


VALID_BRIEF = f"""# UiPath agentic expansion proposal for Acme City

## Executive Summary

Acme City has enough automation signal to move from scattered process support to a focused agentic expansion plan. The strongest near-term opportunity is citizen-service intake, where production inventory rows, case-routing patterns, and public digital-service priorities point to measurable pressure. The decision ask is to approve a 90-minute workshop that validates ownership, confirms deployment constraints, and selects one low-risk pilot. This brief recommends starting with bounded human-reviewed use cases before scaling the pattern across adjacent departments.

## Source and Assumption Note

- Inventory source: synthetic fixture, 24 rows.
- Public strategy sources: official digital service plan and budget summary.
- Data limitations: volume fields are partial and benefits are directional.
- Value assumptions: sizing uses planning ranges and requires customer validation.

## Current Automation Footprint

| Dimension | Finding | Implication |
|---|---|---|
| Production density | Several live intake and routing automations | Scale candidates should reuse current operating patterns |
| Department concentration | Finance, permits, and citizen services recur | Cross-functional workshops should include these owners |
| Value fields | Backlog and cycle-time fields are incomplete | Keep value ranges conservative |

## Public Strategy Alignment

| Public priority | Evidence summary | Automation relevance |
|---|---|---|
| Digital service access | Official plan prioritizes simpler resident transactions | Intake and exception handling are strong automation targets |
| Operational resilience | Budget narrative calls for faster service delivery | Queue triage and status visibility can reduce backlog |

## Prioritized Portfolio

| Rank | Opportunity | Category | Score | Confidence | Why it matters |
|---:|---|---|---:|---|---|
| 1 | Citizen intake triage | Scale now | 86 | High | Combines strategy alignment, production evidence, and bounded pilot scope |
| 2 | Permit exception routing | Validate next | 79 | Medium | Strong process fit but needs owner confirmation |
| 3 | Invoice exception support | Pilot first | 74 | Medium | Narrow and measurable for a first proof point |

## Top 5 High-Impact Recommendations

{recommendation("Citizen intake triage", "citizen intake")}

{recommendation("Permit exception routing", "permit exception routing")}

{recommendation("Invoice exception support", "invoice exception support")}

{recommendation("Case-status summarization", "case-status summarization")}

{recommendation("Audit evidence preparation", "audit evidence preparation")}

## Top 3 Low-Friction POC Candidates

{poc("Citizen intake POC", "citizen intake")}

{poc("Invoice exception POC", "invoice exception support")}

{poc("Permit routing POC", "permit routing")}

## Value Framing

| Opportunity | Primary value levers | Sizing basis | Confidence | Validation needed |
|---|---|---|---|---|
| Citizen intake triage | Cycle time, quality, resident experience | Inventory backlog fields and sampled cases | Medium | Confirm baseline handling time |
| Invoice exception support | Manual effort and rework | Queue counts and exception rate | Medium | Confirm volume and owner |

## Deployment and Governance Considerations

| Consideration | Implication | Recommended control |
|---|---|---|
| Resident data | Sensitive data may appear in case notes | Use human review and audit logs |
| Model governance | Recommendations must be explainable | Log source references and prompts |

## Facts, Assumptions, and Validation Questions

### Facts

- Inventory rows show production and pipeline activity across intake, permits, and invoice support.
- Public strategy emphasizes simpler digital service access and operational resilience.

### Assumptions

- Existing automation owners can supply sample cases for pilot design.
- Deployment constraints allow a human-reviewed agentic workflow.

### Validation questions

1. Which owner approves the first pilot boundary?
2. Which systems can be accessed safely for read-only pilot work?
3. What success metric determines scale or stop?

## Workshop Prep

| Segment | Time | Purpose | Output |
|---|---:|---|---|
| Evidence review | 20 min | Confirm inventory and strategy signals | Validated shortlist |
| Pilot scoping | 30 min | Pick one bounded pilot | Draft pilot charter |
| Governance review | 20 min | Confirm controls | Risk and control list |

## Recommended Next Steps

1. Confirm workshop attendees from citizen services, permits, finance, IT, and governance.
2. Validate sample-case availability and deployment constraints before the workshop.
3. Select one POC and document the pilot charter within one week of the workshop.

## Appendix: Source Ledger

| Source | Date | Type | Relevant priority |
|---|---|---|---|
| Synthetic Acme inventory | 2026-07-01 | Inventory fixture | Automation footprint |
| Acme digital service plan | 2026-06-01 | Official strategy fixture | Digital service access |
"""


class ExecutiveBriefQualityTests(unittest.TestCase):
    def run_validator(self, markdown_text: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "brief.md"
            source.write_text(markdown_text, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(VALIDATE_SCRIPT), str(source)],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_validate_executive_brief_accepts_complete_fixture(self):
        result = self.run_validator(VALID_BRIEF)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK:", result.stdout)

    def test_validate_executive_brief_rejects_hype_language(self):
        result = self.run_validator(
            VALID_BRIEF.replace(
                "focused agentic expansion plan",
                "revolutionary and game-changing agentic expansion plan",
            )
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Banned hype term", result.stderr)

    def test_validate_executive_brief_rejects_missing_recommendation_fields(self):
        result = self.run_validator(VALID_BRIEF.replace("**Governance:**", "**Control model:**", 1))
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing field(s): Governance", result.stderr)

    def test_validate_executive_brief_rejects_missing_questions_and_source_ledger(self):
        invalid = VALID_BRIEF.replace("Appendix: Source Ledger", "Appendix: Evidence")
        invalid = invalid.replace("?", ".")
        result = self.run_validator(invalid)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Missing appendix/source ledger", result.stderr)
        self.assertIn("Expected at least 3 explicit validation questions", result.stderr)

    @unittest.skipUnless(has_python_docx(), "python-docx is not installed")
    def test_rendered_docx_passes_brand_style_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            markdown = tmp_path / "brief.md"
            outputs = tmp_path / "outputs"
            docx = outputs / "brief.docx"
            markdown.write_text(VALID_BRIEF, encoding="utf-8")

            quality = subprocess.run(
                [sys.executable, str(VALIDATE_SCRIPT), str(markdown)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(quality.returncode, 0, quality.stderr)

            render = subprocess.run(
                [sys.executable, str(RENDER_SCRIPT), str(markdown), str(docx), "--portrait"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(render.returncode, 0, render.stderr)

            verify = subprocess.run(
                [
                    sys.executable,
                    str(VERIFY_SCRIPT),
                    str(docx),
                    "--require-output-dir",
                    "--require-brand-style",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(verify.returncode, 0, verify.stderr)

            with zipfile.ZipFile(docx) as archive:
                xml = "\n".join(
                    archive.read(name).decode("utf-8", errors="ignore").upper()
                    for name in archive.namelist()
                    if name.startswith("word/") and name.endswith(".xml")
                )
            self.assertIn("FA4616", xml)
            self.assertIn("182126", xml)
            self.assertIn("0BA2B3", xml)
            self.assertNotIn("1F4E79", xml)


if __name__ == "__main__":
    unittest.main()
