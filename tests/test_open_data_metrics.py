from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.entry_engine.open_data_metrics import compute_open_data_snapshot  # noqa: E402
from app.entry_engine.open_data_models import HistoricalPricePoint, LatestPrice, OpenDataMetric  # noqa: E402
from app.entry_engine.providers.open_data_provider import JsonFileCache, OpenDataProvider  # noqa: E402


def fact(
    val: float,
    start: str,
    end: str,
    *,
    fy: int,
    fp: str,
    form: str,
    filed: str,
) -> dict[str, object]:
    return {
        "val": val,
        "start": start,
        "end": end,
        "fy": fy,
        "fp": fp,
        "form": form,
        "filed": filed,
    }


def mocked_companyfacts() -> dict[str, object]:
    annual_common = [
        ("2022-01-01", "2022-12-31", 2022, "2023-02-03"),
        ("2023-01-01", "2023-12-31", 2023, "2024-02-03"),
        ("2024-01-01", "2024-12-31", 2024, "2025-02-03"),
        ("2025-01-01", "2025-12-31", 2025, "2026-02-03"),
    ]

    def annual(values: list[float]) -> list[dict[str, object]]:
        return [
            fact(value, start, end, fy=fy, fp="FY", form="10-K", filed=filed)
            for value, (start, end, fy, filed) in zip(values, annual_common)
        ]

    q1_2025 = ("2025-01-01", "2025-03-31", 2025, "Q1", "10-Q", "2025-04-25")
    q1_2026 = ("2026-01-01", "2026-03-31", 2026, "Q1", "10-Q", "2026-04-25")

    def quarter(value: float, row: tuple[str, str, int, str, str, str]) -> dict[str, object]:
        start, end, fy, fp, form, filed = row
        return fact(value, start, end, fy=fy, fp=fp, form=form, filed=filed)

    return {
        "entityName": "Alphabet Inc.",
        "facts": {
            "us-gaap": {
                "Revenues": {"units": {"USD": [*annual([1000, 1200, 1400, 1600]), quarter(350, q1_2025), quarter(500, q1_2026)]}},
                "CostOfRevenue": {"units": {"USD": [*annual([400, 480, 560, 640]), quarter(140, q1_2025), quarter(160, q1_2026)]}},
                "NetIncomeLoss": {"units": {"USD": [*annual([100, 120, 140, 200]), quarter(40, q1_2025), quarter(70, q1_2026)]}},
                "OperatingIncomeLoss": {"units": {"USD": [*annual([220, 260, 320, 400]), quarter(80, q1_2025), quarter(150, q1_2026)]}},
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {"USD": [*annual([150, 180, 220, 260]), quarter(50, q1_2025), quarter(80, q1_2026)]}
                },
                "PaymentsToAcquirePropertyPlantAndEquipment": {
                    "units": {"USD": [*annual([20, 30, 40, 50]), quarter(10, q1_2025), quarter(15, q1_2026)]}
                },
                "WeightedAverageNumberOfDilutedSharesOutstanding": {
                    "units": {"shares": [*annual([100, 100, 100, 100]), quarter(100, q1_2025), quarter(101, q1_2026)]}
                },
                "EarningsPerShareDiluted": {"units": {"USD/shares": annual([1.0, 1.2, 1.4, 2.0])}},
                "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [quarter(300, q1_2026)]}},
                "LongTermDebtCurrent": {"units": {"USD": [quarter(20, q1_2026)]}},
                "LongTermDebtNoncurrent": {"units": {"USD": [quarter(80, q1_2026)]}},
                "StockholdersEquity": {"units": {"USD": [quarter(1000, q1_2026)]}},
                "Depreciation": {"units": {"USD": [*annual([10, 12, 14, 16]), quarter(3, q1_2025), quarter(4, q1_2026)]}},
            }
        },
    }


def mocked_price_history() -> list[HistoricalPricePoint]:
    rows = [
        ("2021-04-26", 100),
        ("2024-04-26", 150),
        ("2025-04-26", 180),
        ("2026-01-26", 220),
        ("2026-03-26", 250),
        ("2026-04-19", 190),
        ("2026-04-25", 198),
        ("2026-04-26", 200),
    ]
    return [HistoricalPricePoint(date=day, close=close, source="mock_history") for day, close in rows]


