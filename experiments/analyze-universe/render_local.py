"""Validate and publish assessments authored in this conversation; no model API."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from run import verify_inputs, write_json, parse_table
from audit_support import audit

COLORS = {'Strong': '🟢', 'Solid': '🟢', 'Average': '🟡', 'Weak': '🟠', 'Poor': '🔴',
          'Unknown': '⚪', 'Cheap': '🟢', 'Fair': '🟡', 'Expensive': '🔴'}


def flag_cell(metric, color):
    value, observed = metric.get('value'), metric.get('observed_count') or 0
    coverage = metric.get('coverage') or {}
    assessed = coverage.get('assessed', 0)
    outside_scope = bool(metric.get('checks')) and all(g['state'] == 'not_applicable' for g in metric['checks'])
    label = 'Not applicable' if outside_scope else str(value) if value is not None else f'{observed} detected' if assessed else 'Not assessed'
    detected = [group for group in metric['checks'] if group['state'] == 'flagged']
    tone = color if detected else 'unknown'
    cell = f'<td class="flags {color}-flags"><strong class="{tone}">{html.escape(label)}</strong>'
    if value is not None:
        cell += f'<small>of {metric["max_count"]} {"concern groups" if color == "red" else "positive rules"}</small>'
    elif outside_scope:
        cell += '<small>Outside these rules’ sector scope</small>'
    else:
        cell += f'<small>{coverage.get("assessed", 0)}/{coverage.get("applicable", coverage.get("total", 0))} assessed</small>'
    if detected:
        cell += '<ul class="flag-names">' + ''.join(f'<li>{html.escape(group["title"])}</li>' for group in detected) + '</ul>'
    elif value == 0:
        cell += '<small>None detected by these rules</small>'
    elif assessed and observed == 0:
        cell += '<small>None detected among assessed checks</small>'
    if color == 'red':
        clear = [group for group in metric['checks'] if group['state'] == 'clear']
        if clear:
            cell += '<ul class="assessed-checks">' + ''.join(
                f'<li>{html.escape(group["title"])} · No flag detected</li>' for group in clear) + '</ul>'
    if metric['checks']:
        cell += '<details><summary>All checks</summary>'
        for group in metric['checks']:
            state = {'flagged': 'Detected', 'clear': 'Rule not met' if color == 'green' else 'No flag detected',
                     'unassessed': 'Not assessed', 'not_applicable': 'Outside rule scope'}[group['state']]
            cell += f'<section><b>{html.escape(group["title"])} · {state}</b>'
            if group.get('reason'):
                cell += f'<small>{html.escape(group["reason"])}</small>'
            for branch in group['checks']:
                branch_state = 'Outside rule scope' if group['state'] == 'not_applicable' else {'flagged': 'Detected', 'clear': 'Rule not met' if color == 'green' else 'No flag detected', 'unassessed': 'Not assessed'}[branch['state']]
                cell += f'<p><b>{html.escape(branch["title"])} · {branch_state}</b><br>{html.escape(branch["formula"])}<br>{html.escape(branch["reason"])}</p>'
            cell += '</section>'
        if metric.get('notes'):
            cell += '<small>' + html.escape(metric['notes']) + '</small>'
        cell += '</details>'
    elif metric.get('notes'):
        cell += '<small>' + html.escape(metric['notes']) + '</small>'
    return cell + '</td>'


def unassessed_flags_cell(missing):
    cell = '<td class="flags-not-assessed">'
    if not any(missing.values()):
        return cell + '<span class="pass">None</span></td>'
    for color, checks in missing.items():
        if not checks:
            continue
        label = (f'{color.capitalize()}-flag assessment not available'
                 if any(c['id'] == 'assessment_unavailable' for c in checks)
                 else f'{len(checks)} {color}-flag check' + ('s' if len(checks) != 1 else '') + ' not assessed')
        cell += f'<strong>{html.escape(label)}</strong><ul>'
        for check in checks:
            group = f'{check["group"]}: ' if check['group'] and check['group'] != check['title'] else ''
            cell += f'<li>{html.escape(group + check["title"])}<small>{html.escape(check["reason"])}</small></li>'
        cell += '</ul>'
    return cell + '</td>'


def render(directory):
    manifest, prompt, _ = verify_inputs(directory)
    previous_metadata = json.loads((directory / 'result-metadata.json').read_text()) if (directory / 'result-metadata.json').exists() else {}
    compact = [json.loads(block) for block in re.findall(r'```json\n([^\n]+)\n```', prompt)]
    if [r['ticker'] for r in compact] != manifest['symbols']:
        raise ValueError('Archived Analyze JSON does not match the frozen universe')
    inputs = {r['ticker']: r for r in compact}
    support = json.loads(subprocess.run(
        ['node', str(Path(__file__).with_name('support_context.cjs')), str(directory)],
        check=True, capture_output=True, text=True).stdout)
    if set(support['stocks']) != set(inputs):
        raise ValueError('Support context must cover the frozen universe')
    write_json(directory / 'support-context.json', support)
    assessments_path = directory / 'local-assessments.tsv'
    with assessments_path.open(newline='') as f:
        assessments = list(csv.DictReader(f, delimiter='\t'))
    order_path = directory / 'local-rank-order.txt'
    order = order_path.read_text().split()
    for symbols in [[r['symbol'] for r in assessments], order]:
        if len(symbols) != manifest['count'] or len(set(symbols)) != len(symbols) or set(symbols) != set(inputs):
            raise ValueError('Every universe stock must appear exactly once in assessments and ordering')
    assessed = {r['symbol']: r for r in assessments}
    rows = [{'rank': i, 'symbol': symbol, 'stock': symbol,
        **{key: assessed[symbol][key] for key in ('business_quality', 'valuation', 'rationale')}}
        for i, symbol in enumerate(order, 1)]
    # The order is a recorded qualitative judgment; this script calculates no investment score.
    table = '| Rank | Stock | Business quality | Valuation | Rationale |\n| --- | --- | --- | --- | --- |\n'
    for row in rows:
        table += f"| {row['rank']} | {row['symbol']} | {row['business_quality']} | {row['valuation']} | {row['rationale']} |\n"
    validated = parse_table(table, manifest['symbols'])
    if validated != rows:
        raise ValueError('Table round-trip changed assessments')
    research = json.loads((directory / 'research-notes.json').read_text())
    evidence = directory / 'evidence'
    evidence.mkdir(exist_ok=True)
    for stock in compact:
        write_json(evidence / f"{stock['ticker']}.json", stock)
    preamble = (
        '# Full-universe Analyze — 200 stocks\n\n'
        'Analyzed here in the Codex conversation on 25 October 2026. '
        'All saved market quotes are dated 23 October 2026; each company’s financial date appears in its evidence link.\n\n'
        'The input is the exact existing static Analyze dataset and formatter, with the unchanged investment-analysis '
        'instructions. Companies were reviewed in sections and then compared qualitatively across the whole universe. '
        'Business quality and valuation receive equal importance; no numerical investment score was introduced. '
        'The order is an explicit analytical judgment, not an output from a replacement deterministic formula. '
        'Individual assessments were completed before assigning the global order.\n\n'
        '**Evidence limits:** These are provisional snapshot-based judgments. Static Analyze supplies one fundamentals '
        'quarter, 12 revenue quarters and two annual rows. Dated forward EPS is unavailable; no forward forecast was invented. '
        'Conflicting periods, share units, non-operating earnings and financial-sector comparability are reflected in the '
        'rationales or Unknown tags. Unknown is uncertainty, not an automatic poor-quality or cheap classification. '
        'Technical support context is retained in every evidence record; it does not establish intrinsic value. '
        'Primary-source checks cover six selected companies, not the whole universe; quotes, source inputs and sustainable '
        'earnings have not all been independently verified. New findings are recorded separately without altering supplied metrics. '
        'See [research notes](research-notes.json).\n\n'
        'No deterministic selection was applied before analysis and filter membership was not used to assign ranks. '
        'The independent control is retained for a later comparison. This is selection research, not realized-return validation.\n\n'
    )
    display = '| Rank | Stock | Business quality | Valuation | Rationale |\n| --- | --- | --- | --- | --- |\n'
    for row in rows:
        symbol = row['symbol']
        fact_link = f"[data {inputs[symbol]['financial_as_of']}](evidence/{symbol}.json)"
        checked = research['companies'].get(symbol)
        ir_link = f" [IR {checked['date']}]({checked['url']})" if checked else ''
        display += f"| {row['rank']} | {symbol} | {COLORS[row['business_quality']]} {row['business_quality']} | {COLORS[row['valuation']]} {row['valuation']} | {row['rationale']} {fact_link}{ir_link} |\n"
    (directory / 'ranking.md').write_text(preamble + display)
    write_json(directory / 'ranking.json', rows)
    with (directory / 'ranking.csv').open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Rank', 'Stock', 'Business quality', 'Valuation', 'Rationale'])
        writer.writerows([r['rank'], r['symbol'], r['business_quality'], r['valuation'], r['rationale']] for r in rows)
    audit_result = audit(directory)
    css = ('body{font:15px system-ui;background:#111922;color:#e9eff5;margin:24px}h1{font-size:26px}'
        'p{max-width:1100px;line-height:1.6}a{color:#9acbff}table{border-collapse:collapse;width:100%}'
        'td,th{padding:12px;border-bottom:1px solid #344550;text-align:left;vertical-align:top}'
        'th{position:sticky;top:0;background:#111922}td:last-child{min-width:340px}'
        'input{font:inherit;padding:12px;width:min(85vw,420px);margin:16px 0}small{display:block;margin-top:8px;color:#adbed0}'
        '.Strong,.Solid,.Cheap{color:#89ddae}.Average,.Fair{color:#f3ce82}.Weak{color:#f3ae82}.Expensive,.Poor{color:#ff9a9a}.Unknown{color:#bcc6d0}')
    css += ('.support{min-width:165px}.support-at{color:#89ddae}.support-near{color:#f3ce82}'
        '.support-above,.support-unknown{color:#bcc6d0}.support details{font-size:12px;margin-top:8px}'
        '.support summary{cursor:pointer;color:#9acbff}.support ul{padding-left:16px;line-height:1.7}')
    css += ('.controls{display:flex;flex-wrap:wrap;gap:16px;align-items:center;margin:16px 0}'
        '.controls input[type=checkbox]{width:auto;margin:0 6px 0 0}.controls select{padding:10px;font:inherit}'
        '.financial{min-width:200px}.pass{color:#89ddae}.fail{color:#ff9a9a}.unknown{color:#bcc6d0}'
        '.financial small{line-height:1.6}.financial .reason{color:#e3bba3}')
    css += ('.flags{min-width:195px;max-width:260px}.flags>strong{font-size:22px}'
        '.red{color:#ff9a9a}.green{color:#89ddae}.flag-names{padding-left:18px;line-height:1.5}'
        '.flags details{font-size:12px;margin-top:12px}.flags summary{cursor:pointer;color:#9acbff}'
        '.flags section{margin:14px 0}.flags section p{line-height:1.6}'
        '.flags>small:last-child{font-size:11px;line-height:1.5}')
    css += ('.assessed-checks{padding-left:18px;font-size:12px;line-height:1.5;color:#adbed0}'
        '.flags-not-assessed{min-width:220px;max-width:300px;color:#e3bba3}'
        '.flags-not-assessed ul{padding-left:18px;font-size:12px;line-height:1.5}'
        '.flags-not-assessed small{font-size:11px}')
    assets = Path(__file__).parent
    playground = json.loads(subprocess.run(
        ['node', str(assets / 'filter_playground.cjs'), str(directory)],
        check=True, capture_output=True, text=True).stdout)
    css += (assets / 'filter_playground.css').read_text()
    document = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Invest-OS: filter playground</title><style>' + css + '</style></head><body>')
    document += (assets / 'filter_playground.html').read_text()
    document += '<div class="table-wrap"><table><thead><tr>'
    document += ''.join('<th>' + h + '</th>' for h in ['Original rank','Stock','Red flags','Green flags','flags_not_assessed','Business quality','Valuation','Proximity to support','Three financial rules','Rationale']) + '</tr></thead><tbody>'
    for row in rows:
        symbol = row['symbol']
        checked = research['companies'].get(symbol)
        links = f'<a href="evidence/{html.escape(symbol)}.json">Original analysis data: {html.escape(inputs[symbol]["financial_as_of"])}</a>'
        if checked:
            links += f' · <a href="{html.escape(checked["url"],quote=True)}">Company release: {checked["date"]}</a>'
        context = support['stocks'][symbol]
        nearest = context['nearest']
        def distance(value):
            return f'{value:+.1f}%'
        if nearest:
            status_class = {'At Support': 'support-at', 'Near Support': 'support-near', 'Above Support': 'support-above'}[nearest['status']]
            support_cell = (f'<td class="support"><span class="{status_class}">{nearest["status"]}</span>'
                f'<small>{nearest["timeframe"]} · {distance(nearest["distance_pct"])} from midpoint</small>'
                f'<details><summary>All {len(context["timeframes"])} valid timeframes</summary><ul>')
            for timeframe in context['timeframes']:
                bounds = '–'.join(f'{v:,.2f}' for v in timeframe['zone'])
                support_cell += (f'<li>{timeframe["timeframe"]}: {timeframe["status"]}, {distance(timeframe["distance_pct"])}'
                    f'<br>Zone {html.escape(context["currency"] or "")} {bounds}</li>')
            support_cell += '</ul></details></td>'
        else:
            support_cell = '<td class="support support-unknown">Unknown<small>No valid support zone</small></td>'
        checked_rules = audit_result['stocks'][symbol]
        passes = checked_rules['passes_financial_rules']
        financial_cell = f'<td class="financial"><strong class="{"pass" if passes else "fail"}">{"Pass all three" if passes else "Does not pass"}</strong><small>'
        for field, label in [('revenue','Growth'),('operating_margin','Operating margin'),('red_flag_count','Red flags')]:
            rule = checked_rules['rules'][field]
            value = rule['value']
            value_label = 'Unknown' if value is None else str(int(value)) if field == 'red_flag_count' else f'{value:.2f}%'
            if field == 'red_flag_count' and value is None:
                flag_metric = checked_rules['flag_metrics'][field]
                coverage = flag_metric.get('coverage') or {}
                if coverage.get('assessed', 0):
                    value_label = f'{flag_metric["observed_count"]} detected · {coverage["assessed"]}/{coverage.get("applicable", coverage.get("total", 0))} assessed'
            financial_cell += f'<span class="{rule["status"].lower()}">{label}: {value_label}</span><br>'
        financial_cell += '</small>'
        if audit_result['financial_refresh']:
            financial_cell += f'<small><a href="../../../../frontend/public/data/open-data/snapshots/{html.escape(symbol)}.json">Refreshed financial data</a></small>'
        if checked_rules['exclusion_reasons']:
            reasons = [reason.replace('Red flags: incomplete assessment', 'Unassessed red-flag checks: see flags_not_assessed')
                       for reason in checked_rules['exclusion_reasons']]
            financial_cell += '<small class="reason">' + html.escape('; '.join(reasons)) + '</small>'
        financial_cell += '</td>'
        supported = checked_rules['at_or_near_support']
        document += (f'<tr data-symbol="{html.escape(symbol, quote=True)}" data-support="{int(supported)}" data-financial="{"pass" if passes else "fail"}"><td>{row["rank"]}</td><td><strong>{html.escape(symbol)}</strong><small>{html.escape(inputs[symbol]["company"] or symbol)}</small></td>'
            + flag_cell(checked_rules['flag_metrics']['red_flag_count'], 'red')
            + flag_cell(checked_rules['flag_metrics']['green_flag_count'], 'green')
            + unassessed_flags_cell(checked_rules['flags_not_assessed']) +
            f'<td class="{row["business_quality"]}">{row["business_quality"]}</td><td class="{row["valuation"]}">{row["valuation"]}</td>'
            + support_cell + financial_cell +
            f'<td>{html.escape(row["rationale"])}<small>{links}</small></td></tr>')
    # Inline the UI and data so the experiment also works directly over file://.
    payload = json.dumps(playground, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')
    document += ('</tbody></table></div><script id="playground-data" type="application/json">'
        + payload + '</script><script>' + (assets / 'filter_playground.js').read_text() + '</script></body></html>')
    (directory / 'ranking.html').write_text(document)
    metadata = {'status': 'complete', 'execution': 'Analysis authored in the current Codex conversation; no successful Gemini generation',
        'completed_at': previous_metadata.get('completed_at') or datetime.now(timezone.utc).isoformat(), 'count': len(rows),
        'display_financial_evaluated_on': audit_result['evaluated_on'],
        'model_version': 'Current conversation; exact model version not exposed in the artifact',
        'input_prompt_sha256': manifest['prompt_sha256'], 'input_dataset_sha256': manifest['dataset_sha256'],
        'assessments_sha256': hashlib.sha256(assessments_path.read_bytes()).hexdigest(),
        'rank_order_sha256': hashlib.sha256(order_path.read_bytes()).hexdigest(),
        'research_notes_sha256': hashlib.sha256((directory / 'research-notes.json').read_bytes()).hexdigest(),
        'method': 'Independent qualitative assessments followed by global comparison; equal importance to quality and valuation; no numerical score',
        'single_full_context_request': False, 'external_research_companies': list(research['companies']),
        'independently_verified_quotes': False, 'deterministic_membership_used_for_rank': False,
        'validation': {'every_stock_once': True, 'consecutive_ranks': True, 'valid_tags': True, 'five_columns': True}}
    write_json(directory / 'result-metadata.json', metadata)
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    rows = render(parser.parse_args().run_dir.resolve())
    print(f'Published {len(rows)} validated conversation-authored assessments and global ranks.')
