"""Recalculate current valuations from persisted inputs, without fetching facts."""
from __future__ import annotations

from typing import Callable

from app.entry_engine.open_data_models import LatestPrice, OpenDataMetric, OpenDataSnapshot
from app.entry_engine.open_data_metrics import (
    _computed_metric, _has_statement_currency_mismatch, _is_currency_bridge_unavailable,
    _source_statement_currencies, _unavailable, _valuation_input_unavailable,
)


VALUATION_ALIASES = {
    "pe": ("pe", "pe_ttm"),
    "price_to_sales": ("price_to_sales", "price_to_sales_ttm"),
    "fcf_yield": ("fcf_yield",),
    "forward_pe": ("forward_pe",),
    "peg": ("peg", "peg_proxy"),
    "ev_to_ebitda": ("ev_to_ebitda", "ev_to_ebitda_proxy"),
}


def saved_valuation_inputs(snapshot: OpenDataSnapshot) -> dict[str, OpenDataMetric]:
    """Upgrade older snapshots locally; never guess an unverified currency bridge."""
    if snapshot.valuation_inputs:
        return dict(snapshot.valuation_inputs)
    inputs: dict[str, OpenDataMetric] = {}
    old_price = snapshot.price_opportunity.get("current_price") or snapshot.metrics.get("current_price")
    cap = snapshot.metrics.get("market_cap")
    as_of = old_price.as_of if old_price else snapshot.generated_at.date().isoformat()
    currency = snapshot.price_currency or ("SEK" if snapshot.ticker.endswith(".ST") else "USD")

    def derived(
        key: str, left: OpenDataMetric | None, right: OpenDataMetric | None,
        compute: Callable[[float, float], float],
    ) -> OpenDataMetric:
        return _computed_metric(
            key, left.value if left else None, right.value if right else None, compute,
            source=f"{left.source if left else 'unavailable'}; {right.source if right else 'unavailable'}",
            as_of=as_of, notes="Input recovered from the previous stored valuation and its reference price.",
            fallback_as_of=as_of, tier="proxy_estimate",
        )

    inputs["listing_shares"] = derived("listing_shares", cap, old_price, lambda value, quote: value / quote)
    for key, raw_key, ratio_key, compute in (
        ("revenue", "revenue_ttm", "price_to_sales", lambda cap, ratio: cap / ratio),
        ("net_income", "net_income_ttm", "pe", lambda cap, ratio: cap / ratio),
        ("free_cash_flow", "free_cash_flow_ttm", "fcf_yield", lambda cap, ratio: cap * ratio / 100),
    ):
        raw = snapshot.metrics.get(raw_key)
        if raw is not None and not _has_statement_currency_mismatch(currency, raw):
            inputs[key] = raw
        else:
            inputs[key] = derived(key, cap, snapshot.valuation.get(ratio_key), compute)

    # Existing cross-currency ratios encode the conversion actually used. It
    # is safe to recover that rate only for the same known statement currency.
    raw_income = snapshot.metrics.get("net_income_ttm")
    income = inputs["net_income"]
    for key in ("debt", "cash"):
        raw = snapshot.metrics.get(key) or snapshot.business_health.get(key)
        if raw is None:
            inputs[key] = _unavailable(key, "Saved balance-sheet input was unavailable.", as_of)
        elif not _has_statement_currency_mismatch(currency, raw):
            inputs[key] = raw
        else:
            units = _source_statement_currencies(raw.source)
            if (len(units) == 1 and raw_income is not None
                    and units == _source_statement_currencies(raw_income.source)
                    and raw_income.value not in (None, 0) and income.value is not None
                    and income.value / raw_income.value > 0):
                rate = income.value / raw_income.value
                inputs[key] = raw.model_copy(update={
                    "value": raw.value * rate if raw.value is not None else None,
                    "source": f"{raw.source}; {income.source}",
                    "notes": f"{raw.notes} Converted using the FX bridge recovered from the saved P/E.",
                })
            else:
                inputs[key] = _unavailable(key, "Saved currency bridge was unavailable; a new fundamentals refresh is required.", as_of)

    ev = snapshot.metrics.get("enterprise_value_proxy")
    if ev is None:
        ev = _computed_metric(
            "enterprise_value_proxy", cap.value if cap else None, inputs["debt"].value,
            lambda value, debt: value + debt - (inputs["cash"].value or 0),
            source="persisted_market_cap_and_balance_sheet", as_of=as_of,
            notes="Previous enterprise value recovered from saved market cap, debt and cash.",
            fallback_as_of=as_of, tier="proxy_estimate",
        )
        if inputs["cash"].value is None and "currency bridge" in inputs["cash"].notes:
            ev = _unavailable("enterprise_value_proxy", "Saved currency bridge was unavailable.", as_of)
    inputs["ebitda"] = derived("ebitda", ev, snapshot.valuation.get("ev_to_ebitda"), lambda value, ratio: value / ratio)
    for key, multiple in (
        ("forward_eps_public", snapshot.metrics.get("forward_pe_public_estimate")),
        ("forward_eps_proxy", snapshot.metrics.get("forward_pe_proxy")),
    ):
        inputs[key] = derived(key, old_price, multiple, lambda quote, ratio: quote / ratio)
    # Some old exports carry only the displayed forward multiple.
    if not any(inputs[key].value is not None for key in ("forward_eps_public", "forward_eps_proxy")):
        inputs["forward_eps_public"] = derived(
            "forward_eps_public", old_price, snapshot.valuation.get("forward_pe"), lambda quote, ratio: quote / ratio,
        )
    return inputs


