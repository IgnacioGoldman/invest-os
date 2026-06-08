from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.entry_engine.utils.file_storage import load_latest_open_data_stock_snapshots  # noqa: E402
from app.services.stock_derived_signals import build_stock_derived_signals_file  # noqa: E402


DEFAULT_OUTPUT_DIR = ROOT / "data" / "stocks" / "derived_signals"


def write_derived_signals(output_dir: Path, *, include_low_fidelity: bool = False) -> Path:
    snapshots = load_latest_open_data_stock_snapshots(include_low_fidelity=include_low_fidelity)
    payload = build_stock_derived_signals_file(snapshots)
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_date = payload.generated_at.date().isoformat()
    text = json.dumps(payload.model_dump(mode="json"), indent=2, sort_keys=False)
    dated_path = output_dir / f"{snapshot_date}.json"
    latest_path = output_dir / "latest.json"
    dated_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return latest_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build deterministic derived stock signals from saved open-data snapshots.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Where to write latest.json and the dated derived-signal file.",
    )
    parser.add_argument(
        "--include-low-fidelity",
        action="store_true",
        help="Include snapshots that do not meet the default display coverage threshold.",
    )
    args = parser.parse_args()

    latest_path = write_derived_signals(
        args.output_dir,
        include_low_fidelity=args.include_low_fidelity,
    )
    relative = latest_path.relative_to(ROOT) if latest_path.is_relative_to(ROOT) else latest_path
    print(f"Wrote {relative}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
