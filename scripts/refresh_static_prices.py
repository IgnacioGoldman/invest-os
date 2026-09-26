from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import sys
import time
from typing import Any, Protocol
from urllib.parse import quote

import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.entry_engine.open_data_metrics import backfill_fcf_margin_metric, compute_price_opportunity_metrics, _eps_alignment_metric  # noqa: E402
from app.entry_engine.open_data_models import HistoricalPricePoint, OpenDataMetric, OpenDataSnapshot  # noqa: E402
from app.entry_engine.providers.open_data_provider import OpenDataProvider  # noqa: E402


DEFAULT_BASE_URL = "https://ignaciogoldman.github.io/invest-os/data"
DEFAULT_DATA_DIR = ROOT / "frontend" / "public" / "data"
DEFAULT_UNIVERSE = ROOT / "data" / "stocks" / "stocks.json"
logger = logging.getLogger(__name__)


class PriceHistoryProvider(Protocol):
    def fetch_price_history_since(self, ticker: str, start_date: str) -> list[HistoricalPricePoint]: ...


class DownloadNotFound(RuntimeError):
    pass


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_json_if_present(path: Path) -> Any | None:
    if not path.exists():
        return None
    return _load_json(path)


def _universe_tickers(payload: Any) -> list[str]:
    rows = payload.get("rows") or payload.get("tickers") or [] if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    tickers: list[str] = []
    for row in rows:
        ticker = str(row.get("symbol") or row.get("ticker") or "") if isinstance(row, dict) else str(row)
        ticker = ticker.upper().strip()
        if ticker and ticker not in tickers:
            tickers.append(ticker)
    return tickers


def _rows_by_ticker(rows: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("ticker") or row.get("symbol") or "").upper(): row
        for row in rows
        if isinstance(row, dict) and (row.get("ticker") or row.get("symbol"))
    }


def _merge_stock_rows(deployed: list[Any], local: Any, tickers: list[str]) -> list[dict[str, Any]]:
    deployed_by_ticker = _rows_by_ticker(deployed)
    local_by_ticker = _rows_by_ticker(local)
    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        row = deployed_by_ticker.get(ticker) or local_by_ticker.get(ticker)
        if row is not None:
            rows.append(row)
    return rows


def _download_json(session: requests.Session, base_url: str, path: str, cache_bust: str, *, missing_ok: bool = False) -> Any:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    last_error: Exception | None = None
    for attempt in range(1, 5):
        try:
            response = session.get(
                url,
                params={"run": cache_bust},
                headers={"User-Agent": "Invest OS static price refresh/0.1"},
                timeout=60,
            )
            if response.status_code == 404 and missing_ok:
                raise DownloadNotFound(f"{url} returned 404.")
            response.raise_for_status()
            return response.json()
        except DownloadNotFound:
            raise
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < 4:
                time.sleep(2 ** (attempt - 1))
    raise RuntimeError(f"Could not download {url}: {last_error}")


def hydrate_deployed_data(
    base_url: str,
    data_dir: Path,
    tickers: list[str],
    *,
    cache_bust: str,
    workers: int,
) -> list[dict[str, Any]]:
    session = requests.Session()
    deployed_stocks = _download_json(session, base_url, "open-data/stocks.json", cache_bust)
    deployed_universe = _download_json(session, base_url, "stocks/universe.json", cache_bust)
    if not isinstance(deployed_stocks, list):
        raise ValueError("The deployed stocks payload is not a list.")
    local_stocks = _load_json_if_present(data_dir / "open-data" / "stocks.json")
    local_universe = _load_json_if_present(data_dir / "stocks" / "universe.json")
    stocks = _merge_stock_rows(deployed_stocks, local_stocks, tickers)
    universe = local_universe if local_universe is not None else deployed_universe

    histories: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_map = {
            executor.submit(
                _download_json,
                requests.Session(),
                base_url,
                f"open-data/price-history/{quote(ticker)}.json",
                cache_bust,
                missing_ok=True,
            ): ticker
            for ticker in tickers
        }
        for future in as_completed(future_map):
            ticker = future_map[future]
            try:
                histories[ticker] = future.result()
            except DownloadNotFound:
                history_path = data_dir / "open-data" / "price-history" / f"{ticker}.json"
                histories[ticker] = _load_json_if_present(history_path) or []
                logger.info("%s: deployed price history is missing; using local baseline.", ticker)

    _write_json(data_dir / "open-data" / "stocks.json", stocks)
    _write_json(data_dir / "stocks" / "universe.json", universe)
    for ticker in tickers:
        _write_json(data_dir / "open-data" / "price-history" / f"{ticker}.json", histories[ticker])
    return stocks


