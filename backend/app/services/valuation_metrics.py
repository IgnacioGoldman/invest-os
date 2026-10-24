"""Reported, aligned TTM valuation inputs shared by research and red flags."""
from datetime import date
import math
from app.services.screening_metrics import BUSINESS_MAX_AGE_DAYS, currencies, day, number, quarter_index, result

PRICE_TO_SALES_LIMIT = 10.0
FCF_YIELD_LIMIT = .02  # Fraction, not percentage points.
MARKET_MAX_AGE_DAYS = 7
PUBLIC_SOURCES = ('sec_companyfacts:', 'issuer_statement:', 'yfinance_statement:')
MARKET_SOURCES = (*PUBLIC_SOURCES, 'yfinance', 'yahoo', 'quote:')


def reported_valuation_metrics(snapshot: dict, today: date) -> dict:
    rows = sorted(snapshot.get('historical_series', {}).get('quarterly_fundamentals', []), key=lambda r: r.get('as_of', ''))
    window = rows[-4:]
    latest = rows[-1] if rows else {}
    end = day(latest.get('as_of'))
    quote = snapshot.get('price_opportunity', {}).get('current_price', {})
    cap = snapshot.get('metrics', {}).get('market_cap', {})
    priced = day(quote.get('as_of'))
    listing_currency = snapshot.get('price_currency')
    evidence = []
    values = None
    valid = bool(len(window) == 4 and end and 0 <= (today-end).days <= BUSINESS_MAX_AGE_DAYS
                 and priced and 0 <= (today-priced).days <= MARKET_MAX_AGE_DAYS
                 and number(quote.get('value')) is not None and quote['value'] > 0
                 and number(cap.get('value')) is not None and cap['value'] > 0
                 and cap.get('as_of') == quote.get('as_of') and listing_currency
                 and (not cap.get('currency') or cap['currency'] == listing_currency)
                 and cap.get('tier') in {'exact_public_fact', 'computed_from_public_facts', 'proxy_estimate'}
                 and cap.get('source') and all(s.startswith(MARKET_SOURCES) for s in cap['source'].split('; ')))
    indices = [quarter_index(r.get('period', '')) for r in window]
    dates = [day(r.get('as_of')) for r in window]
    valid = valid and all(i is not None for i in indices) and indices == list(range(indices[-1]-3, indices[-1]+1))
    valid = valid and all(dates) and all(60 <= (b-a).days <= 120 for a,b in zip(dates,dates[1:]))
    latest_report = max((r.get('as_of','') for key in ('quarterly_revenue','quarterly_fundamentals')
                         for r in snapshot.get('historical_series',{}).get(key,[])), default='')
    valid = valid and latest.get('as_of') == latest_report
    units = set()
    for row in window:
        valid = valid and sum(r.get('period') == row.get('period') for r in rows) == 1 and sum(r.get('as_of') == row.get('as_of') for r in rows) == 1
        for key in ('revenue','operating_cash_flow','capex'):
            m = row.get('metrics',{}).get(key,{})
            if (number(m.get('value')) is None or m.get('as_of') != row.get('as_of') or len(currencies(m)) != 1
                    or m.get('tier') not in {'exact_public_fact','computed_from_public_facts'}
                    or 'proxy' in m.get('notes','').lower() or not m.get('source')
                    or not all(s.startswith(PUBLIC_SOURCES) for s in m['source'].split('; '))):
                valid = False
                continue
            units.update(currencies(m))
            if key == 'revenue':
                for other in snapshot.get('historical_series',{}).get('quarterly_revenue',[]):
                    r = other.get('metrics',{}).get('revenue',{})
                    if other.get('as_of') == row['as_of'] and number(r.get('value')) is not None and currencies(r) == currencies(m) and not math.isclose(r['value'],m['value'],rel_tol=1e-12,abs_tol=1e-6):
                        valid = False
            evidence.append({'period':row['period'],'as_of':row['as_of'],'metric':key,'value':m['value'],
                             'currency':next(iter(currencies(m))),'source':m['source']})
    # Do not mix translated TTM values with untranslated quarterly cash flow.
    # A historical statement/listing FX bridge is required for cross-currency issuers.
    valid = valid and units == {listing_currency}
    if valid:
        revenue = sum(r['metrics']['revenue']['value'] for r in window)
        ocf = sum(r['metrics']['operating_cash_flow']['value'] for r in window)
        capex = sum(abs(r['metrics']['capex']['value']) for r in window)
        if revenue > 0 and all(r['metrics']['revenue']['value'] >= 0 for r in window):
            values = {'revenue_ttm':revenue, 'operating_cash_flow_ttm':ocf, 'capex_ttm':capex,
                      'free_cash_flow_ttm':ocf-capex, 'market_cap':cap['value'],
                      'price_to_sales':cap['value']/revenue, 'fcf_yield_fraction':(ocf-capex)/cap['value']}
            if not all(math.isfinite(v) for v in values.values()): values = None
    if values:
        evidence.append({'period':'Market capitalization','as_of':cap['as_of'],'metric':'market_cap',
                         'value':cap['value'],'currency':listing_currency,'source':cap['source']})
    source = '; '.join(dict.fromkeys(e['source'] for e in evidence)) or 'unavailable'
    period = f"TTM ended {latest.get('as_of','')}; price {quote.get('as_of','')}"
    caution = ['Market capitalization uses the saved listing-share estimate; the ratio is a deterministic screening estimate.'] if values and cap.get('tier') == 'proxy_estimate' else []
    def metric(key, formula, value):
        return result({'source':source,'as_of':latest.get('as_of',''),'tier':'computed_from_public_facts','currency':listing_currency},
                      value=value,period=period,formula=formula,status='Computed Metric' if value is not None else 'Unknown',
                      price_as_of=quote.get('as_of'),warnings=caution if value is not None else ['Four aligned public revenue/cash-flow quarters, matching listing currency and a fresh sourced market capitalization are required.'])
    return {'price_to_sales':metric('price_to_sales','market capitalization / latest four reported quarters of revenue', values['price_to_sales'] if values else None),
            'fcf_yield':metric('fcf_yield','sum(quarterly operating cash flow − abs(capex)) / same market capitalization × 100',values['fcf_yield_fraction']*100 if values else None),
            'values':values,'evidence':evidence if values else [],'price_as_of':quote.get('as_of')}
