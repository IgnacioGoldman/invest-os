import gzip
import hashlib
import importlib.util
import json
import csv
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('universe_experiment', Path(__file__).with_name('run.py'))
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)


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
            (directory / 'local-rank-order.txt').write_text('ADBE ADBE')
            with self.assertRaises(ValueError):
                render(directory)


if __name__ == '__main__':
    unittest.main()
