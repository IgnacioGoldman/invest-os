from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.entry_engine.open_data_metrics import compute_open_data_snapshot  # noqa: E402
from app.entry_engine.open_data_models import HistoricalPricePoint, LatestPrice, OpenDataMetric  # noqa: E402
from app.entry_engine.providers.open_data_provider import JsonFileCache, OpenDataProvider  # noqa: E402
from app.services.stock_entry_analysis import analyze_open_data_stock_entry  # noqa: E402
from scripts.open_data_poc import _metric_coverage  # noqa: E402


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


def mocked_ifrs_companyfacts() -> dict[str, object]:
    annual_common = [
        ("2022-01-01", "2022-12-31", 2022, "2023-03-01"),
        ("2023-01-01", "2023-12-31", 2023, "2024-03-01"),
        ("2024-01-01", "2024-12-31", 2024, "2025-03-01"),
        ("2025-01-01", "2025-12-31", 2025, "2026-03-01"),
    ]

    def annual(values: list[float]) -> list[dict[str, object]]:
        return [
            fact(value, start, end, fy=fy, fp="FY", form="20-F", filed=filed)
            for value, (start, end, fy, filed) in zip(values, annual_common)
        ]

    return {
        "entityName": "Nokia Corporation",
        "facts": {
            "ifrs-full": {
                "Revenue": {"units": {"EUR": annual([22000, 23000, 24000, 26000])}},
                "ProfitLoss": {"units": {"EUR": annual([1000, 1200, 1300, 1500])}},
                "GrossProfit": {"units": {"EUR": annual([8000, 8500, 9000, 10000])}},
                "ProfitLossFromOperatingActivities": {"units": {"EUR": annual([1800, 2000, 2100, 2500])}},
                "CashFlowsFromUsedInOperatingActivities": {"units": {"EUR": annual([2500, 2600, 2700, 3000])}},
                "PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets": {
                    "units": {"EUR": annual([400, 420, 430, 450])}
                },
                "AdjustedWeightedAverageShares": {"units": {"shares": annual([5000, 5000, 5000, 5000])}},
                "DilutedEarningsLossPerShare": {"units": {"EUR/shares": annual([0.2, 0.24, 0.26, 0.3])}},
                "CashAndCashEquivalents": {"units": {"EUR": annual([4000, 4200, 4300, 4500])}},
                "Borrowings": {"units": {"EUR": annual([3000, 2900, 2800, 2700])}},
                "Equity": {"units": {"EUR": annual([12000, 12500, 13000, 14000])}},
                "DepreciationAndAmortisationExpense": {"units": {"EUR": annual([800, 820, 830, 850])}},
            }
        },
    }


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

    def test_detects_daily_support_zone_from_repeated_swing_lows(self) -> None:
        start = date(2025, 1, 1)
        support_days = {40: 95.0, 92: 96.0, 144: 95.5}
        history: list[HistoricalPricePoint] = []
        for index in range(180):
            day = start + timedelta(days=index)
            close = 112 + index * 0.05
            low = close - 1.5
            high = close + 1.5
            if index in support_days:
                low = support_days[index]
                close = low + 5
                high = close + 2
            if index == 179:
                close = 99
                low = 98
                high = 101
            history.append(
                HistoricalPricePoint(
                    date=day.isoformat(),
                    close=close,
                    high=high,
                    low=low,
                    source="mock_history",
                )
            )

        snapshot = compute_open_data_snapshot(
            ticker="GOOGL",
            cik=1652044,
            companyfacts=mocked_companyfacts(),
            price=LatestPrice(ticker="GOOGL", price=99, source="mock_price", as_of=history[-1].date),
            price_history=history,
        )

        support = snapshot.price_opportunity["support_1d_distance"]
        self.assertEqual(support.tier, "computed_from_public_facts")
        self.assertIsNotNone(support.value)
        self.assertLess(support.value or 0, 6)
        self.assertIn("Support zone:", support.notes)
        self.assertIn("touches 3", support.notes)

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

    def test_marks_eps_turnaround_as_not_meaningful_growth(self) -> None:
        companyfacts = mocked_companyfacts()
        eps_rows = companyfacts["facts"]["us-gaap"]["EarningsPerShareDiluted"]["units"]["USD/shares"]  # type: ignore[index]
        for row, value in zip(eps_rows, [-1.0, -0.8, -0.5, 0.2]):
            row["val"] = value

        snapshot = compute_open_data_snapshot(
            ticker="GOOGL",
            cik=1652044,
            companyfacts=companyfacts,
            price=LatestPrice(ticker="GOOGL", price=200, source="mock_price", as_of="2026-04-26"),
            generated_as_of="2026-04-26",
        )

        yoy = snapshot.business_health["eps_growth_yoy"]
        cagr = snapshot.business_health["eps_cagr_3y"]

        self.assertIsNone(yoy.value)
        self.assertIn("EPS turned positive", yoy.notes)
        self.assertIn("YoY EPS growth is not meaningful", yoy.notes)
        self.assertIsNone(cagr.value)
        self.assertIn("EPS turned positive", cagr.notes)
        self.assertIn("3-year EPS CAGR is not meaningful", cagr.notes)

    def test_marks_loss_making_eps_and_dependent_valuation_as_not_meaningful(self) -> None:
        companyfacts = mocked_companyfacts()
        eps_rows = companyfacts["facts"]["us-gaap"]["EarningsPerShareDiluted"]["units"]["USD/shares"]  # type: ignore[index]
        income_rows = companyfacts["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"]  # type: ignore[index]
        for row, value in zip(eps_rows, [-1.0, -1.2, -1.4, -2.0]):
            row["val"] = value
        for row in income_rows:
            row["val"] = -abs(float(row["val"]))

        snapshot = compute_open_data_snapshot(
            ticker="RDW",
            cik=1819810,
            companyfacts=companyfacts,
            price=LatestPrice(ticker="RDW", price=10, source="mock_price", as_of="2026-04-26"),
            generated_as_of="2026-04-26",
        )
        coverage = _metric_coverage(snapshot)

        self.assertIsNone(snapshot.business_health["eps_growth_yoy"].value)
        self.assertIn("EPS remains loss-making", snapshot.business_health["eps_growth_yoy"].notes)
        self.assertIsNone(snapshot.business_health["eps_cagr_3y"].value)
        self.assertIn("EPS remains loss-making", snapshot.business_health["eps_cagr_3y"].notes)
        self.assertIsNone(snapshot.valuation["forward_pe"].value)
        self.assertIn("not meaningful", snapshot.valuation["forward_pe"].notes)
        self.assertIsNone(snapshot.valuation["peg"].value)
        self.assertIn("not meaningful", snapshot.valuation["peg"].notes)
        self.assertNotIn("business_health.eps_growth_yoy", coverage["missing_metrics"])
        self.assertNotIn("business_health.eps_cagr_3y", coverage["missing_metrics"])
        self.assertIn("business_health.eps_growth_yoy", {item["metric"] for item in coverage["not_meaningful_metrics"]})

    def test_reads_ifrs_eur_fundamentals_without_mixed_currency_valuation(self) -> None:
        snapshot = compute_open_data_snapshot(
            ticker="NOK",
            cik=924613,
            companyfacts=mocked_ifrs_companyfacts(),
            price=LatestPrice(ticker="NOK", price=10, currency="USD", source="mock_us_adr_price", as_of="2026-04-26"),
            generated_as_of="2026-04-26",
        )

        self.assertEqual(snapshot.name, "Nokia Corporation")
        self.assertEqual(snapshot.metrics["revenue_ttm"].value, 26000)
        self.assertIn("sec_companyfacts:ifrs-full/Revenue:EUR:20-F", snapshot.metrics["revenue_ttm"].source)
        self.assertAlmostEqual(snapshot.business_health["revenue_growth_yoy"].value or 0, 8.3333333333)
        self.assertAlmostEqual(snapshot.business_health["gross_margin"].value or 0, 38.4615384615)
        self.assertEqual(snapshot.business_health["cash"].value, 4500)
        self.assertEqual(snapshot.business_health["debt"].value, 2700)
        self.assertEqual(snapshot.valuation["pe"].tier, "unavailable_open_free")
        self.assertIn("Statement currency (EUR) does not match price currency (USD)", snapshot.valuation["pe"].notes)
        self.assertTrue(any("Foreign-currency fundamentals are supported" in gap for gap in snapshot.data_gaps))

    def test_stock_entry_analysis_uses_open_data_snapshot(self) -> None:
        price_history = [
            HistoricalPricePoint(
                date=point.date,
                close=90 if point.date == "2025-04-26" else point.close,
                volume=point.volume,
                source=point.source,
            )
            for point in mocked_price_history()
        ]
        snapshot = compute_open_data_snapshot(
            ticker="GOOGL",
            cik=1652044,
            companyfacts=mocked_companyfacts(),
            price=LatestPrice(ticker="GOOGL", price=200, source="mock_price", as_of="2026-04-26"),
            price_history=price_history,
            generated_as_of="2026-04-26",
        )

        analysis = analyze_open_data_stock_entry(snapshot)

        self.assertEqual(analysis.ticker, "GOOGL")
        self.assertFalse(analysis.needs_more_data)
        self.assertEqual(analysis.opportunity_type, "Quality compounder pullback")
        self.assertEqual(analysis.business_health.assessment, "strong")
        self.assertEqual(analysis.price_opportunity.assessment, "pullback")
        self.assertTrue(any("Price is down 20.00% over 1 month." in item for item in analysis.price_opportunity.evidence))
        self.assertFalse(any("down -20.00%" in item for item in analysis.price_opportunity.evidence))
        self.assertGreater(analysis.dca_entry.buy_now, 0)
        payload = analysis.model_dump()
        self.assertNotIn("bull_case", payload)
        self.assertNotIn("bear_case", payload)
        self.assertNotIn("risks", payload)
        self.assertNotIn("conditions", payload["dca_entry"])

    def test_stock_entry_analysis_marks_positive_ath_momentum_as_extended_not_unclear(self) -> None:
        price_history = [
            HistoricalPricePoint(date="2021-04-26", close=80, source="mock_history"),
            HistoricalPricePoint(date="2024-04-26", close=120, source="mock_history"),
            HistoricalPricePoint(date="2025-04-26", close=90, source="mock_history"),
            HistoricalPricePoint(date="2026-01-26", close=130, source="mock_history"),
            HistoricalPricePoint(date="2026-03-26", close=150, source="mock_history"),
            HistoricalPricePoint(date="2026-04-19", close=185, source="mock_history"),
            HistoricalPricePoint(date="2026-04-26", close=200, source="mock_history"),
        ]
        snapshot = compute_open_data_snapshot(
            ticker="ASML",
            cik=937966,
            companyfacts=mocked_companyfacts(),
            price=LatestPrice(ticker="ASML", price=200, source="mock_price", as_of="2026-04-26"),
            price_history=price_history,
            generated_as_of="2026-04-26",
        )

        analysis = analyze_open_data_stock_entry(snapshot)

        self.assertFalse(analysis.needs_more_data)
        self.assertEqual(analysis.opportunity_type, "Momentum continuation")
        self.assertEqual(analysis.price_opportunity.assessment, "no_dip")
        self.assertEqual(analysis.dca_entry.buy_now, 0)
        self.assertEqual(analysis.dca_entry.buy_dip_1, 0)
        self.assertEqual(analysis.dca_entry.buy_dip_2, 0)
        self.assertFalse(any("Enough price-history facts" in item for item in analysis.missing_data))
        self.assertTrue(any("Price is up" in item for item in analysis.price_opportunity.evidence))
        self.assertFalse(any("Price is down" in item for item in analysis.price_opportunity.evidence))
        self.assertTrue(any("at or near the all-time high" in item for item in analysis.price_opportunity.evidence))
        self.assertIn(analysis.valuation.assessment, {"pricey", "very_pricey"})
        self.assertTrue(any("high on an absolute basis" in item for item in analysis.valuation.concerns))

    def test_stock_entry_analysis_marks_better_spot_with_sideways_trend_not_unclear(self) -> None:
        snapshot = compute_open_data_snapshot(
            ticker="META",
            cik=1326801,
            companyfacts=mocked_companyfacts(),
            price=LatestPrice(ticker="META", price=170, source="mock_price", as_of="2026-04-26"),
            price_history=[
                HistoricalPricePoint(date="2021-04-26", close=90, source="mock_history"),
                HistoricalPricePoint(date="2024-04-26", close=120, source="mock_history"),
                HistoricalPricePoint(date="2025-04-26", close=182, source="mock_history"),
                HistoricalPricePoint(date="2025-10-26", close=176, source="mock_history"),
                HistoricalPricePoint(date="2026-01-26", close=184, source="mock_history"),
                HistoricalPricePoint(date="2026-02-26", close=216, source="mock_history"),
                HistoricalPricePoint(date="2026-03-26", close=166, source="mock_history"),
                HistoricalPricePoint(date="2026-04-19", close=173, source="mock_history"),
                HistoricalPricePoint(date="2026-04-26", close=170, source="mock_history"),
            ],
            generated_as_of="2026-04-26",
        )

        analysis = analyze_open_data_stock_entry(snapshot)

        self.assertFalse(analysis.needs_more_data)
        self.assertEqual(analysis.price_opportunity.assessment, "better_spot")
        self.assertTrue(any("below the all-time high" in item for item in analysis.price_opportunity.evidence))
        self.assertTrue(any("meaningfully off its high" in item for item in analysis.price_opportunity.concerns))

    def test_stock_entry_analysis_withholds_cheap_label_when_valuation_history_is_distorted(self) -> None:
        snapshot = compute_open_data_snapshot(
            ticker="AZN",
            cik=901832,
            companyfacts=mocked_companyfacts(),
            price=LatestPrice(ticker="AZN", price=170, source="mock_price", as_of="2026-04-26"),
            price_history=[
                HistoricalPricePoint(date="2021-04-26", close=100, source="mock_history"),
                HistoricalPricePoint(date="2024-04-26", close=140, source="mock_history"),
                HistoricalPricePoint(date="2025-04-26", close=180, source="mock_history"),
                HistoricalPricePoint(date="2026-01-26", close=190, source="mock_history"),
                HistoricalPricePoint(date="2026-03-26", close=175, source="mock_history"),
                HistoricalPricePoint(date="2026-04-19", close=172, source="mock_history"),
                HistoricalPricePoint(date="2026-04-26", close=170, source="mock_history"),
            ],
            generated_as_of="2026-04-26",
        )
        snapshot.valuation["pe"] = OpenDataMetric(
            value=12,
            source="mock",
            tier="computed_from_public_facts",
            as_of="2026-04-26",
            notes="mock current PE",
        )
        snapshot.valuation["fcf_yield"] = OpenDataMetric(
            value=7,
            source="mock",
            tier="computed_from_public_facts",
            as_of="2026-04-26",
            notes="mock current FCF yield",
        )
        snapshot.valuation["price_to_sales"] = OpenDataMetric(
            value=2,
            source="mock",
            tier="computed_from_public_facts",
            as_of="2026-04-26",
            notes="mock current price/sales",
        )
        snapshot.valuation["forward_pe"] = OpenDataMetric(
            value=20,
            source="mock",
            tier="proxy_estimate",
            as_of="2026-04-26",
            notes="mock forward PE",
        )
        snapshot.valuation["ev_to_ebitda"] = OpenDataMetric(
            value=10,
            source="mock",
            tier="proxy_estimate",
            as_of="2026-04-26",
            notes="mock EV/EBITDA",
        )
        for row, pe in zip(snapshot.historical_series["valuation_history"], [20, 30, 40, 500]):
            row.metrics["pe"] = OpenDataMetric(
                value=pe,
                source="mock",
                tier="computed_from_public_facts",
                as_of=row.as_of,
                notes="mock annual PE",
            )
            row.metrics["price_to_sales"] = OpenDataMetric(
                value=4,
                source="mock",
                tier="computed_from_public_facts",
                as_of=row.as_of,
                notes="mock annual price/sales",
            )
            row.metrics["ev_to_ebitda"] = OpenDataMetric(
                value=15,
                source="mock",
                tier="proxy_estimate",
                as_of=row.as_of,
                notes="mock annual EV/EBITDA",
            )
        snapshot.data_gaps.append("Foreign-currency fundamentals are supported, while historical valuation still needs historical FX handling.")

        analysis = analyze_open_data_stock_entry(snapshot)

        self.assertEqual(analysis.valuation.assessment, "fair")
        self.assertTrue(
            any("strongest cheap label is withheld" in item for item in analysis.valuation.concerns)
        )

    def test_stock_entry_analysis_marks_complete_but_mixed_business_as_not_needing_more_data(self) -> None:
        companyfacts = mocked_companyfacts()
        eps_rows = companyfacts["facts"]["us-gaap"]["EarningsPerShareDiluted"]["units"]["USD/shares"]  # type: ignore[index]
        for row, value in zip(eps_rows, [1.0, 1.2, 2.1, 2.0]):
            row["val"] = value

        snapshot = compute_open_data_snapshot(
            ticker="META",
            cik=1326801,
            companyfacts=companyfacts,
            price=LatestPrice(ticker="META", price=170, source="mock_price", as_of="2026-04-26"),
            price_history=[
                HistoricalPricePoint(date="2021-04-26", close=100, source="mock_history"),
                HistoricalPricePoint(date="2024-04-26", close=140, source="mock_history"),
                HistoricalPricePoint(date="2025-04-26", close=180, source="mock_history"),
                HistoricalPricePoint(date="2026-01-26", close=190, source="mock_history"),
                HistoricalPricePoint(date="2026-03-26", close=175, source="mock_history"),
                HistoricalPricePoint(date="2026-04-19", close=172, source="mock_history"),
                HistoricalPricePoint(date="2026-04-26", close=170, source="mock_history"),
            ],
            generated_as_of="2026-04-26",
        )

        analysis = analyze_open_data_stock_entry(snapshot)

        self.assertFalse(analysis.needs_more_data)
        self.assertIn(analysis.business_health.assessment, {"mixed", "weak"})
        self.assertEqual(analysis.missing_data, [])
        self.assertLess(analysis.conviction, 6)
        self.assertIn("mixed business facts", analysis.summary)

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
        self.assertEqual(context.known_context_gaps, [])

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
