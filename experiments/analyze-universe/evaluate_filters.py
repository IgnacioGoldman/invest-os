"""Compare a small explicit set of screens with the frozen qualitative review."""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime
from pathlib import Path

from run import ROOT, verify_inputs, write_json

sys.path.insert(0, str(ROOT / 'scripts'))
from evaluate_saved_filters import expression_matches


def numeric(field, comparison, value):
    return {'field': field, 'comparison': comparison, 'value': str(value)}


def expression(rules, support_values=('At Support', 'Near Support')):
    groups = [{'id': f'rule-{i}', 'operator': 'and', 'conditions': [dict(rule, id=f'condition-{i}')]} for i, rule in enumerate(rules)]
    groups.append({'id': 'any-support', 'operator': 'or', 'conditions': [
        {'id': f'{field}-{value}', 'field': f'support_{field}', 'value': value}
        for field in ('1m', '3m', '6m', '1y', '2y', '5y') for value in support_values]})
    return {'operator': 'and', 'groups': groups}


def evaluate(directory):
    manifest, _, snapshots = verify_inputs(directory)
    today = datetime.fromisoformat(manifest['prepared_at'].replace('Z', '+00:00')).date()
    rank_rows = json.loads((directory / 'ranking.json').read_text())
    ranked = {r['symbol']: r for r in rank_rows}
    if len(ranked) != len(snapshots) or set(ranked) != set(manifest['symbols']):
        raise ValueError('Ranking and frozen universe must match')
    support = expression([])
    wanted = {s['ticker'] for s in snapshots if expression_matches(s, support, today)
        and ranked[s['ticker']]['business_quality'] in {'Strong', 'Solid'}
        and ranked[s['ticker']]['valuation'] in {'Cheap', 'Fair'}}
    profitable = numeric('operating_margin', 'gt', 0)
    growing = numeric('revenue', 'gt', 0)
    zero_flags = numeric('red_flag_count', 'eq', 0)
    one_flag = numeric('red_flag_count', 'lte', 1)
    base = [growing, profitable, one_flag]
    definitions = [
        ('support_only', 'At/near any support only', [], []),
        ('growth8_zero_flags', 'Growth ≥8%, margin >0%, flags =0, support', [numeric('revenue','gte',8), profitable, zero_flags], []),
        ('positive_growth_zero_flags', 'Growth >0%, margin >0%, flags =0, support', [growing, profitable, zero_flags], []),
        ('positive_growth_one_flag', 'Growth >0%, margin >0%, flags ≤1, support', base, []),
        ('margin10_one_flag', 'Growth >0%, margin ≥10%, flags ≤1, support', [growing, numeric('operating_margin','gte',10), one_flag], []),
        ('steady_growth_one_flag', 'Positive growth/profit, flags ≤1, steady consistency, support', [*base, {'field':'revenue_consistency','value':'Steady'}], []),
        ('nondeclining_margin', 'Positive growth/profit, flags ≤1, margin trend ≥0 pp, support', [*base, numeric('operating_margin_trend','gte',0)], []),
        ('fcf_margin10', 'Base + TTM FCF margin ≥10%', base, [('fcf_margin','gte',10)]),
        ('fcf_yield3', 'Base + TTM FCF yield ≥3%', base, [('fcf_yield','gte',3)]),
        ('fcf_yield5', 'Base + TTM FCF yield ≥5%', base, [('fcf_yield','gte',5)]),
        ('fcf_margin10_yield3', 'Base + FCF margin ≥10% + FCF yield ≥3%', base, [('fcf_margin','gte',10), ('fcf_yield','gte',3)]),
        ('pe30', 'Base + positive trailing P/E ≤30', base, [('pe','lte',30)]),
        ('pe30_fcf10', 'Base + positive P/E ≤30 + FCF margin ≥10%', base, [('pe','lte',30),('fcf_margin','gte',10)]),
    ]

    def contextual(snapshot, field):
        screening = snapshot.get('screening', {})
        if field == 'fcf_yield':
            metric = screening.get('financial_details', {}).get('fcf_yield', {})
        elif field == 'fcf_margin':
            metric = screening.get('metrics', {}).get('fcf_margin', {})
        else:
            metric = snapshot.get('metrics', {}).get('pe_ttm', {})
        value = metric.get('value')
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not metric.get('source'):
            return None
        if field == 'pe' and value <= 0:
            return None
        return value

    def context_matches(snapshot, conditions):
        for field, comparison, threshold in conditions:
            value = contextual(snapshot, field)
            if value is None or not (value >= threshold if comparison == 'gte' else value <= threshold):
                return False
        return True

    results = []
    for key, name, rules, conditions in definitions:
        screen = expression(rules)
        selected = sorted((s['ticker'] for s in snapshots if expression_matches(s, screen, today)
            and context_matches(s, conditions)), key=lambda symbol: ranked[symbol]['rank'])
        selected_set = set(selected)
        results.append({'key':key,'name':name,'available_in_current_builder':not conditions,
            'expression':screen,'research_only_context_conditions':conditions,
            'count':len(selected),'requested_tag_matches':len(selected_set & wanted),
            'requested_tag_precision_pct':round(100*len(selected_set & wanted)/len(selected),1) if selected else None,
            'requested_tag_recall_pct':round(100*len(selected_set & wanted)/len(wanted),1) if wanted else None,
            'top20':sum(ranked[s]['rank']<=20 for s in selected),
            'top50':sum(ranked[s]['rank']<=50 for s in selected),
            'bottom50':sum(ranked[s]['rank']>=151 for s in selected),
            'selected':[ranked[s] for s in selected],
            'missed_requested':sorted(wanted-selected_set,key=lambda s:ranked[s]['rank'])})
    report = {'date':today.isoformat(),'dataset_sha256':manifest['dataset_sha256'],
        'support_definition':'At Support or Near Support on ANY of 1M, 3M, 6M, 1Y, 2Y, 5Y; existing evaluator, frozen date',
        'reference':'Previously authored qualitative review; not independent return outcomes',
        'limitations':'All comparisons use the same one-date dataset and review. Thresholds are illustrative, not optimized or out-of-sample validated. Context conditions use supplied sourced finite projections and retain existing warnings; they do not certify earnings normalization, quote/share consistency or sector suitability.',
        'requested_count':len(wanted),'requested_symbols':sorted(wanted,key=lambda s:ranked[s]['rank']),
        'results':results}
    output = directory / 'filter-research'
    output.mkdir(exist_ok=True)
    write_json(output / 'evaluation.json', report)
    support_context = json.loads((directory / 'support-context.json').read_text())
    if support_context['prepared_at'] != manifest['prepared_at']:
        raise ValueError('Support display and filter evaluation dates differ')
    cohort = [{**ranked[s], 'support':support_context['stocks'][s]['nearest']}
        for s in report['requested_symbols']]
    write_json(output / 'requested-cohort.json', cohort)
    with (output / 'requested-cohort.csv').open('w',newline='') as f:
        writer=csv.writer(f)
        writer.writerow(['Rank','Stock','Business quality','Valuation','Support status','Timeframe','Distance from support midpoint (%)'])
        writer.writerows([r['rank'],r['symbol'],r['business_quality'],r['valuation'],
            r['support']['status'],r['support']['timeframe'],r['support']['distance_pct']] for r in cohort)
    lines = ['# Filter comparison on the frozen 200-stock review', '',
        f"Evaluation date: {today}. {len(wanted)} stocks match Strong/Solid business quality, Cheap/Fair valuation, and at/near any support in the saved review.", '',
        '**In-sample comparison only.** The review is a subjective reference using the same financial inputs, not future investment outcomes. No screen guarantees a high rank or future returns. Contextual extensions below are research predicates and are not available in the current filter builder. Missing values fail those predicates; finite values with warnings are not independently validated.', '',
        '| Screen | Current builder? | Selected | Requested tags | Top 20 | Top 50 | Bottom 50 |',
        '| --- | --- | --- | --- | --- | --- | --- |']
    for r in results:
        lines.append(f"| {r['name']} | {'Yes' if r['available_in_current_builder'] else 'No'} | {r['count']} | {r['requested_tag_matches']}/{r['count']} | {r['top20']} | {r['top50']} | {r['bottom50']} |")
    for r in results:
        lines.extend(['', f"## {r['name']}", '',
            'Matches: ' + ', '.join(f"{s['symbol']} (#{s['rank']}; {s['business_quality']}/{s['valuation']})" for s in r['selected']) + '.',
            '', 'Requested matches missed: ' + ', '.join(f"{s} (#{ranked[s]['rank']})" for s in r['missed_requested']) + '.'])
    (output / 'comparison.md').write_text('\n'.join(lines)+'\n')
    for r in results:
        if r['available_in_current_builder']:
            write_json(output / f"{r['key']}.json", {'name':r['name'],'expression':r['expression']})
    for r in results:
        print(r['key'],r['count'],'tag matches',r['requested_tag_matches'],'top20',r['top20'],'top50',r['top50'],'bottom50',r['bottom50'])
    print('Requested tag + support symbols:', ', '.join(report['requested_symbols']))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,required=True)
    evaluate(parser.parse_args().run_dir.resolve())
