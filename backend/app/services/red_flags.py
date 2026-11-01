"""Explainable concern counts from existing quarterly facts; never an AI score."""
from __future__ import annotations

import math
from datetime import date, timedelta

from app.services.screening_metrics import (
    BUSINESS_MAX_AGE_DAYS, day, result,
)

RED_FLAG_VERSION = 2
MAX_RED_FLAGS = 4


def build_red_flag_count(snapshot: dict, today: date, valuation: dict | None = None) -> dict:
    from app.services.financial_flag_facts import QuarterlyFlagFacts
    context = QuarterlyFlagFacts(snapshot, today)
    latest, end = context.latest, context.end
    fresh, eligible, excluded = context.fresh, context.eligible, context.excluded
    inputs, facts = context.inputs, context.facts

    def lower(a: float, b: float) -> bool:
        return a < b and not math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-10)

    def outcome(key: str, title: str, formula: str, data, predicate, describe) -> dict:
        if data is None:
            return {'id': key, 'title': title, 'state': 'unassessed', 'formula': formula,
                    'reason': context.failure or 'Comparable, sourced quarterly inputs are missing, invalid or stale.', 'evidence': []}
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
            context.failure = 'Reported operating margin is outside the validated range (−100% to 100%) in a required quarter.'
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

    from app.services.valuation_metrics import reported_valuation_metrics, PRICE_TO_SALES_LIMIT, FCF_YIELD_LIMIT, MARKET_MAX_AGE_DAYS
    valuation = valuation if valuation is not None else reported_valuation_metrics(snapshot, today)
    values = valuation['values'] if fresh and eligible else None
    expensive = {'id':'priced_for_perfection','title':'Priced for Perfection',
        'state': 'flagged' if values and values['price_to_sales'] > PRICE_TO_SALES_LIMIT and values['fcf_yield_fraction'] < FCF_YIELD_LIMIT else 'clear' if values else 'unassessed',
        'formula': 'Market cap / TTM revenue > 10 AND TTM (operating cash flow − abs(capex)) / same market cap < 0.02',
        'reason': 'Stock valuation is unusually high relative to current revenue and free cash flow generation. Initial screening heuristics, not universal valuation standards.' if values else 'Four aligned revenue/cash-flow quarters and a fresh, compatible market capitalization are required.',
        'evidence':valuation['evidence'] if values else [], 'values':values}
    if values and valuation['price_to_sales']['warnings']:
        expensive['reason'] += ' ' + ' '.join(valuation['price_to_sales']['warnings'])
    if values:
        inputs.extend(valuation['evidence'])
    checks = [group('cash_generation', 'Cash-generation concerns', [conversion, fcf]),
              group('operating_performance', 'Operating profitability pressure', [decline, losses]),
              group('balance_sheet', 'Negative book equity', [equity]),
              {**group('priced_for_perfection', 'Priced for Perfection', [expensive]), 'category':'Valuation'}]
    flags = [c for c in checks if c['state'] == 'flagged']
    assessed = sum(c['state'] in {'clear', 'flagged'} for c in checks)
    applicable = sum(c['state'] != 'not_applicable' for c in checks)
    complete = eligible and fresh and assessed == applicable == MAX_RED_FLAGS
    count = len(flags)
    status = 'Complete assessment' if complete else 'Partial assessment' if assessed else 'Not assessed'
    financial_deadline = (end + timedelta(days=BUSINESS_MAX_AGE_DAYS)).isoformat() if end else None
    market_day = day(valuation.get('price_as_of'))
    deadline = min(financial_deadline, (market_day + timedelta(days=MARKET_MAX_AGE_DAYS)).isoformat()) if complete and market_day and financial_deadline else financial_deadline
    source = '; '.join(dict.fromkeys(i['source'] for i in inputs)) or 'unavailable'
    return result({'source': source, 'as_of': latest.get('as_of', ''), 'tier': 'computed_from_public_facts'},
        value=count if complete else None, period=latest.get('period', ''),
        formula='One point per distinct flagged concern group; overlapping rules within a group count once.',
        status=status, validated=complete,
        valid_until=deadline, price_as_of=valuation.get('price_as_of'),
        assessment_version=RED_FLAG_VERSION, max_count=MAX_RED_FLAGS, observed_count=count,
        coverage={'assessed': assessed, 'applicable': applicable, 'total': MAX_RED_FLAGS, 'complete': complete},
        flags=flags, checks=checks,
        notes='Potential concerns, not an investment-quality rating. Incomplete assessments have no numeric screening value.',
        warnings=[] if complete else ['Assessment incomplete or not applicable; do not interpret this as zero red flags.'])