def merge_price_history(
    baseline: list[HistoricalPricePoint],
    updates: list[HistoricalPricePoint],
) -> list[HistoricalPricePoint]:
    by_date = {point.date: point for point in baseline if point.close > 0}
    by_date.update({point.date: point for point in updates if point.close > 0})
    return [by_date[key] for key in sorted(by_date)]


def _has_ohlc_history(points: list[HistoricalPricePoint]) -> bool:
    if not points:
        return False
    latest = date.fromisoformat(points[-1].date[:10])
    cutoff = latest - timedelta(days=365 * 5 + 30)
    relevant = [point for point in points if date.fromisoformat(point.date[:10]) >= cutoff]
    return bool(relevant) and sum(point.low is not None for point in relevant) / len(relevant) >= 0.9


def fetch_updated_history(
    provider: PriceHistoryProvider,
    ticker: str,
    baseline: list[HistoricalPricePoint],
    *,
    overlap_days: int = 14,
    attempts: int = 3,
    retry_backoff: float = 1,
) -> list[HistoricalPricePoint]:
    if not baseline:
        start_date = "1970-01-01"
    elif not _has_ohlc_history(baseline):
        latest = date.fromisoformat(baseline[-1].date[:10])
        start_date = (latest - timedelta(days=365 * 5 + 30)).isoformat()
    else:
        latest = date.fromisoformat(baseline[-1].date[:10])
        start_date = (latest - timedelta(days=overlap_days)).isoformat()
    fetched: list[HistoricalPricePoint] = []
    for attempt in range(1, max(1, attempts) + 1):
        fetched = provider.fetch_price_history_since(ticker, start_date)
        if fetched:
            break
        if attempt < max(1, attempts) and retry_backoff > 0:
            time.sleep(retry_backoff * (2 ** (attempt - 1)))
    if not fetched:
        if baseline:
            logger.warning("%s: recent prices unavailable; retaining the deployed history.", ticker)
            return baseline
        raise RuntimeError(f"{ticker}: no price history was returned and no baseline is available.")
    return merge_price_history(baseline, fetched)


def refresh_snapshot_prices(
    snapshot: OpenDataSnapshot,
    history: list[HistoricalPricePoint],
    *,
    adjusted_eps_growth_yoy: OpenDataMetric | None = None,
    refreshed_at: datetime | None = None,
) -> OpenDataSnapshot:
    snapshot = backfill_fcf_margin_metric(snapshot)
    timestamp = refreshed_at or datetime.now(timezone.utc)
    price_metrics = compute_price_opportunity_metrics(history, fallback_as_of=timestamp.date().isoformat())
    business_health = dict(snapshot.business_health)
    metrics = {key: value for key, value in snapshot.metrics.items() if key != "support_1d_distance"}
    if adjusted_eps_growth_yoy is not None:
        business_health["eps_adjusted_growth_yoy"] = adjusted_eps_growth_yoy
        metrics["eps_adjusted_growth_yoy"] = adjusted_eps_growth_yoy
        gaap_eps = business_health.get("eps_gaap_growth_yoy") or business_health.get("eps_growth_yoy")
        if gaap_eps is not None:
            eps_alignment = _eps_alignment_metric(
                adjusted_eps_growth_yoy,
                gaap_eps,
                timestamp.date().isoformat(),
            )
            business_health["eps_alignment"] = eps_alignment
            metrics["eps_alignment"] = eps_alignment
    metrics.update(price_metrics)
    return snapshot.model_copy(
        update={
            "generated_at": timestamp,
            "business_health": business_health,
            "price_opportunity": price_metrics,
            "metrics": metrics,
        }
    )


