import argparse
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "du_estimate.py"
FIXTURES = ROOT / "tests" / "fixtures"
INPUT_FIXTURE = FIXTURES / "multi-document-input.v1.json"
RATE_FIXTURE = FIXTURES / "rate-profile.v1.json"
STALE_RATE_FIXTURE = FIXTURES / "stale-rate-profile.v1.json"
EXPECTED_FIXTURE = FIXTURES / "expected-output.v1.json"


def load_module():
    spec = importlib.util.spec_from_file_location("du_estimate", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
    )


class DuEstimateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def run_with_payloads(self, *extra_args, input_payload=None, rate_payload=None):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "input.json"
            rate_path = temp_path / "rates.json"
            input_path.write_text(
                json.dumps(input_payload or load_json(INPUT_FIXTURE)),
                encoding="utf-8",
            )
            rate_path.write_text(
                json.dumps(rate_payload or load_json(RATE_FIXTURE)),
                encoding="utf-8",
            )
            return run_cli(
                "--input",
                input_path,
                "--rate-profile",
                rate_path,
                *extra_args,
            )

    def test_versioned_schemas_and_fixtures_are_valid_json(self):
        schema_expectations = {
            "rate-profile.v1.schema.json": self.module.RATE_PROFILE_VERSION,
            "input.v1.schema.json": self.module.INPUT_VERSION,
            "output.v1.schema.json": self.module.OUTPUT_VERSION,
        }
        for filename, version in schema_expectations.items():
            with self.subTest(filename=filename):
                schema = load_json(ROOT / "references" / filename)
                self.assertEqual(schema["properties"]["schema_version"]["const"], version)

        for fixture in FIXTURES.glob("*.json"):
            with self.subTest(fixture=fixture.name):
                self.assertIsInstance(load_json(fixture), dict)

    def test_parse_case_preserves_comma_formatted_legacy_values(self):
        label, transactions, pages = self.module.parse_case("base=1,234,2")

        self.assertEqual(label, "base")
        self.assertEqual(transactions, Decimal("1234"))
        self.assertEqual(pages, Decimal("2"))

    def test_parse_case_rejects_malformed_negative_or_empty_values(self):
        for value in ("base", "=100,1", "bad=-1,2", "bad=1,-2", "bad=1,2,3"):
            with self.subTest(value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    self.module.parse_case(value)

    def test_structured_json_matches_expected_multi_document_output(self):
        result = run_cli(
            "--input",
            INPUT_FIXTURE,
            "--rate-profile",
            RATE_FIXTURE,
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload, load_json(EXPECTED_FIXTURE))
        self.assertEqual(payload["rate_context"]["totals_per_page"]["ai_unit"], "1.125")
        self.assertEqual(payload["scenarios"][0]["totals"]["annual_pages"], "3500")
        self.assertEqual(
            payload["scenarios"][0]["totals"]["units"]["ai_unit"],
            {"exact": "3937.5", "rounded": "3938"},
        )

    def test_markdown_reports_documents_aggregate_totals_and_rate_provenance(self):
        result = run_cli(
            "--input",
            INPUT_FIXTURE,
            "--rate-profile",
            RATE_FIXTURE,
            "--format",
            "markdown",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("- Applicability: **conditional**", result.stdout)
        self.assertIn("| synthetic-ai-add-on | AI Units | 0.125 |", result.stdout)
        self.assertIn("| low | claims | 500 | 3 | 1,500 | 1,687.5 | 1,688 |", result.stdout)
        self.assertIn("## Aggregate Scenario Totals", result.stdout)
        self.assertIn("| base | 5,100 | 5,737.5 | 5,738 | 1,275 | 1,275 |", result.stdout)

    def test_cli_has_no_silent_rate_defaults(self):
        result = run_cli(
            "--case",
            "base=100,2",
            "--applicability",
            "yes",
            "--rationale",
            "Pages are processed by DU.",
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("no rates supplied", result.stderr)
        self.assertIn("--rate-profile PROFILE.json", result.stderr)
        self.assertIn("--verified-on YYYY-MM-DD", result.stderr)

    def test_explicit_rates_require_verification_date(self):
        result = run_cli(
            "--case",
            "base=100,2",
            "--ai-rate",
            "1",
            "--applicability",
            "yes",
            "--rationale",
            "Pages are processed by DU.",
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("explicit rates require --verified-on", result.stderr)

    def test_legacy_case_rejects_rate_profiles_and_missing_rationale(self):
        profile_result = run_cli(
            "--case",
            "base=100,2",
            "--rate-profile",
            RATE_FIXTURE,
            "--applicability",
            "yes",
            "--rationale",
            "Pages are processed by DU.",
        )
        rationale_result = run_cli(
            "--case",
            "base=100,2",
            "--ai-rate",
            "1",
            "--verified-on",
            "2026-07-10",
            "--as-of",
            "2026-07-10",
        )

        self.assertEqual(profile_result.returncode, 2)
        self.assertIn("legacy --case accepts only explicit verified rates", profile_result.stderr)
        self.assertEqual(rationale_result.returncode, 2)
        self.assertIn("requires --applicability", rationale_result.stderr)

    def test_legacy_explicit_rates_support_additive_exact_results(self):
        result = run_cli(
            "--case",
            "mixed=100.5,1.5",
            "--ai-rate",
            "0.5",
            "--extra-ai-rate",
            "0.25",
            "--platform-rate",
            "0.25",
            "--verified-on",
            "2026-07-10",
            "--as-of",
            "2026-07-10",
            "--applicability",
            "yes",
            "--rationale",
            "Every page is processed by DU.",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["input_mode"], "legacy_case")
        self.assertEqual(payload["rate_context"]["totals_per_page"]["ai_unit"], "0.75")
        units = payload["scenarios"][0]["totals"]["units"]
        self.assertEqual(units["ai_unit"], {"exact": "113.0625", "rounded": "113"})
        self.assertEqual(units["platform_unit"], {"exact": "37.6875", "rounded": "38"})

    def test_exact_arithmetic_is_not_limited_by_default_decimal_precision(self):
        transactions = "123456789012345678901234567890"
        result = run_cli(
            "--case",
            f"base={transactions},1",
            "--ai-rate",
            "1",
            "--verified-on",
            "2026-07-10",
            "--as-of",
            "2026-07-10",
            "--applicability",
            "yes",
            "--rationale",
            "Pages are processed by DU.",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        total = json.loads(result.stdout)["scenarios"][0]["totals"]["units"]["ai_unit"]
        self.assertEqual(total, {"exact": transactions, "rounded": transactions})
        self.assertEqual(
            self.module.markdown_number(transactions),
            "123,456,789,012,345,678,901,234,567,890",
        )

    def test_structured_input_accepts_explicit_verified_additive_rates(self):
        result = run_cli(
            "--input",
            INPUT_FIXTURE,
            "--ai-rate",
            "0.5",
            "--extra-ai-rate",
            "0.25",
            "--verified-on",
            "2026-07-01",
            "--max-rate-age-days",
            "30",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["rate_context"]["mode"], "explicit_cli")
        self.assertEqual(payload["rate_context"]["totals_per_page"], {"ai_unit": "0.75"})
        self.assertEqual(
            payload["scenarios"][0]["totals"]["units"]["ai_unit"],
            {"exact": "2625", "rounded": "2625"},
        )

    def test_profile_and_explicit_rate_modes_are_mutually_exclusive(self):
        result = run_cli(
            "--input",
            INPUT_FIXTURE,
            "--rate-profile",
            RATE_FIXTURE,
            "--ai-rate",
            "1",
            "--verified-on",
            "2026-07-10",
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("choose --rate-profile or explicit rates", result.stderr)

    def test_stale_profile_is_rejected_without_override(self):
        result = run_cli(
            "--input",
            INPUT_FIXTURE,
            "--rate-profile",
            STALE_RATE_FIXTURE,
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("stale rate component(s)", result.stderr)
        self.assertIn("--allow-stale-rates", result.stderr)

    def test_stale_profile_override_is_visible_in_json(self):
        result = run_cli(
            "--input",
            INPUT_FIXTURE,
            "--rate-profile",
            STALE_RATE_FIXTURE,
            "--allow-stale-rates",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["rate_context"]["stale_override_used"])
        self.assertTrue(payload["rate_context"]["components"][0]["is_stale"])
        self.assertIn("Stale-rate override used", payload["warnings"][0])

    def test_explicit_rates_use_a_staleness_gate_and_support_override(self):
        args = (
            "--case",
            "base=100,2",
            "--ai-rate",
            "1",
            "--verified-on",
            "2026-05-01",
            "--as-of",
            "2026-07-10",
            "--applicability",
            "yes",
            "--rationale",
            "Pages are processed by DU.",
            "--format",
            "json",
        )
        rejected = run_cli(*args)
        overridden = run_cli(*args, "--allow-stale-rates")

        self.assertEqual(rejected.returncode, 2)
        self.assertIn("stale rate component(s)", rejected.stderr)
        self.assertEqual(overridden.returncode, 0, overridden.stderr)
        self.assertTrue(json.loads(overridden.stdout)["rate_context"]["stale_override_used"])

    def test_rate_profile_contract_rejects_unsafe_variants(self):
        base = load_json(RATE_FIXTURE)
        variants = []

        wrong_version = copy.deepcopy(base)
        wrong_version["schema_version"] = "estimate-du-units.rate-profile.v0"
        variants.append(("wrong version", wrong_version, "schema_version"))

        missing_max_age = copy.deepcopy(base)
        missing_max_age["rates"][0].pop("max_age_days")
        variants.append(("missing max age", missing_max_age, "max_age_days"))

        bad_unit = copy.deepcopy(base)
        bad_unit["rates"][0]["unit"] = "credits"
        variants.append(("bad unit", bad_unit, "must be ai_unit or platform_unit"))

        bad_url = copy.deepcopy(base)
        bad_url["rates"][0]["source_url"] = "local-file"
        variants.append(("bad URL", bad_url, "absolute HTTP(S) URL"))

        bad_rate = copy.deepcopy(base)
        bad_rate["rates"][0]["rate"] = "01"
        variants.append(("noncanonical rate", bad_rate, "decimal string"))

        duplicate_name = copy.deepcopy(base)
        duplicate_name["rates"][1]["name"] = duplicate_name["rates"][0]["name"]
        variants.append(("duplicate name", duplicate_name, "duplicate name"))

        unknown_field = copy.deepcopy(base)
        unknown_field["rates"][0]["currency"] = "USD"
        variants.append(("unknown field", unknown_field, "unsupported field"))

        for name, profile, error in variants:
            with self.subTest(name=name):
                result = self.run_with_payloads(
                    "--format",
                    "json",
                    rate_payload=profile,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn(error, result.stderr)

    def test_future_accessed_or_effective_rates_are_rejected(self):
        for field in ("accessed_on", "effective_on"):
            profile = load_json(RATE_FIXTURE)
            profile["rates"][0][field] = "2026-07-11"
            with self.subTest(field=field):
                result = self.run_with_payloads(rate_payload=profile)
                self.assertEqual(result.returncode, 2)
                self.assertIn(
                    "accessed after" if field == "accessed_on" else "not effective",
                    result.stderr,
                )

    def test_rate_age_boundary_is_current(self):
        profile = load_json(STALE_RATE_FIXTURE)
        profile["rates"][0]["max_age_days"] = 70
        result = self.run_with_payloads(
            "--format",
            "json",
            rate_payload=profile,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        component = json.loads(result.stdout)["rate_context"]["components"][0]
        self.assertEqual(component["age_days"], 70)
        self.assertFalse(component["is_stale"])

    def test_structured_input_contract_rejects_unsafe_variants(self):
        base = load_json(INPUT_FIXTURE)
        variants = []

        missing_rationale = copy.deepcopy(base)
        missing_rationale["applicability"].pop("rationale")
        variants.append(("missing rationale", missing_rationale, "rationale"))

        bad_status = copy.deepcopy(base)
        bad_status["applicability"]["status"] = "unclear"
        variants.append(("bad status", bad_status, "yes, no, or conditional"))

        non_string_status = copy.deepcopy(base)
        non_string_status["applicability"]["status"] = []
        variants.append(("non-string status", non_string_status, "yes, no, or conditional"))

        negative_volume = copy.deepcopy(base)
        negative_volume["scenarios"][0]["documents"][0]["annual_transactions"] = "-1"
        variants.append(("negative volume", negative_volume, "decimal string"))

        numeric_pages = copy.deepcopy(base)
        numeric_pages["scenarios"][0]["documents"][0]["pages_per_transaction"] = 2
        variants.append(("numeric pages", numeric_pages, "decimal string"))

        duplicate_scenario = copy.deepcopy(base)
        duplicate_scenario["scenarios"][1]["name"] = duplicate_scenario["scenarios"][0]["name"]
        variants.append(("duplicate scenario", duplicate_scenario, "duplicate name"))

        duplicate_document = copy.deepcopy(base)
        duplicate_document["scenarios"][0]["documents"][1]["name"] = "invoices"
        variants.append(("duplicate document", duplicate_document, "duplicate name"))

        unknown_field = copy.deepcopy(base)
        unknown_field["customer"] = "example"
        variants.append(("unknown field", unknown_field, "unsupported field"))

        for name, payload, error in variants:
            with self.subTest(name=name):
                with self.assertRaisesRegex(self.module.ContractError, error):
                    self.module.parse_input_contract(payload)

    def test_no_applicability_forces_zero_units_but_preserves_page_totals(self):
        payload = load_json(INPUT_FIXTURE)
        payload["applicability"] = {
            "status": "no",
            "rationale": "The automation uses existing metadata and does not send pages to DU.",
        }
        result = self.run_with_payloads("--format", "json", input_payload=payload)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output["calculation_applied"])
        self.assertEqual(output["scenarios"][0]["totals"]["annual_pages"], "3500")
        self.assertEqual(
            output["scenarios"][0]["totals"]["units"]["ai_unit"],
            {"exact": "0", "rounded": "0"},
        )
        self.assertIn("forced to zero", output["warnings"][0])

    def test_add_on_rates_require_a_base_rate_and_negative_rates_fail(self):
        missing_base = run_cli(
            "--case",
            "base=100,2",
            "--extra-ai-rate",
            "0.1",
            "--verified-on",
            "2026-07-10",
            "--as-of",
            "2026-07-10",
            "--applicability",
            "yes",
            "--rationale",
            "Pages are processed by DU.",
        )
        negative = run_cli(
            "--case",
            "base=100,2",
            "--ai-rate",
            "-1",
            "--verified-on",
            "2026-07-10",
            "--applicability",
            "yes",
            "--rationale",
            "Pages are processed by DU.",
        )

        self.assertEqual(missing_base.returncode, 2)
        self.assertIn("--extra-ai-rate requires an explicit --ai-rate", missing_base.stderr)
        self.assertEqual(negative.returncode, 2)
        self.assertIn("value cannot be negative", negative.stderr)

    def test_invalid_json_is_reported_without_traceback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_input = Path(temp_dir) / "invalid.json"
            invalid_input.write_text("{not json", encoding="utf-8")
            result = run_cli(
                "--input",
                invalid_input,
                "--rate-profile",
                RATE_FIXTURE,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid JSON", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_duplicate_json_keys_and_nonstandard_constants_are_rejected(self):
        invalid_documents = {
            "duplicate": (
                '{"schema_version":"estimate-du-units.input.v1",'
                '"schema_version":"estimate-du-units.input.v1"}',
                "duplicate object key",
            ),
            "constant": (
                '{"schema_version":"estimate-du-units.input.v1","estimate_id":NaN}',
                "unsupported numeric constant",
            ),
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            for name, (raw_json, error) in invalid_documents.items():
                with self.subTest(name=name):
                    invalid_input = Path(temp_dir) / f"{name}.json"
                    invalid_input.write_text(raw_json, encoding="utf-8")
                    result = run_cli(
                        "--input",
                        invalid_input,
                        "--rate-profile",
                        RATE_FIXTURE,
                    )
                    self.assertEqual(result.returncode, 2)
                    self.assertIn(error, result.stderr)
                    self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
