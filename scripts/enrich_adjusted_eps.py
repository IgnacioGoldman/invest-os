from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.entry_engine.open_data_metrics import _eps_alignment_metric  # noqa: E402
from app.entry_engine.open_data_models import OpenDataMetric, OpenDataSnapshot  # noqa: E402
from app.entry_engine.providers.open_data_provider import JsonFileCache, OpenDataProvider  # noqa: E402
from app.services.storage import connect, load_stock_open_data_snapshots, replace_stock_open_data_snapshot  # noqa: E402


logger = logging.getLogger(__name__)


class CountingSession:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.get_count = 0
        self.sec_submission_count = 0
        self.sec_archive_count = 0
        self.other_count = 0

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        self.get_count += 1
        if "data.sec.gov/submissions/" in url:
            self.sec_submission_count += 1
        elif "sec.gov/Archives/edgar/data" in url:
            self.sec_archive_count += 1
        else:
            self.other_count += 1
        return self.session.get(url, **kwargs)

    def report(self) -> dict[str, int]:
        return {
            "total_gets": self.get_count,
            "sec_submissions": self.sec_submission_count,
            "sec_archives": self.sec_archive_count,
            "other": self.other_count,
        }


def _metric_value(metric: OpenDataMetric | None) -> float | None:
    return metric.value if metric is not None else None


def _snapshot_as_of(snapshot: OpenDataSnapshot) -> str:
    return snapshot.generated_at.date().isoformat()


def _unavailable_adjusted_metric(snapshot: OpenDataSnapshot) -> OpenDataMetric:
    return OpenDataMetric(
        value=None,
        source="open_data_provider",
        tier="unavailable_open_free",
        as_of=_snapshot_as_of(snapshot),
        notes="Adjusted EPS growth was not found in an official earnings-release exhibit with high-confidence parsing.",
    )


def _cached_adjusted_eps(cache: JsonFileCache, cik: int) -> OpenDataMetric | None:
    cached = cache.get(f"adjusted_eps_growth_CIK{cik:010d}.json", max_age=timedelta(days=10_000_000))
    if not isinstance(cached, dict) or cached == {"unavailable": True}:
        return None
    try:
        return OpenDataMetric.model_validate(cached)
    except ValueError:
        return None


def _candidate_snapshots(snapshots: list[OpenDataSnapshot], tickers: set[str] | None) -> list[OpenDataSnapshot]:
    candidates: list[OpenDataSnapshot] = []
    for snapshot in snapshots:
        if tickers is not None and snapshot.ticker.upper() not in tickers:
            continue
        gaap = snapshot.business_health.get("eps_gaap_growth_yoy") or snapshot.business_health.get("eps_growth_yoy")
        if snapshot.cik is None or _metric_value(gaap) is None:
            continue
        candidates.append(snapshot)
    return candidates


def _patch_eps_metrics(
    snapshot: OpenDataSnapshot,
    adjusted: OpenDataMetric | None,
) -> tuple[OpenDataSnapshot, bool]:
    gaap = snapshot.business_health.get("eps_gaap_growth_yoy") or snapshot.business_health.get("eps_growth_yoy")
    if gaap is None:
        return snapshot, False

    before = snapshot.model_dump(mode="json")
    adjusted_metric = adjusted or _unavailable_adjusted_metric(snapshot)
    alignment = _eps_alignment_metric(adjusted_metric, gaap, _snapshot_as_of(snapshot))

    snapshot.business_health["eps_gaap_growth_yoy"] = gaap
    snapshot.business_health["eps_adjusted_growth_yoy"] = adjusted_metric
    snapshot.business_health["eps_alignment"] = alignment
    snapshot.metrics["eps_gaap_growth_yoy"] = gaap
    snapshot.metrics["eps_adjusted_growth_yoy"] = adjusted_metric
    snapshot.metrics["eps_alignment"] = alignment
    snapshot.metrics["eps_growth_yoy"] = gaap

    after = snapshot.model_dump(mode="json")
    return snapshot, before != after


