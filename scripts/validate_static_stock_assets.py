"""Check the committed screening index and every linked stock-detail asset."""
import argparse
import json
from pathlib import Path

from validate_static_stock_refresh import _validate_stock_details, _universe_tickers

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "frontend/public/data")
    args = parser.parse_args()
    rows = json.loads((args.data_dir / "open-data/stocks.json").read_text())
    universe = json.loads((args.data_dir / "stocks/universe.json").read_text())
    meta = json.loads((args.data_dir / "meta.json").read_text())
    errors = []
    symbols = [r["ticker"] for r in rows]
    if len(set(symbols)) != len(symbols) or set(symbols) != _universe_tickers(universe):
        errors.append("Screening index contains duplicate, missing or unexpected stocks.")
    if meta.get("stock_count") != len(rows) or set(meta.get("tickers", [])) != set(symbols):
        errors.append("Stock metadata does not match the screening index.")
    for row in rows:
        _validate_stock_details(row["ticker"], row, args.data_dir, errors)
    print(json.dumps({"valid": not errors, "stock_count": len(rows),
                      "detail_count": sum(bool(r.get("detail_path")) for r in rows), "errors": errors}, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
