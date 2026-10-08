"""Collection gaps that justify another bounded fundamentals-source attempt."""
from __future__ import annotations

from app.entry_engine.open_data_models import OpenDataSnapshot
from app.services.revenue_growth_momentum import calculate_revenue_growth_momentum


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
        rows = {(r.period, r.as_of): r for r in histories.get(name, [])}
        for old in old_rows:
            key = (old.period, old.as_of)
            new = rows.get(key)
            if new is None:
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
            new = metrics.get(name)
            if new is not None and any(term in new.notes.lower() for term in ("not meaningful", "loss-making", "crossed from", "positive 3-year eps")):
                continue
            if old.value is not None and (new is None or new.value is None or old.as_of > new.as_of):
                metrics[name] = old
        groups[group] = metrics
    all_metrics = dict(snapshot.metrics)
    for name, old in previous.metrics.items():
        new = all_metrics.get(name)
        if new is not None and any(term in new.notes.lower() for term in ("not meaningful", "loss-making", "crossed from", "positive 3-year eps")):
            continue
        if old.value is not None and (new is None or new.value is None or old.as_of > new.as_of):
            all_metrics[name] = old
    return snapshot.model_copy(update={**groups, "metrics": all_metrics, "historical_series": histories})
