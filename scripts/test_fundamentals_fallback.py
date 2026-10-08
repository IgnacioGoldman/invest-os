from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.entry_engine.open_data_models import OpenDataMetric, OpenDataSnapshot, OpenDataPeriodMetrics
from app.entry_engine.providers.open_data_provider import OpenDataProvider
from app.entry_engine.providers.nibe_reports import refresh_nibe_reports
from app.services.stock_data_quality import retain_verified_history


def primary_facts():
    return {"facts": {"us-gaap": {"RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
        {"val": 400, "start": "2025-01-01", "end": "2025-12-31", "filed": "2026-02-01", "form": "10-K", "fp": "FY", "fy": 2025},
        {"val": 130, "start": "2026-04-01", "end": "2026-06-30", "filed": "2026-08-01", "form": "10-Q", "fp": "Q2", "fy": 2026},
    ]}}}}}


class FundamentalsFallbackTests(unittest.TestCase):
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
