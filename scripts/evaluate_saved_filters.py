from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STOCKS_PATH = ROOT / "frontend" / "public" / "data" / "open-data" / "stocks.json"
SUPPORT_METRICS = {
    "support_1m": "support_1m_distance",
    "support_6m": "support_6m_distance",
    "support_2y": "support_2y_distance",
    "support_5y": "support_5y_distance",
}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _metric_value(snapshot: dict[str, Any], section: str, metric: str) -> float | None:
    return _number(snapshot.get(section, {}).get(metric, {}).get("value"))


def _growth_signal(value: float | None) -> str:
    if value is None:
        return "Unclear"
    if value >= 20:
        return "Strong"
    if value >= 8:
        return "Solid"
    if value >= 0:
        return "Mixed"
    return "Weak"


def _support_signal(value: float | None) -> str:
    if value is None or value > 25:
        return "Far"
    if value <= 2.5:
        return "At support"
    if value <= 6:
        return "Near support"
    return "Above support"


def _period_key(period: str) -> tuple[int, int, str]:
    if period.startswith("FY") and " Q" in period:
        year, quarter = period[2:].split(" Q", 1)
        if year.isdigit() and quarter.isdigit():
            return int(year), int(quarter), period
    return 0, 0, period


def _revenue_momentum(snapshot: dict[str, Any]) -> str:
    rows = sorted(snapshot.get("historical_series", {}).get("quarterly_revenue", []), key=lambda row: _period_key(str(row.get("period", ""))))
    points = [
        _number(row.get("metrics", {}).get("revenue_growth_yoy", {}).get("value"))
        for row in rows
    ]
    points = [point for point in points if point is not None]
    if len(points) < 2:
        return "Unclear"
    change = points[-1] - points[-2]
    if change >= 3:
        return "Accelerating"
    if change <= -3:
        return "Decelerating"
    return "Stable"


def signal_for(snapshot: dict[str, Any], field: str) -> str:
    if field == "revenue":
        return _growth_signal(_metric_value(snapshot, "business_health", "revenue_growth_yoy"))
    if field == "eps":
        return _growth_signal(_metric_value(snapshot, "business_health", "eps_growth_yoy"))
    if field == "momentum":
        return _revenue_momentum(snapshot)
    metric = SUPPORT_METRICS.get(field)
    return _support_signal(_metric_value(snapshot, "price_opportunity", metric)) if metric else "Unclear"


def expression_matches(snapshot: dict[str, Any], expression: dict[str, Any]) -> bool:
    groups = expression.get("groups")
    if not isinstance(groups, list) or not groups:
        return True
    group_results: list[bool] = []
    for group in groups:
        conditions = group.get("conditions") if isinstance(group, dict) else None
        if not isinstance(conditions, list) or not conditions:
            group_results.append(True)
            continue
        results = [
            signal_for(snapshot, str(condition.get("field", ""))) == condition.get("value")
            for condition in conditions
            if isinstance(condition, dict)
        ]
        group_results.append(all(results) if group.get("operator") == "and" else any(results))
    return all(group_results) if expression.get("operator") == "and" else any(group_results)


class SupabaseRest:
    def __init__(self, url: str, service_key: str) -> None:
        self.base = f"{url.rstrip('/')}/rest/v1"
        self.headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        }

    def request(self, method: str, table: str, params: dict[str, str] | None = None, payload: Any = None, prefer: str | None = None) -> Any:
        url = f"{self.base}/{quote(table)}"
        if params:
            url = f"{url}?{urlencode(params, safe='(),.*:')}"
        headers = dict(self.headers)
        if prefer:
            headers["Prefer"] = prefer
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                body = response.read()
                return json.loads(body) if body else None
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase {method} {table} failed ({exc.code}): {detail}") from exc


def evaluate(stocks: list[dict[str, Any]], client: SupabaseRest) -> tuple[int, int]:
    filters = client.request("GET", "saved_filters", {"select": "id,user_id,name,expression,notifications_enabled,last_evaluated_at"}) or []
    evaluated = 0
    notification_count = 0
    now = datetime.now(timezone.utc).isoformat()

    for saved_filter in filters:
        filter_id = str(saved_filter["id"])
        current = {
            str(snapshot.get("ticker", "")).upper()
            for snapshot in stocks
            if snapshot.get("ticker") and expression_matches(snapshot, saved_filter.get("expression") or {})
        }
        existing_rows = client.request(
            "GET",
            "filter_matches",
            {"select": "ticker,first_matched_at,active", "filter_id": f"eq.{filter_id}"},
        ) or []
        existing = {str(row["ticker"]): row for row in existing_rows}
        initialized = saved_filter.get("last_evaluated_at") is not None
        entered = sorted(ticker for ticker in current if ticker not in existing or not existing[ticker].get("active"))

        for ticker, row in existing.items():
            if row.get("active") and ticker not in current:
                client.request("PATCH", "filter_matches", {"filter_id": f"eq.{filter_id}", "ticker": f"eq.{ticker}"}, {"active": False})

        if current:
            match_rows = [
                {
                    "filter_id": filter_id,
                    "ticker": ticker,
                    "first_matched_at": existing.get(ticker, {}).get("first_matched_at") or now,
                    "last_matched_at": now,
                    "active": True,
                }
                for ticker in sorted(current)
            ]
            client.request(
                "POST",
                "filter_matches",
                {"on_conflict": "filter_id,ticker"},
                match_rows,
                "resolution=merge-duplicates",
            )

        if initialized and saved_filter.get("notifications_enabled") and entered:
            rows = [
                {
                    "user_id": saved_filter["user_id"],
                    "filter_id": filter_id,
                    "ticker": ticker,
                    "title": f"{ticker} is a new match",
                    "body": f"{ticker} just entered {saved_filter['name']}.",
                }
                for ticker in entered
            ]
            client.request("POST", "notifications", payload=rows)
            notification_count += len(rows)

        client.request("PATCH", "saved_filters", {"id": f"eq.{filter_id}"}, {"last_evaluated_at": now})
        evaluated += 1

    return evaluated, notification_count


def main() -> None:
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        print("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.", file=sys.stderr)
        raise SystemExit(2)
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_STOCKS_PATH
    stocks = json.loads(path.read_text(encoding="utf-8"))
    evaluated, notifications = evaluate(stocks, SupabaseRest(url, key))
    print(f"Evaluated {evaluated} saved filters and created {notifications} notifications.")


if __name__ == "__main__":
    main()
