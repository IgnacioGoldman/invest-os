from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.entry_engine.open_data_models import HistoricalPricePoint  # noqa: E402
from app.entry_engine.utils.file_storage import load_stock_universe  # noqa: E402
from app.services.storage import DB_FILE  # noqa: E402


DEFAULT_OUTPUT_DIR = ROOT / "frontend" / "public" / "data"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _load_snapshot_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT ticker, payload
        FROM stock_open_data_snapshots
        ORDER BY ticker
        """
    )
    snapshots: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row["payload"])
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            payload["ticker"] = str(payload.get("ticker") or row["ticker"]).upper()
            snapshots.append(payload)
    return snapshots


def _load_active_tickers(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT ticker FROM active_stock_symbols ORDER BY ticker")
    return {str(row["ticker"]).upper() for row in rows}


def _load_price_history(conn: sqlite3.Connection, ticker: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT priced_at, price, source
        FROM historical_prices
        WHERE asset = ? AND currency = 'USD'
        ORDER BY priced_at
        """,
        (ticker.upper(),),
    )
    points: list[dict[str, Any]] = []
    for row in rows:
        try:
            point = HistoricalPricePoint(
                date=str(row["priced_at"]).split("T", 1)[0],
                close=float(row["price"]),
                source=str(row["source"]),
            )
        except (TypeError, ValueError):
            continue
        points.append(point.model_dump(mode="json"))
    return points


def _build_universe_rows(universe_path: Path, loaded: set[str], active: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in load_stock_universe(universe_path):
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        rows.append(
            {
                "symbol": symbol,
                "name": row.get("name"),
                "quote_type": row.get("quote_type"),
                "region": row.get("region"),
                "country": row.get("country"),
                "sector": row.get("sector"),
                "industry": row.get("industry"),
                "active": symbol in active,
                "loaded": symbol in loaded,
            }
        )
    return rows


def export_static_site_data(data_dir: Path, output_dir: Path, universe_path: Path) -> None:
    db_path = data_dir / DB_FILE
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {db_path}")

    if output_dir.exists():
        shutil.rmtree(output_dir)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        snapshots = _load_snapshot_rows(conn)
        active = _load_active_tickers(conn)
        if active:
            snapshots = [snapshot for snapshot in snapshots if snapshot["ticker"] in active]
        loaded = {snapshot["ticker"] for snapshot in snapshots}

        _write_json(output_dir / "open-data" / "stocks.json", snapshots)
        _write_json(output_dir / "stocks" / "universe.json", _build_universe_rows(universe_path, loaded, active or loaded))
        _write_json(
            output_dir / "meta.json",
            {
                "source": "github_actions_static_export",
                "stock_count": len(snapshots),
                "tickers": sorted(loaded),
            },
        )
        for ticker in sorted(loaded):
            _write_json(output_dir / "open-data" / "price-history" / f"{ticker}.json", _load_price_history(conn, ticker))
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Export SQLite stock data into static JSON files for GitHub Pages.")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--universe-file", type=Path, default=ROOT / "data" / "stocks" / "stocks.json")
    args = parser.parse_args()

    data_dir = args.data_dir if args.data_dir.is_absolute() else ROOT / args.data_dir
    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    universe_path = args.universe_file if args.universe_file.is_absolute() else ROOT / args.universe_file
    export_static_site_data(data_dir, output_dir, universe_path)
    print(f"Exported static site data to {output_dir.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
