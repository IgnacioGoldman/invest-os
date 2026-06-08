"""Deterministic multi-asset opportunity signals."""

from __future__ import annotations

import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import requests
from pydantic import BaseModel, Field

from app.config import DATA_DIR
from app.models import PortfolioSnapshot


ASSET_OPPORTUNITY_DIR = DATA_DIR / "assets" / "derived_signals"
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_24HR_URL = "https://api.binance.com/api/v3/ticker/24hr"

AssetClass = Literal["etf", "commodity_proxy", "crypto"]
MetricKind = Literal["percent", "ratio", "compact", "currency"]
RiskBucket = Literal["core", "major", "thematic", "speculative", "defensive", "broad_market"]


class AssetMetric(BaseModel):
    value: float | None = None
    kind: MetricKind = "ratio"
    source: str
    as_of: str
    notes: str = ""


class AssetInterestingFact(BaseModel):
    type: str
    severity: float = Field(ge=0, le=1)
    text: str
    evidence: list[str] = Field(default_factory=list)


class AssetOpportunity(BaseModel):
    symbol: str
    name: str | None = None
    asset_class: AssetClass
    exposure: str
    category: str | None = None
    currency: str = "USD"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    price_metrics: dict[str, AssetMetric] = Field(default_factory=dict)
    native_metrics: dict[str, AssetMetric] = Field(default_factory=dict)
    scores: dict[str, AssetMetric] = Field(default_factory=dict)
    interesting_facts: list[AssetInterestingFact] = Field(default_factory=list)
    risk_bucket: RiskBucket | None = None
    data_gaps: list[str] = Field(default_factory=list)


class AssetOpportunityFile(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "multi_asset_derived_signals"
    deterministic_inputs: list[str] = Field(default_factory=list)
    count: int
    assets: list[AssetOpportunity]
    collection_errors: list[str] = Field(default_factory=list)


DEFAULT_ETFS: list[dict[str, str]] = [
    {"symbol": "VOO", "exposure": "US large-cap equities", "category": "core_us_equity"},
    {"symbol": "VTI", "exposure": "Total US equities", "category": "core_us_equity"},
    {"symbol": "QQQ", "exposure": "Nasdaq 100 growth equities", "category": "growth_equity"},
    {"symbol": "SCHD", "exposure": "US dividend equities", "category": "dividend_equity"},
    {"symbol": "VXUS", "exposure": "International ex-US equities", "category": "global_equity"},
    {"symbol": "VEA", "exposure": "Developed ex-US equities", "category": "global_equity"},
    {"symbol": "VWO", "exposure": "Emerging market equities", "category": "emerging_markets"},
    {"symbol": "BND", "exposure": "US aggregate bonds", "category": "core_bonds"},
    {"symbol": "TLT", "exposure": "Long US Treasuries", "category": "duration_bonds"},
    {"symbol": "SHY", "exposure": "Short US Treasuries", "category": "cash_like_bonds"},
    {"symbol": "VNQ", "exposure": "US real estate", "category": "real_estate"},
    {"symbol": "XLV", "exposure": "US healthcare sector", "category": "sector"},
    {"symbol": "XLE", "exposure": "US energy sector", "category": "sector"},
    {"symbol": "XLU", "exposure": "US utilities sector", "category": "sector"},
    {"symbol": "XLI", "exposure": "US industrial sector", "category": "sector"},
    {"symbol": "SOXX", "exposure": "Semiconductors", "category": "thematic_equity"},
]

DEFAULT_COMMODITY_PROXIES: list[dict[str, str]] = [
    {"symbol": "GLD", "exposure": "Gold", "category": "precious_metals"},
    {"symbol": "IAU", "exposure": "Gold", "category": "precious_metals"},
    {"symbol": "SLV", "exposure": "Silver", "category": "precious_metals"},
    {"symbol": "PPLT", "exposure": "Platinum", "category": "precious_metals"},
    {"symbol": "PALL", "exposure": "Palladium", "category": "precious_metals"},
    {"symbol": "CPER", "exposure": "Copper", "category": "industrial_metals"},
    {"symbol": "DBC", "exposure": "Broad commodities", "category": "broad_commodities"},
    {"symbol": "PDBC", "exposure": "Broad commodities", "category": "broad_commodities"},
    {"symbol": "USO", "exposure": "Crude oil", "category": "energy_commodities"},
]

DEFAULT_CRYPTOS: list[dict[str, str]] = [
    {"symbol": "BTC", "exposure": "Bitcoin", "category": "store_of_value"},
    {"symbol": "ETH", "exposure": "Ethereum", "category": "smart_contracts"},
    {"symbol": "SOL", "exposure": "Solana", "category": "smart_contracts"},
    {"symbol": "BNB", "exposure": "BNB", "category": "exchange_token"},
    {"symbol": "XRP", "exposure": "XRP", "category": "payments"},
    {"symbol": "ADA", "exposure": "Cardano", "category": "smart_contracts"},
    {"symbol": "LINK", "exposure": "Chainlink", "category": "infrastructure"},
    {"symbol": "AVAX", "exposure": "Avalanche", "category": "smart_contracts"},
]


def latest_asset_opportunity_path(data_dir: Path = ASSET_OPPORTUNITY_DIR) -> Path:
    return data_dir / "latest.json"


def save_asset_opportunities(
    payload: AssetOpportunityFile,
    data_dir: Path = ASSET_OPPORTUNITY_DIR,
) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload.model_dump(mode="json"), indent=2, sort_keys=False)
    dated_path = data_dir / f"{payload.generated_at.date().isoformat()}.json"
    latest_path = latest_asset_opportunity_path(data_dir)
    dated_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return latest_path


