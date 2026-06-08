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
    severity: float = Field(ge=0, le=1)
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


def _finite(value: float | None) -> float | None:
    return value if isinstance(value, (int, float)) and value == value else None


def _metric(snapshot: OpenDataSnapshot, group: str, key: str) -> float | None:
    metric = getattr(snapshot, group, {}).get(key)
    return _finite(metric.value) if metric else None


def _flat_metric(snapshot: OpenDataSnapshot, key: str) -> float | None:
    metric = snapshot.metrics.get(key)
    return _finite(metric.value) if metric else None


def _historical_values(snapshot: OpenDataSnapshot, series: str, metric_name: str) -> list[float]:
    rows = sorted(
        snapshot.historical_series.get(series, []),
        key=lambda row: row.period,
    )
    values: list[float] = []
    for row in rows:
        metric = row.metrics.get(metric_name)
        value = _finite(metric.value) if metric else None
        if value is not None:
            values.append(value)
    return values


def _historical_delta(snapshot: OpenDataSnapshot, series: str, metric_name: str, periods_back: int) -> float | None:
    values = _historical_values(snapshot, series, metric_name)
    if len(values) <= periods_back:
        return None
    return values[-1] - values[-1 - periods_back]


def _historical_percent_change(
    snapshot: OpenDataSnapshot,
    series: str,
    metric_name: str,
    periods_back: int,
) -> float | None:
    values = _historical_values(snapshot, series, metric_name)
    if len(values) <= periods_back or values[-1 - periods_back] == 0:
        return None
    return ((values[-1] / values[-1 - periods_back]) - 1) * 100


def _median(values: list[float]) -> float | None:
    clean = sorted(value for value in values if value == value)
    if not clean:
        return None
    middle = len(clean) // 2
    return clean[middle] if len(clean) % 2 else (clean[middle - 1] + clean[middle]) / 2


def _percentile_of_value(values: list[float], value: float | None) -> float | None:
    clean = [item for item in values if item == item]
    if value is None or len(clean) < 2:
        return None
    lower_or_equal = sum(1 for item in clean if item <= value)
    return (lower_or_equal / len(clean)) * 100


def _pct_change_from_median(
    snapshot: OpenDataSnapshot,
    series: str,
    metric_name: str,
    current: float | None,
) -> float | None:
    middle = _median(_historical_values(snapshot, series, metric_name))
    if current is None or middle in (None, 0):
        return None
    return ((current / middle) - 1) * 100


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _peer_percentile(
    snapshots: list[OpenDataSnapshot],
    snapshot: OpenDataSnapshot,
    metric_value,
    *,
    higher_better: bool = True,
) -> float | None:
    same_sector = [
        item
        for item in snapshots
        if item.sector and snapshot.sector and item.sector == snapshot.sector
    ]
    peer_set = same_sector if len(same_sector) >= 3 else snapshots
    current = metric_value(snapshot)
    values = [value for item in peer_set if (value := metric_value(item)) is not None]
    if current is None or len(values) < 2:
        return None
    better_or_equal = sum(1 for value in values if value <= current) if higher_better else sum(1 for value in values if value >= current)
    return (better_or_equal / len(values)) * 100


def _signal(value: float | None, kind: DerivedMetricKind, notes: str) -> DerivedSignal:
    return DerivedSignal(value=value, kind=kind, notes=notes)


def _fmt_pct(value: float | None) -> str:
    return "unknown" if value is None else f"{value:.1f}%"


def _fmt_ratio(value: float | None) -> str:
    return "unknown" if value is None else f"{value:.2f}"


def _fmt_compact(value: float | None) -> str:
    if value is None:
        return "unknown"
    abs_value = abs(value)
    if abs_value >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"
    if abs_value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    return f"${value:,.0f}"


def _severity(value: float, scale: float) -> float:
    return max(0.0, min(abs(value) / scale, 1.0))


