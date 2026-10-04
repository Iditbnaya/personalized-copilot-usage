import copy
from decimal import Decimal
import importlib.util
from pathlib import Path
import sqlite3
import unittest


spec = importlib.util.spec_from_file_location(
    "estimate_tokens", Path(__file__).resolve().parents[1] / "scripts" / "estimate_tokens.py"
)
pricing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pricing)


def config():
    return {
        "pricing_source": pricing.PRICING_SOURCE,
        "pricing_checked_at": "2026-10-04",
        "captured_at": "2026-10-04T13:00:00Z",
        "start": "2026-10-01", "end_exclusive": "2026-10-05",
        "input_semantics": "includes_cache", "usd_per_ai_credit": "0.01",
        "rates": {"demo-model": [
            {"up_to_input_tokens": 100, "input": "2", "output": "10",
             "cached_input": "0.2", "cache_write": "2.5"},
            {"up_to_input_tokens": None, "input": "4", "output": "15",
             "cached_input": "0.4", "cache_write": "5"},
        ]},
        "rows": [{
            "model": "demo-model", "records": 2, "valid_records": 2,
            "input_tokens": 200, "output_tokens": 30,
            "cache_read_tokens": 100, "cache_write_tokens": 40,
            "min_context_tokens": 100, "max_context_tokens": 100,
        }],
    }