def load_latest_asset_opportunities(
    data_dir: Path = ASSET_OPPORTUNITY_DIR,
) -> AssetOpportunityFile | None:
    path = latest_asset_opportunity_path(data_dir)
    if not path.exists():
        return None
    return AssetOpportunityFile.model_validate_json(path.read_text(encoding="utf-8"))


def load_asset_opportunities_by_class(asset_class: AssetClass) -> list[AssetOpportunity]:
    payload = load_latest_asset_opportunities()
    if payload is None:
        return []
    return [asset for asset in payload.assets if asset.asset_class == asset_class]


def _finite(value: Any) -> float | None:
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def _metric(value: float | None, kind: MetricKind, source: str, as_of: str, notes: str = "") -> AssetMetric:
    return AssetMetric(value=value, kind=kind, source=source, as_of=as_of, notes=notes)


def _pct_change(current: float | None, past: float | None) -> float | None:
    if current is None or past in (None, 0):
        return None
    return ((current / past) - 1) * 100


def _annualized_volatility(closes: list[float], window: int) -> float | None:
    tail = closes[-(window + 1) :]
    if len(tail) < max(8, min(window, 12)):
        return None
    returns = [(tail[index] / tail[index - 1]) - 1 for index in range(1, len(tail)) if tail[index - 1] > 0]
    if len(returns) < 2:
        return None
    return statistics.pstdev(returns) * math.sqrt(365 if window <= 90 else 252) * 100


def _max_drawdown(closes: list[float], window: int) -> float | None:
    tail = closes[-window:]
    if len(tail) < 2:
        return None
    peak = tail[0]
    worst = 0.0
    for close in tail:
        peak = max(peak, close)
        if peak > 0:
            worst = min(worst, (close / peak - 1) * 100)
    return worst


