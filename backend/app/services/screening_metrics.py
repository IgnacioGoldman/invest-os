"""Deterministic business facts, red/green flag counts and preserved AI inputs.

Sources establish provenance, not independent verification. First-filter cards
use signed revenue/margin changes, the existing 3 pp momentum threshold and the
existing 140-day quarterly freshness policy. Research-only calculations remain
available without becoming screening labels, rankings or investment scores.
"""
from __future__ import annotations

import math
import re
from datetime import date, timedelta
from typing import Any
from statistics import median

from app.services.revenue_growth_momentum import calculate_revenue_growth_momentum

DROPPED_FIELDS = frozenset({'eps', 'industry_strength', 'valuation', 'fcf_margin', 'forward_pe', 'balance_sheet'})


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


def support_context(snapshot: dict, key: str, today: date | None = None) -> dict | None:
    today = today or date.today()
    prices = snapshot.get('price_opportunity', {})
    m, quote = prices.get(key, {}), prices.get('current_price', {})
    zone = re.search(r'Support zone: \$?([\d,.]+)-\$?([\d,.]+)', m.get('notes', ''))
    end = day(m.get('as_of'))
    if (not zone or number(m.get('value')) is None or m.get('tier') != 'computed_from_public_facts'
            or not m.get('source') or m.get('as_of') != quote.get('as_of') or not end or not 0 <= (today-end).days <= 7
            or number(quote.get('value')) is None):
        return None
    try:
        low, high = (float(value.replace(',', '')) for value in zone.groups())
    except ValueError:
        return None
    if low <= 0 or high < low or quote['value'] < low:
        return None
    return {**m, 'status': 'At Support' if quote['value'] <= high else 'Near Support' if m['value'] <= 6 else 'Above Support'}


# Reuse the 140-day quarterly-revenue freshness rule in
# scripts/screen_revenue_expansion.py. A new stock quote does not refresh facts.
BUSINESS_MAX_AGE_DAYS = 140
BUSINESS_STATUSES = {
    'revenue': {'Growing', 'Flat', 'Declining'},
    'momentum': {'Accelerating', 'Steady', 'Decelerating'},
    'revenue_consistency': {'Steady', 'Choppy'},
    'operating_margin': {'Profitable', 'Loss-making'},
    'operating_margin_trend': {'Improving', 'Stable', 'Declining'},
}


def revenue_strength(value: float | None) -> str:
    """Restore the pre-existing 20/8/0 growth bands without changing signed aliases."""
    if value is None:
        return 'Unknown'
    return 'Strong' if value >= 20 - 1e-10 else 'Solid' if value >= 8 - 1e-10 else 'Flat' if value >= 0 else 'Weak'


def revenue_consistency(values: list[float]) -> dict:
    """Pattern regularity, independent of growth direction and strength."""
    tolerance = max(3.0, .25 * median(abs(v) for v in values))
    curvature = max(abs(values[i] - 2 * values[i-1] + values[i-2]) for i in range(2, len(values)))
    # A sustained new level is not an isolated spike. Require three observations
    # on each side, all within the same documented tolerance of their median.
    sustained_shift = any(all(max(abs(v - median(part)) for v in part) <= tolerance for part in (values[:i], values[i:]))
                          for i in range(3, len(values)-2))
    return {'label': 'Steady' if curvature <= tolerance + 1e-10 or sustained_shift else 'Choppy',
            'max_second_difference_pp': curvature, 'tolerance_pp': tolerance, 'sustained_level_shift': sustained_shift,
            'observation_count': len(values)}


