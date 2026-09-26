from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import requests

from refresh_static_prices import fetch_updated_history, hydrate_deployed_data, merge_price_history, refresh_snapshot_prices

from app.entry_engine.open_data_models import HistoricalPricePoint, OpenDataMetric, OpenDataSnapshot
from app.entry_engine.providers.open_data_provider import OpenDataProvider


def point(day: date, close: float, *, low: float | None = None) -> HistoricalPricePoint:
    return HistoricalPricePoint(
        date=day.isoformat(),
        close=close,
        high=close + 1 if low is not None else None,
        low=low,
        volume=1000 if low is not None else None,
        source="test",
    )


class FakeProvider:
    def __init__(self, full: list[HistoricalPricePoint], recent: list[HistoricalPricePoint]) -> None:
        self.full = full
        self.recent = recent
        self.full_calls = 0
        self.recent_calls: list[str] = []

    def fetch_price_history(self, ticker: str) -> list[HistoricalPricePoint]:
        self.full_calls += 1
        return self.full

    def fetch_price_history_since(self, ticker: str, start_date: str) -> list[HistoricalPricePoint]:
        self.recent_calls.append(start_date)
        return self.recent


class FakeResponse:
    def __init__(self, payload: object = None, *, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)

    def json(self) -> object:
        return self.payload


class FakeSession:
    def __init__(self, routes: dict[str, object]) -> None:
        self.routes = routes

    def get(self, url: str, **_: object) -> FakeResponse:
        path = url.split("/data/", 1)[1]
        payload = self.routes[path]
        if payload == 404:
            return FakeResponse(status_code=404)
        return FakeResponse(payload)


