from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from app.config import Settings
from app.models import CashBalance, Holding, Order, SourceResult
from app.services.normalization import as_float, infer_asset_class, stable_id


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


def _normalize_ib_order(trade: Any) -> Order:
    contract = getattr(trade, "contract", None)
    order = getattr(trade, "order", None)
    status = getattr(trade, "orderStatus", None)
    symbol = _contract_symbol(contract)
    side = str(getattr(order, "action", "BUY")).upper()
    created = None
    fills = getattr(trade, "fills", None) or []
    if fills:
        created = getattr(getattr(fills[0], "execution", None), "time", None)
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
        raw={
            "orderId": getattr(order, "orderId", None),
            "permId": getattr(order, "permId", None),
            "clientId": getattr(order, "clientId", None),
            "account": getattr(order, "account", None),
        },
    )


def _normalize_fill(fill: Any) -> Order:
    execution = fill.execution
    contract = fill.contract
    symbol = _contract_symbol(contract)
    return Order(
        id=stable_id("ibkr-fill", execution.execId, symbol),
        source="ibkr",
        platform="Interactive Brokers",
        symbol=symbol,
        side="SELL" if str(execution.side).upper().startswith("SLD") else "BUY",
        order_type="execution",
        quantity=as_float(execution.shares),
        limit_price=as_float(execution.price) or None,
        status="FILLED",
        created_at=execution.time,
        raw={
            "execId": execution.execId,
            "orderId": execution.orderId,
            "account": execution.acctNumber,
            "exchange": execution.exchange,
        },
    )


def _connect(settings: Settings):
    try:
        IB, ExecutionFilter = _ib_imports()
    except ImportError:
        return None, None, SourceResult(warnings=["ib_insync is not installed; skipped IBKR collection."])

    ib = IB()
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

        for value in ib.accountValues():
            if value.tag not in {"CashBalance", "TotalCashBalance", "SettledCash"}:
                continue
            amount = as_float(value.value)
            if amount == 0:
                continue
            cash_balances.append(
                CashBalance(
                    id=stable_id("ibkr-cash", value.account, value.currency, value.tag),
                    source="ibkr",
                    platform="Interactive Brokers",
                    currency=str(value.currency or "UNKNOWN").upper(),
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


def fetch_ibkr_history(settings: Settings) -> SourceResult:
    ib, ExecutionFilter, error = _connect(settings)
    if error:
        return error

    warnings: list[str] = []
    try:
        # Execution history is a separate request because IBKR does not expose a durable
        # full order database through the local API. This returns recent API-visible fills.
        fills = ib.reqExecutions(ExecutionFilter()) or ib.fills()
        order_history = [_normalize_fill(fill) for fill in fills]
        if not order_history:
            warnings.append("IBKR execution history is empty; TWS/Gateway may only expose recent session data.")
        return SourceResult(order_history=order_history, warnings=warnings)
    except Exception as exc:
        return SourceResult(warnings=[f"IBKR execution history fetch failed: {exc}"])
    finally:
        if ib.isConnected():
            ib.disconnect()
