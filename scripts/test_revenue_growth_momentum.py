from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.revenue_growth_momentum import calculate_revenue_growth_momentum
from evaluate_saved_filters import signal_for


def snapshot(values: list[float | None]) -> dict:
    dates = ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]
    return {"historical_series": {"quarterly_revenue": [
        {"period": f"FY{2025 + i // 4} Q{i % 4 + 1}", "as_of": dates[i],
         "metrics": {"revenue_growth_yoy": {"value": value}}}
        for i, value in enumerate(values)
    ]}}


def scenarios() -> list[tuple[str, dict, dict]]:
    cases = [
        ("dip and recovery", snapshot([11.88, 11.07, 10.25, 11.42, 2.63, 9.42]),
         {"label": "Stable", "change": -1.65, "latestChange": 6.79, "latestMovement": "Rebounding"}),
        ("sustained acceleration", snapshot([8, 9, 10, 12, 13, 14]), {"label": "Accelerating", "change": 4}),
        ("sustained deceleration", snapshot([20, 19, 18, 14, 13, 12]), {"label": "Decelerating", "change": -6}),
        ("isolated spike", snapshot([10, 10, 10, 10, 10, 40]), {"label": "Stable", "change": 0, "latestMovement": "Improving"}),
        ("sudden collapse remains visible", snapshot([10, 10, 10, 10, 10, 0]), {"label": "Stable", "latestChange": -10, "latestMovement": "Weakening"}),
        ("shrinking revenue can accelerate", snapshot([-20, -20, -20, -12, -10, -8]), {"label": "Accelerating", "change": 10}),
        ("upper boundary", snapshot([10, 10, 10, 13, 13, 13]), {"label": "Accelerating", "change": 3}),
        ("lower boundary", snapshot([10, 10, 10, 7, 7, 7]), {"label": "Decelerating", "change": -3}),
        ("within boundary", snapshot([10, 10, 10, 12.999, 12.999, 12.999]), {"label": "Stable"}),
        ("median rather than mean", snapshot([0, 10, 100, 3, 13, 103]), {"label": "Accelerating", "change": 3}),
        ("short history", snapshot([10] * 5), {"label": "Unclear", "change": None}),
        ("missing latest growth does not use stale window", snapshot([10, 10, 10, 10, 10, None]), {"label": "Unclear"}),
        ("missing middle growth", snapshot([10, 10, None, 10, 10, 10]), {"label": "Unclear"}),
        ("boolean is not a growth value", snapshot([10, 10, 10, 10, 10, True]), {"label": "Unclear"}),
    ]
    gap = snapshot([10] * 6)
    gap["historical_series"]["quarterly_revenue"][3]["period"] = "FY2024 Q4"
    cases.append(("fiscal gap or mislabeled quarter", gap, {"label": "Unclear"}))
    duplicate = snapshot([10] * 6)
    duplicate["historical_series"]["quarterly_revenue"][4]["period"] = "FY2025 Q4"
    cases.append(("duplicate quarter", duplicate, {"label": "Unclear"}))
    reversed_rows = snapshot([8, 9, 10, 12, 13, 14])
    reversed_rows["historical_series"]["quarterly_revenue"].reverse()
    cases.append(("unordered source rows", reversed_rows, {"label": "Accelerating", "change": 4}))
    older_gap = snapshot([10] * 6)
    old_row = deepcopy(older_gap["historical_series"]["quarterly_revenue"][0])
    old_row.update(period="FY2023 Q1", as_of="2023-03-31")
    older_gap["historical_series"]["quarterly_revenue"].insert(0, old_row)
    cases.append(("older gap outside latest window", older_gap, {"label": "Stable", "change": 0}))
    return cases


class RevenueGrowthMomentumTests(unittest.TestCase):
    def test_scenarios_and_saved_filter_labels(self) -> None:
        for name, row, expected in scenarios():
            with self.subTest(name=name):
                result = calculate_revenue_growth_momentum(row)
                for key, value in expected.items():
                    if isinstance(value, (int, float)):
                        self.assertAlmostEqual(result[key], value)
                    else:
                        self.assertEqual(result[key], value)
                self.assertEqual(signal_for(row, "momentum"), result["label"])

    def test_nonfinite_values_are_unavailable(self) -> None:
        for value in [float("nan"), float("inf"), float("-inf")]:
            self.assertEqual(calculate_revenue_growth_momentum(snapshot([10] * 5 + [value]))["label"], "Unclear")


if __name__ == "__main__":
    unittest.main()
