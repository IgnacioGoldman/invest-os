from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from app.entry_engine.open_data_models import HistoricalPricePoint, OpenDataSnapshot
from app.services.stock_derived_signals import StockDerivedSignals, StockDerivedSignalsFile


DB_FILE = "invest_os.sqlite"


def db_path(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / DB_FILE


def connect(data_dir: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(data_dir))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS historical_prices (
            asset TEXT NOT NULL,
            currency TEXT NOT NULL,
            priced_at TEXT NOT NULL,
            price REAL NOT NULL,
            source TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (asset, currency, priced_at)
        );

        CREATE TABLE IF NOT EXISTS stock_open_data_snapshots (
            ticker TEXT PRIMARY KEY,
            generated_at TEXT NOT NULL,
            payload TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS stock_derived_signals (
            ticker TEXT PRIMARY KEY,
            generated_at TEXT NOT NULL,
            payload TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS stock_metric_series (
            ticker TEXT NOT NULL,
            series TEXT NOT NULL,
            metric TEXT NOT NULL,
            period TEXT NOT NULL,
            as_of TEXT NOT NULL,
            value REAL,
            source TEXT NOT NULL,
            tier TEXT NOT NULL,
            notes TEXT NOT NULL,
            PRIMARY KEY (ticker, series, metric, period)
        );

        CREATE TABLE IF NOT EXISTS active_stock_symbols (
            ticker TEXT PRIMARY KEY,
            added_at TEXT NOT NULL
        );
        """
    )


def replace_stock_price_history(conn: sqlite3.Connection, ticker: str, points: Iterable[HistoricalPricePoint]) -> None:
    fetched_at = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        """
        INSERT INTO historical_prices (asset, currency, priced_at, price, source, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(asset, currency, priced_at) DO UPDATE SET
            price = excluded.price,
            source = excluded.source,
            fetched_at = excluded.fetched_at
        """,
        [
            (
                ticker.upper(),
                "USD",
                f"{point.date}T00:00:00+00:00" if "T" not in point.date else point.date,
                point.close,
                point.source,
                fetched_at,
            )
            for point in points
            if point.close > 0
        ],
    )


def load_stock_price_history(conn: sqlite3.Connection, ticker: str) -> list[HistoricalPricePoint]:
    rows = conn.execute(
        """
        SELECT priced_at, price, source
        FROM historical_prices
        WHERE asset = ? AND currency = 'USD'
        ORDER BY priced_at
        """,
        (ticker.upper(),),
    )
    return [
        HistoricalPricePoint(
            date=str(row["priced_at"]).split("T", 1)[0],
            close=row["price"],
            source=row["source"],
        )
        for row in rows
    ]


def replace_stock_metric_series(conn: sqlite3.Connection, snapshot: OpenDataSnapshot) -> None:
    conn.execute("DELETE FROM stock_metric_series WHERE ticker = ?", (snapshot.ticker.upper(),))
    rows = []
    for series_name, series_rows in snapshot.historical_series.items():
        for period_row in series_rows:
            for metric_name, metric in period_row.metrics.items():
                rows.append(
                    (
                        snapshot.ticker.upper(),
                        series_name,
                        metric_name,
                        period_row.period,
                        period_row.as_of,
                        metric.value,
                        metric.source,
                        metric.tier,
                        metric.notes,
                    )
                )
    conn.executemany(
        """
        INSERT OR REPLACE INTO stock_metric_series
            (ticker, series, metric, period, as_of, value, source, tier, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def replace_stock_open_data_snapshot(conn: sqlite3.Connection, snapshot: OpenDataSnapshot) -> None:
    conn.execute(
        """
        INSERT INTO stock_open_data_snapshots (ticker, generated_at, payload)
        VALUES (?, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
            generated_at = excluded.generated_at,
            payload = excluded.payload
        """,
        (snapshot.ticker.upper(), snapshot.generated_at.isoformat(), snapshot.model_dump_json()),
    )
    replace_stock_metric_series(conn, snapshot)


def load_stock_open_data_snapshots(conn: sqlite3.Connection) -> list[OpenDataSnapshot]:
    rows = conn.execute("SELECT payload FROM stock_open_data_snapshots ORDER BY ticker")
    return [OpenDataSnapshot.model_validate_json(row["payload"]) for row in rows]


def load_stock_open_data_snapshot(conn: sqlite3.Connection, ticker: str) -> OpenDataSnapshot | None:
    row = conn.execute(
        "SELECT payload FROM stock_open_data_snapshots WHERE ticker = ?",
        (ticker.upper(),),
    ).fetchone()
    return OpenDataSnapshot.model_validate_json(row["payload"]) if row else None


def load_active_stock_tickers(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT ticker FROM active_stock_symbols ORDER BY ticker")
    return [row["ticker"].upper() for row in rows]


def seed_active_stock_tickers(conn: sqlite3.Connection, tickers: Iterable[str]) -> None:
    if conn.execute("SELECT COUNT(*) FROM active_stock_symbols").fetchone()[0] > 0:
        return
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        """
        INSERT OR IGNORE INTO active_stock_symbols (ticker, added_at)
        VALUES (?, ?)
        """,
        [(ticker.upper(), now) for ticker in tickers if ticker.strip()],
    )


def activate_stock_ticker(conn: sqlite3.Connection, ticker: str) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO active_stock_symbols (ticker, added_at)
        VALUES (?, ?)
        """,
        (ticker.upper(), datetime.now(timezone.utc).isoformat()),
    )


def deactivate_stock_ticker(conn: sqlite3.Connection, ticker: str) -> None:
    conn.execute("DELETE FROM active_stock_symbols WHERE ticker = ?", (ticker.upper(),))


def replace_stock_derived_signals_file(conn: sqlite3.Connection, payload: StockDerivedSignalsFile) -> None:
    conn.executemany(
        """
        INSERT INTO stock_derived_signals (ticker, generated_at, payload)
        VALUES (?, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
            generated_at = excluded.generated_at,
            payload = excluded.payload
        """,
        [(stock.ticker.upper(), stock.generated_at.isoformat(), stock.model_dump_json()) for stock in payload.stocks],
    )


def load_stock_derived_signals(conn: sqlite3.Connection) -> dict[str, StockDerivedSignals]:
    rows = conn.execute("SELECT ticker, payload FROM stock_derived_signals")
    return {row["ticker"].upper(): StockDerivedSignals.model_validate_json(row["payload"]) for row in rows}
