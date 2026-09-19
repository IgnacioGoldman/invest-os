from __future__ import annotations

import unittest

from evaluate_saved_filters import expression_matches, signal_for


def snapshot(ticker: str, revenue: float, support_1m: float, support_5y: float) -> dict:
    return {
        "ticker": ticker,
        "business_health": {
            "revenue_growth_yoy": {"value": revenue},
            "eps_growth_yoy": {"value": None},
        },
        "price_opportunity": {
            "support_1m_distance": {"value": support_1m},
            "support_6m_distance": {"value": None},
            "support_2y_distance": {"value": None},
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


if __name__ == "__main__":
    unittest.main()
