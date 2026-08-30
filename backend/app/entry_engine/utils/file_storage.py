from __future__ import annotations

import json
from pathlib import Path

from app.config import DATA_DIR
from app.entry_engine.models import EntrySnapshotFile
from app.entry_engine.open_data_models import OpenDataSnapshot


ENTRY_DATA_DIR = DATA_DIR / "entry"
OPEN_DATA_STOCK_DIR = DATA_DIR / "stocks" / "open_data"
OPEN_DATA_STOCK_UNIVERSE_PATH = DATA_DIR / "stocks" / "stocks.json"
OPEN_DATA_REQUIRED_GROUPS = ("business_health", "price_opportunity", "valuation")
OPEN_DATA_DISPLAY_MIN_COVERAGE = 80.0


def entry_snapshot_path(date: str, data_dir: Path = ENTRY_DATA_DIR) -> Path:
    return data_dir / f"{date}.json"


def save_entry_snapshot(snapshot: EntrySnapshotFile, data_dir: Path = ENTRY_DATA_DIR) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = entry_snapshot_path(snapshot.date, data_dir)
    path.write_text(
        json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=False),
        encoding="utf-8",
    )
    return path


def load_entry_snapshot(date: str, data_dir: Path = ENTRY_DATA_DIR) -> EntrySnapshotFile:
    path = entry_snapshot_path(date, data_dir)
    return EntrySnapshotFile.model_validate_json(path.read_text(encoding="utf-8"))


def load_latest_entry_snapshot(data_dir: Path = ENTRY_DATA_DIR) -> EntrySnapshotFile | None:
    if not data_dir.exists():
        return None
    files = sorted(data_dir.glob("*.json"), reverse=True)
    if not files:
        return None
    return EntrySnapshotFile.model_validate_json(files[0].read_text(encoding="utf-8"))


def open_data_stock_dir(ticker: str, data_dir: Path = OPEN_DATA_STOCK_DIR) -> Path:
    return data_dir / ticker.upper()


def open_data_stock_snapshot_path(ticker: str, snapshot_date: str, data_dir: Path = OPEN_DATA_STOCK_DIR) -> Path:
    return open_data_stock_dir(ticker, data_dir) / f"{snapshot_date}.json"


def save_open_data_stock_snapshot(snapshot: OpenDataSnapshot, data_dir: Path = OPEN_DATA_STOCK_DIR) -> Path:
    snapshot_date = snapshot.generated_at.date().isoformat()
    ticker_dir = open_data_stock_dir(snapshot.ticker, data_dir)
    ticker_dir.mkdir(parents=True, exist_ok=True)
    path = open_data_stock_snapshot_path(snapshot.ticker, snapshot_date, data_dir)
    payload = json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=False)
    path.write_text(payload, encoding="utf-8")
    (ticker_dir / "latest.json").write_text(payload, encoding="utf-8")
    return path


def load_latest_open_data_stock_snapshot(
    ticker: str,
    data_dir: Path = OPEN_DATA_STOCK_DIR,
) -> OpenDataSnapshot | None:
    ticker_dir = open_data_stock_dir(ticker, data_dir)
    latest_path = ticker_dir / "latest.json"
    if latest_path.exists():
        return OpenDataSnapshot.model_validate_json(latest_path.read_text(encoding="utf-8"))

    if not ticker_dir.exists():
        return None
    files = sorted(path for path in ticker_dir.glob("*.json") if path.name != "latest.json")
    if not files:
        return None
    return OpenDataSnapshot.model_validate_json(files[-1].read_text(encoding="utf-8"))


def open_data_stock_snapshot_coverage(snapshot: OpenDataSnapshot) -> float:
    total = 0
    available = 0
    for group_name in OPEN_DATA_REQUIRED_GROUPS:
        group = getattr(snapshot, group_name)
        for metric in group.values():
            total += 1
            if metric.value is not None and metric.tier != "unavailable_open_free":
                available += 1
    return (available / total * 100) if total else 0


def load_open_data_active_tickers(path: Path = OPEN_DATA_STOCK_UNIVERSE_PATH) -> list[str]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    raw_rows: object
    if isinstance(payload, dict):
        raw_rows = payload.get("tickers") or payload.get("rows") or []
    else:
        raw_rows = payload

    if not isinstance(raw_rows, list):
        return []

    tickers: list[str] = []
    seen: set[str] = set()
    for row in raw_rows:
        if isinstance(row, str):
            ticker = row
        elif isinstance(row, dict):
            ticker = str(row.get("symbol") or row.get("ticker") or "")
        else:
            continue
        normalized = ticker.strip().upper()
        if normalized and normalized not in seen:
            seen.add(normalized)
            tickers.append(normalized)
    return tickers


def is_displayable_open_data_stock_snapshot(
    snapshot: OpenDataSnapshot,
    min_coverage: float = OPEN_DATA_DISPLAY_MIN_COVERAGE,
) -> bool:
    return open_data_stock_snapshot_coverage(snapshot) >= min_coverage


def load_latest_open_data_stock_snapshots(
    data_dir: Path = OPEN_DATA_STOCK_DIR,
    *,
    include_low_fidelity: bool = False,
    active_tickers: set[str] | None = None,
) -> list[OpenDataSnapshot]:
    if not data_dir.exists():
        return []

    if active_tickers is None:
        configured_tickers = load_open_data_active_tickers()
        active_tickers = set(configured_tickers) if configured_tickers else None

    snapshots: list[OpenDataSnapshot] = []
    for ticker_dir in sorted(path for path in data_dir.iterdir() if path.is_dir()):
        if active_tickers is not None and ticker_dir.name.upper() not in active_tickers:
            continue
        snapshot = load_latest_open_data_stock_snapshot(ticker_dir.name, data_dir)
        if snapshot is not None and (include_low_fidelity or is_displayable_open_data_stock_snapshot(snapshot)):
            snapshots.append(snapshot)
    snapshots.sort(key=lambda snapshot: snapshot.ticker)
    return snapshots
