"""Rebuild revenue history from cached facts and durable issuer reports, preserving prices."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.entry_engine.open_data_metrics import _quarterly_revenue_rows
from app.entry_engine.open_data_models import OpenDataSnapshot
from app.entry_engine.providers.issuer_revenue import load_issuer_revenue, supplement_issuer_revenue
from app.services.revenue_growth_momentum import calculate_revenue_growth_momentum
from app.services.storage import connect, replace_stock_open_data_snapshot


def repair_revenue_snapshot(snapshot: OpenDataSnapshot, facts: dict) -> OpenDataSnapshot:
    quarters = _quarterly_revenue_rows(facts, datetime.now(timezone.utc).date().isoformat())
    if not quarters:
        raise ValueError(f"{snapshot.ticker}: source has no revenue quarters; refusing to erase history")
    previous = snapshot.historical_series.get("quarterly_revenue", [])
    if previous and max(r.as_of for r in previous) > quarters[-1].as_of:
        raise ValueError(f"{snapshot.ticker}: cached source is older than the saved revenue history")
    latest = quarters[-1].metrics["revenue_growth_yoy"]
    return snapshot.model_copy(update={
        "historical_series": {**snapshot.historical_series, "quarterly_revenue": quarters},
        "business_health": {**snapshot.business_health, "revenue_growth_yoy": latest},
        "metrics": {**snapshot.metrics, "revenue_growth_yoy": latest},
        "revenue_history_version": 1,
        "revenue_history_checked_at": datetime.now(timezone.utc),
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts-dir", type=Path, default=ROOT / ".cache/open_data")
    parser.add_argument("--output", type=Path, default=Path("/tmp/revenue-history-backfill.json"))
    parser.add_argument("--apply", action="store_true", help="Save rebuilt snapshots to SQLite and the static export.")
    args = parser.parse_args()
    export = ROOT / "frontend/public/data/open-data/stocks.json"
    rows = json.loads(export.read_text())
    report, output = [], []
    for row in rows:
        snapshot = OpenDataSnapshot.model_validate(row)
        before = calculate_revenue_growth_momentum(row)
        path = args.facts_dir / f"sec_companyfacts_CIK{snapshot.cik:010d}.json" if snapshot.cik else None
        if path is not None and path.exists():
            facts = json.loads(path.read_text())
            seed = load_issuer_revenue(snapshot.ticker)
            if seed:
                facts = supplement_issuer_revenue(facts, seed)
            snapshot = repair_revenue_snapshot(snapshot, facts)
        else:
            snapshot = snapshot.model_copy(update={"revenue_history_version": 1,
                                                  "revenue_history_checked_at": datetime.now(timezone.utc)})
        payload = snapshot.model_dump(mode="json")
        after = calculate_revenue_growth_momentum(payload)
        if before["label"] != "Unclear" and after["label"] == "Unclear":
            raise ValueError(f"{snapshot.ticker}: rebuild would regress momentum: {after['reason']}")
        report.append({"ticker":snapshot.ticker, "before":before, "after":after,
                       "latest_growth":snapshot.business_health["revenue_growth_yoy"].value})
        output.append(payload)
    args.output.write_text(json.dumps({"symbols":report}, indent=2) + "\n")
    if args.apply:
        with connect(ROOT / "data") as conn:
            for row in output:
                replace_stock_open_data_snapshot(conn, OpenDataSnapshot.model_validate(row))
            conn.commit()
        export.write_text(json.dumps(output, indent=2) + "\n")
    for row in report:
        if row["before"]["label"] == "Unclear":
            print(row["ticker"], "Unclear ->", row["after"]["label"], row["after"]["change"])
    print(f"Calculable momentum: {sum(r['after']['label'] != 'Unclear' for r in report)}/{len(report)}")


if __name__ == "__main__":
    main()