def enrich_adjusted_eps(
    *,
    data_dir: Path,
    tickers: set[str] | None,
    limit: int | None,
    dry_run: bool,
    cache_only: bool,
    max_sec_archive_lookups: int,
    request_timeout: float,
    request_retries: int,
    retry_backoff: float,
) -> dict[str, Any]:
    session = CountingSession()
    provider = OpenDataProvider(
        session=session,  # type: ignore[arg-type]
        request_timeout=request_timeout,
        retry_attempts=request_retries,
        retry_backoff=retry_backoff,
        include_filing_details=not cache_only,
        max_sec_archive_lookups=max_sec_archive_lookups,
    )
    cache = JsonFileCache()

    with connect(data_dir) as conn:
        snapshots = _candidate_snapshots(load_stock_open_data_snapshots(conn), tickers)
        if limit is not None:
            snapshots = snapshots[:limit]

        results: list[dict[str, Any]] = []
        changed_count = 0
        adjusted_count = 0
        for index, snapshot in enumerate(snapshots, start=1):
            assert snapshot.cik is not None
            started = time.monotonic()
            adjusted = _cached_adjusted_eps(cache, snapshot.cik) if cache_only else provider.fetch_adjusted_eps_growth_yoy(snapshot.cik)
            patched, changed = _patch_eps_metrics(snapshot, adjusted)
            if changed:
                changed_count += 1
                if not dry_run:
                    replace_stock_open_data_snapshot(conn, patched)
            if _metric_value(adjusted) is not None:
                adjusted_count += 1
            results.append(
                {
                    "ticker": snapshot.ticker,
                    "cik": snapshot.cik,
                    "adjusted_eps_growth_yoy": _metric_value(adjusted),
                    "eps_alignment": _metric_value(patched.business_health.get("eps_alignment")),
                    "changed": changed,
                    "duration_seconds": round(time.monotonic() - started, 2),
                }
            )
            logger.info(
                "[%s/%s] %s adjusted=%s changed=%s",
                index,
                len(snapshots),
                snapshot.ticker,
                _metric_value(adjusted),
                changed,
            )
        if not dry_run:
            conn.commit()

    return {
        "candidate_count": len(snapshots),
        "changed_count": changed_count,
        "adjusted_eps_found_count": adjusted_count,
        "dry_run": dry_run,
        "cache_only": cache_only,
        "max_sec_archive_lookups": max_sec_archive_lookups,
        "requests": session.report(),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich saved stock snapshots with adjusted EPS and EPS alignment.")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--tickers", help="Comma-separated ticker allowlist.")
    parser.add_argument("--limit", type=int, help="Maximum number of candidate snapshots to process.")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without saving to SQLite.")
    parser.add_argument("--cache-only", action="store_true", help="Use only cached adjusted EPS metrics; do not make SEC requests.")
    parser.add_argument("--max-sec-archive-lookups", type=int, default=1)
    parser.add_argument("--request-timeout", type=float, default=20.0)
    parser.add_argument("--request-retries", type=int, default=1)
    parser.add_argument("--retry-backoff", type=float, default=1.0)
    parser.add_argument("--output", type=Path, help="Write JSON report to this path.")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")
    tickers = {ticker.strip().upper() for ticker in args.tickers.split(",") if ticker.strip()} if args.tickers else None
    report = enrich_adjusted_eps(
        data_dir=args.data_dir if args.data_dir.is_absolute() else ROOT / args.data_dir,
        tickers=tickers,
        limit=args.limit,
        dry_run=args.dry_run,
        cache_only=args.cache_only,
        max_sec_archive_lookups=max(0, args.max_sec_archive_lookups),
        request_timeout=args.request_timeout,
        request_retries=args.request_retries,
        retry_backoff=args.retry_backoff,
    )
    output = json.dumps(report, indent=2, sort_keys=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
