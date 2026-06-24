from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, TypeVar

from pydantic import BaseModel

from app.models import BinanceLedgerEvent, CashBalance, FxRate, HistoricalPrice, Holding, MarketPrice, Order, SourceResult, SourceSyncStatus


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

        CREATE TABLE IF NOT EXISTS market_prices (
            symbol TEXT NOT NULL,
            currency TEXT NOT NULL,
            price REAL NOT NULL,
            source TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (symbol, currency)
        );

        CREATE TABLE IF NOT EXISTS fx_rates (
            currency TEXT NOT NULL,
            base_currency TEXT NOT NULL,
            rate REAL NOT NULL,
            source TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (currency, base_currency)
        );

        CREATE TABLE IF NOT EXISTS ledger_events (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            payload TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS historical_prices (
            asset TEXT NOT NULL,
            currency TEXT NOT NULL,
            priced_at TEXT NOT NULL,
            price REAL NOT NULL,
            source TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (asset, currency, priced_at)
        );

        CREATE TABLE IF NOT EXISTS recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            generated_at TEXT NOT NULL,
            position INTEGER NOT NULL,
            payload TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS recommendation_followups (
            id TEXT PRIMARY KEY,
            recommendation_key TEXT NOT NULL,
            created_at TEXT NOT NULL,
            payload TEXT NOT NULL
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


def replace_order_history(conn: sqlite3.Connection, source: str, orders: Iterable[Order]) -> None:
    _replace_rows(conn, "order_history", source, orders)


def replace_ledger_events(conn: sqlite3.Connection, source: str, events: Iterable[BinanceLedgerEvent]) -> None:
    _replace_rows(conn, "ledger_events", source, events)


def load_ledger_events(conn: sqlite3.Connection) -> list[BinanceLedgerEvent]:
    return _load_rows(conn, "ledger_events", BinanceLedgerEvent)


def replace_market_prices(conn: sqlite3.Connection, prices: Iterable[MarketPrice], *, clear: bool = False) -> None:
    if clear:
        conn.execute("DELETE FROM market_prices")
    conn.executemany(
        """
        INSERT INTO market_prices (symbol, currency, price, source, fetched_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(symbol, currency) DO UPDATE SET
            price = excluded.price,
            source = excluded.source,
            fetched_at = excluded.fetched_at
        """,
        [
            (
                price.symbol.upper(),
                price.currency.upper(),
                price.price,
                price.source,
                price.fetched_at.isoformat(),
            )
            for price in prices
        ],
    )


def replace_fx_rates(conn: sqlite3.Connection, rates: Iterable[FxRate]) -> None:
    conn.executemany(
        """
        INSERT INTO fx_rates (currency, base_currency, rate, source, fetched_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(currency, base_currency) DO UPDATE SET
            rate = excluded.rate,
            source = excluded.source,
            fetched_at = excluded.fetched_at
        """,
        [
            (
                rate.currency.upper(),
                rate.base_currency.upper(),
                rate.rate,
                rate.source,
                rate.fetched_at.isoformat(),
            )
            for rate in rates
        ],
    )


def load_market_prices(conn: sqlite3.Connection) -> dict[tuple[str, str], MarketPrice]:
    rows = conn.execute("SELECT symbol, currency, price, source, fetched_at FROM market_prices")
    return {
        (row["symbol"].upper(), row["currency"].upper()): MarketPrice(
            symbol=row["symbol"],
            currency=row["currency"],
            price=row["price"],
            source=row["source"],
            fetched_at=row["fetched_at"],
        )
        for row in rows
    }


def replace_historical_prices(conn: sqlite3.Connection, prices: Iterable[HistoricalPrice]) -> None:
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
                price.asset.upper(),
                price.currency.upper(),
                price.priced_at.isoformat(),
                price.price,
                price.source,
                price.fetched_at.isoformat(),
            )
            for price in prices
        ],
    )


