import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
GOLDEN = ROOT / "tests" / "fixtures" / "golden"
PROFILER = SCRIPTS / "inventory_profiler.py"
SCORER = SCRIPTS / "score_portfolio.py"
VALIDATOR = SCRIPTS / "validate_portfolio.py"
RENDERER = SCRIPTS / "render_portfolio_markdown.py"
BRIEF_VALIDATOR = SCRIPTS / "validate_executive_brief.py"
CASES = ("sparse", "noisy", "on_prem")

sys.path.insert(0, str(SCRIPTS))
from portfolio_contracts import (  # noqa: E402
    evaluate_outcome_rubric,
    score_portfolio,
    validate_evidence_ledger,
    validate_portfolio,
)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def case_artifacts(case: str):
    case_dir = GOLDEN / case
    return (
        load_json(case_dir / "evidence_ledger.json"),
        load_json(case_dir / "portfolio.json"),
        load_json(case_dir / "expected_outcomes.json"),
    )


def profile_case(case: str, destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    source = destination / "inventory.csv"
    output = destination / "profile"
    shutil.copyfile(GOLDEN / case / "inventory.csv", source)
    result = subprocess.run(
        [sys.executable, str(PROFILER), "--input", str(source), "--outdir", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return load_json(output / "inventory_profile.json"), output / "inventory_profile.json"


class PortfolioPipelineTests(unittest.TestCase):
    def test_synthetic_goldens_validate_and_match_outcome_rubrics(self):
        for case in CASES:
            with self.subTest(case=case):
                ledger, portfolio, expected = case_artifacts(case)
                self.assertEqual(validate_portfolio(portfolio, ledger), [])
                self.assertEqual(score_portfolio(portfolio), portfolio)
                rubric = evaluate_outcome_rubric(portfolio, ledger)
                self.assertEqual(rubric["specificity"], expected["specificity"])
                self.assertEqual(rubric["decision_utility"], expected["decision_utility"])
                self.assertEqual(
                    rubric["pilot_actionability"], expected["pilot_actionability"]
                )

    def test_profiler_generates_stable_ids_used_by_each_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case in CASES:
                with self.subTest(case=case):
                    profile, _profile_path = profile_case(case, root / case)
                    ledger, portfolio, _expected = case_artifacts(case)
                    self.assertEqual(profile["schema_version"], "1.0")
                    self.assertEqual(
                        {item["inventory_id"] for item in profile["inventory_items"]},
                        set(ledger["inventory_profile"]["inventory_ids"]),
                    )
                    self.assertEqual(
                        validate_portfolio(portfolio, ledger, profile=profile), []
                    )

    def test_score_cli_is_deterministic_and_reconstructs_golden(self):
        ledger, portfolio, _expected = case_artifacts("noisy")
        draft = copy.deepcopy(portfolio)
        draft.pop("rankings")
        for opportunity in draft["opportunities"]:
            opportunity.pop("scores")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger_path = root / "evidence_ledger.json"
            draft_path = root / "portfolio_draft.json"
            first = root / "portfolio.first.json"
            second = root / "portfolio.second.json"
            ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
            draft_path.write_text(json.dumps(draft), encoding="utf-8")
            for output in (first, second):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCORER),
                        "--evidence-ledger",
                        str(ledger_path),
                        "--portfolio",
                        str(draft_path),
                        "--output",
                        str(output),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(load_json(first), portfolio)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_rendered_markdown_is_deterministic_and_passes_strict_cross_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case in CASES:
                with self.subTest(case=case):
                    case_dir = GOLDEN / case
                    profile, profile_path = profile_case(case, root / case)
                    first = root / case / "brief.first.md"
                    second = root / case / "brief.second.md"
                    for output in (first, second):
                        result = subprocess.run(
                            [
                                sys.executable,
                                str(RENDERER),
                                "--evidence-ledger",
                                str(case_dir / "evidence_ledger.json"),
                                "--portfolio",
                                str(case_dir / "portfolio.json"),
                                "--inventory-profile",
                                str(profile_path),
                                "--output",
                                str(output),
                            ],
                            capture_output=True,
                            text=True,
                            check=False,
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(first.read_bytes(), second.read_bytes())
                    self.assertEqual(profile["schema_version"], "1.0")

                    validation = subprocess.run(
                        [
                            sys.executable,
                            str(BRIEF_VALIDATOR),
                            str(first),
                            "--min-recommendations",
                            "1",
                            "--min-pocs",
                            "1",
                            "--portfolio",
                            str(case_dir / "portfolio.json"),
                            "--evidence-ledger",
                            str(case_dir / "evidence_ledger.json"),
                            "--inventory-profile",
                            str(profile_path),
                            "--max-source-age-days",
                            "365",
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(validation.returncode, 0, validation.stderr)

    def test_contracts_fail_closed_for_legacy_and_inconsistent_claims(self):
        noisy_ledger, noisy_portfolio, _expected = case_artifacts("noisy")
        legacy = copy.deepcopy(noisy_ledger)
        legacy.pop("schema_version")
        self.assertIn("Unversioned legacy artifacts are unsafe", validate_evidence_ledger(legacy)[0])

        stale_score = copy.deepcopy(noisy_portfolio)
        stale_score["opportunities"][0]["scores"]["high_impact"] += 1
        self.assertTrue(
            any("scores.high_impact must equal" in item for item in validate_portfolio(stale_score, noisy_ledger))
        )

        excluded = copy.deepcopy(noisy_portfolio)
        excluded["opportunities"][0]["evidence_refs"]["inventory_ids"] = [
            "INV-INVENTORY-R00003"
        ]
        self.assertTrue(
            any("cannot use excluded inventory" in item for item in validate_portfolio(excluded, noisy_ledger))
        )

        bad_value = copy.deepcopy(noisy_portfolio)
        bad_value["opportunities"][0]["value_case"]["annual_value"] = 72001.0
        self.assertTrue(
            any("annual_value must equal" in item for item in validate_portfolio(bad_value, noisy_ledger))
        )

        nonnumeric_value = copy.deepcopy(noisy_portfolio)
        nonnumeric_value["opportunities"][0]["value_case"]["inputs"][0]["value"] = "many"
        self.assertTrue(
            any("must be a finite number" in item for item in validate_portfolio(nonnumeric_value, noisy_ledger))
        )

        missing_value_ref = copy.deepcopy(noisy_portfolio)
        missing_value_ref["opportunities"][0]["evidence_refs"]["assumption_ids"].remove(
            "ASM-LOADED-RATE"
        )
        self.assertTrue(
            any(
                "evidence_ref must also appear in opportunity evidence_refs" in item
                for item in validate_portfolio(missing_value_ref, noisy_ledger)
            )
        )

        unvalidated_entitlement = copy.deepcopy(noisy_ledger)
        unvalidated_entitlement["assumptions"][2]["status"] = "unvalidated"
        self.assertTrue(
            any(
                "uses unvalidated entitlement assumption" in item
                for item in validate_evidence_ledger(unvalidated_entitlement)
            )
        )

        malformed_ledger = {"schema_version": "1.0", "customer": []}
        self.assertTrue(validate_portfolio(noisy_portfolio, malformed_ledger))

        malformed_refs = copy.deepcopy(noisy_portfolio)
        malformed_refs["opportunities"][0]["evidence_refs"]["inventory_ids"] = [{}]
        self.assertTrue(validate_portfolio(malformed_refs, noisy_ledger))

        on_prem_ledger, on_prem_portfolio, _expected = case_artifacts("on_prem")
        missing_constraint = copy.deepcopy(on_prem_portfolio)
        missing_constraint["opportunities"][0]["deployment"]["constraints_addressed"].pop()
        self.assertTrue(
            any(
                "must cover every ledger constraint" in item
                for item in validate_portfolio(missing_constraint, on_prem_ledger)
            )
        )

        overclaim = copy.deepcopy(on_prem_portfolio)
        overclaim["opportunities"][0]["capability_fit"][1]["claim"] = "confirmed_entitlement"
        self.assertTrue(
            any(
                "claims confirmed entitlement without confirmed ledger evidence" in item
                for item in validate_portfolio(overclaim, on_prem_ledger)
            )
        )

    def test_brief_cross_checks_reject_mutated_claims(self):
        case_dir = GOLDEN / "noisy"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _profile, profile_path = profile_case("noisy", root)
            valid_path = root / "brief.md"
            render = subprocess.run(
                [
                    sys.executable,
                    str(RENDERER),
                    "--evidence-ledger",
                    str(case_dir / "evidence_ledger.json"),
                    "--portfolio",
                    str(case_dir / "portfolio.json"),
                    "--inventory-profile",
                    str(profile_path),
                    "--output",
                    str(valid_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(render.returncode, 0, render.stderr)
            valid = valid_path.read_text(encoding="utf-8")
            variants = {
                "score": (
                    valid.replace(
                        "| 1 | Invoice exception resolution support | Validate Next | 76 |",
                        "| 1 | Invoice exception resolution support | Validate Next | 75 |",
                        1,
                    ),
                    "does not contain score 76",
                ),
                "inventory_id": (
                    valid.replace("INV-INVENTORY-R00002", "INV-REMOVED"),
                    "does not cite inventory ID INV-INVENTORY-R00002",
                ),
                "profile_name": (
                    valid.replace("Invoice Exception Triage", "Unnamed process"),
                    "does not contain profile/ledger inventory name",
                ),
                "source_date": (
                    valid.replace("2026-03-01", "2026-03-XX"),
                    "does not contain published_date 2026-03-01",
                ),
                "deployment": (
                    valid.replace("PII fields must be redacted", "Redaction requirement omitted"),
                    "omits deployment constraint",
                ),
                "value": (
                    valid.replace("72,000.00", "71,999.00"),
                    "does not contain calculated annual value",
                ),
                "entitlement": (
                    valid.replace(
                        "Action Center (likely fit; entitlement not confirmed)",
                        "Lakeview Finance Authority has Action Center",
                    ),
                    "overclaims unconfirmed entitlement",
                ),
            }
            for name, (markdown, expected) in variants.items():
                with self.subTest(claim=name):
                    mutated = root / f"brief.{name}.md"
                    mutated.write_text(markdown, encoding="utf-8")
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(BRIEF_VALIDATOR),
                            str(mutated),
                            "--min-recommendations",
                            "1",
                            "--min-pocs",
                            "1",
                            "--portfolio",
                            str(case_dir / "portfolio.json"),
                            "--evidence-ledger",
                            str(case_dir / "evidence_ledger.json"),
                            "--inventory-profile",
                            str(profile_path),
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 1)
                    self.assertIn(expected, result.stderr)

    def test_cli_rejects_partial_cross_check_and_stale_sources(self):
        case_dir = GOLDEN / "sparse"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile, profile_path = profile_case("sparse", root)
            markdown = root / "brief.md"
            render = subprocess.run(
                [
                    sys.executable,
                    str(RENDERER),
                    "--evidence-ledger",
                    str(case_dir / "evidence_ledger.json"),
                    "--portfolio",
                    str(case_dir / "portfolio.json"),
                    "--inventory-profile",
                    str(profile_path),
                    "--output",
                    str(markdown),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(render.returncode, 0, render.stderr)
            self.assertEqual(profile["schema_version"], "1.0")

            partial = subprocess.run(
                [
                    sys.executable,
                    str(BRIEF_VALIDATOR),
                    str(markdown),
                    "--portfolio",
                    str(case_dir / "portfolio.json"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(partial.returncode, 1)
            self.assertIn("must be supplied together", partial.stderr)

            stale = subprocess.run(
                [
                    sys.executable,
                    str(BRIEF_VALIDATOR),
                    str(markdown),
                    "--min-recommendations",
                    "1",
                    "--min-pocs",
                    "1",
                    "--portfolio",
                    str(case_dir / "portfolio.json"),
                    "--evidence-ledger",
                    str(case_dir / "evidence_ledger.json"),
                    "--inventory-profile",
                    str(profile_path),
                    "--max-source-age-days",
                    "30",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(stale.returncode, 1)
            self.assertIn("maximum is 30", stale.stderr)


if __name__ == "__main__":
    unittest.main()
