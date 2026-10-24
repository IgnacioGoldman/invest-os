"""Growth pattern rules tested from reported revenue, not trusted growth labels."""
from copy import deepcopy
from datetime import date, timedelta
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.services.screening_metrics import build_screening_metrics
from test_screening_metrics import ordinary, fact, TODAY


def growth_history(growth):
    row = ordinary()
    revenue = []
    for i in range(len(growth) + 4):
        y, q = 2024 + i // 4, i % 4 + 1
        end = f'{y}-{q*3:02d}-{30 if q in (2,3) else 31}'
        value = 100 if i < 4 else revenue[i-4]['metrics']['revenue']['value'] * (1 + growth[i-4] / 100)
        revenue.append({'period': f'FY{y} Q{q}', 'as_of': end, 'metrics': {'revenue': fact(value, 'Revenues', end)}})
    row['historical_series']['quarterly_revenue'] = revenue
    row['historical_series']['quarterly_fundamentals'] = []
    return row, date.fromisoformat(revenue[-1]['as_of']) + timedelta(days=30)


class GrowthPatternTests(unittest.TestCase):
    def test_patterns(self):
        for values, momentum, consistency in [
            ([12,14,16,18,20,22], 'Accelerating', 'Steady'),
            ([1,1,1,1,1,100], 'Steady', 'Choppy'),
            ([2,2,3,2,2,3], 'Steady', 'Steady'),
            ([30,26,22,18,14,10], 'Decelerating', 'Steady'),
            ([15,-5,30,2,40,-10], 'Decelerating', 'Choppy'),
            ([-10,-12,-14,-16,-18,-20], 'Decelerating', 'Steady'),
            ([1,1,1,80,80,80], 'Accelerating', 'Steady'),
            ([12,14,16,18,20,22,24,26], 'Accelerating', 'Steady')]:
            with self.subTest(values=values):
                row, today = growth_history(values)
                m = build_screening_metrics(row, today)['metrics']
                self.assertEqual(m['momentum']['status'], momentum)
                self.assertEqual(m['revenue_consistency']['status'], consistency)
                self.assertTrue(m['revenue_consistency']['validated'])
                self.assertEqual(len(m['momentum']['comparison_periods']), len(values))
                self.assertEqual(len(m['revenue']['observations']), len(values))
                self.assertIsNone(m['revenue_consistency']['value'], 'No artificial numeric category score')

    def test_missing_quarters_and_invalid_inputs_never_become_steady(self):
        for mutate in [lambda r: r['historical_series']['quarterly_revenue'].pop(6),
                       lambda r: r['historical_series']['quarterly_revenue'][1]['metrics']['revenue'].update(value=0),
                       lambda r: r['historical_series']['quarterly_revenue'][1]['metrics']['revenue'].update(source='unknown'),
                       lambda r: r['historical_series']['quarterly_revenue'][-1].update(period='FY2026 Q3')]:
            row, today = growth_history([12,14,16,18,20,22]); mutate(row)
            m = build_screening_metrics(row, today)['metrics']
            self.assertFalse(m['revenue_consistency']['validated'])
            self.assertIsNone(m['momentum']['value'])
        row, today = growth_history([12,14,16,18,20])
        m = build_screening_metrics(row, today)['metrics']
        self.assertTrue(m['revenue']['validated'])
        self.assertFalse(m['revenue_consistency']['validated'])

    def test_classification_has_provenance_and_does_not_mutate_facts(self):
        row, today = growth_history([12,14,16,18,20,22]); before = deepcopy(row)
        m = build_screening_metrics(row, today)['metrics']
        self.assertEqual(row, before)
        self.assertEqual(m['revenue']['strength'], 'Strong')
        self.assertIn('sec_companyfacts:', m['revenue_consistency']['source'])
        self.assertIn('tolerance_pp', m['revenue_consistency']['diagnostics'])
        for value, label in [(20,'Strong'),(8,'Solid'),(0,'Flat'),(-1,'Weak')]:
            row, today = growth_history([value]*6)
            self.assertEqual(build_screening_metrics(row,today)['metrics']['revenue']['strength'], label)

if __name__ == '__main__': unittest.main()