class RefreshStaticPricesTests(unittest.TestCase):
    def test_adjusted_eps_parser_accepts_actuals_and_rejects_outlook(self) -> None:
        provider = OpenDataProvider()
        table = "<tr><td>Non-GAAP EPS (1)</td><td>$</td><td>0.60</td><td>$</td><td>0.81</td><td>35</td><td>%</td></tr>"

        self.assertEqual(provider._parse_adjusted_eps_growth_yoy(table), 35)
        self.assertEqual(provider._parse_adjusted_eps_growth_yoy("Non-GAAP EPS of $0.81, up 35% year-over-year"), 35)
        self.assertIsNone(
            provider._parse_adjusted_eps_growth_yoy(
                "Outlook for Q3: Non-GAAP EPS of $0.84 to $0.88, representing growth of 28% to 35% YoY"
            )
        )

    def test_hydrate_falls_back_to_local_data_for_new_tickers(self) -> None:
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            (data_dir / "open-data" / "price-history").mkdir(parents=True)
            (data_dir / "stocks").mkdir(parents=True)
            local_stocks = [{"ticker": "AAA", "name": "Local AAA"}, {"ticker": "NEW", "name": "New Co"}]
            local_universe = {"rows": [{"symbol": "AAA"}, {"symbol": "NEW"}]}
            local_new_history = [{"date": "2026-09-24", "close": 20}]
            (data_dir / "open-data" / "stocks.json").write_text(json.dumps(local_stocks), encoding="utf-8")
            (data_dir / "stocks" / "universe.json").write_text(json.dumps(local_universe), encoding="utf-8")
            (data_dir / "open-data" / "price-history" / "NEW.json").write_text(
                json.dumps(local_new_history),
                encoding="utf-8",
            )
            routes = {
                "open-data/stocks.json": [{"ticker": "AAA", "name": "Deployed AAA"}],
                "stocks/universe.json": {"rows": [{"symbol": "AAA"}]},
                "open-data/price-history/AAA.json": [{"date": "2026-09-24", "close": 10}],
                "open-data/price-history/NEW.json": 404,
            }

            with patch("refresh_static_prices.requests.Session", side_effect=lambda: FakeSession(routes)):
                stocks = hydrate_deployed_data(
                    "https://example.com/data",
                    data_dir,
                    ["AAA", "NEW"],
                    cache_bust="test",
                    workers=2,
                )

            self.assertEqual([row["ticker"] for row in stocks], ["AAA", "NEW"])
            self.assertEqual(stocks[0]["name"], "Deployed AAA")
            self.assertEqual(stocks[1]["name"], "New Co")
            self.assertEqual(
                json.loads((data_dir / "open-data" / "price-history" / "NEW.json").read_text(encoding="utf-8")),
                local_new_history,
            )
            self.assertEqual(json.loads((data_dir / "stocks" / "universe.json").read_text(encoding="utf-8")), local_universe)

    def test_merge_price_history_replaces_overlapping_dates(self) -> None:
        start = date(2026, 1, 1)
        merged = merge_price_history(
            [point(start, 10), point(start + timedelta(days=1), 11)],
            [point(start + timedelta(days=1), 12, low=9), point(start + timedelta(days=2), 13, low=10)],
        )
        self.assertEqual([item.close for item in merged], [10, 12, 13])
        self.assertEqual(merged[1].low, 9)

    def test_recent_fetch_is_used_when_baseline_has_ohlc(self) -> None:
        start = date(2026, 1, 1)
        baseline = [point(start + timedelta(days=index), 100 + index, low=99 + index) for index in range(20)]
        recent = [point(start + timedelta(days=20), 125, low=123)]
        provider = FakeProvider(full=[], recent=recent)

        updated = fetch_updated_history(provider, "TEST", baseline)

        self.assertEqual(provider.full_calls, 0)
        self.assertEqual(provider.recent_calls, [(start + timedelta(days=5)).isoformat()])
        self.assertEqual(updated[-1].close, 125)

    def test_missing_ohlc_fetches_only_the_five_year_repair_window(self) -> None:
        latest = date(2026, 1, 20)
        baseline = [point(latest - timedelta(days=1), 100), point(latest, 101)]
        provider = FakeProvider(full=[], recent=[point(latest, 102, low=99)])

        updated = fetch_updated_history(provider, "TEST", baseline)

        self.assertEqual(provider.full_calls, 0)
        self.assertEqual(provider.recent_calls, [(latest - timedelta(days=365 * 5 + 30)).isoformat()])
        self.assertEqual(updated[-1].close, 102)

    def test_empty_provider_response_retains_valid_baseline(self) -> None:
        latest = date(2026, 1, 20)
        baseline = [point(latest, 101, low=99)]
        provider = FakeProvider(full=[], recent=[])

        updated = fetch_updated_history(provider, "TEST", baseline, attempts=3, retry_backoff=0)

        self.assertEqual(updated, baseline)
        self.assertEqual(len(provider.recent_calls), 3)

    def test_refresh_preserves_fundamentals_and_updates_price_metrics(self) -> None:
        metric = OpenDataMetric(
            value=20,
            source="sec_companyfacts",
            tier="computed_from_public_facts",
            as_of="2026-06-30",
            notes="Test SEC metric.",
        )
        old_price = OpenDataMetric(
            value=100,
            source="old_price",
            tier="exact_public_fact",
            as_of="2026-01-01",
            notes="Old price.",
        )
        obsolete_support = OpenDataMetric(
            value=1,
            source="old_price",
            tier="computed_from_public_facts",
            as_of="2026-01-01",
            notes="Retired 1D support metric.",
        )
        snapshot = OpenDataSnapshot(
            ticker="TEST",
            business_health={"revenue_growth_yoy": metric},
            price_opportunity={"current_price": old_price, "support_1d_distance": obsolete_support},
            valuation={"pe": metric},
            metrics={"revenue_growth_yoy": metric, "current_price": old_price, "support_1d_distance": obsolete_support},
        )
        start = date(2025, 1, 1)
        history = [point(start + timedelta(days=index), 100 + index / 10, low=99 + index / 10) for index in range(400)]
        refreshed_at = datetime(2026, 2, 1, tzinfo=timezone.utc)

        updated = refresh_snapshot_prices(snapshot, history, refreshed_at=refreshed_at)

        self.assertEqual(updated.business_health, snapshot.business_health)
        self.assertEqual(updated.valuation, snapshot.valuation)
        self.assertEqual(updated.metrics["revenue_growth_yoy"], metric)
        self.assertEqual(updated.price_opportunity["current_price"].value, history[-1].close)
        self.assertEqual(updated.metrics["current_price"].value, history[-1].close)
        self.assertNotIn("support_1d_distance", updated.price_opportunity)
        self.assertNotIn("support_1d_distance", updated.metrics)
        self.assertIn("support_3m_distance", updated.price_opportunity)
        self.assertIn("support_1y_distance", updated.price_opportunity)
        self.assertIn("support_5y_distance", updated.price_opportunity)
        self.assertEqual(updated.generated_at, refreshed_at)


if __name__ == "__main__":
    unittest.main()
