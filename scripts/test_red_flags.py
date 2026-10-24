"""Accounting boundaries, missing coverage and deduplication for Red Flag Count."""
from copy import deepcopy
from datetime import timedelta
import unittest

from test_screening_metrics import TODAY, fact, ordinary
from app.services.red_flags import build_red_flag_count


def clean():
    stock = ordinary()
    for row in stock['historical_series']['quarterly_fundamentals']:
        row['metrics']['equity'] = fact(100, 'StockholdersEquity', row['as_of'])
    return stock


def check(metric, key):
    return next(c for c in metric['checks'] if c['id'] == key)


class RedFlagTests(unittest.TestCase):
    def test_clean_zero_requires_complete_coverage(self):
        m = build_red_flag_count(clean(), TODAY)
        self.assertEqual(m['value'], 0)
        self.assertIs(type(m['value']), int)
        self.assertEqual(m['coverage'], dict(assessed=3, applicable=3, total=3, complete=True))
        self.assertEqual(m['flags'], [])
        self.assertEqual(m['as_of'], '2026-06-30')
        self.assertEqual(m['valid_until'], '2026-11-17')

    def test_three_distinct_groups_and_overlapping_cash_warnings_count_once(self):
        s = clean()
        rows = s['historical_series']['quarterly_fundamentals']
        for r in rows:
            for key, value in [('net_income', 20), ('operating_cash_flow', 5), ('capex', 10)]:
                r['metrics'][key]['value'] = value
        for r in rows[-2:]:
            r['metrics']['operating_income']['value'] = -1
        rows[-1]['metrics']['equity']['value'] = -1
        m = build_red_flag_count(s, TODAY)
        self.assertEqual(m['value'], 3)
        self.assertEqual(len(m['flags']), 3)
        self.assertEqual(check(m, 'cash_generation')['triggered_rules'], ['cash_conversion', 'negative_fcf'])
        self.assertEqual(check(m, 'operating_performance')['triggered_rules'], ['margin_decline', 'operating_losses'])
        for group in m['flags']:
            for branch in group['checks']:
                self.assertTrue(branch['evidence'])
                self.assertIn('sec_companyfacts:', branch['evidence'][0]['source'])

    def test_missing_capex_is_not_a_clean_zero(self):
        s = clean()
        del s['historical_series']['quarterly_fundamentals'][-3]['metrics']['capex']
        m = build_red_flag_count(s, TODAY)
        self.assertIsNone(m['value'])
        self.assertEqual(m['observed_count'], 0)
        self.assertFalse(m['coverage']['complete'])
        self.assertEqual(m['coverage']['assessed'], 2)
        self.assertEqual(check(m, 'cash_generation')['state'], 'unassessed')

    def test_detected_flags_remain_visible_in_partial_assessment(self):
        s = clean()
        del s['historical_series']['quarterly_fundamentals'][-3]['metrics']['capex']
        s['historical_series']['quarterly_fundamentals'][-1]['metrics']['equity']['value'] = -10
        m = build_red_flag_count(s, TODAY)
        self.assertIsNone(m['value'])
        self.assertEqual(m['observed_count'], 1)
        self.assertEqual(m['flags'][0]['id'], 'balance_sheet')

    def test_one_true_branch_determines_a_group_even_if_other_branch_is_missing(self):
        s = clean()
        for r in s['historical_series']['quarterly_fundamentals']:
            r['metrics']['net_income']['value'] = 100
            r['metrics']['operating_cash_flow']['value'] = 10
            del r['metrics']['capex']
        m = build_red_flag_count(s, TODAY)
        self.assertEqual(m['value'], 1)
        self.assertTrue(m['coverage']['complete'])
        self.assertEqual(check(m, 'cash_generation')['triggered_rules'], ['cash_conversion'])

    def test_persistence_and_zero_boundaries(self):
        s = clean()
        rows = s['historical_series']['quarterly_fundamentals']
        rows[-1]['metrics']['operating_income']['value'] = -10
        rows[-1]['metrics']['operating_cash_flow']['value'] = -100
        rows[-1]['metrics']['equity']['value'] = 0
        m = build_red_flag_count(s, TODAY)
        self.assertEqual(m['value'], 0, 'One bad quarter is not a persistent pattern.')
        for r in rows:
            r['metrics']['operating_cash_flow']['value'] = r['metrics']['net_income']['value']
            r['metrics']['capex']['value'] = r['metrics']['operating_cash_flow']['value']
            r['metrics']['operating_income']['value'] = 0
        self.assertEqual(build_red_flag_count(s, TODAY)['value'], 0)

    def test_annual_fcf_must_be_negative_in_both_nonoverlapping_years(self):
        s = clean()
        rows = s['historical_series']['quarterly_fundamentals']
        for r in rows[-4:]:
            r['metrics']['capex']['value'] = 1000
        m = build_red_flag_count(s, TODAY)
        self.assertEqual(check(m, 'cash_generation')['state'], 'clear')
        for r in rows[-8:-4]:
            r['metrics']['capex']['value'] = -1000
        m = build_red_flag_count(s, TODAY)
        self.assertEqual(check(m, 'cash_generation')['state'], 'flagged')
        self.assertEqual(m['value'], 1)

    def test_zero_revenue_does_not_hide_reported_operating_losses(self):
        s = clean()
        for r in s['historical_series']['quarterly_fundamentals'][-2:]:
            r['metrics']['revenue']['value'] = 0
            r['metrics']['operating_income']['value'] = -1
        m = build_red_flag_count(s, TODAY)
        self.assertEqual(check(m, 'operating_performance')['state'], 'flagged')
        self.assertEqual(check(m, 'operating_performance')['triggered_rules'], ['operating_losses'])

    def test_conflicting_revenue_invalidates_margin_comparisons(self):
        s = clean()
        s['historical_series']['quarterly_revenue'] = deepcopy(s['historical_series']['quarterly_revenue'])
        s['historical_series']['quarterly_revenue'][-1]['metrics']['revenue']['value'] *= 2
        m = build_red_flag_count(s, TODAY)
        self.assertIsNone(m['value'])
        self.assertEqual(check(m, 'operating_performance')['state'], 'unassessed')

    def test_proxies_and_currency_mismatch_do_not_become_clean_checks(self):
        for mutation in [dict(tier='proxy_estimate'), dict(notes='Proxy operating income'),
                         dict(source='model:estimate'), dict(source='sec_companyfacts:us-gaap/OperatingIncomeLoss:EUR:10-Q:2026-06-30'),
                         dict(value=float('nan')), dict(value=True), dict(as_of='2026-03-31')]:
            with self.subTest(mutation=mutation):
                s = clean()
                s['historical_series']['quarterly_fundamentals'][-1]['metrics']['operating_income'].update(mutation)
                m = build_red_flag_count(s, TODAY)
                self.assertIsNone(m['value'])
                self.assertEqual(check(m, 'operating_performance')['state'], 'unassessed')

    def test_duplicate_or_nonconsecutive_fiscal_quarters_are_not_comparable(self):
        for kind in ['duplicate', 'missing', 'wrong_year']:
            s = clean()
            rows = s['historical_series']['quarterly_fundamentals']
            if kind == 'duplicate':
                rows.append(deepcopy(rows[-1]))
            elif kind == 'missing':
                del rows[-3]
            else:
                rows[-5]['as_of'] = '2024-06-30'
            m = build_red_flag_count(s, TODAY)
            self.assertIsNone(m['value'])
            self.assertFalse(m['coverage']['complete'])

    def test_sector_exclusions_and_missing_classification_never_mean_zero_flags(self):
        for sector, industry in [('Financial Services', 'Banks'), ('Real Estate', 'REIT'), ('', '')]:
            s = clean()
            s.update(sector=sector, industry=industry)
            m = build_red_flag_count(s, TODAY)
            self.assertIsNone(m['value'])
            self.assertFalse(m['coverage']['complete'])
            self.assertEqual(m['coverage']['assessed'], 0)

    def test_stale_future_and_superseded_reports_are_not_counted(self):
        for today in [TODAY + timedelta(days=100), TODAY - timedelta(days=200)]:
            m = build_red_flag_count(clean(), today)
            self.assertIsNone(m['value'])
            self.assertEqual(m['coverage']['assessed'], 0)
        s = clean()
        s['historical_series']['quarterly_revenue'][-1]['as_of'] = '2026-09-30'
        self.assertEqual(build_red_flag_count(s, TODAY)['coverage']['assessed'], 0)

    def test_no_data_does_not_produce_zero_and_source_data_is_preserved(self):
        self.assertIsNone(build_red_flag_count({}, TODAY)['value'])
        s = clean()
        before = deepcopy(s)
        build_red_flag_count(s, TODAY)
        self.assertEqual(s, before)


if __name__ == '__main__':
    unittest.main()
