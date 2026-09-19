from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.config import DATA_DIR, Settings
from app.entry_engine.providers.open_data_provider import OpenDataProvider
from app.services.open_data_stock_store import load_active_tickers, load_db_or_backfill_stock_snapshots, save_stock_snapshot_to_db
from app.services.storage import connect, replace_stock_derived_signals_file
from app.services.stock_derived_signals import StockDerivedSignalsFile, build_stock_derived_signals_file


ExplorationProgressCallback = Callable[[str, str, int, int], None]

STOCK_DERIVED_SIGNALS_DIR = DATA_DIR / "stocks" / "derived_signals"
MAX_STOCK_REFRESH_WORKERS = 6


def _save_stock_derived_signals(
    payload: StockDerivedSignalsFile,
    data_dir: Path = STOCK_DERIVED_SIGNALS_DIR,
) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload.model_dump(mode="json"), indent=2, sort_keys=False)
    dated_path = data_dir / f"{payload.generated_at.date().isoformat()}.json"
    latest_path = data_dir / "latest.json"
    dated_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return latest_path


def _refresh_stock_symbol(settings: Settings, ticker: str) -> str:
    provider = OpenDataProvider(force_refresh=True, include_filing_details=False)
    snapshot = provider.get_open_data_snapshot(ticker)
    save_stock_snapshot_to_db(settings, snapshot)
    return snapshot.ticker


def _compact_failures(failures: list[str], *, label: str) -> list[str]:
    if not failures:
        return []
    preview = ", ".join(failures[:8])
    suffix = f", +{len(failures) - 8} more" if len(failures) > 8 else ""
    return [f"{label}: {preview}{suffix}"]


def _is_snapshot_fresh_today(generated_at: datetime) -> bool:
    generated = generated_at if generated_at.tzinfo else generated_at.replace(tzinfo=timezone.utc)
    return generated.astimezone(timezone.utc).date() == datetime.now(timezone.utc).date()


def refresh_exploration_data(
    settings: Settings,
    progress: ExplorationProgressCallback | None = None,
) -> list[str]:
    warnings: list[str] = []
    active_tickers = load_active_tickers(settings)
    current_stock_snapshots = load_db_or_backfill_stock_snapshots(settings)
    current_by_ticker = {snapshot.ticker: snapshot for snapshot in current_stock_snapshots}
    missing_tickers = [ticker for ticker in active_tickers if ticker not in current_by_ticker]
    stale_existing_tickers = [
        snapshot.ticker
        for snapshot in current_stock_snapshots
        if not _is_snapshot_fresh_today(snapshot.generated_at)
    ]
    stale_tickers = [*missing_tickers, *stale_existing_tickers]
    skipped_fresh = len(current_stock_snapshots) - len(stale_existing_tickers)
    total_steps = max(1, len(stale_tickers)) + 1

    if progress:
        progress(
            "exploration_beta",
            f"Refreshing {len(stale_tickers)} stale stock symbols; skipping {skipped_fresh} fetched today",
            0,
            total_steps,
        )

    stock_failures: list[str] = []
    if stale_tickers:
        workers = min(MAX_STOCK_REFRESH_WORKERS, len(stale_tickers))
        completed = 0
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_by_ticker = {executor.submit(_refresh_stock_symbol, settings, ticker): ticker for ticker in stale_tickers}
            for future in as_completed(future_by_ticker):
                ticker = future_by_ticker[future]
                completed += 1
                try:
                    future.result()
                except Exception as exc:
                    stock_failures.append(f"{ticker} ({exc})")
                if progress:
                    progress("exploration_beta", f"Refreshed {completed}/{len(stale_tickers)} stale stock symbols", completed, total_steps)
    elif not current_stock_snapshots:
        warnings.append("No stock rows were available to refresh.")

    warnings.extend(_compact_failures(stock_failures, label="Stock refresh failures"))

    if progress:
        progress("exploration_beta_signals", "Rebuilding stock derived signals", max(1, len(stale_tickers)) + 1, total_steps)
    refreshed_stock_snapshots = load_db_or_backfill_stock_snapshots(settings)
    stock_signals = build_stock_derived_signals_file(refreshed_stock_snapshots)
    _save_stock_derived_signals(stock_signals)
    with connect(settings.data_dir) as conn:
        for snapshot in refreshed_stock_snapshots:
            save_stock_snapshot_to_db(settings, snapshot)
        replace_stock_derived_signals_file(conn, stock_signals)
        conn.commit()

    return warnings
