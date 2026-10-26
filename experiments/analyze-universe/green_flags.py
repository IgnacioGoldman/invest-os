"""Three explainable positive financial patterns, counted without weighting."""
from __future__ import annotations

import math
from datetime import date, timedelta

from flag_facts import QuarterlyFlagFacts
from app.services.screening_metrics import BUSINESS_MAX_AGE_DAYS, result

GREEN_FLAG_VERSION = 1
MAX_GREEN_FLAGS = 3
SUSTAINED_GROWTH_MIN_PERCENT = 8


def build_green_flag_count(snapshot: dict, today: date) -> dict:
    context = QuarterlyFlagFacts(snapshot, today)

    def lower(a, b):
        return a < b and not math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-10)

    growth_data = context.facts(8, ('revenue',))
    if growth_data and any(r['metrics']['revenue']['value'] <= 0 for r in growth_data[0]):
        growth_data = None
    growth_values = []
    if growth_data:
        for previous, current in zip(growth_data[0][:4], growth_data[0][4:]):
            value = (current['metrics']['revenue']['value'] / previous['metrics']['revenue']['value'] - 1) * 100
            growth_values.append({'period': current['period'], 'comparison_period': previous['period'], 'growth_yoy': value})
        if any(not math.isfinite(v['growth_yoy']) for v in growth_values):
            growth_data = None
    growth_met = bool(growth_data) and all(not lower(v['growth_yoy'], SUSTAINED_GROWTH_MIN_PERCENT) for v in growth_values)

    operating_data = context.facts(4, ('revenue', 'operating_income'))
    if operating_data and any(r['metrics']['revenue']['value'] <= 0
                              or abs(r['metrics']['operating_income']['value'] / r['metrics']['revenue']['value']) > 1
                              for r in operating_data[0]):
        operating_data = None

    def rule(key, title, formula, data, met, values, reason):
        return {'id': key, 'title': title, 'state': 'flagged' if data and met else 'clear' if data else 'unassessed',
                'formula': formula, 'reason': reason if data else 'Comparable, sourced quarterly inputs are missing, invalid or stale.',
                'evidence': data[1] if data else [], 'values': values if data else []}

    growth = rule('sustained_revenue_growth', 'Sustained revenue growth',
                  'Revenue YoY growth ≥ 8% in each of the latest four quarters (eight comparable revenue quarters required)',
                  growth_data, growth_met, growth_values,
                  'Four consecutive quarters of at least 8% reported revenue growth. Acquisitions, currency changes and base effects can contribute; organic growth is not established.')

    profitable_data = None
    operating_values = []
    if growth_data and operating_data:
        evidence = growth_data[1] + [e for e in operating_data[1] if e['metric'] == 'operating_income']
        if len({e['currency'] for e in evidence}) == 1:
            profitable_data = (operating_data[0], evidence)
            operating_values = [{'period': r['period'], 'operating_income': r['metrics']['operating_income']['value']}
                                for r in operating_data[0]]
    profitable = rule('profitable_growth', 'Profitable growth',
                      'Sustained revenue growth AND operating income > 0 in each of the latest four quarters',
                      profitable_data, growth_met and all(lower(0, v['operating_income']) for v in operating_values),
                      {'growth': growth_values, 'operating_income': operating_values},
                      'Persistent revenue growth accompanied by strictly positive reported operating income. Break-even does not qualify. This overlaps with Sustained revenue growth.')

    cash_data = context.facts(8, ('net_income', 'operating_cash_flow', 'capex'))
    cash_values = []
    if cash_data:
        for four in (cash_data[0][:4], cash_data[0][4:]):
            ni = sum(r['metrics']['net_income']['value'] for r in four)
            ocf = sum(r['metrics']['operating_cash_flow']['value'] for r in four)
            capex = sum(abs(r['metrics']['capex']['value']) for r in four)
            cash_values.append({'period': f"Four quarters ended {four[-1]['as_of']}",
                                'net_income': ni, 'operating_cash_flow': ocf, 'capex': capex, 'free_cash_flow': ocf - capex})
        if any(not math.isfinite(v[k]) for v in cash_values for k in ('net_income', 'operating_cash_flow', 'capex', 'free_cash_flow')):
            cash_data = None
    cash = rule('cash_backed_earnings', 'Cash-backed earnings',
                'Net income > 0 AND operating cash flow ≥ net income AND (operating cash flow − abs(capex)) > 0 in each of the latest two non-overlapping four-quarter periods',
                cash_data, all(lower(0, v['net_income']) and not lower(v['operating_cash_flow'], v['net_income'])
                               and lower(0, v['free_cash_flow']) for v in cash_values), cash_values,
                'Positive profits, earnings-to-cash conversion and positive free cash flow across two separate years. Working capital, stock compensation and other non-cash items still require review.')

    checks = []
    for branch in (growth, profitable, cash):
        state, reason = branch['state'], None
        if not context.eligible:
            state = 'not_applicable' if context.excluded else 'unassessed'
            reason = 'These rules are not calibrated for financial businesses, REITs or investment funds.' if context.excluded else 'Sector and industry classification are required.'
        elif not context.fresh:
            reason = 'A current comparable quarterly report is required (maximum age 140 days).'
        checks.append({'id': branch['id'], 'title': branch['title'], 'state': state, 'reason': reason,
                       'triggered_rules': [branch['id']] if state == 'flagged' else [], 'checks': [branch]})
    flags = [c for c in checks if c['state'] == 'flagged']
    assessed = sum(c['state'] in {'clear', 'flagged'} for c in checks)
    applicable = sum(c['state'] != 'not_applicable' for c in checks)
    complete = context.eligible and context.fresh and assessed == applicable == MAX_GREEN_FLAGS
    source = '; '.join(dict.fromkeys(e['source'] for c in checks for b in c['checks'] for e in b['evidence'])) or 'unavailable'
    return result({'source': source, 'as_of': context.latest.get('as_of', ''), 'tier': 'computed_from_public_facts'},
                  value=len(flags) if complete else None, period=context.latest.get('period', ''),
                  formula='One point for each of three positive rules met. Sustained revenue growth and Profitable growth overlap; this is not a count of independent strengths.',
                  status='Complete assessment' if complete else 'Partial assessment' if assessed else 'Not assessed',
                  validated=complete, valid_until=(context.end + timedelta(days=BUSINESS_MAX_AGE_DAYS)).isoformat() if context.end else None,
                  assessment_version=GREEN_FLAG_VERSION, max_count=MAX_GREEN_FLAGS, observed_count=len(flags),
                  coverage={'assessed': assessed, 'applicable': applicable, 'total': MAX_GREEN_FLAGS, 'complete': complete},
                  flags=flags, checks=checks,
                  notes='Positive reported financial patterns, not an investment-quality rating or valuation assessment. Growth rules overlap. The 8% threshold is a screening heuristic.',
                  warnings=[] if complete else ['Assessment incomplete or not applicable; do not interpret this as zero green flags.'])
