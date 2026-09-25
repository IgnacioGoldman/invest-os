from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
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


def validate_refresh(report: dict[str, Any], universe: Any, stocks: Any, history_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    expected = _universe_tickers(universe)
    if not expected:
        errors.append("The stock universe is empty.")

    results = report.get("results") if isinstance(report.get("results"), list) else []
    result_tickers = {str(row.get("ticker", "")).upper() for row in results if isinstance(row, dict)}
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
    if len(date_counts) > 1:
        errors.append(f"Market dates are inconsistent: {dict(sorted(date_counts.items()))}.")
    if market_as_of:
        age_days = (datetime.now(timezone.utc).date() - date.fromisoformat(market_as_of)).days
        if age_days < 0:
            errors.append(f"Market date {market_as_of} is in the future.")
        elif age_days > 7:
            errors.append(f"Market date {market_as_of} is {age_days} days old.")

    return {
        "valid": not errors,
        "expected_count": len(expected),
        "exported_count": len(stock_by_ticker),
        "market_as_of": market_as_of,
        "market_date_counts": dict(sorted(date_counts.items())),
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
