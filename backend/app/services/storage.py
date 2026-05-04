from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, TypeVar

from pydantic import BaseModel

from app.models import CashBalance, Holding, Order, SourceResult, SourceSyncStatus


DB_FILE = "invest_os.sqlite"
T = TypeVar("T", bound=BaseModel)


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
        CREATE TABLE IF NOT EXISTS holdings (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            payload TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cash_balances (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            payload TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS open_orders (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            payload TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS order_history (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            payload TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS source_sync_status (
            source TEXT PRIMARY KEY,
            last_synced_at TEXT,
            status TEXT NOT NULL,
            warning TEXT
        );
        """
    )
    conn.commit()


def _replace_rows(conn: sqlite3.Connection, table: str, source: str, rows: Iterable[BaseModel]) -> None:
    conn.execute(f"DELETE FROM {table} WHERE source = ?", (source,))
    conn.executemany(
        f"INSERT OR REPLACE INTO {table} (id, source, payload) VALUES (?, ?, ?)",
        [(row.id, source, row.model_dump_json()) for row in rows],
    )


def replace_source_result(
    conn: sqlite3.Connection,
    source: str,
    result: SourceResult,
    *,
    holdings: bool = True,
    cash_balances: bool = True,
    open_orders: bool = True,
    order_history: bool = True,
) -> None:
    if holdings:
        _replace_rows(conn, "holdings", source, result.holdings)
    if cash_balances:
        _replace_rows(conn, "cash_balances", source, result.cash_balances)
    if open_orders:
        _replace_rows(conn, "open_orders", source, result.open_orders)
    if order_history:
        _replace_rows(conn, "order_history", source, result.order_history)


def update_sync_status(conn: sqlite3.Connection, source: str, status: str, warnings: list[str]) -> None:
    warning = "\n".join(warnings) if warnings else None
    conn.execute(
        """
        INSERT INTO source_sync_status (source, last_synced_at, status, warning)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(source) DO UPDATE SET
            last_synced_at = excluded.last_synced_at,
            status = excluded.status,
            warning = excluded.warning
        """,
        (source, datetime.now(timezone.utc).isoformat(), status, warning),
    )


def _load_rows(conn: sqlite3.Connection, table: str, model: type[T]) -> list[T]:
    return [model.model_validate_json(row["payload"]) for row in conn.execute(f"SELECT payload FROM {table}")]


def load_holdings(conn: sqlite3.Connection) -> list[Holding]:
    return _load_rows(conn, "holdings", Holding)


def load_cash_balances(conn: sqlite3.Connection) -> list[CashBalance]:
    return _load_rows(conn, "cash_balances", CashBalance)


def load_open_orders(conn: sqlite3.Connection) -> list[Order]:
    return _load_rows(conn, "open_orders", Order)


def load_order_history(conn: sqlite3.Connection) -> list[Order]:
    return _load_rows(conn, "order_history", Order)


def load_sync_status(conn: sqlite3.Connection) -> list[SourceSyncStatus]:
    statuses = [
        SourceSyncStatus(
            source=row["source"],
            last_synced_at=row["last_synced_at"],
            status=row["status"],
            warning=row["warning"],
        )
        for row in conn.execute("SELECT source, last_synced_at, status, warning FROM source_sync_status ORDER BY source")
    ]
    seen = {status.source for status in statuses}
    for source in ["manual", "binance", "ibkr", "ibkr_history"]:
        if source not in seen:
            statuses.append(SourceSyncStatus(source=source))
    return statuses
