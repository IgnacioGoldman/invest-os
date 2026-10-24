from __future__ import annotations

import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.screening_metrics import build_screening_metrics, day, DROPPED_FIELDS, BUSINESS_STATUSES, support_context  # noqa: E402

DEFAULT_STOCKS_PATH = ROOT / "frontend" / "public" / "data" / "open-data" / "stocks.json"
MATCH_TIMEZONE = ZoneInfo("Europe/Stockholm")
SUPPORT_METRICS = {
    "support_1m": "support_1m_distance",
    "support_3m": "support_3m_distance",
    "support_6m": "support_6m_distance",
    "support_1y": "support_1y_distance",
    "support_2y": "support_2y_distance",
    "support_5y": "support_5y_distance",
}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _filter_value(condition: dict[str, Any]) -> Any:
    value = condition.get("value")
    if condition.get("field") == "momentum" and value == "Stable":
        return "Steady"
    return value


def signal_for(snapshot: dict[str, Any], field: str) -> str:
    if field in DROPPED_FIELDS:
        return "Needs Review"
    if field in SUPPORT_METRICS:
        context = support_context(snapshot, SUPPORT_METRICS[field], today=datetime.now(timezone.utc).date())
        return context['status'] if context else 'Unknown'
    screening = snapshot.get("screening")
    if not screening or field == "upcoming_earnings":
        screening = build_screening_metrics(snapshot, today=datetime.now(timezone.utc).date())
    metric = screening.get("metrics", {}).get(field, {})
    if field == 'red_flag_count' and (metric.get('assessment_version') != 1
            or metric.get('status') not in {'Complete assessment', 'Partial assessment', 'Not assessed'}
            or not day(metric.get('valid_until')) or metric['valid_until'] < datetime.now(timezone.utc).date().isoformat()):
        return 'Not assessed'
    if field in BUSINESS_STATUSES:
        valid_until = str(metric.get('valid_until') or '')
        if not metric.get('validated') or valid_until < datetime.now(timezone.utc).date().isoformat():
            return 'Unknown'
    return screening.get("metrics", {}).get(field, {}).get("status", "Unknown")


FILTER_VALUES = {
    **BUSINESS_STATUSES,
    "upcoming_earnings": {"This week", "Next 30 days", "Later"},
    **{field: {"Inside Support Zone", "Near Support", "Above Support"} for field in SUPPORT_METRICS},
}
NUMERIC_FIELDS = {*BUSINESS_STATUSES, 'red_flag_count'}
NUMERIC_COMPARISONS = {'lt', 'lte', 'eq', 'gte', 'gt'}


def numeric_target(condition: dict) -> float | None:
    value = condition.get('value')
    if isinstance(value, bool) or value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str) or not re.fullmatch(r'[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?', value.strip(), re.I):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or (condition.get('field') == 'red_flag_count' and (value < 0 or not value.is_integer())):
        return None
    return value


def valid_condition(condition: dict) -> bool:
    field = condition.get('field')
    if condition.get('comparison') is not None:
        return field in NUMERIC_FIELDS and isinstance(condition['comparison'], str) and condition['comparison'] in NUMERIC_COMPARISONS and numeric_target(condition) is not None
    return field in FILTER_VALUES and _filter_value(condition) in FILTER_VALUES[field]


def condition_matches(snapshot: dict, condition: dict) -> bool:
    if condition.get('comparison') is None:
        return signal_for(snapshot, str(condition.get('field', ''))) == _filter_value(condition)
    screening = snapshot.get('screening') or build_screening_metrics(snapshot, today=datetime.now(timezone.utc).date())
    m = screening.get('metrics', {}).get(condition['field'], {})
    value, target = _number(m.get('value')), numeric_target(condition)
    deadline = str(m.get('valid_until') or '')
    if (value is None or target is None or not m.get('validated') or not day(deadline) or deadline < datetime.now(timezone.utc).date().isoformat()
            or (condition['field'] == 'red_flag_count' and (not m.get('coverage', {}).get('complete')
                or m.get('status') != 'Complete assessment' or m.get('assessment_version') != 1
                or not value.is_integer() or not 0 <= value <= m.get('max_count', 0)))
            or (condition['field'] in BUSINESS_STATUSES and m.get('status') not in BUSINESS_STATUSES[condition['field']])):
        return False
    comparison = condition['comparison']
    return {'lt': value < target, 'lte': value <= target, 'eq': value == target,
            'gte': value >= target, 'gt': value > target}[comparison]


def expression_matches(snapshot: dict[str, Any], expression: dict[str, Any]) -> bool:
    groups = expression.get("groups")
    if not isinstance(groups, list) or not groups:
        return True
    # Retired rules fail the entire saved expression, even inside an OR group.
    # Silently removing a rule could broaden an existing saved screen.
    if any(isinstance(c, dict) and not valid_condition(c) for g in groups if isinstance(g, dict) for c in g.get("conditions", [])):
        return False
    group_results: list[bool] = []
    for group in groups:
        conditions = group.get("conditions") if isinstance(group, dict) else None
        if not isinstance(conditions, list) or not conditions:
            group_results.append(True)
            continue
        results = [
            condition_matches(snapshot, condition)
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
        filters = custom_filters.get(user_id, [])

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
