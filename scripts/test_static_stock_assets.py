"""Ensure lightweight screening never truncates durable financial histories."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch

from test_revenue_growth_momentum import snapshot
from app.services.revenue_growth_momentum import calculate_revenue_growth_momentum
from app.services.static_stock_assets import load_full_stock_rows, stock_summary, write_stock_assets
from refresh_static_prices import hydrate_deployed_data
from test_refresh_static_prices import FakeSession
from validate_static_stock_refresh import _validate_stock_details


def full_snapshot():
    row = snapshot([8, 9, 10, 12, 13, 14])
    row.update(ticker="TEST", generated_at="2026-10-17T12:00:00Z", business_health={"revenue_growth_yoy": {"value": 14}},
               price_opportunity={"current_price": {"value": 20}}, valuation={"forward_pe": {"value": 15}}, metrics={"cash": {"value": 100}},
               company_context={"recent_filings": [{"form": "10-Q"}] * 10},
               industry_relative_strength={"value": 10, "chart": [{"date": "2026-10-16", "industry": 150}]})
    row["historical_series"]["annual_fundamentals"] = [{"period": str(y), "as_of": f"{y}-12-31", "metrics": {}} for y in range(2000, 2026)]
    row["historical_series"]["valuation_history"] = deepcopy(row["historical_series"]["annual_fundamentals"])
    return row


class StaticStockAssetsTests(unittest.TestCase):
    def test_screening_preserves_current_metrics_and_momentum(self):
        full = full_snapshot()
        summary = stock_summary(full)
        self.assertEqual(calculate_revenue_growth_momentum(full), calculate_revenue_growth_momentum(summary))
        for key in ("business_health", "price_opportunity", "valuation", "metrics"):
            self.assertEqual(summary[key], full[key])
        self.assertEqual(summary["industry_relative_strength"]["value"], 10)
        self.assertEqual(summary["industry_relative_strength"]["chart"], [])
        self.assertEqual(len(full["industry_relative_strength"]["chart"]), 1)
        self.assertEqual(len(summary["historical_series"]["annual_fundamentals"]), 2)

    def test_details_round_trip_preserves_all_history(self):
        full = full_snapshot()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_stock_assets(root, [full])
            self.assertIn("screening", load_full_stock_rows(root)[0])
            self.assertEqual([{k:v for k,v in row.items() if k != "screening"} for row in load_full_stock_rows(root)], [full])
            summary = json.loads((root / "open-data/stocks.json").read_text())[0]
            self.assertIn("detail_path", summary)
            self.assertEqual(len(load_full_stock_rows(root)[0]["historical_series"]["annual_fundamentals"]), 26)
            with self.assertRaises(ValueError):
                write_stock_assets(root, [summary])

    def test_release_validation_requires_matching_full_details(self):
        full = full_snapshot()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_stock_assets(root, [full])
            summary = stock_summary(full)
            errors = []
            _validate_stock_details("TEST", summary, root, errors)
            self.assertEqual(errors, [])
            wrong = deepcopy(full)
            wrong["business_health"]["revenue_growth_yoy"]["value"] = 999
            (root / "open-data/snapshots/TEST.json").write_text(json.dumps(wrong))
            _validate_stock_details("TEST", summary, root, errors)
            self.assertTrue(any("business_health" in e for e in errors))
            errors.clear()
            (root / "open-data/snapshots/TEST.json").unlink()
            _validate_stock_details("TEST", summary, root, errors)
            self.assertTrue(any("missing or invalid" in e for e in errors))

    def test_validation_rejects_different_research_metrics_in_summary_and_detail(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            write_stock_assets(root,[full_snapshot()])
            summary=json.loads((root/"open-data/stocks.json").read_text())[0]
            summary["screening"]["metrics"]["revenue"]["value"]=999
            errors=[]
            _validate_stock_details("TEST",summary,root,errors)
            self.assertTrue(any("screening projection" in e for e in errors))

    def test_deployed_fallback_downloads_full_snapshot(self):
        full = full_snapshot()
        routes = {"open-data/stocks.json": [stock_summary(full)], "stocks/universe.json": [{"symbol": "TEST"}],
                  "open-data/snapshots/TEST.json": full, "open-data/price-history/TEST.json": []}
        with TemporaryDirectory() as directory, patch("refresh_static_prices.requests.Session", side_effect=lambda: FakeSession(routes)):
            rows = hydrate_deployed_data("https://example.com/data", Path(directory), ["TEST"], cache_bust="test", workers=2)
            self.assertEqual(rows, [full])

    def test_local_revenue_repair_preserves_its_own_full_snapshot(self):
        deployed = full_snapshot()
        local = deepcopy(deployed)
        local.update(generated_at="2026-10-17T13:00:00Z", revenue_history_version=2)
        local["historical_series"]["quarterly_revenue"][-1]["metrics"]["revenue_growth_yoy"]["value"] = 99
        routes = {"open-data/stocks.json": [stock_summary(deployed)], "stocks/universe.json": [{"symbol": "TEST"}],
                  "open-data/snapshots/TEST.json": deployed, "open-data/price-history/TEST.json": []}
        with TemporaryDirectory() as directory, patch("refresh_static_prices.requests.Session", side_effect=lambda: FakeSession(routes)):
            root = Path(directory)
            write_stock_assets(root, [local])
            rows = hydrate_deployed_data("https://example.com/data", root, ["TEST"], cache_bust="test", workers=2)
            self.assertIn("screening", rows[0])
            self.assertEqual([{k:v for k,v in row.items() if k != "screening"} for row in rows], [local])

    def test_mismatched_deployed_detail_fails_instead_of_persisting_wrong_data(self):
        full = full_snapshot()
        wrong = {**full, "ticker": "OTHER"}
        routes = {"open-data/stocks.json": [stock_summary(full)], "stocks/universe.json": [{"symbol": "TEST"}],
                  "open-data/snapshots/TEST.json": wrong}
        with TemporaryDirectory() as directory, patch("refresh_static_prices.requests.Session", side_effect=lambda: FakeSession(routes)):
            with self.assertRaises(ValueError):
                hydrate_deployed_data("https://example.com/data", Path(directory), ["TEST"], cache_bust="test", workers=1)


if __name__ == "__main__":
    unittest.main()
