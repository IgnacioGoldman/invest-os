from __future__ import annotations

import json
from pathlib import Path

from app.config import PROJECT_DIR, Settings
from app.entry_engine.open_data_models import HistoricalPricePoint, OpenDataSnapshot
from app.entry_engine.utils.file_storage import load_latest_open_data_stock_snapshots, load_open_data_active_tickers
from app.services.storage import (
    connect,
    load_stock_open_data_snapshots,
    load_stock_price_history,
    replace_stock_derived_signals_file,
    replace_stock_open_data_snapshot,
    replace_stock_price_history,
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


def load_db_or_backfill_stock_snapshots(settings: Settings) -> list[OpenDataSnapshot]:
    active_tickers = set(load_open_data_active_tickers())
    with connect(settings.data_dir) as conn:
        snapshots = load_stock_open_data_snapshots(conn)
        if snapshots:
            backfill_stock_derived_signals(settings)
            return [snapshot for snapshot in snapshots if not active_tickers or snapshot.ticker in active_tickers]

        snapshots = load_latest_open_data_stock_snapshots()
        for snapshot in snapshots:
            replace_stock_open_data_snapshot(conn, snapshot)
            price_history = load_cached_price_history(snapshot.ticker)
            if price_history:
                replace_stock_price_history(conn, snapshot.ticker, price_history)
        conn.commit()
        backfill_stock_derived_signals(settings)
        return snapshots


def load_db_or_backfill_price_history(settings: Settings, ticker: str) -> list[HistoricalPricePoint]:
    with connect(settings.data_dir) as conn:
        points = load_stock_price_history(conn, ticker)
        if points:
            return points
        points = load_cached_price_history(ticker)
        if points:
            replace_stock_price_history(conn, ticker, points)
            conn.commit()
        return points
