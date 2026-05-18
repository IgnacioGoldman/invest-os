from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal

from pydantic import BaseModel, Field


SourceName = Literal["binance", "ibkr", "manual", "demo"]
OrderSide = Literal["BUY", "SELL"]
RefreshSource = Literal[
    "all",
    "binance",
    "binance_ledger",
    "ibkr",
    "ibkr_history",
    "manual",
    "market_data",
    "fx",
    "prices_fx",
]


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
    valuation_source: str | None = None
    valuation_timestamp: datetime | None = None
    value_in_base: float | None = None


class CashBalance(BaseModel):
    id: str
    source: SourceName
    platform: str
    currency: str
    balance: float
    purpose: str = "other"
    updated_at: datetime = Field(default_factory=utc_now)
    value_in_base: float | None = None


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
    quote_currency: str | None = None
    purchase_amount: float | None = None
    current_value: float | None = None
    roi_percent: float | None = None
    cost_basis_amount: float | None = None
    realized_pnl: float | None = None
    realized_roi_percent: float | None = None
    unrealized_pnl: float | None = None
    unrealized_roi_percent: float | None = None
    remaining_quantity: float | None = None
    remaining_cost_basis: float | None = None
    position_status: str | None = None
    account_value_before: float | None = None
    account_value_after: float | None = None
    account_value_currency: str | None = None
    account_value_source: str | None = None
    account_value_warning: str | None = None
    account_balances_after: Dict[str, float] = Field(default_factory=dict)
    account_asset_values_after: Dict[str, float] = Field(default_factory=dict)
    valuation_source: str | None = None
    valuation_timestamp: datetime | None = None


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


class MarketPrice(BaseModel):
    symbol: str
    currency: str
    price: float
    source: str
    fetched_at: datetime = Field(default_factory=utc_now)


class FxRate(BaseModel):
    currency: str
    base_currency: str
    rate: float
    source: str
    fetched_at: datetime = Field(default_factory=utc_now)


class DisplayRate(BaseModel):
    currency: str
    rate_from_base: float
    source: str
    fetched_at: datetime | None = None


class BinanceLedgerEvent(BaseModel):
    id: str
    source: Literal["binance"] = "binance"
    platform: str = "Binance"
    event_type: Literal["start", "deposit", "withdrawal", "convert", "fiat_deposit", "fiat_withdrawal", "transfer"]
    asset: str
    amount: float
    original_amount: float | None = None
    credited_amount: float | None = None
    fee: float = 0
    status: str | None = None
    created_at: datetime
    balance_changes: Dict[str, float] = Field(default_factory=dict)
    raw: Dict[str, Any] = Field(default_factory=dict)
    account_value_after: float | None = None
    account_value_currency: str | None = None
    account_value_source: str | None = None
    account_value_warning: str | None = None
    account_balances_after: Dict[str, float] = Field(default_factory=dict)
    account_asset_values_after: Dict[str, float] = Field(default_factory=dict)


class HistoricalPrice(BaseModel):
    asset: str
    currency: str = "USD"
    priced_at: datetime
    price: float
    source: str
    fetched_at: datetime = Field(default_factory=utc_now)


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
    ledger_events: list[BinanceLedgerEvent] = Field(default_factory=list)
    platform_breakdown: list[BreakdownItem] = Field(default_factory=list)
    asset_class_breakdown: list[BreakdownItem] = Field(default_factory=list)
    top_positions: list[Holding] = Field(default_factory=list)
    data_warnings: list[str] = Field(default_factory=list)
    source_sync_status: list[SourceSyncStatus] = Field(default_factory=list)
    display_rates: list[DisplayRate] = Field(default_factory=list)