def _price_metrics(closes: list[float], volumes: list[float], source: str, as_of: str) -> dict[str, AssetMetric]:
    current = closes[-1] if closes else None
    high_52w = max(closes[-252:]) if len(closes) >= 2 else None
    low_52w = min(closes[-252:]) if len(closes) >= 2 else None
    ath = max(closes) if closes else None
    avg_volume_30d = statistics.fmean(volumes[-30:]) if volumes else None
    avg_dollar_volume_30d = avg_volume_30d * current if avg_volume_30d is not None and current is not None else None
    return {
        "current_price": _metric(current, "currency", source, as_of, "Latest available close."),
        "change_1m": _metric(_pct_change(current, closes[-22] if len(closes) >= 22 else None), "percent", source, as_of),
        "change_3m": _metric(_pct_change(current, closes[-64] if len(closes) >= 64 else None), "percent", source, as_of),
        "change_6m": _metric(_pct_change(current, closes[-127] if len(closes) >= 127 else None), "percent", source, as_of),
        "change_1y": _metric(_pct_change(current, closes[-253] if len(closes) >= 253 else None), "percent", source, as_of),
        "change_3y": _metric(_pct_change(current, closes[-757] if len(closes) >= 757 else None), "percent", source, as_of),
        "distance_from_52w_high": _metric(_pct_change(current, high_52w), "percent", source, as_of),
        "distance_from_52w_low": _metric(_pct_change(current, low_52w), "percent", source, as_of),
        "distance_from_ath": _metric(_pct_change(current, ath), "percent", source, as_of),
        "volatility_30d": _metric(_annualized_volatility(closes, 30), "percent", source, as_of),
        "volatility_90d": _metric(_annualized_volatility(closes, 90), "percent", source, as_of),
        "max_drawdown_1y": _metric(_max_drawdown(closes, 252), "percent", source, as_of),
        "avg_volume_30d": _metric(avg_volume_30d, "compact", source, as_of),
        "avg_dollar_volume_30d": _metric(avg_dollar_volume_30d, "compact", source, as_of),
    }


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(value, high))


def _liquidity_score(avg_dollar_volume: float | None) -> float | None:
    if avg_dollar_volume is None or avg_dollar_volume <= 0:
        return None
    return _clamp((math.log10(avg_dollar_volume) - 5) / 4 * 100)


def _momentum_score(change_3m: float | None, change_1y: float | None) -> float | None:
    parts = []
    if change_3m is not None:
        parts.append(_clamp(50 + change_3m * 1.6))
    if change_1y is not None:
        parts.append(_clamp(45 + change_1y * 0.7))
    return statistics.fmean(parts) if parts else None


def _drawdown_score(distance_52w: float | None, max_drawdown_1y: float | None) -> float | None:
    if distance_52w is None:
        return None
    drawdown = abs(distance_52w)
    if drawdown <= 3:
        score = 35
    elif drawdown <= 15:
        score = 60 + drawdown
    elif drawdown <= 35:
        score = 90 - (drawdown - 15)
    else:
        score = 45
    if max_drawdown_1y is not None and max_drawdown_1y < -45:
        score -= 15
    return _clamp(score)


def _volatility_risk_score(volatility_90d: float | None, asset_class: AssetClass) -> float | None:
    if volatility_90d is None:
        return None
    baseline = 80 if asset_class == "crypto" else 28 if asset_class == "etf" else 35
    return _clamp((volatility_90d / baseline) * 100)


def _expense_score(expense_ratio: float | None) -> float | None:
    if expense_ratio is None:
        return None
    return _clamp(100 - expense_ratio * 80)


def _portfolio_fit_score(asset: dict[str, str], portfolio_snapshot: PortfolioSnapshot | None) -> float | None:
    if portfolio_snapshot is None or portfolio_snapshot.total_net_worth <= 0:
        return None
    target_class = asset["asset_class"]
    class_value = sum(
        holding.value_in_base or 0
        for holding in portfolio_snapshot.holdings
        if holding.asset_class.lower() == target_class.replace("_proxy", "")
    )
    if target_class == "commodity_proxy":
        class_value = sum(
            holding.value_in_base or 0
            for holding in portfolio_snapshot.holdings
            if holding.asset_class.lower() in {"commodity", "commodity_proxy", "gold", "silver"}
        )
    class_weight = (class_value / portfolio_snapshot.total_net_worth) * 100
    existing_symbol = any(holding.symbol.upper() == asset["symbol"] for holding in portfolio_snapshot.holdings)
    fit = 72 - class_weight * 1.8
    if existing_symbol:
        fit -= 18
    if target_class in {"etf", "commodity_proxy"} and class_weight < 5:
        fit += 12
    return _clamp(fit)