def refresh_prices(
    snapshots: list[dict[str, Any]],
    data_dir: Path,
    tickers: list[str],
    *,
    workers: int,
) -> dict[str, Any]:
    snapshot_by_ticker = {
        str(row.get("ticker") or "").upper(): row
        for row in snapshots
        if isinstance(row, dict) and row.get("ticker")
    }
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    updated_snapshots: dict[str, OpenDataSnapshot] = {}
    updated_histories: dict[str, list[HistoricalPricePoint]] = {}
    refreshed_at = datetime.now(timezone.utc)

    def refresh_one(ticker: str) -> tuple[OpenDataSnapshot, list[HistoricalPricePoint]]:
        raw_snapshot = snapshot_by_ticker.get(ticker)
        if raw_snapshot is None:
            raise ValueError(f"{ticker}: deployed snapshot is missing.")
        history_path = data_dir / "open-data" / "price-history" / f"{ticker}.json"
        baseline = [HistoricalPricePoint.model_validate(row) for row in _load_json(history_path)]
        provider = OpenDataProvider(include_filing_details=False)
        history = fetch_updated_history(provider, ticker, baseline)
        raw_model = OpenDataSnapshot.model_validate(raw_snapshot)
        adjusted_eps_growth_yoy = provider.fetch_adjusted_eps_growth_yoy(raw_model.cik) if raw_model.cik else None
        snapshot = refresh_snapshot_prices(
            raw_model,
            history,
            adjusted_eps_growth_yoy=adjusted_eps_growth_yoy,
            refreshed_at=refreshed_at,
        )
        return snapshot, history

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_map = {executor.submit(refresh_one, ticker): ticker for ticker in tickers}
        for future in as_completed(future_map):
            ticker = future_map[future]
            try:
                snapshot, history = future.result()
                updated_snapshots[ticker] = snapshot
                updated_histories[ticker] = history
                results.append(
                    {
                        "ticker": ticker,
                        "generated_at": snapshot.generated_at.isoformat(),
                        "saved_to": f"frontend/public/data/open-data/price-history/{ticker}.json",
                    }
                )
            except Exception as exc:
                logger.exception("Price refresh failed for %s", ticker)
                failures.append({"ticker": ticker, "error": str(exc)})

    output_rows: list[dict[str, Any]] = []
    for ticker in tickers:
        snapshot = updated_snapshots.get(ticker)
        if snapshot is not None:
            output_rows.append(snapshot.model_dump(mode="json"))
            _write_json(
                data_dir / "open-data" / "price-history" / f"{ticker}.json",
                [point.model_dump(mode="json") for point in updated_histories[ticker]],
            )
        elif ticker in snapshot_by_ticker:
            fallback_snapshot = backfill_fcf_margin_metric(OpenDataSnapshot.model_validate(snapshot_by_ticker[ticker]))
            output_rows.append(fallback_snapshot.model_dump(mode="json"))

    _write_json(data_dir / "open-data" / "stocks.json", output_rows)
    market_dates = [
        str(row.get("price_opportunity", {}).get("current_price", {}).get("as_of"))[:10]
        for row in output_rows
        if row.get("price_opportunity", {}).get("current_price", {}).get("as_of")
    ]
    date_counts = Counter(market_dates)
    market_as_of = date_counts.most_common(1)[0][0] if date_counts else None
    _write_json(
        data_dir / "meta.json",
        {
            "schema_version": 1,
            "refreshed_at": refreshed_at.isoformat().replace("+00:00", "Z"),
            "market_as_of": market_as_of,
            "market_date_counts": dict(sorted(date_counts.items())),
            "source": "github_actions_price_refresh",
            "stock_count": len(output_rows),
            "tickers": sorted(str(row.get("ticker") or "").upper() for row in output_rows),
        },
    )
    return {
        "mode": "price_only",
        "requested_count": len(tickers),
        "source": "deployed_static_snapshot",
        "collected_count": len(results),
        "failed_count": len(failures),
        "skipped_low_fidelity_count": 0,
        "results": sorted(results, key=lambda row: row["ticker"]),
        "skipped_low_fidelity": [],
        "failures": sorted(failures, key=lambda row: row["ticker"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh static price data without downloading SEC fundamentals.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--cache-bust", default=str(int(time.time())))
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))

    universe = _load_json(args.universe)
    tickers = _universe_tickers(universe)
    if not tickers:
        raise SystemExit("The stock universe is empty.")
    snapshots = hydrate_deployed_data(
        args.base_url,
        args.data_dir,
        tickers,
        cache_bust=args.cache_bust,
        workers=args.workers,
    )
    report = refresh_prices(snapshots, args.data_dir, tickers, workers=args.workers)
    _write_json(args.output, report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
