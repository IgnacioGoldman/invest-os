from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import open_data_poc
from refresh_static_prices import main as refresh_prices_main, refresh_prices, refresh_snapshot_prices
from app.entry_engine.open_data_metrics import compute_open_data_snapshot
from app.entry_engine.open_data_models import HistoricalPricePoint, LatestPrice, OpenDataMetric
from app.entry_engine.providers.open_data_provider import JsonFileCache, OpenDataProvider
from app.services.stock_data_quality import retain_verified_history
from app.services.storage import (
    connect, load_stock_open_data_snapshot, load_stock_price_history,
    replace_stock_open_data_snapshot, replace_stock_price_history,
)
from export_static_site_data import _load_price_history as exported_history


def metric(value, source="test", as_of="2026-06-30"):
    return OpenDataMetric(value=value, source=source, as_of=as_of, tier="computed_from_public_facts", notes="Test input.")


def facts(*, income=100, currency="USD"):
    values = {
        "Revenues": 1000, "NetIncomeLoss": income,
        "NetCashProvidedByUsedInOperatingActivities": 100,
        "PaymentsToAcquirePropertyPlantAndEquipment": 20,
        "OperatingIncomeLoss": 150, "DepreciationDepletionAndAmortization": 50,
        "LongTermDebtCurrent": 50, "LongTermDebtNoncurrent": 250,
        "CashAndCashEquivalentsAtCarryingValue": 100,
        "WeightedAverageNumberOfDilutedSharesOutstanding": 10,
    }
    return {"entityName": "Test", "facts": {"us-gaap": {
        key: {"units": {"shares" if "SharesOutstanding" in key else currency: [{
            "val": value, "start": "2025-01-01", "end": "2025-12-31",
            "fy": 2025, "fp": "FY", "form": "10-K", "filed": "2026-02-01",
        }]}} for key, value in values.items()
    }}}


def snapshot(*, currency="USD", statement_currency="USD", adr_ratio=1):
    row = compute_open_data_snapshot(
        ticker="TEST", cik=123, companyfacts=facts(currency=statement_currency),
        price=LatestPrice(ticker="TEST", price=100, currency=currency, source="test", as_of="2026-10-12"),
        price_history=[HistoricalPricePoint(date="2026-10-12", close=100, source="test")],
        adr_ratio=adr_ratio, statement_currency_rates={statement_currency: metric(2, "fx:test")},
    )
    growth = metric(25)
    return row.model_copy(update={
        "business_health": {**row.business_health, "eps_cagr_3y": growth},
        "metrics": {**row.metrics, "eps_cagr_3y": growth},
    })


NEW_HISTORY = [HistoricalPricePoint(date="2026-10-13", close=200, low=190, high=210, source="test")]