class TokenEstimateTests(unittest.TestCase):
    def test_cached_categories_not_double_counted(self):
        result = pricing.estimate(config())
        self.assertEqual(result["estimated_usd"], Decimal("0.00054"))
        self.assertEqual(result["estimated_credit_equivalent"], Decimal("0.054"))
        self.assertEqual(result["status"], "estimated")
        self.assertIn("Not actual billed", result["billing_warning"])

    def test_accumulated_input_does_not_choose_long_context(self):
        data = config()
        self.assertGreater(data["rows"][0]["input_tokens"], 100)
        self.assertEqual(pricing.estimate(data)["estimated_usd"], Decimal("0.00054"))

    def test_long_context_boundary_is_per_record_and_exclusive(self):
        data = config()
        data["rows"][0].update(records=1, valid_records=1, input_tokens=101,
                               output_tokens=0, cache_read_tokens=0, cache_write_tokens=0,
                               min_context_tokens=101, max_context_tokens=101)
        self.assertEqual(pricing.estimate(data)["estimated_usd"], Decimal("0.000404"))

    def test_excludes_cache_semantics(self):
        data = config()
        data["input_semantics"] = "excludes_cache"
        data["rows"][0]["input_tokens"] = 60
        self.assertEqual(pricing.estimate(data)["estimated_usd"], Decimal("0.00054"))

    def test_unknown_model_keeps_partial_total_explicit(self):
        data = config()
        row = copy.deepcopy(data["rows"][0])
        row["model"] = "unknown-model"
        data["rows"].append(row)
        result = pricing.estimate(data)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["records"], 4)
        self.assertEqual(result["priced_records"], 2)
        self.assertEqual(result["estimated_usd"], Decimal("0.00054"))
        self.assertIsNone(result["by_model"][1]["estimated_usd"])

    def test_unknown_only_is_unavailable_not_zero(self):
        data = config()
        data["rows"][0]["model"] = "auto"
        result = pricing.estimate(data)
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["estimated_usd"])

    def test_empty_history_is_not_zero_billing(self):
        data = config()
        data["rows"] = []
        result = pricing.estimate(data)
        self.assertEqual(result["status"], "no_local_records")
        self.assertIsNone(result["estimated_usd"])

    def test_zero_recorded_tokens_have_zero_estimate(self):
        data = config()
        data["rows"][0].update(input_tokens=0, output_tokens=0, cache_read_tokens=0,
                               cache_write_tokens=0, min_context_tokens=0, max_context_tokens=0)
        self.assertEqual(pricing.estimate(data)["estimated_usd"], Decimal(0))

    def test_bad_or_missing_token_groups_are_excluded(self):
        for patch in (
            {"valid_records": 1}, {"output_tokens": None}, {"input_tokens": -1},
            {"cache_read_tokens": True}, {"cache_write_tokens": "NaN"},
            {"min_context_tokens": 90, "max_context_tokens": 110},
            {"cache_read_tokens": 201}, {"min_context_tokens": 101},
        ):
            with self.subTest(patch=patch):
                data = config()
                data["rows"][0].update(patch)
                result = pricing.estimate(data)
                self.assertEqual(result["status"], "unavailable")
                self.assertTrue(result["by_model"][0]["exclusions"])

    def test_unavailable_cache_rate_cannot_price_positive_cache_tokens(self):
        data = config()
        data["rates"]["demo-model"][0]["cache_write"] = None
        self.assertEqual(pricing.estimate(data)["status"], "unavailable")
        data["rows"][0]["cache_write_tokens"] = 0
        self.assertEqual(pricing.estimate(data)["status"], "estimated")

    def test_rates_and_source_require_explicit_valid_inputs(self):
        for key, value in (
            ("pricing_source", "https://example.com"), ("input_semantics", "guess"),
            ("usd_per_ai_credit", 0), ("usd_per_ai_credit", "NaN"),
            ("start", "20261001"), ("end_exclusive", "2026-09-30"),
            ("captured_at", "2026-10-04T13:00:00"), ("pricing_checked_at", "unknown"),
        ):
            with self.subTest(key=key):
                data = config()
                data[key] = value
                with self.assertRaises(pricing.EstimateError):
                    pricing.estimate(data)

    def test_invalid_tier_definition_is_a_hard_error(self):
        for tiers in (
            [{"up_to_input_tokens": None}],
            config()["rates"]["demo-model"][:-1],
            list(reversed(config()["rates"]["demo-model"])),
        ):
            data = config()
            data["rates"]["demo-model"] = tiers
            with self.assertRaises(pricing.EstimateError):
                pricing.estimate(data)

    def test_possible_query_truncation_is_a_hard_error(self):
        data = config()
        data["rows"] *= 501
        with self.assertRaisesRegex(pricing.EstimateError, "truncated"):
            pricing.estimate(data)

    def test_generated_sql_respects_dates_capture_tiers_and_invalid_rows(self):
        data = config()
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.row_factory = sqlite3.Row
        db.execute("""CREATE TABLE assistant_usage_events
            (model TEXT, input_tokens INTEGER, output_tokens INTEGER,
             cache_read_tokens INTEGER, cache_write_tokens INTEGER, created_at TEXT)""")
        db.executemany("INSERT INTO assistant_usage_events VALUES (?,?,?,?,?,?)", [
            ("demo-model", 100, 15, 50, 20, "2026-10-01T01:00:00Z"),
            ("demo-model", 100, 15, 50, 20, "2026-10-02 01:00:00"),
            ("demo-model", 101, 0, 0, 0, "2026-10-03T01:00:00Z"),
            ("demo-model", 100, None, 0, 0, "2026-10-03T02:00:00Z"),
            ("demo-model", 100, 1, 200, 0, "2026-10-03T03:00:00Z"),
            ("demo-model", 100, -1, 0, 0, "2026-10-03T04:00:00Z"),
            ("demo-model", 100, 999, 0, 0, "2026-09-30T23:00:00Z"),
            ("demo-model", 100, 999, 0, 0, "2026-10-05T00:00:00Z"),
            ("demo-model", 100, 999, 0, 0, "2026-10-04T13:00:01Z"),
        ])
        data["rows"] = [dict(row) for row in db.execute(pricing.make_query(data))]
        result = pricing.estimate(data)
        self.assertEqual(result["records"], 6)
        self.assertEqual(result["priced_records"], 3)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["estimated_usd"], Decimal("0.000944"))


if __name__ == "__main__":
    unittest.main()
