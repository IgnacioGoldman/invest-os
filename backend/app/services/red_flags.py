"""Explainable concern counts from existing quarterly facts; never an AI score."""
from __future__ import annotations

import math
from datetime import date, timedelta

from app.services.screening_metrics import (
    BUSINESS_MAX_AGE_DAYS, currencies, day, financial, number, quarter_index, result,
)

RED_FLAG_VERSION = 1
MAX_RED_FLAGS = 3


def build_red_flag_count(snapshot: dict, today: date) -> dict:
    history = snapshot.get('historical_series', {})
    rows = sorted(history.get('quarterly_fundamentals', []), key=lambda r: r.get('as_of', ''))
    latest = rows[-1] if rows else {}
    end = day(latest.get('as_of'))
    latest_report = max((r.get('as_of', '') for key in ('quarterly_fundamentals', 'quarterly_revenue')
                         for r in history.get(key, [])), default='')
    fresh = bool(end and 0 <= (today - end).days <= BUSINESS_MAX_AGE_DAYS
                 and latest.get('as_of') == latest_report)
    classification = f"{snapshot.get('sector') or ''} {snapshot.get('industry') or ''}".strip().lower()
    excluded = financial(snapshot) or any(term in classification for term in ('reit', 'real estate investment trust', 'investment fund'))
    eligible = bool(classification) and not excluded
    inputs: list[dict] = []

    def lower(a: float, b: float) -> bool:
        return a < b and not math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-10)

    def facts(count: int, keys: tuple[str, ...]) -> tuple[list[dict], list[dict]] | None:
        if not fresh or not eligible or len(rows) < count:
            return None
        window = rows[-count:]
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
            if (sum(r.get('period') == row['period'] for r in rows) != 1
                    or sum(r.get('as_of') == row['as_of'] for r in rows) != 1):
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
                    comparable = [r.get('metrics', {}).get('revenue', {}) for r in history.get('quarterly_revenue', [])
                                  if r.get('period') == row['period'] and r.get('as_of') == row['as_of']]
                    if any(number(other.get('value')) is not None and currencies(other) == currencies(m)
                           and not math.isclose(other['value'], m['value'], rel_tol=1e-12, abs_tol=1e-6) for other in comparable):
                        return None
                evidence.append({'period': row['period'], 'as_of': row['as_of'], 'metric': key,
                                 'value': m['value'], 'currency': next(iter(currencies(m))), 'source': m['source']})
        if len(units) != 1:
            return None
        inputs.extend(evidence)
        return window, evidence

    def outcome(key: str, title: str, formula: str, data, predicate, describe) -> dict:
        if data is None:
            return {'id': key, 'title': title, 'state': 'unassessed', 'formula': formula,
                    'reason': 'Comparable, sourced quarterly inputs are missing, invalid or stale.', 'evidence': []}
        window, evidence = data
        triggered, values = predicate(window)
        return {'id': key, 'title': title, 'state': 'flagged' if triggered else 'clear',
                'formula': formula, 'reason': describe(values), 'evidence': evidence, 'values': values}

    def cash_conversion(window):
        values = []
        for four in (window[:4], window[1:]):
            ni = sum(r['metrics']['net_income']['value'] for r in four)
            ocf = sum(r['metrics']['operating_cash_flow']['value'] for r in four)
            values.append({'period': f"TTM ended {four[-1]['as_of']}", 'net_income': ni, 'operating_cash_flow': ocf})
        return all(v['net_income'] > 0 and lower(v['operating_cash_flow'], v['net_income']) for v in values), values

    def negative_fcf(window):
        values = []
        for four in (window[:4], window[4:]):
            ocf = sum(r['metrics']['operating_cash_flow']['value'] for r in four)
            capex = sum(abs(r['metrics']['capex']['value']) for r in four)
            values.append({'period': f"TTM ended {four[-1]['as_of']}", 'operating_cash_flow': ocf, 'capex': capex, 'free_cash_flow': ocf-capex})
        return all(lower(v['free_cash_flow'], 0) for v in values), values

    conversion = outcome('cash_conversion', 'Persistent earnings-to-cash gap',
        'TTM net income > 0 and TTM operating cash flow < TTM net income at both of the latest two quarter ends',
        facts(5, ('net_income', 'operating_cash_flow')), cash_conversion,
        lambda v: 'Operating cash flow compared with positive reported earnings over two consecutive rolling TTM periods; working capital and non-cash items require context.')
    fcf = outcome('negative_fcf', 'Persistent negative free cash flow',
        'Sum(operating cash flow − abs(capex)) < 0 in each of the latest two non-overlapping four-quarter periods',
        facts(8, ('operating_cash_flow', 'capex')), negative_fcf,
        lambda v: 'Free cash flow assessed over two non-overlapping years; investment spending can explain negative cash flow.')

    def margin_decline(window):
        values = []
        for current, previous in zip(window[-2:], window[:2]):
            current_margin = current['metrics']['operating_income']['value'] / current['metrics']['revenue']['value'] * 100
            previous_margin = previous['metrics']['operating_income']['value'] / previous['metrics']['revenue']['value'] * 100
            values.append({'period': current['period'], 'comparison_period': previous['period'],
                           'operating_margin': current_margin, 'previous_operating_margin': previous_margin,
                           'change_pp': current_margin-previous_margin})
        return all(lower(v['change_pp'], 0) for v in values), values

    def operating_data(count):
        data = facts(count, ('operating_income', 'revenue'))
        if data and any(r['metrics']['revenue']['value'] <= 0
                        or abs(r['metrics']['operating_income']['value'] / r['metrics']['revenue']['value']) > 1 for r in data[0]):
            return None
        return data

    decline = outcome('margin_decline', 'Consecutive margin deterioration',
        'Operating income / revenue is lower than the equivalent prior-year quarter in both latest quarters',
        operating_data(6), margin_decline,
        lambda v: 'Two consecutive year-over-year operating-margin comparisons; restructuring, investment and business mix can affect margins.')
    losses = outcome('operating_losses', 'Consecutive operating losses',
        'Operating income < 0 in both latest quarters', facts(2, ('operating_income',)),
        lambda w: (all(lower(r['metrics']['operating_income']['value'], 0) for r in w),
                   [{'period': r['period'], 'operating_income': r['metrics']['operating_income']['value']} for r in w]),
        lambda v: 'Operating losses in consecutive quarters are a potential concern, including for businesses investing for growth.')
    equity = outcome('negative_equity', 'Negative book equity', 'Latest reported quarter-end stockholders’ equity < 0',
        facts(1, ('equity',)),
        lambda w: (lower(w[-1]['metrics']['equity']['value'], 0), {'equity': w[-1]['metrics']['equity']['value']}),
        lambda v: 'Negative reported book equity; buybacks, distributions and accounting history can explain the deficit. This is not an insolvency finding.')

    def group(key, title, branches):
        flagged = [b for b in branches if b['state'] == 'flagged']
        determined = bool(flagged) or all(b['state'] == 'clear' for b in branches)
        state = 'flagged' if flagged else 'clear' if determined else 'unassessed'
        reason = None
        if not eligible:
            state = 'not_applicable' if excluded else 'unassessed'
            reason = 'These rules are not calibrated for financial businesses, REITs or investment funds.' if excluded else 'Sector and industry classification are required.'
        elif not fresh:
            reason = 'A current comparable quarterly report is required (maximum age 140 days).'
        return {'id': key, 'title': title, 'state': state, 'reason': reason,
                'triggered_rules': [b['id'] for b in flagged], 'checks': branches}

    checks = [group('cash_generation', 'Cash-generation concerns', [conversion, fcf]),
              group('operating_performance', 'Operating profitability pressure', [decline, losses]),
              group('balance_sheet', 'Negative book equity', [equity])]
    flags = [c for c in checks if c['state'] == 'flagged']
    assessed = sum(c['state'] in {'clear', 'flagged'} for c in checks)
    applicable = sum(c['state'] != 'not_applicable' for c in checks)
    complete = eligible and fresh and assessed == applicable == MAX_RED_FLAGS
    count = len(flags)
    status = 'Complete assessment' if complete else 'Partial assessment' if assessed else 'Not assessed'
    source = '; '.join(dict.fromkeys(i['source'] for i in inputs)) or 'unavailable'
    return result({'source': source, 'as_of': latest.get('as_of', ''), 'tier': 'computed_from_public_facts'},
        value=count if complete else None, period=latest.get('period', ''),
        formula='One point per distinct flagged concern group; overlapping rules within a group count once.',
        status=status, validated=complete,
        valid_until=(end + timedelta(days=BUSINESS_MAX_AGE_DAYS)).isoformat() if end else None,
        assessment_version=RED_FLAG_VERSION, max_count=MAX_RED_FLAGS, observed_count=count,
        coverage={'assessed': assessed, 'applicable': applicable, 'total': MAX_RED_FLAGS, 'complete': complete},
        flags=flags, checks=checks,
        notes='Potential concerns, not an investment-quality rating. Incomplete assessments have no numeric screening value.',
        warnings=[] if complete else ['Assessment incomplete or not applicable; do not interpret this as zero red flags.'])
