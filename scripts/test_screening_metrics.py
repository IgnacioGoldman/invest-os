"""Research-screening regressions using the supplied GOOG snapshot and clean facts."""
from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.services.screening_metrics import build_screening_metrics
from app.entry_engine.open_data_models import OpenDataSnapshot, OpenDataMetric, LatestPrice
from app.entry_engine.valuation_refresh import reprice_valuation
from app.services.stock_derived_signals import build_stock_derived_signals

TODAY = date(2026, 10, 24)


def fact(value, concept, end='2026-06-30', notes='Reported quarterly fact.'):
    return {'value': value, 'source': f'sec_companyfacts:us-gaap/{concept}:USD:10-Q:{end}',
            'as_of': end, 'tier': 'exact_public_fact', 'notes': notes}


def ordinary(revenue_growth=12):
    rows = []
    for i in range(10):
        year, quarter = 2024 + i // 4, i % 4 + 1
        end = f'{year}-{quarter*3:02d}-{30 if quarter in (2,3) else 31}'
        revenue = 100 if i < 4 else 100 * (1 + revenue_growth / 100) ** (i // 4)
        metrics = {'revenue': fact(revenue, 'Revenues', end)}
        if i >= 4:
            prior = rows[i-4]['metrics']['revenue']['value']
            metrics['revenue_growth_yoy'] = {**fact((revenue/prior-1)*100,'Revenues',end), 'tier':'computed_from_public_facts'}
        rows.append({'period': f'FY{year} Q{quarter}', 'as_of': end, 'metrics': metrics})
    quarter_rows = []
    for r in rows:
        m = r['metrics']; revenue = m['revenue']['value']; end = r['as_of']
        quarter_rows.append({**r, 'metrics': {**m,
            'operating_income': fact(revenue*.2, 'OperatingIncomeLoss', end),
            'net_income': fact(revenue*.15, 'NetIncomeLoss', end),
            'gross_profit': fact(revenue*.4, 'GrossProfit', end),
            'operating_cash_flow': fact(revenue*.3, 'NetCashProvidedByUsedInOperatingActivities', end),
            'capex': fact(revenue*.1, 'PaymentsToAcquirePropertyPlantAndEquipment', end),
            'free_cash_flow': fact(revenue*.2, 'NetCashProvidedByUsedInOperatingActivities', end)}})
    return {'ticker':'NORMAL', 'generated_at':'2026-10-24T12:00:00Z', 'sector':'Technology', 'industry':'Software', 'price_currency':'USD',
        'historical_series': {'quarterly_revenue':rows, 'quarterly_fundamentals':quarter_rows},
        'business_health': {'cash': fact(50, 'CashAndCashEquivalentsAtCarryingValue'), 'debt': fact(20,'Borrowings'),
                            'long_term_investments': fact(1000, 'LongTermInvestments')},
        'metrics': {'revenue_ttm':fact(400, 'Revenues',notes='TTM'), 'operating_cash_flow_ttm':fact(120,'NetCashProvidedByUsedInOperatingActivities',notes='TTM'),
                    'capex_ttm': fact(40,'PaymentsToAcquirePropertyPlantAndEquipment',notes='TTM')},
        'valuation': {}, 'valuation_inputs': {}, 'price_opportunity': {'current_price': {'value':100, 'source':'quote:test', 'as_of':TODAY.isoformat(),'tier':'exact_public_fact','notes':'Saved market quote.'}}}


class ScreeningMetricsTests(unittest.TestCase):
    def test_combined_cash_facts_are_preserved_but_cannot_supply_cash_equivalents(self):
        from app.entry_engine.open_data_metrics import compute_open_data_snapshot
        from test_refresh_separation import facts
        source=facts()
        tags=source['facts']['us-gaap']
        cash=tags.pop('CashAndCashEquivalentsAtCarryingValue')
        tags['CashCashEquivalentsAndShortTermInvestments']=deepcopy(cash)
        tags['CashCashEquivalentsAndShortTermInvestments']['units']['USD'][0]['val']=1000
        tags['CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents']=cash
        result=compute_open_data_snapshot(ticker='TEST',cik=123,companyfacts=source,price=None)
        self.assertIsNone(result.business_health['cash'].value)
        self.assertEqual(result.metrics['cash_with_investments_reported'].value,1000)
        self.assertEqual(result.metrics['cash_including_restricted_reported'].value,100)
        self.assertIsNone(result.screening['metrics']['balance_sheet']['value'])

    def test_goog_q2_exceptional_earnings_do_not_generate_investment_ratings(self):
        s=json.loads((Path(__file__).parent/'fixtures/goog-q2-2026.json').read_text())
        before=deepcopy(s)
        result=build_screening_metrics(s,TODAY); m=result['metrics']
        self.assertAlmostEqual(s['business_health']['eps_gaap_growth_yoy']['value'],294.37229437229433)
        self.assertAlmostEqual(s['business_health']['net_margin']['value'],93.65337740826071)
        self.assertAlmostEqual(s['valuation']['peg']['value'],.18,delta=.02)
        self.assertAlmostEqual(m['operating_margin']['value'],34.03285585495342)
        self.assertAlmostEqual(m['fcf_margin']['value'],11.948208654618202)
        self.assertEqual(m['fcf_margin']['status'],'Needs Review')
        self.assertTrue(any('negative' in w for w in m['fcf_margin']['warnings']))
        self.assertTrue(any('capex exceeds' in w for w in m['fcf_margin']['warnings']))
        self.assertTrue(any('net income exceeds' in w for w in result['warnings']))
        self.assertIsNone(m['forward_pe']['value'])
        self.assertNotIn('eps',m); self.assertNotIn('peg',m)
        self.assertEqual(s,before,'Computing screening must preserve raw research facts')
        derived=build_stock_derived_signals(OpenDataSnapshot.model_validate(s),[])
        self.assertNotIn('unusual_score',derived.derived_metrics)
        self.assertNotIn('sector_pe_cheap_rank',derived.derived_metrics)

    def test_ordinary_company_preserves_reproducible_values_without_false_gain_alarm(self):
        result=build_screening_metrics(ordinary(),TODAY);m=result['metrics']
        self.assertAlmostEqual(m['revenue']['value'],12)
        self.assertEqual(m['revenue']['status'],'Moderate Growth')
        self.assertEqual(m['momentum']['status'],'Steady')
        self.assertAlmostEqual(m['operating_margin']['value'],20)
        self.assertAlmostEqual(m['operating_margin']['yoy_change_pp'],0)
        self.assertAlmostEqual(m['fcf_margin']['value'],20)
        self.assertEqual(m['balance_sheet']['value'],30,'Strategic investments must be excluded')
        self.assertEqual(result['warnings'],[])

    def test_missing_mixed_currency_periods_negative_denominator_and_financial_sectors(self):
        for mutate in [lambda s:s['metrics'].pop('capex_ttm'),
                       lambda s:s['metrics']['revenue_ttm'].update(value=-400),
                       lambda s:s['metrics']['capex_ttm'].update(as_of='2026-03-31'),
                       lambda s:s['metrics']['capex_ttm'].update(source='sec_companyfacts:us-gaap/Capex:EUR:10-Q:2026-06-30'),
                       lambda s:s.update(sector='Financial Services',industry='Banks')]:
            s=ordinary();mutate(s)
            self.assertIsNone(build_screening_metrics(s,TODAY)['metrics']['fcf_margin']['value'])
        missing=build_screening_metrics({},TODAY)
        self.assertTrue(all(m['value'] is None for m in missing['metrics'].values()))
        s=ordinary();s['metrics']['capex_ttm']['value']=0
        self.assertEqual(build_screening_metrics(s,TODAY)['metrics']['fcf_margin']['value'],30)

    def test_latest_missing_quarter_cannot_reuse_an_older_good_metric(self):
        s=ordinary();s['historical_series']['quarterly_fundamentals'][-1]['metrics'].pop('operating_income')
        s['historical_series']['quarterly_revenue'][-1]['metrics']['revenue']['value']=None
        m=build_screening_metrics(s,TODAY)['metrics']
        for key in ('revenue','momentum','operating_margin'):self.assertIsNone(m[key]['value'])

    def test_balance_scope_and_date_checks_exclude_ambiguous_cash_and_partial_debt(self):
        for key,concept in [('cash','CashCashEquivalentsAndShortTermInvestments'),('cash','CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents'),('debt','LongTermDebtNoncurrent')]:
            s=ordinary();s['business_health'][key]=fact(20,concept)
            m=build_screening_metrics(s,TODAY)['metrics']['balance_sheet']
            self.assertIsNone(m['value']);self.assertEqual(m['components'][key]['value'],20)
        s=ordinary();s['business_health']['debt']['as_of']='2026-03-31'
        self.assertIsNone(build_screening_metrics(s,TODAY)['metrics']['balance_sheet']['value'])

    def test_forward_estimate_requires_explicit_fresh_metadata_and_survives_repricing(self):
        s=ordinary();eps={**fact(5,'ExpectedEPS',TODAY.isoformat()),'source':'analyst:test','tier':'proxy_estimate','currency':'USD','forecast_horizon':'FY2027 annual','estimate_as_of':TODAY.isoformat()}
        s['valuation_inputs']['forward_eps_public']=eps
        self.assertEqual(build_screening_metrics(s,TODAY)['metrics']['forward_pe']['value'],20)
        for key,bad in [('forecast_horizon',None),('forecast_horizon','Unknown'),('forecast_horizon','FY2025 annual'),('estimate_as_of','2026-10-01'),('currency','EUR'),('value',0),('value',-5),('value',float('inf'))]:
            altered=deepcopy(s);altered['valuation_inputs']['forward_eps_public'][key]=bad
            self.assertIsNone(build_screening_metrics(altered,TODAY)['metrics']['forward_pe']['value'])
        updated=reprice_valuation(OpenDataSnapshot.model_validate(s),LatestPrice(ticker='NORMAL',price=150,currency='USD',source='quote:test',as_of=date.today().isoformat()),
            forward_eps=OpenDataMetric.model_validate({**eps,'estimate_as_of':date.today().isoformat(),'forecast_horizon':f'FY{date.today().year+1} annual'}))
        self.assertEqual(updated.valuation['forward_pe'].value,30)

    def test_estimate_collection_does_not_refresh_old_analyst_metadata(self):
        s=ordinary();s['valuation_inputs']['forward_eps_public']={**fact(5,'ExpectedEPS'),'source':'analyst:test','currency':'USD','forecast_horizon':'FY2027 annual','estimate_as_of':'2026-09-01','as_of':TODAY.isoformat()}
        self.assertIsNone(build_screening_metrics(s,TODAY)['metrics']['forward_pe']['value'])

    def test_earlier_momentum_observations_require_comparable_underlying_revenue(self):
        s=ordinary();s['historical_series']['quarterly_revenue'][1]['metrics']['revenue']['source']='unknown'
        self.assertIsNone(build_screening_metrics(s,TODAY)['metrics']['momentum']['value'])

if __name__=='__main__':unittest.main()
