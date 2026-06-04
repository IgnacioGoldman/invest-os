from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StockUniverseItem(BaseModel):
    ticker: str
    name: str | None = None
    exchange: str | None = None
    country: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    avg_volume: float | None = None


class BusinessHealth(BaseModel):
    revenue_growth_yoy: float | None = None
    revenue_cagr_3y: float | None = None
    eps_growth_yoy: float | None = None
    eps_cagr_3y: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    free_cash_flow: float | None = None
    roe: float | None = None
    roic: float | None = None
    cash: float | None = None
    debt: float | None = None
    debt_to_equity: float | None = None


class PriceOpportunity(BaseModel):
    current_price: float | None = None
    change_1d: float | None = None
    change_1w: float | None = None
    change_1m: float | None = None
    change_3m: float | None = None
    change_6m: float | None = None
    change_1y: float | None = None
    change_2y: float | None = None
    change_5y: float | None = None
    distance_from_ath: float | None = None
    distance_from_52w_high: float | None = None
    distance_from_52w_low: float | None = None


class Valuation(BaseModel):
    pe: float | None = None
    forward_pe: float | None = None
    peg: float | None = None
    price_to_sales: float | None = None
    ev_to_ebitda: float | None = None
    fcf_yield: float | None = None


class EntryStockSnapshot(BaseModel):
    date: str
    ticker: str
    name: str | None = None
    exchange: str | None = None
    country: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    avg_volume: float | None = None
    business_health: BusinessHealth = Field(default_factory=BusinessHealth)
    price_opportunity: PriceOpportunity = Field(default_factory=PriceOpportunity)
    valuation: Valuation = Field(default_factory=Valuation)


class EntrySnapshotFile(BaseModel):
    date: str
    source: str = "fmp"
    generated_at: datetime = Field(default_factory=utc_now)
    count: int = 0
    failed_tickers: list[str] = Field(default_factory=list)
    stocks: list[EntryStockSnapshot] = Field(default_factory=list)


class EntrySnapshotRequest(BaseModel):
    limit: int = Field(default=2000, ge=1, le=5000)