def _score_metrics(
    price_metrics: dict[str, AssetMetric],
    native_metrics: dict[str, AssetMetric],
    asset_class: AssetClass,
    portfolio_fit: float | None,
) -> dict[str, AssetMetric]:
    as_of = next(iter(price_metrics.values())).as_of if price_metrics else datetime.now(timezone.utc).date().isoformat()
    source = "derived_from_price_metrics"
    liquidity = _liquidity_score(price_metrics.get("avg_dollar_volume_30d", AssetMetric(source="", as_of="")).value)
    momentum = _momentum_score(
        price_metrics.get("change_3m", AssetMetric(source="", as_of="")).value,
        price_metrics.get("change_1y", AssetMetric(source="", as_of="")).value,
    )
    drawdown = _drawdown_score(
        price_metrics.get("distance_from_52w_high", AssetMetric(source="", as_of="")).value,
        price_metrics.get("max_drawdown_1y", AssetMetric(source="", as_of="")).value,
    )
    risk = _volatility_risk_score(
        price_metrics.get("volatility_90d", AssetMetric(source="", as_of="")).value,
        asset_class,
    )
    expense = _expense_score(native_metrics.get("expense_ratio", AssetMetric(source="", as_of="")).value)
    attractiveness_parts = [value for value in [drawdown, momentum, expense] if value is not None]
    attractiveness = statistics.fmean(attractiveness_parts) if attractiveness_parts else None
    risk_adjustment = None if risk is None else max(0, 20 - risk * 0.18)
    overall_parts = [value for value in [attractiveness, liquidity, portfolio_fit, risk_adjustment] if value is not None]
    overall = statistics.fmean(overall_parts) if overall_parts else None
    return {
        "overall_opportunity_score": _metric(overall, "ratio", source, as_of, "Composite of price attractiveness, liquidity, risk, and portfolio fit."),
        "valuation_or_price_attractiveness_score": _metric(attractiveness, "ratio", source, as_of),
        "momentum_score": _metric(momentum, "ratio", source, as_of),
        "drawdown_score": _metric(drawdown, "ratio", source, as_of),
        "liquidity_score": _metric(liquidity, "ratio", source, as_of),
        "volatility_risk_score": _metric(risk, "ratio", source, as_of, "Higher means more volatile/risky."),
        "portfolio_fit_score": _metric(portfolio_fit, "ratio", "portfolio_snapshot", as_of, "Higher means more diversifying versus the current portfolio."),
    }


def _interesting_facts(
    symbol: str,
    asset_class: AssetClass,
    price_metrics: dict[str, AssetMetric],
    scores: dict[str, AssetMetric],
    native_metrics: dict[str, AssetMetric],
) -> list[AssetInterestingFact]:
    facts: list[AssetInterestingFact] = []
    change_3m = price_metrics["change_3m"].value
    change_1y = price_metrics["change_1y"].value
    distance_high = price_metrics["distance_from_52w_high"].value
    risk = scores["volatility_risk_score"].value
    liquidity = scores["liquidity_score"].value
    expense = native_metrics.get("expense_ratio")
    portfolio_fit = scores["portfolio_fit_score"].value

    if change_3m is not None and abs(change_3m) >= 12:
        direction = "strong positive" if change_3m > 0 else "negative"
        facts.append(AssetInterestingFact(type="three_month_momentum", severity=min(abs(change_3m) / 35, 1), text=f"{symbol} has {direction} 3-month momentum at {change_3m:.1f}%.", evidence=["price_metrics.change_3m"]))
    if change_1y is not None and abs(change_1y) >= 25:
        direction = "up" if change_1y > 0 else "down"
        facts.append(AssetInterestingFact(type="one_year_move", severity=min(abs(change_1y) / 70, 1), text=f"{symbol} is {direction} {abs(change_1y):.1f}% over one year.", evidence=["price_metrics.change_1y"]))
    if distance_high is not None and distance_high <= -12:
        facts.append(AssetInterestingFact(type="off_highs", severity=min(abs(distance_high) / 35, 1), text=f"{symbol} trades {abs(distance_high):.1f}% below its 52-week high.", evidence=["price_metrics.distance_from_52w_high"]))
    if risk is not None and risk >= 85:
        facts.append(AssetInterestingFact(type="high_volatility", severity=min(risk / 100, 1), text=f"{symbol} has high realized volatility for its asset class.", evidence=["price_metrics.volatility_90d"]))
    if liquidity is not None and liquidity <= 35:
        facts.append(AssetInterestingFact(type="liquidity_caution", severity=0.65, text=f"{symbol} has weaker liquidity than the rest of the opportunity set.", evidence=["price_metrics.avg_dollar_volume_30d"]))
    if expense is not None and expense.value is not None and asset_class in {"etf", "commodity_proxy"}:
        if expense.value <= 0.12:
            facts.append(AssetInterestingFact(type="low_expense", severity=0.35, text=f"{symbol} has a low expense ratio at {expense.value:.2f}%.", evidence=["native_metrics.expense_ratio"]))
        elif expense.value >= 0.75:
            facts.append(AssetInterestingFact(type="high_expense", severity=0.55, text=f"{symbol} has a relatively high expense ratio at {expense.value:.2f}%.", evidence=["native_metrics.expense_ratio"]))
    if portfolio_fit is not None and portfolio_fit >= 75:
        facts.append(AssetInterestingFact(type="portfolio_fit", severity=0.55, text=f"{symbol} improves diversification versus the current portfolio mix.", evidence=["scores.portfolio_fit_score"]))
    facts.sort(key=lambda fact: fact.severity, reverse=True)
    return facts[:6]


