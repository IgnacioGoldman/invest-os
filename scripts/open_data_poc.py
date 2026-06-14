from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.entry_engine.providers.open_data_provider import OpenDataProvider  # noqa: E402
from app.entry_engine.utils.file_storage import save_open_data_stock_snapshot  # noqa: E402
from app.services.stock_entry_analysis import analyze_open_data_stock_entry  # noqa: E402


YAHOO_MOST_ACTIVE_URL = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
DEFAULT_UNIVERSE_PATH = ROOT / "data" / "stocks" / "stocks.json"
DEFAULT_SKIP_TICKERS = {"GOOGL"}
REQUIRED_GROUPS = ("business_health", "price_opportunity", "valuation")
EPS_DEPENDENT_METRICS = {
    "business_health.eps_growth_yoy",
    "business_health.eps_cagr_3y",
    "valuation.forward_pe",
    "valuation.peg",
}
logger = logging.getLogger(__name__)


def _metric_unavailable_reason(metric: Any) -> str:
    notes = str(getattr(metric, "notes", "") or "")
    _, _, reason = notes.partition(": ")
    return reason or notes or "Metric was unavailable from open/free public inputs."


def _is_not_meaningful_missing(metric_name: str, metric: Any, groups: dict[str, Any]) -> bool:
    notes = str(getattr(metric, "notes", "") or "").lower()
    if "not meaningful" in notes:
        return True

    if metric_name not in EPS_DEPENDENT_METRICS:
        return False

    if "trailing eps" in notes:
        return True

    if metric_name == "valuation.peg":
        eps_cagr = groups["business_health"].get("eps_cagr_3y")
        return eps_cagr is not None and _is_not_meaningful_missing("business_health.eps_cagr_3y", eps_cagr, groups)

    return False


def _unsupported_metric_paths(snapshot: Any) -> list[str]:
    gaps = list(getattr(snapshot, "data_gaps", []) or [])
    unsupported: list[str] = []
    for gap in gaps:
        if "unsupported metric path" in gap.lower():
            unsupported.append(gap)
    return unsupported


