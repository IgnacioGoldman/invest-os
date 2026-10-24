"""Small screening snapshots with complete, independently loadable stock details."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.screening_metrics import build_screening_metrics


def stock_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    summary = dict(snapshot)
    history = snapshot.get("historical_series", {})
    summary["historical_series"] = {
        key: sorted(history.get(key, []), key=lambda row: row["as_of"])[-count:]
        for key, count in (("quarterly_revenue", 12), ("quarterly_fundamentals", 1), ("annual_fundamentals", 2))
    }
    if snapshot.get("industry_relative_strength"):
        summary["industry_relative_strength"] = {
            key: value for key, value in snapshot["industry_relative_strength"].items() if key != "chart"
        }
        summary["industry_relative_strength"]["chart"] = []
    if snapshot.get("company_context"):
        summary["company_context"] = {
            **snapshot["company_context"], "recent_filings": snapshot["company_context"].get("recent_filings", [])[:3],
        }
    summary["detail_path"] = f"/open-data/snapshots/{snapshot['ticker']}.json"
    return summary


def write_stock_assets(data_dir: Path, snapshots: list[dict[str, Any]]) -> None:
    directory = data_dir / "open-data"
    details = directory / "snapshots"
    details.mkdir(parents=True, exist_ok=True)
    snapshots = [{**snapshot, "screening": build_screening_metrics(snapshot)} for snapshot in snapshots]
    for snapshot in snapshots:
        if snapshot.get("detail_path"):
            raise ValueError("Full snapshots are required when publishing stock assets.")
        path = details / f"{snapshot['ticker']}.json"
        path.write_text(json.dumps(snapshot, separators=(",", ":"), allow_nan=False) + "\n")
    summaries = [stock_summary(snapshot) for snapshot in snapshots]
    (directory / "stocks.json").write_text(json.dumps(summaries, separators=(",", ":"), allow_nan=False) + "\n")


def load_full_stock_rows(data_dir: Path) -> list[dict[str, Any]]:
    rows = json.loads((data_dir / "open-data/stocks.json").read_text())
    return [
        json.loads((data_dir / row["detail_path"].lstrip("/")).read_text()) if row.get("detail_path") else row
        for row in rows
    ]
