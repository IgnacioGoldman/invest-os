"""Evidence-bound stock entry analysis for collected open-data facts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.entry_engine.open_data_models import OpenDataMetric, OpenDataSnapshot
from app.entry_engine.utils.file_storage import (
    load_latest_open_data_stock_snapshot,
    load_latest_open_data_stock_snapshots,
)
from app.services.stock_derived_signals import StockDerivedSignals, build_stock_derived_signals, build_stock_derived_signals_file


OpportunityType = Literal[
    "Temporary selloff",
    "Quality compounder pullback",
    "Valuation reset",
    "Momentum continuation",
    "Falling knife risk",
    "Insufficient data",
]


class StockEntryAnalysisSection(BaseModel):
    assessment: str
    evidence: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)


class StockEntryDcaPlan(BaseModel):
    buy_now: int = 0
    buy_dip_1: int = 0
    buy_dip_2: int = 0


class StockEntryAnalysis(BaseModel):
    ticker: str
    name: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_snapshot_generated_at: datetime | None = None
    needs_more_data: bool
    conviction: float
    summary: str
    opportunity_type: OpportunityType
    business_health: StockEntryAnalysisSection
    price_opportunity: StockEntryAnalysisSection
    valuation: StockEntryAnalysisSection
    company_context: StockEntryAnalysisSection
    missing_data: list[str] = Field(default_factory=list)
    dca_entry: StockEntryDcaPlan


def _metric(snapshot: OpenDataSnapshot, group: str, key: str) -> OpenDataMetric | None:
    value = getattr(snapshot, group, {}).get(key)
    return value if isinstance(value, OpenDataMetric) else None


def _value(snapshot: OpenDataSnapshot, group: str, key: str) -> float | None:
    metric = _metric(snapshot, group, key)
    return metric.value if metric else None


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:.2f}%"


def _fmt_money(value: float | None) -> str:
    if value is None:
        return "unknown"
    abs_value = abs(value)
    if abs_value >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"
    if abs_value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    return f"${value:,.2f}"


def _fmt_ratio(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:.2f}"


def _fmt_abs_pct(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{abs(value):.2f}%"


def _price_move_sentence(label: str, value: float | None) -> str:
    if value is None:
        return f"Price move over {label} is unknown."
    if value > 0:
        return f"Price is up {_fmt_pct(value)} over {label}."
    if value < 0:
        return f"Price is down {_fmt_abs_pct(value)} over {label}."
    return f"Price is flat over {label}."


def _distance_from_high_sentence(distance_ath: float | None) -> str:
    if distance_ath is None:
        return "Distance from the all-time high / 52-week high is unknown."
    if distance_ath >= -1:
        return "Price is at or near the all-time high / 52-week high."
    return f"Price is {_fmt_abs_pct(distance_ath)} below the all-time high / 52-week high."


def _absolute_valuation_flags(
    pe: float | None,
    forward_pe: OpenDataMetric | None,
    price_to_sales: float | None,
    ev_to_ebitda: OpenDataMetric | None,
    fcf_yield: float | None,
) -> list[str]:
    flags: list[str] = []
    if pe is not None and pe >= 40:
        flags.append(f"Trailing PE is high on an absolute basis at {_fmt_ratio(pe)}.")
    if forward_pe is not None and forward_pe.value is not None and forward_pe.value >= 30:
        flags.append(f"Forward PE is high on an absolute basis at {_fmt_ratio(forward_pe.value)}.")
    if price_to_sales is not None and price_to_sales >= 10:
        flags.append(f"Price/sales is high on an absolute basis at {_fmt_ratio(price_to_sales)}.")
    if ev_to_ebitda is not None and ev_to_ebitda.value is not None and ev_to_ebitda.value >= 25:
        flags.append(f"EV/EBITDA is high on an absolute basis at {_fmt_ratio(ev_to_ebitda.value)}.")
    if fcf_yield is not None and fcf_yield <= 2:
        flags.append(f"FCF yield is low on an absolute basis at {_fmt_pct(fcf_yield)}.")
    return flags


def _business_assessment(
    business_data_available: bool,
    revenue_yoy: float | None,
    eps_yoy: float | None,
    operating_margin: float | None,
    roe: float | None,
) -> str:
    if not business_data_available:
        return "unclear"
    if (
        (revenue_yoy or 0) >= 8
        and (eps_yoy or 0) >= 10
        and (operating_margin or 0) >= 20
        and (roe or 0) >= 20
    ):
        return "strong"
    weak_signals = sum(
        (
            (revenue_yoy or 0) < 0,
            (eps_yoy or 0) < 0,
            (operating_margin or 0) < 10,
            (roe or 0) < 5,
        )
    )
    if weak_signals >= 2 or (operating_margin or 0) < 5 or (roe or 0) < 0:
        return "weak"
    if (revenue_yoy or 0) >= 4 and (eps_yoy or 0) >= 0 and (operating_margin or 0) >= 15 and (roe or 0) >= 10:
        return "solid"
    return "mixed"


def _price_assessment(
    *,
    price_data_available: bool,
    has_short_pullback: bool,
    distance_ath: float | None,
    change_1m: float | None,
    change_3m: float | None,
    change_6m: float | None,
    change_1y: float | None,
    longer_trend_strong: bool,
    price_extended: bool,
) -> str:
    if not price_data_available:
        return "unclear"
    if price_extended:
        return "no_dip"
    if (distance_ath or 0) <= -30 and ((change_3m or 0) <= -15 or (change_6m or 0) <= -20 or (change_1y or 0) <= -30):
        return "falling"
    if has_short_pullback and longer_trend_strong:
        return "pullback"
    if longer_trend_strong:
        return "strong_trend"
    if (distance_ath or 0) <= -25:
        return "deep_pullback"
    if (distance_ath or 0) <= -8 or (change_1m or 0) <= -5:
        return "better_spot"
    return "no_dip"


def _valuation_assessment(
    *,
    needs_valuation_data: bool,
    pe: float | None,
    pe_median: float | None,
    price_to_sales: float | None,
    fcf_yield: float | None,
    valuation_expensive: bool,
    absolute_valuation_flags: list[str],
    valuation_history_reliable: bool,
) -> str:
    if needs_valuation_data:
        return "unclear"
    if len(absolute_valuation_flags) >= 3 or (pe is not None and pe >= 60) or (price_to_sales is not None and price_to_sales >= 15):
        return "very_pricey"
    if valuation_expensive:
        return "pricey"
    if (
        pe is not None
        and pe_median is not None
        and pe <= pe_median * 0.8
        and (fcf_yield is None or fcf_yield >= 4)
    ):
        if not valuation_history_reliable:
            return "fair"
        return "cheap"
    if pe is not None and pe_median is not None and pe > pe_median * 1.1 and valuation_history_reliable:
        return "slightly_expensive"
    return "fair"


def _valuation_comparison_sentence(
    label: str,
    value: float | None,
    median: float | None,
    max_value: float | None,
) -> str:
    if median is None and max_value is None:
        return f"{label} is {_fmt_ratio(value)}; historical range is unavailable from open data."
    return (
        f"{label} is {_fmt_ratio(value)} versus available annual-row median of {_fmt_ratio(median)} "
        f"and max of {_fmt_ratio(max_value)}."
    )


def _valuation_range(snapshot: OpenDataSnapshot, key: str) -> float | None:
    rows = snapshot.historical_series.get("valuation_ranges", [])
    if not rows:
        return None
    metric = rows[0].metrics.get(key)
    return metric.value if metric else None


def _historical_valuation_values(snapshot: OpenDataSnapshot, key: str) -> list[float]:
    values: list[float] = []
    for row in snapshot.historical_series.get("valuation_history", []):
        metric = row.metrics.get(key)
        if metric and metric.value is not None and metric.value > 0:
            values.append(metric.value)
    return values


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    midpoint = len(sorted_values) // 2
    if len(sorted_values) % 2:
        return sorted_values[midpoint]
    return (sorted_values[midpoint - 1] + sorted_values[midpoint]) / 2


def _has_historical_bridge_gap(snapshot: OpenDataSnapshot) -> bool:
    gap_text = " ".join(snapshot.data_gaps).lower()
    return (
        "historical fx" in gap_text
        or "historical valuation" in gap_text
        or ("ifrs" in gap_text and "historical" in gap_text)
    )


def _valuation_history_quality(snapshot: OpenDataSnapshot) -> tuple[bool, list[str]]:
    pe_values = _historical_valuation_values(snapshot, "pe")
    reasons: list[str] = []

    if len(pe_values) < 4:
        reasons.append("fewer than four usable annual PE history points")

    pe_median = _median(pe_values)
    if pe_values and pe_median and max(pe_values) >= pe_median * 8:
        reasons.append("PE history contains a severe outlier")

    if _has_historical_bridge_gap(snapshot):
        reasons.append("historical valuation bridge has IFRS/FX/ADR limitations")

    return not reasons, reasons


def _annual_metric_values(snapshot: OpenDataSnapshot, key: str) -> list[float]:
    rows = snapshot.historical_series.get("annual_fundamentals", [])
    values: list[float] = []
    for row in rows:
        metric = row.metrics.get(key)
        if metric and metric.value is not None:
            values.append(metric.value)
    return values


def _company_context(snapshot: OpenDataSnapshot) -> StockEntryAnalysisSection:
    context = snapshot.company_context
    if context is None or not context.recent_filings:
        return StockEntryAnalysisSection(
            assessment="no_recent_sec_context",
            evidence=[],
            concerns=["No recent SEC filing metadata is supplied."],
        )

    evidence: list[str] = []
    concerns: list[str] = []
    latest_10q = next((filing for filing in context.recent_filings if filing.form == "10-Q"), None)
    if latest_10q:
        report = f" for report date {latest_10q.report_date}" if latest_10q.report_date else ""
        evidence.append(f"Recent 10-Q filed {latest_10q.filing_date}{report}.")

    earnings_8k = next(
        (
            filing
            for filing in context.recent_filings
            if filing.form == "8-K"
            and "2.02" in filing.items
            and "9.01" in filing.items
            and any(exhibit.type == "EX-99.1" for exhibit in filing.exhibits)
        ),
        None,
    )
    if earnings_8k:
        evidence.append(
            f"Recent 8-K filed {earnings_8k.filing_date} includes Items 2.02 and 9.01 with EX-99.1, "
            "indicating an earnings-related filing exists."
        )

    item_502_count = sum(1 for filing in context.recent_filings if "5.02" in filing.items)
    if item_502_count:
        evidence.append(
            f"{item_502_count} recent 8-K filing(s) include Item 5.02, indicating officer/director or compensation-related filing context."
        )

    if earnings_8k:
        concerns.append(
            "EX-99.1 text is not supplied, so guidance or earnings-release content should not be inferred."
        )
    concerns.append(
        "SEC filing metadata alone does not establish whether a price move was caused by guidance, regulation, management tone, or market overreaction."
    )

    return StockEntryAnalysisSection(
        assessment="recent_sec_context_available_but_not_interpretable_for_sentiment",
        evidence=evidence,
        concerns=concerns,
    )


def _derived_value(signals: StockDerivedSignals | None, key: str) -> float | None:
    if signals is None:
        return None
    signal = signals.derived_metrics.get(key)
    return signal.value if signal else None


def _derived_signal_adjustment(signals: StockDerivedSignals | None, *, valuation_history_reliable: bool) -> float:
    if signals is None:
        return 0.0

    adjustment = 0.0
    unusual_score = _derived_value(signals, "unusual_score")
    pe_vs_median = _derived_value(signals, "pe_vs_median")
    fcfy_hist = _derived_value(signals, "fcfy_hist_percentile")
    sector_fcfy = _derived_value(signals, "sector_fcfy_rank")
    sector_cheap = _derived_value(signals, "sector_pe_cheap_rank")
    price_fund_gap = _derived_value(signals, "price_fund_gap")
    net_cash = _derived_value(signals, "net_cash")
    net_debt_to_fcf = _derived_value(signals, "net_debt_to_fcf")
    fcf_conversion = _derived_value(signals, "fcf_conversion")
    growth_plus_fcfy = _derived_value(signals, "growth_plus_fcfy")
    sector_rev = _derived_value(signals, "sector_rev_rank")
    op_margin_delta = _derived_value(signals, "op_margin_yoy_delta")
    shares_change = _derived_value(signals, "shares_3y_change")

    if unusual_score is not None:
        if unusual_score >= 85:
            adjustment += 0.35
        elif unusual_score >= 70:
            adjustment += 0.2
        elif unusual_score <= 25:
            adjustment -= 0.15

    if pe_vs_median is not None and valuation_history_reliable:
        if pe_vs_median <= -35:
            adjustment += 0.3
        elif pe_vs_median <= -20:
            adjustment += 0.2
        elif pe_vs_median >= 30:
            adjustment -= 0.25

    if fcfy_hist is not None and valuation_history_reliable:
        if fcfy_hist >= 85:
            adjustment += 0.25
        elif fcfy_hist <= 20:
            adjustment -= 0.15

    if sector_cheap is not None:
        if sector_cheap >= 80:
            adjustment += 0.15
        elif sector_cheap <= 20:
            adjustment -= 0.15

    if sector_fcfy is not None and sector_fcfy >= 80:
        adjustment += 0.1

    if price_fund_gap is not None:
        if price_fund_gap <= -35:
            adjustment += 0.2
        elif price_fund_gap <= -20:
            adjustment += 0.1
        elif price_fund_gap >= 35:
            adjustment -= 0.15

    if net_cash is not None and net_cash > 0:
        adjustment += 0.1
    if net_debt_to_fcf is not None and net_debt_to_fcf >= 3:
        adjustment -= 0.25

    if fcf_conversion is not None:
        if fcf_conversion >= 130:
            adjustment += 0.15
        elif fcf_conversion <= 60:
            adjustment -= 0.2

    if growth_plus_fcfy is not None:
        if growth_plus_fcfy >= 14:
            adjustment += 0.1
        elif growth_plus_fcfy <= 4:
            adjustment -= 0.1

    if sector_rev is not None and sector_rev <= 20:
        adjustment -= 0.2
    if op_margin_delta is not None and op_margin_delta <= -3:
        adjustment -= 0.15
    if shares_change is not None and shares_change >= 5:
        adjustment -= 0.2

    return max(-0.8, min(1.3, adjustment))


def _final_conviction(base: float, adjustment: float, *, needs_more_data: bool, price_assessment: str) -> float:
    conviction = base + adjustment
    if needs_more_data:
        conviction = min(conviction, 5.2)
    if price_assessment == "falling":
        conviction = min(conviction, 6.3)
    if price_assessment == "no_dip":
        conviction = min(conviction, 6.0)
    return round(max(0.0, min(10.0, conviction)), 1)


def _support_price_adjustment(
    *,
    support_at: bool,
    support_near: bool,
    needs_more_data: bool,
    business_assessment: str,
    price_assessment: str,
) -> float:
    if needs_more_data or business_assessment == "weak" or price_assessment == "falling":
        return 0.0
    if support_at:
        return 0.3
    if support_near:
        return 0.15
    return 0.0


def analyze_open_data_stock_entry(
    snapshot: OpenDataSnapshot,
    peer_snapshots: list[OpenDataSnapshot] | None = None,
    derived_signals: StockDerivedSignals | None = None,
) -> StockEntryAnalysis:
    revenue_yoy = _value(snapshot, "business_health", "revenue_growth_yoy")
    revenue_cagr = _value(snapshot, "business_health", "revenue_cagr_3y")
    eps_yoy = _value(snapshot, "business_health", "eps_growth_yoy")
    eps_cagr = _value(snapshot, "business_health", "eps_cagr_3y")
    gross_margin = _value(snapshot, "business_health", "gross_margin")
    operating_margin = _value(snapshot, "business_health", "operating_margin")
    net_margin = _value(snapshot, "business_health", "net_margin")
    fcf = _value(snapshot, "business_health", "free_cash_flow")
    roe = _value(snapshot, "business_health", "roe")
    roic = _metric(snapshot, "business_health", "roic")
    debt_to_equity = _value(snapshot, "business_health", "debt_to_equity")

    current_price = _value(snapshot, "price_opportunity", "current_price")
    change_1w = _value(snapshot, "price_opportunity", "change_1w")
    change_1m = _value(snapshot, "price_opportunity", "change_1m")
    change_3m = _value(snapshot, "price_opportunity", "change_3m")
    change_6m = _value(snapshot, "price_opportunity", "change_6m")
    change_1y = _value(snapshot, "price_opportunity", "change_1y")
    distance_ath = _value(snapshot, "price_opportunity", "distance_from_ath")
    distance_52w_low = _value(snapshot, "price_opportunity", "distance_from_52w_low")
    support_1d_distance = _value(snapshot, "price_opportunity", "support_1d_distance")

    pe = _value(snapshot, "valuation", "pe")
    forward_pe = _metric(snapshot, "valuation", "forward_pe")
    peg = _metric(snapshot, "valuation", "peg")
    price_to_sales = _value(snapshot, "valuation", "price_to_sales")
    ev_to_ebitda = _metric(snapshot, "valuation", "ev_to_ebitda")
    fcf_yield = _value(snapshot, "valuation", "fcf_yield")

    pe_median = _valuation_range(snapshot, "pe_median")
    pe_max = _valuation_range(snapshot, "pe_max")
    ps_max = _valuation_range(snapshot, "price_to_sales_max")
    ev_max = _valuation_range(snapshot, "ev_to_ebitda_max")
    fcf_yield_min = _valuation_range(snapshot, "fcf_yield_min")
    fcf_yield_max = _valuation_range(snapshot, "fcf_yield_max")

    business_evidence = [
        f"Revenue growth YoY is {_fmt_pct(revenue_yoy)} and 3-year revenue CAGR is {_fmt_pct(revenue_cagr)}.",
        f"Diluted EPS growth YoY is {_fmt_pct(eps_yoy)} and 3-year EPS CAGR is {_fmt_pct(eps_cagr)}.",
        f"Latest margins are gross {_fmt_pct(gross_margin)}, operating {_fmt_pct(operating_margin)}, net {_fmt_pct(net_margin)}.",
        f"TTM free cash flow is {_fmt_money(fcf)}; ROE is {_fmt_pct(roe)}; debt-to-equity is {_fmt_ratio(debt_to_equity)}.",
    ]
    business_concerns: list[str] = []
    if roic and roic.tier == "proxy_estimate":
        business_concerns.append("ROIC is a proxy estimate, not a fully tax-adjusted exact figure.")
    fcf_margins = _annual_metric_values(snapshot, "fcf_margin")
    if len(fcf_margins) >= 2 and fcf_margins[-1] < fcf_margins[0]:
        business_concerns.append(
            f"Annual FCF margin declined from {_fmt_pct(fcf_margins[0])} to {_fmt_pct(fcf_margins[-1])} across supplied annual history."
        )

    is_quality = (
        (revenue_yoy or 0) >= 8
        and (eps_yoy or 0) >= 10
        and (operating_margin or 0) >= 20
        and (roe or 0) >= 20
    )

    price_evidence = [
        f"Latest close is {_fmt_money(current_price)}.",
        f"{_price_move_sentence('1 week', change_1w)} {_price_move_sentence('1 month', change_1m)}",
        _distance_from_high_sentence(distance_ath),
        f"Longer-term trend: {_fmt_pct(change_3m)} over 3 months, {_fmt_pct(change_6m)} over 6 months, {_fmt_pct(change_1y)} over 1 year.",
    ]
    support_at = support_1d_distance is not None and support_1d_distance <= 2.5
    support_near = support_1d_distance is not None and support_1d_distance <= 6
    if support_1d_distance is not None:
        support_label = "at" if support_at else "near" if support_near else "above"
        price_evidence.append(f"Daily support signal: price is {support_label} the nearest repeated support zone at {_fmt_pct(support_1d_distance)} from zone midpoint.")
    price_concerns: list[str] = []
    if distance_ath is not None and distance_ath > -20:
        price_concerns.append("This is not a deep beaten-up setup based on supplied price facts.")
    if distance_52w_low is not None and distance_52w_low > 50:
        price_concerns.append(
            f"Price is still {_fmt_pct(distance_52w_low)} above the 52-week low, so the pullback may be shallow relative to the prior run."
        )

    price_data_available = (
        current_price is not None
        and change_1w is not None
        and change_1m is not None
        and change_3m is not None
        and change_6m is not None
        and change_1y is not None
        and distance_ath is not None
        and distance_52w_low is not None
    )
    has_short_pullback = price_data_available and (change_1m or 0) <= -5 and (distance_ath or 0) <= -8
    longer_trend_strong = (change_1y or 0) >= 25
    price_extended = price_data_available and distance_ath >= -3 and (change_1m or 0) > 5
    price_assessment = _price_assessment(
        price_data_available=price_data_available,
        has_short_pullback=has_short_pullback,
        distance_ath=distance_ath,
        change_1m=change_1m,
        change_3m=change_3m,
        change_6m=change_6m,
        change_1y=change_1y,
        longer_trend_strong=longer_trend_strong,
        price_extended=price_extended,
    )
    if support_at and price_assessment == "strong_trend":
        price_assessment = "pullback"
    elif support_at and price_assessment == "deep_pullback":
        price_assessment = "better_spot"
    elif support_near and price_assessment == "no_dip":
        price_assessment = "better_spot"
    price_no_clear_dip = price_data_available and not has_short_pullback and not support_near
    if price_assessment == "better_spot":
        price_concerns.append("The stock is meaningfully off its high, but the supplied trend is sideways or weak rather than a clean rising pullback.")
    if price_assessment == "deep_pullback":
        price_concerns.append("The pullback is real and deep, but the supplied longer-term price trend is weak rather than strongly rising.")
    if price_assessment == "falling":
        price_concerns.append("The drawdown is large and trend evidence is weak, so this may still be a falling setup.")

    valuation_evidence = [
        _valuation_comparison_sentence("Trailing PE", pe, pe_median, pe_max),
        _valuation_comparison_sentence("Price/sales", price_to_sales, None, ps_max),
        _valuation_comparison_sentence("EV/EBITDA proxy", ev_to_ebitda.value if ev_to_ebitda else None, None, ev_max),
    ]
    if forward_pe:
        valuation_evidence.append(
            f"Forward PE is {_fmt_ratio(forward_pe.value)}, but this is a {forward_pe.tier.replace('_', ' ')}."
        )

    valuation_concerns: list[str] = []
    if fcf_yield is not None and fcf_yield_min is not None and fcf_yield < fcf_yield_min:
        valuation_concerns.append(
            f"FCF yield is {_fmt_pct(fcf_yield)}, below the available annual-row range of {_fmt_pct(fcf_yield_min)} to {_fmt_pct(fcf_yield_max)}."
        )
    absolute_valuation_flags = _absolute_valuation_flags(pe, forward_pe, price_to_sales, ev_to_ebitda, fcf_yield)
    valuation_concerns.extend(absolute_valuation_flags)
    if peg and peg.tier == "proxy_estimate":
        valuation_concerns.append("PEG is a proxy based on public facts, not analyst-consensus PEG.")
    if ev_to_ebitda and ev_to_ebitda.tier == "proxy_estimate":
        valuation_concerns.append("EV/EBITDA is a proxy estimate from open/free public facts.")
    valuation_history_reliable, valuation_history_quality_reasons = _valuation_history_quality(snapshot)
    valuation_would_screen_cheap = (
        pe is not None
        and pe_median is not None
        and pe <= pe_median * 0.8
        and (fcf_yield is None or fcf_yield >= 4)
    )
    if valuation_would_screen_cheap and not valuation_history_reliable:
        valuation_concerns.append(
            "Valuation screens attractive, but the strongest cheap label is withheld because "
            + "; ".join(valuation_history_quality_reasons)
            + "."
        )

    valuation_expensive = any(
        (
            pe is not None and pe_median is not None and pe > pe_median,
            price_to_sales is not None and ps_max is not None and price_to_sales > ps_max,
            fcf_yield is not None and fcf_yield_min is not None and fcf_yield < fcf_yield_min,
            len(absolute_valuation_flags) >= 2,
        )
    )

    business_data_available = (
        revenue_yoy is not None
        and revenue_cagr is not None
        and gross_margin is not None
        and operating_margin is not None
        and net_margin is not None
        and fcf is not None
        and roe is not None
        and debt_to_equity is not None
    )
    needs_valuation_data = pe is None or price_to_sales is None
    needs_more_data = not business_data_available or needs_valuation_data or not price_data_available
    business_assessment = _business_assessment(business_data_available, revenue_yoy, eps_yoy, operating_margin, roe)
    valuation_assessment = _valuation_assessment(
        needs_valuation_data=needs_valuation_data,
        pe=pe,
        pe_median=pe_median,
        price_to_sales=price_to_sales,
        fcf_yield=fcf_yield,
        valuation_expensive=valuation_expensive,
        absolute_valuation_flags=absolute_valuation_flags,
        valuation_history_reliable=valuation_history_reliable,
    )
    missing_data: list[str] = []
    if needs_more_data:
        if needs_valuation_data:
            missing_data.append("Historical and current valuation facts before judging whether the entry price is attractive.")
        if not business_data_available:
            missing_data.append("Enough business-health facts to judge growth, margins, returns, cash generation, and balance-sheet quality.")
        if not price_data_available:
            missing_data.append("Enough price-history facts to judge whether the stock is actually offering a useful pullback.")

    if needs_more_data:
        opportunity_type: OpportunityType = "Insufficient data"
    elif (has_short_pullback or support_at) and is_quality:
        opportunity_type = "Quality compounder pullback"
    elif longer_trend_strong:
        opportunity_type = "Momentum continuation"
    else:
        opportunity_type = "Temporary selloff"

    base_conviction = 6.8
    if needs_more_data:
        base_conviction = 4.5
    elif not is_quality:
        base_conviction = 5.0
    elif price_extended and not support_near:
        base_conviction = 5.6
    elif valuation_expensive:
        base_conviction = 6.8
    elif is_quality and (has_short_pullback or support_at):
        base_conviction = 7.4
    elif is_quality and support_near:
        base_conviction = 7.0

    if derived_signals is None:
        derived_signals = build_stock_derived_signals(snapshot, peer_snapshots or [snapshot])
    derived_adjustment = _derived_signal_adjustment(
        derived_signals,
        valuation_history_reliable=valuation_history_reliable,
    )
    support_adjustment = _support_price_adjustment(
        support_at=support_at,
        support_near=support_near,
        needs_more_data=needs_more_data,
        business_assessment=business_assessment,
        price_assessment=price_assessment,
    )
    conviction = _final_conviction(
        base_conviction,
        derived_adjustment + support_adjustment,
        needs_more_data=needs_more_data,
        price_assessment=price_assessment,
    )

    summary = (
        f"{snapshot.name or snapshot.ticker} looks like a strong business with a real short-term pullback, "
        "but the stock is not broadly beaten up and valuation is elevated versus its own recent public-fact history."
        if is_quality and has_short_pullback and valuation_expensive
        else f"{snapshot.name or snapshot.ticker} has strong facts, but price is extended rather than offering a clear pullback."
        if is_quality and price_extended
        else f"{snapshot.name or snapshot.ticker} has strong facts, but this is trend-following rather than a clear dip."
        if is_quality and price_no_clear_dip
        else f"{snapshot.name or snapshot.ticker} has mixed business facts, so the setup is not clean enough for a high-conviction entry."
        if business_data_available
        else f"{snapshot.name or snapshot.ticker} has an entry setup that still depends on the supplied fact quality and missing context."
    )

    dca = StockEntryDcaPlan(
        buy_now=0 if needs_more_data or price_no_clear_dip else (30 if valuation_expensive else 40),
        buy_dip_1=0 if needs_more_data or price_no_clear_dip else (35 if valuation_expensive else 30),
        buy_dip_2=0 if needs_more_data or price_no_clear_dip else (35 if valuation_expensive else 30),
    )

    return StockEntryAnalysis(
        ticker=snapshot.ticker,
        name=snapshot.name,
        source_snapshot_generated_at=snapshot.generated_at,
        needs_more_data=needs_more_data,
        conviction=conviction,
        summary=summary,
        opportunity_type=opportunity_type,
        business_health=StockEntryAnalysisSection(
            assessment=business_assessment,
            evidence=business_evidence,
            concerns=business_concerns,
        ),
        price_opportunity=StockEntryAnalysisSection(
            assessment=price_assessment,
            evidence=price_evidence,
            concerns=price_concerns,
        ),
        valuation=StockEntryAnalysisSection(
            assessment=valuation_assessment,
            evidence=valuation_evidence,
            concerns=valuation_concerns,
        ),
        company_context=_company_context(snapshot),
        missing_data=missing_data,
        dca_entry=dca,
    )


def analyze_latest_open_data_stock_entry(ticker: str) -> StockEntryAnalysis | None:
    snapshot = load_latest_open_data_stock_snapshot(ticker)
    if snapshot is None:
        return None
    return analyze_open_data_stock_entry(snapshot, load_latest_open_data_stock_snapshots())


def analyze_latest_open_data_stock_entries() -> dict[str, StockEntryAnalysis]:
    snapshots = load_latest_open_data_stock_snapshots()
    if not snapshots:
        return {}
    derived_file = build_stock_derived_signals_file(snapshots)
    derived_by_ticker = {signals.ticker: signals for signals in derived_file.stocks}
    return {
        snapshot.ticker: analyze_open_data_stock_entry(
            snapshot,
            snapshots,
            derived_by_ticker.get(snapshot.ticker),
        )
        for snapshot in snapshots
    }
