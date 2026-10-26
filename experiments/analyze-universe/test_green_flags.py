"""Thresholds, persistence, provenance and coverage for Green Flag Count."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import sys
import unittest

# Reuse reported-fact fixtures and validators without registering app metrics.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'backend'))

from test_screening_metrics import TODAY, ordinary
from green_flags import build_green_flag_count
from audit_support import flag_assessment


def check(metric, key):
    return next(c for c in metric['checks'] if c['id'] == key)


class GreenFlagTests(unittest.TestCase):
    def test_three_flags_include_evidence_and_explicit_overlap(self):
        stock = ordinary()
        before = deepcopy(stock)
        m = build_green_flag_count(stock, TODAY)
        self.assertEqual(m['value'], 3)
        self.assertIs(type(m['value']), int)
        self.assertEqual(m['max_count'], 3)
        self.assertEqual(m['coverage'], dict(assessed=3, applicable=3, total=3, complete=True))
        self.assertEqual(m['valid_until'], '2026-11-17')
        self.assertIn('overlap', m['notes'])
        for group in m['flags']:
            self.assertTrue(group['checks'][0]['evidence'])
            self.assertTrue(group['checks'][0]['values'])
        self.assertEqual(stock, before)

    def test_growth_threshold_and_persistence(self):
        for rate, count in [(8, 3), (7.99, 1), (0, 1), (-8, 1)]:
            with self.subTest(rate=rate):
                self.assertEqual(build_green_flag_count(ordinary(rate), TODAY)['value'], count)
        stock = ordinary()
        rows = stock['historical_series']['quarterly_fundamentals']
        rows[-2]['metrics']['revenue']['value'] = rows[-6]['metrics']['revenue']['value']
        stock['historical_series']['quarterly_revenue'] = []
        m = build_green_flag_count(stock, TODAY)
        self.assertEqual(check(m, 'sustained_revenue_growth')['state'], 'clear')
        self.assertEqual(check(m, 'profitable_growth')['state'], 'clear')

    def test_growth_is_recomputed_instead_of_trusting_saved_labels(self):
        stock = ordinary(0)
        for row in stock['historical_series']['quarterly_fundamentals']:
            row['metrics']['revenue_growth_yoy'] = dict(value=100)
        self.assertEqual(build_green_flag_count(stock, TODAY)['value'], 1)

    def test_break_even_or_one_losing_quarter_does_not_qualify_as_profitable_growth(self):
        for value in [0, -1]:
            stock = ordinary()
            stock['historical_series']['quarterly_fundamentals'][-3]['metrics']['operating_income']['value'] = value
            m = build_green_flag_count(stock, TODAY)
            self.assertEqual(m['value'], 2)
            self.assertEqual(check(m, 'profitable_growth')['state'], 'clear')

    def test_cash_conversion_equality_qualifies_but_zero_profit_or_fcf_does_not(self):
        for kind, expected in [('equal_conversion', 3), ('zero_profit', 2), ('zero_fcf', 2), ('poor_conversion', 2)]:
            stock = ordinary()
            for r in stock['historical_series']['quarterly_fundamentals']:
                m = r['metrics']
                m['operating_cash_flow']['value'] = m['net_income']['value']
                if kind == 'zero_profit':
                    m['net_income']['value'] = 0
                if kind == 'zero_fcf':
                    m['capex']['value'] = -m['operating_cash_flow']['value']
                if kind == 'poor_conversion':
                    m['operating_cash_flow']['value'] = m['net_income']['value'] - 1
            self.assertEqual(build_green_flag_count(stock, TODAY)['value'], expected, kind)

    def test_cash_rule_requires_both_nonoverlapping_years(self):
        stock = ordinary()
        rows = stock['historical_series']['quarterly_fundamentals']
        for r in rows[-8:-4]:
            r['metrics']['capex']['value'] = 1000
        m = build_green_flag_count(stock, TODAY)
        self.assertEqual(m['value'], 2)
        values = check(m, 'cash_backed_earnings')['checks'][0]['values']
        self.assertLess(values[0]['free_cash_flow'], 0)
        self.assertGreater(values[1]['free_cash_flow'], 0)

    def test_cash_rule_uses_annual_totals_and_handles_capex_sign(self):
        stock = ordinary()
        rows = stock['historical_series']['quarterly_fundamentals']
        rows[-1]['metrics']['operating_cash_flow']['value'] = 0
        for r in rows:
            r['metrics']['capex']['value'] *= -1
        self.assertEqual(build_green_flag_count(stock, TODAY)['value'], 3)

    def test_complete_zero_is_distinct_from_missing_data(self):
        stock = ordinary(-8)
        for r in stock['historical_series']['quarterly_fundamentals']:
            r['metrics']['net_income']['value'] = -1
        m = build_green_flag_count(stock, TODAY)
        self.assertEqual(m['value'], 0)
        self.assertTrue(m['coverage']['complete'])
        self.assertIsNone(build_green_flag_count({}, TODAY)['value'])

    def test_missing_capex_retains_two_confirmed_flags_without_numeric_value(self):
        stock = ordinary()
        del stock['historical_series']['quarterly_fundamentals'][-3]['metrics']['capex']
        m = build_green_flag_count(stock, TODAY)
        self.assertIsNone(m['value'])
        self.assertEqual(m['observed_count'], 2)
        self.assertEqual(m['coverage']['assessed'], 2)
        self.assertEqual(check(m, 'cash_backed_earnings')['state'], 'unassessed')

    def test_only_latest_four_operating_quarters_are_required(self):
        stock = ordinary()
        for r in stock['historical_series']['quarterly_fundamentals'][:-4]:
            del r['metrics']['operating_income']
        self.assertEqual(build_green_flag_count(stock, TODAY)['value'], 3)

    def test_invalid_operating_inputs_do_not_hide_growth_or_cash_flags(self):
        for mutation in [dict(value=True), dict(value=float('nan')), dict(value=10000),
                         dict(tier='proxy_estimate'), dict(source='model:estimate'),
                         dict(notes='Proxy'), dict(currency='EUR'), dict(as_of='2026-03-31')]:
            stock = ordinary()
            stock['historical_series']['quarterly_fundamentals'][-1]['metrics']['operating_income'].update(mutation)
            m = build_green_flag_count(stock, TODAY)
            self.assertIsNone(m['value'])
            self.assertEqual(m['observed_count'], 2)
            self.assertEqual(check(m, 'profitable_growth')['state'], 'unassessed')

    def test_invalid_revenue_or_conflicting_history_cannot_establish_growth(self):
        for mutation in [dict(value=0), dict(value=-1), dict(value=float('inf')), dict(currency='EUR')]:
            stock = ordinary()
            stock['historical_series']['quarterly_fundamentals'][-1]['metrics']['revenue'].update(mutation)
            self.assertEqual(check(build_green_flag_count(stock, TODAY), 'sustained_revenue_growth')['state'], 'unassessed')
        stock = ordinary()
        stock['historical_series']['quarterly_revenue'] = deepcopy(stock['historical_series']['quarterly_revenue'])
        stock['historical_series']['quarterly_revenue'][-1]['metrics']['revenue']['value'] *= 2
        self.assertEqual(check(build_green_flag_count(stock, TODAY), 'sustained_revenue_growth')['state'], 'unassessed')

    def test_missing_duplicate_and_misaligned_quarters_fail_coverage(self):
        for kind in ['missing', 'duplicate', 'wrong_year', 'short_history']:
            stock = ordinary()
            rows = stock['historical_series']['quarterly_fundamentals']
            if kind == 'missing':
                del rows[-3]
            elif kind == 'duplicate':
                rows.append(deepcopy(rows[-1]))
            elif kind == 'wrong_year':
                rows[-5]['as_of'] = '2024-06-30'
            else:
                del rows[:-7]
            self.assertIsNone(build_green_flag_count(stock, TODAY)['value'], kind)

    def test_stale_future_superseded_and_excluded_reports_cannot_mean_zero(self):
        for when in [TODAY + timedelta(days=100), TODAY - timedelta(days=200)]:
            self.assertEqual(build_green_flag_count(ordinary(), when)['coverage']['assessed'], 0)
        for sector, industry in [('Financial Services', 'Banks'), ('Real Estate', 'REIT'), ('', '')]:
            stock = ordinary()
            stock.update(sector=sector, industry=industry)
            m = build_green_flag_count(stock, TODAY)
            self.assertIsNone(m['value'])
            self.assertEqual(m['coverage']['assessed'], 0)
        stock = ordinary()
        stock['historical_series']['quarterly_revenue'][-1]['as_of'] = '2026-09-30'
        self.assertEqual(build_green_flag_count(stock, TODAY)['coverage']['assessed'], 0)

    def test_market_quote_does_not_affect_green_flag_freshness(self):
        stock = ordinary()
        stock['price_opportunity'] = {}
        self.assertEqual(build_green_flag_count(stock, TODAY)['value'], 3)

    def test_experiment_display_preserves_coverage_without_registering_app_metrics(self):
        from app.services.screening_metrics import build_screening_metrics
        stock = ordinary()
        metric = build_green_flag_count(stock, TODAY)
        self.assertEqual(flag_assessment(metric, TODAY, 1)['value'], 3)
        metric['coverage']['complete'] = False
        self.assertIsNone(flag_assessment(metric, TODAY, 1)['value'])
        self.assertNotIn('green_flag_count', build_screening_metrics(stock, TODAY)['metrics'])


if __name__ == '__main__':
    unittest.main()
