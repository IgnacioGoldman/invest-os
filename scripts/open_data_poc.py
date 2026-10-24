from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.entry_engine.providers.open_data_provider import OpenDataProvider  # noqa: E402
from app.entry_engine.open_data_models import LatestPrice, OpenDataCompanyFiling, OpenDataSnapshot  # noqa: E402
from app.entry_engine.valuation_refresh import reprice_valuation  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.services.open_data_stock_store import (  # noqa: E402
    activate_stock,
    load_cached_price_history,
    save_stock_snapshot_to_db,
)
from app.services.storage import (  # noqa: E402
    connect,
    load_stock_open_data_snapshot,
    load_stock_price_history,
    replace_stock_open_data_snapshot,
    load_stock_sec_refresh_state,
    replace_stock_sec_refresh_state,
)
from app.services.stock_data_quality import fundamental_gap_reasons, retain_verified_history  # noqa: E402
from app.services.industry_strength import rebuild_saved_industry_strength  # noqa: E402
from app.entry_engine.providers.issuer_revenue import issuer_revenue_check_due, load_issuer_revenue  # noqa: E402


YAHOO_MOST_ACTIVE_URL = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
DEFAULT_UNIVERSE_PATH = ROOT / "data" / "stocks" / "stocks.json"
DEFAULT_SKIP_TICKERS = {"GOOGL"}
REQUIRED_GROUPS = ("business_health", "price_opportunity", "valuation")
EPS_DEPENDENT_METRICS = {
    "business_health.eps_growth_yoy",
    "business_health.eps_gaap_growth_yoy",
    "business_health.eps_cagr_3y",
    "valuation.forward_pe",
    "valuation.peg",
}
logger = logging.getLogger(__name__)
SEC_FUNDAMENTAL_FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A"}
SEC_EARNINGS_TERMS = ("earnings", "results", "press", "release", "quarter", "interim", "half-year")


def _parse_date_key(value: Any) -> tuple[int, int, int]:
    try:
        parts = str(value)[:10].split("-")
        if len(parts) != 3:
            return (0, 0, 0)
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except (TypeError, ValueError):
        return (0, 0, 0)


def _filing_payload_text(filing: dict[str, Any]) -> str:
    return " ".join(
        str(filing.get(key) or "")
        for key in ("primary_document", "primaryDocument", "primary_doc_description", "primaryDocDescription", "description")
    ).lower()


def _is_relevant_sec_filing(filing: dict[str, Any]) -> bool:
    form = str(filing.get("form") or "").upper()
    if form in SEC_FUNDAMENTAL_FORMS:
        return True
    items = str(filing.get("items") or "")
    if form == "8-K" and "2.02" in items:
        return True
    if form == "6-K" and any(term in _filing_payload_text(filing) for term in SEC_EARNINGS_TERMS):
        return True
    return False


