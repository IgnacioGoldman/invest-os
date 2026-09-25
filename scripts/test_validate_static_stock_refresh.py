from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from validate_static_stock_refresh import SUPPORT_KEYS, validate_refresh


def stock(ticker: str, market_date: str = "2026-09-22") -> dict:
    return {
        "ticker": ticker,
        "price_opportunity": {
            "current_price": {"value": 100.0, "as_of": market_date},
            **{key: {"value": 2.0, "as_of": market_date} for key in SUPPORT_KEYS},
        },
    }


class StaticStockRefreshValidatorTests(unittest.TestCase):
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
