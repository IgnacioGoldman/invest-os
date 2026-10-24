from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SUPPORT_KEYS = (
    "support_1m_distance",
    "support_3m_distance",
    "support_6m_distance",
    "support_1y_distance",
    "support_2y_distance",
    "support_5y_distance",
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _universe_tickers(payload: Any) -> set[str]:
    rows = payload.get("rows") or payload.get("tickers") or [] if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return set()
    return {
        str(row.get("symbol") or row.get("ticker") or "").upper() if isinstance(row, dict) else str(row).upper()
        for row in rows
        if (isinstance(row, str) and row) or (isinstance(row, dict) and (row.get("symbol") or row.get("ticker")))
    }


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _metric_value(metric: Any) -> float | None:
    return _finite_number(metric.get("value") if isinstance(metric, dict) else None)


def _observation_dates(ticker: str, snapshot: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    prices = snapshot.get("price_opportunity")
    current = prices.get("current_price") if isinstance(prices, dict) else None
    return {"ticker": ticker,
            "price_as_of": current.get("as_of") if isinstance(current, dict) else None,
            "latest_fundamental_as_of": result.get("latest_fundamental_as_of")}


def _latest_series_metric_by_as_of(snapshot: dict[str, Any], series_name: str, metric_name: str) -> tuple[date, float] | None:
    historical_series = snapshot.get("historical_series")
    if not isinstance(historical_series, dict):
        return None
    rows = historical_series.get(series_name)
    if not isinstance(rows, list):
        return None
    candidates: list[tuple[date, float]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        as_of = _parse_date(row.get("as_of"))
        metrics = row.get("metrics")
        if as_of is None or not isinstance(metrics, dict):
            continue
        value = _metric_value(metrics.get(metric_name))
        if value is not None:
            candidates.append((as_of, value))
    return max(candidates, key=lambda item: item[0]) if candidates else None


def _validate_latest_revenue_growth(ticker: str, snapshot: dict[str, Any], errors: list[str]) -> None:
    business_health = snapshot.get("business_health")
    if not isinstance(business_health, dict):
        return
    card_value = _metric_value(business_health.get("revenue_growth_yoy"))
    latest_series = _latest_series_metric_by_as_of(snapshot, "quarterly_revenue", "revenue_growth_yoy")
    if card_value is None or latest_series is None:
        return
    latest_date, latest_value = latest_series
    if not math.isclose(card_value, latest_value, rel_tol=1e-9, abs_tol=1e-6):
        errors.append(
            f"{ticker}: latest revenue_growth_yoy card value {card_value:.6f} does not match "
            f"latest dated quarterly_revenue value {latest_value:.6f} as of {latest_date.isoformat()}."
        )


def _validate_fcf_margin(ticker: str, snapshot: dict[str, Any], errors: list[str]) -> None:
    business_health = snapshot.get("business_health")
    metrics = snapshot.get("metrics")
    if not isinstance(business_health, dict) or not isinstance(metrics, dict):
        return
    margin = business_health.get("fcf_margin")
    if isinstance(margin, dict) and margin.get("value") is None and "not meaningful" in str(margin.get("notes", "")).lower():
        # Financial companies can have cash-flow inputs without a comparable FCF margin.
        return
    free_cash_flow = _metric_value(metrics.get("free_cash_flow_ttm"))
    revenue = _metric_value(metrics.get("revenue_ttm"))
    if free_cash_flow is None or revenue in (None, 0):
        return
    value = _metric_value(business_health.get("fcf_margin"))
    expected = (free_cash_flow / revenue) * 100
    if value is None:
        errors.append(f"{ticker}: fcf_margin is missing even though free_cash_flow_ttm and revenue_ttm are available.")
    elif not math.isclose(value, expected, rel_tol=1e-9, abs_tol=1e-6):
        errors.append(f"{ticker}: fcf_margin {value:.6f} does not match free_cash_flow_ttm / revenue_ttm {expected:.6f}.")


def _validate_stock_details(ticker: str, snapshot: dict[str, Any], data_dir: Path, errors: list[str]) -> None:
    path = snapshot.get("detail_path")
    if not path:
        return
    if path != f"/open-data/snapshots/{ticker}.json":
        errors.append(f"{ticker}: unexpected stock detail path.")
        return
    try:
        detail = _load_json(data_dir / path.lstrip("/"))
    except (OSError, ValueError):
        errors.append(f"{ticker}: full stock detail export is missing or invalid.")
        return
    if not isinstance(detail, dict) or detail.get("detail_path"):
        errors.append(f"{ticker}: full stock detail export is not a complete snapshot.")
        return
    for key in ("ticker", "generated_at", "business_health", "price_opportunity", "valuation", "metrics"):
        if detail.get(key) != snapshot.get(key):
            errors.append(f"{ticker}: full stock details and screening data disagree on {key}.")
    if "screening" in snapshot and detail.get("screening") != snapshot["screening"]:
        errors.append(f"{ticker}: full stock details and screening data disagree on screening projection.")
    full_history = detail.get("historical_series", {})
    for key, rows in snapshot.get("historical_series", {}).items():
        if rows != sorted(full_history.get(key, []), key=lambda row: row["as_of"])[-len(rows):] and rows:
            errors.append(f"{ticker}: screening history does not match full {key} history.")


def _market_session_group(snapshot: dict[str, Any]) -> str | None:
    exchange = str(snapshot.get("exchange") or "").upper()
    if "STOCKHOLM" in exchange:
        return "Stockholm"
    if exchange in {"NYSE", "NASDAQ", "US-LISTED"}:
        return "US"
    return None


def _compatible_market_dates(stocks: list[dict[str, Any]]) -> bool:
    """Allow adjacent US/Stockholm session dates, but keep each market uniform."""
    by_market: dict[str, set[date]] = {}
    for snapshot in stocks:
        group = _market_session_group(snapshot)
        price_metrics = snapshot.get("price_opportunity")
        if not isinstance(price_metrics, dict):
            return False
        current = price_metrics.get("current_price")
        market_date = _parse_date(current.get("as_of")) if isinstance(current, dict) else None
        if group is None or market_date is None:
            return False
        by_market.setdefault(group, set()).add(market_date)
    if set(by_market) != {"US", "Stockholm"} or any(len(dates) != 1 for dates in by_market.values()):
        return False
    older, newer = sorted(next(iter(dates)) for dates in by_market.values())
    previous_weekday = newer - timedelta(days=1)
    while previous_weekday.weekday() >= 5:
        previous_weekday -= timedelta(days=1)
    return newer.weekday() < 5 and older == previous_weekday


def validate_refresh(report: dict[str, Any], universe: Any, stocks: Any, history_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    expected = _universe_tickers(universe)
    if not expected:
        errors.append("The stock universe is empty.")

    results = report.get("results") if isinstance(report.get("results"), list) else []
    result_tickers = {str(row.get("ticker", "")).upper() for row in results if isinstance(row, dict)}
    result_by_ticker = {str(row.get("ticker", "")).upper(): row for row in results if isinstance(row, dict)}
    unsaved = sorted(
        str(row.get("ticker", "")).upper()
        for row in results
        if isinstance(row, dict) and not row.get("saved_to")
    )
    if report.get("failed_count"):
        errors.append(f"Collector reported {report['failed_count']} failed ticker(s).")
    if report.get("skipped_low_fidelity_count"):
        errors.append(f"Collector skipped {report['skipped_low_fidelity_count']} low-fidelity ticker(s).")
    if result_tickers != expected:
        errors.append(f"Collector ticker mismatch: missing={sorted(expected - result_tickers)}, extra={sorted(result_tickers - expected)}.")
    if unsaved:
        errors.append(f"Collector did not persist: {unsaved}.")

    if not isinstance(stocks, list):
        errors.append("Exported stocks payload is not a list.")
        stocks = []
    stock_by_ticker = {
        str(row.get("ticker", "")).upper(): row
        for row in stocks
        if isinstance(row, dict) and row.get("ticker")
    }
    if set(stock_by_ticker) != expected:
        errors.append(f"Export ticker mismatch: missing={sorted(expected - set(stock_by_ticker))}, extra={sorted(set(stock_by_ticker) - expected)}.")

    market_dates: list[str] = []
    for ticker, snapshot in sorted(stock_by_ticker.items()):
        _validate_stock_details(ticker, snapshot, history_dir.parent.parent, errors)
        price_metrics = snapshot.get("price_opportunity")
        if not isinstance(price_metrics, dict):
            errors.append(f"{ticker}: price_opportunity is missing.")
            continue
        current = price_metrics.get("current_price")
        value = current.get("value") if isinstance(current, dict) else None
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or value <= 0:
            errors.append(f"{ticker}: current price is invalid.")
        market_date = _parse_date(current.get("as_of") if isinstance(current, dict) else None)
        if market_date is None:
            errors.append(f"{ticker}: current price market date is invalid.")
        else:
            market_dates.append(market_date.isoformat())
        missing_support = [key for key in SUPPORT_KEYS if key not in price_metrics]
        if missing_support:
            errors.append(f"{ticker}: missing support metrics {missing_support}.")
        _validate_latest_revenue_growth(ticker, snapshot, errors)
        _validate_fcf_margin(ticker, snapshot, errors)

        history_path = history_dir / f"{ticker}.json"
        if not history_path.exists():
            errors.append(f"{ticker}: price history export is missing.")
            continue
        history = _load_json(history_path)
        if not isinstance(history, list) or not history:
            errors.append(f"{ticker}: price history export is empty.")
            continue
        history_date = _parse_date(history[-1].get("date") if isinstance(history[-1], dict) else None)
        if market_date and history_date != market_date:
            errors.append(f"{ticker}: latest history date {history_date} does not match market date {market_date}.")

    date_counts = Counter(market_dates)
    market_as_of = date_counts.most_common(1)[0][0] if date_counts else None
    if len(date_counts) > 1 and not _compatible_market_dates(list(stock_by_ticker.values())):
        errors.append(f"Market dates are inconsistent: {dict(sorted(date_counts.items()))}.")
    today = datetime.now(timezone.utc).date()
    for market_date in date_counts:
        age_days = (today - date.fromisoformat(market_date)).days
        if age_days < 0:
            errors.append(f"Market date {market_date} is in the future.")
        elif age_days > 7:
            errors.append(f"Market date {market_date} is {age_days} days old.")

    return {
        "valid": not errors,
        "expected_count": len(expected),
        "exported_count": len(stock_by_ticker),
        "market_as_of": market_as_of,
        "market_date_counts": dict(sorted(date_counts.items())),
        "refresh_counts": dict(Counter(row.get("refresh_status", "not_reported") for row in results if isinstance(row, dict))),
        "sec_check_counts": dict(Counter(row["sec_check_status"] for row in results if isinstance(row, dict) and row.get("sec_check_status"))),
        "source_warnings": [{"ticker": row.get("ticker"), "notes": row["source_notes"]}
                            for row in results if isinstance(row, dict) and row.get("source_notes")],
        "data_dates": [_observation_dates(ticker, snapshot, result_by_ticker.get(ticker, {}))
                       for ticker, snapshot in sorted(stock_by_ticker.items())],
        "errors": errors,
    }


def _write_summary(path: Path, result: dict[str, Any]) -> None:
    status = "Passed" if result["valid"] else "Failed"
    lines = [
        "## Stock data refresh",
        "",
        f"- Validation: **{status}**",
        f"- Market data as of: **{result['market_as_of'] or 'Unavailable'}**",
        f"- Exported stocks: **{result['exported_count']} / {result['expected_count']}**",
    ]
    counts = result.get("refresh_counts", {})
    if any(key != "not_reported" for key in counts):
        lines.extend([
            f"- Refreshed: **{counts.get('refreshed', 0)}**",
            f"- Verified unchanged: **{counts.get('verified_unchanged', 0)}**",
            f"- Retained without source verification: **{counts.get('retained_unverified', 0)}**",
        ])
    if result.get("sec_check_counts"):
        counts = result["sec_check_counts"]
        lines.append(f"- SEC checks: **{counts.get('verified', 0)} verified**, **{counts.get('unavailable', 0)} unavailable**, **{counts.get('not_applicable', 0)} not applicable**")
    lines.extend(["", "### Market dates", "", "| Price date | Stocks |", "| --- | ---: |",
                  *[f"| {day} | {count} |" for day, count in result["market_date_counts"].items()]])
    if result.get("source_warnings"):
        lines.extend(["", "### Source checks requiring attention", "",
                      "Validation can pass while saved observations are retained. Their data dates remain unchanged.", ""])
        for row in result["source_warnings"]:
            # Keep multiline provider errors in a single list item.
            notes = " ".join(" ".join(str(note).split()) for note in row["notes"])
            lines.append(f"- {row['ticker']}: {notes}")
    if result.get("data_dates"):
        lines.extend(["", "### Observation dates", "",
                      "Financial metrics can cover different reporting periods; the date below is the latest available fundamental metric date.", "",
                      "| Stock | Price date | Latest fundamental metric date |", "| --- | --- | --- |",
                      *[f"| {row['ticker']} | {row['price_as_of'] or 'Unavailable'} | {row['latest_fundamental_as_of'] or 'Not reported'} |"
                        for row in result["data_dates"]]])
    if result["errors"]:
        lines.extend(["", "### Errors", *[f"- {error}" for error in result["errors"]]])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a refreshed static stock-data export before deployment.")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--universe", type=Path, default=ROOT / "data" / "stocks" / "stocks.json")
    parser.add_argument("--stocks", type=Path, default=ROOT / "frontend" / "public" / "data" / "open-data" / "stocks.json")
    parser.add_argument("--history-dir", type=Path, default=ROOT / "frontend" / "public" / "data" / "open-data" / "price-history")
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()

    result = validate_refresh(
        _load_json(args.report),
        _load_json(args.universe),
        _load_json(args.stocks),
        args.history_dir,
    )
    print(json.dumps(result, indent=2))
    if args.summary:
        _write_summary(args.summary, result)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
