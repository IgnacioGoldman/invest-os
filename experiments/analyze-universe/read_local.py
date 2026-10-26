"""Read-only worksheet from the exact archived Analyze JSON; no recalculation."""
import json
import sys
from pathlib import Path

directory = Path(sys.argv[1])
start, stop = map(int, sys.argv[2:])
rows = json.loads((directory / 'compact-stocks.json').read_text())
aliases = dict(zip(['revenue_growth_yoy_pct','revenue_momentum_pp','operating_margin_pct','operating_margin_trend_pp',
    'revenue_ttm','operating_income_ttm','net_income_ttm','operating_cash_flow_ttm','capex_ttm','free_cash_flow_ttm',
    'cash','debt','equity','market_cap','shares_diluted_m','gross_margin','net_margin','revenue_cagr_3y',
    'eps_gaap_growth_yoy','eps_cagr_3y','roe','roic','fcf_margin_ttm','debt_to_equity','peg',
    'ev_to_ebitda_proxy','gross_profit_ttm','ebitda_proxy','enterprise_value_proxy','pe_ttm','price_to_sales','fcf_yield_pct'],
    ['g','mom','op%','opΔ','rev','op','NI','OCF','capex','FCF','cash','debt','eq','MC','shares','GM%',
     'NM%','rev3y','epsg','eps3y','ROE','ROICp','FCF%','D/E','PEGp','EV/EBITDAp','GP','EBITDAp','EVp','PE','PS','FCFy%']))
history_keys = ['revenue','gross_profit','operating_income','net_income','operating_cash_flow','capex','free_cash_flow','cash','debt','equity','shares_diluted','eps_diluted']
print('All money/shares millions. Unchanged Analyze values. p=proxy. Missing=?.')
print('HISTORY order: ' + ','.join(history_keys))
print('COMMON WARNINGS: Every stock lacks a usable dated forward EPS/PE; supplied net cash/debt may have incompatible definitions. ROIC/PEG/EV-EBITDA are proxies. Financial-business operating ratios may be inapplicable.')
for x in rows[start:stop]:
    print('\n' + x['ticker'] + ' | ' + x['company'] + ' | ' + x['industry'] + ' | ' + x['financial_as_of'] + ' ' + str(x['currency']))
    print(' '.join(aliases.get(k,k)+'='+str(v['v'])+('p' if v['t']=='p' and not aliases.get(k,k).endswith('p') else '') for k,v in x['metrics'].items()))
    print('Revenue quarterly growth:', ','.join(str(r['values'].get('revenue_growth_yoy',{}).get('v','?')) for r in x['revenue_quarters']))
    for row in x['annual'] + x['quarters']:
        print(row['period'], row['as_of'], ','.join(str(row['values'].get(k,{}).get('v','?')) for k in history_keys))
    risk=x['red_flags']
    print('Flags:',risk['count'],'coverage',risk.get('coverage'), 'detected',
        [(g['group'],[(r['rule'],r['values']) for r in g['rules']]) for g in risk.get('detected',[])])
    print('Warnings:',[w for w in x['warnings'] if not w.startswith(('A positive sourced','The estimate or market','Net cash/debt'))])
    print('Price',x['market'].get('price',{}).get('v'),'supports',[(r['timeframe'],r['distance_pct'],r.get('zone')) for r in x['market']['supports']],
        '1y%',x['market'].get('return_1y_pct',{}).get('v'),'52w%',x['market'].get('from_52w_high_pct',{}).get('v'))
