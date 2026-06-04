from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


MetricTier = Literal[
    "exact_public_fact",
    "computed_from_public_facts",
    "proxy_estimate",
    "unavailable_open_free",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OpenDataMetric(BaseModel):
    value: float | None = None
    source: str
    tier: MetricTier
    as_of: str
    notes: str


class LatestPrice(BaseModel):
    ticker: str
    price: float
    currency: str = "USD"
    source: str
    as_of: str


class HistoricalPricePoint(BaseModel):
    date: str
    close: float
    volume: float | None = None
    source: str


class OpenDataPeriodMetrics(BaseModel):
    period: str
    as_of: str
    metrics: dict[str, OpenDataMetric] = Field(default_factory=dict)


class OpenDataFilingExhibit(BaseModel):
    document: str
    description: str | None = None
    type: str | None = None
    url: str | None = None


class OpenDataCompanyFiling(BaseModel):
    accession_number: str
    form: str
    filing_date: str
    report_date: str | None = None
    acceptance_datetime: str | None = None
    primary_document: str | None = None
    primary_document_description: str | None = None
    items: list[str] = Field(default_factory=list)
    exhibits: list[OpenDataFilingExhibit] = Field(default_factory=list)
    source_url: str | None = None
    notes: str = ""


class OpenDataCompanyContext(BaseModel):
    source: str = "sec_submissions"
    as_of: str
    recent_filings: list[OpenDataCompanyFiling] = Field(default_factory=list)
    known_context_gaps: list[str] = Field(default_factory=list)
    notes: str = ""


class OpenDataSnapshot(BaseModel):
    ticker: str
    name: str | None = None
    cik: int | None = None
    exchange: str | None = None
    country: str | None = None
    sector: str | None = None
    industry: str | None = None
    source: str = "open_free_public"
    generated_at: datetime = Field(default_factory=utc_now)
    business_health: dict[str, OpenDataMetric] = Field(default_factory=dict)
    price_opportunity: dict[str, OpenDataMetric] = Field(default_factory=dict)
    valuation: dict[str, OpenDataMetric] = Field(default_factory=dict)
    historical_series: dict[str, list[OpenDataPeriodMetrics]] = Field(default_factory=dict)
    company_context: OpenDataCompanyContext | None = None
    data_gaps: list[str] = Field(default_factory=list)
    metrics: dict[str, OpenDataMetric] = Field(default_factory=dict)
