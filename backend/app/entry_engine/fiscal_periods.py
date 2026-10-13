"""Resolve SEC fact periods from statement dates, rather than filing-context FY labels."""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any


PERIOD_SCHEMA_VERSION = 1
_ANNUAL_FORMS = ("10-K", "20-F", "40-F")
_ANCHORS = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
            "Revenue", "RevenueFromSaleOfGoods", "NetIncomeLoss", "ProfitLoss")


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def normalize_companyfacts_periods(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("_fiscal_periods_version") == PERIOD_SCHEMA_VERSION:
        return payload
    facts = payload.get("facts", {})
    if not isinstance(facts, dict):
        return {**payload, "_fiscal_periods_version": PERIOD_SCHEMA_VERSION}
    spans: set[tuple[date, date]] = set()
    naming: set[tuple[date, int]] = set()
    for taxonomy in ("us-gaap", "ifrs-full"):
        for concept in _ANCHORS:
            for rows in facts.get(taxonomy, {}).get(concept, {}).get("units", {}).values():
                for row in rows:
                    start, end, filed = (_date(row.get(key)) for key in ("start", "end", "filed"))
                    if (start is None or end is None or not 300 <= (end - start).days <= 400
                            or not str(row.get("form", "")).startswith(_ANNUAL_FORMS)):
                        continue
                    spans.add((start, end))
                    if filed and 0 <= (filed - end).days <= 180 and isinstance(row.get("fy"), int):
                        naming.add((end, row["fy"] - end.year))
    if not spans:
        return {**payload, "_fiscal_periods_version": PERIOD_SCHEMA_VERSION}
    counts = Counter(offset for _, offset in naming)
    offset = min(counts, key=lambda value: (-counts[value], abs(value))) if counts else 0
    ordered = sorted(spans, key=lambda pair: pair[1])

    def identity(end: date) -> tuple[int, int] | None:
        matches = [(start, last) for start, last in ordered if start <= end <= last]
        if matches:
            start, last = matches[-1]
        else:
            # Exact annual spans cover 52/53-week and changed calendars. Only
            # interim periods within one year of a verified span are projected.
            first, previous = ordered[-1] if end > ordered[-1][1] else ordered[0]
            if end > previous and (end - previous).days <= 300:
                start, last = previous + timedelta(days=1), previous + timedelta(days=365)
            elif end < first and (first - end).days <= 300:
                start, last = first - timedelta(days=365), first - timedelta(days=1)
            else:
                return None
        progress, length = (end - start).days + 1, (last - start).days + 1
        quarter = round(4 * progress / length)
        if quarter not in (1, 2, 3, 4) or abs(progress - quarter * length / 4) > 20:
            return None
        return last.year + offset, quarter

    normalized = dict(facts)
    for taxonomy in ("us-gaap", "ifrs-full"):
        concepts = dict(facts.get(taxonomy, {}))
        for concept, data in concepts.items():
            units = {}
            for unit, rows in data.get("units", {}).items():
                new_rows = []
                for row in rows:
                    end, start = _date(row.get("end")), _date(row.get("start"))
                    period = identity(end) if end else None
                    if period:
                        fy, quarter = period
                        annual = (start is not None and 300 <= (end - start).days <= 400) or (
                            start is None and any(end == last for _, last in ordered)
                            and str(row.get("form", "")).startswith(_ANNUAL_FORMS))
                        row = {**row, "fy": fy, "fp": "FY" if annual else f"Q{quarter}"}
                    new_rows.append(row)
                units[unit] = new_rows
            concepts[concept] = {**data, "units": units}
        if taxonomy in facts:
            normalized[taxonomy] = concepts
    return {**payload, "facts": normalized, "_fiscal_periods_version": PERIOD_SCHEMA_VERSION}
