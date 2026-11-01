"""Refresh missing flag inputs and assess the saved universe, without AI credentials.

Uses explicit local paths and public financial sources; never loads application
settings or .env files. Saved prices and qualitative rankings are retained.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.entry_engine.providers.open_data_provider import OpenDataProvider
from app.entry_engine.open_data_models import LatestPrice
from app.entry_engine.valuation_refresh import reprice_valuation
from app.services.red_flags import build_red_flag_count
from app.services.static_stock_assets import load_full_stock_rows, write_stock_assets
from app.services.stock_data_quality import retain_verified_history
from app.services.storage import connect, load_stock_open_data_snapshot, load_stock_price_history, replace_stock_open_data_snapshot
from green_flags import build_green_flag_count


def assess(snapshot, today):
    return {'red': build_red_flag_count(snapshot, today), 'green': build_green_flag_count(snapshot, today)}


def outside_scope(metric):
    return bool(metric['checks']) and all(g['state'] == 'not_applicable' for g in metric['checks'])


def coverage(assessments):
    return {color: dict(Counter('Not applicable' if outside_scope(a[color]) else a[color]['status']
                               for a in assessments.values())) for color in ('red', 'green')}


def assessment_summary(metric):
    return {key: metric[key] for key in ('value', 'observed_count', 'status', 'coverage')} | {
        'checks': [{key: group.get(key) for key in ('id', 'title', 'state', 'reason')} | {
            'checks': [{key: branch.get(key) for key in ('id', 'title', 'state', 'reason')}
                       for branch in group['checks']]}
            for group in metric['checks']]}


def write_coverage_report(directory, before, after, today):
    """Reviewable coverage and every remaining missing check for all symbols."""
    from audit_support import unassessed_flag_checks
    directory.mkdir(parents=True, exist_ok=True)
    summary = {'evaluated_on': today.isoformat(), 'universe': len(after),
               'before': coverage(before), 'after': coverage(after),
               'stocks': {symbol: {color: assessment_summary(m) for color, m in metrics.items()}
                          for symbol, metrics in after.items()}}
    (directory / 'flag-coverage.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
    lines = ['# Universe flag coverage', '', f'Evaluated on {today}; all {len(after)} symbols assessed.', '',
             'Counts below describe concern groups. A detected group can still contain an unassessed branch; every such branch is listed separately.', '',
             '| Rules | Complete before | Complete now | Partial now | Not assessed | Not applicable |',
             '| --- | --- | --- | --- | --- | --- |']
    previous, current = coverage(before), coverage(after)
    for color in ('red', 'green'):
        counts = current[color]
        lines.append(f'| {color.title()} | {previous[color].get("Complete assessment", 0)} | {counts.get("Complete assessment", 0)} | {counts.get("Partial assessment", 0)} | {counts.get("Not assessed", 0)} | {counts.get("Not applicable", 0)} |')
    lines += ['', 'Not applicable identifies financial businesses, REITs and investment funds outside these rules’ sector scope. Missing capex is never assumed to be zero; proxy operating income cannot replace a reported value.', '',
              '| Stock | Rules | Detected | Groups assessed | Check not assessed | Missing input / reason |',
              '| --- | --- | --- | --- | --- | --- |']
    with (directory / 'flag-coverage.csv').open('w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Symbol', 'Rules', 'Status', 'Detected', 'Groups assessed', 'flags_not_assessed'])
        for symbol, assessment in sorted(after.items()):
            for color, metric in assessment.items():
                missing = unassessed_flag_checks(metric)
                count = metric['coverage']['assessed']
                group_coverage = f'{count}/{metric["coverage"]["applicable"]}'
                detected = metric['observed_count'] if count else 'Unknown'
                status = 'Not applicable' if outside_scope(metric) else metric['status']
                writer.writerow([symbol, color, status, detected, group_coverage,
                                 '; '.join(f'{m["title"]}: {m["reason"]}' for m in missing)])
                for m in missing:
                    lines.append(f'| {symbol} | {color} | {detected} | {group_coverage} | {m["title"]} | {m["reason"]} |')
    (directory / 'flag-coverage.md').write_text('\n'.join(lines) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--as-of', type=date.fromisoformat, default=date.today())
    parser.add_argument('--collect', action='store_true', help='Repair eligible incomplete assessments with public financial sources.')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    asset_dir = ROOT / 'frontend/public/data'
    rows = load_full_stock_rows(asset_dir)
    before = {s['ticker']: assess(s, args.as_of) for s in rows}
    targets = [s['ticker'] for s in rows if any(not outside_scope(m) and not m['coverage']['complete'] for m in before[s['ticker']].values())]
    report = {'evaluated_on': args.as_of.isoformat(), 'universe': len(rows), 'before': coverage(before),
              'targets': targets, 'collection': [], 'assessments_before': before}
    report_path = args.output_dir / 'collection.json'

    def checkpoint():
        report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')

    checkpoint()
    if args.collect:
        # SQLite's backup API makes a consistent recovery copy before writes.
        with sqlite3.connect(ROOT / 'data/invest_os.sqlite') as source, sqlite3.connect(args.output_dir / 'before.sqlite') as backup:
            source.backup(backup)
        provider = OpenDataProvider(include_filing_details=False, max_sec_archive_lookups=0)
        replacements = {}
        for index, ticker in enumerate(targets, 1):
            started = time.monotonic()
            try:
                with connect(ROOT / 'data') as conn:
                    previous = load_stock_open_data_snapshot(conn, ticker)
                    prices = load_stock_price_history(conn, ticker)
                if previous is None:
                    raise ValueError('Saved fundamentals are required')
                current = provider.get_open_data_snapshot(ticker, saved_snapshot=previous, saved_price_history=prices)
                current = retain_verified_history(current, previous)
                price = current.price_opportunity['current_price']
                current = reprice_valuation(current, LatestPrice(ticker=ticker, price=price.value, as_of=price.as_of,
                    source=price.source, currency=current.price_currency or 'USD'))
                if current.price_opportunity != previous.price_opportunity:
                    raise ValueError('Saved price metrics changed')
                with connect(ROOT / 'data') as conn:
                    replace_stock_open_data_snapshot(conn, current)
                    conn.commit()
                replacements[ticker] = current.model_dump(mode='json')
                record = {'ticker': ticker, 'status': 'saved', 'source_notes': current.data_gaps,
                          'assessment': assess(replacements[ticker], args.as_of)}
            except Exception as exc:
                record = {'ticker': ticker, 'status': 'failed', 'error': str(exc)}
            record['seconds'] = round(time.monotonic() - started, 2)
            report['collection'].append(record)
            checkpoint()
            print(f'{index}/{len(targets)} {ticker}: {record["status"]} ({record["seconds"]}s)', flush=True)
        rows = [{**s, **replacements[s['ticker']]} if s['ticker'] in replacements else s for s in rows]
        for snapshot in rows:
            snapshot.pop('detail_path', None)
        write_stock_assets(asset_dir, rows)
    after = {s['ticker']: assess(s, args.as_of) for s in rows}
    report.update(after=coverage(after), assessments=after)
    checkpoint()
    write_coverage_report(args.output_dir, before, after, args.as_of)
    print(json.dumps({'before': report['before'], 'after': report['after']}, indent=2))


if __name__ == '__main__':
    main()