class RefreshSeparationTests(unittest.TestCase):
    def test_prices_recalculate_all_ratios_and_aliases_without_mutating_facts(self):
        old = snapshot()
        updated = refresh_snapshot_prices(old, NEW_HISTORY)
        self.assertEqual(updated.business_health, old.business_health)
        self.assertEqual(updated.historical_series, old.historical_series)
        for key in ("net_income_ttm", "revenue_ttm", "free_cash_flow_ttm", "shares_diluted"):
            self.assertEqual(updated.metrics[key], old.metrics[key])
        expected = {"pe": 20, "price_to_sales": 2, "fcf_yield": 4, "ev_to_ebitda": 11, "peg": 0.8, "forward_pe": 16}
        for key, value in expected.items():
            self.assertAlmostEqual(updated.valuation[key].value, value, msg=key)
            self.assertEqual(updated.valuation[key].as_of, "2026-10-13")
        self.assertEqual(updated.metrics["market_cap"].value, 2000)
        self.assertEqual(updated.valuation["pe"], updated.metrics["pe_ttm"])
        self.assertEqual(updated.valuation["peg"], updated.metrics["peg_proxy"])
        self.assertEqual(updated.valuation["ev_to_ebitda"], updated.metrics["ev_to_ebitda_proxy"])

    def test_legacy_snapshots_upgrade_without_sec_and_preserve_adr_basis(self):
        for adr_ratio in (1, 2, 5):
            old = snapshot(adr_ratio=adr_ratio)
            legacy = old.model_copy(update={
                "price_currency": None, "valuation_inputs": {},
                "metrics": {k: v for k, v in old.metrics.items() if k not in {"ebitda_proxy", "enterprise_value_proxy"}},
            })
            updated = refresh_snapshot_prices(legacy, NEW_HISTORY)
            self.assertAlmostEqual(updated.metrics["market_cap"].value, 2000 / adr_ratio)
            self.assertAlmostEqual(updated.valuation["pe"].value, 20 / adr_ratio)
            self.assertAlmostEqual(updated.valuation["ev_to_ebitda"].value, (2000 / adr_ratio + 200) / 200)
            self.assertTrue(updated.valuation_inputs)

    def test_saved_fx_and_legacy_fx_bridge_use_listing_currency(self):
        old = snapshot(statement_currency="EUR")
        legacy = old.model_copy(update={
            "price_currency": None, "valuation_inputs": {},
            "metrics": {k: v for k, v in old.metrics.items() if k not in {"ebitda_proxy", "enterprise_value_proxy"}},
        })
        for row in (old, legacy):
            updated = refresh_snapshot_prices(row, NEW_HISTORY)
            self.assertAlmostEqual(updated.valuation["pe"].value, 10)
            self.assertAlmostEqual(updated.valuation["fcf_yield"].value, 8)
            self.assertAlmostEqual(updated.valuation["ev_to_ebitda"].value, 6)

    def test_yahoo_forward_eps_updates_forward_pe_and_loss_invalidates_it(self):
        old = snapshot()
        for eps, expected in ((8, 25), (0, None), (-2, None)):
            updated = refresh_snapshot_prices(old, NEW_HISTORY, forward_eps=metric(eps, "yfinance:forwardEps"))
            self.assertEqual(updated.valuation["forward_pe"].value, expected)
            self.assertEqual(updated.valuation_inputs["forward_eps_public"].value, eps)

    def test_yahoo_eps_requires_verified_matching_currency(self):
        provider = OpenDataProvider(cache=SimpleNamespace())
        with patch.object(provider, "_fetch_yfinance_info", return_value={"forwardEps": 8, "currency": "EUR"}):
            self.assertIsNone(provider.fetch_forward_eps_estimate("TEST", currency="USD"))
            self.assertEqual(provider.fetch_forward_eps_estimate("TEST", currency="EUR").value, 8)

    def test_sec_request_guard_fails_before_any_http_request(self):
        session = Mock()
        provider = OpenDataProvider(cache=SimpleNamespace(), session=session, allow_sec_requests=False)
        for url in ("https://www.sec.gov/files/company_tickers.json", "https://data.sec.gov/submissions/CIK1.json"):
            with self.assertRaisesRegex(RuntimeError, "SEC requests are disabled"):
                provider._get(url)
        session.get.assert_not_called()

    def test_entire_price_refresh_updates_db_and_exports_with_sec_disabled(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with connect(root / "db") as conn:
                replace_stock_open_data_snapshot(conn, snapshot())
                replace_stock_price_history(conn, "TEST", [HistoricalPricePoint(date="2026-10-12", close=100, low=90, source="test")])
                conn.commit()
            with (
                patch.object(OpenDataProvider, "fetch_price_history_since", return_value=NEW_HISTORY),
                patch.object(OpenDataProvider, "fetch_next_earnings_release", return_value=None),
                patch.object(OpenDataProvider, "fetch_forward_eps_estimate", return_value=metric(8)),
                patch.object(OpenDataProvider, "_sec_get_json", side_effect=AssertionError("SEC called")) as sec,
                patch.object(OpenDataProvider, "fetch_companyfacts", side_effect=AssertionError("Facts called")) as companyfacts,
                patch.object(OpenDataProvider, "get_open_data_snapshot", side_effect=AssertionError("Full collection called")) as collection,
            ):
                report = refresh_prices([], root / "static", ["TEST"], workers=1, db_data_dir=root / "db")
            self.assertEqual(report["failed_count"], 0)
            sec.assert_not_called(); companyfacts.assert_not_called(); collection.assert_not_called()
            with connect(root / "db") as conn:
                saved = load_stock_open_data_snapshot(conn, "TEST")
            self.assertEqual(saved.valuation["pe"].value, 20)
            self.assertEqual(saved.valuation["forward_pe"].value, 25)
            self.assertTrue((root / "static/open-data/stocks.json").exists())

    def test_cli_uses_complete_sqlite_baseline_even_if_pages_is_unreachable(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            universe = root / "universe.json"
            universe.write_text(json.dumps({"tickers": ["TEST"]}))
            with connect(root / "db") as conn:
                replace_stock_open_data_snapshot(conn, snapshot())
                replace_stock_price_history(conn, "TEST", [HistoricalPricePoint(date="2026-10-12", close=100, low=90, source="test")])
                conn.commit()
            with (
                patch("sys.argv", ["refresh_static_prices.py", "--db-data-dir", str(root / "db"),
                    "--data-dir", str(root / "static"), "--universe", str(universe), "--output", str(root / "report.json")]),
                patch("refresh_static_prices.hydrate_deployed_data", side_effect=AssertionError("Pages is unavailable")) as download,
                patch.object(OpenDataProvider, "fetch_price_history_since", return_value=NEW_HISTORY),
                patch.object(OpenDataProvider, "fetch_next_earnings_release", return_value=None),
                patch.object(OpenDataProvider, "fetch_forward_eps_estimate", return_value=None),
                patch("builtins.print"),
            ):
                self.assertEqual(refresh_prices_main(), 0)
            download.assert_not_called()
            self.assertEqual(json.loads((root / "report.json").read_text())["failed_count"], 0)

    def test_static_export_uses_sqlite_instead_of_an_unrelated_cached_download(self):
        with TemporaryDirectory() as directory:
            with connect(Path(directory)) as conn:
                replace_stock_price_history(conn, "TEST", NEW_HISTORY)
                with patch("export_static_site_data.load_cached_price_history", side_effect=AssertionError("Cache accessed")):
                    self.assertEqual(exported_history(conn, "TEST")[-1]["close"], 200)

    def test_fundamentals_use_saved_prices_and_never_write_cached_candles(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            old = snapshot()
            history = [HistoricalPricePoint(date="2026-10-12", close=100, source="test")]
            with connect(root) as conn:
                replace_stock_open_data_snapshot(conn, old)
                replace_stock_price_history(conn, "TEST", history)
                conn.commit()
            provider = OpenDataProvider(cache=JsonFileCache(root / "cache"))
            with (
                patch("open_data_poc.get_settings", return_value=SimpleNamespace(data_dir=root)),
                patch("open_data_poc.load_cached_price_history", side_effect=AssertionError("Cached candles accessed")),
                patch("open_data_poc.save_stock_snapshot_to_db", side_effect=AssertionError("Cached candles persisted")),
                patch.object(provider, "resolve_company_metadata", return_value={"cik": 123, "currency": "USD"}),
                patch.object(provider, "fetch_companyfacts", return_value=facts(income=200)),
                patch.object(provider, "fetch_company_context", return_value=None),
                patch.object(provider, "fetch_statement_currency_rates", return_value={}),
                patch.object(provider, "_supplement_sec_companyfacts", return_value=(None, "No fallback")),
                patch.object(provider, "fetch_price_history", side_effect=AssertionError("New history fetched")),
                patch.object(provider, "fetch_latest_price", side_effect=AssertionError("New price fetched")),
                patch.object(provider, "fetch_market_cap_estimate", side_effect=AssertionError("New cap fetched")),
                patch.object(provider, "fetch_forward_pe_estimate", side_effect=AssertionError("New multiple fetched")),
                patch.object(provider, "fetch_next_earnings_release", side_effect=AssertionError("Calendar fetched")),
            ):
                result = open_data_poc._collect_ticker(provider, "TEST", True, reuse_saved_prices=True)
            self.assertIsNotNone(result["saved_to"])
            with connect(root) as conn:
                updated = load_stock_open_data_snapshot(conn, "TEST")
                self.assertEqual(load_stock_price_history(conn, "TEST"), history)
            self.assertEqual(updated.price_opportunity, old.price_opportunity)
            self.assertEqual(updated.metrics["current_price"], old.metrics["current_price"])
            self.assertEqual(updated.metrics["net_income_ttm"].value, 200)
            self.assertEqual(updated.valuation["pe"].value, 5)

    def test_missing_saved_prices_do_not_silently_fetch_them(self):
        provider = Mock()
        with TemporaryDirectory() as directory, patch("open_data_poc.get_settings", return_value=SimpleNamespace(data_dir=Path(directory))):
            with self.assertRaisesRegex(ValueError, "saved snapshot is required"):
                open_data_poc._collect_ticker(provider, "TEST", True, reuse_saved_prices=True)
        provider.get_open_data_snapshot.assert_not_called()

    def test_retained_fcf_bundle_keeps_matching_valuation_inputs(self):
        old = snapshot()
        thin = compute_open_data_snapshot(ticker="TEST", cik=123, companyfacts={}, price=None)
        updated = retain_verified_history(thin, old)
        self.assertEqual(updated.valuation_inputs["free_cash_flow"], old.valuation_inputs["free_cash_flow"])
        self.assertEqual(updated.valuation_inputs["revenue"], old.valuation_inputs["revenue"])

    def test_repeated_refreshes_keep_the_original_share_and_currency_basis(self):
        old = snapshot(statement_currency="EUR", adr_ratio=2)
        first = refresh_snapshot_prices(old, NEW_HISTORY)
        second = refresh_snapshot_prices(first, [NEW_HISTORY[-1].model_copy(update={"date": "2026-10-14", "close": 400})])
        self.assertEqual(second.metrics["market_cap"].value, 2000)
        self.assertEqual(second.valuation["pe"].value, 10)
        self.assertEqual(second.valuation_inputs["listing_shares"], old.valuation_inputs["listing_shares"])
        self.assertEqual(second.valuation_inputs["net_income"], old.valuation_inputs["net_income"])


if __name__ == "__main__":
    unittest.main()
