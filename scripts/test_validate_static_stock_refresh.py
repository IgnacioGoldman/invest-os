from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from validate_static_stock_refresh import SUPPORT_KEYS, _validate_fcf_margin, _write_summary, validate_refresh


def stock(ticker: str, market_date: str = "2026-09-22") -> dict:
    return {
        "ticker": ticker,
        "price_opportunity": {
            "current_price": {"value": 100.0, "as_of": market_date},
            **{key: {"value": 2.0, "as_of": market_date} for key in SUPPORT_KEYS},
        },
    }


class StaticStockRefreshValidatorTests(unittest.TestCase):
    def test_financial_fcf_margin_can_be_explicitly_not_meaningful(self) -> None:
        row = {"business_health": {"fcf_margin": {"value": None, "notes": "FCF margin is not meaningful for this financial business."}},
               "metrics": {"revenue_ttm": {"value": 100}, "free_cash_flow_ttm": {"value": 20}}}
        errors = []
        _validate_fcf_margin("BANK", row, errors)
        self.assertEqual(errors, [])

    def test_missing_or_incorrect_comparable_fcf_margin_still_fails(self) -> None:
        for metric in ({"value": None, "notes": "Missing input"}, {"value": 999}):
            with self.subTest(metric=metric):
                row = {"business_health": {"fcf_margin": metric},
                       "metrics": {"revenue_ttm": {"value": 100}, "free_cash_flow_ttm": {"value": 20}}}
                errors = []
                _validate_fcf_margin("TEST", row, errors)
                self.assertEqual(len(errors), 1)

    def test_unverified_retention_is_visible_without_changing_deployment_validation(self) -> None:
        with TemporaryDirectory() as directory:
            history_dir = Path(directory)
            (history_dir / "AAA.json").write_text(json.dumps([{"date":"2026-09-22","close":100}]))
            result = validate_refresh({"results":[{"ticker":"AAA","saved_to":"db","refresh_status":"retained_unverified",
                "sec_check_status":"unavailable","source_notes":["SEC unavailable; retained saved data."],
                "latest_fundamental_as_of":"2026-06-30"}]},{"tickers":["AAA"]},[stock("AAA")],history_dir)
            self.assertTrue(result["valid"],result["errors"])
            summary_path = history_dir / "summary.md"
            _write_summary(summary_path,result)
            summary = summary_path.read_text()
            self.assertIn("Retained without source verification: **1**",summary)
            self.assertIn("**1 unavailable**",summary)
            self.assertIn("SEC unavailable",summary)
            self.assertIn("| AAA | 2026-09-22 | 2026-06-30 |",summary)
            self.assertEqual(result["market_as_of"],"2026-09-22")

    def setUp(self) -> None:
        # Fixture dates describe a fixed refresh, independently of today's date.
        clock = patch("validate_static_stock_refresh.datetime")
        self.clock = clock.start()
        self.clock.now.return_value = datetime(2026, 9, 23, tzinfo=timezone.utc)
        self.addCleanup(clock.stop)

    def validate_market_rows(self, rows: list[dict]) -> dict:
        with TemporaryDirectory() as directory:
            history_dir = Path(directory)
            for row in rows:
                (history_dir / f"{row['ticker']}.json").write_text(json.dumps([
                    {"date": row["price_opportunity"]["current_price"]["as_of"], "close": 100.0},
                ]))
            return validate_refresh(
                {"results": [{"ticker": row["ticker"], "saved_to": "data/invest_os.sqlite"} for row in rows]},
                {"tickers": [row["ticker"] for row in rows]}, rows, history_dir,
            )

    def test_morning_us_and_stockholm_session_dates_pass(self) -> None:
        result = self.validate_market_rows([
            {**stock("AAA", "2026-09-22"), "exchange": "NYSE"},
            {**stock("NIBE-B.ST", "2026-09-23"), "exchange": "Stockholm"},
        ])
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["market_date_counts"], {"2026-09-22": 1, "2026-09-23": 1})

    def test_friday_and_monday_market_sessions_pass(self) -> None:
        self.clock.now.return_value = datetime(2026, 9, 28, tzinfo=timezone.utc)
        result = self.validate_market_rows([
            {**stock("AAA", "2026-09-25"), "exchange": "Nasdaq"},
            {**stock("AXFO.ST", "2026-09-28"), "exchange": "Nasdaq Stockholm"},
        ])
        self.assertTrue(result["valid"], result["errors"])

    def test_inconsistent_dates_within_one_market_still_fail(self) -> None:
        result = self.validate_market_rows([
            {**stock("AAA", "2026-09-22"), "exchange": "NYSE"},
            {**stock("BBB", "2026-09-23"), "exchange": "Nasdaq"},
            {**stock("AXFO.ST", "2026-09-23"), "exchange": "Nasdaq Stockholm"},
        ])
        self.assertFalse(result["valid"])
        self.assertTrue(any("Market dates are inconsistent" in error for error in result["errors"]))

    def test_more_than_one_weekday_of_market_lag_still_fails(self) -> None:
        result = self.validate_market_rows([
            {**stock("AAA", "2026-09-21"), "exchange": "NYSE"},
            {**stock("AXFO.ST", "2026-09-23"), "exchange": "Stockholm"},
        ])
        self.assertFalse(result["valid"])

    def test_unknown_market_does_not_allow_mixed_dates(self) -> None:
        result = self.validate_market_rows([
            stock("AAA", "2026-09-22"),
            {**stock("AXFO.ST", "2026-09-23"), "exchange": "Stockholm"},
        ])
        self.assertFalse(result["valid"])

    def test_future_or_stale_minority_market_dates_still_fail(self) -> None:
        for older, newer, message in [
            ("2026-09-23", "2026-09-24", "in the future"),
            ("2026-09-14", "2026-09-15", "days old"),
        ]:
            result = self.validate_market_rows([
                {**stock("AAA", older), "exchange": "NYSE"},
                {**stock("BBB", older), "exchange": "Nasdaq"},
                {**stock("AXFO.ST", newer), "exchange": "Stockholm"},
            ])
            self.assertFalse(result["valid"])
            self.assertTrue(any(message in error for error in result["errors"]))

    def test_complete_coherent_export_passes(self) -> None:
        with TemporaryDirectory() as directory:
            history_dir = Path(directory)
            for ticker in ("AAA", "BBB"):
                (history_dir / f"{ticker}.json").write_text(
                    json.dumps([{"date": "2026-09-22", "close": 100.0}]),
                    encoding="utf-8",
                )
            report = {
                "failed_count": 0,
                "skipped_low_fidelity_count": 0,
                "results": [
                    {"ticker": "AAA", "saved_to": "data/invest_os.sqlite"},
                    {"ticker": "BBB", "saved_to": "data/invest_os.sqlite"},
                ],
            }
            result = validate_refresh(
                report,
                {"tickers": ["AAA", "BBB"]},
                [stock("AAA"), stock("BBB")],
                history_dir,
            )
            self.assertTrue(result["valid"], result["errors"])
            self.assertEqual(result["market_as_of"], "2026-09-22")

    def test_missing_and_inconsistent_rows_fail(self) -> None:
        with TemporaryDirectory() as directory:
            history_dir = Path(directory)
            (history_dir / "AAA.json").write_text(
                json.dumps([{"date": "2026-09-21", "close": 100.0}]),
                encoding="utf-8",
            )
            result = validate_refresh(
                {
                    "failed_count": 1,
                    "skipped_low_fidelity_count": 0,
                    "results": [{"ticker": "AAA", "saved_to": None}],
                },
                {"tickers": ["AAA", "BBB"]},
                [stock("AAA", "2026-09-22")],
                history_dir,
            )
            self.assertFalse(result["valid"])
            self.assertTrue(any("ticker mismatch" in error.lower() for error in result["errors"]))
            self.assertTrue(any("latest history date" in error.lower() for error in result["errors"]))

    def test_latest_revenue_growth_uses_latest_dated_quarter_not_period_label(self) -> None:
        with TemporaryDirectory() as directory:
            history_dir = Path(directory)
            (history_dir / "ORCL.json").write_text(
                json.dumps([{"date": "2026-09-22", "close": 100.0}]),
                encoding="utf-8",
            )
            snapshot = stock("ORCL")
            snapshot["business_health"] = {
                "revenue_growth_yoy": {"value": 45.374614864357106, "as_of": "2026-08-31"},
            }
            snapshot["historical_series"] = {
                "quarterly_revenue": [
                    {
                        "period": "FY2026 Q4",
                        "as_of": "2026-05-31",
                        "metrics": {"revenue_growth_yoy": {"value": 20.6313274224989}},
                    },
                    {
                        "period": "FY2026 Q1",
                        "as_of": "2026-08-31",
                        "metrics": {"revenue_growth_yoy": {"value": 45.374614864357106}},
                    },
                ],
            }
            result = validate_refresh(
                {
                    "failed_count": 0,
                    "skipped_low_fidelity_count": 0,
                    "results": [{"ticker": "ORCL", "saved_to": "data/invest_os.sqlite"}],
                },
                {"tickers": ["ORCL"]},
                [snapshot],
                history_dir,
            )
            self.assertTrue(result["valid"], result["errors"])

            snapshot["business_health"]["revenue_growth_yoy"]["value"] = 20.6313274224989
            result = validate_refresh(
                {
                    "failed_count": 0,
                    "skipped_low_fidelity_count": 0,
                    "results": [{"ticker": "ORCL", "saved_to": "data/invest_os.sqlite"}],
                },
                {"tickers": ["ORCL"]},
                [snapshot],
                history_dir,
            )
            self.assertFalse(result["valid"])
            self.assertTrue(any("latest revenue_growth_yoy" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