def _risk_bucket(asset_class: AssetClass, category: str | None) -> RiskBucket:
    if asset_class == "crypto":
        return "core" if category in {"store_of_value", "smart_contracts"} else "speculative"
    if asset_class == "commodity_proxy":
        return "defensive" if category == "precious_metals" else "thematic"
    if category in {"core_us_equity", "global_equity", "core_bonds"}:
        return "broad_market"
    if category in {"cash_like_bonds", "duration_bonds"}:
        return "defensive"
    return "thematic"


def _build_yfinance_asset(asset: dict[str, str], portfolio_snapshot: PortfolioSnapshot | None) -> AssetOpportunity:
    import yfinance as yf  # type: ignore[import-not-found]

    symbol = asset["symbol"].upper()
    ticker = yf.Ticker(symbol)
    gaps: list[str] = []
    info: dict[str, Any] = {}
    try:
        info = ticker.get_info() or {}
    except Exception as exc:
        gaps.append(f"yfinance info unavailable: {exc}")

    history = ticker.history(period="5y", interval="1d", auto_adjust=False)
    if history is None or history.empty or "Close" not in history:
        raise ValueError(f"No yfinance price history for {symbol}.")
    closes = [_finite(value) for value in history["Close"].dropna().tolist()]
    volumes = [_finite(value) for value in history.get("Volume", []).dropna().tolist()] if "Volume" in history else []
    close_values = [value for value in closes if value is not None and value > 0]
    volume_values = [value for value in volumes if value is not None and value >= 0]
    as_of = str(history.index[-1].date())
    price_metrics = _price_metrics(close_values, volume_values, f"yfinance:{symbol}", as_of)
    raw_expense = _finite(info.get("annualReportExpenseRatio") or info.get("netExpenseRatio"))
    raw_yield = _finite(info.get("yield") or info.get("trailingAnnualDividendYield"))
    expense_ratio = raw_expense * 100 if raw_expense is not None and raw_expense < 0.01 else raw_expense
    dividend_yield = raw_yield * 100 if raw_yield is not None and raw_yield <= 1 else raw_yield
    native_metrics = {
        "expense_ratio": _metric(expense_ratio, "percent", f"yfinance:{symbol}", as_of, "Fund annual expense ratio when available."),
        "dividend_yield": _metric(dividend_yield, "percent", f"yfinance:{symbol}", as_of),
        "total_assets": _metric(_finite(info.get("totalAssets")), "compact", f"yfinance:{symbol}", as_of),
    }
    scores = _score_metrics(price_metrics, native_metrics, asset["asset_class"], _portfolio_fit_score(asset, portfolio_snapshot))
    name = info.get("longName") or info.get("shortName") or symbol
    return AssetOpportunity(
        symbol=symbol,
        name=str(name),
        asset_class=asset["asset_class"],
        exposure=asset["exposure"],
        category=asset.get("category"),
        currency=str(info.get("currency") or "USD"),
        price_metrics=price_metrics,
        native_metrics=native_metrics,
        scores=scores,
        interesting_facts=_interesting_facts(symbol, asset["asset_class"], price_metrics, scores, native_metrics),
        risk_bucket=_risk_bucket(asset["asset_class"], asset.get("category")),
        data_gaps=gaps,
    )


