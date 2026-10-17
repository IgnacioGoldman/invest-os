"""Rebuild industry context independently, including existing static exports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.entry_engine.open_data_models import HistoricalPricePoint, OpenDataSnapshot  # noqa: E402
from app.services.industry_strength import enrich_industry_strength, rebuild_saved_industry_strength  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--static-dir", type=Path, default=ROOT / "frontend/public/data")
    parser.add_argument("--no-fetch", action="store_true", help="Use saved benchmark prices without a network request.")
    args = parser.parse_args()
    updated = rebuild_saved_industry_strength(args.data_dir, fetch_benchmark=not args.no_fetch)
    path = args.static_dir / "open-data/stocks.json"
    if path.exists():
        # Static export may be newer than SQLite; preserve its prices and facts.
        raw_rows = json.loads(path.read_text())
        rows = [OpenDataSnapshot.model_validate(row) for row in raw_rows]
        histories = {}
        for row in rows:
            history_path = args.static_dir / f"open-data/price-history/{row.ticker}.json"
            histories[row.ticker] = [HistoricalPricePoint.model_validate(p) for p in json.loads(history_path.read_text())] if history_path.exists() else []
        updated = enrich_industry_strength(rows, histories, args.data_dir)
        temporary = path.with_suffix(".json.tmp")
        by_ticker = {row.ticker: row.industry_relative_strength for row in updated}
        for row in raw_rows:
            row["industry_relative_strength"] = by_ticker[row["ticker"]]
        temporary.write_text(json.dumps(raw_rows, indent=2) + "\n")
        temporary.replace(path)
    available = [s.ticker for s in updated if s.industry_relative_strength and s.industry_relative_strength["value"] is not None]
    print(json.dumps({"stocks": len(updated), "available": available, "unclear": len(updated) - len(available)}))


if __name__ == "__main__":
    main()
