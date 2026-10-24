"""Strict valuation boundaries, coverage, integration and dated reference examples."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from test_screening_metrics import ordinary, TODAY
from test_red_flags import clean, check
from app.services.red_flags import build_red_flag_count
from app.services.valuation_metrics import reported_valuation_metrics
from app.services.screening_metrics import build_screening_metrics
from evaluate_saved_filters import expression_matches


def valuation(ps=16.5, yield_fraction=.011):
    s=clean()
    for r in s['historical_series']['quarterly_fundamentals'][-4:]:
        r['metrics']['revenue']['value']=100
        r['metrics']['operating_cash_flow']['value']=100
        r['metrics']['capex']['value']=100-ps*100*yield_fraction
    s['historical_series']['quarterly_revenue']=[]
    s['metrics']['market_cap']['value']=400*ps
    return s


class PricedForPerfectionTests(unittest.TestCase):
    def test_strict_boundaries_and_negative_or_zero_cashflow(self):
        for ps,yield_fraction,flag in [(16.5,.011,True),(39,.006,True),(9,.011,False),(11,.03,False),
                                      (9,.03,False),(10,.011,False),(11,.02,False),(11,0,True),(11,-.01,True)]:
            with self.subTest(ps=ps,yield_fraction=yield_fraction):
                s=valuation(ps,yield_fraction); before=deepcopy(s)
                m=build_red_flag_count(s,TODAY)
                group=check(m,'priced_for_perfection')
                self.assertEqual(group['state'],'flagged' if flag else 'clear')
                self.assertEqual(group['triggered_rules'],['priced_for_perfection'] if flag else [])
                self.assertEqual(s,before)
                self.assertEqual(m,build_red_flag_count(s,TODAY))
                values=group['checks'][0]['values']
                self.assertAlmostEqual(values['price_to_sales'],ps)
                self.assertAlmostEqual(values['fcf_yield_fraction'],yield_fraction)

    def test_unreliable_inputs_leave_assessment_incomplete(self):
        for mutate in [lambda s:s['metrics'].pop('market_cap'),
                       lambda s:s['metrics']['market_cap'].update(value=0),
                       lambda s:s['metrics']['market_cap'].update(as_of='2026-09-01'),
                       lambda s:s['metrics']['market_cap'].update(currency='EUR'),
                       lambda s:s['historical_series']['quarterly_fundamentals'][-1]['metrics'].pop('capex'),
                       lambda s:s['historical_series']['quarterly_fundamentals'][-1]['metrics'].pop('revenue'),
                       lambda s:s['historical_series']['quarterly_fundamentals'][-1]['metrics']['operating_cash_flow'].update(value=None),
                       lambda s:s['historical_series']['quarterly_fundamentals'][-1]['metrics']['capex'].update(tier='proxy_estimate'),
                       lambda s:s['historical_series']['quarterly_fundamentals'].pop(-2),
                       lambda s:s.update(price_currency='EUR')]:
            s=valuation();mutate(s);m=build_red_flag_count(s,TODAY)
            self.assertEqual(check(m,'priced_for_perfection')['state'],'unassessed')
            self.assertIsNone(m['value'])
            self.assertFalse(m['coverage']['complete'])
        for revenue in [0,-1]:
            s=valuation()
            for r in s['historical_series']['quarterly_fundamentals'][-4:]: r['metrics']['revenue']['value']=revenue
            self.assertIsNone(reported_valuation_metrics(s,TODAY)['values'])

    def test_count_filter_and_shared_research_calculation(self):
        s=valuation();s['screening']=build_screening_metrics(s,TODAY)
        m=s['screening']['metrics']['red_flag_count']
        self.assertEqual(m['value'],1)
        self.assertEqual(m['max_count'],4)
        self.assertEqual(m['coverage']['assessed'],4)
        expression={'operator':'and','groups':[{'conditions':[{'field':'red_flag_count','comparison':'eq','value':'0'}]}]}
        self.assertFalse(expression_matches(s,expression))
        values=check(m,'priced_for_perfection')['checks'][0]['values']
        self.assertEqual(s['screening']['financial_details']['price_to_sales']['value'],values['price_to_sales'])
        self.assertEqual(s['screening']['financial_details']['fcf_yield']['value'],values['fcf_yield_fraction']*100)
        s['historical_series']['quarterly_fundamentals'][-1]['metrics']['equity']['value']=-1
        self.assertEqual(build_red_flag_count(s,TODAY)['value'],2)

    def test_october_23_reference_snapshots(self):
        for symbol,ps,yield_percent in [('SHOP',16.5,1.0743),('ALAB',39.227,.5868)]:
            s=json.loads((Path(__file__).parent/'fixtures'/f'{symbol.lower()}-valuation-2026-10-23.json').read_text())
            m=build_red_flag_count(s,TODAY)
            group=check(m,'priced_for_perfection')
            self.assertEqual(group['state'],'flagged')
            values=group['checks'][0]['values']
            self.assertAlmostEqual(values['price_to_sales'],ps,delta=.01)
            self.assertAlmostEqual(values['fcf_yield_fraction']*100,yield_percent,delta=.01)
            self.assertEqual(len([f for f in m['flags'] if f['id']=='priced_for_perfection']),1)

    def test_financial_industry_remains_outside_rule_scope(self):
        s=valuation();s.update(sector='Financial Services',industry='Banks')
        m=build_red_flag_count(s,TODAY)
        self.assertEqual(check(m,'priced_for_perfection')['state'],'not_applicable')
        self.assertIsNone(m['value'])

if __name__=='__main__':unittest.main()
