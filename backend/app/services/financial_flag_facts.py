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
        self.failure = ''

    def facts(self, count: int, keys: tuple[str, ...]) -> tuple[list[dict], list[dict]] | None:
        self.failure = ''
        def unavailable(reason):
            self.failure = reason
            return None
        if not self.eligible:
            return unavailable('These rules are outside the company’s sector scope.' if self.excluded
                               else 'Sector and industry classification are required.')
        if not self.fresh:
            return unavailable('A current comparable quarterly report is required (maximum age 140 days).')
        if len(self.rows) < count:
            return unavailable(f'{count} comparable quarterly reports are required; only {len(self.rows)} are available.')
        window = self.rows[-count:]
        indices = [quarter_index(r.get('period', '')) for r in window]
        if any(i is None for i in indices) or indices != list(range(indices[-1] - count + 1, indices[-1] + 1)):
            return unavailable(f'The latest {count} reports do not form consecutive fiscal quarters.')
        dates = [day(r.get('as_of')) for r in window]
        if any(d is None for d in dates) or any(not 60 <= (b - a).days <= 120 for a, b in zip(dates, dates[1:])):
            return unavailable('Quarter-end dates are invalid or inconsistent with consecutive quarters.')
        if any(not 350 <= (dates[i] - dates[i-4]).days <= 380 for i in range(4, len(dates))):
            return unavailable('Prior-year comparison dates are not one reporting year apart.')
        evidence, units = [], set()
        for row in window:
            if (sum(r.get('period') == row['period'] for r in self.rows) != 1
                    or sum(r.get('as_of') == row['as_of'] for r in self.rows) != 1):
                return unavailable(f'{row["period"]} ({row["as_of"]}) has duplicate fiscal periods or statement dates.')
            for key in keys:
                m = row.get('metrics', {}).get(key, {})
                sources = m.get('source', '').split('; ')
                label = f'{row["period"]} ({row["as_of"]}): {key.replace("_", " ")}'
                if number(m.get('value')) is None:
                    return unavailable(f'{label} is unavailable.')
                if m.get('as_of') != row['as_of']:
                    return unavailable(f'{label} is dated {m.get("as_of") or "unknown"}, so it cannot supply this quarter.')
                if m.get('tier') not in {'exact_public_fact', 'computed_from_public_facts'} or 'proxy' in (m.get('notes') or '').lower():
                    return unavailable(f'{label} is a proxy or lacks a validated reported value.')
                if not sources or not all(s.startswith(('sec_companyfacts:', 'issuer_statement:', 'yfinance_statement:')) for s in sources):
                    return unavailable(f'{label} lacks a supported public statement source.')
                if len(currencies(m)) != 1:
                    return unavailable(f'{label} lacks a single verifiable reporting currency.')
                units.update(currencies(m))
                if key == 'revenue':
                    comparable = [r.get('metrics', {}).get('revenue', {}) for r in self.history.get('quarterly_revenue', [])
                                  if r.get('period') == row['period'] and r.get('as_of') == row['as_of']]
                    if any(number(other.get('value')) is not None and currencies(other) == currencies(m)
                           and not math.isclose(other['value'], m['value'], rel_tol=1e-12, abs_tol=1e-6) for other in comparable):
                        return unavailable(f'{label} conflicts with the saved quarterly revenue series.')
                evidence.append({'period': row['period'], 'as_of': row['as_of'], 'metric': key,
                                 'value': m['value'], 'currency': next(iter(currencies(m))), 'source': m['source']})
        if len(units) != 1:
            return unavailable('Required quarterly inputs use different reporting currencies.')
        self.inputs.extend(evidence)
        return window, evidence
