from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal

from pydantic import BaseModel, Field


SourceName = Literal["binance", "ibkr", "manual", "demo"]
OrderSide = Literal["BUY", "SELL"]
RefreshSource = Literal["all", "binance", "ibkr", "ibkr_history", "manual"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Holding(BaseModel):
    id: str
    source: SourceName
    platform: str
    symbol: str
    name: str | None = None
    asset_class: str
    quantity: float
    currency: str
    current_price: float | None = None
    market_value: float
    cost_basis: float | None = None
    unrealized_pnl: float | None = None
    sector: str | None = None
    vertical: str | None = None
    geography: str | None = None
    confidence: Literal["api", "manual_verified", "manual_unverified"]
    updated_at: datetime = Field(default_factory=utc_now)


class CashBalance(BaseModel):
    id: str
    source: SourceName
    platform: str
    currency: str
    balance: float
    purpose: str = "other"
    updated_at: datetime = Field(default_factory=utc_now)


class Order(BaseModel):
    id: str
    source: SourceName
    platform: str
    symbol: str
    side: OrderSide
    order_type: str | None = None
    quantity: float
    limit_price: float | None = None
    status: str | None = None
    created_at: datetime | None = None
    purpose: str = "unknown"
    raw: Dict[str, Any] = Field(default_factory=dict)


class BreakdownItem(BaseModel):
    name: str
    value: float
    percent: float


class SourceResult(BaseModel):
    holdings: list[Holding] = Field(default_factory=list)
    cash_balances: list[CashBalance] = Field(default_factory=list)
    open_orders: list[Order] = Field(default_factory=list)
    order_history: list[Order] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SourceSyncStatus(BaseModel):
    source: str
    last_synced_at: datetime | None = None
    status: str = "never"
    warning: str | None = None


class RefreshRequest(BaseModel):
    source: RefreshSource = "all"


class PortfolioSnapshot(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    base_currency: str = "EUR"
    total_net_worth: float = 0
    total_cash: float = 0
    total_invested: float = 0
    holdings: list[Holding] = Field(default_factory=list)
    cash_balances: list[CashBalance] = Field(default_factory=list)
    open_orders: list[Order] = Field(default_factory=list)
    order_history: list[Order] = Field(default_factory=list)
    platform_breakdown: list[BreakdownItem] = Field(default_factory=list)
    asset_class_breakdown: list[BreakdownItem] = Field(default_factory=list)
    top_positions: list[Holding] = Field(default_factory=list)
    data_warnings: list[str] = Field(default_factory=list)
    source_sync_status: list[SourceSyncStatus] = Field(default_factory=list)