def build_business_performance(snapshot: dict, today: date) -> dict:
    """Validate report inputs and calculate only descriptive first-filter facts."""
    history = snapshot.get('historical_series', {})
    rows = sorted(history.get('quarterly_revenue', []), key=lambda r: r.get('as_of', ''))
    quarters = sorted(history.get('quarterly_fundamentals', []), key=lambda r: r.get('as_of', ''))
    latest_revenue = rows[-1] if rows else {}
    latest_operating = quarters[-1] if quarters else {}
    latest_report = max(latest_revenue.get('as_of', ''), latest_operating.get('as_of', ''))

    def unique(row: dict, series: list[dict]) -> bool:
        return quarter_index(row.get('period', '')) is not None and sum(r.get('period') == row['period'] for r in series) == 1 and sum(r.get('as_of') == row.get('as_of') for r in series) == 1

    def public_input(m: dict, row: dict) -> bool:
        # These checks validate the input's structure and reproducibility. They
        # do not establish independent verification of the publisher's figures.
        return (number(m.get('value')) is not None and len(currencies(m)) == 1
                and m.get('as_of') == row.get('as_of') and day(m.get('as_of')) is not None
                and m.get('tier') in {'exact_public_fact', 'computed_from_public_facts'}
                and str(m.get('source', '')).startswith(('sec_companyfacts:', 'issuer_statement:', 'yfinance_statement:'))
                and 'proxy' not in (m.get('notes') or '').lower())

    def prior_for(row: dict, series: list[dict]) -> dict:
        idx = quarter_index(row.get('period', ''))
        matches = [r for r in series if idx is not None and quarter_index(r.get('period', '')) == idx - 4]
        if len(matches) != 1 or not unique(row, series):
            return {}
        current_date, previous_date = day(row.get('as_of')), day(matches[0].get('as_of'))
        return matches[0] if current_date and previous_date and 350 <= (current_date - previous_date).days <= 380 else {}

    def metric(row: dict, formula: str) -> dict:
        end = day(row.get('as_of'))
        return result(period=row.get('period', ''), as_of=row.get('as_of', ''), formula=formula,
                      validated=False, valid_until=(end + timedelta(days=BUSINESS_MAX_AGE_DAYS)).isoformat() if end else None)

    def publish(m: dict, value: float | None, status: str, inputs: list[dict], row: dict) -> dict:
        end = day(row.get('as_of'))
        if (number(value) is not None and end and 0 <= (today - end).days <= BUSINESS_MAX_AGE_DAYS
                and row.get('as_of') == latest_report):
            m.update(value=value, status=status, validated=True,
                     source='; '.join(dict.fromkeys(i['source'] for i in inputs)),
                     currency=next(iter(currencies(inputs[0]))))
        return m

    def growth_for(row: dict) -> tuple[float | None, list[dict]]:
        prior = prior_for(row, rows)
        current = row.get('metrics', {}).get('revenue', {})
        previous = prior.get('metrics', {}).get('revenue', {})
        if not (public_input(current, row) and public_input(previous, prior)
                and currencies(current) == currencies(previous) and current['value'] >= 0 and previous['value'] > 0):
            return None, []
        value = (current['value'] / previous['value'] - 1) * 100
        stored = number(row.get('metrics', {}).get('revenue_growth_yoy', {}).get('value'))
        if stored is not None and not math.isclose(stored, value, abs_tol=1e-6):
            return None, []
        return value, [current, previous]

    growth = metric(latest_revenue, '(latest quarter revenue / same fiscal quarter prior-year revenue − 1) × 100')
    value, inputs = growth_for(latest_revenue)
    if value is not None:
        publish(growth, value, 'Growing' if value > 0 else 'Declining' if value < 0 else 'Flat', inputs, latest_revenue)

    growth['strength'] = revenue_strength(growth['value'])

    momentum = metric(latest_revenue, 'median(latest 3 quarterly YoY growth rates) − median(preceding 3), pp')
    validated_rows, all_inputs, observations = [], {}, []
    for row in rows:
        value, inputs = growth_for(row)
        validated_rows.append({**row, 'metrics': {'revenue_growth_yoy': {'value': value}}})
        all_inputs[row.get('period', '')] = inputs
        if value is not None:
            observations.append({'period': row['period'], 'as_of': row['as_of'], 'value': value,
                                 'currency': next(iter(currencies(inputs[0]))),
                                 'source': '; '.join(dict.fromkeys(i['source'] for i in inputs))})
    movement = calculate_revenue_growth_momentum({'historical_series': {'quarterly_revenue': validated_rows}})
    used = movement['points']
    window = [row for row in validated_rows if row['period'] in {p['period'] for p in used}]
    comparable_window = bool(window) and all(
        60 <= (day(b['as_of']) - day(a['as_of'])).days <= 120 for a, b in zip(window, window[1:]))
    window_inputs = [i for row in window for i in all_inputs[row['period']]]
    same_currency = bool(window_inputs) and len(set.union(*(currencies(i) for i in window_inputs))) == 1
    if growth['validated'] and movement['change'] is not None and comparable_window and same_currency:
        publish(momentum, movement['change'], movement['label'], window_inputs, latest_revenue)
        half = len(used) // 2
        momentum['formula'] = f'median(latest {half} quarterly YoY growth rates) − median(preceding {half}), pp; ±3 pp thresholds'
        momentum['period'] = '; '.join(row['period'] for row in window)
        momentum['comparison_periods'] = [row['period'] for row in window]
        momentum['detail'] = movement
    # The chart and all consumers use these recomputed, source-linked observations.
    growth['observations'] = observations
    consistency = metric(latest_revenue, 'max absolute second difference ≤ max(3 pp, 25% of median absolute growth); or sustained level shift (≥3 quarters each side)')
    if momentum['validated']:
        pattern = revenue_consistency([point['value'] for point in used])
        consistency.update(momentum, value=None, status=pattern['label'], formula=consistency['formula'],
                           diagnostics=pattern)

    def operating_issues(row: dict) -> list[dict]:
        income = row.get('metrics', {}).get('operating_income', {})
        revenue = row.get('metrics', {}).get('revenue', {})
        issues = []

        def add(code: str, message: str):
            issues.append({'code': code, 'message': message})

        if not unique(row, quarters):
            add('invalid_period', 'Missing, invalid or duplicate fiscal quarter/date.')
        if financial(snapshot):
            add('financial_sector', 'Excluded by the financial-sector comparability rule.')
        for label, key, value in [('Operating income', 'operating_income', income), ('Revenue', 'revenue', revenue)]:
            if number(value.get('value')) is None:
                add(f'missing_{key}', f'{label} is missing for the latest fundamentals quarter ({row.get("as_of") or "undated"}).')
            elif value.get('tier') == 'proxy_estimate' or 'proxy' in (value.get('notes') or '').lower():
                add(f'proxy_{key}', f'{label} is only a proxy estimate; the screening rule excludes proxies.')
            elif not public_input(value, row):
                add(f'invalid_{key}', f'{label} lacks an accepted public source, tier, currency or matching report date.')
        if number(income.get('value')) is not None and number(revenue.get('value')) is not None:
            if not compatible(income, revenue):
                add('incompatible_inputs', 'Operating income and revenue have incompatible currencies or report dates.')
            elif revenue['value'] <= 0:
                add('nonpositive_revenue', 'Quarterly revenue is not positive.')
            elif abs(income['value'] / revenue['value'] * 100) > 100:
                add('unusual_magnitude', 'Absolute operating margin exceeds 100%; the screening rule requires interpretation.')
        return issues

    def operating_for(row: dict) -> tuple[float | None, list[dict]]:
        if operating_issues(row):
            return None, []
        income, revenue = (row['metrics'][key] for key in ('operating_income', 'revenue'))
        return income['value'] / revenue['value'] * 100, [income, revenue]

    operating = metric(latest_operating, 'latest quarter operating income / same-quarter revenue × 100')
    operating['validation_issues'] = operating_issues(latest_operating)
    operating_date = day(latest_operating.get('as_of'))
    if not operating_date:
        operating['validation_issues'].append({'code': 'invalid_date', 'message': 'Missing or invalid fundamentals report date.'})
    elif operating_date > today:
        operating['validation_issues'].append({'code': 'future_report', 'message': f'Fundamentals report date {operating_date} is after evaluation date {today}.'})
    elif (today - operating_date).days > BUSINESS_MAX_AGE_DAYS:
        operating['validation_issues'].append({'code': 'stale_report', 'message': f'Report {operating_date} expired on {operating["valid_until"]} ({BUSINESS_MAX_AGE_DAYS}-day limit).'})
    if latest_operating.get('as_of') != latest_report:
        operating['validation_issues'].append({'code': 'older_fundamentals', 'message': f'Fundamentals quarter {latest_operating.get("as_of")} is behind the latest report {latest_report}.'})
    value, inputs = operating_for(latest_operating)
    if value is not None:
        publish(operating, value, 'Profitable' if value >= 0 else 'Loss-making', inputs, latest_operating)
    trend = metric(latest_operating, 'latest quarter operating margin − same fiscal quarter prior-year operating margin, pp')
    prior = prior_for(latest_operating, quarters)
    previous, prior_inputs = operating_for(prior)
    if operating['validated'] and previous is not None and currencies(inputs[0]) == currencies(prior_inputs[0]):
        delta = value - previous
        delta = 0.0 if math.isclose(delta, 0, abs_tol=1e-10) else delta
        publish(trend, delta, 'Improving' if delta > 0 else 'Declining' if delta < 0 else 'Stable', inputs + prior_inputs, latest_operating)
        trend['comparison_periods'] = [prior['period'], latest_operating['period']]
    operating['yoy_change_pp'] = trend['value']
    business = {'revenue': growth, 'momentum': momentum, 'revenue_consistency': consistency, 'operating_margin': operating, 'operating_margin_trend': trend}
    revenue_input = latest_revenue.get('metrics', {}).get('revenue', {})
    operating_revenue = latest_operating.get('metrics', {}).get('revenue', {})
    if (latest_revenue.get('as_of') == latest_operating.get('as_of')
            and public_input(revenue_input, latest_revenue) and public_input(operating_revenue, latest_operating)
            and currencies(revenue_input) == currencies(operating_revenue)
            and not math.isclose(revenue_input['value'], operating_revenue['value'], rel_tol=1e-12, abs_tol=1e-6)):
        for m in business.values():
            m.update(value=None, validated=False, status='Unknown', notes='Conflicting revenue amounts for the same reporting quarter.')
        operating['validation_issues'].append({'code': 'conflicting_revenue',
            'message': f'Conflicting revenue for {latest_operating["as_of"]}: revenue history {revenue_input["value"]:,.0f} versus fundamentals {operating_revenue["value"]:,.0f} {next(iter(currencies(revenue_input)))}.'})
    return business