def reprice_valuation(
    snapshot: OpenDataSnapshot,
    price: LatestPrice,
    *,
    forward_eps: OpenDataMetric | None = None,
) -> OpenDataSnapshot:
    inputs = saved_valuation_inputs(snapshot)
    if snapshot.price_currency and snapshot.price_currency != price.currency:
        raise ValueError(f"{snapshot.ticker}: saved valuation currency differs from the price currency.")
    as_of = price.as_of

    def input_metric(key: str) -> OpenDataMetric:
        return inputs.get(key) or _unavailable(key, "Saved valuation input was unavailable.", as_of)

    shares = input_metric("listing_shares")
    cap = _computed_metric(
        "market_cap", price.price, shares.value, lambda quote, count: quote * count,
        source=f"{price.source}; {shares.source}", as_of=as_of,
        notes="Current price multiplied by saved listing share count, including its ADR adjustment.",
        fallback_as_of=as_of, tier=shares.tier if shares.value is not None else "computed_from_public_facts",
    )

    def ratio(key: str, denominator_key: str, *, inverse: bool = False) -> OpenDataMetric:
        denominator = input_metric(denominator_key)
        if _is_currency_bridge_unavailable(denominator):
            return _valuation_input_unavailable(key, denominator, as_of)
        return _computed_metric(
            key, denominator.value if inverse else cap.value,
            cap.value if inverse else denominator.value,
            (lambda value, cap: value / cap * 100) if inverse else (lambda cap, value: cap / value),
            source=f"{cap.source}; {denominator.source}", as_of=as_of,
            notes=f"Recalculated using current market cap and saved {denominator_key} in the listing currency.",
            fallback_as_of=as_of,
        )

    valuation = {
        "pe": ratio("pe_ttm", "net_income"),
        "price_to_sales": ratio("price_to_sales_ttm", "revenue"),
        "fcf_yield": ratio("fcf_yield", "free_cash_flow", inverse=True),
    }
    debt, cash = input_metric("debt"), input_metric("cash")
    ev = _computed_metric(
        "enterprise_value_proxy", cap.value, debt.value,
        lambda value, debt: value + debt - (cash.value or 0),
        source=f"{cap.source}; {debt.source}; {cash.source}", as_of=as_of,
        notes="Current market cap plus saved debt minus saved cash in the listing currency.",
        fallback_as_of=as_of, tier="proxy_estimate",
    )
    for balance in (debt, cash):
        if _is_currency_bridge_unavailable(balance) or ("currency bridge" in balance.notes.lower() and balance.value is None):
            ev = _unavailable("enterprise_value_proxy", balance.notes, as_of)
    ebitda = input_metric("ebitda")
    valuation["ev_to_ebitda"] = _computed_metric(
        "ev_to_ebitda", ev.value, ebitda.value, lambda value, earnings: value / earnings,
        source=f"{ev.source}; {ebitda.source}", as_of=as_of,
        notes="Current enterprise value divided by saved EBITDA in the listing currency.",
        fallback_as_of=as_of, tier="proxy_estimate",
    )
    growth = snapshot.business_health.get("eps_cagr_3y") or snapshot.metrics.get("eps_cagr_3y")
    valuation["peg"] = (
        _unavailable("peg", "Positive 3-year EPS CAGR was unavailable; PEG is not meaningful.", as_of)
        if growth is None or growth.value is None or growth.value <= 0 else
        _computed_metric(
            "peg", valuation["pe"].value, growth.value, lambda multiple, growth: multiple / growth,
            source=f"{valuation['pe'].source}; {growth.source}", as_of=as_of,
            notes="Trailing P/E divided by saved 3-year EPS CAGR percentage.",
            fallback_as_of=as_of, tier="proxy_estimate",
        )
    )
    if forward_eps is not None and forward_eps.value is not None:
        inputs["forward_eps_public"] = forward_eps
    # Rebuild the growth proxy when financial data changes, using listing
    # shares (already ADR adjusted), not an old earnings denominator.
    income = input_metric("net_income")
    if (income.value is not None and income.value > 0 and shares.value is not None and shares.value > 0
            and growth is not None and growth.value is not None and growth.value > -100):
        inputs["forward_eps_proxy"] = _computed_metric(
            "forward_eps_proxy", income.value, shares.value,
            lambda earnings, count: earnings / count * (1 + growth.value / 100),
            source=f"{income.source}; {shares.source}; {growth.source}", as_of=income.as_of,
            notes="Saved trailing EPS per listed share grown by 3-year EPS CAGR; not analyst consensus.",
            fallback_as_of=as_of, tier="proxy_estimate",
        )
    else:
        inputs["forward_eps_proxy"] = _unavailable("forward_eps_proxy", "Positive trailing EPS and a usable EPS growth rate were unavailable.", as_of)
    proxy = _computed_metric(
        "forward_pe_proxy", price.price, input_metric("forward_eps_proxy").value,
        lambda quote, eps: quote / eps, source=f"{price.source}; {input_metric('forward_eps_proxy').source}",
        as_of=as_of, notes="Current price divided by the saved historical-growth EPS proxy.",
        fallback_as_of=as_of, tier="proxy_estimate",
    )
    if input_metric("forward_eps_proxy").value is None:
        proxy = _unavailable(
            "forward_pe_proxy",
            "Positive 3-year EPS CAGR or trailing EPS was unavailable; forward P/E proxy is not meaningful.",
            as_of,
        )
    public_eps = inputs.get("forward_eps_public")
    public = _computed_metric(
        "forward_pe_public_estimate", price.price, public_eps.value if public_eps else None,
        lambda quote, eps: quote / eps, source=f"{price.source}; {public_eps.source if public_eps else 'unavailable'}",
        as_of=as_of, notes="Current price divided by saved expected EPS from Yahoo or its implied forward P/E input; not an SEC fact.",
        fallback_as_of=as_of, tier="proxy_estimate",
    )
    # Public multiples and historical-growth proxies remain raw research data.
    # Only an explicitly dated EPS forecast can supply the displayed estimate.
    from app.services.screening_metrics import build_screening_metrics
    checked = build_screening_metrics({**snapshot.model_dump(mode="json"),
        "price_currency": price.currency,
        "price_opportunity": {**{k: v.model_dump(mode="json") for k, v in snapshot.price_opportunity.items()},
            "current_price": {"value": price.price, "source": price.source, "as_of": price.as_of}},
        "valuation_inputs": {k: v.model_dump(mode="json") for k, v in inputs.items()}})
    valuation["forward_pe"] = OpenDataMetric.model_validate(checked["metrics"]["forward_pe"])
    # Preserve deliberate exclusions instead of reviving them on a price update.
    for key, previous in snapshot.valuation.items():
        if previous.value is None and "not meaningful" in previous.notes.lower() and key in {"fcf_yield", "ev_to_ebitda"}:
            valuation[key] = previous
    metrics = {**snapshot.metrics, "market_cap": cap, "enterprise_value_proxy": ev,
               "forward_pe_proxy": proxy, "forward_pe_public_estimate": public}
    for key, aliases in VALUATION_ALIASES.items():
        for alias in aliases:
            metrics[alias] = valuation[key]
    return snapshot.model_copy(update={
        "valuation": valuation, "metrics": metrics,
        "valuation_inputs": inputs, "price_currency": price.currency, "screening": checked,
    })
