"""Audit current fundamental gaps and the latest six revenue-growth quarters."""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.revenue_growth_momentum import calculate_revenue_growth_momentum


def audit(rows: list[dict]) -> dict:
    result = []
    for row in sorted(rows, key=lambda r: r["ticker"]):
        quarters = row.get("historical_series", {}).get("quarterly_revenue", [])
        momentum = calculate_revenue_growth_momentum(row)
        missing, not_meaningful = {}, {}
        for group in ("business_health", "valuation"):
            for key, metric in row[group].items():
                if key == "eps_growth_yoy":  # Deprecated alias; audit the GAAP metric.
                    continue
                if metric.get("value") is not None:
                    continue
                note = metric.get("notes", "")
                bucket = not_meaningful if any(term in note.lower() for term in ("not meaningful", "loss-making", "positive 3-year eps", "positive eps", "crossed from")) else missing
                bucket[f"{group}.{key}"] = note
        result.append({
            "ticker": row["ticker"],
            "revenue_growth_observations": sum(q["metrics"].get("revenue_growth_yoy", {}).get("value") is not None for q in quarters),
            "latest_revenue_period": quarters[-1]["period"] if quarters else None,
            "revenue_momentum": momentum,
            "missing_inputs": missing,
            "not_meaningful": not_meaningful,
        })
    return {"audited_on": date.today().isoformat(), "symbol_count": len(result), "symbols": result}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "frontend/public/data/open-data/stocks.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(json.loads(args.input.read_text()))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    for row in report["symbols"]:
        if row["revenue_momentum"]["label"] == "Unclear" or row["missing_inputs"]:
            print(f"{row['ticker']}: revenue YoY={row['revenue_growth_observations']}; missing={', '.join(row['missing_inputs']) or 'none'}")
    print(f"Audited {report['symbol_count']} symbols")


if __name__ == "__main__":
    main()
