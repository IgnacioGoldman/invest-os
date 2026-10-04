from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.entry_engine.open_data_models import HistoricalPricePoint, OpenDataSnapshot
from app.services.stock_derived_signals import StockDerivedSignals, StockDerivedSignalsFile


DB_FILE = "invest_os.sqlite"
DEPRECATED_STOCK_METRIC_KEYS = frozenset({"eps_adjusted_growth_yoy", "eps_alignment"})


def db_path(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / DB_FILE


def connect(data_dir: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(data_dir))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def strip_deprecated_stock_metrics_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for section in ("business_health", "metrics"):
        metrics = payload.get(section)
        if isinstance(metrics, dict):
            for key in DEPRECATED_STOCK_METRIC_KEYS:
                metrics.pop(key, None)
    return payload


def _strip_deprecated_stock_metrics(snapshot: OpenDataSnapshot) -> OpenDataSnapshot:
    business_health = {
        key: value for key, value in snapshot.business_health.items() if key not in DEPRECATED_STOCK_METRIC_KEYS
    }
    metrics = {key: value for key, value in snapshot.metrics.items() if key not in DEPRECATED_STOCK_METRIC_KEYS}
    return snapshot.model_copy(update={"business_health": business_health, "metrics": metrics})


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

        CREATE TABLE IF NOT EXISTS stock_sec_refresh_state (
            ticker TEXT PRIMARY KEY,
            cik INTEGER,
            accession_number TEXT,
            filing_date TEXT,
            form TEXT,
            checked_at TEXT NOT NULL
        );
        """
    )
    _ensure_historical_price_columns(conn)


def _ensure_historical_price_columns(conn: sqlite3.Connection) -> None:
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(historical_prices)")}
    for column, column_type in {
        "high": "REAL",
        "low": "REAL",
        "volume": "REAL",
    }.items():
        if column not in columns:
            conn.execute(f"ALTER TABLE historical_prices ADD COLUMN {column} {column_type}")


def replace_stock_price_history(conn: sqlite3.Connection, ticker: str, points: Iterable[HistoricalPricePoint]) -> None:
    fetched_at = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        """
        INSERT INTO historical_prices (asset, currency, priced_at, price, source, fetched_at, high, low, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(asset, currency, priced_at) DO UPDATE SET
            price = excluded.price,
            source = excluded.source,
            fetched_at = excluded.fetched_at,
            high = excluded.high,
            low = excluded.low,
            volume = excluded.volume
        """,
        [
            (
                ticker.upper(),
                "USD",
                f"{point.date}T00:00:00+00:00" if "T" not in point.date else point.date,
                point.close,
                point.source,
                fetched_at,
                point.high,
                point.low,
                point.volume,
            )
            for point in points
            if point.close > 0
        ],
    )


def load_stock_price_history(conn: sqlite3.Connection, ticker: str) -> list[HistoricalPricePoint]:
    rows = conn.execute(
        """
        SELECT priced_at, price, source, high, low, volume
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
            high=row["high"],
            low=row["low"],
            volume=row["volume"],
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
    snapshot = _strip_deprecated_stock_metrics(snapshot)
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
    snapshots: list[OpenDataSnapshot] = []
    for row in rows:
        payload = json.loads(row["payload"])
        if isinstance(payload, dict):
            strip_deprecated_stock_metrics_payload(payload)
        snapshots.append(OpenDataSnapshot.model_validate(payload))
    return snapshots


def load_stock_open_data_snapshot(conn: sqlite3.Connection, ticker: str) -> OpenDataSnapshot | None:
    row = conn.execute(
        "SELECT payload FROM stock_open_data_snapshots WHERE ticker = ?",
        (ticker.upper(),),
    ).fetchone()
    if row is None:
        return None
    payload = json.loads(row["payload"])
    if isinstance(payload, dict):
        strip_deprecated_stock_metrics_payload(payload)
    return OpenDataSnapshot.model_validate(payload)


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


def load_stock_sec_refresh_state(conn: sqlite3.Connection, ticker: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT ticker, cik, accession_number, filing_date, form, checked_at
        FROM stock_sec_refresh_state
        WHERE ticker = ?
        """,
        (ticker.upper(),),
    ).fetchone()


def replace_stock_sec_refresh_state(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    cik: int | None,
    accession_number: str | None,
    filing_date: str | None,
    form: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO stock_sec_refresh_state (ticker, cik, accession_number, filing_date, form, checked_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
            cik = excluded.cik,
            accession_number = excluded.accession_number,
            filing_date = excluded.filing_date,
            form = excluded.form,
            checked_at = excluded.checked_at
        """,
        (
            ticker.upper(),
            cik,
            accession_number,
            filing_date,
            form,
            datetime.now(timezone.utc).isoformat(),
        ),
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
