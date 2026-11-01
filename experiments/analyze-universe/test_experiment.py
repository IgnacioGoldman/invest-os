import gzip
import hashlib
import importlib.util
import json
import csv
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('universe_experiment', Path(__file__).with_name('run.py'))
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)


class PartialFlagDisplay(unittest.TestCase):
    def test_unassessed_branch_is_visible_even_when_group_has_a_detected_flag(self):
        sys.path.insert(0, str(Path(__file__).parent))
        from audit_support import unassessed_flag_checks
        from render_local import flag_cell, unassessed_flags_cell
        metric = {'value': None, 'observed_count': 1, 'max_count': 4,
            'coverage': {'assessed': 3, 'applicable': 4}, 'checks': [
                {'id': 'mixed', 'title': 'Profitability', 'state': 'flagged', 'reason': '', 'checks': [
                    {'id': 'loss', 'title': 'Losses', 'state': 'flagged', 'formula': 'income < 0', 'reason': 'Losses detected.'},
                    {'id': 'trend', 'title': 'Margin trend', 'state': 'unassessed', 'formula': 'YoY change', 'reason': 'Prior quarter missing.'}]}]}
        missing = unassessed_flag_checks(metric)
        self.assertEqual([r['id'] for r in missing], ['trend'])
        self.assertIn('1 detected',flag_cell(metric,'red'))
        self.assertIn('3/4 assessed',flag_cell(metric,'red'))
        self.assertIn('Prior quarter missing.',unassessed_flags_cell({'red':missing,'green':[]}))
        self.assertIsNone(metric['value'],'Displaying observed flags must not turn a partial assessment into a numeric screening value')

    def test_empty_and_out_of_scope_assessments_are_distinct(self):
        from audit_support import unassessed_flag_checks
        from render_local import flag_cell
        unavailable = {'value':None,'coverage':{},'checks':[],'notes':'Assessment expired.'}
        self.assertEqual(unassessed_flag_checks(unavailable)[0]['id'],'assessment_unavailable')
        self.assertIn('Not assessed',flag_cell(unavailable,'red'))
        self.assertNotIn('0 detected',flag_cell(unavailable,'red'))
        self.assertEqual(unassessed_flag_checks({'checks':[{'state':'not_applicable'}]}),[])
        excluded = {'value':None,'coverage':{'assessed':0,'applicable':0},'checks':[{
            'state':'not_applicable','title':'Financial-sector scope','checks':[{
                'state':'unassessed','title':'Cash flow','formula':'test','reason':'No comparable inputs'}]}]}
        self.assertEqual(unassessed_flag_checks(excluded),[])
        self.assertIn('Not applicable',flag_cell(excluded,'red'))
        self.assertNotIn('Not assessed',flag_cell(excluded,'red'))


class RankingValidation(unittest.TestCase):
    table = ('| Rank | Stock | Business quality | Valuation | Rationale |\n'
             '| --- | --- | --- | --- | --- |\n'
             '| 1 | **AAA** | 🟢 Strong | 🟡 Fair | Cash generation; dated evidence. |\n'
             '| 2 | BBB | Unknown | Unknown | Insufficient comparable data. |\n')

    def test_accepts_complete_colored_output_and_preserves_unknown(self):
        rows = experiment.parse_table(self.table, ['AAA', 'BBB'])
        self.assertEqual([r['symbol'] for r in rows], ['AAA', 'BBB'])
        self.assertEqual(rows[1]['valuation'], 'Unknown')

    def test_rejects_partial_duplicate_skipped_and_fabricated_symbols(self):
        for table in [self.table.split('| 2')[0], self.table.replace('BBB', 'AAA'),
                      self.table.replace('| 2 |', '| 3 |'), self.table.replace('BBB', 'CCC')]:
            with self.subTest(table=table), self.assertRaises(ValueError):
                experiment.parse_table(table, ['AAA', 'BBB'])

    def test_rejects_numeric_scoring_and_extra_columns(self):
        for table in [self.table.replace('🟢 Strong', '9'), self.table.replace('🟢 Strong', 'Strong 9/10'),
                      self.table.replace('🟢 Strong', 'Strong or Solid'), self.table.replace('🟡 Fair |', '🟡 Fair | 10 |')]:
            with self.subTest(table=table), self.assertRaises(ValueError):
                experiment.parse_table(table, ['AAA', 'BBB'])

    def test_preserves_escaped_pipes_in_rationale(self):
        rows = experiment.parse_table(self.table.replace('Cash generation;', r'Cash \| generation;'), ['AAA', 'BBB'])
        self.assertIn(r'\|', rows[0]['rationale'])


