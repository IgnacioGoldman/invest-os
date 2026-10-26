"""Prepare and validate the isolated, conversation-authored Analyze experiment."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))


def write_json(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    temp.replace(path)

def verify_inputs(directory):
    manifest = json.loads((directory / 'manifest.json').read_text())
    prompt = (directory / 'analysis-prompt.md').read_text()
    data = gzip.decompress((directory / 'snapshots.json.gz').read_bytes())
    for value, expected in [(prompt.encode(), manifest['prompt_sha256']), (data, manifest['dataset_sha256'])]:
        if hashlib.sha256(value).hexdigest() != expected:
            raise ValueError('Frozen prompt or dataset hash mismatch')
    if (directory / 'source').exists():
        for name, expected in manifest.get('source_sha256', {}).items():
            if hashlib.sha256((directory / 'source' / name).read_bytes()).hexdigest() != expected:
                raise ValueError('Frozen formatter source hash mismatch')
    snapshots = json.loads(data)
    symbols = [s['ticker'] for s in snapshots]
    if symbols != manifest['symbols'] or len(symbols) != manifest['count'] or len(set(symbols)) != len(symbols):
        raise ValueError('Frozen universe mismatch')
    return manifest, prompt, snapshots

def freeze_filter_membership(directory):
    """Independent control, never included in the AI prompt. No AI-based filtering."""
    from app.services.simulation.strategy import screen_stock, select_candidates
    from app.services.simulation.screening import ENTRY_EXPRESSION, screen_expression_matches
    from app.services.static_stock_assets import load_full_stock_rows

    manifest, _, _ = verify_inputs(directory)
    today = datetime.fromisoformat(manifest['prepared_at'].replace('Z', '+00:00')).date()
    full = load_full_stock_rows(ROOT / 'frontend/public/data')
    if {s['ticker'] for s in full} != set(manifest['symbols']):
        raise ValueError('Control universe differs from Analyze universe')
    frozen = json.loads(gzip.decompress((directory / 'snapshots.json.gz').read_bytes()))
    dates = {s['ticker']: s['generated_at'] for s in frozen}
    if any(s['generated_at'] != dates[s['ticker']] for s in full):
        raise ValueError('Control snapshots changed during preparation')
    screens = [screen_stock(s, today) for s in full]
    base = [s['symbol'] for s in screens if screen_expression_matches(
        {'screening': s['projection']}, today)]
    result = {
        'evaluated_on': today.isoformat(), 'scope': 'Auto fixed entry strategy, not private user saved filters',
        'source': 'Existing screen_stock on full detail snapshots, as used by run_portfolio_simulation.py',
        'base_expression': ENTRY_EXPRESSION, 'base_expression_symbols': sorted(base),
        'eligible_symbols': sorted(s['symbol'] for s in screens if s['eligible']),
        'shortlisted_without_holdings': [s['symbol'] for s in select_candidates(screens, set(), set())],
        'rows': [{k: s[k] for k in ('symbol', 'eligible', 'reasons', 'revenue_strength',
            'operating_margin', 'forward_pe_class', 'red_flags', 'financial_as_of', 'price_as_of')} for s in screens],
        'full_snapshot_sha256': {s['ticker']: hashlib.sha256(json.dumps(s, sort_keys=True).encode()).hexdigest() for s in full},
    }
    write_json(directory / 'deterministic-control.json', result)

def parse_table(text, symbols):
    quality = {'Strong', 'Solid', 'Average', 'Weak', 'Poor', 'Unknown'}
    valuation = {'Cheap', 'Fair', 'Expensive', 'Unknown'}
    rows = []
    def tag(cell, allowed):
        words = re.findall(r'[A-Za-z0-9]+', re.sub(r'<[^>]+>', '', cell))
        if len(words) != 1 or words[0] not in allowed:
            raise ValueError(f'Invalid assessment tag: {cell}')
        return words[0]
    for line in text.splitlines():
        if not re.match(r'^\s*\|\s*(?:\*\*)?\d+', line):
            continue
        cells = [c.strip() for c in re.split(r'(?<!\\)\|', line.strip().strip('|'))]
        if len(cells) != 5:
            raise ValueError('Rank table must have exactly five columns')
        rank = int(cells[0].replace('*', ''))
        matches = [s for s in symbols if re.search(r'(?<![A-Za-z0-9.-])' + re.escape(s) + r'(?![A-Za-z0-9.-])', cells[1])]
        if len(matches) != 1 or not cells[4]:
            raise ValueError(f'Ambiguous/missing symbol or rationale at rank {rank}')
        rows.append({'rank': rank, 'symbol': matches[0], 'stock': cells[1],
            'business_quality': tag(cells[2], quality), 'valuation': tag(cells[3], valuation), 'rationale': cells[4]})
    if [r['rank'] for r in rows] != list(range(1, len(symbols) + 1)):
        raise ValueError('Ranks must be consecutive from 1 through the entire universe')
    actual = [r['symbol'] for r in rows]
    if len(set(actual)) != len(symbols) or set(actual) != set(symbols):
        raise ValueError('Every universe stock must appear exactly once')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['prepare', 'verify'])
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    directory = args.run_dir.resolve()
    if args.phase == 'prepare':
        subprocess.run(['node', str(Path(__file__).with_name('prepare.cjs')), str(directory)], check=True)
        freeze_filter_membership(directory)
        print('Prepared exact Analyze inputs and independent deterministic control. Analyze here in the conversation; no model API is invoked.')
    else:
        manifest, _, _ = verify_inputs(directory)
        print(f"Verified {manifest['count']} frozen stock inputs.")

if __name__ == '__main__':
    main()
