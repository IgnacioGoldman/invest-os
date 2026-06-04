from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.entry_engine.providers.open_data_provider import OpenDataProvider  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the open/free public-data stock metrics proof-of-concept.")
    parser.add_argument("ticker", help="Only GOOGL is supported by this proof-of-concept.")
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.WARNING))
    snapshot = OpenDataProvider().get_open_data_snapshot(args.ticker)
    print(json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=False))


if __name__ == "__main__":
    main()