class LocalIsolation(unittest.TestCase):
    def fixture(self, directory):
        data = json.dumps([{'ticker': 'AAA'}]).encode()
        prompt = 'Unchanged fixture prompt'
        (directory / 'snapshots.json.gz').write_bytes(gzip.compress(data))
        (directory / 'analysis-prompt.md').write_text(prompt)
        experiment.write_json(directory / 'manifest.json', {'symbols': ['AAA'], 'count': 1,
            'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
            'dataset_sha256': hashlib.sha256(data).hexdigest()})

    def test_frozen_input_is_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self.fixture(directory)
            manifest, prompt, rows = experiment.verify_inputs(directory)
            self.assertEqual(manifest['count'], 1)
            self.assertEqual(rows[0]['ticker'], 'AAA')

    def test_tampered_prompt_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self.fixture(directory)
            (directory / 'analysis-prompt.md').write_text('Changed')
            with self.assertRaises(ValueError):
                experiment.verify_inputs(directory)

    def test_complete_local_export_has_200_stocks_and_five_csv_columns_without_network(self):
        sys.path.insert(0, str(Path(__file__).parent))
        from render_local import render
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            source = Path(__file__).parent / 'runs/2026-10-25'
            for name in ['manifest.json', 'snapshots.json.gz', 'analysis-prompt.md', 'local-assessments.tsv', 'local-rank-order.txt', 'research-notes.json']:
                shutil.copyfile(source / name, directory / name)
            shutil.copytree(source / 'source', directory / 'source')
            with patch('socket.create_connection', side_effect=AssertionError('Local export must not use network')):
                rows = render(directory)
            self.assertEqual(len(rows), 200)
            self.assertEqual(len({r['symbol'] for r in rows}), 200)
            with (directory / 'ranking.csv').open() as f:
                csv_rows = list(csv.reader(f))
            self.assertEqual(len(csv_rows), 201)
            self.assertTrue(all(len(row) == 5 for row in csv_rows))
            self.assertEqual(len(list((directory / 'evidence').glob('*.json'))), 200)
            audit = json.loads((directory / 'filter-research/support-audit.json').read_text())
            _, _, frozen = experiment.verify_inputs(source)
            original = {s['ticker']: s for s in frozen}
            self.assertEqual((audit['at_or_near_support'],audit['pass_all_three'],audit['do_not_pass']),(64,33,31))
            for symbol, row in audit['stocks'].items():
                for field, rule in row['rules'].items():
                    self.assertEqual(rule['value'],original[symbol]['screening']['metrics'][field]['value'])
            unknown = [row for row in audit['stocks'].values() if row['rules']['operating_margin']['status']=='Unknown']
            self.assertEqual(len(unknown),29)
            self.assertTrue(all(row['rules']['operating_margin']['validation_issues'] for row in unknown))
            for symbol, code in [('BMY','proxy_operating_income'),('ARES','financial_sector'),('B','missing_operating_income'),
                                 ('KO','stale_report'),('MELI','conflicting_revenue'),('MSTR','unusual_magnitude'),('AXFO.ST','future_report')]:
                self.assertIn(code,[issue['code'] for issue in audit['stocks'][symbol]['rules']['operating_margin']['validation_issues']])
            document = (directory / 'ranking.html').read_text()
            self.assertNotIn('Operating margin: unavailable or unvalidated',document)
            self.assertIn('Operating income is only a proxy estimate',document)
            self.assertIn('id="filter-builder"',document)
            self.assertNotIn('Method and evidence limits',document)
            self.assertNotIn('id="financial-refresh"',document)
            payload = json.loads(re.search(r'<script id="playground-data" type="application/json">(.*?)</script>', document).group(1))
            self.assertEqual(len(payload['stocks']), 200)
            self.assertEqual([p['name'] for p in payload['presets']], ['Pullback', 'Support'])
            self.assertEqual([p['rules'][2]['timeframes'] for p in payload['presets']],
                [['support_1m', 'support_3m', 'support_6m'], ['support_1y', 'support_2y', 'support_5y']])
            self.assertIn('<th>Red flags</th><th>Green flags</th>',document)
            self.assertEqual(document.count('<td class="flags red-flags">'),200)
            self.assertEqual(document.count('<td class="flags green-flags">'),200)
            self.assertTrue(all(s['flag_metrics']['green_flag_count']['value'] is None for s in audit['stocks'].values()))
            for name in ['financial-refresh.json','financial-refresh.json.gz']:
                shutil.copyfile(source / name,directory / name)
            with patch('socket.create_connection',side_effect=AssertionError('Refreshed export must not use network')):
                refreshed = render(directory)
            self.assertEqual(refreshed,rows,'Refreshing financial checks must preserve every qualitative ranking')
            updated = json.loads((directory / 'filter-research/support-audit.json').read_text())
            self.assertEqual(sum(s['rules']['operating_margin']['status']=='Unknown' for s in updated['stocks'].values()),15)
            for symbol in ['BMY','V','KO','KLAC','DY','YPF','AXFO.ST','MELI']:
                self.assertEqual(updated['stocks'][symbol]['rules']['operating_margin']['status'],'Pass')
            updated_document = (directory / 'ranking.html').read_text()
            updated_payload = json.loads(re.search(r'<script id="playground-data" type="application/json">(.*?)</script>', updated_document).group(1))
            self.assertEqual(updated_payload['evaluatedOn'], '2026-10-26')
            self.assertEqual([len(p['symbols']) for p in updated_payload['presets']], [17, 9])
            projected = {s['symbol']: s for s in updated_payload['stocks']}
            self.assertIsNone(projected['BMY']['metrics']['red_flag_count']['value'])
            self.assertEqual(projected['ANIP']['metrics']['green_flag_count']['value'], 2)
            self.assertEqual(updated['stocks']['ANIP']['flag_metrics']['green_flag_count']['value'],2)
            bmy = updated['stocks']['BMY']
            self.assertIsNone(bmy['rules']['red_flag_count']['value'])
            self.assertFalse(bmy['rules']['red_flag_count']['passes'])
            self.assertEqual(bmy['flag_metrics']['red_flag_count']['observed_count'],0)
            self.assertEqual([r['id'] for r in bmy['flags_not_assessed']['red']],['margin_decline'])
            self.assertIn('<th>flags_not_assessed</th>',(directory / 'ranking.html').read_text())
            self.assertNotIn('Red flags: incomplete assessment',(directory / 'ranking.html').read_text())
            self.assertIn('Cash-backed earnings',(directory / 'ranking.html').read_text())
            self.assertEqual((directory / 'snapshots.json.gz').read_bytes(),(source / 'snapshots.json.gz').read_bytes())
            (directory / 'local-rank-order.txt').write_text('ADBE ADBE')
            with self.assertRaises(ValueError):
                render(directory)


if __name__ == '__main__':
    unittest.main()
