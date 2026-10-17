"""Comparable, neutral industry price context, rebuilt from saved daily closes."""

from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from app.config import PROJECT_DIR
from app.entry_engine.open_data_models import HistoricalPricePoint, OpenDataSnapshot


CLASSIFICATIONS_PATH = PROJECT_DIR / "data/stocks/industry-classifications.json"
BENCHMARK_FILE = Path("stocks/benchmarks/sp500.json")
BENCHMARK = {"symbol": "^GSPC", "name": "S&P 500", "currency": "USD", "market": "US",
             "source_url": "https://finance.yahoo.com/quote/%5EGSPC/history/"}
MIN_PEERS = 5
MIN_SESSIONS = 200
MAX_AGE_DAYS = 7
logger = logging.getLogger(__name__)


def load_classifications(path: Path = CLASSIFICATIONS_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _prices(points: list[HistoricalPricePoint]) -> dict[str, float]:
    result: dict[str, float] = {}
    for point in points:
        try:
            day = date.fromisoformat(point.date).isoformat()
        except ValueError:
            continue
        if math.isfinite(point.close) and point.close > 0:
            result[day] = point.close
    return result


def load_benchmark(data_dir: Path) -> list[HistoricalPricePoint]:
    try:
        payload = json.loads((data_dir / BENCHMARK_FILE).read_text(encoding="utf-8"))
        if payload.get("symbol") != BENCHMARK["symbol"] or payload.get("return_basis") != "price":
            return []
        return [HistoricalPricePoint.model_validate(row) for row in payload["prices"]]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def refresh_benchmark(data_dir: Path) -> list[HistoricalPricePoint]:
    """Fetch only market prices, retain verified cache on failure, never request SEC."""
    from app.entry_engine.providers.open_data_provider import OpenDataProvider

    saved = load_benchmark(data_dir)
    provider = OpenDataProvider(include_filing_details=False, allow_sec_requests=False)
    try:
        # Use the index explicitly; generic equity/Stooq symbol conversion is unsuitable.
        fetched = provider._fetch_yfinance_history(BENCHMARK["symbol"],
            start_date=(datetime.now(timezone.utc).date() - timedelta(days=800)).isoformat())
    except Exception as exc:
        logger.warning("S&P 500 refresh failed; retaining saved benchmark: %s", exc)
        fetched = []
    if not fetched:
        return saved
    merged = {p.date: p for p in saved if p.date in _prices([p])}
    merged.update({p.date: p for p in fetched if p.date in _prices([p])})
    points = sorted(merged.values(), key=lambda p: p.date)
    # A malformed/thin response must not replace the durable annual baseline.
    if len(points) < MIN_SESSIONS:
        logger.warning("S&P 500 history is too short for an annual comparison.")
        return saved
    cutoff = date.fromisoformat(points[-1].date) - timedelta(days=800)
    points = [p for p in points if p.date >= cutoff.isoformat()]
    path = data_dir / BENCHMARK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**BENCHMARK, "return_basis": "price", "fetched_at": datetime.now(timezone.utc).isoformat(),
               "prices": [p.model_dump(mode="json") for p in points]}
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return points


def strength_label(value: float | None) -> str:
    if value is None:
        return "Unclear"
    return "Ahead of market" if value >= 5 else "Behind market" if value <= -5 else "In line with market"


