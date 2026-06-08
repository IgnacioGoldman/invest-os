from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.asset_opportunities import (  # noqa: E402
    ASSET_OPPORTUNITY_DIR,
    build_asset_opportunities_file,
    save_asset_opportunities,
)
from app.snapshot import get_portfolio_snapshot  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build deterministic ETF, commodity-proxy, and crypto opportunity signals.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ASSET_OPPORTUNITY_DIR,
        help="Where to write latest.json and the dated derived-signal file.",
    )
    parser.add_argument("--skip-etfs", action="store_true", help="Skip ETF opportunity signals.")
    parser.add_argument("--skip-commodities", action="store_true", help="Skip commodity-proxy opportunity signals.")
    parser.add_argument("--skip-crypto", action="store_true", help="Skip crypto opportunity signals.")
    parser.add_argument(
        "--no-portfolio-fit",
        action="store_true",
        help="Do not use the current cached portfolio snapshot for portfolio_fit_score.",
    )
    args = parser.parse_args()

    portfolio_snapshot = None if args.no_portfolio_fit else get_portfolio_snapshot()
    payload = build_asset_opportunities_file(
        portfolio_snapshot=portfolio_snapshot,
        include_etfs=not args.skip_etfs,
        include_commodities=not args.skip_commodities,
        include_crypto=not args.skip_crypto,
    )
    latest_path = save_asset_opportunities(payload, args.output_dir)
    relative = latest_path.relative_to(ROOT) if latest_path.is_relative_to(ROOT) else latest_path
    print(f"Wrote {relative} with {payload.count} assets")
    if payload.collection_errors:
        print(f"Collection errors: {len(payload.collection_errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
