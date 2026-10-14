"""Collection gaps that justify another bounded fundamentals-source attempt."""
from __future__ import annotations

from app.entry_engine.open_data_models import OpenDataSnapshot
from app.entry_engine.open_data_metrics import backfill_fcf_margin_metric
from app.services.revenue_growth_momentum import calculate_revenue_growth_momentum


FCF_BUNDLE_KEYS = (
    "revenue_ttm", "operating_cash_flow_ttm", "capex_ttm", "free_cash_flow_ttm",
    "fcf_margin", "fcf_margin_ttm",
)


def _complete_fcf_bundle(snapshot: OpenDataSnapshot) -> bool:
    inputs = [snapshot.metrics.get(key) for key in FCF_BUNDLE_KEYS[:4]]
    return (
        all(metric is not None and metric.value is not None for metric in inputs)
        and len({metric.as_of for metric in inputs if metric is not None}) == 1
    )


def fundamental_gap_reasons(snapshot: OpenDataSnapshot, *, include_history: bool = True) -> list[str]:
    reasons = []
    for group_name in ("business_health", "valuation"):
        for key, metric in getattr(snapshot, group_name).items():
            if not include_history and key in {"revenue_cagr_3y", "eps_cagr_3y", "peg"}:
                continue
            if key == "eps_growth_yoy" or metric.value is not None:
                continue
            note = metric.notes.lower()
            if any(term in note for term in ("not meaningful", "loss-making", "positive 3-year eps", "positive eps", "crossed from")):
                continue
            reasons.append(f"{group_name}.{key}")
    if include_history and calculate_revenue_growth_momentum(snapshot.model_dump(mode="json"))["label"] == "Unclear":
        reasons.append("historical_series.latest_six_revenue_growth_quarters")
    return reasons


def retain_verified_history(snapshot: OpenDataSnapshot, previous: OpenDataSnapshot | None) -> OpenDataSnapshot:
    """A thin or unavailable source must not erase already persisted facts."""
    if previous is None:
        return snapshot
    histories = dict(snapshot.historical_series)
    for name, old_rows in previous.historical_series.items():
        corrected_dates = {row.as_of for row in histories.get(name, [])}
        rows = {(r.period, r.as_of): r for r in histories.get(name, [])}
        for old in old_rows:
            key = (old.period, old.as_of)
            new = rows.get(key)
            if new is None:
                if name in {"quarterly_revenue", "quarterly_fundamentals"} and old.as_of in corrected_dates:
                    # A fresh canonical fiscal label supersedes an older label
                    # for the same statement date; retaining both creates gaps.
                    continue
                rows[key] = old
            else:
                metrics = dict(new.metrics)
                for metric_name, metric in old.metrics.items():
                    if metric.value is not None and (metric_name not in metrics or metrics[metric_name].value is None):
                        metrics[metric_name] = metric
                rows[key] = new.model_copy(update={"metrics": metrics})
        histories[name] = sorted(rows.values(), key=lambda r: (r.as_of, r.period))
    groups = {}
    for group in ("business_health", "valuation"):
        metrics = dict(getattr(snapshot, group))
        for name, old in getattr(previous, group).items():
            if group == "business_health" and name == "fcf_margin":
                continue
            new = metrics.get(name)
            if new is not None and any(term in new.notes.lower() for term in ("not meaningful", "loss-making", "crossed from", "positive 3-year eps")):
                continue
            if old.value is not None and (new is None or new.value is None or old.as_of > new.as_of):
                metrics[name] = old
        groups[group] = metrics
    all_metrics = dict(snapshot.metrics)
    for name, old in previous.metrics.items():
        if name in FCF_BUNDLE_KEYS:
            continue
        new = all_metrics.get(name)
        if new is not None and any(term in new.notes.lower() for term in ("not meaningful", "loss-making", "crossed from", "positive 3-year eps")):
            continue
        if old.value is not None and (new is None or new.value is None or old.as_of > new.as_of):
            all_metrics[name] = old
    # Related TTM inputs must survive an outage as a complete calculation,
    # rather than independently restoring newer-looking values from old data.
    selected = snapshot
    if _complete_fcf_bundle(previous) and (
        not _complete_fcf_bundle(snapshot)
        or previous.metrics["revenue_ttm"].as_of > snapshot.metrics["revenue_ttm"].as_of
    ):
        selected = previous
    for key in FCF_BUNDLE_KEYS:
        if key in selected.metrics:
            all_metrics[key] = selected.metrics[key]
        else:
            all_metrics.pop(key, None)
    groups["business_health"].pop("fcf_margin", None)
    all_metrics.pop("fcf_margin", None)
    all_metrics.pop("fcf_margin_ttm", None)

    # Retained history can contain a newer quarter than a thin current source.
    # Use its actual dated growth fact for both the card and flattened alias.
    for row in sorted(histories.get("quarterly_revenue", []), key=lambda r: r.as_of, reverse=True):
        growth = row.metrics.get("revenue_growth_yoy")
        if growth is not None and growth.value is not None:
            groups["business_health"]["revenue_growth_yoy"] = growth
            all_metrics["revenue_growth_yoy"] = growth
            break
    # A retained financial input must keep its matching valuation denominator
    # (including the original currency conversion), rather than a thin new one.
    from app.entry_engine.valuation_refresh import saved_valuation_inputs
    valuation_inputs = saved_valuation_inputs(snapshot)
    old_inputs = saved_valuation_inputs(previous)
    for key, raw_key in {
        "revenue": "revenue_ttm", "net_income": "net_income_ttm",
        "free_cash_flow": "free_cash_flow_ttm", "ebitda": "ebitda_proxy",
        "debt": "debt", "cash": "cash", "listing_shares": "shares_diluted",
    }.items():
        raw = all_metrics.get(raw_key)
        if (raw is not None and raw == previous.metrics.get(raw_key)
                and raw != snapshot.metrics.get(raw_key) and key in old_inputs):
            valuation_inputs[key] = old_inputs[key]
    for key in ("forward_eps_public",):
        if (key not in valuation_inputs or valuation_inputs[key].value is None) and key in old_inputs:
            valuation_inputs[key] = old_inputs[key]
    result = snapshot.model_copy(update={
        **groups, "metrics": all_metrics, "historical_series": histories, "valuation_inputs": valuation_inputs,
    })
    result = backfill_fcf_margin_metric(result)
    if "fcf_margin" not in result.business_health:
        unavailable = selected.business_health.get("fcf_margin")
        if unavailable is not None and unavailable.value is None:
            result = result.model_copy(update={
                "business_health": {**result.business_health, "fcf_margin": unavailable},
                "metrics": {**result.metrics, "fcf_margin_ttm": unavailable},
            })
    if "fcf_margin" in result.business_health:
        result = result.model_copy(update={"metrics": {**result.metrics, "fcf_margin": result.business_health["fcf_margin"]}})
    return result
