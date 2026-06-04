from __future__ import annotations

import json
from pathlib import Path

from app.config import DATA_DIR
from app.entry_engine.models import EntrySnapshotFile
from app.entry_engine.open_data_models import OpenDataSnapshot


ENTRY_DATA_DIR = DATA_DIR / "entry"
OPEN_DATA_STOCK_DIR = DATA_DIR / "stocks" / "open_data"


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