def build_screening_metrics(snapshot: dict, today: date | None = None) -> dict:
    from app.services.red_flags import build_red_flag_count
    today = today or date.today()
    raw = snapshot.get('metrics', {})
    health = snapshot.get('business_health', {})
    history = snapshot.get('historical_series', {})
    quarters = sorted(history.get('quarterly_fundamentals', []), key=lambda r: r.get('as_of', ''))
    latest = quarters[-1] if quarters else {}
    qm = latest.get('metrics', {})
    period = latest.get('period', '')
    warnings: list[str] = []
    output = build_business_performance(snapshot, today)
    # Retain interpretation-heavy calculations and warnings for Analyze with AI.
    op = qm.get('operating_income', {})
    if op.get('tier') == 'proxy_estimate' or 'proxy' in op.get('notes', '').lower():
        op = {}
    index = quarter_index(period)
    prior_quarters = [r for r in quarters if index is not None and quarter_index(r.get('period', '')) == index - 4]

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
    from app.services.valuation_metrics import reported_valuation_metrics
    valuation = reported_valuation_metrics(snapshot, today)
    for key in ('price_to_sales','fcf_yield'):
        advanced[key] = valuation[key]
        if financial(snapshot):
            advanced[key].update(value=None, status='Unknown')
    for m in output.values():
        if m['value'] is not None and (number(m['value']) is None):
            m.update(value=None, status='Needs Review')
            m['warnings'].append('Calculation did not produce a finite value.')
    earnings = snapshot.get('price_opportunity', {}).get('days_to_next_earnings', raw.get('days_to_next_earnings', {}))
    match = re.search(r':(\d{4}-\d{2}-\d{2})(?:/(\d{4}-\d{2}-\d{2}))?$', earnings.get('source', ''))
    event_date = day(match[1]) if match else None
    event_end = day(match[2]) if match and match[2] else event_date
    event_days = (event_date - today).days if event_date and event_end and event_end >= event_date else None
    collected = day(earnings.get('as_of'))
    if event_days is None or event_days <= 0 or not collected or not 0 <= (today-collected).days <= 7:
        event_days = None
    output['upcoming_earnings'] = result(earnings, value=event_days, period=match[0][1:] if match else 'Unknown date',
        formula='source event/window start date − current date', status='Unknown' if event_days is None else 'This week' if event_days <= 7 else 'Next 30 days' if event_days <= 30 else 'Later')
    output['red_flag_count'] = build_red_flag_count(snapshot, today, valuation)
    return {'version': 4, 'as_of': today.isoformat(), 'metrics': output, 'financial_details': advanced, 'warnings': warnings,
            'verification': 'Source identifiers preserve provenance; financial inputs have not been independently verified.'}


def enrich_screening(snapshot):
    return snapshot.model_copy(update={'screening': build_screening_metrics(snapshot.model_dump(mode='json'))})
