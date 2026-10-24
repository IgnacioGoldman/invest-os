"""Conservative research metrics. Raw snapshots are never overwritten.

Source identifiers establish provenance, not independent verification. No quality
score or valuation rating is calculated here. Policy cutoffs reuse existing
revenue (20/8/0), momentum (3 pp), and market freshness (7 days) rules.
"""
from __future__ import annotations

import math
import re
from datetime import date, timedelta
from typing import Any

from app.services.revenue_growth_momentum import calculate_revenue_growth_momentum

DROPPED_FIELDS = frozenset({'eps', 'industry_strength', 'valuation'})


def number(value: Any) -> float | None:
    return float(value) if not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) else None


def day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def currencies(metric: dict) -> set[str]:
    if metric.get('currency'):
        return {metric['currency']}
    return set(re.findall(r':([A-Z]{3})(?:/shares)?:', metric.get('source', '')))


def compatible(*metrics: dict) -> bool:
    units = [currencies(m) for m in metrics]
    return bool(metrics) and all(number(m.get('value')) is not None for m in metrics) and all(len(u) == 1 for u in units) and len(set.union(*units)) == 1 and len({m.get('as_of') for m in metrics}) == 1


def result(metric: dict | None = None, *, value: float | None = None, period: str = '', formula: str = '', status: str = 'Unknown', warnings: list[str] | None = None, **extra: Any) -> dict:
    m = metric or {}
    return {**m, 'value': value, 'source': m.get('source', 'unavailable'),
            'as_of': m.get('as_of', ''), 'tier': m.get('tier', 'computed_from_public_facts'),
            'notes': m.get('notes', ''), 'kind': 'Estimate' if m.get('tier') == 'proxy_estimate' else 'Reported Fact' if m.get('tier') == 'exact_public_fact' else 'Computed Metric',
            'currency': m.get('currency') or (next(iter(currencies(m))) if len(currencies(m)) == 1 else None),
            'period': period, 'formula': formula, 'status': status, 'warnings': warnings or [], **extra}


def compute(left: dict, right: dict, formula: str, period: str, operation, *, positive_denominator: bool = True) -> dict:
    valid = compatible(left, right) and (not positive_denominator or (number(right.get('value')) or 0) > 0)
    value = operation(left['value'], right['value']) if valid else None
    if number(value) is None:
        value = None
    return result({'source': f"{left.get('source', 'unavailable')}; {right.get('source', 'unavailable')}",
                   'as_of': left.get('as_of', ''), 'tier': 'computed_from_public_facts'},
                  value=value, period=period, formula=formula,
                  status='Computed Metric' if value is not None else 'Unknown',
                  warnings=[] if value is not None else ['Missing or incompatible inputs, currency, period, or denominator.'])


def quarter_index(period: str) -> int | None:
    m = re.fullmatch(r'FY(\d+) Q([1-4])', period)
    return int(m[1]) * 4 + int(m[2]) - 1 if m else None


def financial(snapshot: dict) -> bool:
    text = f"{snapshot.get('sector') or ''} {snapshot.get('industry') or ''}".lower()
    return any(term in text for term in ('financial', 'bank', 'insurance', 'insurer', 'credit', 'asset management', 'capital markets', 'broker'))


