"""Six/eight-quarter revenue growth momentum, matching frontend/src/revenueGrowthMomentum.ts."""
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
            "label": "Unknown", "change": None, "recentMedian": None, "priorMedian": None,
            "latestChange": None, "latestMovement": None, "points": [], "reason": reason,
        }

    rows = snapshot.get("historical_series", {}).get("quarterly_revenue", [])
    if any(_quarter_index(str(row.get("period", ""))) is None for row in rows):
        return unclear("Quarterly revenue history contains an invalid fiscal period.")
    window = sorted(rows, key=lambda row: row.get("as_of") or f"{_quarter_index(row['period']):08d}")[-8:]
    # Prefer eight complete observations; six remain the normal minimum.
    if len(window) < 8 or any(not isinstance(r.get('metrics', {}).get('revenue_growth_yoy', {}).get('value'), (int, float)) or isinstance(r.get('metrics', {}).get('revenue_growth_yoy', {}).get('value'), bool) or not math.isfinite(r.get('metrics', {}).get('revenue_growth_yoy', {}).get('value')) for r in window):
        window = window[-6:]
    if len(window) < 6:
        return unclear("Needs six consecutive quarters with comparable revenue YoY growth.")
    if any(_quarter_index(window[i]["period"]) != _quarter_index(window[i - 1]["period"]) + 1 for i in range(1, len(window))):
        return unclear("The latest six revenue quarters contain a gap or duplicate fiscal period.")
    points = []
    for row in window:
        value = row.get("metrics", {}).get("revenue_growth_yoy", {}).get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return unclear(f"{row['period']} has no comparable revenue YoY growth.")
        points.append({"period": row["period"], "value": value})
    half = len(points) // 2
    recent_median = median(point["value"] for point in points[half:])
    prior_median = median(point["value"] for point in points[:half])
    change = recent_median - prior_median
    latest, previous = points[-1]["value"], points[-2]["value"]
    latest_change = latest - previous
    if latest_change >= 3:
        latest_movement = "Rebounding" if previous <= prior_median - 3 and abs(latest - prior_median) < 3 else "Improving"
    else:
        latest_movement = "Weakening" if latest_change <= -3 else "Steady"
    return {
        "label": "Accelerating" if change >= 3 else "Decelerating" if change <= -3 else "Steady",
        "change": change, "recentMedian": recent_median, "priorMedian": prior_median,
        "latestChange": latest_change, "latestMovement": latest_movement, "points": points, "reason": None,
    }
