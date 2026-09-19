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
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STOCKS_PATH = ROOT / "frontend" / "public" / "data" / "open-data" / "stocks.json"
MATCH_TIMEZONE = ZoneInfo("Europe/Stockholm")
SUPPORT_METRICS = {
    "support_1m": "support_1m_distance",
    "support_6m": "support_6m_distance",
    "support_2y": "support_2y_distance",
    "support_5y": "support_5y_distance",
}


def _support_conditions(fields: list[str]) -> list[dict[str, str]]:
    return [
        {"field": field, "value": value}
        for field in fields
        for value in ("At support", "Near support")
    ]


def _strong_yoy_expression(support_fields: list[str]) -> dict[str, Any]:
    return {
        "operator": "and",
        "groups": [
            {"operator": "or", "conditions": _support_conditions(support_fields)},
            {
                "operator": "or",
                "conditions": [
                    {"field": "revenue", "value": "Strong"},
                    {"field": "revenue", "value": "Solid"},
                ],
            },
        ],
    }


BUILT_IN_FILTERS = {
    "builtin:pullback": _strong_yoy_expression(["support_1m"]),
    "builtin:support": _strong_yoy_expression(["support_6m", "support_2y", "support_5y"]),
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
    rows = sorted(
        snapshot.get("historical_series", {}).get("quarterly_revenue", []),
        key=lambda row: _period_key(str(row.get("period", ""))),
    )
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

    def request(
        self,
        method: str,
        table: str,
        params: dict[str, str] | None = None,
        payload: Any = None,
        prefer: str | None = None,
    ) -> Any:
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


def _filters_by_user(saved_filters: list[dict[str, Any]]) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    result: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for saved_filter in saved_filters:
        user_id = str(saved_filter.get("user_id", ""))
        filter_id = str(saved_filter.get("id", ""))
        expression = saved_filter.get("expression")
        if user_id and filter_id and isinstance(expression, dict):
            result.setdefault(user_id, []).append((f"saved:{filter_id}", expression))
    return result


def evaluate(stocks: list[dict[str, Any]], client: SupabaseRest) -> tuple[int, int]:
    profiles = client.request("GET", "user_profiles", {"select": "user_id"}) or []
    watchlist_rows = client.request("GET", "watchlist_items", {"select": "user_id,ticker"}) or []
    saved_filters = client.request("GET", "saved_filters", {"select": "id,user_id,expression"}) or []
    evaluations = client.request("GET", "filter_evaluations", {"select": "user_id,filter_key"}) or []
    states = client.request(
        "GET",
        "filter_match_state",
        {"select": "user_id,filter_key,ticker,first_matched_at,active"},
    ) or []

    stocks_by_ticker = {
        str(snapshot.get("ticker", "")).upper(): snapshot
        for snapshot in stocks
        if snapshot.get("ticker")
    }
    watchlists: dict[str, set[str]] = {}
    for row in watchlist_rows:
        watchlists.setdefault(str(row["user_id"]), set()).add(str(row["ticker"]).upper())

    custom_filters = _filters_by_user(saved_filters)
    initialized = {(str(row["user_id"]), str(row["filter_key"])) for row in evaluations}
    state_by_filter: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for row in states:
        key = (str(row["user_id"]), str(row["filter_key"]))
        state_by_filter.setdefault(key, {})[str(row["ticker"]).upper()] = row

    now = datetime.now(timezone.utc).isoformat()
    matched_on = datetime.now(MATCH_TIMEZONE).date().isoformat()
    evaluated_count = 0
    event_count = 0

    for profile in profiles:
        user_id = str(profile["user_id"])
        watched_stocks = [
            stocks_by_ticker[ticker]
            for ticker in sorted(watchlists.get(user_id, set()))
            if ticker in stocks_by_ticker
        ]
        filters = list(BUILT_IN_FILTERS.items()) + custom_filters.get(user_id, [])

        for filter_key, expression in filters:
            tracking_key = (user_id, filter_key)
            existing = state_by_filter.get(tracking_key, {})
            current = {
                str(snapshot["ticker"]).upper()
                for snapshot in watched_stocks
                if expression_matches(snapshot, expression)
            }
            entered = sorted(
                ticker
                for ticker in current
                if ticker not in existing or not existing[ticker].get("active")
            )

            for ticker, row in existing.items():
                if row.get("active") and ticker not in current:
                    client.request(
                        "PATCH",
                        "filter_match_state",
                        {
                            "user_id": f"eq.{user_id}",
                            "filter_key": f"eq.{filter_key}",
                            "ticker": f"eq.{ticker}",
                        },
                        {"active": False},
                    )

            if current:
                state_rows = [
                    {
                        "user_id": user_id,
                        "filter_key": filter_key,
                        "ticker": ticker,
                        "first_matched_at": existing.get(ticker, {}).get("first_matched_at") or now,
                        "last_matched_at": now,
                        "active": True,
                    }
                    for ticker in sorted(current)
                ]
                client.request(
                    "POST",
                    "filter_match_state",
                    {"on_conflict": "user_id,filter_key,ticker"},
                    state_rows,
                    "resolution=merge-duplicates,return=minimal",
                )

            if tracking_key in initialized and entered:
                event_rows = [
                    {
                        "user_id": user_id,
                        "filter_key": filter_key,
                        "ticker": ticker,
                        "matched_on": matched_on,
                    }
                    for ticker in entered
                ]
                client.request(
                    "POST",
                    "filter_match_events",
                    {"on_conflict": "user_id,filter_key,ticker,matched_on"},
                    event_rows,
                    "resolution=ignore-duplicates,return=minimal",
                )
                event_count += len(event_rows)

            client.request(
                "POST",
                "filter_evaluations",
                {"on_conflict": "user_id,filter_key"},
                {"user_id": user_id, "filter_key": filter_key, "last_evaluated_at": now},
                "resolution=merge-duplicates,return=minimal",
            )
            evaluated_count += 1

    return evaluated_count, event_count


def main() -> None:
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        print("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.", file=sys.stderr)
        raise SystemExit(2)
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_STOCKS_PATH
    stocks = json.loads(path.read_text(encoding="utf-8"))
    evaluated, events = evaluate(stocks, SupabaseRest(url, key))
    print(f"Evaluated {evaluated} watchlist filters and created {events} daily match events.")


if __name__ == "__main__":
    main()
