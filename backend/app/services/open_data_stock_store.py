from __future__ import annotations

import json
from pathlib import Path

from app.config import PROJECT_DIR, Settings
from app.entry_engine.open_data_metrics import SUPPORT_DISTANCE_WINDOWS, _support_distance_metric
from app.entry_engine.open_data_models import HistoricalPricePoint, OpenDataSnapshot
from app.services.storage import (
    activate_stock_ticker,
    connect,
    deactivate_stock_ticker,
    load_active_stock_tickers,
    load_stock_open_data_snapshot,
    load_stock_open_data_snapshots,
    load_stock_price_history,
    replace_stock_derived_signals_file,
    replace_stock_open_data_snapshot,
    replace_stock_price_history,
    seed_active_stock_tickers,
)
from app.services.stock_derived_signals import StockDerivedSignalsFile


def load_cached_price_history(ticker: str, cache_dir: Path | None = None) -> list[HistoricalPricePoint]:
    path = (cache_dir or PROJECT_DIR / ".cache" / "open_data") / f"price_history_{ticker.upper().strip()}.json"
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(rows, list):
        return []
    points: list[HistoricalPricePoint] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            points.append(HistoricalPricePoint.model_validate(row))
        except ValueError:
            continue
    return points


def save_stock_snapshot_to_db(settings: Settings, snapshot: OpenDataSnapshot) -> None:
    with connect(settings.data_dir) as conn:
        replace_stock_open_data_snapshot(conn, snapshot)
        price_history = load_cached_price_history(snapshot.ticker)
        if price_history:
            replace_stock_price_history(conn, snapshot.ticker, price_history)
        conn.commit()


def backfill_stock_derived_signals(settings: Settings) -> None:
    path = settings.data_dir / "stocks" / "derived_signals" / "latest.json"
    if not path.exists():
        return
    try:
        payload = StockDerivedSignalsFile.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    with connect(settings.data_dir) as conn:
        replace_stock_derived_signals_file(conn, payload)
        conn.commit()


def ensure_active_stock_seed(settings: Settings) -> None:
    with connect(settings.data_dir) as conn:
        seed_active_stock_tickers(conn, [snapshot.ticker for snapshot in load_stock_open_data_snapshots(conn)])
        conn.commit()


def load_active_tickers(settings: Settings) -> list[str]:
    ensure_active_stock_seed(settings)
    with connect(settings.data_dir) as conn:
        return load_active_stock_tickers(conn)


def activate_stock(settings: Settings, ticker: str) -> None:
    with connect(settings.data_dir) as conn:
        activate_stock_ticker(conn, ticker)
        conn.commit()


def deactivate_stock(settings: Settings, ticker: str) -> None:
    with connect(settings.data_dir) as conn:
        deactivate_stock_ticker(conn, ticker)
        conn.commit()


def load_db_stock_snapshot(settings: Settings, ticker: str) -> OpenDataSnapshot | None:
    with connect(settings.data_dir) as conn:
        return load_stock_open_data_snapshot(conn, ticker)


def load_db_or_backfill_stock_snapshots(settings: Settings) -> list[OpenDataSnapshot]:
    ensure_active_stock_seed(settings)
    with connect(settings.data_dir) as conn:
        active_tickers = set(load_active_stock_tickers(conn))
        snapshots = [
            _snapshot_with_support_backfill(conn, snapshot)
            for snapshot in load_stock_open_data_snapshots(conn)
            if not active_tickers or snapshot.ticker in active_tickers
        ]
        conn.commit()
    backfill_stock_derived_signals(settings)
    return snapshots


def load_all_db_stock_snapshots(settings: Settings) -> list[OpenDataSnapshot]:
    with connect(settings.data_dir) as conn:
        return load_stock_open_data_snapshots(conn)


def _snapshot_with_support_backfill(
    conn,
    snapshot: OpenDataSnapshot,
) -> OpenDataSnapshot:
    current_price = snapshot.price_opportunity.get("current_price")
    if current_price is None or current_price.value is None:
        return snapshot
    points = load_stock_price_history(conn, snapshot.ticker)
    if not points:
        return snapshot
    price_opportunity = dict(snapshot.price_opportunity)
    changed = False
    for key, (label, days) in SUPPORT_DISTANCE_WINDOWS.items():
        existing = price_opportunity.get(key)
        updated = _support_distance_metric(
            key,
            label,
            days,
            points,
            current_price.value,
            current_price.source,
            current_price.as_of,
            current_price.as_of,
        )
        if existing != updated:
            price_opportunity[key] = updated
            changed = True
    if not changed:
        return snapshot
    metrics = dict(snapshot.metrics)
    metrics.update({key: value for key, value in price_opportunity.items() if key in SUPPORT_DISTANCE_WINDOWS})
    updated = snapshot.model_copy(update={"price_opportunity": price_opportunity, "metrics": metrics})
    replace_stock_open_data_snapshot(conn, updated)
    return updated


def load_db_or_backfill_price_history(settings: Settings, ticker: str) -> list[HistoricalPricePoint]:
    with connect(settings.data_dir) as conn:
        return load_stock_price_history(conn, ticker)