def _interesting_facts(snapshot: OpenDataSnapshot, metrics: dict[str, DerivedSignal]) -> list[InterestingFact]:
    facts: list[InterestingFact] = []
    name = snapshot.name or snapshot.ticker

    pe_vs_median = metrics["pe_vs_median"].value
    if pe_vs_median is not None and abs(pe_vs_median) >= 20:
        direction = "below" if pe_vs_median < 0 else "above"
        facts.append(
            InterestingFact(
                type="valuation_vs_history",
                severity=_severity(pe_vs_median, 60),
                text=f"{name} PE is {_fmt_pct(abs(pe_vs_median))} {direction} its available historical median.",
                evidence=["valuation.pe", "valuation_history.pe"],
            )
        )

    fcfy_hist = metrics["fcfy_hist_percentile"].value
    if fcfy_hist is not None and (fcfy_hist >= 80 or fcfy_hist <= 20):
        label = "high" if fcfy_hist >= 80 else "low"
        facts.append(
            InterestingFact(
                type="fcf_yield_percentile",
                severity=_severity(fcfy_hist - 50, 50),
                text=f"FCF yield is in a {label} historical percentile at {_fmt_pct(fcfy_hist)}.",
                evidence=["valuation.fcf_yield", "valuation_history.fcf_yield"],
            )
        )

    rev_accel = metrics["rev_accel"].value
    if rev_accel is not None and abs(rev_accel) >= 5:
        label = "accelerating" if rev_accel > 0 else "decelerating"
        facts.append(
            InterestingFact(
                type="revenue_acceleration",
                severity=_severity(rev_accel, 25),
                text=f"Revenue growth is {label}: YoY growth differs from 3-year CAGR by {_fmt_pct(rev_accel)}.",
                evidence=["business_health.revenue_growth_yoy", "business_health.revenue_cagr_3y"],
            )
        )

    eps_accel = metrics["eps_accel"].value
    if eps_accel is not None and abs(eps_accel) >= 10:
        label = "accelerating" if eps_accel > 0 else "decelerating"
        facts.append(
            InterestingFact(
                type="eps_acceleration",
                severity=_severity(eps_accel, 50),
                text=f"EPS growth is {label}: YoY growth differs from 3-year CAGR by {_fmt_pct(eps_accel)}.",
                evidence=["business_health.eps_growth_yoy", "business_health.eps_cagr_3y"],
            )
        )

    op_delta = metrics["op_margin_yoy_delta"].value
    if op_delta is not None and abs(op_delta) >= 2:
        direction = "expanded" if op_delta > 0 else "compressed"
        facts.append(
            InterestingFact(
                type="operating_margin_change",
                severity=_severity(op_delta, 8),
                text=f"Annual operating margin {direction} by {_fmt_pct(abs(op_delta))} year over year.",
                evidence=["historical_series.annual_fundamentals.operating_margin"],
            )
        )

    fcf_conversion = metrics["fcf_conversion"].value
    if fcf_conversion is not None and (fcf_conversion >= 110 or fcf_conversion <= 60):
        label = "strong" if fcf_conversion >= 110 else "weak"
        facts.append(
            InterestingFact(
                type="fcf_conversion",
                severity=_severity(fcf_conversion - 100, 100),
                text=f"FCF conversion looks {label}: FCF is {_fmt_pct(fcf_conversion)} of TTM net income.",
                evidence=["business_health.free_cash_flow", "metrics.net_income_ttm"],
            )
        )

    shares_change = metrics["shares_3y_change"].value
    if shares_change is not None and abs(shares_change) >= 3:
        label = "buybacks" if shares_change < 0 else "dilution"
        facts.append(
            InterestingFact(
                type="share_count_change",
                severity=_severity(shares_change, 15),
                text=f"Three-year diluted share count change suggests {label}: {_fmt_pct(shares_change)}.",
                evidence=["historical_series.annual_fundamentals.shares_diluted"],
            )
        )

    sector_rev = metrics["sector_rev_rank"].value
    if sector_rev is not None and (sector_rev >= 80 or sector_rev <= 20):
        label = "top" if sector_rev >= 80 else "bottom"
        facts.append(
            InterestingFact(
                type="sector_growth_rank",
                severity=_severity(sector_rev - 50, 50),
                text=f"Revenue CAGR ranks in the {label} peer percentile at {_fmt_pct(sector_rev)}.",
                evidence=["business_health.revenue_cagr_3y", "sector_peer_set"],
            )
        )

    cheap_rank = metrics["sector_pe_cheap_rank"].value
    if cheap_rank is not None and (cheap_rank >= 80 or cheap_rank <= 20):
        label = "cheap" if cheap_rank >= 80 else "expensive"
        facts.append(
            InterestingFact(
                type="sector_pe_rank",
                severity=_severity(cheap_rank - 50, 50),
                text=f"PE screens {label} versus peers: cheapness percentile is {_fmt_pct(cheap_rank)}.",
                evidence=["valuation.pe", "sector_peer_set"],
            )
        )

    price_fund_gap = metrics["price_fund_gap"].value
    if price_fund_gap is not None and abs(price_fund_gap) >= 20:
        label = "lags" if price_fund_gap < 0 else "runs ahead of"
        facts.append(
            InterestingFact(
                type="price_fundamental_gap",
                severity=_severity(price_fund_gap, 60),
                text=f"One-year price performance {label} revenue growth by {_fmt_pct(abs(price_fund_gap))}.",
                evidence=["price_opportunity.change_1y", "business_health.revenue_growth_yoy"],
            )
        )

    net_cash = metrics["net_cash"].value
    net_debt_to_fcf = metrics["net_debt_to_fcf"].value
    if net_cash is not None and net_cash > 0:
        facts.append(
            InterestingFact(
                type="balance_sheet_net_cash",
                severity=min(net_cash / 50_000_000_000, 1.0),
                text=f"Balance sheet is net cash by {_fmt_compact(net_cash)}.",
                evidence=["business_health.cash", "business_health.debt"],
            )
        )
    elif net_debt_to_fcf is not None and net_debt_to_fcf >= 3:
        facts.append(
            InterestingFact(
                type="balance_sheet_leverage",
                severity=min(net_debt_to_fcf / 6, 1.0),
                text=f"Net debt is {_fmt_ratio(net_debt_to_fcf)}x TTM FCF.",
                evidence=["business_health.cash", "business_health.debt", "business_health.free_cash_flow"],
            )
        )

    facts.sort(key=lambda fact: fact.severity, reverse=True)
    return facts[:8]


