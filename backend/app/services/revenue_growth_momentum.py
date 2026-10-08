"""Six-quarter revenue growth momentum, matching frontend/src/revenueGrowthMomentum.ts."""
from __future__ import annotations

import math
import re
from statistics import median
from typing import Any


def _quarter_index(period: str) -> int | None:
    match = re.fullmatch(r"FY(\d+)\s+Q([1-4])", period)
    return int(match[1]) * 4 + int(match[2]) - 1 if match else None


def calculate_revenue_growth_momentum(snapshot: dict[str, Any]) -> dict[str, Any]:
    def unclear(reason: str) -> dict[str, Any]:
        return {
            "label": "Unclear", "change": None, "recentMedian": None, "priorMedian": None,
            "latestChange": None, "latestMovement": None, "points": [], "reason": reason,
        }

    rows = snapshot.get("historical_series", {}).get("quarterly_revenue", [])
    if any(_quarter_index(str(row.get("period", ""))) is None for row in rows):
        return unclear("Quarterly revenue history contains an invalid fiscal period.")
    window = sorted(rows, key=lambda row: row.get("as_of") or f"{_quarter_index(row['period']):08d}")[-6:]
    if len(window) < 6:
        return unclear("Needs six consecutive quarters with comparable revenue YoY growth.")
    if any(_quarter_index(window[i]["period"]) != _quarter_index(window[i - 1]["period"]) + 1 for i in range(1, 6)):
        return unclear("The latest six revenue quarters contain a gap or duplicate fiscal period.")
    points = []
    for row in window:
        value = row.get("metrics", {}).get("revenue_growth_yoy", {}).get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return unclear(f"{row['period']} has no comparable revenue YoY growth.")
        points.append({"period": row["period"], "value": value})
    recent_median = median(point["value"] for point in points[3:])
    prior_median = median(point["value"] for point in points[:3])
    change = recent_median - prior_median
    latest, previous = points[5]["value"], points[4]["value"]
    latest_change = latest - previous
    if latest_change >= 3:
        latest_movement = "Rebounding" if previous <= prior_median - 3 and abs(latest - prior_median) < 3 else "Improving"
    else:
        latest_movement = "Weakening" if latest_change <= -3 else "Steady"
    return {
        "label": "Accelerating" if change >= 3 else "Decelerating" if change <= -3 else "Stable",
        "change": change, "recentMedian": recent_median, "priorMedian": prior_median,
        "latestChange": latest_change, "latestMovement": latest_movement, "points": points, "reason": None,
    }
