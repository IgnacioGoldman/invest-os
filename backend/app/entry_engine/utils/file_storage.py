from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import DATA_DIR


OPEN_DATA_STOCK_UNIVERSE_PATH = DATA_DIR / "stocks" / "stocks.json"


def _normalize_universe_row(row: Any) -> dict[str, Any] | None:
    if isinstance(row, str):
        symbol = row
        item: dict[str, Any] = {"symbol": symbol}
    elif isinstance(row, dict):
        symbol = str(row.get("symbol") or row.get("ticker") or "")
        item = dict(row)
        item["symbol"] = symbol
    else:
        return None

    item["symbol"] = str(item["symbol"]).strip().upper()
    if not item["symbol"]:
        return None
    return item


def load_stock_universe(path: Path = OPEN_DATA_STOCK_UNIVERSE_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    metadata_by_symbol: dict[str, dict[str, Any]] = {}
    if isinstance(payload, dict):
        raw_rows = payload.get("tickers") or payload.get("rows") or []
        raw_metadata = payload.get("rows") if payload.get("tickers") is not None else payload.get("metadata")
        if isinstance(raw_metadata, list):
            for raw_row in raw_metadata:
                metadata = _normalize_universe_row(raw_row)
                if metadata is not None:
                    metadata_by_symbol[metadata["symbol"]] = metadata
    else:
        raw_rows = payload

    if not isinstance(raw_rows, list):
        return []

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_row in raw_rows:
        row = _normalize_universe_row(raw_row)
        if row is None or row["symbol"] in seen:
            continue
        if row["symbol"] in metadata_by_symbol:
            row = {**metadata_by_symbol[row["symbol"]], **row}
        seen.add(row["symbol"])
        rows.append(row)
    return rows


def load_stock_universe_tickers(path: Path = OPEN_DATA_STOCK_UNIVERSE_PATH) -> list[str]:
    return [row["symbol"] for row in load_stock_universe(path)]