def load_historical_prices(conn: sqlite3.Connection) -> dict[tuple[str, str, str], HistoricalPrice]:
    rows = conn.execute("SELECT asset, currency, priced_at, price, source, fetched_at FROM historical_prices")
    return {
        (row["asset"].upper(), row["currency"].upper(), row["priced_at"]): HistoricalPrice(
            asset=row["asset"],
            currency=row["currency"],
            priced_at=row["priced_at"],
            price=row["price"],
            source=row["source"],
            fetched_at=row["fetched_at"],
        )
        for row in rows
    }


def load_fx_rates(conn: sqlite3.Connection, base_currency: str) -> dict[str, FxRate]:
    base_currency = base_currency.upper()
    rows = conn.execute(
        "SELECT currency, base_currency, rate, source, fetched_at FROM fx_rates WHERE base_currency = ?",
        (base_currency,),
    )
    rates = {
        row["currency"].upper(): FxRate(
            currency=row["currency"],
            base_currency=row["base_currency"],
            rate=row["rate"],
            source=row["source"],
            fetched_at=row["fetched_at"],
        )
        for row in rows
    }
    rates[base_currency] = FxRate(currency=base_currency, base_currency=base_currency, rate=1.0, source="system")
    rates["BASE"] = FxRate(currency="BASE", base_currency=base_currency, rate=1.0, source="system")
    return rates


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
    for source in ["manual", "binance", "binance_ledger", "ibkr", "ibkr_history", "market_data", "fx"]:
        if source not in seen:
            statuses.append(SourceSyncStatus(source=source))
    return statuses


def replace_recommendations(conn: sqlite3.Connection, generated_at: datetime, recommendations: Iterable[BaseModel]) -> None:
    conn.execute("DELETE FROM recommendations")
    conn.executemany(
        "INSERT INTO recommendations (generated_at, position, payload) VALUES (?, ?, ?)",
        [
            (generated_at.isoformat(), position, recommendation.model_dump_json())
            for position, recommendation in enumerate(recommendations)
        ],
    )


def load_recommendation_payloads(conn: sqlite3.Connection) -> list[str]:
    return [
        row["payload"]
        for row in conn.execute("SELECT payload FROM recommendations ORDER BY position, id")
    ]


def load_recommendations_generated_at(conn: sqlite3.Connection) -> datetime | None:
    row = conn.execute("SELECT MAX(generated_at) AS generated_at FROM recommendations").fetchone()
    if row is None or row["generated_at"] is None:
        return None
    return datetime.fromisoformat(row["generated_at"])


def save_recommendation_followup(conn: sqlite3.Connection, followup: BaseModel) -> None:
    followup_id = getattr(followup, "follow_up_id", None)
    recommendation_key = getattr(followup, "recommendation_key", None)
    generated_at = getattr(followup, "generated_at", datetime.now(timezone.utc))
    if not followup_id or not recommendation_key:
        raise ValueError("Recommendation follow-up requires follow_up_id and recommendation_key.")

    existing = conn.execute(
        "SELECT created_at FROM recommendation_followups WHERE id = ?",
        (followup_id,),
    ).fetchone()
    if existing is None:
        conn.execute(
            """
            INSERT INTO recommendation_followups (id, recommendation_key, created_at, payload)
            VALUES (?, ?, ?, ?)
            """,
            (followup_id, recommendation_key, generated_at.isoformat(), followup.model_dump_json()),
        )
        return

    conn.execute(
        """
        UPDATE recommendation_followups
        SET recommendation_key = ?, payload = ?
        WHERE id = ?
        """,
        (recommendation_key, followup.model_dump_json(), followup_id),
    )


def load_recommendation_followup_payload(conn: sqlite3.Connection, followup_id: str) -> str | None:
    row = conn.execute(
        "SELECT payload FROM recommendation_followups WHERE id = ?",
        (followup_id,),
    ).fetchone()
    return row["payload"] if row else None


def load_recommendation_followup_payloads(conn: sqlite3.Connection) -> list[str]:
    return [
        row["payload"]
        for row in conn.execute(
            "SELECT payload FROM recommendation_followups ORDER BY created_at, id"
        )
    ]
