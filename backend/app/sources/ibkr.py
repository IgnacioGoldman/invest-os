from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode, urljoin
from urllib.request import urlopen
import xml.etree.ElementTree as ET

try:
    import requests
except ImportError:  # pragma: no cover - fallback for minimal installs.
    requests = None

from app.config import Settings
from app.models import CashBalance, Holding, Order, SourceResult
from app.services.normalization import as_float, infer_asset_class, stable_id

FLEX_SEND_REQUEST_URL = "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest"
FLEX_GET_STATEMENT_URL = "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement"
FLEX_VERSION = "3"
FLEX_TIMEOUT_SECONDS = 30


def _ensure_event_loop() -> None:
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def _ib_imports():
    _ensure_event_loop()
    from ib_insync import IB, ExecutionFilter

    return IB, ExecutionFilter


def _contract_symbol(contract: Any) -> str:
    return str(getattr(contract, "symbol", None) or getattr(contract, "localSymbol", None) or "UNKNOWN")


def _usable_price(*values: Any) -> float | None:
    for value in values:
        price = as_float(value)
        if price > 0 and price < 1_000_000_000:
            return price
    return None


def _ib_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", " ")
    for fmt in (
        "%Y%m%d %H:%M:%S",
        "%Y%m%d  %H:%M:%S",
        "%Y%m%d-%H:%M:%S",
        "%Y%m%d;%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d;%H:%M:%S",
        "%Y%m%d",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _trade_created_at(trade: Any) -> datetime | None:
    fills = getattr(trade, "fills", None) or []
    if fills:
        created = _ib_datetime(getattr(getattr(fills[0], "execution", None), "time", None))
        if created:
            return created
    logs = getattr(trade, "log", None) or []
    for entry in reversed(logs):
        created = _ib_datetime(getattr(entry, "time", None))
        if created:
            return created
    status = getattr(trade, "orderStatus", None)
    return _ib_datetime(getattr(status, "completedTime", None))


def _xml_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_text(root: ET.Element, name: str) -> str | None:
    for child in root.iter():
        if _xml_name(child.tag).lower() == name.lower() and child.text:
            return child.text.strip()
    return None


def _flex_http_get(url: str, params: dict[str, str]) -> ET.Element:
    if requests is not None:
        response = requests.get(url, params=params, timeout=FLEX_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.content
    else:
        separator = "&" if "?" in url else "?"
        request_url = f"{url}{separator}{urlencode(params)}"
        with urlopen(request_url, timeout=FLEX_TIMEOUT_SECONDS) as response:
            payload = response.read()
    return ET.fromstring(payload)


def _flex_statement_url(raw_url: str | None) -> str:
    if not raw_url:
        return FLEX_GET_STATEMENT_URL
    url = raw_url.strip()
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return urljoin("https://gdcdyn.interactivebrokers.com", url)
    if "." in url.split("/", 1)[0]:
        return f"https://{url}"
    return FLEX_GET_STATEMENT_URL


def _flex_error(root: ET.Element) -> str | None:
    status = _xml_text(root, "Status")
    if status and status.lower() != "success":
        code = _xml_text(root, "ErrorCode")
        message = _xml_text(root, "ErrorMessage") or status
        return f"{code}: {message}" if code else message
    message = _xml_text(root, "ErrorMessage")
    if message:
        code = _xml_text(root, "ErrorCode")
        return f"{code}: {message}" if code else message
    return None


def _flex_retryable_error(error: str | None) -> bool:
    if not error:
        return False
    normalized = error.lower()
    return (
        "1001" in normalized
        or "1019" in normalized
        or "could not be generated" in normalized
        or "generation in progress" in normalized
    )


def _redact_flex_token(text: str, settings: Settings) -> str:
    if settings.ibkr_flex_token:
        text = text.replace(settings.ibkr_flex_token, "<redacted>")
    return text


def _flex_attr(attrs: dict[str, str], *names: str) -> str | None:
    lowered = {key.lower(): value for key, value in attrs.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value not in (None, ""):
            return value.strip()
    return None


def _flex_float(attrs: dict[str, str], *names: str) -> float:
    value = _flex_attr(attrs, *names)
    if value is None:
        return 0.0
    return as_float(value.replace(",", ""))


def _flex_side(attrs: dict[str, str], quantity: float) -> str:
    raw_side = (_flex_attr(attrs, "buySell", "side", "action") or "").upper()
    transaction_type = (_flex_attr(attrs, "transactionType", "type") or "").upper()
    if raw_side.startswith(("SELL", "SLD", "S")) or "SELL" in transaction_type or "SLD" in transaction_type:
        return "SELL"
    if raw_side.startswith(("BUY", "BOT", "B")) or "BUY" in transaction_type or "BOT" in transaction_type:
        return "BUY"
    return "SELL" if quantity < 0 else "BUY"


def _flex_trade_datetime(attrs: dict[str, str]) -> datetime | None:
    return (
        _ib_datetime(_flex_attr(attrs, "dateTime", "tradeTime", "time"))
        or _ib_datetime(_flex_attr(attrs, "tradeDate", "date", "reportDate"))
    )


def _normalize_flex_trade(attrs: dict[str, str]) -> Order | None:
    asset_category = (_flex_attr(attrs, "assetCategory") or "").upper()
    if asset_category == "CASH":
        return None

    symbol = _flex_attr(attrs, "symbol", "underlyingSymbol", "description")
    if not symbol:
        return None

    raw_quantity = _flex_float(attrs, "quantity", "shares")
    quantity = abs(raw_quantity)
    if quantity <= 0:
        return None

    price = _usable_price(_flex_attr(attrs, "tradePrice", "price"))
    trade_money = abs(_flex_float(attrs, "tradeMoney", "proceeds"))
    quote_amount = trade_money or (quantity * price if price is not None else None)
    currency = (_flex_attr(attrs, "currency", "ibCommissionCurrency") or "UNKNOWN").upper()
    side = _flex_side(attrs, raw_quantity)
    created_at = _flex_trade_datetime(attrs)
    trade_id = _flex_attr(attrs, "tradeID", "tradeId", "transactionID", "ibOrderID", "orderID", "orderId")
    account_id = _flex_attr(attrs, "accountId", "accountID", "account")

    raw = dict(attrs)
    raw.update(
        {
            "source": "flex_web_service",
            "quoteQty": quote_amount,
            "commission": abs(_flex_float(attrs, "ibCommission", "commission")),
            "commissionAsset": _flex_attr(attrs, "ibCommissionCurrency", "commissionCurrency"),
        }
    )

    return Order(
        id=stable_id("ibkr-flex-trade", account_id, trade_id, symbol, side, created_at, quantity, price, quote_amount),
        source="ibkr",
        platform="Interactive Brokers",
        symbol=symbol.upper(),
        side=side,  # type: ignore[arg-type]
        order_type=_flex_attr(attrs, "transactionType", "assetCategory") or "flex_trade",
        quantity=quantity,
        limit_price=price,
        status="FILLED",
        created_at=created_at,
        quote_currency=currency,
        purchase_amount=quote_amount,
        raw=raw,
    )


def _parse_flex_trades(xml_payload: str | bytes) -> list[Order]:
    root = ET.fromstring(xml_payload)
    orders: list[Order] = []
    for item in root.iter():
        if _xml_name(item.tag) != "Trade":
            continue
        order = _normalize_flex_trade(dict(item.attrib))
        if order is not None:
            orders.append(order)
    return orders


def fetch_ibkr_flex_history(settings: Settings) -> SourceResult:
    if not settings.ibkr_flex_token:
        return SourceResult(warnings=["IBKR_FLEX_TOKEN is not configured; skipped IBKR Flex history import."])

    try:
        request: ET.Element | None = None
        request_error: str | None = None
        for attempt in range(4):
            request = _flex_http_get(
                FLEX_SEND_REQUEST_URL,
                {"t": settings.ibkr_flex_token, "q": settings.ibkr_flex_query_id, "v": FLEX_VERSION},
            )
            request_error = _flex_error(request)
            if not _flex_retryable_error(request_error):
                break
            if attempt < 3:
                time.sleep(2 + attempt * 2)
        error = request_error
        if error:
            return SourceResult(warnings=[f"IBKR Flex request failed: {error}"])
        if request is None:
            return SourceResult(warnings=["IBKR Flex request failed: empty response."])

        reference_code = _xml_text(request, "ReferenceCode")
        if not reference_code:
            return SourceResult(warnings=["IBKR Flex request did not return a reference code."])

        statement_url = _flex_statement_url(_xml_text(request, "Url"))
        statement: ET.Element | None = None
        statement_error: str | None = None
        for attempt in range(5):
            statement = _flex_http_get(
                statement_url,
                {"t": settings.ibkr_flex_token, "q": reference_code, "v": FLEX_VERSION},
            )
            statement_error = _flex_error(statement)
            if not _flex_retryable_error(statement_error):
                break
            if attempt < 4:
                time.sleep(2 + attempt * 2)
        if statement_error:
            return SourceResult(warnings=[f"IBKR Flex statement fetch failed: {statement_error}"])
        if statement is None:
            return SourceResult(warnings=["IBKR Flex statement fetch failed: empty response."])

        order_history = [
            order.model_copy(update={"raw": {**order.raw, "flex_query_id": settings.ibkr_flex_query_id}})
            for order in _parse_flex_trades(ET.tostring(statement, encoding="utf-8"))
        ]
        if not order_history:
            return SourceResult(warnings=["IBKR Flex statement returned no Trade rows. Check query 1554875 includes Trades."])
        return SourceResult(order_history=order_history)
    except Exception as exc:
        detail = _redact_flex_token(str(exc) or exc.__class__.__name__, settings)
        return SourceResult(warnings=[f"IBKR Flex history fetch failed: {detail}"])


def _normalize_ib_order(trade: Any) -> Order:
    contract = getattr(trade, "contract", None)
    order = getattr(trade, "order", None)
    status = getattr(trade, "orderStatus", None)
    symbol = _contract_symbol(contract)
    currency = str(getattr(contract, "currency", None) or "UNKNOWN").upper()
    side = str(getattr(order, "action", "BUY")).upper()
    created = _trade_created_at(trade)
    return Order(
        id=stable_id("ibkr-order", getattr(order, "orderId", None), symbol),
        source="ibkr",
        platform="Interactive Brokers",
        symbol=symbol,
        side="SELL" if side == "SELL" else "BUY",
        order_type=getattr(order, "orderType", None),
        quantity=as_float(getattr(order, "totalQuantity", None)),
        limit_price=as_float(getattr(order, "lmtPrice", None)) or None,
        status=getattr(status, "status", None),
        created_at=created,
        quote_currency=currency,
        raw={
            "orderId": getattr(order, "orderId", None),
            "permId": getattr(order, "permId", None),
            "clientId": getattr(order, "clientId", None),
            "account": getattr(order, "account", None),
            "currency": currency,
        },
    )


def _normalize_fill(fill: Any) -> Order:
    execution = fill.execution
    contract = fill.contract
    symbol = _contract_symbol(contract)
    currency = str(getattr(contract, "currency", None) or "UNKNOWN").upper()
    quantity = as_float(execution.shares)
    price = _usable_price(execution.price)
    return Order(
        id=stable_id("ibkr-fill", execution.execId, symbol),
        source="ibkr",
        platform="Interactive Brokers",
        symbol=symbol,
        side="SELL" if str(execution.side).upper().startswith("SLD") else "BUY",
        order_type="execution",
        quantity=quantity,
        limit_price=price,
        status="FILLED",
        created_at=execution.time,
        quote_currency=currency,
        purchase_amount=quantity * price if price is not None else None,
        raw={
            "execId": execution.execId,
            "orderId": execution.orderId,
            "account": execution.acctNumber,
            "exchange": execution.exchange,
            "currency": currency,
        },
    )


def _normalize_completed_trade(trade: Any) -> Order | None:
    contract = getattr(trade, "contract", None)
    order = getattr(trade, "order", None)
    status = getattr(trade, "orderStatus", None)
    if contract is None or order is None:
        return None

    symbol = _contract_symbol(contract)
    currency = str(getattr(contract, "currency", None) or "UNKNOWN").upper()
    side = str(getattr(order, "action", "BUY")).upper()
    status_text = str(getattr(status, "status", None) or "FILLED").upper()
    filled_quantity = as_float(getattr(status, "filled", None))
    quantity = filled_quantity or as_float(getattr(order, "totalQuantity", None))
    if quantity <= 0 or ("FILLED" not in status_text and filled_quantity <= 0):
        return None

    price = _usable_price(getattr(status, "avgFillPrice", None), getattr(order, "lmtPrice", None))
    order_id = getattr(order, "orderId", None)
    perm_id = getattr(order, "permId", None)
    created_at = _trade_created_at(trade)

    return Order(
        id=stable_id("ibkr-completed-order", perm_id, order_id, symbol, created_at),
        source="ibkr",
        platform="Interactive Brokers",
        symbol=symbol,
        side="SELL" if side == "SELL" else "BUY",
        order_type=getattr(order, "orderType", None) or "completed_order",
        quantity=quantity,
        limit_price=price,
        status=getattr(status, "status", None) or "FILLED",
        created_at=created_at,
        quote_currency=currency,
        purchase_amount=quantity * price if price is not None else None,
        raw={
            "orderId": order_id,
            "permId": perm_id,
            "clientId": getattr(order, "clientId", None),
            "account": getattr(order, "account", None),
            "currency": currency,
            "source": "completed_orders",
        },
    )


def _select_cash_values(account_values: list[Any], base_currency: str) -> list[Any]:
    candidates = [
        value
        for value in account_values
        if value.tag in {"CashBalance", "TotalCashBalance", "SettledCash"} and as_float(value.value) != 0
    ]
    if not candidates:
        return []

    # IBKR can return overlapping cash rows such as CashBalance, SettledCash,
    # TotalCashBalance, and BASE pseudo-currency. Prefer TotalCashBalance and
    # concrete currencies so the same cash is not counted multiple times.
    preferred = [value for value in candidates if value.tag == "TotalCashBalance"] or candidates
    concrete = [value for value in preferred if str(value.currency or "").upper() not in {"BASE", ""}]
    selected = concrete or preferred

    by_currency: dict[str, Any] = {}
    for value in selected:
        currency = str(value.currency or base_currency).upper()
        if currency == "BASE":
            currency = base_currency.upper()
        existing = by_currency.get(currency)
        if existing is None or value.tag == "TotalCashBalance":
            by_currency[currency] = value
    return list(by_currency.values())


def _connect(settings: Settings):
    try:
        IB, ExecutionFilter = _ib_imports()
    except ImportError:
        return None, None, SourceResult(warnings=["ib_insync is not installed; skipped IBKR collection."])

    ib = IB()
    ib.RequestTimeout = 8
    try:
        ib.connect(
            settings.ibkr_host,
            settings.ibkr_port,
            clientId=settings.ibkr_client_id,
            timeout=6,
            readonly=True,
        )
    except Exception as exc:
        return None, None, SourceResult(warnings=[f"IBKR connection failed; is TWS or IB Gateway running? {exc}"])
    return ib, ExecutionFilter, None


def fetch_ibkr(settings: Settings) -> SourceResult:
    ib, _execution_filter, error = _connect(settings)
    if error:
        return error

    warnings: list[str] = []
    try:
        now = datetime.now(timezone.utc)
        holdings: list[Holding] = []
        cash_balances: list[CashBalance] = []

        for item in ib.portfolio():
            contract = item.contract
            symbol = _contract_symbol(contract)
            quantity = as_float(item.position)
            if quantity == 0:
                continue
            currency = str(getattr(contract, "currency", None) or "UNKNOWN").upper()
            holdings.append(
                Holding(
                    id=stable_id("ibkr-holding", getattr(contract, "conId", None), symbol),
                    source="ibkr",
                    platform="Interactive Brokers",
                    symbol=symbol,
                    name=getattr(contract, "localSymbol", None) or symbol,
                    asset_class=infer_asset_class(symbol, "ibkr"),
                    quantity=quantity,
                    currency=currency,
                    current_price=as_float(item.marketPrice) or None,
                    market_value=as_float(item.marketValue),
                    cost_basis=as_float(item.averageCost) * quantity if item.averageCost else None,
                    unrealized_pnl=as_float(item.unrealizedPNL),
                    confidence="api",
                    updated_at=now,
                )
            )

        for value in _select_cash_values(ib.accountValues(), settings.base_currency):
            amount = as_float(value.value)
            currency = str(value.currency or settings.base_currency).upper()
            if currency == "BASE":
                currency = settings.base_currency
            cash_balances.append(
                CashBalance(
                    id=stable_id("ibkr-cash", value.account, value.currency, value.tag),
                    source="ibkr",
                    platform="Interactive Brokers",
                    currency=currency,
                    balance=amount,
                    purpose="deployable_cash",
                    updated_at=now,
                )
            )

        open_orders = [_normalize_ib_order(trade) for trade in ib.openTrades()]

        return SourceResult(
            holdings=holdings,
            cash_balances=cash_balances,
            open_orders=open_orders,
            warnings=warnings,
        )
    except Exception as exc:
        return SourceResult(warnings=[f"IBKR data fetch failed: {exc}"])
    finally:
        if ib.isConnected():
            ib.disconnect()


def fetch_ibkr_api_history(settings: Settings) -> SourceResult:
    ib, ExecutionFilter, error = _connect(settings)
    if error:
        return error

    warnings: list[str] = []
    try:
        # Execution history is a separate request because IBKR does not expose a durable
        # full order database through the local API. This returns recent API-visible fills,
        # then falls back to completed order records when TWS/Gateway exposes them.
        fills = ib.reqExecutions(ExecutionFilter()) or ib.fills()
        order_history = [_normalize_fill(fill) for fill in fills]
        fill_order_ids = {
            getattr(fill.execution, "orderId", None)
            for fill in fills
            if getattr(fill, "execution", None) is not None
        }
        if hasattr(ib, "reqCompletedOrders"):
            try:
                completed_trades = ib.reqCompletedOrders(apiOnly=False) or []
                completed_rows = [
                    row
                    for trade in completed_trades
                    if getattr(getattr(trade, "order", None), "orderId", None) not in fill_order_ids
                    if (row := _normalize_completed_trade(trade)) is not None
                ]
                order_history.extend(completed_rows)
            except Exception as exc:
                detail = str(exc) or exc.__class__.__name__
                warnings.append(f"IBKR completed-order history fetch failed: {detail}")
        if not order_history:
            warnings.append(
                "IBKR activity history returned no executions. TWS/Gateway usually exposes only recent "
                "API-visible executions; older purchases may require an IBKR Activity Statement/Flex import."
            )
        return SourceResult(order_history=order_history, warnings=warnings)
    except Exception as exc:
        return SourceResult(warnings=[f"IBKR execution history fetch failed: {exc}"])
    finally:
        if ib.isConnected():
            ib.disconnect()


def fetch_ibkr_history(settings: Settings) -> SourceResult:
    if not settings.ibkr_flex_token:
        return fetch_ibkr_api_history(settings)

    flex_result = fetch_ibkr_flex_history(settings)
    if flex_result.order_history:
        return flex_result

    api_result = fetch_ibkr_api_history(settings)
    if api_result.order_history:
        return SourceResult(
            order_history=api_result.order_history,
            warnings=[
                *flex_result.warnings,
                "IBKR Flex history failed; used recent TWS/Gateway execution history instead.",
                *api_result.warnings,
            ],
        )

    return SourceResult(warnings=[*flex_result.warnings, *api_result.warnings])
