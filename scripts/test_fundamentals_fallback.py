from __future__ import annotations

import json
from contextlib import ExitStack
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.entry_engine.open_data_models import HistoricalPricePoint, OpenDataMetric, OpenDataSnapshot, OpenDataPeriodMetrics
from app.entry_engine.open_data_metrics import compute_open_data_snapshot
from app.entry_engine.providers.open_data_provider import OpenDataProvider
from app.entry_engine.providers.nibe_reports import refresh_nibe_reports
from app.services.stock_data_quality import retain_verified_history
from validate_static_stock_refresh import _validate_fcf_margin, _validate_latest_revenue_growth


def primary_facts():
    return {"facts": {"us-gaap": {"RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
        {"val": 400, "start": "2025-01-01", "end": "2025-12-31", "filed": "2026-02-01", "form": "10-K", "fp": "FY", "fy": 2025},
        {"val": 130, "start": "2026-04-01", "end": "2026-06-30", "filed": "2026-08-01", "form": "10-Q", "fp": "Q2", "fy": 2026},
    ]}}}}}


def statement_row(value, end, *, quarterly=False):
    year = int(end[:4])
    return {"val": value, "start": f"{year}-04-01" if quarterly else f"{year}-01-01", "end": end,
            "filed": f"{year}-08-01" if quarterly else f"{year + 1}-02-01",
            "form": "10-Q" if quarterly else "10-K", "fp": "Q2" if quarterly else "FY", "fy": year}


def facts_for(taxonomy, rows):
    return {"facts": {taxonomy: {name: {"units": {"USD": values}} for name, values in rows.items()}}}


def fallback_snapshot(primary, vendor):
    provider = OpenDataProvider()
    with ExitStack() as stack:
        for name, value in {
            "resolve_company_metadata": {"cik": 123}, "fetch_companyfacts": primary,
            "fetch_price_history": [], "fetch_latest_price": None,
            "fetch_forward_pe_estimate": None, "fetch_market_cap_estimate": None,
            "fetch_next_earnings_release": None, "fetch_company_context": None,
            "fetch_statement_currency_rates": {}, "fetch_yfinance_companyfacts": vendor,
        }.items():
            stack.enter_context(patch.object(provider, name, return_value=value))
        return provider.get_open_data_snapshot("TEST")