def _fetch_top_volume_stocks(limit: int, skip_tickers: set[str]) -> list[dict[str, Any]]:
    response = requests.get(
        YAHOO_MOST_ACTIVE_URL,
        params={"scrIds": "most_actives", "count": max(limit * 10 + len(skip_tickers), 50), "formatted": "false"},
        headers={"User-Agent": "Invest OS open-data validation/0.1"},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    results = data.get("finance", {}).get("result", [])
    quotes = results[0].get("quotes", []) if results else []
    stocks: list[dict[str, Any]] = []
    for quote in quotes:
        if not isinstance(quote, dict):
            continue
        symbol = str(quote.get("symbol") or "").upper()
        if not symbol or symbol in skip_tickers or symbol.startswith("^"):
            continue
        if quote.get("quoteType") not in {"EQUITY", "ADR"}:
            continue
        volume = quote.get("regularMarketVolume") or quote.get("averageDailyVolume3Month") or 0
        try:
            volume_value = float(volume)
        except (TypeError, ValueError):
            volume_value = 0
        stocks.append(
            {
                "ticker": symbol,
                "name": quote.get("shortName") or quote.get("longName"),
                "exchange": quote.get("fullExchangeName") or quote.get("exchange"),
                "volume": volume_value,
            }
        )
    stocks.sort(key=lambda item: item["volume"], reverse=True)
    return stocks


def _load_universe_stocks(path: Path, limit: int | None, skip_tickers: set[str]) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_rows = payload.get("rows") if isinstance(payload, dict) else payload
    if not isinstance(raw_rows, list):
        raise ValueError(f"Universe file {path} must contain a list or a 'rows' list.")

    stocks: list[dict[str, Any]] = []
    for row in raw_rows:
        if isinstance(row, str):
            symbol = row.upper()
            item: dict[str, Any] = {"ticker": symbol}
        elif isinstance(row, dict):
            symbol = str(row.get("symbol") or row.get("ticker") or "").upper()
            item = {
                "ticker": symbol,
                "name": row.get("name"),
                "exchange": row.get("exchange"),
                "region": row.get("region"),
                "sector": row.get("sector"),
                "industry": row.get("industry"),
                "composite_score": row.get("composite_score"),
                "dollar_volume": row.get("dollar_volume"),
            }
        else:
            continue
        if not symbol or symbol in skip_tickers:
            continue
        stocks.append(item)
        if limit is not None and len(stocks) >= limit:
            break
    return stocks


def _metric_coverage(snapshot: Any) -> dict[str, Any]:
    missing: list[str] = []
    not_meaningful: list[dict[str, str]] = []
    weak_proxy: list[str] = []
    total = 0
    available = 0
    groups = {group_name: getattr(snapshot, group_name) for group_name in REQUIRED_GROUPS}
    for group_name in REQUIRED_GROUPS:
        group = groups[group_name]
        for key, metric in group.items():
            total += 1
            metric_name = f"{group_name}.{key}"
            if metric.value is None or metric.tier == "unavailable_open_free":
                if _is_not_meaningful_missing(metric_name, metric, groups):
                    not_meaningful.append({"metric": metric_name, "reason": _metric_unavailable_reason(metric)})
                    continue
                missing.append(metric_name)
                continue
            available += 1
            if metric.tier == "proxy_estimate":
                weak_proxy.append(metric_name)

    collectable_total = total - len(not_meaningful)
    return {
        "available_metrics": available,
        "total_metrics": total,
        "coverage_percent": round((available / total * 100) if total else 0, 2),
        "collectable_metrics": collectable_total,
        "collectable_coverage_percent": round((available / collectable_total * 100) if collectable_total else 0, 2),
        "missing_metrics": missing,
        "not_meaningful_metrics": not_meaningful,
        "proxy_metrics": weak_proxy,
        "unsupported_metric_paths": _unsupported_metric_paths(snapshot),
        "provider_data_gaps": snapshot.data_gaps,
    }


def _collect_ticker(
    provider: OpenDataProvider,
    ticker: str,
    save: bool,
    *,
    min_coverage_to_save: float | None = None,
    include_analysis: bool = False,
) -> dict[str, Any]:
    snapshot = provider.get_open_data_snapshot(ticker)
    coverage = _metric_coverage(snapshot)
    analysis_payload: dict[str, Any] = {}
    if include_analysis:
        analysis = analyze_open_data_stock_entry(snapshot)
        analysis_payload = {
            "analysis": {
                "needs_more_data": analysis.needs_more_data,
                "conviction": analysis.conviction,
                "opportunity_type": analysis.opportunity_type,
                "business": analysis.business_health.assessment,
                "price": analysis.price_opportunity.assessment,
                "valuation": analysis.valuation.assessment,
                "missing_data": analysis.missing_data,
            }
        }
    should_save = (
        save
        and (min_coverage_to_save is None or coverage["collectable_coverage_percent"] >= min_coverage_to_save)
        and not coverage["unsupported_metric_paths"]
    )
    saved_path = save_open_data_stock_snapshot(snapshot) if should_save else None
    return {
        "ticker": snapshot.ticker,
        "name": snapshot.name,
        "cik": snapshot.cik,
        "source": snapshot.source,
        "generated_at": snapshot.generated_at.isoformat(),
        "saved_path": str(saved_path.relative_to(ROOT)) if saved_path else None,
        **analysis_payload,
        **coverage,
    }


def _collect_item_with_retries(
    item: dict[str, Any],
    *,
    save: bool,
    min_coverage: float,
    include_analysis: bool,
    include_filing_details: bool,
    ticker_retries: int,
    request_timeout: float,
    request_retries: int,
    retry_backoff: float,
) -> dict[str, Any]:
    ticker = item["ticker"]
    started = time.monotonic()
    last_error: Exception | None = None
    for attempt in range(1, max(1, ticker_retries) + 1):
        provider = OpenDataProvider(
            request_timeout=request_timeout,
            retry_attempts=request_retries,
            retry_backoff=retry_backoff,
            include_filing_details=include_filing_details,
        )
        try:
            result = {
                **item,
                **_collect_ticker(
                    provider,
                    ticker,
                    save,
                    min_coverage_to_save=min_coverage,
                    include_analysis=include_analysis,
                ),
            }
            result["duration_seconds"] = round(time.monotonic() - started, 2)
            result["attempts"] = attempt
            return result
        except Exception as exc:
            last_error = exc
            if attempt >= max(1, ticker_retries):
                break
            sleep_for = retry_backoff * (2 ** (attempt - 1))
            logger.warning("%s failed on attempt %s/%s: %s", ticker, attempt, ticker_retries, exc)
            if sleep_for > 0:
                time.sleep(sleep_for)

    assert last_error is not None
    raise last_error


def _write_report(path: Path | None, report: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _build_report(
    *,
    mode: str,
    requested_count: int,
    source: str,
    skip_tickers: set[str],
    min_coverage: float,
    include_filing_details: bool,
    results: list[dict[str, Any]],
    skipped_low_fidelity: list[dict[str, Any]],
    failures: list[dict[str, str]],
) -> dict[str, Any]:
    ordered_results = [dict(item) for item in sorted(results, key=lambda item: int(item.get("_index", 0)))]
    ordered_skipped = [dict(item) for item in sorted(skipped_low_fidelity, key=lambda item: int(item.get("_index", 0)))]
    ordered_failures = [dict(item) for item in sorted(failures, key=lambda item: int(item.get("_index", 0)))]
    for collection in (ordered_results, ordered_skipped, ordered_failures):
        for row in collection:
            row.pop("_index", None)
    return {
        "mode": mode,
        "requested_count": requested_count,
        "source": source,
        "skipped_tickers": sorted(skip_tickers),
        "min_coverage_percent": min_coverage,
        "include_filing_details": include_filing_details,
        "collected_count": len(ordered_results),
        "failed_count": len(ordered_failures),
        "skipped_low_fidelity_count": len(ordered_skipped),
        "results": ordered_results,
        "skipped_low_fidelity": ordered_skipped,
        "failures": ordered_failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the open/free public-data stock metrics proof-of-concept.")
    parser.add_argument("ticker", nargs="?", help="Ticker to collect. If omitted, collect top-volume stocks.")
    parser.add_argument("--top-volume", type=int, default=5, help="Number of top-volume stocks to collect when ticker is omitted.")
    parser.add_argument(
        "--universe-file",
        type=Path,
        help="Collect tickers from a stocks.json universe file instead of Yahoo most-actives.",
    )
    parser.add_argument("--limit", type=int, help="Limit universe-file collection count.")
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=80.0,
        help="Minimum metric coverage percent required in top-volume mode.",
    )
    parser.add_argument("--include-googl", action="store_true", help="Do not skip GOOGL in top-volume mode.")
    parser.add_argument("--include-analysis", action="store_true", help="Include deterministic stock-entry analysis in the run output.")
    parser.add_argument(
        "--skip-filing-details",
        action="store_true",
        help=(
            "Skip per-filing SEC archive exhibit lookups. Recent filing metadata is still collected; "
            "this is recommended for large universe runs."
        ),
    )
    parser.add_argument("--no-save", action="store_true", help="Do not persist snapshots under data/stocks/open_data/.")
    parser.add_argument("--output", type=Path, help="Write the JSON run report to a file as well as stdout.")
    parser.add_argument("--workers", type=int, default=6, help="Number of tickers to collect in parallel.")
    parser.add_argument("--ticker-retries", type=int, default=2, help="Retry a whole ticker collection this many times.")
    parser.add_argument("--request-timeout", type=float, default=15.0, help="Per-request timeout used by the open-data provider.")
    parser.add_argument("--request-retries", type=int, default=2, help="Retry individual HTTP requests this many times.")
    parser.add_argument("--retry-backoff", type=float, default=0.75, help="Base seconds for exponential retry backoff.")
    parser.add_argument("--checkpoint-every", type=int, default=1, help="Write --output after every N completed tickers.")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    provider = OpenDataProvider(
        request_timeout=args.request_timeout,
        retry_attempts=args.request_retries,
        retry_backoff=args.retry_backoff,
        include_filing_details=not args.skip_filing_details,
    )
    save = not args.no_save

    if args.ticker:
        result = _collect_ticker(provider, args.ticker, save, include_analysis=args.include_analysis)
        output = json.dumps(result, indent=2, sort_keys=False)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output + "\n", encoding="utf-8")
        print(output)
        return

    skip_tickers = set() if args.include_googl else set(DEFAULT_SKIP_TICKERS)
    if args.universe_file:
        universe_path = args.universe_file if args.universe_file.is_absolute() else ROOT / args.universe_file
        universe = _load_universe_stocks(universe_path, args.limit, skip_tickers)
        mode = "universe_file"
        source = str(universe_path.relative_to(ROOT))
        requested_count = len(universe)
        max_results = len(universe)
    else:
        universe = _fetch_top_volume_stocks(args.top_volume, skip_tickers)
        mode = "top_volume"
        source = "yahoo_finance_most_actives"
        requested_count = args.top_volume
        max_results = args.top_volume
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    skipped_low_fidelity: list[dict[str, Any]] = []

    work_items = list(enumerate(universe[:max_results] if mode == "top_volume" else universe))
    logger.info(
        "Collecting %s tickers with %s worker(s), ticker retries=%s, request timeout=%.1fs",
        len(work_items),
        max(1, args.workers),
        args.ticker_retries,
        args.request_timeout,
    )

    def record_result(index: int, item: dict[str, Any], result: dict[str, Any] | None, error: Exception | None = None) -> None:
        ticker = item["ticker"]
        if error is not None:
            logger.error(
                "Open-data collection failed for %s",
                ticker,
                exc_info=(type(error), error, error.__traceback__),
            )
            failures.append({"_index": index, "ticker": ticker, "error": str(error)})
            return
        assert result is not None
        result["_index"] = index
        if result["collectable_coverage_percent"] < args.min_coverage:
            skipped_low_fidelity.append(
                {
                    "_index": index,
                    "ticker": ticker,
                    "name": result.get("name") or item.get("name"),
                    "volume": item.get("volume"),
                    "coverage_percent": result["coverage_percent"],
                    "collectable_coverage_percent": result["collectable_coverage_percent"],
                    "missing_metrics": result["missing_metrics"],
                    "not_meaningful_metrics": result["not_meaningful_metrics"],
                    "unsupported_metric_paths": result["unsupported_metric_paths"],
                    "reason": f"Collectable metric coverage below {args.min_coverage:.0f}% threshold.",
                }
            )
            logger.info(
                "Skipped %s: collectable coverage %.2f%%",
                ticker,
                result["collectable_coverage_percent"],
            )
            return
        results.append(result)
        logger.info(
            "Collected %s: coverage %.2f%%, collectable %.2f%%, missing=%s, duration=%.2fs",
            ticker,
            result["coverage_percent"],
            result["collectable_coverage_percent"],
            len(result["missing_metrics"]),
            result["duration_seconds"],
        )

    def checkpoint(completed: int) -> None:
        if not args.output or args.checkpoint_every <= 0 or completed % args.checkpoint_every != 0:
            return
        _write_report(
            args.output,
            _build_report(
                mode=mode,
                requested_count=requested_count,
                source=source,
                skip_tickers=skip_tickers,
                    min_coverage=args.min_coverage,
                    include_filing_details=not args.skip_filing_details,
                    results=results,
                    skipped_low_fidelity=skipped_low_fidelity,
                    failures=failures,
            ),
        )

    if max(1, args.workers) == 1:
        for completed, (index, item) in enumerate(work_items, start=1):
            ticker = item["ticker"]
            logger.info("[%s/%s] Collecting %s", completed, len(work_items), ticker)
            try:
                result = _collect_item_with_retries(
                    item,
                    save=save,
                    min_coverage=args.min_coverage,
                    include_analysis=args.include_analysis,
                    include_filing_details=not args.skip_filing_details,
                    ticker_retries=args.ticker_retries,
                    request_timeout=args.request_timeout,
                    request_retries=args.request_retries,
                    retry_backoff=args.retry_backoff,
                )
                record_result(index, item, result)
            except Exception as exc:
                record_result(index, item, None, exc)
            checkpoint(completed)
    else:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            future_map = {
                executor.submit(
                    _collect_item_with_retries,
                    item,
                    save=save,
                    min_coverage=args.min_coverage,
                    include_analysis=args.include_analysis,
                    include_filing_details=not args.skip_filing_details,
                    ticker_retries=args.ticker_retries,
                    request_timeout=args.request_timeout,
                    request_retries=args.request_retries,
                    retry_backoff=args.retry_backoff,
                ): (index, item)
                for index, item in work_items
            }
            for completed, future in enumerate(as_completed(future_map), start=1):
                index, item = future_map[future]
                ticker = item["ticker"]
                try:
                    record_result(index, item, future.result())
                except Exception as exc:
                    record_result(index, item, None, exc)
                logger.info("[%s/%s] Finished %s", completed, len(work_items), ticker)
                checkpoint(completed)

    report = _build_report(
        mode=mode,
        requested_count=requested_count,
        source=source,
        skip_tickers=skip_tickers,
        min_coverage=args.min_coverage,
        include_filing_details=not args.skip_filing_details,
        results=results,
        skipped_low_fidelity=skipped_low_fidelity,
        failures=failures,
    )
    output = json.dumps(report, indent=2, sort_keys=False)
    _write_report(args.output, report)
    print(output)


if __name__ == "__main__":
    main()
