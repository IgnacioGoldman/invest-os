from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import unittest

from refresh_static_prices import fetch_updated_history, merge_price_history, refresh_snapshot_prices

from app.entry_engine.open_data_models import HistoricalPricePoint, OpenDataMetric, OpenDataSnapshot


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


class RefreshStaticPricesTests(unittest.TestCase):
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
