from __future__ import annotations

import argparse
import logging

from app.entry_engine.build_entry_snapshot import build_entry_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a factual stock entry snapshot.")
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--date", default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    snapshot = build_entry_snapshot(limit=args.limit, date=args.date)
    print(f"Stored {snapshot.count} stocks for {snapshot.date}; failed={len(snapshot.failed_tickers)}")


if __name__ == "__main__":
    main()

