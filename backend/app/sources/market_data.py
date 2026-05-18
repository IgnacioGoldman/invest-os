from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO

import requests

from app.models import Holding, MarketPrice
from app.services.normalization import as_float


BINANCE_TICKERS_URL = "https://api.binance.com/api/v3/ticker/price"
STOOQ_URL = "https://stooq.com/q/l/"
STABLE_QUOTES = ("USDT", "USDC", "FDUSD")
QUOTE_PRIORITY = ("EUR", "USD", "USDT", "USDC", "FDUSD")


def _fetch_binance_tickers() -> tuple[dict[str, float], str | None]:
    try:
        response = requests.get(BINANCE_TICKERS_URL, timeout=12)
        response.raise_for_status()
        rows = response.json()
        return {row["symbol"].upper(): as_float(row["price"]) for row in rows if row.get("symbol")}, None
    except requests.RequestException as exc:
        return {}, f"Binance market price fetch failed: {exc}"


def _stooq_symbols(symbol: str, currency: str) -> list[str]:
    normalized = symbol.strip().lower()
    if not normalized or not normalized.replace(".", "").replace("-", "").isalnum():
        return []
    if "." in normalized:
        return [normalized]
    if currency.upper() == "EUR":
        return [f"{normalized}.de", f"{normalized}.nl", f"{normalized}.mi", f"{normalized}.pa", f"{normalized}.as"]
    if currency.upper() == "GBP":
        return [f"{normalized}.uk", f"{normalized}.us"]
    return [f"{normalized}.us", f"{normalized}.de", f"{normalized}.nl"]


def _fetch_stooq_price(symbol: str, currency: str) -> tuple[float | None, str | None]:
    for query_symbol in _stooq_symbols(symbol, currency):
        try:
            response = requests.get(
                STOOQ_URL,
                params={"s": query_symbol, "f": "sd2t2c", "h": "", "e": "csv"},
                timeout=10,
            )
            response.raise_for_status()
            rows = list(csv.DictReader(StringIO(response.text)))
            if not rows:
                continue
            close = rows[0].get("Close")
            if not close or close == "N/D":
                continue
            return float(close), f"stooq:{query_symbol.upper()}"
        except (ValueError, requests.RequestException):
            continue
    return None, None


def _binance_price_for_holding(holding: Holding, tickers: dict[str, float]) -> tuple[float | None, str | None]:
    symbol = holding.symbol.upper()
    preferred_currency = "USD" if holding.currency.upper() in STABLE_QUOTES else holding.currency.upper()
    candidates = [preferred_currency, *QUOTE_PRIORITY]
    for quote in dict.fromkeys(candidates):
        pair_quote = "USDT" if quote == "USD" else quote
        pair = f"{symbol}{pair_quote}"
        if pair in tickers:
            return tickers[pair], pair_quote
    return None, None


def fetch_market_prices(holdings: list[Holding]) -> tuple[list[MarketPrice], list[str]]:
    now = datetime.now(timezone.utc)
    prices: list[MarketPrice] = []
    warnings: list[str] = []
    tickers, ticker_warning = _fetch_binance_tickers()
    if ticker_warning:
        warnings.append(ticker_warning)

    seen: set[tuple[str, str]] = set()
    for holding in holdings:
        symbol = holding.symbol.upper()
        if not symbol or symbol == "UNKNOWN":
            continue

        price = None
        currency = None
        source = None

        if holding.asset_class.lower() == "crypto" or holding.source == "binance":
            price, currency = _binance_price_for_holding(holding, tickers)
            source = "binance_public" if price is not None else None
        elif holding.asset_class.lower() in {"stock", "equity", "etf"}:
            price, source = _fetch_stooq_price(symbol, holding.currency)
            currency = holding.currency.upper() if price is not None else None

        if price is None or currency is None or source is None:
            if holding.current_price is None:
                warnings.append(f"Market price unavailable for {symbol}.")
            continue

        key = (symbol, currency.upper())
        if key in seen:
            continue
        seen.add(key)
        prices.append(
            MarketPrice(
                symbol=symbol,
                currency=currency.upper(),
                price=price,
                source=source,
                fetched_at=now,
            )
        )

    return prices, warnings
