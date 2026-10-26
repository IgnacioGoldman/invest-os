"""Shared input validation for deterministic financial flags."""
from __future__ import annotations

import math
from datetime import date

from app.services.screening_metrics import (
    BUSINESS_MAX_AGE_DAYS, currencies, day, financial, number, quarter_index,
)


class QuarterlyFlagFacts:
    def __init__(self, snapshot: dict, today: date):
        self.history = snapshot.get('historical_series', {})
        self.rows = sorted(self.history.get('quarterly_fundamentals', []), key=lambda r: r.get('as_of', ''))
        self.latest = self.rows[-1] if self.rows else {}
        self.end = day(self.latest.get('as_of'))
        latest_report = max((r.get('as_of', '') for key in ('quarterly_fundamentals', 'quarterly_revenue')
                             for r in self.history.get(key, [])), default='')
        self.fresh = bool(self.end and 0 <= (today - self.end).days <= BUSINESS_MAX_AGE_DAYS
                          and self.latest.get('as_of') == latest_report)
        classification = f"{snapshot.get('sector') or ''} {snapshot.get('industry') or ''}".strip().lower()
        self.excluded = financial(snapshot) or any(term in classification for term in ('reit', 'real estate investment trust', 'investment fund'))
        self.eligible = bool(classification) and not self.excluded
        self.inputs: list[dict] = []

    def facts(self, count: int, keys: tuple[str, ...]) -> tuple[list[dict], list[dict]] | None:
        if not self.fresh or not self.eligible or len(self.rows) < count:
            return None
        window = self.rows[-count:]
        indices = [quarter_index(r.get('period', '')) for r in window]
        if any(i is None for i in indices) or indices != list(range(indices[-1] - count + 1, indices[-1] + 1)):
            return None
        dates = [day(r.get('as_of')) for r in window]
        if any(d is None for d in dates) or any(not 60 <= (b - a).days <= 120 for a, b in zip(dates, dates[1:])):
            return None
        if any(not 350 <= (dates[i] - dates[i-4]).days <= 380 for i in range(4, len(dates))):
            return None
        evidence, units = [], set()
        for row in window:
            if (sum(r.get('period') == row['period'] for r in self.rows) != 1
                    or sum(r.get('as_of') == row['as_of'] for r in self.rows) != 1):
                return None
            for key in keys:
                m = row.get('metrics', {}).get(key, {})
                sources = m.get('source', '').split('; ')
                if (number(m.get('value')) is None or m.get('as_of') != row['as_of']
                        or m.get('tier') not in {'exact_public_fact', 'computed_from_public_facts'}
                        or not sources or not all(s.startswith(('sec_companyfacts:', 'issuer_statement:', 'yfinance_statement:')) for s in sources)
                        or 'proxy' in (m.get('notes') or '').lower() or len(currencies(m)) != 1):
                    return None
                units.update(currencies(m))
                if key == 'revenue':
                    comparable = [r.get('metrics', {}).get('revenue', {}) for r in self.history.get('quarterly_revenue', [])
                                  if r.get('period') == row['period'] and r.get('as_of') == row['as_of']]
                    if any(number(other.get('value')) is not None and currencies(other) == currencies(m)
                           and not math.isclose(other['value'], m['value'], rel_tol=1e-12, abs_tol=1e-6) for other in comparable):
                        return None
                evidence.append({'period': row['period'], 'as_of': row['as_of'], 'metric': key,
                                 'value': m['value'], 'currency': next(iter(currencies(m))), 'source': m['source']})
        if len(units) != 1:
            return None
        self.inputs.extend(evidence)
        return window, evidence
