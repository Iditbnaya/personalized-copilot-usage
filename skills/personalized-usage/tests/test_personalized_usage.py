import argparse
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "personalized_usage",
    Path(__file__).resolve().parents[1] / "scripts" / "personalized_usage.py",
)
usage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usage)


def row(model="model-a", product="Copilot", unit="AI credits"):
    return {
        "product": product, "sku": "included", "model": model, "unitType": unit,
        "grossQuantity": 10, "discountQuantity": 7, "netQuantity": 3,
        "grossAmount": 1, "discountAmount": 0, "netAmount": 1,
    }


class FakeGitHub:
    def __init__(self, rows=None, user="alice", period=None, fail_source=None):
        self.rows = [] if rows is None else rows
        self.user = user
        self.period = period or {"year": 2026, "month": 10}
        self.fail_source = fail_source
        self.paths = []

    def get(self, path):
        self.paths.append(path)
        if path == "/user":
            return {"login": "alice"}
        if self.fail_source and self.fail_source in path:
            raise usage.UsageError("Forbidden.")
        return {"user": self.user, "timePeriod": self.period, "usageItems": self.rows}


class UsageTests(unittest.TestCase):
    def test_browser_reuse_precedes_sign_in_and_stops_login_loop(self):
        root = Path(__file__).resolve().parents[1]
        skill = (root / "SKILL.md").read_text(encoding="utf-8")
        reference = (root / "references" / "browser-session.md").read_text(encoding="utf-8")
        self.assertIn("references/browser-session.md", skill)
        self.assertIn('`action: "list"` first', reference)
        self.assertIn("read the SAME page/context again", reference)
        self.assertIn("stop the login loop", reference)
        self.assertIn("Do not export `storageState`", reference)
        self.assertIn("A host\nwith a built-in browser may ignore", reference)
        self.assertIn("Do not call `browser_close`", reference)

    def test_documented_browser_profile_is_persistent_not_isolated(self):
        import re
        reference = (Path(__file__).resolve().parents[1] /
                     "references" / "browser-session.md").read_text(encoding="utf-8")
        configs = re.findall(r"```json\n(.*?)\n```", reference, re.S)
        self.assertEqual(len(configs), 1)
        args = json.loads(configs[0])["mcpServers"]["playwright"]["args"]
        self.assertIn("--user-data-dir", args)
        self.assertNotIn("--isolated", args)
        self.assertNotIn("--storage-state", args)
        self.assertIn("YOUR_USER", args[args.index("--user-data-dir") + 1])

    def test_browser_guidance_defines_current_state_actions(self):
        root = Path(__file__).resolve().parents[1]
        skill = (root / "SKILL.md").read_text(encoding="utf-8")
        reference = (root / "references" / "browser-session.md").read_text(encoding="utf-8")
        rows = [line for line in reference.splitlines() if line.startswith("| `")]
        expected = {
            "signed_in": "Do not prompt for login",
            "authentication_required": "Prompt the user",
            "unknown": "Do not infer that the user is logged out",
            "account_mismatch": "Ask the user to confirm/select",
        }
        self.assertEqual(len(rows), len(expected))
        for state, action in expected.items():
            with self.subTest(state=state):
                row = next(line for line in rows if line.startswith(f"| `{state}`:"))
                self.assertIn(action, row)
        self.assertIn("This is NOT a once-per-conversation login restriction", reference)
        self.assertNotIn("do not repeat the login\nprompt if it is still signed out", skill)

    def test_browser_guidance_checks_saved_session_before_login_prompt(self):
        reference = (Path(__file__).resolve().parents[1] /
                     "references" / "browser-session.md").read_text(encoding="utf-8")
        self.assertIn("a new page is not\n   a new profile", reference)
        self.assertIn("BEFORE deciding whether to ask for login", reference)
        self.assertIn("Expired cookies may be", reference)
        self.assertIn("do not assert a profile mismatch as the only possible cause", reference)
        self.assertIn("Do not interrupt login/SSO", reference)

    def test_overview_totals_have_financial_source_guards(self):
        skill = (Path(__file__).resolve().parents[1] / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Total tokens (input + output, derived)", skill)
        self.assertIn("Total AI credits consumed", skill)
        self.assertIn("Usage cost (USD)", skill)
        self.assertIn("billing amount (currency unspecified)", skill)
        self.assertIn("partial recorded total", skill)
        self.assertIn("Do not total a truncated model table", skill)
        self.assertIn("Never add ai_credit and premium_request", skill)

    def test_local_activity_routes_before_browser(self):
        skill = (Path(__file__).resolve().parents[1] / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Do not block the local report on browser sign-in", skill)
        reference = (Path(__file__).resolve().parents[1] /
                     "references" / "local-activity.md").read_text(encoding="utf-8")
        self.assertIn('source: "local"', reference)
        self.assertIn("not cryptographically verified", reference)
        self.assertIn("never COALESCE", reference)

    def test_local_query_examples_preserve_nulls_units_and_dates(self):
        import re
        import sqlite3
        reference = (Path(__file__).resolve().parents[1] /
                     "references" / "local-activity.md").read_text(encoding="utf-8")
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        self.addCleanup(db.close)
        db.execute("""CREATE TABLE assistant_usage_events
            (session_id TEXT, model TEXT, created_at TEXT, input_tokens INTEGER,
             output_tokens INTEGER, cache_read_tokens INTEGER,
             cache_write_tokens INTEGER, reasoning_tokens INTEGER)""")
        db.executemany("INSERT INTO assistant_usage_events VALUES (?,?,?,?,?,?,?,?)", [
            ("s1", "a", "2026-10-01T01:00:00Z", 100, 20, 80, 10, 5),
            ("s1", "a", "2026-10-02 01:00:00", None, 30, None, None, None),
            ("s2", "b", "2026-10-02T02:00:00Z", 50, 10, 40, 0, 0),
            ("s3", "c", "2026-09-30T23:00:00Z", 999, 999, 0, 0, 0),
            ("s4", "d", "2026-11-01T00:00:00Z", 999, 999, 0, 0, 0),
        ])
        queries = re.findall(r"```sql\n(.*?)\n```", reference, re.S)
        self.assertEqual(len(queries), 4)
        results = [db.execute(q.replace("START_DATE", "2026-10-01").replace(
            "END_EXCLUSIVE", "2026-11-01")).fetchall() for q in queries]
        models = results[1]
        self.assertEqual([r["model"] for r in models], ["a", "b"])
        self.assertEqual(models[0]["recorded_api_events"], 2)
        self.assertEqual(models[0]["input_tokens"], 100)
        self.assertEqual(models[0]["input_samples"], 1)
        self.assertEqual(models[0]["output_tokens"], 50)
        self.assertEqual(models[0]["output_samples"], 2)
        self.assertEqual(models[1]["input_samples"], 1)
        self.assertEqual(models[1]["output_samples"], 1)
        self.assertEqual(models[1]["input_tokens"] + models[1]["output_tokens"], 60)
        self.assertEqual(len(results[2]), 2)
        self.assertEqual(len(results[3]), 2)
        empty = queries[1].replace("START_DATE", "2026-12-01").replace(
            "END_EXCLUSIVE", "2027-01-01")
        self.assertEqual(db.execute(empty).fetchall(), [])

    def test_personal_identity_only(self):
        client = FakeGitHub([row()])
        report = usage.fetch_usage(client, dt.date(2026, 10, 1), dt.date(2026, 10, 31))
        self.assertEqual(report["user"], "alice")
        self.assertEqual(len(client.paths), 3)
        self.assertTrue(all("/users/alice/" in path for path in client.paths[1:]))

    def test_other_identity_never_disclosed(self):
        report = usage.fetch_usage(
            FakeGitHub([row()], user="bob"),
            dt.date(2026, 10, 1), dt.date(2026, 10, 31),
        )
        for source in report["sources"]:
            self.assertEqual(source["status"], "unavailable")
            self.assertEqual(source["byModel"], [])

    def test_wrong_period_rejected(self):
        with self.assertRaises(usage.UsageError):
            usage.validate_report(
                {"user": "alice", "timePeriod": {"year": 2026, "month": 9},
                 "usageItems": [row()]},
                "alice", {"year": 2026, "month": 10},
            )

    def test_aggregation_preserves_units_products_models(self):
        totals = usage.aggregate([
            row(), row(), row("model-b"),
            row(unit="premium requests"), row(product="Other"),
        ], True)
        self.assertEqual(len(totals), 4)
        model_a = next(item for item in totals if
                       item["product"] == "Copilot" and
                       item["unitType"] == "AI credits" and item["model"] == "model-a")
        self.assertEqual(model_a["grossQuantity"], 20)
        self.assertEqual(model_a["netQuantity"], 6)
        self.assertEqual(model_a["netAmount"], 2)

    def test_decimal_precision(self):
        item = usage.parse_json(json.dumps(row()).replace('"grossAmount": 1', '"grossAmount": 0.1'))
        total = usage.aggregate([item, item, item], False)[0]["grossAmount"]
        self.assertEqual(str(total), "0.3")

    def test_no_fake_tokens_limits_or_remaining(self):
        report = usage.fetch_usage(
            FakeGitHub([row()]), dt.date(2026, 10, 1), dt.date(2026, 10, 31)
        )
        self.assertNotIn("remaining", report)
        self.assertNotIn("totalTokens", report)
        self.assertIn("allocated quotas and remaining balances",
                      report["unavailableFromTheseAPIs"])

    def test_empty_is_not_zero_total_usage(self):
        report = usage.fetch_usage(
            FakeGitHub(), dt.date(2026, 10, 1), dt.date(2026, 10, 31)
        )
        self.assertEqual(report["sources"][0]["status"], "no_personal_billing_rows")
        self.assertEqual(report["sources"][0]["totalsByProductAndUnit"], [])
        self.assertIn("do not establish zero", report["coverageWarning"])

    def test_failed_source_does_not_hide_successful_source(self):
        report = usage.fetch_usage(
            FakeGitHub([row()], fail_source="premium_request"),
            dt.date(2026, 10, 1), dt.date(2026, 10, 31),
        )
        self.assertEqual(report["sources"][0]["status"], "ok")
        self.assertEqual(report["sources"][1]["status"], "unavailable")

    def test_non_copilot_products_excluded(self):
        report = usage.fetch_usage(
            FakeGitHub([row(product="Actions")]),
            dt.date(2026, 10, 1), dt.date(2026, 10, 31),
        )
        self.assertEqual(report["sources"][0]["byModel"], [])
        self.assertEqual(report["sources"][0]["excludedNonCopilotRows"], 1)

    def test_malformed_quantities_fail_explicitly(self):
        for value in (None, True, "10"):
            item = row()
            item["grossQuantity"] = value
            with self.assertRaises(usage.UsageError):
                usage.validate_report(
                    {"user": "alice", "timePeriod": {"year": 2026, "month": 10},
                     "usageItems": [item]}, "alice", {"year": 2026, "month": 10},
                )

    def test_ranges_and_leap_year(self):
        self.assertEqual(
            usage.filters(dt.date(2024, 2, 1), dt.date(2024, 3, 2)),
            [{"year": 2024, "month": 2}, {"year": 2024, "month": 3, "day": 1},
             {"year": 2024, "month": 3, "day": 2}],
        )
        args = argparse.Namespace(period="last-7-days", start=None, end=None)
        self.assertEqual(
            usage.dates(args, dt.date(2026, 10, 4)),
            (dt.date(2026, 9, 28), dt.date(2026, 10, 4)),
        )

    def test_bad_custom_ranges(self):
        for start, end in (("2026-10-04", "2026-10-01"),
                           ("2026-01-01", "2026-10-01"),
                           ("2026-10-05", "2026-10-06"), ("bad", "bad")):
            args = argparse.Namespace(period="custom", start=start, end=end)
            with self.assertRaises(usage.UsageError):
                usage.dates(args, dt.date(2026, 10, 4))

    def test_no_cli_required_with_environment_token(self):
        with patch.dict(os.environ, {"GH_TOKEN": "test-token"}, clear=True):
            with patch.object(usage.shutil, "which", return_value=None):
                client = usage.GitHub()
        self.assertEqual(client.token, "test-token")
        self.assertIsNone(client.gh)

    def test_missing_auth_actionable_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(usage.shutil, "which", return_value=None):
                with self.assertRaisesRegex(usage.UsageError, "Copilot CLI is not required"):
                    usage.GitHub()

    def test_redirect_refused(self):
        with self.assertRaises(usage.UsageError):
            usage.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other")

    def test_managed_users_default_to_self_service_not_billing(self):
        skill = (
            Path(__file__).resolve().parents[1] / "SKILL.md"
        ).read_text(encoding="utf-8")
        default = skill.split("## Default: non-admin self-service usage", 1)[1].split(
            "## Optional: personally purchased plan billing details", 1
        )[0]
        self.assertIn("https://github.com/settings/copilot", default)
        self.assertIn("Do NOT run the billing script first", default)
        self.assertNotIn("https://github.com/settings/billing", default)
        self.assertIn("do not invent month boundaries", default)

    def test_missing_auth_never_sends_user_to_billing_settings(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(usage.shutil, "which", return_value=None):
                with self.assertRaises(usage.UsageError) as raised:
                    usage.GitHub()
        self.assertIn("https://github.com/settings/copilot", str(raised.exception))
        self.assertNotIn("/settings/billing", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
