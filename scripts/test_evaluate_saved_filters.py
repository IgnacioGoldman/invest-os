from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

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
    forward_pe: float | None = 18,
    fcf_yield: float | None = 4,
    price_to_sales: float | None = 6,
    ev_to_ebitda: float | None = 18,
    days_to_next_earnings: float | None = None,
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
            "days_to_next_earnings": {"value": days_to_next_earnings},
        },
        "valuation": {
            "forward_pe": {"value": forward_pe},
            "fcf_yield": {"value": fcf_yield},
            "price_to_sales": {"value": price_to_sales},
            "ev_to_ebitda": {"value": ev_to_ebitda},
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
        {
            "operator": "or",
            "conditions": [
                {"field": "valuation", "value": "Cheap"},
                {"field": "valuation", "value": "Fair"},
            ],
        },
    ],
}


class SavedFilterEvaluatorTests(unittest.TestCase):
    def test_industry_strength_uses_the_card_status_and_matching_price_dates(self) -> None:
        row = snapshot("INDUSTRY", 25, 1, 1)
        today = datetime.now(timezone.utc).date().isoformat()
        row["price_opportunity"]["current_price"] = {"as_of": today}
        for value, expected in ((5, "Ahead of market"), (4.99, "In line with market"), (-4.99, "In line with market"), (-5, "Behind market"), (None, "Unclear")):
            with self.subTest(value=value):
                row["industry_relative_strength"] = {"value": value, "end_date": today}
                self.assertEqual(signal_for(row, "industry_strength"), expected)
        stale = (datetime.now(timezone.utc).date() - timedelta(days=8)).isoformat()
        row["industry_relative_strength"] = {"value": 10, "end_date": stale}
        row["price_opportunity"]["current_price"]["as_of"] = stale
        self.assertEqual(signal_for(row, "industry_strength"), "Unclear")
        row["industry_relative_strength"]["end_date"] = today
        self.assertEqual(signal_for(row, "industry_strength"), "Unclear")

    def test_industry_and_support_timeframe_match_together(self) -> None:
        row = snapshot("MATCH", 25, 30, 1, support_1y=4)
        today = datetime.now(timezone.utc).date().isoformat()
        row["price_opportunity"]["current_price"] = {"as_of": today}
        row["industry_relative_strength"] = {"value": 8, "end_date": today}
        expression = {"operator": "and", "groups": [
            {"operator": "or", "conditions": [{"field": "industry_strength", "value": "Ahead of market"}]},
            {"operator": "or", "conditions": [{"field": "support_1y", "value": "At support"}, {"field": "support_1y", "value": "Near support"}]},
        ]}
        self.assertTrue(expression_matches(row, expression))
        expression["groups"][1]["conditions"] = [{"field": "support_1m", "value": "Near support"}]
        self.assertFalse(expression_matches(row, expression))

    def test_missing_and_fallback_metric_statuses_match_stock_cards(self) -> None:
        row = snapshot("MISSING", 25, 1, 1)
        row["business_health"]["revenue_growth_yoy"] = {"value": None, "tier": "unavailable_open_free"}
        row["business_health"]["eps_gaap_growth_yoy"] = {"value": None, "tier": "unavailable_open_free"}
        row["business_health"]["eps_growth_yoy"] = {"value": 25}
        row["metrics"] = {"days_to_next_earnings": {"value": 5}}
        self.assertEqual(signal_for(row, "revenue"), "Unavailable")
        self.assertEqual(signal_for(row, "eps"), "Unavailable")
        row["price_opportunity"].pop("days_to_next_earnings", None)
        self.assertEqual(signal_for(row, "upcoming_earnings"), "This week")

    def test_multi_select_values_match_any_value_and_require_every_metric(self) -> None:
        expression = {
            "icon": "trend",
            "operator": "and",
            "groups": [
                {"operator": "or", "conditions": [
                    {"field": "revenue", "value": "Strong"},
                    {"field": "revenue", "value": "Solid"},
                ]},
                {"operator": "or", "conditions": [
                    {"field": "valuation", "value": "Cheap"},
                    {"field": "valuation", "value": "Fair"},
                ]},
            ],
        }
        for revenue in (25, 12):
            for forward_pe in (15, 22):
                with self.subTest(revenue=revenue, forward_pe=forward_pe):
                    self.assertTrue(expression_matches(snapshot("MATCH", revenue, 1, 1, forward_pe=forward_pe), expression))
        self.assertFalse(expression_matches(snapshot("WEAK", -5, 1, 1, forward_pe=15), expression))
        self.assertFalse(expression_matches(snapshot("PRICEY", 25, 1, 1, forward_pe=40), expression))

    def test_grouped_and_or_expression_matches_frontend_semantics(self) -> None:
        self.assertTrue(expression_matches(snapshot("MATCH", 12, 18, 1.5), STRONG_YOY_SUPPORT))
        self.assertFalse(expression_matches(snapshot("NO_GROWTH", 2, 1, 30), STRONG_YOY_SUPPORT))
        self.assertFalse(expression_matches(snapshot("NO_SUPPORT", 25, 7, 30), STRONG_YOY_SUPPORT))

    def test_signal_boundaries_match_frontend(self) -> None:
        row = snapshot("EDGE", 20, 2.5, 25)
        self.assertEqual(signal_for(row, "revenue"), "Strong")
        self.assertEqual(signal_for(row, "support_1m"), "At support")
        self.assertEqual(signal_for(row, "support_5y"), "Above support")
        self.assertEqual(signal_for(row, "valuation"), "Cheap")
        self.assertEqual(signal_for(snapshot("FLAT", 4, 2.5, 25), "revenue"), "Flat")
        modest_eps = snapshot("MODEST_EPS", 20, 2.5, 25)
        modest_eps["business_health"]["eps_growth_yoy"]["value"] = 4
        self.assertEqual(signal_for(modest_eps, "eps"), "Modest")

        app_like = snapshot("APP_LIKE", 50, 1, 1, forward_pe=14.9, fcf_yield=4.3, price_to_sales=15.4, ev_to_ebitda=19.6)
        self.assertEqual(signal_for(app_like, "valuation"), "Pricey")

        earnings = snapshot("EARNINGS", 20, 2.5, 25, days_to_next_earnings=7)
        self.assertEqual(signal_for(earnings, "upcoming_earnings"), "This week")
        self.assertEqual(signal_for(snapshot("NEXT_21", 20, 2.5, 25, days_to_next_earnings=21), "upcoming_earnings"), "Next 30 days")
        self.assertEqual(signal_for(snapshot("NEXT_30", 20, 2.5, 25, days_to_next_earnings=30), "upcoming_earnings"), "Next 30 days")
        self.assertEqual(signal_for(snapshot("LATER", 20, 2.5, 25, days_to_next_earnings=31), "upcoming_earnings"), "Later")

    def test_metric_specific_labels_cover_boundaries(self) -> None:
        row = snapshot("BOUNDARY", 4, 12, 30)
        for value, eps_label, fcf_label in [
            (-0.01, "Weak", "Weak"),
            (0, "Modest", "Thin"),
            (7.99, "Modest", "Thin"),
            (8, "Solid", "Thin"),
            (9.99, "Solid", "Thin"),
            (10, "Solid", "Solid"),
            (19.99, "Solid", "Solid"),
            (20, "Strong", "Strong"),
            (None, "Unclear", "Unclear"),
        ]:
            with self.subTest(value=value):
                row["business_health"]["eps_gaap_growth_yoy"] = {"value": value}
                row["business_health"]["fcf_margin"] = {"value": value}
                self.assertEqual(signal_for(row, "eps"), eps_label)
                self.assertEqual(signal_for(row, "fcf_margin"), fcf_label)
                self.assertEqual(signal_for(row, "revenue"), "Flat")

    def test_old_and_new_saved_metric_labels_match_the_same_band(self) -> None:
        row = snapshot("SAVED", 20, 12, 30)
        row["business_health"]["eps_gaap_growth_yoy"] = {"value": 4}
        row["business_health"]["fcf_margin"] = {"value": 5}
        for field, label in [("eps", "Modest"), ("fcf_margin", "Thin")]:
            for saved_label in [label, "Mixed"]:
                with self.subTest(field=field, label=saved_label):
                    expression = {"operator": "and", "groups": [
                        {"operator": "and", "conditions": [{"field": field, "value": saved_label}]},
                    ]}
                    self.assertTrue(expression_matches(row, expression))
                    outside_band = snapshot("OUTSIDE", 20, 12, 30)
                    outside_band["business_health"]["eps_gaap_growth_yoy"] = {"value": 20}
                    outside_band["business_health"]["fcf_margin"] = {"value": 20}
                    self.assertFalse(expression_matches(outside_band, expression))

    def test_support_presets_require_every_timeframe_and_accept_either_status(self) -> None:
        for key, fields in [
            ("builtin:pullback", ("support_1m", "support_3m", "support_6m")),
            ("builtin:support", ("support_1y", "support_2y", "support_5y")),
        ]:
            for value in (1, 5):
                with self.subTest(key=key, support=value):
                    row = snapshot("MATCH", 12, 30, 30)
                    for field in fields:
                        row["price_opportunity"][f"{field}_distance"]["value"] = value
                    self.assertTrue(expression_matches(row, BUILT_IN_FILTERS[key]))
                    for field in fields:
                        for outside in (7, None):
                            with self.subTest(field=field, outside=outside):
                                row["price_opportunity"][f"{field}_distance"]["value"] = outside
                                self.assertFalse(expression_matches(row, BUILT_IN_FILTERS[key]))
                        row["price_opportunity"][f"{field}_distance"]["value"] = value
                    row["business_health"]["revenue_growth_yoy"]["value"] = 2
                    self.assertFalse(expression_matches(row, BUILT_IN_FILTERS[key]))

    def test_forward_pe_signal_uses_earnings_multiple_only(self) -> None:
        for value, label in [
            (0.01, "Cheap"), (18, "Cheap"), (18.01, "Fair"), (25, "Fair"),
            (25.01, "Unclear"), (34.99, "Unclear"), (35, "Pricey"),
            (49.99, "Pricey"), (50, "Very pricey"), (None, "Unclear"),
            (0, "Unclear"), (-1, "Unclear"), (float("nan"), "Unclear"),
            (float("inf"), "Unclear"), (float("-inf"), "Unclear"),
        ]:
            with self.subTest(value=value):
                row = snapshot("FORWARD_PE", 30, 1, 30, forward_pe=value, price_to_sales=15)
                self.assertEqual(signal_for(row, "forward_pe"), label)

    def test_support_presets_use_forward_pe_instead_of_composite_valuation(self) -> None:
        for key in ("builtin:pullback", "builtin:support"):
            for value in (0.01, 18, 18.01, 25):
                with self.subTest(key=key, forward_pe=value):
                    row = snapshot("FAIR_PRICE", 12, 1, 1, support_3m=1, support_6m=1,
                                   support_1y=1, support_2y=1, forward_pe=value, price_to_sales=25)
                    self.assertEqual(signal_for(row, "valuation"), "Very pricey")
                    self.assertTrue(expression_matches(row, BUILT_IN_FILTERS[key]))
            for value in (None, 0, -1, 25.01, 30, float("nan"), float("-inf")):
                with self.subTest(key=key, forward_pe=value):
                    row = snapshot("COMPOSITE_FAIR", 12, 1, 1, support_3m=1, support_6m=1,
                                   support_1y=1, support_2y=1, forward_pe=value)
                    self.assertIn(signal_for(row, "valuation"), ("Cheap", "Fair"))
                    self.assertFalse(expression_matches(row, BUILT_IN_FILTERS[key]))
            del row["valuation"]["forward_pe"]
            self.assertFalse(expression_matches(row, BUILT_IN_FILTERS[key]))

    def test_forward_pe_becoming_fair_creates_pullback_badge(self) -> None:
        client = FakeSupabase()
        row = snapshot("TEST", 12, 1, 30, support_3m=5, support_6m=1, forward_pe=30)
        self.assertEqual(evaluate([row], client), (3, 0))
        row["valuation"]["forward_pe"]["value"] = 25
        self.assertEqual(evaluate([row], client), (3, 1))
        self.assertEqual(client.events[0]["filter_key"], "builtin:pullback")
        row["valuation"]["forward_pe"]["value"] = 18
        self.assertEqual(evaluate([row], client), (3, 0))

    def test_upcoming_earnings_preset_requires_next_30_days_and_strong_or_solid_yoy(self) -> None:
        strong = snapshot("STRONG", 25, 12, 30, days_to_next_earnings=7)
        self.assertTrue(expression_matches(strong, BUILT_IN_FILTERS["builtin:earnings_this_week"]))

        solid = snapshot("SOLID", 12, 12, 30, days_to_next_earnings=30)
        self.assertTrue(expression_matches(solid, BUILT_IN_FILTERS["builtin:earnings_this_week"]))

        weak_growth = snapshot("WEAK", 2, 12, 30, days_to_next_earnings=3)
        self.assertFalse(expression_matches(weak_growth, BUILT_IN_FILTERS["builtin:earnings_this_week"]))

        later_earnings = snapshot("LATER", 25, 12, 30, days_to_next_earnings=31)
        self.assertFalse(expression_matches(later_earnings, BUILT_IN_FILTERS["builtin:earnings_this_week"]))

    def test_first_run_is_quiet_then_new_match_creates_daily_badge_event(self) -> None:
        client = FakeSupabase()
        evaluated, events = evaluate([snapshot("TEST", 12, 12, 30)], client)
        self.assertEqual((evaluated, events), (3, 0))

        evaluated, events = evaluate([snapshot("TEST", 12, 1, 30, support_3m=5, support_6m=1)], client)
        self.assertEqual((evaluated, events), (3, 1))
        self.assertEqual(client.events[0]["filter_key"], "builtin:pullback")
        self.assertEqual(client.events[0]["ticker"], "TEST")


if __name__ == "__main__":
    unittest.main()
