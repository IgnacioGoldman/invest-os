from __future__ import annotations

import unittest

from evaluate_saved_filters import BUILT_IN_FILTERS, evaluate, expression_matches, signal_for


class FakeSupabase:
    def __init__(self) -> None:
        self.profiles = [{"user_id": "user-1"}]
        self.watchlist = [{"user_id": "user-1", "ticker": "TEST"}]
        self.evaluations: list[dict] = []
        self.states: list[dict] = []
        self.events: list[dict] = []

    def request(self, method, table, params=None, payload=None, prefer=None):
        if method == "GET":
            return {
                "user_profiles": self.profiles,
                "watchlist_items": self.watchlist,
                "saved_filters": [],
                "filter_evaluations": self.evaluations,
                "filter_match_state": self.states,
            }[table]
        if method == "PATCH":
            for row in self.states:
                if all(str(row[key]) == value.removeprefix("eq.") for key, value in (params or {}).items()):
                    row.update(payload)
            return None
        rows = payload if isinstance(payload, list) else [payload]
        target = {
            "filter_evaluations": self.evaluations,
            "filter_match_state": self.states,
            "filter_match_events": self.events,
        }[table]
        key_fields = {
            "filter_evaluations": ("user_id", "filter_key"),
            "filter_match_state": ("user_id", "filter_key", "ticker"),
            "filter_match_events": ("user_id", "filter_key", "ticker", "matched_on"),
        }[table]
        for row in rows:
            existing = next((item for item in target if all(item.get(key) == row.get(key) for key in key_fields)), None)
            if existing:
                existing.update(row)
            else:
                target.append(dict(row))
        return None


def snapshot(
    ticker: str,
    revenue: float,
    support_1m: float,
    support_5y: float,
    support_3m: float | None = None,
    support_6m: float | None = None,
    support_1y: float | None = None,
    support_2y: float | None = None,
) -> dict:
    return {
        "ticker": ticker,
        "business_health": {
            "revenue_growth_yoy": {"value": revenue},
            "eps_growth_yoy": {"value": None},
        },
        "price_opportunity": {
            "support_1m_distance": {"value": support_1m},
            "support_3m_distance": {"value": support_3m},
            "support_6m_distance": {"value": support_6m},
            "support_1y_distance": {"value": support_1y},
            "support_2y_distance": {"value": support_2y},
            "support_5y_distance": {"value": support_5y},
        },
        "historical_series": {},
    }


STRONG_YOY_SUPPORT = {
    "operator": "and",
    "groups": [
        {
            "operator": "or",
            "conditions": [
                {"field": "support_1m", "value": "At support"},
                {"field": "support_5y", "value": "At support"},
            ],
        },
        {
            "operator": "or",
            "conditions": [
                {"field": "revenue", "value": "Strong"},
                {"field": "revenue", "value": "Solid"},
            ],
        },
    ],
}


class SavedFilterEvaluatorTests(unittest.TestCase):
    def test_grouped_and_or_expression_matches_frontend_semantics(self) -> None:
        self.assertTrue(expression_matches(snapshot("MATCH", 12, 18, 1.5), STRONG_YOY_SUPPORT))
        self.assertFalse(expression_matches(snapshot("NO_GROWTH", 2, 1, 30), STRONG_YOY_SUPPORT))
        self.assertFalse(expression_matches(snapshot("NO_SUPPORT", 25, 7, 30), STRONG_YOY_SUPPORT))

    def test_signal_boundaries_match_frontend(self) -> None:
        row = snapshot("EDGE", 20, 2.5, 25)
        self.assertEqual(signal_for(row, "revenue"), "Strong")
        self.assertEqual(signal_for(row, "support_1m"), "At support")
        self.assertEqual(signal_for(row, "support_5y"), "Above support")

    def test_pullback_preset_only_uses_one_month_support(self) -> None:
        row = snapshot("PULLBACK", 12, 4, 30, support_6m=1)
        self.assertTrue(expression_matches(row, BUILT_IN_FILTERS["builtin:pullback"]))

        long_term_only = snapshot("LONG", 12, 12, 30, support_6m=1)
        self.assertFalse(expression_matches(long_term_only, BUILT_IN_FILTERS["builtin:pullback"]))

    def test_support_preset_uses_three_month_through_five_year_support(self) -> None:
        row = snapshot("SUPPORT", 25, 20, 30, support_1y=5)
        self.assertTrue(expression_matches(row, BUILT_IN_FILTERS["builtin:support"]))

        one_month_only = snapshot("SHORT", 25, 1, 30)
        self.assertFalse(expression_matches(one_month_only, BUILT_IN_FILTERS["builtin:support"]))

    def test_first_run_is_quiet_then_new_match_creates_daily_badge_event(self) -> None:
        client = FakeSupabase()
        evaluated, events = evaluate([snapshot("TEST", 12, 12, 30)], client)
        self.assertEqual((evaluated, events), (2, 0))

        evaluated, events = evaluate([snapshot("TEST", 12, 1, 30)], client)
        self.assertEqual((evaluated, events), (2, 1))
        self.assertEqual(client.events[0]["filter_key"], "builtin:pullback")
        self.assertEqual(client.events[0]["ticker"], "TEST")


if __name__ == "__main__":
    unittest.main()