def _binance_klines(symbol: str) -> tuple[list[float], list[float], str]:
    response = requests.get(
        BINANCE_KLINES_URL,
        params={"symbol": f"{symbol}USDT", "interval": "1d", "limit": 1000},
        timeout=20,
    )
    response.raise_for_status()
    rows = response.json()
    closes = [float(row[4]) for row in rows]
    volumes = [float(row[7]) for row in rows]
    as_of = datetime.fromtimestamp(rows[-1][6] / 1000, timezone.utc).date().isoformat()
    return closes, volumes, as_of


def _binance_24h(symbol: str) -> dict[str, Any]:
    response = requests.get(BINANCE_24HR_URL, params={"symbol": f"{symbol}USDT"}, timeout=12)
    response.raise_for_status()
    return response.json()


def _build_crypto_asset(asset: dict[str, str], portfolio_snapshot: PortfolioSnapshot | None) -> AssetOpportunity:
    symbol = asset["symbol"].upper()
    closes, quote_volumes, as_of = _binance_klines(symbol)
    price_metrics = _price_metrics(closes, quote_volumes, f"binance:{symbol}USDT", as_of)
    ticker_24h: dict[str, Any] = {}
    gaps: list[str] = []
    try:
        ticker_24h = _binance_24h(symbol)
    except requests.RequestException as exc:
        gaps.append(f"Binance 24h ticker unavailable: {exc}")
    native_metrics = {
        "quote_volume_24h": _metric(_finite(float(ticker_24h["quoteVolume"])) if ticker_24h.get("quoteVolume") else None, "compact", f"binance:{symbol}USDT", as_of),
        "price_change_24h": _metric(_finite(float(ticker_24h["priceChangePercent"])) if ticker_24h.get("priceChangePercent") else None, "percent", f"binance:{symbol}USDT", as_of),
    }
    scores = _score_metrics(price_metrics, native_metrics, "crypto", _portfolio_fit_score(asset, portfolio_snapshot))
    return AssetOpportunity(
        symbol=symbol,
        name=asset["exposure"],
        asset_class="crypto",
        exposure=asset["exposure"],
        category=asset.get("category"),
        currency="USDT",
        price_metrics=price_metrics,
        native_metrics=native_metrics,
        scores=scores,
        interesting_facts=_interesting_facts(symbol, "crypto", price_metrics, scores, native_metrics),
        risk_bucket=_risk_bucket("crypto", asset.get("category")),
        data_gaps=gaps,
    )


def build_asset_opportunities_file(
    *,
    portfolio_snapshot: PortfolioSnapshot | None = None,
    include_etfs: bool = True,
    include_commodities: bool = True,
    include_crypto: bool = True,
) -> AssetOpportunityFile:
    assets: list[AssetOpportunity] = []
    deterministic_inputs: list[str] = []
    failures: list[str] = []
    if include_etfs:
        for item in DEFAULT_ETFS:
            try:
                assets.append(_build_yfinance_asset({**item, "asset_class": "etf"}, portfolio_snapshot))
            except Exception as exc:
                failures.append(f"{item['symbol']}: {exc}")
    if include_commodities:
        for item in DEFAULT_COMMODITY_PROXIES:
            try:
                assets.append(_build_yfinance_asset({**item, "asset_class": "commodity_proxy"}, portfolio_snapshot))
            except Exception as exc:
                failures.append(f"{item['symbol']}: {exc}")
    if include_crypto:
        for item in DEFAULT_CRYPTOS:
            try:
                assets.append(_build_crypto_asset({**item, "asset_class": "crypto"}, portfolio_snapshot))
            except Exception as exc:
                failures.append(f"{item['symbol']}: {exc}")

    deterministic_inputs.extend(
        [
            "yfinance ETF and commodity-proxy price/history/info",
            "Binance public crypto klines and 24h ticker",
            "portfolio snapshot for portfolio_fit_score when available",
        ]
    )
    generated = datetime.now(timezone.utc)
    return AssetOpportunityFile(
        generated_at=generated,
        deterministic_inputs=deterministic_inputs,
        count=len(assets),
        assets=assets,
        collection_errors=failures,
    )
