from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.entry_engine.open_data_models import HistoricalPricePoint, OpenDataMetric, OpenDataSnapshot
from app.services.industry_strength import (
    BENCHMARK, BENCHMARK_FILE, build_industry_strength, load_benchmark,
    refresh_benchmark, rebuild_saved_industry_strength, strength_label,
)
from app.services.storage import connect, load_stock_open_data_snapshot, replace_stock_open_data_snapshot, replace_stock_price_history
from export_static_site_data import export_static_site_data
from refresh_static_prices import refresh_prices


def fixture():
    end = datetime.now(timezone.utc).date()
    while end.weekday() > 4:
        end -= timedelta(days=1)
    try:
        start = end.replace(year=end.year - 1)
    except ValueError:
        start = end.replace(year=end.year - 1, day=28)
    while start.weekday() > 4:
        start -= timedelta(days=1)
    days = [start + timedelta(days=i) for i in range((end - start).days + 1) if (start + timedelta(days=i)).weekday() < 5]

    def history(gain):
        return [HistoricalPricePoint(date=d.isoformat(), close=100 + gain * i / (len(days) - 1), source="test") for i, d in enumerate(days)]

    rows, histories, entries = [], {}, {}
    for i, gain in enumerate([18, 10, 20, 30, 40, 50]):
        symbol = "MU" if i == 0 else f"P{i}"
        rows.append(OpenDataSnapshot(ticker=symbol, cik=i + 1, sector="Technology", industry="Semiconductors", price_currency="USD",
            price_opportunity={"current_price": OpenDataMetric(value=100 + gain, source="test", tier="exact_public_fact", as_of=end.isoformat(), notes="Close.")}))
        histories[symbol] = history(gain)
        entries[symbol] = {"sector": "Technology", "industry": "Semiconductors", "original_sector": "Technology", "original_industry": "Semiconductors", "market": "US", "currency": "USD", "sources": []}
    registry = {"source": "test review", "reviewed_at": end.isoformat(), "stocks": entries}
    return rows, histories, history(15), registry, end


