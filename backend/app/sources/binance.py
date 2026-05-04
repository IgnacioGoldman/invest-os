from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import requests

from app.config import Settings
from app.models import CashBalance, Holding, Order, SourceResult
from app.services.normalization import as_float, infer_asset_class, parse_datetime, stable_id


BINANCE_BASE_URL = "https://api.binance.com"
QUOTE_ASSETS = ("EUR", "USDT", "USDC", "FDUSD", "BTC", "ETH")


class BinanceClient:
    def __init__(self, settings: Settings):
        self.api_key = settings.binance_api_key
        self.api_secret = settings.binance_api_secret

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.api_secret)

    def _signed_get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self.api_secret:
            raise RuntimeError("Binance API secret is not configured.")
        query = dict(params or {})
        query["timestamp"] = int(time.time() * 1000)
        query.setdefault("recvWindow", 5000)
        encoded = urlencode(query)
        signature = hmac.new(self.api_secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        headers = {"X-MBX-APIKEY": self.api_key or ""}
        response = requests.get(
            f"{BINANCE_BASE_URL}{path}?{encoded}&signature={signature}",
            headers=headers,
            timeout=12,
        )
        response.raise_for_status()
        return response.json()

    def _public_get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = requests.get(f"{BINANCE_BASE_URL}{path}", params=params or {}, timeout=12)
        response.raise_for_status()
        return response.json()


def _ticker_map(client: BinanceClient) -> tuple[dict[str, float], list[str]]:
    warnings: list[str] = []
    try:
        rows = client._public_get("/api/v3/ticker/price")
        return {row["symbol"]: as_float(row["price"]) for row in rows if "symbol" in row}, warnings
    except requests.RequestException as exc:
        warnings.append(f"Binance public ticker fetch failed: {exc}")
        return {}, warnings


def _price_asset(asset: str, tickers: dict[str, float]) -> tuple[float | None, str]:
    if asset == "EUR":
        return 1.0, "EUR"
    for quote in QUOTE_ASSETS:
        pair = f"{asset}{quote}"
        if pair in tickers:
            return tickers[pair], quote
    if asset in {"USDT", "USDC", "FDUSD"}:
        return 1.0, asset
    return None, asset


def _symbols_for_history(assets: list[str], open_orders: list[dict[str, Any]]) -> list[str]:
    symbols = {str(order.get("symbol")) for order in open_orders if order.get("symbol")}
    for asset in assets:
        for quote in ("EUR", "USDT", "USDC"):
            if asset != quote:
                symbols.add(f"{asset}{quote}")
    return sorted(symbols)[:25]


def _normalize_order(raw: dict[str, Any], is_history: bool = False) -> Order:
    symbol = str(raw.get("symbol") or "UNKNOWN")
    created = raw.get("time") or raw.get("transactTime") or raw.get("updateTime")
    order_id = (raw.get("id") if is_history else raw.get("orderId")) or raw.get("orderId") or stable_id(
        "binance-order", symbol, created
    )
    quantity = as_float(raw.get("origQty") or raw.get("qty") or raw.get("executedQty"))
    raw_side = raw.get("side")
    if raw_side is None and "isBuyer" in raw:
        raw_side = "BUY" if raw.get("isBuyer") else "SELL"
    return Order(
        id=stable_id("binance", order_id, symbol, "history" if is_history else "open"),
        source="binance",
        platform="Binance",
        symbol=symbol,
        side="SELL" if str(raw_side).upper() == "SELL" else "BUY",
        order_type=raw.get("type") or "trade",
        quantity=quantity,
        limit_price=as_float(raw.get("price")) or None,
        status=raw.get("status") or ("FILLED" if is_history else "OPEN"),
        created_at=parse_datetime(created) if created else None,
        raw=raw,
    )


def fetch_binance(settings: Settings) -> SourceResult:
    client = BinanceClient(settings)
    if not client.configured:
        return SourceResult(warnings=["Binance credentials are missing; skipped Binance API collection."])

    warnings: list[str] = []
    try:
        account = client._signed_get("/api/v3/account")
    except requests.RequestException as exc:
        return SourceResult(warnings=[f"Binance account fetch failed: {exc}"])

    tickers, ticker_warnings = _ticker_map(client)
    warnings.extend(ticker_warnings)

    holdings: list[Holding] = []
    cash_balances: list[CashBalance] = []
    nonzero_assets: list[str] = []
    now = datetime.now(timezone.utc)

    for balance in account.get("balances", []):
        asset = str(balance.get("asset") or "").upper()
        free = as_float(balance.get("free"))
        locked = as_float(balance.get("locked"))
        quantity = free + locked
        if not asset or quantity <= 0:
            continue
        nonzero_assets.append(asset)
        if asset in {"EUR", "USD", "GBP", "SEK", "USDT", "USDC", "FDUSD"}:
            cash_balances.append(
                CashBalance(
                    id=stable_id("binance-cash", asset),
                    source="binance",
                    platform="Binance",
                    currency=asset,
                    balance=quantity,
                    purpose="deployable_cash",
                    updated_at=now,
                )
            )
            continue

        current_price, currency = _price_asset(asset, tickers)
        market_value = quantity * current_price if current_price is not None else 0
        if current_price is None:
            warnings.append(f"Binance price unavailable for {asset}; market value set to 0.")
        holdings.append(
            Holding(
                id=stable_id("binance-holding", asset),
                source="binance",
                platform="Binance",
                symbol=asset,
                name=asset,
                asset_class=infer_asset_class(asset, "binance"),
                quantity=quantity,
                currency=currency,
                current_price=current_price,
                market_value=market_value,
                confidence="api",
                updated_at=now,
            )
        )

    try:
        raw_open_orders = client._signed_get("/api/v3/openOrders")
        open_orders = [_normalize_order(order) for order in raw_open_orders]
    except requests.RequestException as exc:
        warnings.append(f"Binance open orders fetch failed: {exc}")
        raw_open_orders = []
        open_orders = []

    order_history: list[Order] = []
    # Binance trade history is symbol-scoped; query a conservative symbol set to avoid noisy API use.
    for symbol in _symbols_for_history(nonzero_assets, raw_open_orders):
        try:
            trades = client._signed_get("/api/v3/myTrades", {"symbol": symbol, "limit": 20})
            order_history.extend(_normalize_order({**trade, "symbol": symbol}, is_history=True) for trade in trades)
        except requests.RequestException:
            continue

    if not order_history:
        warnings.append("Binance recent trade history was unavailable or empty for detected symbols.")

    return SourceResult(
        holdings=holdings,
        cash_balances=cash_balances,
        open_orders=open_orders,
        order_history=order_history[:100],
        warnings=warnings,
    )
