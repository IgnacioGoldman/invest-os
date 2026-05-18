from __future__ import annotations

import hashlib
import hmac
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import requests

from app.config import Settings
from app.models import BinanceLedgerEvent, CashBalance, HistoricalPrice, Holding, Order, SourceResult
from app.services.normalization import as_float, infer_asset_class, parse_datetime, stable_id


BINANCE_BASE_URL = "https://api.binance.com"
logger = logging.getLogger(__name__)
QUOTE_ASSETS = ("EUR", "USDT", "USDC", "FDUSD", "BTC", "ETH")
USD_LIKE_ASSETS = {"USD", "USDT", "USDC", "FDUSD"}
FIAT_LEDGER_MIN_START = datetime(2025, 10, 1, tzinfo=timezone.utc)
SPOT_WALLET = "MAIN"
TRANSFER_TYPES = (
    "MAIN_UMFUTURE",
    "UMFUTURE_MAIN",
    "MAIN_CMFUTURE",
    "CMFUTURE_MAIN",
    "MAIN_MARGIN",
    "MARGIN_MAIN",
    "MAIN_FUNDING",
    "FUNDING_MAIN",
)


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


def _split_pair(symbol: str) -> tuple[str, str | None]:
    for quote in ("USDT", "USDC", "FDUSD", "EUR", "USD", "BTC", "ETH"):
        if symbol.upper().endswith(quote) and len(symbol) > len(quote):
            return symbol[: -len(quote)].upper(), quote
    return symbol.upper(), None


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
            trades = client._signed_get(
                "/api/v3/myTrades",
                {
                    "symbol": symbol,
                    "limit": 1000,
                    "startTime": _milliseconds(settings.binance_ledger_start_date),
                },
            )
            order_history.extend(
                order
                for trade in trades
                if (order := _normalize_order({**trade, "symbol": symbol}, is_history=True)).created_at
                and order.created_at >= settings.binance_ledger_start_date
            )
        except requests.RequestException:
            continue

    if not order_history:
        warnings.append("Binance recent trade history was unavailable or empty for detected symbols.")

    return SourceResult(
        holdings=holdings,
        cash_balances=cash_balances,
        open_orders=open_orders,
        order_history=order_history,
        warnings=warnings,
    )