class IndustryStrengthTests(unittest.TestCase):
    def setUp(self):
        self.rows, self.histories, self.market, self.registry, self.today = fixture()

    def build(self, rows=None, histories=None, market=None, today=None):
        return build_industry_strength(rows if rows is not None else self.rows,
            histories if histories is not None else self.histories, market if market is not None else self.market,
            self.registry, today=today or self.today)[0].industry_relative_strength

    def test_uses_industry_minus_market_and_keeps_stock_comparison_separate(self):
        result = self.build()
        self.assertAlmostEqual(result["value"], 15)
        self.assertAlmostEqual(result["industry_return"], 30)
        self.assertAlmostEqual(result["stock_return"], 18)
        self.assertAlmostEqual(result["stock_vs_industry"], -12)
        self.assertEqual(result["label"], "Ahead of market")
        self.assertEqual(result["peer_count"], 5)
        self.assertNotIn("MU", [p["ticker"] for p in result["peers"]])
        self.assertEqual(result["chart"][0]["industry"], 100)
        self.assertAlmostEqual(result["chart"][-1]["industry"], 130)
        self.assertAlmostEqual(result["chart"][-1]["market"], 115)

    def test_current_prices_rebuild_previous_comparison(self):
        old = self.build()
        self.histories["P1"][-1] = self.histories["P1"][-1].model_copy(update={"close": 160})
        self.rows[0].industry_relative_strength = old
        new = self.build()
        self.assertAlmostEqual(new["value"], 25)
        self.assertNotEqual(old["value"], new["value"])

    def test_peer_share_price_does_not_change_equal_weight(self):
        self.histories["P1"] = [p.model_copy(update={"close": p.close * 100}) for p in self.histories["P1"]]
        self.assertAlmostEqual(self.build()["industry_return"], 30)

    def test_tags_have_exact_nonoverlapping_boundaries(self):
        for value, label in [(5, "Ahead of market"), (-5, "Behind market"), (4.999, "In line with market"), (-4.999, "In line with market"), (0, "In line with market"), (None, "Unclear")]:
            self.assertEqual(strength_label(value), label)

    def test_positive_gap_can_describe_a_falling_industry(self):
        market = [p.model_copy(update={"close": 100 - 40 * i / (len(self.market) - 1)}) for i, p in enumerate(self.market)]
        histories = {t: [p.model_copy(update={"close": 100 - 20 * i / (len(points) - 1)}) for i, p in enumerate(points)] for t, points in self.histories.items()}
        result = self.build(histories=histories, market=market)
        self.assertAlmostEqual(result["industry_return"], -20)
        self.assertAlmostEqual(result["value"], 20)
        self.assertEqual(result["label"], "Ahead of market")

    def test_short_history_is_excluded_instead_of_using_since_listing_return(self):
        self.histories["P1"] = self.histories["P1"][-80:]
        result = self.build()
        self.assertIsNone(result["value"])
        self.assertEqual(result["peer_count"], 4)
        self.assertEqual(result["excluded_peers"][0]["ticker"], "P1")
        self.assertIn("at least 5", result["reason"])

    def test_duplicate_issuer_cannot_fill_peer_minimum(self):
        self.rows[-1].cik = self.rows[-2].cik
        result = self.build()
        self.assertIsNone(result["value"])
        self.assertEqual(result["tracked_peer_count"], 4)

    def test_other_share_class_of_selected_stock_is_excluded(self):
        self.rows[-1].cik = self.rows[0].cik
        self.assertEqual(self.build()["peer_count"], 4)

    def test_changed_classification_requires_review(self):
        self.rows[0].industry = "Changed"
        result = self.build()
        self.assertIsNone(result["value"])
        self.assertIn("needs review", result["reason"])

    def test_no_sector_or_universe_fallback_for_small_group(self):
        self.registry["stocks"]["MU"]["industry"] = "Memory chips"
        result = self.build()
        self.assertIsNone(result["value"])
        self.assertEqual(result["peer_count"], 0)

    def test_mismatched_currency_is_excluded(self):
        self.rows[-1].price_currency = "SEK"
        self.assertEqual(self.build()["peer_count"], 4)

    def test_unsupported_market_is_unclear(self):
        self.registry["stocks"]["MU"]["market"] = "SE"
        self.assertIn("not configured", self.build()["reason"])

    def test_missing_or_stale_market_end_cannot_shift_comparison_window(self):
        for market in [[], self.market[:-1]]:
            result = self.build(market=market)
            self.assertIsNone(result["value"])
            self.assertIn("benchmark refresh", result["reason"])

    def test_stale_or_future_stock_prices_are_unclear(self):
        for today in [self.today + timedelta(days=8), self.today - timedelta(days=1)]:
            self.assertIsNone(self.build(today=today)["value"])

    def test_sparse_year_and_nonfinite_endpoint_are_excluded(self):
        for bad in [self.histories["P1"][::2] + self.histories["P1"][-1:],
                    self.histories["P1"][:-1] + [self.histories["P1"][-1].model_copy(update={"close": float("inf")})]]:
            histories = {**self.histories, "P1": bad}
            self.assertIsNone(self.build(histories=histories)["value"])

    def test_outside_industry_never_influences_average(self):
        extra = self.rows[-1].model_copy(update={"ticker": "OTHER", "cik": 100, "industry": "Software"})
        self.registry["stocks"]["OTHER"] = {**self.registry["stocks"]["P5"], "original_industry": "Software", "industry": "Software"}
        self.assertAlmostEqual(self.build(rows=[*self.rows, extra])["value"], 15)

    def test_benchmark_failure_retains_saved_price_history_and_disables_sec(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / BENCHMARK_FILE
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({**BENCHMARK, "return_basis": "price", "prices": [p.model_dump(mode="json") for p in self.market]}))
            before = path.read_text()
            with patch("app.entry_engine.providers.open_data_provider.OpenDataProvider") as provider:
                provider.return_value._fetch_yfinance_history.return_value = []
                result = refresh_benchmark(Path(directory))
            self.assertEqual(result, self.market)
            self.assertEqual(path.read_text(), before)
            self.assertFalse(provider.call_args.kwargs["allow_sec_requests"])

    def test_wrong_benchmark_return_basis_is_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / BENCHMARK_FILE
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({**BENCHMARK, "return_basis": "total_return", "prices": []}))
            self.assertEqual(load_benchmark(Path(directory)), [])

    def test_price_refresh_rebuilds_industry_metric_from_updated_peer_prices(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            benchmark_path = root / BENCHMARK_FILE
            benchmark_path.parent.mkdir(parents=True)
            benchmark_path.write_text(json.dumps({**BENCHMARK, "return_basis": "price", "prices": [p.model_dump(mode="json") for p in self.market]}))
            for row in self.rows:
                path = root / f"open-data/price-history/{row.ticker}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps([p.model_dump(mode="json") for p in self.histories[row.ticker]]))
                row.industry_relative_strength = {"value": 999, "label": "Old comparison"}
            updated = {**self.histories, "P1": [*self.histories["P1"][:-1], self.histories["P1"][-1].model_copy(update={"close": 160})]}
            with (
                patch("app.services.industry_strength.load_classifications", return_value=self.registry),
                patch("refresh_static_prices.fetch_updated_history", side_effect=lambda provider, ticker, baseline: updated[ticker]),
                patch("refresh_static_prices.OpenDataProvider") as provider,
            ):
                provider.return_value.fetch_next_earnings_release.return_value = None
                provider.return_value.fetch_forward_eps_estimate.return_value = None
                report = refresh_prices([r.model_dump(mode="json") for r in self.rows], root, [r.ticker for r in self.rows], workers=1, db_data_dir=None)
            self.assertEqual(report["failed_count"], 0)
            exported = json.loads((root / "open-data/stocks.json").read_text())
            mu = next(r for r in exported if r["ticker"] == "MU")
            self.assertAlmostEqual(mu["industry_relative_strength"]["value"], 25)

    def test_database_rebuild_and_static_export_use_current_saved_history(self):
        with TemporaryDirectory() as directory:
            data_dir = Path(directory) / "db"
            with connect(data_dir) as conn:
                for row in self.rows:
                    replace_stock_open_data_snapshot(conn, row)
                    replace_stock_price_history(conn, row.ticker, self.histories[row.ticker])
                conn.commit()
            path = data_dir / BENCHMARK_FILE
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({**BENCHMARK, "return_basis": "price", "prices": [p.model_dump(mode="json") for p in self.market]}))
            universe = Path(directory) / "universe.json"
            universe.write_text(json.dumps([r.ticker for r in self.rows]))
            with patch("app.services.industry_strength.load_classifications", return_value=self.registry):
                rebuild_saved_industry_strength(data_dir, fetch_benchmark=False)
                with connect(data_dir) as conn:
                    self.assertAlmostEqual(load_stock_open_data_snapshot(conn, "MU").industry_relative_strength["value"], 15)
                    replace_stock_price_history(conn, "P1", [*self.histories["P1"][:-1], self.histories["P1"][-1].model_copy(update={"close": 160})])
                    conn.commit()
                # Export must calculate again, rather than publish yesterday's cached gap.
                export_static_site_data(data_dir, Path(directory) / "static", universe)
            exported = json.loads((Path(directory) / "static/open-data/stocks.json").read_text())
            mu = next(r for r in exported if r["ticker"] == "MU")
            self.assertAlmostEqual(mu["industry_relative_strength"]["value"], 25)


if __name__ == "__main__":
    unittest.main()
