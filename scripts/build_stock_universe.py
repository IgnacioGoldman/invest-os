from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "stocks" / "stocks.json"

NASDAQ_SCREENER_URL = "https://api.nasdaq.com/api/screener/stocks"
NASDAQ_QUOTE_URL = "https://api.nasdaq.com/api/quote/{symbol}/info"
USER_AGENT = "Mozilla/5.0 (compatible; Invest OS stock universe builder/0.1)"

MAJOR_SECTORS = (
    "Technology",
    "Communication Services",
    "Consumer Cyclical",
    "Consumer Defensive",
    "Financials",
    "Healthcare",
    "Industrials",
    "Energy",
    "Materials",
    "Utilities",
    "Real Estate",
)
SECTOR_ALIASES = {
    "Consumer Discretionary": "Consumer Cyclical",
    "Consumer Staples": "Consumer Defensive",
    "Finance": "Financials",
    "Health Care": "Healthcare",
    "Telecommunications": "Communication Services",
    "Basic Materials": "Materials",
}
EXCLUDED_NAME_PARTS = (
    " warrant",
    " rights",
    " right ",
    " unit",
    " preferred",
    " preference",
    " depositary share",
    " notes due",
    " senior note",
    " bond",
    " etf",
    " etn",
    " fund",
    " acquisition corp",
    " blank check",
)
ISSUER_SUFFIX_PATTERN = re.compile(
    r"\b("
    r"class\s+[a-z]|common\s+stock|capital\s+stock|ordinary\s+shares?|american\s+depositary\s+shares?|"
    r"ads|sponsored|incorporated|corporation|corp\.?|inc\.?|limited|ltd\.?|plc|company|co\.?"
    r")\b",
    re.IGNORECASE,
)


@dataclass
class StockCandidate:
    symbol: str
    name: str | None
    quote_type: str
    region: str
    country: str | None
    sector: str
    industry: str | None
    price: float | None
    market_cap: float | None
    volume: float | None
    avg_volume_20d: float | None = None
    dollar_volume: float | None = None
    avg_dollar_volume_20d: float | None = None
    relative_volume: float | None = None
    volatility_20d: float | None = None
    spread_estimate: float | None = None
    data_quality_score: float = 0
    composite_score: float = 0
    exchange: str | None = None
    source: str = "nasdaq_screener"


def _number(value: Any) -> float | None:
    if value in (None, "", "N/A", "NA", "--"):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("$", "").replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _symbol_for_yahoo(symbol: str) -> str:
    return symbol.strip().upper().replace("/", "-")


def _normalize_sector(value: Any) -> str:
    sector = str(value or "").strip()
    return SECTOR_ALIASES.get(sector, sector) if sector else "Unknown"


def _region_bucket(country: str | None) -> str:
    if not country:
        return "OTHER"
    normalized = country.strip().lower()
    if normalized in {"united states", "usa", "us"}:
        return "US"
    return "ADR"


def _is_common_equity(row: dict[str, Any]) -> bool:
    symbol = str(row.get("symbol") or "").strip()
    name = str(row.get("name") or "").strip().lower()
    if not symbol or "^" in symbol or "." in symbol:
        return False
    return not any(part in f" {name} " for part in EXCLUDED_NAME_PARTS)


def _issuer_key(candidate: StockCandidate) -> str:
    name = candidate.name or candidate.symbol
    cleaned = ISSUER_SUFFIX_PATTERN.sub(" ", name)
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned.lower()).strip()
    return cleaned or candidate.symbol.lower()


