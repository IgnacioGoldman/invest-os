from __future__ import annotations

from pathlib import Path
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.entry_engine.open_data_metrics import compute_open_data_snapshot
from app.entry_engine.providers.nibe_reports import parse_nibe_report, merge_nibe_facts
from app.entry_engine.providers.open_data_provider import OpenDataProvider
from app.services.revenue_growth_momentum import calculate_revenue_growth_momentum


class NibeReportTests(unittest.TestCase):
    def test_backfill_has_comparable_history_and_prefers_issuer_to_vendor(self):
        issuer = json.loads((ROOT / "data/stocks/issuer_facts/NIBE-B.ST.json").read_text())
        facts = {**issuer, "facts": {**issuer["facts"], "yfinance": {
            "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"SEK": [{
                "val": 1, "start": "2026-04-01", "end": "2026-06-30", "filed": "2026-06-30",
                "form": "YF-QUARTER", "fp": "Q2", "fy": 2026,
            }]}}
        }}}
        snapshot = compute_open_data_snapshot(ticker="NIBE-B.ST", cik=None, companyfacts=facts, price=None)
        quarters = {r.period: r for r in snapshot.historical_series["quarterly_revenue"]}
        self.assertEqual(quarters["FY2026 Q2"].metrics["revenue"].value, 10_849_000_000)
        self.assertAlmostEqual(quarters["FY2026 Q2"].metrics["revenue_growth_yoy"].value, (10849 / 10082 - 1) * 100)
        self.assertAlmostEqual(quarters["FY2025 Q4"].metrics["revenue_growth_yoy"].value, (11000 / 11025 - 1) * 100)
        self.assertIn("https://storage.mfn.se/", quarters["FY2026 Q2"].metrics["revenue"].source)
        self.assertNotEqual(calculate_revenue_growth_momentum(snapshot.model_dump(mode="json"))["label"], "Unclear")
        fundamentals = {r.period: r for r in snapshot.historical_series["quarterly_fundamentals"]}
        self.assertEqual(fundamentals["FY2024 Q1"].metrics["operating_income"].value, -579_000_000)
        self.assertEqual(snapshot.business_health["free_cash_flow"].value, 796_000_000)
        self.assertEqual(snapshot.business_health["fcf_margin"].as_of, "2026-06-30")

    def test_redesigned_table_never_imports_adjusted_profit(self):
        text = """LAST NINE QUARTERS
Q1 2026 Q2 2026 Q1 2025 Q2 2025 Q3 2025 Q4 2025 Q2 2024 Q3 2024 Q4 2024
NET SALES
GROUP TOTAL SEK m 9,650 10,849 9,673 10,082 10,086 11,000 10,035 9,967 11,025
OPERATING PROFIT
GROUP TOTAL SEK m 868 1,232 782 944 1,139 1,260 669 912 1,669
ADJUSTED OPERATING PROFIT
GROUP TOTAL SEK m 868 1,232 782 944 1,139 1,438 669 912 1,129
"""
        page = SimpleNamespace(extract_text=lambda **kwargs: text)
        with patch("app.entry_engine.providers.nibe_reports.PdfReader", return_value=SimpleNamespace(pages=[page])):
            parsed = parse_nibe_report(b"", year=2026, quarter=2, filed="2026-08-21", url="https://issuer/report.pdf")
            profits = parsed["facts"]["issuer"]["OperatingIncomeLoss"]["units"]["SEK"]
            self.assertEqual(next(r["val"] for r in profits if r["end"] == "2025-12-31"), 1_260_000_000)
            text = text.replace("9,650 10,849", "9,650")
            with self.assertRaisesRegex(ValueError, "do not align"):
                parse_nibe_report(b"", year=2026, quarter=2, filed="2026-08-21", url="https://issuer/report.pdf")

    def test_merge_keeps_latest_restatement_and_prior_history(self):
        def facts(value, end, filed):
            return {"facts": {"issuer": {"Revenue": {"units": {"SEK": [{"val": value, "end": end, "filed": filed}]}}}}}
        target = facts(10, "2025-06-30", "2025-08-22")
        merge_nibe_facts(target, facts(11, "2025-06-30", "2026-08-21"))
        merge_nibe_facts(target, facts(9, "2025-06-30", "2025-08-22"))
        merge_nibe_facts(target, facts(12, "2026-06-30", "2026-08-21"))
        self.assertEqual([r["val"] for r in target["facts"]["issuer"]["Revenue"]["units"]["SEK"]], [11, 12])

    def test_regular_collector_preserves_curated_history(self):
        with patch.object(OpenDataProvider, "fetch_yfinance_companyfacts", return_value={"facts": {"yfinance": {}}}), patch("app.entry_engine.providers.nibe_reports.refresh_nibe_reports", side_effect=lambda provider, seed: (seed, [])), patch.object(Path, "write_text"):
            facts = OpenDataProvider().fetch_non_sec_companyfacts("NIBE-B.ST", {})
        self.assertGreater(len(facts["facts"]["issuer"]["RevenueFromContractWithCustomerExcludingAssessedTax"]["units"]["SEK"]), 10)


if __name__ == "__main__":
    unittest.main()