class OpenDataMetricsTest(unittest.TestCase):
    def test_computes_ttm_valuation_and_proxy_metrics_from_public_inputs(self) -> None:
        snapshot = compute_open_data_snapshot(
            ticker="GOOGL",
            cik=1652044,
            companyfacts=mocked_companyfacts(),
            price=LatestPrice(ticker="GOOGL", price=200, source="mock_price", as_of="2026-04-26"),
            price_history=mocked_price_history(),
            generated_as_of="2026-04-26",
        )
        metrics = snapshot.metrics

        self.assertEqual(snapshot.name, "Alphabet Inc.")
        self.assertEqual(metrics["revenue_ttm"].value, 1750)
        self.assertEqual(metrics["net_income_ttm"].value, 230)
        self.assertEqual(metrics["operating_cash_flow_ttm"].value, 290)
        self.assertEqual(metrics["capex_ttm"].value, 55)
        self.assertEqual(metrics["free_cash_flow_ttm"].value, 235)
        self.assertEqual(metrics["shares_diluted"].value, 101)
        self.assertEqual(metrics["market_cap"].value, 20200)
        self.assertAlmostEqual(metrics["pe_ttm"].value or 0, 87.8260869565)
        self.assertAlmostEqual(metrics["price_to_sales_ttm"].value or 0, 11.5428571429)
        self.assertAlmostEqual(metrics["fcf_yield"].value or 0, 1.1633663366)
        self.assertAlmostEqual(snapshot.business_health["gross_margin"].value or 0, 62.2857142857)
        self.assertAlmostEqual(snapshot.price_opportunity["change_1d"].value or 0, 1.0101010101)
        self.assertAlmostEqual(snapshot.price_opportunity["change_1m"].value or 0, -20)
        self.assertAlmostEqual(snapshot.price_opportunity["distance_from_ath"].value or 0, -20)
        self.assertAlmostEqual(metrics["eps_growth_3y_proxy"].value or 0, 25.9921049895)
        self.assertAlmostEqual(metrics["forward_pe_proxy"].value or 0, 69.7076114125)
        self.assertAlmostEqual(metrics["peg_proxy"].value or 0, 3.3789524547)

        self.assertEqual(metrics["revenue_ttm"].tier, "computed_from_public_facts")
        self.assertEqual(metrics["shares_diluted"].tier, "exact_public_fact")
        self.assertEqual(snapshot.valuation["ev_to_ebitda"].tier, "proxy_estimate")
        self.assertEqual(metrics["forward_pe_proxy"].tier, "proxy_estimate")
        self.assertIn("not analyst consensus", metrics["forward_pe_proxy"].notes)
        self.assertIn("annual_fundamentals", snapshot.historical_series)
        self.assertIn("valuation_history", snapshot.historical_series)
        self.assertEqual([row.period for row in snapshot.historical_series["annual_fundamentals"]], [
            "2022",
            "2023",
            "2024",
            "2025",
        ])
        latest_annual = snapshot.historical_series["annual_fundamentals"][-1]
        self.assertEqual(latest_annual.metrics["revenue"].value, 1600)
        self.assertAlmostEqual(latest_annual.metrics["fcf_margin"].value or 0, 13.125)
        latest_valuation = snapshot.historical_series["valuation_history"][-1]
        self.assertEqual(latest_valuation.metrics["year_end_price"].value, 180)
        self.assertAlmostEqual(latest_valuation.metrics["pe"].value or 0, 90)
        self.assertTrue(snapshot.data_gaps)

    def test_marks_price_derived_metrics_unavailable_without_open_price(self) -> None:
        snapshot = compute_open_data_snapshot(
            ticker="GOOGL",
            cik=1652044,
            companyfacts=mocked_companyfacts(),
            price=None,
            generated_as_of="2026-04-26",
        )

        self.assertEqual(snapshot.metrics["revenue_ttm"].value, 1750)
        self.assertEqual(snapshot.metrics["market_cap"].tier, "unavailable_open_free")
        self.assertEqual(snapshot.metrics["pe_ttm"].tier, "unavailable_open_free")
        self.assertEqual(snapshot.metrics["forward_pe_proxy"].tier, "unavailable_open_free")

    def test_uses_public_forward_pe_estimate_when_available(self) -> None:
        snapshot = compute_open_data_snapshot(
            ticker="GOOGL",
            cik=1652044,
            companyfacts=mocked_companyfacts(),
            price=LatestPrice(ticker="GOOGL", price=200, source="mock_price", as_of="2026-04-26"),
            price_history=mocked_price_history(),
            forward_pe_estimate=OpenDataMetric(
                value=42,
                source="yfinance:forwardPE",
                tier="proxy_estimate",
                as_of="2026-04-26",
                notes="Mock public forward PE estimate.",
            ),
            generated_as_of="2026-04-26",
        )

        self.assertEqual(snapshot.valuation["forward_pe"].value, 42)
        self.assertEqual(snapshot.valuation["forward_pe"].source, "yfinance:forwardPE")
        self.assertNotEqual(snapshot.metrics["forward_pe_proxy"].value, 42)
        self.assertEqual(snapshot.metrics["forward_pe_public_estimate"].value, 42)
        self.assertFalse(any("forward PE estimate was unavailable" in gap for gap in snapshot.data_gaps))

    def test_fills_historical_shares_and_debt_from_public_fact_fallbacks(self) -> None:
        companyfacts = mocked_companyfacts()
        us_gaap = companyfacts["facts"]["us-gaap"]  # type: ignore[index]
        shares_rows = us_gaap["WeightedAverageNumberOfDilutedSharesOutstanding"]["units"]["shares"]  # type: ignore[index]
        us_gaap["WeightedAverageNumberOfDilutedSharesOutstanding"]["units"]["shares"] = [  # type: ignore[index]
            row for row in shares_rows if row["fy"] != 2022
        ]
        us_gaap["LongTermDebt"] = {"units": {"USD": [  # type: ignore[index]
            fact(70, "2022-01-01", "2022-12-31", fy=2022, fp="FY", form="10-K", filed="2023-02-03"),
            fact(75, "2023-01-01", "2023-12-31", fy=2023, fp="FY", form="10-K", filed="2024-02-03"),
        ]}}

        snapshot = compute_open_data_snapshot(
            ticker="GOOGL",
            cik=1652044,
            companyfacts=companyfacts,
            price=LatestPrice(ticker="GOOGL", price=200, source="mock_price", as_of="2026-04-26"),
            price_history=mocked_price_history(),
            generated_as_of="2026-04-26",
        )

        annual_by_year = {row.period: row for row in snapshot.historical_series["annual_fundamentals"]}
        valuation_by_year = {row.period: row for row in snapshot.historical_series["valuation_history"]}

        self.assertEqual(annual_by_year["2022"].metrics["shares_diluted"].value, 100)
        self.assertEqual(annual_by_year["2022"].metrics["shares_diluted"].tier, "computed_from_public_facts")
        self.assertEqual(annual_by_year["2022"].metrics["debt"].value, 70)
        self.assertEqual(annual_by_year["2023"].metrics["debt"].value, 75)
        self.assertEqual(valuation_by_year["2022"].metrics["market_cap"].value, 10000)
        self.assertEqual(valuation_by_year["2022"].metrics["pe"].value, 100)