def fetch_nasdaq_candidates(session: requests.Session, *, limit: int) -> list[StockCandidate]:
    response = session.get(
        NASDAQ_SCREENER_URL,
        params={"tableonly": "true", "download": "true", "limit": limit, "offset": 0},
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    rows = response.json().get("data", {}).get("rows", [])
    candidates: list[StockCandidate] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not _is_common_equity(row):
            continue
        price = _number(row.get("lastsale"))
        volume = _number(row.get("volume"))
        market_cap = _number(row.get("marketCap"))
        country = str(row.get("country") or "").strip() or None
        region = _region_bucket(country)
        if region not in {"US", "ADR"}:
            continue
        symbol = _symbol_for_yahoo(str(row.get("symbol") or ""))
        quote_type = "ADR" if region == "ADR" else "EQUITY"
        candidates.append(
            StockCandidate(
                symbol=symbol,
                name=str(row.get("name") or "").strip() or None,
                quote_type=quote_type,
                region=region,
                country=country,
                sector=_normalize_sector(row.get("sector")),
                industry=str(row.get("industry") or "").strip() or None,
                price=price,
                market_cap=market_cap,
                volume=volume,
                dollar_volume=(price * volume) if price is not None and volume is not None else None,
                exchange="US-listed",
            )
        )
    return candidates


def enrich_history(candidates: list[StockCandidate], *, chunk_size: int = 80) -> None:
    try:
        import yfinance as yf  # type: ignore[import-not-found]
    except ImportError:
        return

    by_symbol = {candidate.symbol: candidate for candidate in candidates}
    symbols = list(by_symbol)
    for start in range(0, len(symbols), chunk_size):
        chunk = symbols[start : start + chunk_size]
        try:
            frame = yf.download(
                " ".join(chunk),
                period="1mo",
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=True,
            )
        except Exception:
            continue
        for symbol in chunk:
            try:
                data = frame[symbol] if len(chunk) > 1 else frame
            except Exception:
                continue
            if data is None or data.empty or "Close" not in data or "Volume" not in data:
                continue
            closes = [float(value) for value in data["Close"].dropna().tail(21).tolist() if value]
            volumes = [float(value) for value in data["Volume"].dropna().tail(20).tolist() if value]
            if not closes or not volumes:
                continue
            candidate = by_symbol[symbol]
            avg_volume = statistics.fmean(volumes)
            avg_price = statistics.fmean(closes[-20:]) if len(closes) >= 20 else statistics.fmean(closes)
            returns = [
                (closes[index] / closes[index - 1]) - 1
                for index in range(1, len(closes))
                if closes[index - 1] > 0
            ]
            candidate.avg_volume_20d = avg_volume
            candidate.avg_dollar_volume_20d = avg_volume * avg_price
            candidate.relative_volume = (candidate.volume / avg_volume) if candidate.volume is not None and avg_volume else None
            candidate.volatility_20d = statistics.pstdev(returns) if len(returns) >= 2 else None


def enrich_spreads(
    session: requests.Session,
    candidates: list[StockCandidate],
    *,
    limit: int,
    delay: float,
    timeout: float,
) -> None:
    for candidate in candidates[:limit]:
        try:
            response = session.get(
                NASDAQ_QUOTE_URL.format(symbol=candidate.symbol),
                params={"assetclass": "stocks"},
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json().get("data")
            primary = data.get("primaryData", {}) if isinstance(data, dict) else {}
        except (requests.RequestException, ValueError):
            continue
        bid = _number(primary.get("bidPrice"))
        ask = _number(primary.get("askPrice"))
        if bid is not None and ask is not None and bid > 0 and ask >= bid:
            midpoint = (bid + ask) / 2
            candidate.spread_estimate = (ask - bid) / midpoint if midpoint else None
        if delay > 0:
            time.sleep(delay)


def _log_norm(value: float | None, values: list[float]) -> float:
    if value is None or value <= 0 or not values:
        return 0
    logs = sorted(math.log(max(item, 1)) for item in values if item and item > 0)
    if not logs:
        return 0
    low = logs[max(0, int(len(logs) * 0.10) - 1)]
    high = logs[min(len(logs) - 1, int(len(logs) * 0.95))]
    if high <= low:
        return 1
    return max(0, min(1, (math.log(max(value, 1)) - low) / (high - low)))


def _relative_volume_score(value: float | None) -> float:
    if value is None or value <= 0:
        return 0
    if value <= 1.5:
        return min(1, value / 1.5)
    if value <= 3:
        return 1
    return max(0.35, 1 - ((value - 3) / 8))


def _spread_score(value: float | None) -> float:
    if value is None:
        return 0.55
    if value <= 0.001:
        return 1
    if value <= 0.003:
        return 0.85
    if value <= 0.006:
        return 0.65
    if value <= 0.012:
        return 0.35
    return 0.1


def _volatility_score(value: float | None) -> float:
    if value is None:
        return 0.4
    if 0.015 <= value <= 0.055:
        return 1
    if value < 0.015:
        return max(0.25, value / 0.015)
    return max(0.25, 1 - ((value - 0.055) / 0.12))


def _data_quality(candidate: StockCandidate) -> float:
    checks = (
        candidate.price,
        candidate.market_cap,
        candidate.volume,
        candidate.avg_volume_20d,
        candidate.dollar_volume,
        candidate.avg_dollar_volume_20d,
        candidate.relative_volume,
        candidate.volatility_20d,
        candidate.spread_estimate,
        candidate.sector if candidate.sector != "Unknown" else None,
        candidate.industry,
        candidate.country,
    )
    return sum(1 for value in checks if value not in (None, "")) / len(checks)


def score_candidates(candidates: list[StockCandidate]) -> None:
    dollar_values = [item.dollar_volume or 0 for item in candidates]
    avg_dollar_values = [item.avg_dollar_volume_20d or 0 for item in candidates]
    market_caps = [item.market_cap or 0 for item in candidates]
    for candidate in candidates:
        candidate.data_quality_score = round(_data_quality(candidate), 4)
        candidate.composite_score = round(
            (
                25 * _log_norm(candidate.dollar_volume, dollar_values)
                + 25 * _log_norm(candidate.avg_dollar_volume_20d, avg_dollar_values)
                + 20 * _log_norm(candidate.market_cap, market_caps)
                + 10 * _relative_volume_score(candidate.relative_volume)
                + 10 * _spread_score(candidate.spread_estimate)
                + 5 * _volatility_score(candidate.volatility_20d)
                + 5 * candidate.data_quality_score
            ),
            2,
        )


def filter_candidates(
    candidates: list[StockCandidate],
    *,
    min_price: float,
    min_market_cap: float,
    min_dollar_volume: float,
    min_avg_dollar_volume: float,
    min_data_quality: float,
) -> list[StockCandidate]:
    filtered = []
    for candidate in candidates:
        if candidate.price is None or candidate.price < min_price:
            continue
        if candidate.market_cap is None or candidate.market_cap < min_market_cap:
            continue
        if candidate.dollar_volume is None or candidate.dollar_volume < min_dollar_volume:
            continue
        if candidate.avg_dollar_volume_20d is None or candidate.avg_dollar_volume_20d < min_avg_dollar_volume:
            continue
        if candidate.sector == "Unknown":
            continue
        if candidate.data_quality_score < min_data_quality:
            continue
        filtered.append(candidate)
    return filtered


def select_balanced_universe(
    candidates: list[StockCandidate],
    *,
    count: int,
    us_target: int,
    adr_target: int,
    max_per_sector: int,
    min_major_sectors: int,
    forced_candidates: list[StockCandidate] | None = None,
) -> list[StockCandidate]:
    sorted_candidates = sorted(candidates, key=lambda item: item.composite_score, reverse=True)
    selected: list[StockCandidate] = []
    selected_symbols: set[str] = set()
    selected_issuers: set[str] = set()
    sector_counts: dict[str, int] = {}
    region_counts = {"US": 0, "ADR": 0}
    region_caps = {"US": us_target, "ADR": adr_target}

    def can_add(candidate: StockCandidate) -> bool:
        if candidate.symbol in selected_symbols:
            return False
        if _issuer_key(candidate) in selected_issuers:
            return False
        if len(selected) >= count:
            return False
        if sector_counts.get(candidate.sector, 0) >= max_per_sector:
            return False
        cap = region_caps.get(candidate.region)
        return cap is None or region_counts.get(candidate.region, 0) < cap

    def add(candidate: StockCandidate) -> bool:
        if not can_add(candidate):
            return False
        selected.append(candidate)
        selected_symbols.add(candidate.symbol)
        selected_issuers.add(_issuer_key(candidate))
        sector_counts[candidate.sector] = sector_counts.get(candidate.sector, 0) + 1
        region_counts[candidate.region] = region_counts.get(candidate.region, 0) + 1
        return True

    for candidate in sorted(forced_candidates or [], key=lambda item: item.composite_score, reverse=True):
        if candidate.symbol in selected_symbols or _issuer_key(candidate) in selected_issuers or len(selected) >= count:
            continue
        selected.append(candidate)
        selected_symbols.add(candidate.symbol)
        selected_issuers.add(_issuer_key(candidate))
        sector_counts[candidate.sector] = sector_counts.get(candidate.sector, 0) + 1
        region_counts[candidate.region] = region_counts.get(candidate.region, 0) + 1

    sector_order = sorted(
        MAJOR_SECTORS,
        key=lambda sector: max((item.composite_score for item in sorted_candidates if item.sector == sector), default=-1),
        reverse=True,
    )
    for sector in sector_order:
        if len({item.sector for item in selected if item.sector in MAJOR_SECTORS}) >= min_major_sectors:
            break
        for candidate in sorted_candidates:
            if candidate.sector == sector and add(candidate):
                break

    for candidate in sorted_candidates:
        add(candidate)

    if len(selected) < count:
        for candidate in sorted_candidates:
            if candidate.symbol in selected_symbols or len(selected) >= count:
                continue
            if _issuer_key(candidate) in selected_issuers:
                continue
            if sector_counts.get(candidate.sector, 0) >= max_per_sector:
                continue
            selected.append(candidate)
            selected_symbols.add(candidate.symbol)
            selected_issuers.add(_issuer_key(candidate))
            sector_counts[candidate.sector] = sector_counts.get(candidate.sector, 0) + 1

    return selected


def build_universe(args: argparse.Namespace) -> dict[str, Any]:
    session = requests.Session()
    forced_symbols = {symbol.strip().upper() for symbol in args.force_tickers.split(",") if symbol.strip()}
    raw_candidates = fetch_nasdaq_candidates(session, limit=args.nasdaq_limit)
    raw_candidates.sort(key=lambda item: ((item.dollar_volume or 0), (item.market_cap or 0)), reverse=True)
    candidates = raw_candidates[: args.candidate_pool]
    missing_forced_candidates = [
        candidate for candidate in raw_candidates if candidate.symbol in forced_symbols and candidate.symbol not in {item.symbol for item in candidates}
    ]
    candidates.extend(missing_forced_candidates)
    enrich_history(candidates, chunk_size=args.history_chunk_size)
    score_candidates(candidates)
    spread_pool = sorted(candidates, key=lambda item: item.composite_score, reverse=True)
    enrich_spreads(
        session,
        spread_pool,
        limit=args.spread_enrich_limit,
        delay=args.quote_delay,
        timeout=args.quote_timeout,
    )
    score_candidates(candidates)
    eligible = filter_candidates(
        candidates,
        min_price=args.min_price,
        min_market_cap=args.min_market_cap,
        min_dollar_volume=args.min_dollar_volume,
        min_avg_dollar_volume=args.min_avg_dollar_volume,
        min_data_quality=args.min_data_quality,
    )
    forced_candidates = [candidate for candidate in candidates if candidate.symbol in forced_symbols]
    forced_missing = sorted(forced_symbols - {candidate.symbol for candidate in forced_candidates})
    selected = select_balanced_universe(
        eligible,
        count=args.count,
        us_target=args.us_target,
        adr_target=args.adr_target,
        max_per_sector=args.max_per_sector,
        min_major_sectors=args.min_major_sectors,
        forced_candidates=forced_candidates,
    )
    selected.sort(key=lambda item: item.composite_score, reverse=True)
    rows = [asdict(item) for item in selected]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "candidate_pool": "nasdaq_screener_stocks",
            "history": "yfinance_1mo_daily",
            "spread": "nasdaq_quote_bid_ask",
        },
        "parameters": {
            "count": args.count,
            "candidate_pool": args.candidate_pool,
            "nasdaq_limit": args.nasdaq_limit,
            "region_targets": {"US": args.us_target, "ADR": args.adr_target},
            "max_per_sector": args.max_per_sector,
            "min_major_sectors": args.min_major_sectors,
            "min_price": args.min_price,
            "min_market_cap": args.min_market_cap,
            "min_dollar_volume": args.min_dollar_volume,
            "min_avg_dollar_volume": args.min_avg_dollar_volume,
            "min_data_quality": args.min_data_quality,
            "spread_enrich_limit": args.spread_enrich_limit,
            "quote_timeout": args.quote_timeout,
            "force_tickers": sorted(forced_symbols),
        },
        "methodology": (
            "Build a broad US-listed candidate pool, compute liquidity/activity/size/volatility/data-quality scores, "
            "then apply region and sector caps so the output is liquid but not dominated by one theme."
        ),
        "tickers": [item.symbol for item in selected],
        "rows": rows,
        "summary": {
            "raw_candidates": len(raw_candidates),
            "scored_candidates": len(candidates),
            "eligible_candidates": len(eligible),
            "selected_count": len(selected),
            "forced_selected": sorted(symbol for symbol in forced_symbols if symbol in {item.symbol for item in selected}),
            "forced_missing": forced_missing,
            "region_counts": _counts(item.region for item in selected),
            "sector_counts": _counts(item.sector for item in selected),
        },
    }


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a balanced stock universe for Open Data Fundamentals.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Where to write stocks.json.")
    parser.add_argument("--count", type=int, default=500, help="Number of tickers to select.")
    parser.add_argument("--candidate-pool", type=int, default=2500, help="How many high-liquidity candidates to score deeply.")
    parser.add_argument("--nasdaq-limit", type=int, default=12000, help="How many Nasdaq screener rows to fetch.")
    parser.add_argument("--us-target", type=int, default=425, help="Maximum US common-stock selections.")
    parser.add_argument("--adr-target", type=int, default=75, help="Maximum ADR/foreign-listed selections.")
    parser.add_argument("--max-per-sector", type=int, default=90)
    parser.add_argument("--min-major-sectors", type=int, default=8)
    parser.add_argument("--min-price", type=float, default=5)
    parser.add_argument("--min-market-cap", type=float, default=1_000_000_000)
    parser.add_argument("--min-dollar-volume", type=float, default=25_000_000)
    parser.add_argument("--min-avg-dollar-volume", type=float, default=50_000_000)
    parser.add_argument("--min-data-quality", type=float, default=0.75)
    parser.add_argument("--spread-enrich-limit", type=int, default=120)
    parser.add_argument("--history-chunk-size", type=int, default=80)
    parser.add_argument("--quote-delay", type=float, default=0.02)
    parser.add_argument("--quote-timeout", type=float, default=5)
    parser.add_argument(
        "--force-tickers",
        default="DT",
        help="Comma-separated ticker symbols to force into the output universe when present in the source pool.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv or sys.argv[1:])
    result = build_universe(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output),
                **result["summary"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
