"""AI-generated portfolio recommendations."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import requests
from pydantic import BaseModel, Field, ValidationError

from app.config import Settings, get_settings
from app.models import PortfolioSnapshot
from app.entry_engine.open_data_models import OpenDataMetric, OpenDataSnapshot
from app.entry_engine.utils.file_storage import load_latest_open_data_stock_snapshot
from app.services.storage import (
    connect,
    load_recommendation_followup_payload,
    load_recommendation_followup_payloads,
    load_recommendation_payloads,
    load_recommendations_generated_at,
    replace_recommendations,
    save_recommendation_followup,
)
from app.services.stock_entry_analysis import StockEntryAnalysis, analyze_latest_open_data_stock_entry


PROJECT_DIR = Path(__file__).resolve().parents[3]
PORTFOLIO_RECOMMENDATIONS_SKILL_DIR = PROJECT_DIR / "skills" / "portfolio-recommendations"
STOCK_DERIVED_SIGNALS_PATH = PROJECT_DIR / "data" / "stocks" / "derived_signals" / "latest.json"
ASSET_DERIVED_SIGNALS_PATH = PROJECT_DIR / "data" / "assets" / "derived_signals" / "latest.json"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


class Recommendation(BaseModel):
    severity: Literal["info", "warning", "critical"]
    category: Literal[
        "allocation",
        "drawdown_reserve",
        "trim_or_exit",
        "capital_move",
        "entry",
        "concentration",
        "theme",
    ] = "allocation"
    title: str
    detail: str


class RecommendationList(BaseModel):
    recommendations: list[Recommendation]


class RecommendationSnapshot(BaseModel):
    generated_at: datetime | None = None
    recommendations: list[Recommendation]


class RecommendationFollowUpRequest(BaseModel):
    recommendation: Recommendation
    question: str


class RecommendationFollowUpResponse(BaseModel):
    recommendation_key: str
    question: str
    generated_at: datetime
    mode: Literal["openai", "codex_required", "codex"]
    status: Literal["complete", "pending_codex"] = "complete"
    answer: str
    context_tickers: list[str] = Field(default_factory=list)
    follow_up_id: str | None = None
    codex_command: str | None = None


class RecommendationFollowUpCodexResultRequest(BaseModel):
    request_id: str
    answer: str


def recommendation_key(recommendation: Recommendation) -> str:
    return f"{recommendation.category}:{recommendation.severity}:{recommendation.title}:{recommendation.detail}"


RECOMMENDATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "recommendations": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "severity": {"type": "string", "enum": ["info", "warning", "critical"]},
                    "category": {
                        "type": "string",
                        "enum": [
                            "allocation",
                            "drawdown_reserve",
                            "trim_or_exit",
                            "capital_move",
                            "entry",
                            "concentration",
                            "theme",
                        ],
                    },
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                },
                "required": ["severity", "category", "title", "detail"],
            },
        }
    },
    "required": ["recommendations"],
}


def _skill_text() -> str:
    if PORTFOLIO_RECOMMENDATIONS_SKILL_DIR.exists():
        skill_parts = []
        for path in sorted(PORTFOLIO_RECOMMENDATIONS_SKILL_DIR.glob("*.md")):
            skill_parts.append(f"# Skill file: {path.name}\n\n{path.read_text(encoding='utf-8')}")
        if skill_parts:
            return "\n\n---\n\n".join(skill_parts)
    return (
        "Analyze the portfolio snapshot as a read-only portfolio advisor. "
        "Return concise, actionable recommendations without placing trades."
    )


def _snapshot_payload(snapshot: PortfolioSnapshot) -> str:
    return json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True)


def _safe_load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _compact_stock_signals(limit: int = 50) -> dict[str, Any] | None:
    payload = _safe_load_json(STOCK_DERIVED_SIGNALS_PATH)
    if not isinstance(payload, dict):
        return None
    rows = payload.get("stocks")
    if not isinstance(rows, list):
        return None

    def unusual(row: dict[str, Any]) -> float:
        metric = row.get("derived_metrics", {}).get("unusual_score", {})
        value = metric.get("value")
        return float(value) if isinstance(value, (int, float)) else -1

    selected = sorted((row for row in rows if isinstance(row, dict)), key=unusual, reverse=True)[:limit]
    compact = []
    for row in selected:
        metrics = row.get("derived_metrics", {})
        compact.append(
            {
                "ticker": row.get("ticker"),
                "name": row.get("name"),
                "sector": row.get("sector"),
                "industry": row.get("industry"),
                "derived_metrics": {
                    key: metrics.get(key)
                    for key in (
                        "unusual_score",
                        "fcfy_hist_percentile",
                        "pe_vs_median",
                        "rev_accel",
                        "eps_accel",
                        "growth_plus_fcfy",
                        "sector_rev_rank",
                        "sector_fcfy_rank",
                        "sector_pe_cheap_rank",
                        "price_fund_gap",
                        "net_debt_to_fcf",
                    )
                    if key in metrics
                },
                "interesting_facts": row.get("interesting_facts", [])[:5],
                "data_gaps": row.get("data_gaps", [])[:5],
            }
        )
    return {
        "source": payload.get("source"),
        "generated_at": payload.get("generated_at"),
        "count": payload.get("count"),
        "selection_note": f"Top {len(compact)} stocks by deterministic unusual_score; full file remains at data/stocks/derived_signals/latest.json.",
        "stocks": compact,
    }


def _deterministic_opportunity_payload() -> str:
    context = {
        "multi_asset_derived_signals": _safe_load_json(ASSET_DERIVED_SIGNALS_PATH),
        "stock_derived_signals_compact": _compact_stock_signals(),
        "missing_files": [
            str(path.relative_to(PROJECT_DIR))
            for path in (ASSET_DERIVED_SIGNALS_PATH, STOCK_DERIVED_SIGNALS_PATH)
            if not path.exists()
        ],
    }
    return json.dumps(context, indent=2, sort_keys=True)


def _extract_text(response_json: dict[str, Any]) -> str:
    output_text = response_json.get("output_text")
    if isinstance(output_text, str):
        return output_text

    parts: list[str] = []
    for item in response_json.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                parts.append(content["text"])
    return "\n".join(parts)


def _stock_metric(snapshot: OpenDataSnapshot | None, group: str, key: str) -> OpenDataMetric | None:
    if snapshot is None:
        return None
    metric = getattr(snapshot, group, {}).get(key)
    return metric if isinstance(metric, OpenDataMetric) else None


def _stock_value(snapshot: OpenDataSnapshot | None, group: str, key: str) -> float | None:
    metric = _stock_metric(snapshot, group, key)
    return metric.value if metric else None


def _derived_stock_row(ticker: str) -> dict[str, Any] | None:
    payload = _safe_load_json(STOCK_DERIVED_SIGNALS_PATH)
    rows = payload.get("stocks") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and str(row.get("ticker") or "").upper() == ticker.upper():
            return row
    return None


def _known_tickers(snapshot: PortfolioSnapshot) -> set[str]:
    tickers = {holding.symbol.upper() for holding in snapshot.holdings if holding.symbol}
    payload = _safe_load_json(STOCK_DERIVED_SIGNALS_PATH)
    rows = payload.get("stocks") if isinstance(payload, dict) else None
    if isinstance(rows, list):
        tickers.update(str(row.get("ticker") or "").upper() for row in rows if isinstance(row, dict) and row.get("ticker"))
    return tickers


def _extract_context_tickers(snapshot: PortfolioSnapshot, recommendation: Recommendation, question: str) -> list[str]:
    known = _known_tickers(snapshot)
    recommendation_text = f"{recommendation.title} {recommendation.detail}".upper()
    stopwords = {
        "A",
        "AI",
        "AN",
        "AND",
        "BUY",
        "CAP",
        "EUR",
        "I",
        "IF",
        "IN",
        "IS",
        "IT",
        "NO",
        "OR",
        "SELL",
        "THE",
        "TO",
        "USD",
    }
    recommendation_tokens = {
        token for token in re.findall(r"\b[A-Z][A-Z0-9.-]{0,5}\b", recommendation_text) if token not in stopwords
    }
    explicit_question_tokens = {
        token.upper() for token in re.findall(r"\$([A-Za-z][A-Za-z0-9.-]{0,5})\b", question) if token.upper() not in stopwords
    }
    uppercase_question_tokens = {
        token for token in re.findall(r"\b[A-Z][A-Z0-9.-]{1,5}\b", question) if token not in stopwords
    }
    tokens = recommendation_tokens | explicit_question_tokens | uppercase_question_tokens
    return sorted(token for token in tokens if token in known)


def _target_price_from_question(question: str, current_price: float | None) -> float | None:
    values = [float(match) for match in re.findall(r"(?:\$|price(?:\s+goes)?\s+to\s+)?\b(\d+(?:\.\d+)?)\b", question.lower())]
    if not values:
        return None
    if current_price:
        higher_values = [value for value in values if value > current_price * 1.05]
        if higher_values:
            return max(higher_values)
    return max(values)


def _nearest_dollar(value: float) -> int:
    return int(round(value))


def _ticker_position(snapshot: PortfolioSnapshot, ticker: str):
    holdings = [holding for holding in snapshot.holdings if holding.symbol.upper() == ticker.upper()]
    quantity = sum(holding.quantity for holding in holdings)
    value_in_base = sum(holding.value_in_base or 0 for holding in holdings)
    current_price = next((holding.current_price for holding in holdings if holding.current_price is not None), None)
    currency = next((holding.currency for holding in holdings if holding.currency), "USD")
    return holdings, quantity, value_in_base, current_price, currency


def _position_value_at_price(snapshot: PortfolioSnapshot, quantity: float, target_price: float, currency: str) -> float | None:
    converted_unit = _convert_to_base(snapshot, target_price, currency)
    if converted_unit is None:
        return None
    return quantity * converted_unit


def _percent_of_net_worth(snapshot: PortfolioSnapshot, value: float) -> float:
    return value / snapshot.total_net_worth * 100 if snapshot.total_net_worth > 0 else 0.0


def _stock_context_summary(ticker: str) -> tuple[OpenDataSnapshot | None, StockEntryAnalysis | None, dict[str, Any] | None]:
    stock_snapshot = load_latest_open_data_stock_snapshot(ticker)
    stock_analysis = analyze_latest_open_data_stock_entry(ticker)
    return stock_snapshot, stock_analysis, _derived_stock_row(ticker)


def _local_ticker_followup(snapshot: PortfolioSnapshot, recommendation: Recommendation, question: str, ticker: str) -> str:
    stock_snapshot, stock_analysis, derived = _stock_context_summary(ticker)
    _holdings, quantity, current_value, current_price, currency = _ticker_position(snapshot, ticker)
    current_price = current_price or _stock_value(stock_snapshot, "price_opportunity", "current_price")
    target_price = _target_price_from_question(question, current_price)
    current_percent = _percent_of_net_worth(snapshot, current_value)
    target_sentence = ""
    trim_plan = ""
    if target_price and current_price and quantity > 0:
        target_value = _position_value_at_price(snapshot, quantity, target_price, currency)
        if target_value is not None:
            implied_net_worth = snapshot.total_net_worth + (target_value - current_value)
            target_percent = target_value / implied_net_worth * 100 if implied_net_worth > 0 else 0.0
            target_sentence = (
                f"At ${target_price:.0f}, the position would be about {_format_base(snapshot, target_value)} "
                f"or {_format_percent(target_percent)} of net worth, assuming the rest of the portfolio is unchanged."
            )
            first_trim = _nearest_dollar(current_price + (target_price - current_price) * 0.30)
            second_trim = _nearest_dollar(current_price + (target_price - current_price) * 0.60)
            trim_plan = (
                f"I would not wait for ${target_price:.0f} with the whole position. A more robust plan is to trim "
                f"15-20% around ${first_trim}, another 20-25% around ${second_trim}, and leave the rest for "
                f"${max(second_trim + 1, int(target_price) - 3)}-${int(target_price)} if momentum and fundamentals still support it."
            )

    support = _stock_metric(stock_snapshot, "price_opportunity", "support_1d_distance")
    revenue_growth = _stock_value(stock_snapshot, "business_health", "revenue_growth_yoy")
    fcf_yield = _stock_value(stock_snapshot, "valuation", "fcf_yield")
    pe = _stock_value(stock_snapshot, "valuation", "pe")
    derived_metrics = derived.get("derived_metrics", {}) if isinstance(derived, dict) else {}
    fcfy_percentile = (derived_metrics.get("fcfy_hist_percentile") or {}).get("value")
    price_gap = (derived_metrics.get("price_fund_gap") or {}).get("value")
    evidence = [
        f"{ticker} is currently about {_format_base(snapshot, current_value)} or {_format_percent(current_percent)} of net worth.",
    ]
    if current_price:
        evidence.append(f"Latest price in the snapshot is ${current_price:.2f}.")
    if revenue_growth is not None:
        evidence.append(f"Revenue growth is {_format_percent(revenue_growth)} YoY.")
    if fcf_yield is not None:
        evidence.append(f"FCF yield is {_format_percent(fcf_yield)}.")
    if pe is not None:
        evidence.append(f"Trailing PE is {pe:.1f}.")
    if fcfy_percentile is not None:
        evidence.append(f"FCF-yield historical percentile is {fcfy_percentile:.0f}%.")
    if price_gap is not None:
        evidence.append(f"One-year price performance lags revenue growth by {_format_percent(abs(price_gap))}.")
    if stock_analysis:
        evidence.append(f"Local stock analysis: {stock_analysis.opportunity_type}, conviction {stock_analysis.conviction:.1f}/10.")
    if support:
        evidence.append(support.notes)

    answer_parts = [
        "Short answer: I would make this a staged trim, not a single all-or-nothing target.",
        *evidence,
    ]
    if target_sentence:
        answer_parts.append(target_sentence)
    if trim_plan:
        answer_parts.append(trim_plan)
    answer_parts.append(
        "Reasoning: the business quality is real, but this is already a large single-name exposure. A staged trim lets you keep upside while reducing the risk that a reasonable target becomes a psychological anchor."
    )
    answer_parts.append("This is advisory analysis, not an instruction to place a trade.")
    return "\n\n".join(answer_parts)


def _local_followup_answer(snapshot: PortfolioSnapshot, recommendation: Recommendation, question: str, tickers: list[str]) -> str:
    if tickers:
        return _local_ticker_followup(snapshot, recommendation, question, tickers[0])
    return (
        "I would treat this as a sizing and sequencing question. The recommendation is flagging portfolio risk, not predicting a single outcome. "
        "Use it to define a concrete guardrail: what exposure is acceptable, what condition would trigger a trim, and what capital should remain reserved before adding new risk. "
        "If you ask with a specific ticker, price, or target, I can use the position and stock-insight data to give a more precise staged plan."
    )


def _followup_context(snapshot: PortfolioSnapshot, recommendation: Recommendation, question: str, tickers: list[str]) -> dict[str, Any]:
    stock_context: dict[str, Any] = {}
    for ticker in tickers:
        stock_snapshot, stock_analysis, derived = _stock_context_summary(ticker)
        stock_context[ticker] = {
            "open_data_snapshot": stock_snapshot.model_dump(mode="json") if stock_snapshot else None,
            "stock_entry_analysis": stock_analysis.model_dump(mode="json") if stock_analysis else None,
            "derived_signals": derived,
        }
    return {
        "recommendation": recommendation.model_dump(mode="json"),
        "question": question,
        "context_tickers": tickers,
        "portfolio_snapshot": snapshot.model_dump(mode="json"),
        "stock_context": stock_context,
    }


def _codex_followup_command(request_id: str, request: RecommendationFollowUpRequest, tickers: list[str]) -> str:
    callback_payload = json.dumps({"request_id": request_id, "answer": "REPLACE_WITH_FINAL_ANALYSIS"})
    return (
        f"Paste this into Codex IDE while the Invest OS backend is running from {PROJECT_DIR}:\n\n"
        "Answer this Invest OS recommendation follow-up using AI reasoning and the local repo data. "
        "Inspect the current portfolio snapshot, saved recommendations, and any relevant stock/asset insight files. "
        "Do not place trades, and do not use a deterministic fallback as the final answer.\n\n"
        f"Recommendation JSON:\n{json.dumps(request.recommendation.model_dump(mode='json'), indent=2, sort_keys=True)}\n\n"
        f"User question:\n{request.question}\n\n"
        f"Detected context tickers: {', '.join(tickers) if tickers else 'none'}\n\n"
        "When you have the final answer, post it back to the app with this callback shape. "
        "Replace REPLACE_WITH_FINAL_ANALYSIS with your final JSON-escaped answer:\n\n"
        "curl -s -H 'Content-Type: application/json' "
        "-X POST http://127.0.0.1:8000/api/recommendations/follow-up/codex-result "
        f"--data '{callback_payload}'"
    )


def _openai_missing_followup_response(
    request: RecommendationFollowUpRequest,
    tickers: list[str],
    settings: Settings,
) -> RecommendationFollowUpResponse:
    request_id = uuid.uuid4().hex
    response = RecommendationFollowUpResponse(
        recommendation_key=recommendation_key(request.recommendation),
        question=request.question,
        generated_at=datetime.now(timezone.utc),
        mode="codex_required",
        status="pending_codex",
        answer=(
            "OPENAI_API_KEY is not configured, so Invest OS cannot run this conversational AI analysis in-app. "
            "Use the Codex IDE prompt below to analyze it locally, then post the result back to this thread."
        ),
        context_tickers=tickers,
        follow_up_id=request_id,
        codex_command=_codex_followup_command(request_id, request, tickers),
    )
    _store_recommendation_followup(response, settings)
    return response


def _store_recommendation_followup(response: RecommendationFollowUpResponse, settings: Settings) -> None:
    with connect(settings.data_dir) as conn:
        save_recommendation_followup(conn, response)
        conn.commit()


def load_recommendation_followups(settings: Settings | None = None) -> list[RecommendationFollowUpResponse]:
    settings = settings or get_settings()
    with connect(settings.data_dir) as conn:
        return [
            RecommendationFollowUpResponse.model_validate_json(payload)
            for payload in load_recommendation_followup_payloads(conn)
        ]


def load_recommendation_followup_result(
    request_id: str,
    settings: Settings | None = None,
) -> RecommendationFollowUpResponse | None:
    settings = settings or get_settings()
    with connect(settings.data_dir) as conn:
        payload = load_recommendation_followup_payload(conn, request_id)
    return RecommendationFollowUpResponse.model_validate_json(payload) if payload else None


def submit_recommendation_followup_codex_result(
    request: RecommendationFollowUpCodexResultRequest,
    settings: Settings | None = None,
) -> RecommendationFollowUpResponse | None:
    settings = settings or get_settings()
    answer = request.answer.strip()
    if not answer:
        raise ValueError("Answer cannot be empty.")
    existing = load_recommendation_followup_result(request.request_id, settings)
    if existing is None:
        return None
    response = RecommendationFollowUpResponse(
        recommendation_key=existing.recommendation_key,
        question=existing.question,
        generated_at=datetime.now(timezone.utc),
        mode="codex",
        status="complete",
        answer=answer,
        context_tickers=existing.context_tickers,
        follow_up_id=request.request_id,
    )
    _store_recommendation_followup(response, settings)
    return response


def answer_recommendation_followup(
    snapshot: PortfolioSnapshot,
    request: RecommendationFollowUpRequest,
    settings: Settings | None = None,
) -> RecommendationFollowUpResponse:
    settings = settings or get_settings()
    tickers = _extract_context_tickers(snapshot, request.recommendation, request.question)
    if not settings.openai_api_key:
        return _openai_missing_followup_response(request, tickers, settings)

    context = _followup_context(snapshot, request.recommendation, request.question, tickers)
    response = requests.post(
        OPENAI_RESPONSES_URL,
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.openai_recommendation_model,
            "instructions": (
                f"{_skill_text()}\n\n"
                "Answer the user's follow-up conversationally and concisely. Use the supplied portfolio snapshot, "
                "recommendation, and stock insight context. Give concrete staged actions or decision thresholds when useful. "
                "Do not claim certainty and do not say you placed or will place trades."
            ),
            "input": json.dumps(context, indent=2, sort_keys=True),
        },
        timeout=45,
    )
    response.raise_for_status()
    answer = _extract_text(response.json()).strip()
    if not answer:
        raise ValueError("AI follow-up returned an empty answer.")
    followup = RecommendationFollowUpResponse(
        recommendation_key=recommendation_key(request.recommendation),
        question=request.question,
        generated_at=datetime.now(timezone.utc),
        mode="openai",
        status="complete",
        answer=answer,
        context_tickers=tickers,
        follow_up_id=uuid.uuid4().hex,
    )
    _store_recommendation_followup(followup, settings)
    return followup


def _breakdown_percent(snapshot: PortfolioSnapshot, name: str) -> float:
    for item in snapshot.asset_class_breakdown:
        if item.name.lower() == name.lower():
            return item.percent
    return 0.0


def _breakdown_value(snapshot: PortfolioSnapshot, name: str) -> float:
    for item in snapshot.asset_class_breakdown:
        if item.name.lower() == name.lower():
            return item.value
    return 0.0


def _display_rate_from_base(snapshot: PortfolioSnapshot, currency: str) -> float | None:
    normalized = currency.upper()
    for rate in snapshot.display_rates:
        if rate.currency.upper() == normalized:
            return rate.rate_from_base
    if normalized == snapshot.base_currency.upper():
        return 1.0
    return None


def _convert_to_base(snapshot: PortfolioSnapshot, value: float, currency: str | None) -> float | None:
    if currency is None:
        return None
    normalized = currency.upper()
    if normalized in {"USDT", "USDC", "FDUSD"}:
        normalized = "USD"
    rate_from_base = _display_rate_from_base(snapshot, normalized)
    if rate_from_base is None or rate_from_base <= 0:
        return None
    return value / rate_from_base


def _order_quote(symbol: str) -> str | None:
    for quote in ("USDT", "USDC", "FDUSD", "EUR", "USD", "BTC", "ETH"):
        if symbol.upper().endswith(quote) and len(symbol) > len(quote):
            return quote
    return None


def _open_buy_order_reserve(snapshot: PortfolioSnapshot) -> float:
    total = 0.0
    for order in snapshot.open_orders:
        if order.side != "BUY" or order.limit_price is None:
            continue
        quote_amount = order.limit_price * order.quantity
        converted = _convert_to_base(snapshot, quote_amount, _order_quote(order.symbol))
        if converted is not None:
            total += converted
    return total


def _holding_percent(snapshot: PortfolioSnapshot, value_in_base: float | None) -> float:
    if value_in_base is None or snapshot.total_net_worth <= 0:
        return 0.0
    return value_in_base / snapshot.total_net_worth * 100


def _format_base(snapshot: PortfolioSnapshot, value: float) -> str:
    return f"{value:,.0f} {snapshot.base_currency}"


def _format_percent(value: float) -> str:
    return f"{value:.1f}%"


def _local_recommendations(snapshot: PortfolioSnapshot) -> list[Recommendation]:
    recommendations: list[Recommendation] = []
    net_worth = snapshot.total_net_worth
    top_holding = max(snapshot.holdings, key=lambda item: item.value_in_base or 0, default=None)
    direct_crypto_value = _breakdown_value(snapshot, "crypto")
    direct_crypto_percent = _breakdown_percent(snapshot, "crypto")
    cash_percent = _breakdown_percent(snapshot, "cash")
    open_buy_reserve = _open_buy_order_reserve(snapshot)
    open_buy_reserve_percent = open_buy_reserve / net_worth * 100 if net_worth else 0.0
    mstr_value = sum((holding.value_in_base or 0) for holding in snapshot.holdings if holding.symbol.upper() == "MSTR")
    crypto_linked_value = direct_crypto_value + mstr_value + open_buy_reserve
    crypto_linked_percent = crypto_linked_value / net_worth * 100 if net_worth else direct_crypto_percent
    deployable_cash = sum(
        cash.value_in_base or 0
        for cash in snapshot.cash_balances
        if cash.purpose in {"deployable_cash", "reserved_for_orders"}
    )
    defensive_cash = sum(
        cash.value_in_base or 0
        for cash in snapshot.cash_balances
        if cash.purpose in {"emergency_fund", "monthly_spending"}
    )

    if top_holding and top_holding.value_in_base:
        top_percent = _holding_percent(snapshot, top_holding.value_in_base)
        if top_percent >= 20:
            recommendations.append(
                Recommendation(
                    severity="critical" if top_percent >= 30 else "warning",
                    category="trim_or_exit",
                    title=f"Set {top_holding.symbol} cap before adding risk",
                    detail=(
                        f"{top_holding.symbol} is about {_format_base(snapshot, top_holding.value_in_base)} "
                        f"or {_format_percent(top_percent)} of net worth. Decide whether this is a hold, "
                        "capped exposure, staged trim, or no-new-buy sleeve before funding another concentrated entry."
                    ),
                )
            )

    if crypto_linked_percent >= 10:
        detail = (
            f"Direct crypto is {_format_percent(direct_crypto_percent)} of net worth"
            f" and crypto-linked exposure is about {_format_percent(crypto_linked_percent)}"
            " after counting MSTR and open buy-order reserve."
        )
        if open_buy_reserve > 0:
            detail += f" Open BUY orders reserve roughly {_format_base(snapshot, open_buy_reserve)}."
        detail += " Treat BTC, ETH, MSTR, and reserved BTC orders as one risk sleeve before adding more crypto risk."
        recommendations.append(
            Recommendation(
                severity="warning",
                category="allocation",
                title="Count crypto risk beyond spot holdings",
                detail=detail,
            )
        )

    if open_buy_reserve > 0:
        recommendations.append(
            Recommendation(
                severity="warning",
                category="drawdown_reserve",
                title="Confirm the drawdown-buying reserve",
                detail=(
                    f"Open BUY orders reserve about {_format_base(snapshot, open_buy_reserve)} "
                    f"({_format_percent(open_buy_reserve_percent)} of net worth). If that is intentional crash optionality, "
                    "avoid allocating the same deployable cash elsewhere; if it is stale, review or cancel before new entries."
                ),
            )
        )

    if defensive_cash > 0 and deployable_cash > 0:
        recommendations.append(
            Recommendation(
                severity="warning",
                category="capital_move",
                title="Separate defensive cash from deployable cash",
                detail=(
                    f"Cash is {_format_percent(cash_percent)} of net worth, with about "
                    f"{_format_base(snapshot, defensive_cash)} marked defensive and "
                    f"{_format_base(snapshot, deployable_cash)} deployable. Use broker or exchange deployable cash first; "
                    "move bank cash only if the defensive buffer is explicitly larger than needed."
                ),
            )
        )

    if snapshot.data_warnings or any(status.status != "success" for status in snapshot.source_sync_status):
        recommendations.append(
            Recommendation(
                severity="warning",
                category="allocation",
                title="Resolve data warnings before changing allocation",
                detail=(
                    "The snapshot has source warnings or non-success sync statuses. Refresh or inspect those sources before "
                    "treating these local recommendations as final."
                ),
            )
        )

    recommendations.append(
        Recommendation(
            severity="warning",
            category="theme",
            title="Only research entries after rebalance checks",
            detail=(
                "After concentration, crypto-sleeve, and reserve decisions are clear, research new entries in underrepresented "
                "areas such as healthcare, energy/grid/utilities, industrial automation, defense/cyber resilience, or selective "
                "non-US exposure rather than another tech-like single name."
            ),
        )
    )

    return recommendations[:8]


def load_saved_recommendations(settings: Settings | None = None) -> list[Recommendation]:
    settings = settings or get_settings()
    with connect(settings.data_dir) as conn:
        return [
            Recommendation.model_validate_json(payload)
            for payload in load_recommendation_payloads(conn)
        ]


def load_saved_recommendation_snapshot(settings: Settings | None = None) -> RecommendationSnapshot:
    settings = settings or get_settings()
    with connect(settings.data_dir) as conn:
        return RecommendationSnapshot(
            generated_at=load_recommendations_generated_at(conn),
            recommendations=[
                Recommendation.model_validate_json(payload)
                for payload in load_recommendation_payloads(conn)
            ],
        )


def save_recommendations(recommendations: list[Recommendation], settings: Settings | None = None) -> list[Recommendation]:
    settings = settings or get_settings()
    with connect(settings.data_dir) as conn:
        replace_recommendations(conn, datetime.now(timezone.utc), recommendations)
        conn.commit()
    return recommendations


def generate_recommendations(snapshot: PortfolioSnapshot, settings: Settings | None = None) -> list[Recommendation]:
    settings = settings or get_settings()
    if not settings.openai_api_key:
        return _local_recommendations(snapshot)

    instructions = (
        f"{_skill_text()}\n\n"
        "Return only JSON matching the provided schema. Keep recommendations specific to the supplied snapshot. "
        "Use deterministic opportunity signals when supplied, but do not force a new entry if portfolio fit, "
        "risk, cash, concentration, stale data, or missing data argue for waiting. "
        "Do not use fixed portfolio thresholds unless they are explicitly present in the supplied context."
    )
    response = requests.post(
        OPENAI_RESPONSES_URL,
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.openai_recommendation_model,
            "instructions": instructions,
            "input": (
                f"Portfolio snapshot JSON:\n{_snapshot_payload(snapshot)}\n\n"
                f"Deterministic opportunity context JSON:\n{_deterministic_opportunity_payload()}"
            ),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "portfolio_recommendations",
                    "schema": RECOMMENDATION_SCHEMA,
                    "strict": True,
                }
            },
        },
        timeout=45,
    )
    response.raise_for_status()

    try:
        parsed = RecommendationList.model_validate_json(_extract_text(response.json()))
        return parsed.recommendations
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"AI recommendations response did not match expected format: {exc}") from exc


def generate_and_store(snapshot: PortfolioSnapshot, settings: Settings | None = None) -> list[Recommendation]:
    settings = settings or get_settings()
    recommendations = generate_recommendations(snapshot, settings)
    if recommendations:
        save_recommendations(recommendations, settings)
    return recommendations


def evaluate(_snapshot: PortfolioSnapshot, settings: Settings | None = None) -> list[Recommendation]:
    return load_saved_recommendations(settings)