class OpenDataProviderCompanyContextTest(unittest.TestCase):
    def test_builds_company_context_from_sec_submissions(self) -> None:
        submissions = {
            "filings": {
                "recent": {
                    "accessionNumber": ["0001652044-26-000001", "0001652044-26-000002", "0001652044-26-000003"],
                    "form": ["8-K", "10-Q", "4"],
                    "filingDate": ["2026-04-25", "2026-04-24", "2026-04-23"],
                    "reportDate": ["2026-04-25", "2026-03-31", "2026-04-22"],
                    "acceptanceDateTime": ["2026-04-25T16:01:00.000Z", "2026-04-24T16:01:00.000Z", ""],
                    "primaryDocument": ["goog-20260425.htm", "goog-20260331.htm", "xslF345X05/doc4.xml"],
                    "primaryDocDescription": ["Current report", "Quarterly report", ""],
                    "items": ["2.02, 9.01", "", ""],
                }
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            provider = OpenDataProvider(cache=JsonFileCache(Path(tmpdir)))
            provider._fetch_filing_exhibits = lambda cik, accession: [  # type: ignore[method-assign]
                {
                    "document": "exhibit991.htm",
                    "description": "Press release",
                    "type": "EX-99.1",
                    "url": "https://www.sec.gov/example",
                }
            ]
            context = provider._company_context_from_submissions(1652044, submissions)

        self.assertIsNotNone(context)
        assert context is not None
        self.assertEqual(context.as_of, "2026-04-25")
        self.assertEqual(len(context.recent_filings), 2)
        self.assertEqual(context.recent_filings[0].form, "8-K")
        self.assertEqual(context.recent_filings[0].items, ["2.02", "9.01"])
        self.assertEqual(context.recent_filings[0].exhibits[0].type, "EX-99.1")
        self.assertIn("General media/news sentiment", context.known_context_gaps[0])

    def test_filters_static_sec_assets_from_filing_exhibits(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = OpenDataProvider(cache=JsonFileCache(Path(tmpdir)))

            self.assertFalse(provider._is_meaningful_filing_exhibit("text.gif", None, "Complete submission text file"))
            self.assertFalse(provider._is_meaningful_filing_exhibit("FilingSummary.xml", None, "Filing Summary"))
            self.assertTrue(provider._is_meaningful_filing_exhibit("exhibit991.htm", "EX-99.1", "Press release"))
            self.assertTrue(provider._is_meaningful_filing_exhibit("exhibit101.htm", "EX-10.1", "Agreement"))
            self.assertTrue(provider._is_meaningful_filing_exhibit("googexhibit991q12026.htm", "text.gif", None))
            self.assertEqual(provider._infer_exhibit_type("googexhibit991q12026.htm", "text.gif", None), "EX-99.1")
            self.assertEqual(provider._infer_exhibit_type("d109021dex410.htm", "text.gif", None), "EX-4.10")
            self.assertEqual(provider._infer_exhibit_type("googexhibit1001q12026.htm", "text.gif", None), "EX-10.1")


if __name__ == "__main__":
    unittest.main()