def _milliseconds(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


def _minute(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.replace(second=0, microsecond=0)


def _ledger_windows(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    return _time_windows(start, end, days=89)


def _time_windows(start: datetime, end: datetime, *, days: int) -> list[tuple[datetime, datetime]]:
    windows: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        window_end = min(cursor + timedelta(days=days), end)
        windows.append((cursor, window_end))
        cursor = window_end + timedelta(milliseconds=1)
    return windows


def _normalize_deposit(raw: dict[str, Any]) -> BinanceLedgerEvent | None:
    if str(raw.get("status")) not in {"1", "SUCCESS", "success"}:
        return None
    asset = str(raw.get("coin") or raw.get("asset") or "").upper()
    amount = as_float(raw.get("amount"))
    created = raw.get("insertTime") or raw.get("successTime")
    if not asset or amount <= 0 or created is None:
        return None
    return BinanceLedgerEvent(
        id=stable_id("binance-ledger", "deposit", raw.get("txId"), asset, created, amount),
        event_type="deposit",
        asset=asset,
        amount=amount,
        status=str(raw.get("status")),
        created_at=parse_datetime(created),
        balance_changes={asset: amount},
        raw=raw,
    )


def _normalize_withdrawal(raw: dict[str, Any]) -> BinanceLedgerEvent | None:
    if str(raw.get("status")) not in {"6", "COMPLETED", "completed"}:
        return None
    asset = str(raw.get("coin") or raw.get("asset") or "").upper()
    amount = as_float(raw.get("amount"))
    fee = as_float(raw.get("transactionFee"))
    created = raw.get("completeTime") or raw.get("applyTime")
    if not asset or amount <= 0 or created is None:
        return None
    return BinanceLedgerEvent(
        id=stable_id("binance-ledger", "withdrawal", raw.get("id"), raw.get("txId"), asset, created, amount),
        event_type="withdrawal",
        asset=asset,
        amount=amount,
        fee=fee,
        status=str(raw.get("status")),
        created_at=parse_datetime(created),
        balance_changes={asset: -(amount + fee)},
        raw=raw,
    )


def _is_terminal_fiat_status(raw: dict[str, Any]) -> bool:
    status = str(raw.get("status") or raw.get("orderStatus") or "").lower()
    if not status:
        return True
    return not any(marker in status for marker in ("fail", "cancel", "reject", "expired"))


def _normalize_fiat_order(raw: dict[str, Any], transaction_type: int) -> BinanceLedgerEvent | None:
    if not _is_terminal_fiat_status(raw):
        return None
    asset = str(raw.get("fiatCurrency") or raw.get("currency") or raw.get("asset") or "").upper()
    credited_amount = as_float(raw.get("amount"))
    original_amount = as_float(raw.get("indicatedAmount"))
    if original_amount <= 0:
        original_amount = credited_amount
    amount = credited_amount if credited_amount > 0 else original_amount
    fee = as_float(raw.get("totalFee") or raw.get("fee"))
    if fee <= 0 and original_amount > amount and transaction_type == 0:
        fee = original_amount - amount
    created = raw.get("createTime") or raw.get("updateTime")
    if not asset or amount <= 0 or created is None:
        return None
    event_type = "fiat_deposit" if transaction_type == 0 else "fiat_withdrawal"
    signed_amount = amount if transaction_type == 0 else -(amount + fee)
    return BinanceLedgerEvent(
        id=stable_id("binance-ledger", event_type, raw.get("orderNo"), raw.get("id"), asset, created, amount),
        event_type=event_type,
        asset=asset,
        amount=amount,
        original_amount=original_amount,
        credited_amount=amount if transaction_type == 0 else None,
        fee=fee,
        status=str(raw.get("status") or raw.get("orderStatus") or ""),
        created_at=parse_datetime(created),
        balance_changes={asset: signed_amount},
        raw=raw,
    )


def _normalize_universal_transfer(raw: dict[str, Any]) -> BinanceLedgerEvent | None:
    if not isinstance(raw, dict):
        return None
    status = str(raw.get("status") or "").upper()
    if status and status != "CONFIRMED":
        return None
    transfer_type = str(raw.get("type") or "").upper()
    asset = str(raw.get("asset") or "").upper()
    amount = as_float(raw.get("amount"))
    created = raw.get("timestamp")
    if not transfer_type or not asset or amount <= 0 or created is None:
        return None

    from_wallet, _, to_wallet = transfer_type.partition("_")
    spot_change = 0.0
    if from_wallet == SPOT_WALLET:
        spot_change = -amount
    elif to_wallet == SPOT_WALLET:
        spot_change = amount

    return BinanceLedgerEvent(
        id=stable_id("binance-ledger", "transfer", raw.get("tranId"), transfer_type, asset, created, amount),
        event_type="transfer",
        asset=asset,
        amount=amount,
        status=status or None,
        created_at=parse_datetime(created),
        balance_changes={asset: spot_change} if spot_change else {},
        raw=raw,
    )


def _normalize_convert(raw: dict[str, Any]) -> BinanceLedgerEvent | None:
    status = str(raw.get("orderStatus") or raw.get("status") or "").lower()
    if status and "success" not in status and "complete" not in status:
        return None
    from_asset = str(raw.get("fromAsset") or "").upper()
    to_asset = str(raw.get("toAsset") or "").upper()
    from_amount = as_float(raw.get("fromAmount"))
    to_amount = as_float(raw.get("toAmount"))
    created = raw.get("createTime") or raw.get("orderTime")
    if not from_asset or not to_asset or from_amount <= 0 or to_amount <= 0 or created is None:
        return None
    return BinanceLedgerEvent(
        id=stable_id("binance-ledger", "convert", raw.get("orderId"), from_asset, to_asset, created, from_amount, to_amount),
        event_type="convert",
        asset=to_asset,
        amount=to_amount,
        status=str(raw.get("orderStatus") or raw.get("status") or ""),
        created_at=parse_datetime(created),
        balance_changes={from_asset: -from_amount, to_asset: to_amount},
        raw=raw,
    )


def _fiat_rows_from_response(response: Any) -> list[dict[str, Any]]:
    rows = response.get("data", response) if isinstance(response, dict) else response
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _fetch_fiat_orders(
    client: BinanceClient,
    start: datetime,
    end: datetime,
    *,
    transaction_type: int,
    label: str,
) -> list[BinanceLedgerEvent]:
    events: list[BinanceLedgerEvent] = []
    page = 1
    while True:
        fiat_rows = client._signed_get(
            "/sapi/v1/fiat/orders",
            {
                "transactionType": transaction_type,
                "beginTime": _milliseconds(start),
                "endTime": _milliseconds(end),
                "page": page,
                "rows": 500,
            },
        )
        rows = _fiat_rows_from_response(fiat_rows)
        logger.info(
            "Binance fiat %s page %s returned %s raw rows for %s to %s",
            label,
            page,
            len(rows),
            start.date(),
            end.date(),
        )
        events.extend(
            event
            for row in rows
            if (event := _normalize_fiat_order(row, transaction_type)) is not None
        )
        if len(rows) < 500:
            break
        page += 1
    return events


def _fetch_transfer_events(client: BinanceClient, settings: Settings) -> tuple[list[BinanceLedgerEvent], list[str]]:
    warnings: list[str] = []
    events: list[BinanceLedgerEvent] = []
    now = datetime.now(timezone.utc)

    ledger_start = min(settings.binance_ledger_start_date, FIAT_LEDGER_MIN_START)

    for start, end in _ledger_windows(ledger_start, now):
        params = {"startTime": _milliseconds(start), "endTime": _milliseconds(end)}
        try:
            deposits = client._signed_get("/sapi/v1/capital/deposit/hisrec", params)
            events.extend(event for row in deposits if (event := _normalize_deposit(row)) is not None)
        except requests.RequestException as exc:
            warnings.append(f"Binance deposit history fetch failed for {start.date()} to {end.date()}: {exc}")

        try:
            withdrawals = client._signed_get("/sapi/v1/capital/withdraw/history", params)
            events.extend(event for row in withdrawals if (event := _normalize_withdrawal(row)) is not None)
        except requests.RequestException as exc:
            warnings.append(f"Binance withdrawal history fetch failed for {start.date()} to {end.date()}: {exc}")

        try:
            events.extend(_fetch_fiat_orders(client, start, end, transaction_type=0, label="deposits"))
        except requests.RequestException as exc:
            warnings.append(f"Binance fiat deposit history fetch failed for {start.date()} to {end.date()}: {exc}")

        try:
            events.extend(_fetch_fiat_orders(client, start, end, transaction_type=1, label="withdrawals"))
        except requests.RequestException as exc:
            warnings.append(f"Binance fiat withdrawal history fetch failed for {start.date()} to {end.date()}: {exc}")

    universal_start = max(settings.binance_ledger_start_date, now - timedelta(days=179))
    if universal_start > settings.binance_ledger_start_date:
        warnings.append("Binance universal transfer history only supports the last 6 months; older futures/funding transfers were skipped.")
    for start, end in _time_windows(universal_start, now, days=29):
        for transfer_type in TRANSFER_TYPES:
            try:
                page = 1
                while True:
                    transfer_rows = client._signed_get(
                        "/sapi/v1/asset/transfer",
                        {
                            "type": transfer_type,
                            "startTime": _milliseconds(start),
                            "endTime": _milliseconds(end),
                            "current": page,
                            "size": 100,
                        },
                    )
                    rows = transfer_rows.get("rows", []) if isinstance(transfer_rows, dict) else transfer_rows
                    if not isinstance(rows, list):
                        break
                    events.extend(event for row in rows if (event := _normalize_universal_transfer(row)) is not None)
                    if len(rows) < 100:
                        break
                    page += 1
            except requests.RequestException as exc:
                warnings.append(
                    f"Binance universal transfer history fetch failed for {transfer_type} "
                    f"{start.date()} to {end.date()}: {exc}"
                )

    for start, end in _time_windows(settings.binance_ledger_start_date, now, days=29):
        try:
            convert_rows = client._signed_get(
                "/sapi/v1/convert/tradeFlow",
                {"startTime": _milliseconds(start), "endTime": _milliseconds(end), "limit": 1000},
            )
            rows = convert_rows.get("list", convert_rows) if isinstance(convert_rows, dict) else convert_rows
            events.extend(event for row in rows if (event := _normalize_convert(row)) is not None)
        except requests.RequestException as exc:
            warnings.append(f"Binance convert history fetch failed for {start.date()} to {end.date()}: {exc}")

    return events, warnings


def _historical_usd_price(client: BinanceClient, asset: str, priced_at: datetime) -> HistoricalPrice | None:
    asset = asset.upper()
    if asset in USD_LIKE_ASSETS:
        return None
    minute = _minute(priced_at)
    for quote in ("USDT", "USDC", "FDUSD"):
        symbol = f"{asset}{quote}"
        try:
            rows = client._public_get(
                "/api/v3/klines",
                {
                    "symbol": symbol,
                    "interval": "1m",
                    "startTime": _milliseconds(minute),
                    "endTime": _milliseconds(minute + timedelta(minutes=1)),
                    "limit": 1,
                },
            )
        except requests.RequestException:
            continue
        if rows:
            return HistoricalPrice(
                asset=asset,
                currency="USD",
                priced_at=minute,
                price=as_float(rows[0][4]),
                source=f"binance_kline:{symbol}",
                fetched_at=datetime.now(timezone.utc),
            )
    return None


def fetch_binance_historical_prices(
    settings: Settings,
    requirements: dict[datetime, set[str]],
) -> tuple[list[HistoricalPrice], list[str]]:
    client = BinanceClient(settings)
    if not client.configured:
        return [], ["Binance credentials are missing; skipped Binance historical price collection."]

    historical_prices: list[HistoricalPrice] = []
    missing_price_counts: dict[str, int] = {}
    for timestamp, assets in sorted(requirements.items()):
        for asset in sorted(asset.upper() for asset in assets):
            if asset in USD_LIKE_ASSETS:
                continue
            price = _historical_usd_price(client, asset, timestamp)
            if price:
                historical_prices.append(price)
            else:
                missing_price_counts[asset] = missing_price_counts.get(asset, 0) + 1

    warnings = [
        f"Missing Binance historical USD price for {asset} at {count} activity timestamp(s)."
        for asset, count in sorted(missing_price_counts.items())
    ]
    return historical_prices, warnings


def fetch_binance_ledger(settings: Settings, orders: list[Order]) -> tuple[list[BinanceLedgerEvent], list[HistoricalPrice], list[str]]:
    client = BinanceClient(settings)
    if not client.configured:
        return [], [], ["Binance credentials are missing; skipped Binance ledger collection."]

    events, warnings = _fetch_transfer_events(client, settings)

    assets = {event.asset.upper() for event in events}
    for event in events:
        assets.update(asset.upper() for asset in event.balance_changes)
    timestamps = {_minute(order.created_at) for order in orders if order.source == "binance" and order.created_at}
    for order in orders:
        if order.source != "binance":
            continue
        base, quote = _split_pair(order.symbol)
        assets.add(base)
        if quote:
            assets.add(quote)
        commission_asset = order.raw.get("commissionAsset")
        if commission_asset:
            assets.add(str(commission_asset).upper())

    historical_prices, price_warnings = fetch_binance_historical_prices(
        settings,
        {timestamp: set(assets) for timestamp in timestamps},
    )
    warnings.extend(price_warnings)

    if not events:
        warnings.append("Binance ledger is empty or unavailable for the configured date range.")

    return events, historical_prices, warnings
