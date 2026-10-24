"""Derived stock signals that surface numerically unusual facts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.entry_engine.open_data_models import OpenDataSnapshot


DerivedMetricKind = Literal["percent", "pp", "ratio", "compact", "count"]


class DerivedSignal(BaseModel):
    value: float | int | None = None
    kind: DerivedMetricKind
    notes: str
    coverage: dict | None = None
    flags: list[dict] = Field(default_factory=list)
    observed_count: int | None = None


class InterestingFact(BaseModel):
    type: str
    severity: float | None = Field(default=None, ge=0, le=1)
    text: str
    evidence: list[str] = Field(default_factory=list)


class StockDerivedSignals(BaseModel):
    ticker: str
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_snapshot_generated_at: datetime | None = None
    derived_metrics: dict[str, DerivedSignal] = Field(default_factory=dict)
    interesting_facts: list[InterestingFact] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)


class StockDerivedSignalsFile(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "open_data_derived_signals"
    count: int
    stocks: list[StockDerivedSignals]


def build_stock_derived_signals(snapshot: OpenDataSnapshot, snapshots: list[OpenDataSnapshot]) -> StockDerivedSignals:
    """Expose reproducible research context without composite investment scores."""
    from app.services.screening_metrics import build_screening_metrics
    screening = build_screening_metrics(snapshot.model_dump(mode="json"))
    metrics = screening["metrics"]
    derived = {
        key: DerivedSignal(value=metrics[key]['value'], kind='pp' if key in {'momentum', 'operating_margin_trend'} else 'percent', notes=metrics[key]['formula'])
        for key in ('revenue', 'momentum', 'operating_margin', 'operating_margin_trend')
    }
    flags = metrics['red_flag_count']
    derived['red_flag_count'] = DerivedSignal(value=flags['value'], kind='count', notes=flags['notes'],
        coverage=flags['coverage'], flags=flags['flags'], observed_count=flags['observed_count'])
    return StockDerivedSignals(
        ticker=snapshot.ticker, name=snapshot.name, sector=snapshot.sector, industry=snapshot.industry,
        source_snapshot_generated_at=snapshot.generated_at, derived_metrics=derived,
        interesting_facts=[],
        data_gaps=snapshot.data_gaps,
    )


def build_stock_derived_signals_file(snapshots: list[OpenDataSnapshot]) -> StockDerivedSignalsFile:
    stocks = [build_stock_derived_signals(snapshot, snapshots) for snapshot in sorted(snapshots, key=lambda item: item.ticker)]
    return StockDerivedSignalsFile(count=len(stocks), stocks=stocks)