class FundamentalsFallbackTests(unittest.TestCase):
    def test_full_collection_uses_yahoo_history_without_waiting_for_stooq(self):
        history = [HistoricalPricePoint(date="2026-10-12", close=100, source="yfinance")]
        cache = SimpleNamespace(get=lambda *args: None, set=lambda *args: None)
        provider = OpenDataProvider(cache=cache)
        with patch.object(provider, "_fetch_yfinance_history", return_value=history), patch.object(provider, "_fetch_stooq_history") as stooq:
            self.assertEqual(provider.fetch_price_history("TEST"), history)
        stooq.assert_not_called()

    def test_full_collection_retains_stooq_as_history_fallback(self):
        history = [HistoricalPricePoint(date="2026-10-12", close=100, source="stooq")]
        cache = SimpleNamespace(get=lambda *args: None, set=lambda *args: None)
        provider = OpenDataProvider(cache=cache)
        with patch.object(provider, "_fetch_yfinance_history", return_value=[]), patch.object(provider, "_fetch_stooq_history", return_value=history) as stooq:
            self.assertEqual(provider.fetch_price_history("TEST"), history)
        stooq.assert_called_once_with("TEST")

    def assert_consistent(self, snapshot):
        errors = []
        payload = snapshot.model_dump(mode="json")
        _validate_fcf_margin(snapshot.ticker, payload, errors)
        _validate_latest_revenue_growth(snapshot.ticker, payload, errors)
        self.assertFalse(errors, errors)
        margin = snapshot.business_health.get("fcf_margin")
        if margin is not None:
            self.assertEqual(margin, snapshot.metrics["fcf_margin_ttm"])
            self.assertEqual(margin, snapshot.metrics["fcf_margin"])

    def test_azn_newer_vendor_quarter_updates_growth_card_and_history_together(self):
        primary = facts_for("ifrs-full", {
            "RevenueFromSaleOfGoods": [statement_row(100, "2024-06-30", quarterly=True), statement_row(110, "2025-06-30", quarterly=True)],
            "Revenue": [statement_row(400, "2025-12-31")],
            "CashFlowsFromUsedInOperatingActivities": [statement_row(100, "2025-12-31")],
            "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities": [statement_row(20, "2025-12-31")],
        })
        vendor = facts_for("yfinance", {
            "RevenueFromContractWithCustomerExcludingAssessedTax": [statement_row(999, "2025-06-30", quarterly=True), statement_row(132, "2026-06-30", quarterly=True)],
            # Yahoo's alias must not replace the reported IFRS capex value.
            "PaymentsToAcquirePropertyPlantAndEquipment": [statement_row(60, "2025-12-31")],
        })
        snapshot = fallback_snapshot(primary, vendor)
        self.assertAlmostEqual(snapshot.business_health["revenue_growth_yoy"].value, 20)
        self.assertEqual(snapshot.business_health["revenue_growth_yoy"].as_of, "2026-06-30")
        self.assertEqual(snapshot.metrics["capex_ttm"].value, 20)
        self.assertAlmostEqual(snapshot.business_health["fcf_margin"].value, 20)
        self.assert_consistent(snapshot)

    def test_total_revenue_takes_priority_over_product_sales_in_the_same_period(self):
        primary = facts_for("ifrs-full", {
            "Revenue": [statement_row(100, "2025-06-30", quarterly=True), statement_row(120, "2026-06-30", quarterly=True)],
            "RevenueFromSaleOfGoods": [statement_row(80, "2025-06-30", quarterly=True), statement_row(100, "2026-06-30", quarterly=True)],
        })
        snapshot = compute_open_data_snapshot(ticker="TEST", cik=123, companyfacts=primary, price=None)
        self.assertEqual(snapshot.business_health["revenue_growth_yoy"].value, 20)
        self.assertEqual(snapshot.historical_series["quarterly_revenue"][-1].metrics["revenue"].value, 120)
        self.assert_consistent(snapshot)

    def test_cop_capex_gap_recalculates_fcf_for_a_complete_common_period(self):
        def ytd(value, year):
            row = statement_row(value, f"{year}-06-30", quarterly=True)
            row["start"] = f"{year}-01-01"
            return row
        primary = facts_for("us-gaap", {
            "Revenues": [statement_row(400, "2025-12-31"), ytd(200, 2025), ytd(250, 2026)],
            "NetCashProvidedByUsedInOperatingActivities": [statement_row(100, "2025-12-31"), ytd(40, 2025), ytd(60, 2026)],
            "PaymentsToAcquireProductiveAssets": [statement_row(10, "2022-12-31")],
        })
        vendor = facts_for("yfinance", {
            "RevenueFromContractWithCustomerExcludingAssessedTax": [statement_row(999, "2025-12-31")],
            "PaymentsToAcquirePropertyPlantAndEquipment": [statement_row(30, "2025-12-31")],
        })
        snapshot = fallback_snapshot(primary, vendor)
        self.assertEqual(snapshot.metrics["revenue_ttm"].value, 400)
        self.assertEqual(snapshot.metrics["operating_cash_flow_ttm"].value, 100)
        self.assertEqual(snapshot.metrics["free_cash_flow_ttm"].value, 70)
        self.assertAlmostEqual(snapshot.business_health["fcf_margin"].value, 17.5)
        self.assertEqual({snapshot.metrics[key].as_of for key in ("revenue_ttm", "operating_cash_flow_ttm", "capex_ttm", "free_cash_flow_ttm")}, {"2025-12-31"})
        previous = compute_open_data_snapshot(ticker="TEST", cik=123, companyfacts=primary, price=None)
        # The previous calculation had a newer-looking date but stale capex.
        self.assertEqual(previous.metrics["revenue_ttm"].as_of, "2026-06-30")
        retained = retain_verified_history(snapshot, previous)
        self.assertEqual(retained.metrics["revenue_ttm"].value, 400)
        self.assertEqual(retained.metrics["capex_ttm"].value, 30)
        self.assert_consistent(retained)

    def test_thin_refresh_retains_complete_fcf_inputs_and_percentage_together(self):
        facts = facts_for("us-gaap", {
            "Revenues": [statement_row(400, "2025-12-31")],
            "NetCashProvidedByUsedInOperatingActivities": [statement_row(100, "2025-12-31")],
            "PaymentsToAcquirePropertyPlantAndEquipment": [statement_row(20, "2025-12-31")],
        })
        previous = compute_open_data_snapshot(ticker="TEST", cik=123, companyfacts=facts, price=None)
        current = compute_open_data_snapshot(ticker="TEST", cik=123, companyfacts={}, price=None)
        result = retain_verified_history(current, previous)
        self.assertEqual(result.metrics["free_cash_flow_ttm"].value, 80)
        self.assertEqual(result.business_health["fcf_margin"].value, 20)
        self.assert_consistent(result)

    def test_fallback_without_a_common_fcf_period_keeps_known_revenue(self):
        primary = facts_for("us-gaap", {
            "Revenues": [statement_row(400, "2025-12-31")],
            "NetCashProvidedByUsedInOperatingActivities": [statement_row(100, "2025-12-31")],
        })
        vendor = facts_for("yfinance", {
            "RevenueFromContractWithCustomerExcludingAssessedTax": [statement_row(999, "2025-12-31")],
            "PaymentsToAcquirePropertyPlantAndEquipment": [statement_row(20, "2022-12-31")],
        })
        snapshot = fallback_snapshot(primary, vendor)
        self.assertEqual(snapshot.metrics["revenue_ttm"].value, 400)
        self.assertEqual(snapshot.metrics["operating_cash_flow_ttm"].value, 100)
        self.assertIsNone(snapshot.business_health["fcf_margin"].value)
        retained = retain_verified_history(snapshot, OpenDataSnapshot(ticker="TEST"))
        self.assertIsNone(retained.business_health["fcf_margin"].value)
        self.assert_consistent(retained)

    def test_thin_refresh_keeps_newer_complete_fcf_bundle(self):
        def snapshot(year, sales, cash_flow, capex):
            return compute_open_data_snapshot(ticker="TEST", cik=123, price=None, companyfacts=facts_for("us-gaap", {
                "Revenues": [statement_row(sales, f"{year}-12-31")],
                "NetCashProvidedByUsedInOperatingActivities": [statement_row(cash_flow, f"{year}-12-31")],
                "PaymentsToAcquirePropertyPlantAndEquipment": [statement_row(capex, f"{year}-12-31")],
            }))
        result = retain_verified_history(snapshot(2024, 300, 80, 20), snapshot(2025, 400, 100, 20))
        self.assertEqual(result.metrics["revenue_ttm"].value, 400)
        self.assertEqual(result.business_health["fcf_margin"].as_of, "2025-12-31")
        self.assert_consistent(result)

    def test_retained_newer_revenue_history_updates_card_and_alias(self):
        old_growth = OpenDataMetric(value=20, source="issuer", tier="exact_public_fact", as_of="2026-06-30", notes="Reported")
        current_growth = old_growth.model_copy(update={"value": 10, "as_of": "2025-06-30"})
        previous = OpenDataSnapshot(ticker="TEST", historical_series={"quarterly_revenue": [OpenDataPeriodMetrics(period="FY2026 Q2", as_of="2026-06-30", metrics={"revenue_growth_yoy": old_growth})]})
        current = OpenDataSnapshot(ticker="TEST", business_health={"revenue_growth_yoy": current_growth}, metrics={"revenue_growth_yoy": current_growth})
        result = retain_verified_history(current, previous)
        self.assertEqual(result.business_health["revenue_growth_yoy"], old_growth)
        self.assertEqual(result.metrics["revenue_growth_yoy"], old_growth)
        self.assert_consistent(result)

    def test_snapshot_fallback_fills_current_growth_without_overriding_sec_revenue(self):
        def row(value, year):
            return {"val": value, "start": f"{year}-04-01", "end": f"{year}-06-30", "filed": f"{year}-06-30", "form": "YF-QUARTER", "fp": "Q2", "fy": year}
        vendor = {"facts": {"yfinance": {"RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [row(100, 2025), row(999, 2026)]}}}}}
        provider = OpenDataProvider()
        with patch.object(provider, "resolve_company_metadata", return_value={"cik": 123}), patch.object(provider, "fetch_companyfacts", return_value=primary_facts()), patch.object(provider, "fetch_price_history", return_value=[]), patch.object(provider, "fetch_latest_price", return_value=None), patch.object(provider, "fetch_forward_pe_estimate", return_value=None), patch.object(provider, "fetch_market_cap_estimate", return_value=None), patch.object(provider, "fetch_next_earnings_release", return_value=None), patch.object(provider, "fetch_company_context", return_value=None), patch.object(provider, "fetch_statement_currency_rates", return_value={}), patch.object(provider, "fetch_yfinance_companyfacts", return_value=vendor):
            snapshot = provider.get_open_data_snapshot("TEST")
        self.assertAlmostEqual(snapshot.business_health["revenue_growth_yoy"].value, 30)
        latest = snapshot.historical_series["quarterly_revenue"][-1]
        self.assertEqual(latest.metrics["revenue"].value, 130)
        self.assertIn("sec_companyfacts", latest.metrics["revenue"].source)

    def test_daily_nibe_discovery_does_not_download_missing_old_reports(self):
        seed = json.loads((ROOT / "data/stocks/issuer_facts/NIBE-B.ST.json").read_text())
        seed["reports"] = [r for r in seed["reports"] if r["year"] != 2024]
        html = '<tr><div class="mfn-archive-event-date">2025-02-14</div><a href="https://issuer/old.pdf" title="Report Q4 2024"></a></tr><tr><div class="mfn-archive-event-date">2026-08-21</div><a href="https://issuer/latest.pdf" title="Report Q2 2026"></a></tr>'
        calls = []
        def get(url, **kwargs):
            calls.append(url)
            return SimpleNamespace(text=html)
        provider = SimpleNamespace(request_timeout=1, _get=get)
        result, notes = refresh_nibe_reports(provider, seed)
        self.assertEqual(result, seed)
        self.assertFalse(notes)
        self.assertEqual(calls, ["https://www.nibegroup.com/report-archive"])

    def test_secondary_currency_mismatch_is_rejected(self):
        vendor = {"facts": {"yfinance": {"RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"ARS": [{"val": 999}]}}}}}
        with patch.object(OpenDataProvider, "fetch_yfinance_companyfacts", return_value=vendor):
            facts, note = OpenDataProvider()._supplement_sec_companyfacts("YPF", {}, primary_facts())
        self.assertIsNone(facts)
        self.assertIn("USD reporting currency", note)

    def test_calendar_fallback_excludes_eps_and_adr_share_counts(self):
        vendor = {"facts": {"yfinance": {
            "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [{"val": 100}]}},
            "EarningsPerShareDiluted": {"units": {"USD/shares": [{"val": 5}]}},
            "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": [{"val": 10}]}},
        }}}
        original = primary_facts()
        with patch.object(OpenDataProvider, "fetch_yfinance_companyfacts", return_value=vendor):
            facts, _ = OpenDataProvider()._supplement_sec_companyfacts("TEST", {}, original)
        self.assertEqual(list(facts["facts"]["yfinance"]), ["RevenueFromContractWithCustomerExcludingAssessedTax"])
        self.assertNotIn("yfinance", original["facts"])

    def test_noncalendar_fiscal_periods_are_not_guessed(self):
        primary = primary_facts()
        primary["facts"]["us-gaap"]["RevenueFromContractWithCustomerExcludingAssessedTax"]["units"]["USD"][1]["fp"] = "Q3"
        with patch.object(OpenDataProvider, "fetch_yfinance_companyfacts") as fetch:
            facts, note = OpenDataProvider()._supplement_sec_companyfacts("CRM", {}, primary)
        self.assertIsNone(facts)
        self.assertIn("fiscal periods", note)
        fetch.assert_not_called()

    def test_issuer_workbook_outage_tries_yahoo(self):
        vendor = {"facts": {"yfinance": {}}}
        with patch.object(OpenDataProvider, "fetch_issuer_workbook_companyfacts", side_effect=ValueError("invalid workbook")), patch.object(OpenDataProvider, "fetch_yfinance_companyfacts", return_value=vendor) as fetch:
            facts = OpenDataProvider().fetch_non_sec_companyfacts("AXFO.ST", {})
        fetch.assert_called_once()
        self.assertIn("Issuer workbook unavailable", facts["collection_notes"][0])

    def test_failed_nibe_archive_keeps_all_verified_history(self):
        seed = json.loads((ROOT / "data/stocks/issuer_facts/NIBE-B.ST.json").read_text())
        provider = SimpleNamespace(request_timeout=1, _get=lambda *a, **k: (_ for _ in ()).throw(ValueError("unavailable")))
        result, notes = refresh_nibe_reports(provider, seed)
        self.assertEqual(result, seed)
        self.assertIn("retained verified history", notes[0])

    def test_invalid_new_nibe_pdf_does_not_mark_report_imported(self):
        seed = json.loads((ROOT / "data/stocks/issuer_facts/NIBE-B.ST.json").read_text())
        html = '<tr><div class="mfn-archive-event-date">2026-11-17</div><a href="https://issuer/Q3.pdf" title="Report Q3 2026"></a></tr>'
        responses = iter([SimpleNamespace(text=html), SimpleNamespace(content=b"invalid")])
        provider = SimpleNamespace(request_timeout=1, _get=lambda *a, **k: next(responses))
        result, notes = refresh_nibe_reports(provider, seed)
        self.assertEqual(result, seed)
        self.assertIn("could not be imported", notes[0])

    def test_new_nibe_report_is_merged_for_the_next_daily_run(self):
        seed = json.loads((ROOT / "data/stocks/issuer_facts/NIBE-B.ST.json").read_text())
        html = '<tr><div class="mfn-archive-event-date">2026-11-17</div><a href="https://issuer/Q3.pdf" title="Report Q3 2026"></a></tr>'
        responses = iter([SimpleNamespace(text=html), SimpleNamespace(content=b"pdf")])
        provider = SimpleNamespace(request_timeout=1, _get=lambda *a, **k: next(responses))
        with patch("app.entry_engine.providers.nibe_reports.parse_nibe_report", return_value={"facts": {"issuer": {}}}):
            result, notes = refresh_nibe_reports(provider, seed)
        self.assertFalse(notes)
        self.assertEqual(result["reports"][-1]["quarter"], 3)
        self.assertEqual(len(seed["reports"]), 4)

    def test_thin_refresh_retains_old_history_and_does_not_restore_invalid_peg(self):
        metric = OpenDataMetric(value=10, source="issuer", tier="exact_public_fact", as_of="2025-06-30", notes="Reported")
        old = OpenDataSnapshot(ticker="TEST", business_health={"revenue_growth_yoy": metric}, valuation={"peg": metric}, historical_series={"quarterly_revenue": [OpenDataPeriodMetrics(period="FY2025 Q2", as_of="2025-06-30", metrics={"revenue": metric})]})
        current = OpenDataSnapshot(ticker="TEST", valuation={"peg": metric.model_copy(update={"value": None, "notes": "PEG is not meaningful with negative EPS growth"})})
        result = retain_verified_history(current, old)
        self.assertEqual(len(result.historical_series["quarterly_revenue"]), 1)
        self.assertEqual(result.business_health["revenue_growth_yoy"].value, 10)
        self.assertIsNone(result.valuation["peg"].value)


if __name__ == "__main__":
    unittest.main()