def _latest_relevant_sec_filing(submissions: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(submissions, dict):
        return None
    recent = submissions.get("filings", {}).get("recent") if isinstance(submissions.get("filings"), dict) else None
    if not isinstance(recent, dict):
        return None
    forms = recent.get("form") if isinstance(recent.get("form"), list) else []
    candidates: list[dict[str, Any]] = []
    for index, form in enumerate(forms):
        filing = {
            "form": form,
            "filing_date": _recent_value(recent, "filingDate", index),
            "accession_number": _recent_value(recent, "accessionNumber", index),
            "items": _recent_value(recent, "items", index),
            "primary_document": _recent_value(recent, "primaryDocument", index),
            "primary_doc_description": _recent_value(recent, "primaryDocDescription", index),
        }
        if _is_relevant_sec_filing(filing):
            candidates.append(filing)
    return max(candidates, key=lambda filing: (_parse_date_key(filing.get("filing_date")), str(filing.get("accession_number") or ""))) if candidates else None


def _recent_value(recent: dict[str, Any], key: str, index: int) -> Any:
    values = recent.get(key)
    return values[index] if isinstance(values, list) and index < len(values) else None


def _sec_submissions_verified(submissions: Any) -> bool:
    filings = submissions.get("filings") if isinstance(submissions, dict) else None
    recent = filings.get("recent") if isinstance(filings, dict) else None
    if not isinstance(recent, dict):
        return False
    columns = [recent.get(key) for key in ("form", "filingDate", "accessionNumber")]
    return all(isinstance(column, list) for column in columns) and len({len(column) for column in columns}) == 1


def _latest_relevant_context_filing(snapshot: OpenDataSnapshot | None) -> dict[str, Any] | None:
    if snapshot is None or snapshot.company_context is None:
        return None
    candidates: list[dict[str, Any]] = []
    for context_filing in snapshot.company_context.recent_filings:
        filing = _context_filing_payload(context_filing)
        if _is_relevant_sec_filing(filing):
            candidates.append(filing)
    return max(candidates, key=lambda filing: (_parse_date_key(filing.get("filing_date")), str(filing.get("accession_number") or ""))) if candidates else None


def _context_filing_payload(filing: OpenDataCompanyFiling) -> dict[str, Any]:
    return {
        "form": filing.form,
        "filing_date": filing.filing_date,
        "accession_number": filing.accession_number,
        "items": ",".join(filing.items),
        "primary_document": filing.primary_document,
        "primary_doc_description": filing.primary_document_description,
    }


def _state_accession(state: Any) -> str | None:
    if state is None:
        return None
    return str(state["accession_number"]) if state["accession_number"] else None


def _metric_unavailable_reason(metric: Any) -> str:
    notes = str(getattr(metric, "notes", "") or "")
    _, _, reason = notes.partition(": ")
    return reason or notes or "Metric was unavailable from open/free public inputs."


def _is_not_meaningful_missing(metric_name: str, metric: Any, groups: dict[str, Any]) -> bool:
    notes = str(getattr(metric, "notes", "") or "").lower()
    if "not meaningful" in notes:
        return True

    if metric_name not in EPS_DEPENDENT_METRICS:
        return False

    if "trailing eps" in notes:
        return True

    if metric_name == "valuation.peg":
        eps_cagr = groups["business_health"].get("eps_cagr_3y")
        return eps_cagr is not None and _is_not_meaningful_missing("business_health.eps_cagr_3y", eps_cagr, groups)

    return False


def _unsupported_metric_paths(snapshot: Any) -> list[str]:
    gaps = list(getattr(snapshot, "data_gaps", []) or [])
    unsupported: list[str] = []
    for gap in gaps:
        if "unsupported metric path" in gap.lower():
            unsupported.append(gap)
    return unsupported


def _fetch_top_volume_stocks(limit: int, skip_tickers: set[str]) -> list[dict[str, Any]]:
    response = requests.get(
        YAHOO_MOST_ACTIVE_URL,
        params={"scrIds": "most_actives", "count": max(limit * 10 + len(skip_tickers), 50), "formatted": "false"},
        headers={"User-Agent": "Invest OS open-data validation/0.1"},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    results = data.get("finance", {}).get("result", [])
    quotes = results[0].get("quotes", []) if results else []
    stocks: list[dict[str, Any]] = []
    for quote in quotes:
        if not isinstance(quote, dict):
            continue
        symbol = str(quote.get("symbol") or "").upper()
        if not symbol or symbol in skip_tickers or symbol.startswith("^"):
            continue
        if quote.get("quoteType") not in {"EQUITY", "ADR"}:
            continue
        volume = quote.get("regularMarketVolume") or quote.get("averageDailyVolume3Month") or 0
        try:
            volume_value = float(volume)
        except (TypeError, ValueError):
            volume_value = 0
        stocks.append(
            {
                "ticker": symbol,
                "name": quote.get("shortName") or quote.get("longName"),
                "exchange": quote.get("fullExchangeName") or quote.get("exchange"),
                "volume": volume_value,
            }
        )
    stocks.sort(key=lambda item: item["volume"], reverse=True)
    return stocks


def _load_universe_stocks(path: Path, limit: int | None, skip_tickers: set[str]) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_rows = (payload.get("rows") or payload.get("tickers")) if isinstance(payload, dict) else payload
    if not isinstance(raw_rows, list):
        raise ValueError(f"Universe file {path} must contain a list or a 'rows' list.")

    stocks: list[dict[str, Any]] = []
    for row in raw_rows:
        if isinstance(row, str):
            symbol = row.upper()
            item: dict[str, Any] = {"ticker": symbol}
        elif isinstance(row, dict):
            symbol = str(row.get("symbol") or row.get("ticker") or "").upper()
            item = {
                "ticker": symbol,
                "name": row.get("name"),
                "exchange": row.get("exchange"),
                "region": row.get("region"),
                "sector": row.get("sector"),
                "industry": row.get("industry"),
                "composite_score": row.get("composite_score"),
                "dollar_volume": row.get("dollar_volume"),
            }
        else:
            continue
        if not symbol or symbol in skip_tickers:
            continue
        stocks.append(item)
        if limit is not None and len(stocks) >= limit:
            break
    return stocks


def _metric_coverage(snapshot: Any) -> dict[str, Any]:
    missing: list[str] = []
    not_meaningful: list[dict[str, str]] = []
    weak_proxy: list[str] = []
    total = 0
    available = 0
    groups = {group_name: getattr(snapshot, group_name) for group_name in REQUIRED_GROUPS}
    for group_name in REQUIRED_GROUPS:
        group = groups[group_name]
        for key, metric in group.items():
            total += 1
            metric_name = f"{group_name}.{key}"
            if metric.value is None or metric.tier == "unavailable_open_free":
                if _is_not_meaningful_missing(metric_name, metric, groups):
                    not_meaningful.append({"metric": metric_name, "reason": _metric_unavailable_reason(metric)})
                    continue
                missing.append(metric_name)
                continue
            available += 1
            if metric.tier == "proxy_estimate":
                weak_proxy.append(metric_name)

    collectable_total = total - len(not_meaningful)
    return {
        "available_metrics": available,
        "total_metrics": total,
        "coverage_percent": round((available / total * 100) if total else 0, 2),
        "collectable_metrics": collectable_total,
        "collectable_coverage_percent": round((available / collectable_total * 100) if collectable_total else 0, 2),
        "missing_metrics": missing,
        "not_meaningful_metrics": not_meaningful,
        "proxy_metrics": weak_proxy,
        "unsupported_metric_paths": _unsupported_metric_paths(snapshot),
        "provider_data_gaps": snapshot.data_gaps,
    }


def _sec_state_kwargs(ticker: str, cik: int | None, filing: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "cik": cik,
        "accession_number": str(filing.get("accession_number") or "") if filing else None,
        "filing_date": str(filing.get("filing_date") or "") if filing else None,
        "form": str(filing.get("form") or "") if filing else None,
    }


def _save_sec_refresh_state(ticker: str, cik: int | None, filing: dict[str, Any] | None) -> None:
    settings = get_settings()
    with connect(settings.data_dir) as conn:
        replace_stock_sec_refresh_state(conn, **_sec_state_kwargs(ticker, cik, filing))
        conn.commit()


def _preserved_result(
    *,
    index: int,
    item: dict[str, Any],
    snapshot: OpenDataSnapshot,
    latest_filing: dict[str, Any] | None,
    reason: str,
    duration_seconds: float,
) -> dict[str, Any]:
    coverage = _metric_coverage(snapshot)
    return {
        **item,
        "_index": index,
        "ticker": snapshot.ticker,
        "name": snapshot.name or item.get("name"),
        "cik": snapshot.cik,
        "source": snapshot.source,
        "generated_at": snapshot.generated_at.isoformat(),
        "saved_to": "data/invest_os.sqlite",
        "analysis": None,
        "collection_status": "preserved",
        "refresh_status": "retained_unverified" if item.get("sec_check_status") == "unavailable" or item.get("issuer_check_status") == "unavailable" else "verified_unchanged",
        "skip_reason": reason,
        "latest_sec_accession": latest_filing.get("accession_number") if latest_filing else None,
        "latest_sec_filing_date": latest_filing.get("filing_date") if latest_filing else None,
        "latest_sec_form": latest_filing.get("form") if latest_filing else None,
        "duration_seconds": round(duration_seconds, 2),
        "attempts": 0,
        **_snapshot_dates(snapshot),
        **coverage,
    }


def _snapshot_dates(snapshot: OpenDataSnapshot) -> dict[str, Any]:
    current = snapshot.price_opportunity.get("current_price")
    dates = sorted(metric.as_of for metric in snapshot.business_health.values() if metric.value is not None)
    return {"price_as_of": current.as_of if current else None,
            "latest_fundamental_as_of": dates[-1] if dates else None}


def _filter_incremental_sec_work_items(
    work_items: list[tuple[int, dict[str, Any]]],
    provider: OpenDataProvider,
    *,
    save: bool,
    repair_data_gaps: bool = False,
    repair_current_data: bool = False,
    repair_revenue_history: bool = False,
) -> tuple[list[tuple[int, dict[str, Any]]], list[dict[str, Any]]]:
    if not save:
        return work_items, []
    settings = get_settings()
    collect_items: list[tuple[int, dict[str, Any]]] = []
    preserved: list[dict[str, Any]] = []
    with connect(settings.data_dir) as conn:
        for index, item in work_items:
            started = time.monotonic()
            ticker = item["ticker"]
            try:
                existing_snapshot = load_stock_open_data_snapshot(conn, ticker)
                try:
                    cik = provider.resolve_cik(ticker)
                except Exception as exc:
                    if existing_snapshot is not None and existing_snapshot.cik is not None:
                        item["sec_check_status"] = "unavailable"
                        item["source_notes"] = [f"SEC company lookup failed; retained saved data: {exc}"]
                        preserved.append(
                            _preserved_result(
                                index=index,
                                item=item,
                                snapshot=existing_snapshot,
                                latest_filing=None,
                                reason="sec_metadata_unavailable_preserved_existing_snapshot",
                                duration_seconds=time.monotonic() - started,
                            )
                        )
                        continue
                    item["sec_check_status"] = "not_applicable"
                    collect_items.append((index, item))
                    continue

                submissions = provider._fetch_sec_submissions(cik)
                verified = _sec_submissions_verified(submissions)
                item["sec_check_status"] = "verified" if verified else "unavailable"
                if not verified:
                    item["source_notes"] = ["SEC submissions could not be verified; latest filing status is unknown."]
                latest_filing = _latest_relevant_sec_filing(submissions)
                existing_filing = _latest_relevant_context_filing(existing_snapshot)
                state = load_stock_sec_refresh_state(conn, ticker)
                known_accession = _state_accession(state) or (
                    str(existing_filing.get("accession_number") or "") if existing_filing else None
                )
                latest_accession = str(latest_filing.get("accession_number") or "") if latest_filing else None

                repairs = fundamental_gap_reasons(existing_snapshot, include_history=repair_data_gaps) if (repair_data_gaps or repair_current_data) and existing_snapshot is not None else []
                # Supported issuer discovery must not depend on descriptive 6-K titles.
                seed = load_issuer_revenue(ticker)
                if seed is not None:
                    if issuer_revenue_check_due(ticker, seed):
                        repairs.append("issuer_report_check_due")
                    revenue = existing_snapshot.historical_series.get("quarterly_revenue", []) if existing_snapshot else []
                    latest_saved = max((row.as_of for row in revenue), default="")
                    latest_issuer = max(row["end"] for row in seed["facts"]["issuer"]["Revenues"]["units"]["USD"])
                    if latest_issuer > latest_saved:
                        repairs.append("issuer_report_data_changed")
                if repair_revenue_history and existing_snapshot is not None:
                    from app.services.revenue_growth_momentum import calculate_revenue_growth_momentum
                    checked = existing_snapshot.revenue_history_checked_at
                    due = checked is None or datetime.now(timezone.utc) - checked >= timedelta(days=7)
                    if existing_snapshot.revenue_history_version < 1 or (due and calculate_revenue_growth_momentum(existing_snapshot.model_dump(mode="json"))["label"] == "Unknown"):
                        repairs.append("historical_series.revenue_history_repair")
                if existing_snapshot is not None and not repairs and (latest_accession is None or latest_accession == known_accession):
                    if verified:
                        replace_stock_sec_refresh_state(conn, **_sec_state_kwargs(ticker, cik, latest_filing or existing_filing))
                    preserved.append(
                        _preserved_result(
                            index=index,
                            item=item,
                            snapshot=existing_snapshot,
                            latest_filing=latest_filing or existing_filing,
                            reason="sec_filings_unchanged" if verified else "sec_metadata_unavailable_preserved_existing_snapshot",
                            duration_seconds=time.monotonic() - started,
                        )
                    )
                    continue
                item["_latest_sec_cik"] = cik
                item["_latest_sec_filing"] = latest_filing
                if repairs:
                    item["repair_reasons"] = repairs
                item["_issuer_check_only"] = bool(
                    existing_snapshot is not None and repairs
                    and all(reason.startswith("issuer_report_") for reason in repairs)
                    and (latest_accession is None or latest_accession == known_accession)
                )
                collect_items.append((index, item))
            except Exception as exc:
                item["sec_check_status"] = "unavailable"
                item["source_notes"] = [f"SEC preflight failed; attempting normal collection: {exc}"]
                logger.warning("%s: incremental SEC preflight failed; collecting normally: %s", ticker, exc)
                collect_items.append((index, item))
        conn.commit()
    return collect_items, preserved


def _collect_ticker(
    provider: OpenDataProvider,
    ticker: str,
    save: bool,
    *,
    min_coverage_to_save: float | None = None,
    include_analysis: bool = False,
    reuse_saved_prices: bool = False,
) -> dict[str, Any]:
    previous = None
    if save or reuse_saved_prices:
        with connect(get_settings().data_dir) as conn:
            previous = load_stock_open_data_snapshot(conn, ticker)
            price_history = load_stock_price_history(conn, ticker) if reuse_saved_prices else []
    if reuse_saved_prices:
        if previous is None:
            raise ValueError(f"{ticker}: a saved snapshot is required; bootstrap the stock before running incremental fundamentals.")
        snapshot = provider.get_open_data_snapshot(ticker, saved_snapshot=previous, saved_price_history=price_history)
    else:
        snapshot = provider.get_open_data_snapshot(ticker)
    if save:
        snapshot = retain_verified_history(snapshot, previous)
    if reuse_saved_prices:
        current = snapshot.price_opportunity["current_price"]
        snapshot = reprice_valuation(snapshot, LatestPrice(
            ticker=ticker, price=current.value, as_of=current.as_of, source=current.source,
            currency=snapshot.price_currency or ("SEK" if ticker.endswith(".ST") else "USD"),
        ))
    elif not load_cached_price_history(snapshot.ticker):
        raise RuntimeError(f"{snapshot.ticker}: historical prices were unavailable.")
    coverage = _metric_coverage(snapshot)
    should_save = (
        save
        and (min_coverage_to_save is None or coverage["collectable_coverage_percent"] >= min_coverage_to_save)
        and not coverage["unsupported_metric_paths"]
    )
    if should_save:
        settings = get_settings()
        if reuse_saved_prices:
            with connect(settings.data_dir) as conn:
                replace_stock_open_data_snapshot(conn, snapshot)
                conn.commit()
        else:
            save_stock_snapshot_to_db(settings, snapshot)
        activate_stock(settings, snapshot.ticker)
    return {
        "ticker": snapshot.ticker,
        "name": snapshot.name,
        "cik": snapshot.cik,
        "source": snapshot.source,
        "generated_at": snapshot.generated_at.isoformat(),
        "saved_to": "data/invest_os.sqlite" if should_save else None,
        "analysis": None if include_analysis else None,
        **_snapshot_dates(snapshot),
        "source_notes": [note for note in snapshot.data_gaps if any(term in note.lower() for term in ("failed", "retained", "unavailable;"))],
        **coverage,
    }


def _collect_item_with_retries(
    item: dict[str, Any],
    *,
    save: bool,
    min_coverage: float,
    include_analysis: bool,
    include_filing_details: bool,
    max_sec_archive_lookups: int | None,
    ticker_retries: int,
    request_timeout: float,
    request_retries: int,
    retry_backoff: float,
    reuse_saved_prices: bool = False,
) -> dict[str, Any]:
    ticker = item["ticker"]
    started = time.monotonic()
    last_error: Exception | None = None
    for attempt in range(1, max(1, ticker_retries) + 1):
        provider = OpenDataProvider(
            request_timeout=request_timeout,
            retry_attempts=request_retries,
            retry_backoff=retry_backoff,
            include_filing_details=include_filing_details,
            max_sec_archive_lookups=max_sec_archive_lookups,
        )
        try:
            collected = _collect_ticker(
                provider, ticker, save, min_coverage_to_save=min_coverage,
                include_analysis=include_analysis, reuse_saved_prices=reuse_saved_prices,
            )
            result = {
                **item,
                **collected,
                "source_notes": list(dict.fromkeys([*item.get("source_notes", []), *collected.get("source_notes", [])])),
                "refresh_status": "refreshed",
            }
            result["duration_seconds"] = round(time.monotonic() - started, 2)
            result["attempts"] = attempt
            return result
        except Exception as exc:
            last_error = exc
            if attempt >= max(1, ticker_retries):
                break
            sleep_for = retry_backoff * (2 ** (attempt - 1))
            logger.warning("%s failed on attempt %s/%s: %s", ticker, attempt, ticker_retries, exc)
            if sleep_for > 0:
                time.sleep(sleep_for)

    assert last_error is not None
    # Independent issuer discovery is additive: its outage must not make a
    # previously preservable, otherwise unchanged stock fail the whole refresh.
    if save and item.get("_issuer_check_only"):
        with connect(get_settings().data_dir) as conn:
            previous = load_stock_open_data_snapshot(conn, ticker)
        if previous is not None:
            retained_item = {**item, "issuer_check_status": "unavailable",
                             "source_notes": [*item.get("source_notes", []), f"Issuer collection failed; retained saved snapshot: {last_error}"]}
            return _preserved_result(index=0, item=retained_item, snapshot=previous,
                                     latest_filing=item.get("_latest_sec_filing"),
                                     reason="issuer_check_unavailable_preserved_existing_snapshot",
                                     duration_seconds=time.monotonic() - started)
    raise last_error


def _write_report(path: Path | None, report: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _build_report(
    *,
    mode: str,
    requested_count: int,
    source: str,
    skip_tickers: set[str],
    min_coverage: float,
    include_filing_details: bool,
    results: list[dict[str, Any]],
    skipped_low_fidelity: list[dict[str, Any]],
    failures: list[dict[str, str]],
) -> dict[str, Any]:
    ordered_results = [dict(item) for item in sorted(results, key=lambda item: int(item.get("_index", 0)))]
    ordered_skipped = [dict(item) for item in sorted(skipped_low_fidelity, key=lambda item: int(item.get("_index", 0)))]
    ordered_failures = [dict(item) for item in sorted(failures, key=lambda item: int(item.get("_index", 0)))]
    for collection in (ordered_results, ordered_skipped, ordered_failures):
        for row in collection:
            row.pop("_index", None)
            row.pop("_issuer_check_only", None)
    preserved_count = sum(1 for row in ordered_results if row.get("collection_status") == "preserved")
    return {
        "mode": mode,
        "requested_count": requested_count,
        "source": source,
        "skipped_tickers": sorted(skip_tickers),
        "min_coverage_percent": min_coverage,
        "include_filing_details": include_filing_details,
        "collected_count": len(ordered_results),
        "refreshed_count": len(ordered_results) - preserved_count,
        "preserved_count": preserved_count,
        "verified_unchanged_count": sum(row.get("refresh_status") == "verified_unchanged" for row in ordered_results),
        "retained_unverified_count": sum(row.get("refresh_status") == "retained_unverified" for row in ordered_results),
        "sec_unverified_count": sum(row.get("sec_check_status") == "unavailable" for row in ordered_results),
        "failed_count": len(ordered_failures),
        "skipped_low_fidelity_count": len(ordered_skipped),
        "results": ordered_results,
        "skipped_low_fidelity": ordered_skipped,
        "failures": ordered_failures,
    }


def _record_collected_sec_state(result: dict[str, Any], item: dict[str, Any], *, incremental_sec: bool, save: bool) -> None:
    if not incremental_sec or not save or not result.get("saved_to") or item.get("sec_check_status") == "unavailable":
        return
    cik = item.get("_latest_sec_cik") or result.get("cik")
    try:
        parsed_cik = int(cik) if cik is not None else None
    except (TypeError, ValueError):
        parsed_cik = None
    _save_sec_refresh_state(result["ticker"], parsed_cik, item.get("_latest_sec_filing"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the open/free public-data stock metrics proof-of-concept.")
    parser.add_argument("ticker", nargs="?", help="Ticker to collect. If omitted, collect top-volume stocks.")
    parser.add_argument("--top-volume", type=int, default=5, help="Number of top-volume stocks to collect when ticker is omitted.")
    parser.add_argument(
        "--universe-file",
        type=Path,
        help="Collect tickers from a stocks.json universe file instead of Yahoo most-actives.",
    )
    parser.add_argument("--limit", type=int, help="Limit universe-file collection count.")
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=80.0,
        help="Minimum metric coverage percent required in top-volume mode.",
    )
    parser.add_argument("--include-googl", action="store_true", help="Do not skip GOOGL in top-volume mode.")
    parser.add_argument("--include-analysis", action="store_true", help="Include deterministic stock-entry analysis in the run output.")
    parser.add_argument(
        "--skip-filing-details",
        action="store_true",
        help=(
            "Skip per-filing SEC archive exhibit lookups. "
            "Recent filing metadata is still collected; this is recommended for large universe runs."
        ),
    )
    parser.add_argument(
        "--max-sec-archive-lookups",
        type=int,
        help=(
            "Maximum optional SEC Archives filing-index lookups per ticker. "
            "Defaults to the provider's conservative SEC_ARCHIVE_LOOKUP_LIMIT."
        ),
    )
    parser.add_argument("--no-save", action="store_true", help="Do not persist snapshots to SQLite.")
    parser.add_argument("--reuse-saved-prices", action="store_true", help="Use SQLite prices/history and leave them unchanged; do not fetch new prices or market estimates.")
    parser.add_argument(
        "--incremental-sec",
        action="store_true",
        help="Preserve existing SQLite snapshots unless SEC recent submissions contain a newer relevant filing.",
    )
    parser.add_argument("--repair-data-gaps", action="store_true", help="Recollect symbols with missing fundamentals or an unusable latest six-quarter revenue window, even when SEC filings are unchanged.")
    parser.add_argument("--repair-current-data", action="store_true", help="Retry missing current fundamentals on the daily refresh; historical windows/CAGR gaps never trigger collection.")
    parser.add_argument("--repair-revenue-history", action="store_true", help="Upgrade revenue period parsing once; retry incomplete momentum windows at most weekly when filings are unchanged.")
    parser.add_argument("--output", type=Path, help="Write the JSON run report to a file as well as stdout.")
    parser.add_argument("--workers", type=int, default=3, help="Number of tickers to collect in parallel.")
    parser.add_argument("--ticker-retries", type=int, default=2, help="Retry a whole ticker collection this many times.")
    parser.add_argument("--request-timeout", type=float, default=15.0, help="Per-request timeout used by the open-data provider.")
    parser.add_argument("--request-retries", type=int, default=2, help="Retry individual HTTP requests this many times.")
    parser.add_argument("--retry-backoff", type=float, default=0.75, help="Base seconds for exponential retry backoff.")
    parser.add_argument("--checkpoint-every", type=int, default=1, help="Write --output after every N completed tickers.")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    provider = OpenDataProvider(
        request_timeout=args.request_timeout,
        retry_attempts=args.request_retries,
        retry_backoff=args.retry_backoff,
        include_filing_details=not args.skip_filing_details,
        max_sec_archive_lookups=args.max_sec_archive_lookups,
    )
    save = not args.no_save

    if args.ticker:
        result = _collect_ticker(provider, args.ticker, save, include_analysis=args.include_analysis, reuse_saved_prices=args.reuse_saved_prices)
        if save:
            rebuild_saved_industry_strength(get_settings().data_dir)
        output = json.dumps(result, indent=2, sort_keys=False)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output + "\n", encoding="utf-8")
        print(output)
        return

    skip_tickers = set() if args.include_googl else set(DEFAULT_SKIP_TICKERS)
    if args.universe_file:
        universe_path = args.universe_file if args.universe_file.is_absolute() else ROOT / args.universe_file
        universe = _load_universe_stocks(universe_path, args.limit, skip_tickers)
        mode = "universe_file"
        source = str(universe_path.relative_to(ROOT))
        requested_count = len(universe)
        max_results = len(universe)
    else:
        universe = _fetch_top_volume_stocks(args.top_volume, skip_tickers)
        mode = "top_volume"
        source = "yahoo_finance_most_actives"
        requested_count = args.top_volume
        max_results = args.top_volume
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    skipped_low_fidelity: list[dict[str, Any]] = []

    work_items = list(enumerate(universe[:max_results] if mode == "top_volume" else universe))
    if args.incremental_sec:
        work_items, preserved_results = _filter_incremental_sec_work_items(work_items, provider, save=save, repair_data_gaps=args.repair_data_gaps, repair_current_data=args.repair_current_data, repair_revenue_history=args.repair_revenue_history)
        results.extend(preserved_results)
        logger.info(
            "Incremental SEC preflight preserved %s ticker(s) and selected %s ticker(s) for collection.",
            len(preserved_results),
            len(work_items),
        )
    logger.info(
        "Collecting %s tickers with %s worker(s), ticker retries=%s, request timeout=%.1fs",
        len(work_items),
        max(1, args.workers),
        args.ticker_retries,
        args.request_timeout,
    )

    def record_result(index: int, item: dict[str, Any], result: dict[str, Any] | None, error: Exception | None = None) -> None:
        ticker = item["ticker"]
        if error is not None:
            logger.error(
                "Open-data collection failed for %s",
                ticker,
                exc_info=(type(error), error, error.__traceback__),
            )
            failures.append({"_index": index, "ticker": ticker, "error": str(error)})
            return
        assert result is not None
        result["_index"] = index
        result.setdefault("collection_status", "collected")
        _record_collected_sec_state(result, item, incremental_sec=args.incremental_sec, save=save)
        if result["collectable_coverage_percent"] < args.min_coverage:
            skipped_low_fidelity.append(
                {
                    "_index": index,
                    "ticker": ticker,
                    "name": result.get("name") or item.get("name"),
                    "volume": item.get("volume"),
                    "coverage_percent": result["coverage_percent"],
                    "collectable_coverage_percent": result["collectable_coverage_percent"],
                    "missing_metrics": result["missing_metrics"],
                    "not_meaningful_metrics": result["not_meaningful_metrics"],
                    "unsupported_metric_paths": result["unsupported_metric_paths"],
                    "reason": f"Collectable metric coverage below {args.min_coverage:.0f}% threshold.",
                }
            )
            logger.info(
                "Skipped %s: collectable coverage %.2f%%",
                ticker,
                result["collectable_coverage_percent"],
            )
            return
        results.append(result)
        logger.info(
            "Collected %s: coverage %.2f%%, collectable %.2f%%, missing=%s, duration=%.2fs",
            ticker,
            result["coverage_percent"],
            result["collectable_coverage_percent"],
            len(result["missing_metrics"]),
            result["duration_seconds"],
        )

    def checkpoint(completed: int) -> None:
        if not args.output or args.checkpoint_every <= 0 or completed % args.checkpoint_every != 0:
            return
        _write_report(
            args.output,
            _build_report(
                mode=mode,
                requested_count=requested_count,
                source=source,
                skip_tickers=skip_tickers,
                    min_coverage=args.min_coverage,
                    include_filing_details=not args.skip_filing_details,
                    results=results,
                    skipped_low_fidelity=skipped_low_fidelity,
                    failures=failures,
            ),
        )

    if max(1, args.workers) == 1:
        for completed, (index, item) in enumerate(work_items, start=1):
            ticker = item["ticker"]
            logger.info("[%s/%s] Collecting %s", completed, len(work_items), ticker)
            try:
                result = _collect_item_with_retries(
                    item,
                    save=save,
                    min_coverage=args.min_coverage,
                    include_analysis=args.include_analysis,
                    include_filing_details=not args.skip_filing_details,
                    max_sec_archive_lookups=args.max_sec_archive_lookups,
                    ticker_retries=args.ticker_retries,
                    request_timeout=args.request_timeout,
                    request_retries=args.request_retries,
                    retry_backoff=args.retry_backoff,
                    reuse_saved_prices=args.reuse_saved_prices,
                )
                record_result(index, item, result)
            except Exception as exc:
                record_result(index, item, None, exc)
            checkpoint(completed)
    else:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            future_map = {
                executor.submit(
                    _collect_item_with_retries,
                    item,
                    save=save,
                    min_coverage=args.min_coverage,
                    include_analysis=args.include_analysis,
                    include_filing_details=not args.skip_filing_details,
                    max_sec_archive_lookups=args.max_sec_archive_lookups,
                    ticker_retries=args.ticker_retries,
                    request_timeout=args.request_timeout,
                    request_retries=args.request_retries,
                    retry_backoff=args.retry_backoff,
                    reuse_saved_prices=args.reuse_saved_prices,
                ): (index, item)
                for index, item in work_items
            }
            for completed, future in enumerate(as_completed(future_map), start=1):
                index, item = future_map[future]
                ticker = item["ticker"]
                try:
                    record_result(index, item, future.result())
                except Exception as exc:
                    record_result(index, item, None, exc)
                logger.info("[%s/%s] Finished %s", completed, len(work_items), ticker)
                checkpoint(completed)

    if save:
        rebuild_saved_industry_strength(get_settings().data_dir)

    report = _build_report(
        mode=mode,
        requested_count=requested_count,
        source=source,
        skip_tickers=skip_tickers,
        min_coverage=args.min_coverage,
        include_filing_details=not args.skip_filing_details,
        results=results,
        skipped_low_fidelity=skipped_low_fidelity,
        failures=failures,
    )
    output = json.dumps(report, indent=2, sort_keys=False)
    _write_report(args.output, report)
    print(output)
    if save and work_items and not results:
        raise SystemExit("No stock snapshots were collected; refusing to continue with an empty saved dataset.")


if __name__ == "__main__":
    main()
