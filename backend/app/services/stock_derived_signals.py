"""Derived stock signals that surface numerically unusual facts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.entry_engine.open_data_models import OpenDataSnapshot


DerivedMetricKind = Literal["percent", "ratio", "compact"]


class DerivedSignal(BaseModel):
    value: float | None = None
    kind: DerivedMetricKind
    notes: str


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
        "rev_accel": DerivedSignal(value=metrics["momentum"]["value"], kind="percent", notes="Revenue growth momentum: median(latest three quarterly YoY rates) minus median(preceding three), in percentage points."),
        "op_margin_yoy_delta": DerivedSignal(value=metrics["operating_margin"].get("yoy_change_pp"), kind="percent", notes="Latest-quarter operating margin minus the same fiscal quarter last year, in percentage points."),
        "net_cash": DerivedSignal(value=metrics["balance_sheet"]["value"], kind="compact", notes="Compatible unrestricted cash equivalents minus complete debt; investments excluded. Unknown when scope is incomplete."),
    }
    warnings = list(screening["warnings"])
    for metric in metrics.values():
        warnings.extend(metric["warnings"])
    return StockDerivedSignals(
        ticker=snapshot.ticker, name=snapshot.name, sector=snapshot.sector, industry=snapshot.industry,
        source_snapshot_generated_at=snapshot.generated_at, derived_metrics=derived,
        interesting_facts=[InterestingFact(type="needs_review", text=warning) for warning in dict.fromkeys(warnings)],
        data_gaps=snapshot.data_gaps,
    )


def build_stock_derived_signals_file(snapshots: list[OpenDataSnapshot]) -> StockDerivedSignalsFile:
    stocks = [build_stock_derived_signals(snapshot, snapshots) for snapshot in sorted(snapshots, key=lambda item: item.ticker)]
    return StockDerivedSignalsFile(count=len(stocks), stocks=stocks)
