from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.entry_engine.open_data_metrics import compute_open_data_snapshot  # noqa: E402
from app.entry_engine.open_data_models import HistoricalPricePoint  # noqa: E402
from app.entry_engine.providers.open_data_provider import OpenDataProvider  # noqa: E402
from app.entry_engine.utils.file_storage import load_stock_universe  # noqa: E402


class OpenDataProviderTests(unittest.TestCase):
    def test_stock_universe_loader_merges_ordered_tickers_with_metadata_rows(self) -> None:
        payload = {
            "tickers": ["AAA", "AXFO.ST"],
            "rows": [
                {"symbol": "AAA", "name": "AAA Corp", "country": "United States"},
                {"symbol": "AXFO.ST", "name": "Axfood AB (publ)", "country": "Sweden", "currency": "SEK"},
            ],
        }

        with TemporaryDirectory() as directory:
            path = Path(directory) / "stocks.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            rows = load_stock_universe(path)

        self.assertEqual([row["symbol"] for row in rows], ["AAA", "AXFO.ST"])
        self.assertEqual(rows[1]["name"], "Axfood AB (publ)")
        self.assertEqual(rows[1]["currency"], "SEK")

    def test_yfinance_statement_frames_feed_existing_metric_engine_with_sek_currency(self) -> None:
        columns = pd.to_datetime(["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"])
        quarter_columns = pd.to_datetime(["2026-06-30", "2025-06-30"])
        frames = {
            "income_annual": pd.DataFrame(
                {
                    columns[0]: [1000.0, 420.0, 160.0, 110.0, 5.5, 20.0, 210.0],
                    columns[1]: [900.0, 360.0, 135.0, 90.0, 4.5, 20.0, 180.0],
                    columns[2]: [810.0, 320.0, 120.0, 80.0, 4.0, 20.0, 160.0],
                    columns[3]: [700.0, 280.0, 100.0, 70.0, 3.5, 20.0, 135.0],
                },
                index=[
                    "Total Revenue",
                    "Gross Profit",
                    "Operating Income",
                    "Net Income",
                    "Diluted EPS",
                    "Diluted Average Shares",
                    "EBITDA",
                ],
            ),
            "income_quarterly": pd.DataFrame(
                {
                    quarter_columns[0]: [260.0, 110.0, 45.0, 30.0, 1.5, 20.0, 55.0],
                    quarter_columns[1]: [220.0, 88.0, 33.0, 22.0, 1.1, 20.0, 42.0],
                },
                index=[
                    "Total Revenue",
                    "Gross Profit",
                    "Operating Income",
                    "Net Income",
                    "Diluted EPS",
                    "Diluted Average Shares",
                    "EBITDA",
                ],
            ),
            "cashflow_annual": pd.DataFrame(
                {
                    columns[0]: [150.0, -30.0],
                    columns[1]: [130.0, -25.0],
                    columns[2]: [110.0, -20.0],
                    columns[3]: [100.0, -18.0],
                },
                index=["Operating Cash Flow", "Capital Expenditure"],
            ),
            "cashflow_quarterly": pd.DataFrame(
                {
                    quarter_columns[0]: [40.0, 32.0],
                    quarter_columns[1]: [35.0, 27.0],
                },
                index=["Operating Cash Flow", "Free Cash Flow"],
            ),
            "balance_annual": pd.DataFrame(
                {
                    columns[0]: [80.0, 300.0, 420.0],
                    columns[1]: [70.0, 280.0, 390.0],
                    columns[2]: [65.0, 260.0, 360.0],
                    columns[3]: [60.0, 240.0, 340.0],
                },
                index=["Cash And Cash Equivalents", "Total Debt", "Stockholders Equity"],
            ),
            "balance_quarterly": pd.DataFrame(
                {
                    quarter_columns[0]: [85.0, 310.0, 440.0],
                    quarter_columns[1]: [75.0, 290.0, 400.0],
                },
                index=["Cash And Cash Equivalents", "Total Debt", "Stockholders Equity"],
            ),
        }
        provider = OpenDataProvider()

        companyfacts = provider._yfinance_companyfacts_from_frames(
            "TEST.ST",
            {"name": "Test Sweden AB"},
            {"longName": "Test Sweden AB"},
            frames,
            "SEK",
        )
        price_history = [
            HistoricalPricePoint(date=f"{year}-12-31", close=20 + year - 2022, source="test")
            for year in range(2022, 2026)
        ]
        price = provider._latest_price_from_history("TEST.ST", price_history, currency="SEK")

        snapshot = compute_open_data_snapshot(
            ticker="TEST.ST",
            cik=None,
            companyfacts=companyfacts,
            price=price,
            price_history=price_history,
            exchange="Nasdaq Stockholm",
            country="Sweden",
            sector="Industrials",
            industry="Building Products",
            forward_pe_estimate=None,
            company_context=provider._yfinance_company_context("TEST.ST"),
            statement_currency_rates={},
            market_cap_estimate=None,
            generated_as_of=date(2026, 9, 26).isoformat(),
        )

        self.assertEqual(snapshot.price_opportunity["current_price"].source, "test")
        self.assertEqual(snapshot.price_opportunity["current_price"].value, 23)
        self.assertEqual(snapshot.business_health["revenue_growth_yoy"].value, (260 - 220) / 220 * 100)
        self.assertEqual(snapshot.metrics["capex_ttm"].source.split(":", 1)[0], "yfinance_statement")
        self.assertEqual(snapshot.business_health["free_cash_flow"].value, 32)
        valuation = snapshot.historical_series["valuation_history"][-1].metrics
        self.assertIsNotNone(valuation["pe"].value)
        self.assertIsNotNone(valuation["price_to_sales"].value)


if __name__ == "__main__":
    unittest.main()
