"""Local stock-analysis brief for Codex and future AI endpoints."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.models import Holding, PortfolioSnapshot
from app.services.portfolio import build_snapshot


PROJECT_DIR = Path(__file__).resolve().parents[3]
SKILLS_DIR = PROJECT_DIR / "skills"
STOCK_SKILL_PATH = SKILLS_DIR / "analyze_stocks.md"

STOCK_ASSET_CLASSES = {"equity", "stock", "etf", "fund"}
STOCK_SOURCES = {"ibkr"}
WATCHLIST_PATH = PROJECT_DIR / "data" / "manual" / "watchlist.yaml"

DEFAULT_STOCK_RULES: dict[str, Any] = {
    "profit_review_percent": 20,
    "strong_gain_review_percent": 35,
    "loss_review_percent": -15,
    "max_single_stock_percent_of_net_worth": 15,
    "high_volatility_symbols": ["TSLA", "MSTR"],
    "high_volatility_profit_review_percent": 15,
    "default_trailing_stop_percent": 12,
    "tighter_trailing_stop_percent": 8,
    "avoid_buying_without_fresh_price": True,
}


class StockPositionBrief(BaseModel):
    symbol: str
    name: str | None = None
    source: str
    platform: str
    asset_class: str
    quantity: float
    currency: str
    current_price: float | None = None
    market_value: float
    value_in_base: float | None = None
    portfolio_weight_percent: float
    cost_basis: float | None = None
    unrealized_pnl: float | None = None
    unrealized_pnl_percent: float | None = None
    action_bias: Literal["hold", "review", "trim_review", "exit_candidate"]
    flags: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    exit_framework: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"]


class WatchlistOpportunityBrief(BaseModel):
    symbol: str
    name: str | None = None
    asset_class: str = "equity"
    currency: str = "USD"
    sector: str | None = None
    vertical: str | None = None
    geography: str | None = None
    thesis: str | None = None
    why_interesting: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    preferred_entry: str | None = None
    max_position_percent_of_net_worth: float | None = None
    action_bias: Literal["research", "watchlist", "staged_entry_candidate"] = "research"
    evidence: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "low"


class StockAnalysisBrief(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    base_currency: str
    net_worth: float
    stock_value: float
    stock_weight_percent: float
    cash_value: float
    cash_weight_percent: float
    positions: list[StockPositionBrief]
    opportunities: list[WatchlistOpportunityBrief]
    missing_data: list[str] = Field(default_factory=list)
    local_codex_instruction: str


def _load_yaml(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with open(path) as fh:
        return yaml.safe_load(fh) or default


def _pct(part: float | None, whole: float | None) -> float:
    if part is None or whole is None or whole == 0:
        return 0.0
    return round(part / whole * 100, 2)


def _is_stock_holding(holding: Holding) -> bool:
    if holding.asset_class.lower() == "rsu":
        return False
    return holding.asset_class.lower() in STOCK_ASSET_CLASSES or holding.source.lower() in STOCK_SOURCES


def _pnl_percent(holding: Holding) -> float | None:
    if holding.cost_basis is None or holding.cost_basis <= 0 or holding.unrealized_pnl is None:
        return None
    return round(holding.unrealized_pnl / holding.cost_basis * 100, 2)


def _position_action(
    holding: Holding,
    weight_percent: float,
    pnl_percent: float | None,
    rules: dict[str, Any] = DEFAULT_STOCK_RULES,
) -> tuple[Literal["hold", "review", "trim_review", "exit_candidate"], list[str], list[str]]:
    profit_review = float(rules["profit_review_percent"])
    strong_gain = float(rules["strong_gain_review_percent"])
    loss_review = float(rules["loss_review_percent"])
    max_weight = float(rules["max_single_stock_percent_of_net_worth"])
    high_vol_symbols = {str(item).upper() for item in rules["high_volatility_symbols"]}
    high_vol_profit = float(rules["high_volatility_profit_review_percent"])

    flags: list[str] = []
    evidence: list[str] = []
    action: Literal["hold", "review", "trim_review", "exit_candidate"] = "hold"

    if weight_percent >= max_weight:
        flags.append("position_size_above_stock_limit")
        evidence.append(f"Position is {weight_percent}% of net worth vs {max_weight}% stock-level limit.")
        action = "trim_review"

    if pnl_percent is not None:
        if pnl_percent >= strong_gain:
            flags.append("strong_unrealized_gain")
            evidence.append(f"Unrealized gain is {pnl_percent}% vs {strong_gain}% strong-gain review threshold.")
            action = "exit_candidate" if holding.symbol.upper() in high_vol_symbols else "trim_review"
        elif holding.symbol.upper() in high_vol_symbols and pnl_percent >= high_vol_profit:
            flags.append("high_volatility_gain_to_protect")
            evidence.append(
                f"{holding.symbol.upper()} is marked high-volatility and is up {pnl_percent}% vs "
                f"{high_vol_profit}% review threshold."
            )
            action = "trim_review"
        elif pnl_percent >= profit_review:
            flags.append("profit_review")
            evidence.append(f"Unrealized gain is {pnl_percent}% vs {profit_review}% profit-review threshold.")
            action = "trim_review" if action == "hold" else action
        elif pnl_percent <= loss_review:
            flags.append("loss_review")
            evidence.append(f"Unrealized return is {pnl_percent}% vs {loss_review}% loss-review threshold.")
            action = "review" if action == "hold" else action

    return action, flags, evidence


def _position_brief(
    holding: Holding,
    snapshot: PortfolioSnapshot,
    rules: dict[str, Any] = DEFAULT_STOCK_RULES,
) -> StockPositionBrief:
    value = holding.value_in_base
    weight = _pct(value, snapshot.total_net_worth)
    pnl_pct = _pnl_percent(holding)
    action, flags, evidence = _position_action(holding, weight, pnl_pct, rules)

    default_trailing = rules["default_trailing_stop_percent"]
    tight_trailing = rules["tighter_trailing_stop_percent"]
    high_vol_symbols = {str(item).upper() for item in rules["high_volatility_symbols"]}
    trailing = tight_trailing if holding.symbol.upper() in high_vol_symbols else default_trailing

    missing_data: list[str] = []
    if holding.cost_basis is None:
        missing_data.append("cost_basis")
    if holding.current_price is None:
        missing_data.append("current_price")
    if holding.valuation_timestamp is None:
        missing_data.append("valuation_timestamp")

    risk_notes = []
    if holding.symbol.upper() in high_vol_symbols:
        risk_notes.append("High-volatility stock: protect gains and avoid thesis drift.")
    exit_framework = [
        f"Review whether to trim if gains are meaningful and the thesis is no longer improving.",
        f"Consider a {trailing}% trailing-stop reference for gain protection; keep final orders manual.",
        "Define an invalidation point: what business or price action would make this no longer worth holding?",
    ]

    confidence: Literal["low", "medium", "high"] = "high"
    if missing_data:
        confidence = "medium" if len(missing_data) <= 1 else "low"

    return StockPositionBrief(
        symbol=holding.symbol,
        name=holding.name,
        source=holding.source,
        platform=holding.platform,
        asset_class=holding.asset_class,
        quantity=holding.quantity,
        currency=holding.currency,
        current_price=holding.current_price,
        market_value=round(holding.market_value, 2),
        value_in_base=value,
        portfolio_weight_percent=weight,
        cost_basis=holding.cost_basis,
        unrealized_pnl=holding.unrealized_pnl,
        unrealized_pnl_percent=pnl_pct,
        action_bias=action,
        flags=flags,
        evidence=evidence or ["No rule threshold was crossed; review only if thesis or allocation changed."],
        risk_notes=risk_notes,
        exit_framework=exit_framework,
        missing_data=missing_data,
        confidence=confidence,
    )


def _load_watchlist() -> list[dict[str, Any]]:
    return _load_yaml(WATCHLIST_PATH, [])


def _opportunity_brief(
    item: dict[str, Any],
    rules: dict[str, Any] = DEFAULT_STOCK_RULES,
) -> WatchlistOpportunityBrief:
    missing_data = ["fresh_price", "valuation_multiples", "recent_financials", "technical_entry_levels"]
    evidence = []
    for reason in item.get("why_interesting", []) or []:
        evidence.append(str(reason))
    if item.get("thesis"):
        evidence.append("Manual thesis is present.")
    action: Literal["research", "watchlist", "staged_entry_candidate"] = (
        "staged_entry_candidate" if evidence else "research"
    )
    if rules["avoid_buying_without_fresh_price"]:
        evidence.append("Fresh market/fundamental data is required before any buy decision.")

    return WatchlistOpportunityBrief(
        symbol=str(item.get("symbol", "UNKNOWN")).upper(),
        name=item.get("name"),
        asset_class=item.get("asset_class", "equity"),
        currency=str(item.get("currency", "USD")).upper(),
        sector=item.get("sector"),
        vertical=item.get("vertical"),
        geography=item.get("geography"),
        thesis=item.get("thesis"),
        why_interesting=[str(value) for value in item.get("why_interesting", []) or []],
        key_risks=[str(value) for value in item.get("key_risks", []) or []],
        preferred_entry=item.get("preferred_entry"),
        max_position_percent_of_net_worth=item.get("max_position_percent_of_net_worth"),
        action_bias=action,
        evidence=evidence,
        missing_data=missing_data,
        confidence="low",
    )


def build_stock_analysis(settings: Settings | None = None) -> StockAnalysisBrief:
    settings = settings or get_settings()
    snapshot = build_snapshot(settings)
    positions = [
        _position_brief(holding, snapshot)
        for holding in snapshot.holdings
        if _is_stock_holding(holding)
    ]
    positions.sort(
        key=lambda item: (
            {"exit_candidate": 0, "trim_review": 1, "review": 2, "hold": 3}[item.action_bias],
            -item.portfolio_weight_percent,
        )
    )

    opportunities = [_opportunity_brief(item) for item in _load_watchlist()]
    stock_value = sum(item.value_in_base or 0 for item in positions)
    missing_data = sorted({missing for item in positions for missing in item.missing_data})
    if opportunities:
        missing_data.extend(
            sorted({missing for item in opportunities for missing in item.missing_data})
        )

    return StockAnalysisBrief(
        base_currency=snapshot.base_currency,
        net_worth=snapshot.total_net_worth,
        stock_value=round(stock_value, 2),
        stock_weight_percent=_pct(stock_value, snapshot.total_net_worth),
        cash_value=snapshot.total_cash,
        cash_weight_percent=_pct(snapshot.total_cash, snapshot.total_net_worth),
        positions=positions,
        opportunities=opportunities,
        missing_data=sorted(set(missing_data)),
        local_codex_instruction=(
            "Use this stock brief plus skills/analyze_stocks.md as the professional financial advisor "
            "instruction. Do not place trades. Focus on exit discipline for current positions, staged "
            "entries for opportunities, missing data, and concrete next actions."
        ),
    )


def render_markdown(brief: StockAnalysisBrief) -> str:
    def amount(value: float | None, suffix: str = "") -> str:
        if value is None:
            return "unknown"
        return f"{value:,.2f}{suffix}"

    lines = [
        "# Local Stock Analysis Brief",
        "",
        f"Generated: {brief.generated_at.isoformat()}",
        f"Base currency: {brief.base_currency}",
        f"Net worth: {brief.net_worth:,.2f} {brief.base_currency}",
        f"Stock exposure: {brief.stock_value:,.2f} {brief.base_currency} ({brief.stock_weight_percent:.2f}%)",
        f"Cash: {brief.cash_value:,.2f} {brief.base_currency} ({brief.cash_weight_percent:.2f}%)",
        "",
        "## Codex Instruction",
        brief.local_codex_instruction,
        f"Skill file: {STOCK_SKILL_PATH.relative_to(PROJECT_DIR)}",
        "",
        "## Existing Positions",
    ]
    for position in brief.positions:
        lines.extend(
            [
                "",
                f"### {position.symbol} - {position.action_bias}",
                f"- Value: {amount(position.value_in_base)} {brief.base_currency} ({position.portfolio_weight_percent:.2f}% of net worth)",
                f"- Price: {amount(position.current_price)} {position.currency}",
                f"- P/L: {amount(position.unrealized_pnl)} {position.currency} "
                f"({amount(position.unrealized_pnl_percent, '%')})",
                f"- Flags: {', '.join(position.flags) if position.flags else 'none'}",
                f"- Evidence: {'; '.join(position.evidence)}",
                f"- Risk notes: {'; '.join(position.risk_notes) if position.risk_notes else 'none'}",
                f"- Exit framework: {'; '.join(position.exit_framework)}",
                f"- Missing data: {', '.join(position.missing_data) if position.missing_data else 'none'}",
                f"- Confidence: {position.confidence}",
            ]
        )

    lines.extend(["", "## Opportunities"])
    if not brief.opportunities:
        lines.append("No watchlist opportunities loaded.")
    for opportunity in brief.opportunities:
        lines.extend(
            [
                "",
                f"### {opportunity.symbol} - {opportunity.action_bias}",
                f"- Name: {opportunity.name or opportunity.symbol}",
                f"- Theme: {opportunity.vertical or 'unknown'} / {opportunity.geography or 'unknown'}",
                f"- Thesis: {opportunity.thesis or 'missing'}",
                f"- Evidence: {'; '.join(opportunity.evidence) if opportunity.evidence else 'none'}",
                f"- Risks: {'; '.join(opportunity.key_risks) if opportunity.key_risks else 'none'}",
                f"- Preferred entry: {opportunity.preferred_entry or 'staged limit entries'}",
                f"- Missing data: {', '.join(opportunity.missing_data) if opportunity.missing_data else 'none'}",
                f"- Confidence: {opportunity.confidence}",
            ]
        )

    lines.extend(["", "## Missing Data", ", ".join(brief.missing_data) if brief.missing_data else "none"])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a local Codex-ready stock analysis brief.")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = parser.parse_args()
    brief = build_stock_analysis()
    if args.format == "json":
        print(brief.model_dump_json(indent=2))
    else:
        print(render_markdown(brief))


if __name__ == "__main__":
    main()
