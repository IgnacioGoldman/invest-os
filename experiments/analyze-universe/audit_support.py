"""Explain support eligibility and each of the three existing financial rules."""
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
from evaluate_saved_filters import condition_matches, expression_matches
from evaluate_filters import expression, numeric

RULES = [
    ('revenue', 'Revenue growth', numeric('revenue', 'gt', 0)),
    ('operating_margin', 'Operating margin', numeric('operating_margin', 'gt', 0)),
    ('red_flag_count', 'Red flags', numeric('red_flag_count', 'lte', 1)),
]


def audit(directory):
    manifest, _, snapshots = verify_inputs(directory)
    today = datetime.fromisoformat(manifest['prepared_at'].replace('Z', '+00:00')).date()
    ranked = json.loads((directory / 'ranking.json').read_text())
    by_symbol = {s['ticker']: s for s in snapshots}
    support = json.loads((directory / 'support-context.json').read_text())
    if support['prepared_at'] != manifest['prepared_at']:
        raise ValueError('Support and financial checks must use the same frozen date')
    stocks = {}
    for row in ranked:
        symbol = row['symbol']
        snapshot = by_symbol[symbol]
        at_support = expression_matches(snapshot, expression([]), today)
        nearest = support['stocks'][symbol]['nearest']
        if at_support != bool(nearest and nearest['status'] in {'At Support','Near Support'}):
            raise ValueError('Support display disagrees with existing filter evaluator')
        rules = {}
        for field, label, condition in RULES:
            metric = snapshot.get('screening', {}).get('metrics', {}).get(field, {})
            value = metric.get('value')
            known = (isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)
                and metric.get('validated') and str(metric.get('valid_until') or '') >= today.isoformat())
            if field == 'red_flag_count':
                known = known and metric.get('coverage', {}).get('complete') and metric.get('assessment_version') == 2
            passes = condition_matches(snapshot, condition, today)
            if passes:
                status, reason = 'Pass', ''
            elif not known:
                status = 'Unknown'
                reason = f'{label}: incomplete assessment' if field == 'red_flag_count' else f'{label}: unavailable or unvalidated'
            else:
                status = 'Fail'
                reason = f'{label}: {value:g} exceeds 1' if field == 'red_flag_count' else f'{label}: {value:.2f}% is not above 0%'
            rules[field] = {'value':value if known else None,'passes':passes,'status':status,'reason':reason}
        all_pass = all(r['passes'] for r in rules.values())
        expected = expression_matches(snapshot, expression([rule for _,_,rule in RULES]), today)
        if expected != (at_support and all_pass):
            raise ValueError('Per-rule explanations disagree with the combined existing filter')
        stocks[symbol] = {**row, 'at_or_near_support':at_support, 'support':nearest,
            'passes_financial_rules':all_pass, 'rules':rules,
            'exclusion_reasons':[r['reason'] for r in rules.values() if not r['passes']]}
    supported = [stocks[r['symbol']] for r in ranked if stocks[r['symbol']]['at_or_near_support']]
    for i, row in enumerate(supported,1):
        row['support_rank'] = i
    passed = [r for r in supported if r['passes_financial_rules']]
    excluded = [r for r in supported if not r['passes_financial_rules']]
    result = {'evaluated_on':today.isoformat(),'market_dates':manifest['market_dates'],
        'dataset_sha256':manifest['dataset_sha256'], 'universe':len(ranked), 'at_or_near_support':len(supported),
        'pass_all_three':len(passed),'do_not_pass':len(excluded),
        'support_symbols':[r['symbol'] for r in supported],
        'retention_within_support_list':{f'top_{n}':{'retained':sum(r['passes_financial_rules'] for r in supported[:n]),'total':len(supported[:n])}
            for n in (10,20,32)},
        'bottom_half_retained':sum(r['passes_financial_rules'] for r in supported[32:]),
        'stocks':stocks}
    output = directory / 'filter-research'
    output.mkdir(exist_ok=True)
    write_json(output / 'support-audit.json', result)
    with (output / 'support-audit.csv').open('w',newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Rank within support list','Original rank','Stock','Revenue Growth YoY (%)','Operating Margin (%)','Red Flag Count','Pass all three?','Reasons','Business quality','Valuation'])
        for row in supported:
            writer.writerow([row['support_rank'],row['rank'],row['symbol'],
                *[row['rules'][field]['value'] if row['rules'][field]['value'] is not None else 'Unknown' for field,_,_ in RULES],
                'Yes' if row['passes_financial_rules'] else 'No','; '.join(row['exclusion_reasons']),row['business_quality'],row['valuation']])
    lines = ['# Support list and the three financial rules','',
        f"**{len(ranked)} stocks → {len(supported)} at/near any support → {len(passed)} pass all three rules; {len(excluded)} do not pass.**",'',
        'Support uses ANY existing timeframe. The financial rules are revenue growth >0%, operating margin >0%, and a complete validated red-flag count ≤1. Checks use the frozen experiment date. Original ranks below refer to the 200-stock AI ranking; order within the smaller support list is shown separately. Unknown inputs do not pass a numeric rule.','']
    for title,rows in [('Pass all three',passed),('Do not pass all three',excluded)]:
        lines.extend([f'## {title}', '', '| Support-list position | Original rank | Stock | Growth | Operating margin | Flags | Reason if excluded |',
            '| --- | --- | --- | --- | --- | --- | --- |'])
        for row in rows:
            values = [row['rules'][field]['value'] for field,_,_ in RULES]
            formatted = ['Unknown' if value is None else f'{value:.2f}%' if i<2 else str(int(value)) for i,value in enumerate(values)]
            lines.append(f"| {row['support_rank']} | {row['rank']} | {row['symbol']} | {' | '.join(formatted)} | {'; '.join(row['exclusion_reasons']) or '—'} |")
        lines.append('')
    (output / 'support-audit.md').write_text('\n'.join(lines))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,required=True)
    result = audit(parser.parse_args().run_dir.resolve())
    print(f"{result['universe']} → {result['at_or_near_support']} at/near support → {result['pass_all_three']} pass; {result['do_not_pass']} excluded")