def build_stock_derived_signals(
    snapshot: OpenDataSnapshot,
    snapshots: list[OpenDataSnapshot],
) -> StockDerivedSignals:
    revenue_growth = _metric(snapshot, "business_health", "revenue_growth_yoy")
    revenue_cagr = _metric(snapshot, "business_health", "revenue_cagr_3y")
    eps_growth = _metric(snapshot, "business_health", "eps_growth_yoy")
    eps_cagr = _metric(snapshot, "business_health", "eps_cagr_3y")
    cash = _metric(snapshot, "business_health", "cash")
    debt = _metric(snapshot, "business_health", "debt")
    fcf = _metric(snapshot, "business_health", "free_cash_flow")
    pe = _metric(snapshot, "valuation", "pe")
    ps = _metric(snapshot, "valuation", "price_to_sales")
    fcf_yield = _metric(snapshot, "valuation", "fcf_yield")
    price_1y = _metric(snapshot, "price_opportunity", "change_1y")
    distance_ath = _metric(snapshot, "price_opportunity", "distance_from_ath")
    net_income = _flat_metric(snapshot, "net_income_ttm")

    pe_hist = _percentile_of_value(_historical_values(snapshot, "valuation_history", "pe"), pe)
    ps_hist = _percentile_of_value(_historical_values(snapshot, "valuation_history", "price_to_sales"), ps)
    fcfy_hist = _percentile_of_value(_historical_values(snapshot, "valuation_history", "fcf_yield"), fcf_yield)
    rev_accel = None if revenue_growth is None or revenue_cagr is None else revenue_growth - revenue_cagr
    eps_accel = None if eps_growth is None or eps_cagr is None else eps_growth - eps_cagr
    pe_vs_median = _pct_change_from_median(snapshot, "valuation_history", "pe", pe)
    price_fund_gap = None if price_1y is None or revenue_growth is None else price_1y - revenue_growth
    growth_plus_fcfy = None if revenue_cagr is None or fcf_yield is None else revenue_cagr + fcf_yield
    net_cash = None if cash is None or debt is None else cash - debt
    net_debt = None if cash is None or debt is None else debt - cash
    fcf_conversion = _ratio(fcf, net_income)

    unusual_inputs = [
        None if pe_hist is None else 100 - pe_hist,
        fcfy_hist,
        None if rev_accel is None else max(min(50 + rev_accel * 2, 100), 0),
        None if price_fund_gap is None else max(min(50 - price_fund_gap, 100), 0),
        None if distance_ath is None else max(min(abs(distance_ath) * 2, 100), 0),
    ]
    clean_unusual_inputs = [value for value in unusual_inputs if value is not None]
    unusual_score = (
        sum(clean_unusual_inputs) / len(clean_unusual_inputs)
        if clean_unusual_inputs
        else None
    )

    metrics = {
        "unusual_score": _signal(unusual_score, "ratio", "Composite unusualness score from valuation compression, FCF-yield percentile, growth acceleration, price/fundamental gap, and drawdown."),
        "pe_hist_percentile": _signal(pe_hist, "percent", "Current PE percentile against available annual valuation history. Higher means more expensive versus its own history."),
        "pe_vs_median": _signal(pe_vs_median, "percent", "Current PE premium or discount versus available annual valuation-history median."),
        "ps_hist_percentile": _signal(ps_hist, "percent", "Current price/sales percentile against available annual valuation history."),
        "fcfy_hist_percentile": _signal(fcfy_hist, "percent", "Current FCF yield percentile against available annual valuation history. Higher means more attractive cash-flow yield versus its own history."),
        "rev_accel": _signal(rev_accel, "percent", "Revenue growth YoY minus 3-year revenue CAGR."),
        "eps_accel": _signal(eps_accel, "percent", "EPS growth YoY minus 3-year EPS CAGR."),
        "op_margin_yoy_delta": _signal(_historical_delta(snapshot, "annual_fundamentals", "operating_margin", 1), "percent", "Latest annual operating margin minus prior-year annual operating margin."),
        "fcf_margin_3y_delta": _signal(_historical_delta(snapshot, "annual_fundamentals", "fcf_margin", 3), "percent", "Latest annual FCF margin minus annual FCF margin three periods earlier."),
        "fcf_conversion": _signal(None if fcf_conversion is None else fcf_conversion * 100, "percent", "TTM free cash flow divided by TTM net income."),
        "net_cash": _signal(net_cash, "compact", "Cash minus debt. Negative values indicate net debt."),
        "net_debt_to_fcf": _signal(_ratio(net_debt, fcf), "ratio", "Net debt divided by TTM free cash flow. Negative values indicate net cash."),
        "shares_3y_change": _signal(_historical_percent_change(snapshot, "annual_fundamentals", "shares_diluted", 3), "percent", "Latest annual diluted shares versus three annual periods earlier. Negative suggests buybacks; positive suggests dilution."),
        "pe_to_rev_cagr": _signal(_ratio(pe, revenue_cagr), "ratio", "Trailing PE divided by 3-year revenue CAGR percentage."),
        "growth_plus_fcfy": _signal(growth_plus_fcfy, "percent", "3-year revenue CAGR plus current FCF yield."),
        "sector_rev_rank": _signal(_peer_percentile(snapshots, snapshot, lambda item: _metric(item, "business_health", "revenue_cagr_3y")), "percent", "Revenue CAGR percentile within sector when enough peers exist, otherwise within the loaded universe."),
        "sector_roic_rank": _signal(_peer_percentile(snapshots, snapshot, lambda item: _metric(item, "business_health", "roic")), "percent", "ROIC percentile within sector when enough peers exist, otherwise within the loaded universe."),
        "sector_fcfy_rank": _signal(_peer_percentile(snapshots, snapshot, lambda item: _metric(item, "valuation", "fcf_yield")), "percent", "FCF-yield percentile within sector when enough peers exist, otherwise within the loaded universe."),
        "sector_pe_cheap_rank": _signal(_peer_percentile(snapshots, snapshot, lambda item: _metric(item, "valuation", "pe"), higher_better=False), "percent", "Cheapness percentile by PE within sector when enough peers exist, otherwise within the loaded universe. Higher means lower PE than more peers."),
        "price_fund_gap": _signal(price_fund_gap, "percent", "1-year price change minus latest revenue growth YoY. Negative values can flag price weakness despite business growth."),
    }

    return StockDerivedSignals(
        ticker=snapshot.ticker,
        name=snapshot.name,
        sector=snapshot.sector,
        industry=snapshot.industry,
        source_snapshot_generated_at=snapshot.generated_at,
        derived_metrics=metrics,
        interesting_facts=_interesting_facts(snapshot, metrics),
        data_gaps=snapshot.data_gaps,
    )


def build_stock_derived_signals_file(snapshots: list[OpenDataSnapshot]) -> StockDerivedSignalsFile:
    stocks = [build_stock_derived_signals(snapshot, snapshots) for snapshot in sorted(snapshots, key=lambda item: item.ticker)]
    return StockDerivedSignalsFile(count=len(stocks), stocks=stocks)