def build_screening_metrics(snapshot: dict, today: date | None = None) -> dict:
    today = today or date.today()
    raw = snapshot.get('metrics', {})
    health = snapshot.get('business_health', {})
    history = snapshot.get('historical_series', {})
    revenue_rows = sorted(history.get('quarterly_revenue', []), key=lambda r: r.get('as_of', ''))
    quarters = sorted(history.get('quarterly_fundamentals', []), key=lambda r: r.get('as_of', ''))
    latest = quarters[-1] if quarters else {}
    qm = latest.get('metrics', {})
    period = latest.get('period', '')
    warnings: list[str] = []
    output: dict[str, Any] = {}

    # Use the latest quarter, including a missing latest observation. Never
    # search backwards for an older usable value and present it as current.
    latest_revenue = revenue_rows[-1] if revenue_rows else {}
    rp = latest_revenue.get('period', '')
    index = quarter_index(rp)
    matches = [r for r in revenue_rows if index is not None and quarter_index(r.get('period', '')) == index - 4]
    current = latest_revenue.get('metrics', {}).get('revenue', {})
    prior = matches[0].get('metrics', {}).get('revenue', {}) if len(matches) == 1 else {}
    reported = latest_revenue.get('metrics', {}).get('revenue_growth_yoy', {})
    growth = result(reported, period=rp, formula='(quarter revenue / same fiscal quarter prior-year revenue - 1) × 100', kind='Computed Metric')
    dates = (day(current.get('as_of')), day(prior.get('as_of')))
    if (number(current.get('value')) is not None and number(prior.get('value')) is not None
            and current['value'] > 0 and prior['value'] > 0 and currencies(current) == currencies(prior) and len(currencies(current)) == 1
            and all(dates) and 350 <= (dates[0] - dates[1]).days <= 380
            and sum(r.get('period') == rp for r in revenue_rows) == 1):
        value = (current['value'] / prior['value'] - 1) * 100
        growth.update(value=value, source=f"{current.get('source')}; {prior.get('source')}", as_of=current.get('as_of'),
                      status='High Growth' if value >= 20 else 'Moderate Growth' if value >= 8 else 'Flat' if value >= 0 else 'Declining')
    else:
        growth['warnings'] = ['Comparable latest-quarter revenue and prior-year fiscal quarter are required.']
    output['revenue'] = growth

    validated_rows = []
    for row in revenue_rows:
        ri = quarter_index(row.get('period', ''))
        rm = row.get('metrics', {})
        rv = rm.get('revenue', {})
        candidates = [r for r in revenue_rows if ri is not None and quarter_index(r.get('period', '')) == ri - 4]
        pv = candidates[0].get('metrics', {}).get('revenue', {}) if len(candidates) == 1 else {}
        rd, pd = day(rv.get('as_of')), day(pv.get('as_of'))
        valid = (number(rv.get('value')) is not None and number(pv.get('value')) is not None and rv['value'] > 0 and pv['value'] > 0
                 and len(currencies(rv)) == 1 and currencies(rv) == currencies(pv) and rd and pd and 350 <= (rd-pd).days <= 380)
        computed = (rv['value'] / pv['value'] - 1) * 100 if valid else None
        stored = number(rm.get('revenue_growth_yoy', {}).get('value'))
        if computed is not None and stored is not None and not math.isclose(computed, stored, abs_tol=1e-6):
            computed = None
        validated_rows.append({**row, 'metrics': {**rm, 'revenue_growth_yoy': {**rm.get('revenue_growth_yoy', {}), 'value': computed}}})
    momentum = calculate_revenue_growth_momentum({**snapshot, 'historical_series': {**history, 'quarterly_revenue': validated_rows}})
    stored_growth = number(reported.get('value'))
    if growth['value'] is not None and stored_growth is not None and not math.isclose(growth['value'], stored_growth, abs_tol=1e-6):
        growth.update(value=None, status='Needs Review', warnings=['Stored growth disagrees with the comparable revenue calculation.'])
    if growth['value'] is None:
        momentum.update(label='Unknown', change=None, reason='Latest comparable revenue is unavailable.')
    output['momentum'] = result(value=momentum['change'], period='; '.join(p['period'] for p in momentum['points']),
        formula='median(latest 3 quarterly YoY growth rates) − median(preceding 3), pp',
        status={'Stable': 'Steady', 'Unclear': 'Unknown'}.get(momentum['label'], momentum['label']),
        as_of=latest_revenue.get('as_of', ''), notes='Existing thresholds: accelerating ≥3 pp; decelerating ≤−3 pp; otherwise steady.', warnings=[momentum['reason']] if momentum['reason'] else [], source='; '.join(r.get('metrics', {}).get('revenue_growth_yoy', {}).get('source', '') for r in revenue_rows[-6:]))

    op = qm.get('operating_income', {})
    # Approximate R&D + SG&A proxies must not masquerade as core profitability.
    if op.get('tier') == 'proxy_estimate' or 'proxy' in op.get('notes', '').lower():
        op = {}
    operating = compute(op, qm.get('revenue', {}), 'quarter operating income / quarter revenue × 100', period, lambda a, b: a / b * 100)
    idx = quarter_index(period)
    prior_quarters = [r for r in quarters if idx is not None and quarter_index(r.get('period', '')) == idx - 4]
    operating['yoy_change_pp'] = None
    if len(prior_quarters) == 1 and operating['value'] is not None:
        prior_q = prior_quarters[0]
        pm = prior_q['metrics']
        previous = compute(pm.get('operating_income', {}), pm.get('revenue', {}), '', prior_q['period'], lambda a, b: a / b * 100)
        a, b = day(latest.get('as_of')), day(prior_q.get('as_of'))
        if previous['value'] is not None and pm.get('operating_income', {}).get('tier') != 'proxy_estimate' and 'proxy' not in pm.get('operating_income', {}).get('notes', '').lower() and a and b and 350 <= (a-b).days <= 380 and currencies(op) == currencies(pm.get('operating_income', {})):
            operating['yoy_change_pp'] = operating['value'] - previous['value']
    if operating['value'] is not None and (abs(operating['value']) > 100 or op.get('as_of') != latest.get('as_of')):
        operating['status'] = 'Needs Review'
        operating['warnings'].append('Operating margin exceeds revenue in magnitude or does not match the latest fiscal period; inspect the calculation inputs.')
    output['operating_margin'] = operating

    revenue, ocf, capex = (raw.get(k, {}) for k in ('revenue_ttm', 'operating_cash_flow_ttm', 'capex_ttm'))
    fcf = compute(ocf, capex, 'TTM operating cash flow − TTM capex (positive cash outflow)', f"TTM ended {revenue.get('as_of', 'Unknown')}", lambda a, b: a - abs(b), positive_denominator=False)
    fcf_margin = compute(fcf, revenue, '(TTM operating cash flow − TTM capex) / TTM revenue × 100', fcf['period'], lambda a, b: a / b * 100)
    # A known TTM selection or explicit period is required, even for legacy data.
    if not all((m.get('period') or '').startswith('TTM') or 'ttm' in m.get('notes', '').lower() or 'annual' in m.get('notes', '').lower() for m in (revenue, ocf, capex)):
        fcf_margin.update(value=None, status='Unknown', warnings=['TTM measurement periods are not documented for all inputs.'])
    recent_fcf = qm.get('free_cash_flow', {})
    recent_capex, recent_ocf = qm.get('capex', {}), qm.get('operating_cash_flow', {})
    if number(recent_fcf.get('value')) is not None and recent_fcf['value'] < 0:
        fcf_margin['warnings'].append(f"{period}: recent-quarter free cash flow is negative ({recent_fcf['value']:,.0f}); TTM can conceal this.")
    if compatible(recent_capex, recent_ocf) and abs(recent_capex['value']) > recent_ocf['value']:
        fcf_margin['warnings'].append(f'{period}: capex exceeds operating cash flow; investigate unusually high investment spending.')
    previous_rows = [r for r in prior_quarters if compatible(r['metrics'].get('free_cash_flow', {}), r['metrics'].get('revenue', {}))]
    if previous_rows and compatible(recent_fcf, qm.get('revenue', {})) and previous_rows[0]['metrics']['revenue']['value'] > 0 and qm['revenue']['value'] > 0:
        pm = previous_rows[0]['metrics']
        delta = (recent_fcf['value'] / qm['revenue']['value'] - pm['free_cash_flow']['value'] / pm['revenue']['value']) * 100
        if delta < 0 and not math.isclose(delta, 0, abs_tol=1e-10):
            fcf_margin['warnings'].append(f'{period}: quarterly FCF margin deteriorated {delta:.2f} pp YoY; assess materiality. This is separate from TTM margin.')
    if fcf_margin['value'] is not None and fcf_margin['warnings']:
        fcf_margin['status'] = 'Needs Review'
    output['fcf_margin'] = fcf_margin

    price = snapshot.get('price_opportunity', {}).get('current_price', {})
    eps = snapshot.get('valuation_inputs', {}).get('forward_eps_public', {})
    estimate_date, price_date = day(eps.get('estimate_as_of')), day(price.get('as_of'))
    horizon = eps.get('forecast_horizon')
    fiscal_horizon = re.fullmatch(r'FY(\d{4})(?: annual)?', str(horizon))
    identifiable_horizon = str(horizon).lower() in {'ntm', 'next 12 months'} or bool(fiscal_horizon and int(fiscal_horizon[1]) >= today.year)
    valid_eps = (number(eps.get('value')) is not None and eps['value'] > 0 and eps.get('source') not in (None, '', 'unavailable')
                 and identifiable_horizon and estimate_date and 0 <= (today - estimate_date).days <= 7
                 and eps.get('currency') == snapshot.get('price_currency') and 'implied' not in eps.get('notes', '').lower())
    valid_price = number(price.get('value')) is not None and price['value'] > 0 and price_date and 0 <= (today - price_date).days <= 7
    forward = result(eps, period=horizon or 'Unknown forecast horizon', formula='current price / sourced annual forward EPS', kind='Estimate',
        estimate_as_of=eps.get('estimate_as_of'), forecast_horizon=horizon, price_as_of=price.get('as_of'))
    if valid_eps and valid_price:
        forward.update(value=price['value'] / eps['value'], status='Estimate', source=f"{price['source']}; {eps['source']}", tier='proxy_estimate')
    else:
        forward['warnings'] = ['A positive sourced annual EPS estimate, identifiable forecast horizon, currency and estimate date are required; quote and estimate must be no older than seven days. Historical EPS extrapolation is excluded.']
    output['forward_pe'] = forward

    balances = {}
    for key in ('cash', 'short_term_investments', 'long_term_investments', 'debt'):
        m = health.get(key, raw.get(key, {}))
        balances[key] = result(m, value=number(m.get('value')), period=f"Balance at {m.get('as_of', 'Unknown')}", status='Reported Fact' if m.get('tier') == 'exact_public_fact' else 'Computed Metric' if number(m.get('value')) is not None else 'Unknown')
    cash, debt = balances['cash'], balances['debt']
    for key in ('cash', 'debt'):
        balances[key]['formula'] = 'Reported scope: ' + balances[key]['source']
    for key in ('short_term_investments', 'long_term_investments'):
        balances[key]['warnings'].append('Investment composition and liquidity require review; excluded from net cash.')
    precise_cash = any(f'/{tag}:' in cash['source'] for tag in ('CashAndCashEquivalentsAtCarryingValue', 'CashAndCashEquivalents'))
    # Partial debt tags cannot establish total debt. Never assume missing debt=0.
    debt_source = debt['source']
    total_debt = ('LongTermDebtCurrent:' in debt_source and 'LongTermDebtNoncurrent:' in debt_source and 'ShortTermBorrowings:' in debt_source) or any(f'/{tag}:' in debt_source for tag in ('Borrowings', 'TotalDebt'))
    net = compute(cash, debt, 'cash and cash equivalents − total debt; investments excluded', cash['period'], lambda a, b: a-b, positive_denominator=False)
    if not (precise_cash and total_debt) or (cash['value'] or 0) < 0 or (debt['value'] or 0) < 0:
        net.update(value=None, status='Needs Review', warnings=['Net cash/debt requires unrestricted cash equivalents and complete compatible debt. Investments are excluded; inspect component definitions.'])
    output['balance_sheet'] = {**net, 'components': balances}

    net_income = qm.get('net_income', {})
    if compatible(net_income, op) and net_income['value'] > op['value'] and net_income['value'] > 0:
        warnings.append(f'{period}: net income exceeds operating income. Investigate investment gains, tax effects and other non-operating items; GAAP EPS growth, net margin, trailing P/E and PEG can mislead. This check does not establish the cause.')
    if financial(snapshot):
        for key in ('operating_margin', 'fcf_margin'):
            output[key].update(value=None, status='Unknown')
            output[key]['warnings'].append('Not comparable for this financial business; lending, deposits and financing affect standard operating-company ratios.')
    for key in ('revenue', 'operating_margin', 'fcf_margin'):
        m = output[key]
        if m['value'] is not None and (not day(m['as_of']) or day(m['as_of']) > today):
            m.update(value=None, status='Needs Review')
            m['warnings'].append('Invalid or future reporting period.')
    advanced = {}
    gross = compute(qm.get('gross_profit', {}), qm.get('revenue', {}), 'quarter gross profit / quarter revenue × 100', period, lambda a,b: a/b*100)
    if financial(snapshot):
        gross.update(value=None, status='Unknown')
    advanced['gross_margin'] = gross
    market_cap = raw.get('market_cap', {})
    inputs = snapshot.get('valuation_inputs', {})
    for key, denominator_key, raw_key in (('price_to_sales', 'revenue', 'revenue_ttm'), ('fcf_yield', 'free_cash_flow', 'free_cash_flow_ttm')):
        m = snapshot.get('valuation', {}).get(key, {})
        statement = inputs.get(denominator_key, raw.get(raw_key, {}))
        value = None
        currency = snapshot.get('price_currency')
        valid = (valid_price and currency and currencies(statement) == {currency} and number(statement.get('value')) is not None
                 and number(market_cap.get('value')) is not None and market_cap['value'] > 0
                 and market_cap.get('as_of') == price.get('as_of') and statement.get('as_of') == revenue.get('as_of'))
        if valid and key == 'price_to_sales' and statement['value'] > 0:
            value = market_cap['value'] / statement['value']
        elif valid and key == 'fcf_yield' and not financial(snapshot):
            value = statement['value'] / market_cap['value'] * 100
        advanced[key] = result(m, value=value, period=f"TTM ended {revenue.get('as_of', 'Unknown')}; price {price.get('as_of', 'Unknown')}",
            formula='market cap / TTM revenue' if key == 'price_to_sales' else 'TTM FCF / market cap × 100', status='Computed Metric' if value is not None else 'Unknown',
            warnings=[] if value is not None else ['Missing, stale or incompatible market-cap/statement inputs.'])
    for m in output.values():
        if m['value'] is not None and (number(m['value']) is None):
            m.update(value=None, status='Needs Review')
            m['warnings'].append('Calculation did not produce a finite value.')
    earnings = snapshot.get('price_opportunity', {}).get('days_to_next_earnings', raw.get('days_to_next_earnings', {}))
    match = re.search(r':(\d{4}-\d{2}-\d{2})(?:/(\d{4}-\d{2}-\d{2}))?$', earnings.get('source', ''))
    event_date = day(match[1]) if match else None
    event_days = (event_date - today).days if event_date else None
    collected = day(earnings.get('as_of'))
    if event_days is None or event_days < 0 or not collected or not 0 <= (today-collected).days <= 7:
        event_days = None
    output['upcoming_earnings'] = result(earnings, value=event_days, period=match[0][1:] if match else 'Unknown date',
        formula='source event/window start date − current date', status='Unknown' if event_days is None else 'This week' if event_days <= 7 else 'Next 30 days' if event_days <= 30 else 'Later')
    return {'version': 1, 'as_of': today.isoformat(), 'metrics': output, 'financial_details': advanced, 'warnings': warnings,
            'verification': 'Source identifiers preserve provenance; financial inputs have not been independently verified.'}


def enrich_screening(snapshot):
    return snapshot.model_copy(update={'screening': build_screening_metrics(snapshot.model_dump(mode='json'))})
