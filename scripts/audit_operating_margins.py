"""Compare current validated margins with an immutable Analyze run."""
from __future__ import annotations

import argparse
import csv
from datetime import date
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.services.screening_metrics import build_business_performance, support_context
from app.services.static_stock_assets import load_full_stock_rows
from evaluate_saved_filters import condition_matches


def price_fingerprint(prices: dict) -> str:
    # Pydantic may add optional null fields during export; those are not price changes.
    normalized = {key: {k: v for k, v in metric.items() if v is not None} for key, metric in prices.items()}
    return hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()


def audit(baseline_run: Path, data_dir: Path, output_dir: Path, today: date, price_baseline: Path | None = None) -> dict:
    manifest = json.loads((baseline_run / 'manifest.json').read_text())
    data = gzip.decompress((baseline_run / 'snapshots.json.gz').read_bytes())
    if hashlib.sha256(data).hexdigest() != manifest['dataset_sha256']:
        raise ValueError('Frozen baseline hash mismatch')
    baseline = {s['ticker']: s for s in json.loads(data)}
    current = {s['ticker']: s for s in load_full_stock_rows(data_dir)}
    if set(baseline) != set(current):
        raise ValueError('Baseline and current universes differ')
    ranks = {r['symbol']: r['rank'] for r in json.loads((baseline_run / 'ranking.json').read_text())}
    saved_prices = json.loads(price_baseline.read_text())['stocks'] if price_baseline else None
    if saved_prices is not None and set(saved_prices) != set(current):
        raise ValueError('Price baseline and current universes differ')
    before_date = date.fromisoformat(manifest['prepared_at'][:10])
    stocks = []
    for symbol in sorted(current, key=ranks.get):
        old, new = baseline[symbol], current[symbol]
        before = build_business_performance(old, before_date)['operating_margin']
        after = build_business_performance(new, today)['operating_margin']
        rules = [('revenue', 'gt', '0'), ('operating_margin', 'gt', '0'), ('red_flag_count', 'lte', '1')]
        supported = any((context := support_context(new, f'support_{timeframe}_distance', today))
                        and context['status'] in {'At Support', 'Near Support'} for timeframe in ('1m','3m','6m','1y','2y','5y'))
        stocks.append({'symbol': symbol, 'original_rank': ranks[symbol], 'before': before, 'after': after,
            'repaired': not before['validated'] and after['validated'], 'at_or_near_support': supported,
            'passes_financial_rules': all(condition_matches(new, {'field': field, 'comparison': comparison, 'value': value}, today)
                                         for field, comparison, value in rules),
            'price_unchanged': price_fingerprint(new['price_opportunity']) == saved_prices[symbol] if saved_prices is not None else None})
    result = {'evaluated_on': today.isoformat(), 'baseline_prepared_at': manifest['prepared_at'],
        'baseline_dataset_sha256': manifest['dataset_sha256'], 'universe': len(stocks),
        'unknown_before': sum(not s['before']['validated'] for s in stocks),
        'unknown_after': sum(not s['after']['validated'] for s in stocks),
        'repaired': [s['symbol'] for s in stocks if s['repaired']],
        'regressions': [s['symbol'] for s in stocks if s['before']['validated'] and not s['after']['validated']],
        'all_prices_unchanged': all(s['price_unchanged'] for s in stocks) if saved_prices is not None else None,
        'price_baseline_sha256': hashlib.sha256(price_baseline.read_bytes()).hexdigest() if price_baseline else None,
        'at_or_near_support': sum(s['at_or_near_support'] for s in stocks),
        'supported_passing_financial_rules': sum(s['at_or_near_support'] and s['passes_financial_rules'] for s in stocks),
        'stocks': stocks}
    if result['regressions'] or result['all_prices_unchanged'] is False:
        raise ValueError('Margin availability regressed or saved price data changed')
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / 'operating-margin-audit.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    lines = ['# Local operating-margin repair', '',
        f"Evaluated {today}: **{result['unknown_before']} → {result['unknown_after']} Unknown margins** across {len(stocks)} stocks; "
        f"{len(result['repaired'])} recovered, no availability regressions. "
        + ('Saved prices match the captured before-repair baseline.' if result['all_prices_unchanged'] else 'No before-repair price baseline supplied.'), '',
        'This report compares refreshed fundamentals with the frozen 25 October Analyze run. Original ranks are historical; '
        'no new AI ranking or investment assessment was performed. Financial-sector exclusions and extreme-margin safeguards remain in force.', '',
        f"{result['at_or_near_support']} stocks are at/near support; {result['supported_passing_financial_rules']} pass all three financial rules with the refreshed inputs.", '']
    for title, selected in [('Recovered margins', [s for s in stocks if s['repaired']]),
                            ('Remaining Unknown', [s for s in stocks if not s['after']['validated']])]:
        lines.extend([f'## {title}', '', '| Original rank | Stock | Margin | Report date | Details |', '| --- | --- | --- | --- | --- |'])
        for s in selected:
            m = s['after']
            value = f"{m['value']:.2f}%" if m['validated'] else 'Unknown'
            details = ' '.join(i['message'] for i in (s['before'] if s['repaired'] else m)['validation_issues'])
            lines.append(f"| {s['original_rank']} | {s['symbol']} | {value} | {m['as_of']} | {details} |")
        lines.append('')
    (output_dir / 'operating-margin-audit.md').write_text('\n'.join(lines))
    with (output_dir / 'operating-margin-audit.csv').open('w', newline='') as f:
        writer = csv.writer(f, lineterminator='\n')
        writer.writerow(['Original rank', 'Ticker', 'Before (%)', 'After (%)', 'Report date', 'Repaired', 'Remaining causes'])
        for s in stocks:
            writer.writerow([s['original_rank'], s['symbol'], s['before']['value'], s['after']['value'], s['after']['as_of'],
                             s['repaired'], '; '.join(i['message'] for i in s['after']['validation_issues'])])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-run', type=Path, required=True)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'frontend/public/data')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--as-of', type=date.fromisoformat, default=date.today())
    parser.add_argument('--price-baseline', type=Path, help='JSON containing pre-repair price fingerprints under stocks, keyed by ticker.')
    args = parser.parse_args()
    result = audit(args.baseline_run, args.data_dir, args.output_dir, args.as_of, args.price_baseline)
    print(f"{result['unknown_before']} → {result['unknown_after']} Unknown; {len(result['repaired'])} recovered; no regressions.")
