"""Recommendation engine for deterministic portfolio policy checks."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel

from app.models import PortfolioSnapshot


DEFAULT_ALLOCATION_RULES = {
    "cash_reserve": {
        "target_percent": 20,
        "warning_low_percent": 10,
        "warning_high_percent": 40,
    },
    "invested_ratio": {
        "target_percent": 80,
        "overinvested_threshold": 90,
        "underinvested_threshold": 60,
    },
    "concentration": {
        "max_single_position_percent": 25,
        "warn_single_position_percent": 15,
    },
    "diversification": {
        "min_asset_classes": 2,
    },
    "platform_risk": {
        "max_single_platform_percent": 60,
    },
    "swing_trading": {
        "warn_many_open_orders": 10,
    },
    "stale_data": {
        "warn_hours": 48,
    },
}


class Recommendation(BaseModel):
    severity: Literal["info", "warning", "critical"]
    title: str
    detail: str


def _pct(part: float, whole: float) -> float:
    return round(part / whole * 100, 1) if whole else 0.0


def _hours_since(dt: datetime | None) -> float | None:
    if dt is None:
        return None
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).total_seconds() / 3600


def evaluate(snapshot: PortfolioSnapshot) -> list[Recommendation]:
    rules = DEFAULT_ALLOCATION_RULES
    recs: list[Recommendation] = []
    nw = snapshot.total_net_worth
    cash = snapshot.total_cash
    invested = snapshot.total_invested

    if nw <= 0:
        return recs

    # ── Cash Reserve ──
    cr = rules.get("cash_reserve", {})
    cash_pct = _pct(cash, nw)
    target = cr.get("target_percent", 20)
    low = cr.get("warning_low_percent", 10)
    high = cr.get("warning_high_percent", 40)

    if cash_pct < low:
        recs.append(Recommendation(
            severity="critical",
            title="Cash reserve critically low",
            detail=f"Cash is {cash_pct}% of net worth (target {target}%). Consider trimming positions to rebuild reserves.",
        ))
    elif cash_pct < target:
        recs.append(Recommendation(
            severity="warning",
            title="Cash below target",
            detail=f"Cash is {cash_pct}% of net worth (target {target}%). Building a buffer improves flexibility for swing trades.",
        ))
    elif cash_pct > high:
        recs.append(Recommendation(
            severity="warning",
            title="Excess idle cash",
            detail=f"Cash is {cash_pct}% of net worth. Consider deploying some into diversified positions or short-term opportunities.",
        ))
    else:
        recs.append(Recommendation(
            severity="info",
            title="Cash reserve healthy",
            detail=f"Cash is {cash_pct}% of net worth — within the {low}–{high}% comfort zone.",
        ))

    # ── Invested Ratio ──
    ir = rules.get("invested_ratio", {})
    inv_pct = _pct(invested, nw)
    over_thresh = ir.get("overinvested_threshold", 90)
    under_thresh = ir.get("underinvested_threshold", 60)

    if inv_pct >= over_thresh:
        recs.append(Recommendation(
            severity="warning",
            title="Over-invested",
            detail=f"{inv_pct}% of net worth is deployed. This leaves little room for new opportunities or drawdowns.",
        ))
    elif inv_pct <= under_thresh:
        recs.append(Recommendation(
            severity="warning",
            title="Under-invested",
            detail=f"Only {inv_pct}% deployed. Capital sitting idle loses to inflation — look for quality entries.",
        ))
    else:
        recs.append(Recommendation(
            severity="info",
            title="Investment ratio balanced",
            detail=f"{inv_pct}% of net worth is invested — within target range.",
        ))

    # ── Single-Position Concentration ──
    conc = rules.get("concentration", {})
    hard_cap = conc.get("max_single_position_percent", 25)
    soft_warn = conc.get("warn_single_position_percent", 15)

    for h in snapshot.holdings:
        val = h.value_in_base if h.value_in_base is not None else 0
        pos_pct = _pct(val, nw)
        if pos_pct >= hard_cap:
            recs.append(Recommendation(
                severity="critical",
                title=f"{h.symbol} is {pos_pct}% of portfolio",
                detail=f"Single position exceeds {hard_cap}% cap. Consider trimming to reduce concentration risk.",
            ))
        elif pos_pct >= soft_warn:
            recs.append(Recommendation(
                severity="warning",
                title=f"{h.symbol} concentration at {pos_pct}%",
                detail=f"Position is approaching the {hard_cap}% hard cap. Monitor closely.",
            ))

    # ── Asset-Class Diversification ──
    div_rules = rules.get("diversification", {})
    min_classes = div_rules.get("min_asset_classes", 2)
    classes = {h.asset_class for h in snapshot.holdings}
    if len(classes) < min_classes:
        recs.append(Recommendation(
            severity="warning",
            title="Low asset-class diversity",
            detail=f"Positions span only {len(classes)} class(es) ({', '.join(sorted(classes)) or 'none'}). Diversifying reduces overall risk.",
        ))

    # ── Platform Concentration ──
    plat = rules.get("platform_risk", {})
    max_plat_pct = plat.get("max_single_platform_percent", 60)
    for item in snapshot.platform_breakdown:
        if item.percent > max_plat_pct:
            recs.append(Recommendation(
                severity="warning",
                title=f"{item.name} holds {round(item.percent)}% of value",
                detail=f"Platform concentration exceeds {max_plat_pct}%. Spreading across platforms mitigates custodial risk.",
            ))

    # ── Swing / Open Orders ──
    sw = rules.get("swing_trading", {})
    warn_many = sw.get("warn_many_open_orders", 10)
    open_count = len(snapshot.open_orders)
    if open_count >= warn_many:
        recs.append(Recommendation(
            severity="warning",
            title=f"{open_count} open orders",
            detail=f"Having many open orders increases execution risk. Review and cancel stale ones.",
        ))

    # ── Stale Valuations ──
    stale = rules.get("stale_data", {})
    stale_hours = stale.get("warn_hours", 48)
    stale_symbols: list[str] = []
    for h in snapshot.holdings:
        age = _hours_since(h.valuation_timestamp)
        if age is not None and age > stale_hours:
            stale_symbols.append(h.symbol)
    if stale_symbols:
        recs.append(Recommendation(
            severity="warning",
            title=f"{len(stale_symbols)} stale valuation(s)",
            detail=f"Prices older than {stale_hours}h for: {', '.join(stale_symbols[:5])}{'…' if len(stale_symbols) > 5 else ''}. Refresh market data.",
        ))

    return recs