def build_industry_strength(
    snapshots: list[OpenDataSnapshot],
    histories: dict[str, list[HistoricalPricePoint]],
    benchmark: list[HistoricalPricePoint],
    classifications: dict[str, Any],
    *,
    today: date | None = None,
) -> list[OpenDataSnapshot]:
    today = today or datetime.now(timezone.utc).date()
    reviewed = classifications.get("stocks", {})
    prices = {symbol: _prices(points) for symbol, points in histories.items()}
    market_prices = _prices(benchmark)
    generated_at = datetime.now(timezone.utc).isoformat()

    def classification(snapshot: OpenDataSnapshot) -> dict[str, Any] | None:
        entry = reviewed.get(snapshot.ticker)
        # A provider classification change requires review rather than a silent regrouping.
        if not entry or entry.get("original_sector") != snapshot.sector or entry.get("original_industry") != snapshot.industry:
            return None
        return entry

    output = []
    for snapshot in snapshots:
        entry = classification(snapshot)
        result: dict[str, Any] = {
            "period": "1Y", "value": None, "label": "Unclear", "reason": None,
            "sector": entry.get("sector") if entry else snapshot.sector,
            "industry": entry.get("industry") if entry else snapshot.industry,
            "classification_source": classifications.get("source"),
            "classification_reviewed_at": classifications.get("reviewed_at"),
            "classification_sources": entry.get("sources", []) if entry else [],
            "original_sector": snapshot.sector, "original_industry": snapshot.industry,
            "benchmark": BENCHMARK, "start_date": None, "end_date": None,
            "generated_at": generated_at, "industry_return": None, "market_return": None,
            "stock_return": None, "stock_vs_industry": None, "peer_count": 0,
            "tracked_peer_count": 0, "peers": [], "excluded_peers": [], "chart": [],
            "tier": "unavailable_open_free", "source": "invest_os:industry_strength:1y:v1",
        }

        def unavailable(reason: str) -> None:
            result["reason"] = reason

        if entry is None:
            unavailable("Industry classification is missing or changed and needs review.")
        elif entry.get("market") != "US" or (snapshot.price_currency or entry.get("currency")) != "USD":
            unavailable("A compatible market benchmark is not configured for this listing's market and currency.")
        else:
            own = prices.get(snapshot.ticker, {})
            end = str(snapshot.price_opportunity.get("current_price").as_of)[:10] if snapshot.price_opportunity.get("current_price") else None
            if not end or end not in own:
                unavailable("The stock's latest close is unavailable in saved price history.")
            elif (today - date.fromisoformat(end)).days > MAX_AGE_DAYS or date.fromisoformat(end) > today:
                unavailable("The stock price is stale or dated in the future; waiting for a fresh completed session.")
            elif end not in market_prices:
                unavailable("S&P 500 price history does not cover the stock's latest session; waiting for benchmark refresh.")
            else:
                end_day = date.fromisoformat(end)
                try:
                    anniversary = end_day.replace(year=end_day.year - 1)
                except ValueError:
                    anniversary = end_day.replace(year=end_day.year - 1, day=28)
                starts = [d for d in market_prices if d <= anniversary.isoformat()]
                start = max(starts) if starts else None
                if not start or (anniversary - date.fromisoformat(start)).days > 7 or start not in own:
                    unavailable("A full year of comparable stock and market price history is unavailable.")
                else:
                    dates = sorted(d for d in market_prices if start <= d <= end)
                    result.update(start_date=start, end_date=end)
                    candidates = []
                    seen = {str(snapshot.cik or snapshot.ticker)}
                    for peer in sorted(snapshots, key=lambda s: s.ticker):
                        peer_entry = classification(peer)
                        identity = str(peer.cik or peer.ticker)
                        if identity in seen or not peer_entry:
                            continue
                        if (peer_entry.get("sector"), peer_entry.get("industry"), peer_entry.get("market"), peer_entry.get("currency")) != (entry.get("sector"), entry.get("industry"), "US", "USD"):
                            continue
                        seen.add(identity)
                        candidates.append(peer)
                    result["tracked_peer_count"] = len(candidates)
                    eligible = []
                    for peer in candidates:
                        peer_prices = prices.get(peer.ticker, {})
                        reason = None
                        if (peer.price_currency or reviewed[peer.ticker].get("currency")) != "USD":
                            reason = "Quote currency differs."
                        elif start not in peer_prices or end not in peer_prices:
                            reason = "Missing comparable start or end close."
                        elif sum(d in peer_prices for d in dates) < max(MIN_SESSIONS, len(dates) * 0.9):
                            reason = "Insufficient daily history over the full comparison year."
                        if reason:
                            result["excluded_peers"].append({"ticker": peer.ticker, "reason": reason})
                        else:
                            eligible.append(peer)
                            result["peers"].append({"ticker": peer.ticker, "name": peer.name,
                                "return_pct": (peer_prices[end] / peer_prices[start] - 1) * 100})
                    result["peer_count"] = len(eligible)
                    if len(eligible) < MIN_PEERS:
                        unavailable(f"Needs at least {MIN_PEERS} comparable other companies; {len(eligible)} of {len(candidates)} tracked peers qualify.")
                    else:
                        common = [d for d in dates if d in own and all(d in prices[p.ticker] for p in eligible)]
                        if len(common) < max(MIN_SESSIONS, len(dates) * 0.9):
                            unavailable("Too many missing sessions to compare the stock, peer basket, and market consistently.")
                        else:
                            industry_return = mean(p["return_pct"] for p in result["peers"])
                            market_return = (market_prices[end] / market_prices[start] - 1) * 100
                            stock_return = (own[end] / own[start] - 1) * 100
                            value = industry_return - market_return
                            result.update(value=value, label=strength_label(value), industry_return=industry_return,
                                market_return=market_return, stock_return=stock_return,
                                stock_vs_industry=stock_return - industry_return, tier="computed_from_public_facts")
                            result["chart"] = [{"date": d, "stock": own[d] / own[start] * 100,
                                "industry": mean(prices[p.ticker][d] / prices[p.ticker][start] * 100 for p in eligible),
                                "market": market_prices[d] / market_prices[start] * 100} for d in common]
        output.append(snapshot.model_copy(update={"industry_relative_strength": result}))
    return output


def enrich_industry_strength(
    snapshots: list[OpenDataSnapshot], histories: dict[str, list[HistoricalPricePoint]], data_dir: Path,
) -> list[OpenDataSnapshot]:
    return build_industry_strength(snapshots, histories, load_benchmark(data_dir), load_classifications())


def rebuild_saved_industry_strength(data_dir: Path, *, fetch_benchmark: bool = True) -> list[OpenDataSnapshot]:
    from app.services.storage import (connect, load_active_stock_tickers, load_stock_open_data_snapshots,
                                      load_stock_price_history, replace_stock_open_data_snapshot)

    if fetch_benchmark:
        refresh_benchmark(data_dir)
    with connect(data_dir) as conn:
        active = set(load_active_stock_tickers(conn))
        snapshots = [s for s in load_stock_open_data_snapshots(conn) if not active or s.ticker in active]
        histories = {s.ticker: load_stock_price_history(conn, s.ticker) for s in snapshots}
        updated = enrich_industry_strength(snapshots, histories, data_dir)
        for snapshot in updated:
            replace_stock_open_data_snapshot(conn, snapshot)
        conn.commit()
    return updated
