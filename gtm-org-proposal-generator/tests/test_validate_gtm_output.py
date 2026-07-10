import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_gtm_output.py"


def load_module():
    spec = importlib.util.spec_from_file_location("validate_gtm_output", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


VALID_CONTRACT = {
    "contract_version": "gtm-org-proposal-generator/v1",
    "confirmed_scope": {
        "organization": "Fixture Agency",
        "target_entity": "Fixture Agency Benefits Division",
        "industry_vertical": "Public sector",
        "uipath_deployment_type": "Automation Cloud Public Sector",
        "research_scope": "public-authoritative-only",
        "accessed_date": "2026-07-10",
    },
    "classification": {
        "data_classification": "Public",
        "retention": "Retain only in approved public-source GTM workspaces per account-team policy.",
    },
    "source_ledger": [
        {
            "source_id": "S1",
            "title": "FY2026 budget book",
            "publisher": "Fixture Agency",
            "publication_date": "FY2026",
            "url": "https://example.gov/budget",
            "accessed_date": "2026-07-10",
            "facts_supported": ["Benefits budget"],
        },
        {
            "source_id": "S2",
            "title": "UiPath Document Understanding documentation",
            "publisher": "UiPath",
            "publication_date": "2026-07-10",
            "url": "https://docs.uipath.com/document-understanding",
            "accessed_date": "2026-07-10",
            "facts_supported": ["Capability availability evidence"],
        },
    ],
    "capability_ledger": [
        {
            "capability_id": "C1",
            "capability_name": "Document Understanding",
            "deployment_type": "Automation Cloud Public Sector",
            "availability": "requires-confirmation",
            "docs_url": "https://docs.uipath.com/document-understanding",
            "docs_checked_date": "2026-07-10",
            "source_ids": ["S2"],
        }
    ],
    "budget_program_areas": [
        {
            "rank": 1,
            "program_area": "Benefits licensing services",
            "budget": "$10,000,000",
            "budget_basis": "FY2026 operating budget",
            "source_ids": ["S1"],
            "admin_cost": {
                "estimate": "$1,000,000 / 10%",
                "tier": "Derived",
                "math": "$10,000,000 x 10% planning assumption",
                "source_ids": ["S1"],
            },
        }
    ],
    "prioritized_use_cases": [
        {
            "rank": 1,
            "use_case": "Benefits document intake",
            "target_program_area": "Benefits licensing services",
            "driver": "Manual document intake creates avoidable review effort.",
            "capability_ids": ["C1"],
            "impact_range": "$250,000-$500,000 potential annual value",
            "confidence": "Medium",
            "estimate_tier": "Derived",
            "source_ids": ["S1"],
            "impact_math": {
                "baseline": "$10,000,000 benefits operating budget",
                "addressable_share": "5% addressable administrative workload",
                "productivity_or_cost_assumption": "50% handling-effort reduction on addressable work",
                "resulting_range": "$250,000-$500,000 potential annual value",
                "source_ids": ["S1"],
            },
        }
    ],
    "proposal_cards": [
        {
            "rank": 1,
            "use_case": "Benefits document intake",
            "business_challenge": "The benefits team has a $10,000,000 operating budget with manual document intake pressure.",
            "proposed_solution": "Use deployment-appropriate document extraction with human review for exceptions.",
            "capability_ids": ["C1"],
            "estimated_impact": "$250,000-$500,000 potential annual value",
            "estimate_tier": "Derived",
            "impact_math": {
                "baseline": "$10,000,000 benefits operating budget",
                "addressable_share": "5% addressable administrative workload",
                "productivity_or_cost_assumption": "50% handling-effort reduction on addressable work",
                "resulting_range": "$250,000-$500,000 potential annual value",
                "source_ids": ["S1"],
            },
            "confidence": "Medium",
            "source_ids": ["S1"],
            "validation_required": [
                "Confirm monthly document volume with program owner.",
                "Confirm deployment availability for Document Understanding in the tenant.",
            ],
        }
    ],
    "evidence_gaps": [
        {
            "gap": "Fewer than 10 proposal cards are included because only one source-backed use case is complete.",
            "impact": "Portfolio breadth is intentionally limited until more public sources are available.",
            "resolution_path": "Add source-backed process volume, backlog, or staffing evidence before adding cards.",
        }
    ],
    "assumptions": [
        "Impact range is planning-only until process mining or SME volume data is available."
    ],
}


GOLDEN_MARKDOWN = """# Fixture Agency GTM Proposal

Contract version: `gtm-org-proposal-generator/v1`
Data classification: Public
Retention: Retain only in approved public-source GTM workspaces per account-team policy.

## Confirmed Scope

- Organization: Fixture Agency
- Target entity: Fixture Agency Benefits Division
- Industry vertical: Public sector
- UiPath deployment type: Automation Cloud Public Sector
- Research scope: public-authoritative-only
- Accessed date: 2026-07-10

## Source Ledger

| Source ID | Title | Publisher | Date/FY | URL | Accessed | Facts Supported |
| --- | --- | --- | --- | --- | --- | --- |
| [S1] | FY2026 budget book | Fixture Agency | FY2026 | https://example.gov/budget | 2026-07-10 | Benefits budget |
| [S2] | UiPath Document Understanding documentation | UiPath | 2026-07-10 | https://docs.uipath.com/document-understanding | 2026-07-10 | Capability availability evidence |

## Capability Ledger

| Capability ID | Capability | Deployment | Availability | Docs Checked | Docs URL | Sources |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | Document Understanding | Automation Cloud Public Sector | requires-confirmation | 2026-07-10 | https://docs.uipath.com/document-understanding | [S2] |

## Budget / Program Areas

| Rank | Program / Area | Budget | Budget Basis | Admin Cost | Admin Tier | Admin Math | Sources |
| ---: | --- | ---: | --- | ---: | --- | --- | --- |
| 1 | Benefits licensing services | $10,000,000 | FY2026 operating budget | $1,000,000 / 10% | Derived | $10,000,000 x 10% planning assumption | [S1] |

## Prioritized Use Cases

| Rank | Use Case | Target Program / Area | Evidence-Based Driver | UiPath Capability Fit | Estimated Impact Range | Confidence | Estimate Tier | Sources |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Benefits document intake | Benefits licensing services | Manual document intake creates avoidable review effort. | Document Understanding (C1) | $250,000-$500,000 potential annual value | Medium | Derived | [S1] |

## Proposal Cards

### 1. Benefits document intake

**Business Challenge**: The benefits team has a $10,000,000 operating budget with manual document intake pressure.

**Proposed Solution**: Use deployment-appropriate document extraction with human review for exceptions.

**Relevant UiPath Capabilities**: Document Understanding (C1)

**Estimated Impact**: $250,000-$500,000 potential annual value

**Impact Math**: Baseline: $10,000,000 benefits operating budget; Addressable share: 5% addressable administrative workload; Productivity/cost assumption: 50% handling-effort reduction on addressable work; Resulting range: $250,000-$500,000 potential annual value.

**Estimate Tier**: Derived
**Confidence**: Medium
**Sources**: [S1]
**Validation Required**: Confirm monthly document volume with program owner.; Confirm deployment availability for Document Understanding in the tenant.

## Evidence Gaps

- Fewer than 10 proposal cards are included because only one source-backed use case is complete. Impact: Portfolio breadth is intentionally limited until more public sources are available. Resolution: Add source-backed process volume, backlog, or staffing evidence before adding cards.

## Assumptions and Validation Needed

- Impact range is planning-only until process mining or SME volume data is available.
"""


class ValidateGtmOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_valid_contract_passes_and_renders_golden_markdown(self):
        self.assertEqual(self.module.validate_contract(VALID_CONTRACT), [])

        rendered = self.module.render_markdown(VALID_CONTRACT)

        self.assertEqual(rendered, GOLDEN_MARKDOWN)

    def test_cli_validates_and_renders_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            contract_path = Path(tmp) / "contract.json"
            rendered_path = Path(tmp) / "proposal.md"
            contract_path.write_text(json.dumps(VALID_CONTRACT), encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(contract_path), "--render", str(rendered_path)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(rendered_path.read_text(encoding="utf-8"), GOLDEN_MARKDOWN)
            self.assertIn("validated and rendered", result.stdout)

    def test_legacy_markdown_fails_closed_with_migration_guidance(self):
        errors = self.module.validate_text("## Confirmed Scope\n\nlegacy markdown\n")

        self.assertEqual(len(errors), 1)
        self.assertIn("legacy free-form Markdown validation is disabled", errors[0])

    def test_missing_source_reference_fails(self):
        contract = copy.deepcopy(VALID_CONTRACT)
        contract["proposal_cards"][0]["source_ids"] = ["S99"]

        errors = self.module.validate_contract(contract)

        self.assertIn(
            "proposal_cards[1].source_ids references undefined source ID: S99",
            errors,
        )

    def test_capability_deployment_and_date_validation_fail(self):
        contract = copy.deepcopy(VALID_CONTRACT)
        contract["capability_ledger"][0]["deployment_type"] = "Automation Suite"
        contract["capability_ledger"][0]["docs_checked_date"] = "2026-07-11"

        errors = self.module.validate_contract(contract)

        self.assertIn(
            "capability_ledger[1].deployment_type must match confirmed_scope.uipath_deployment_type",
            errors,
        )
        self.assertIn(
            "capability_ledger[1].docs_checked_date cannot be after confirmed_scope.accessed_date",
            errors,
        )

    def test_fewer_than_10_cards_requires_evidence_gap_but_not_10_cards(self):
        self.assertEqual(len(VALID_CONTRACT["proposal_cards"]), 1)
        self.assertEqual(self.module.validate_contract(VALID_CONTRACT), [])

        contract = copy.deepcopy(VALID_CONTRACT)
        contract["evidence_gaps"] = []

        errors = self.module.validate_contract(contract)

        self.assertIn(
            "evidence_gaps must explain why fewer than 10 proposal cards were produced",
            errors,
        )

    def test_math_tier_and_unsafe_claim_quality_checks_fail(self):
        contract = copy.deepcopy(VALID_CONTRACT)
        del contract["proposal_cards"][0]["impact_math"]["addressable_share"]
        contract["proposal_cards"][0]["estimate_tier"] = "Guess"
        contract["proposal_cards"][0]["estimated_impact"] = "Guaranteed ROI with no risk"

        errors = self.module.validate_contract(contract)

        self.assertIn(
            "proposal_cards[1].estimate_tier must be one of Assumption, Benchmarked, Derived, Documented",
            errors,
        )
        self.assertIn(
            "proposal_cards[1].impact_math.addressable_share is required",
            errors,
        )
        self.assertTrue(any("unsupported overclaim phrase" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
