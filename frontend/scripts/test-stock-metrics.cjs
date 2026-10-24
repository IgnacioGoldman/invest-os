const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const ts = require('typescript');
const { spawnSync } = require('node:child_process');

// Use the app's existing TypeScript dependency; the production build checks types.
require.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText, filename);
const { STOCK_METRICS, SUPPORT_TIMEFRAMES, stockMetricForField } = require('../src/stockMetrics.ts');
const { supportSignal } = require('../src/metricStatus.ts');
const { metricRulesFromExpression, expressionFromMetricRules, groupSupportTimeframes } = require('../src/metricFilterRules.ts');
const stocks = JSON.parse(fs.readFileSync(path.join(__dirname, '../public/data/open-data/stocks.json'), 'utf8'));

test('every card exposes selectable statuses using its actual calculation', () => {
  const keys = STOCK_METRICS.map(metric => metric.key);
  assert.equal(new Set(keys).size, keys.length);
  for (const metric of STOCK_METRICS) {
    assert.ok(metric.options.length > 0, metric.title);
    assert.equal(new Set(metric.options).size, metric.options.length);
    const missing = structuredClone(stocks[0]);
    missing.business_health.revenue_growth_yoy = { value: null, tier: 'unavailable_open_free' };
    missing.business_health.eps_gaap_growth_yoy = { value: null, tier: 'unavailable_open_free' };
    missing.industry_relative_strength = undefined;
    for (const stock of [...stocks, missing]) {
      const signal = metric.getSignal(stock);
      assert.ok(metric.options.includes(signal.label), `${metric.title}: ${signal.label} is missing from the filter`);
    }
    if (metric.field !== 'support') assert.equal(stockMetricForField(metric.field), metric);
  }
  assert.equal(stockMetricForField('valuation'), undefined);
});

test('all support timeframes resolve to the stock card definition', () => {
  const support = STOCK_METRICS.find(metric => metric.key === 'support');
  for (const timeframe of SUPPORT_TIMEFRAMES) assert.equal(stockMetricForField(timeframe.field), support);
});

test('only six financial cards are primary; retired metrics are absent', () => {
  assert.deepEqual(STOCK_METRICS.filter(metric => !metric.context).map(metric => metric.key),
    ['revenue', 'momentum', 'operating_margin', 'fcf_margin', 'forward_pe', 'balance_sheet']);
  for (const field of ['eps', 'industry_strength', 'valuation']) assert.equal(stockMetricForField(field), undefined);
});

test('unsupported Forward P/E is Unknown regardless of a raw low multiple', () => {
  const stock = structuredClone(stocks[0]);
  stock.valuation.forward_pe = { value: 15 };
  delete stock.screening;
  assert.equal(stockMetricForField('forward_pe').getSignal(stock).label, 'Unknown');
  assert.equal(stockMetricForField('forward_pe').getValue(stock), null);
});

test('dated estimates expire without a refresh and never produce valuation ratings', () => {
  const stock = structuredClone(stocks[0]);
  const today = new Date().toISOString().slice(0, 10);
  stock.screening = { metrics: { forward_pe: { value: 20, status: 'Estimate', forecast_horizon: 'FY2027 annual', estimate_as_of: today, price_as_of: today, warnings: [] } } };
  const metric = stockMetricForField('forward_pe');
  assert.equal(metric.getValue(stock), 20);
  assert.equal(metric.getSignal(stock).label, 'Estimate');
  stock.screening.metrics.forward_pe.estimate_as_of = '2000-01-01';
  assert.equal(metric.getValue(stock), null);
  assert.equal(metric.getSignal(stock).label, 'Unknown');
});

test('earnings and support use neutral styling, including missing support', () => {
  const { metricSignal } = require('../src/metricStatus.ts');
  for (const label of ['Inside Support Zone', 'Near Support', 'Above Support', 'This week', 'Next 30 days', 'Estimate', 'Computed Metric']) assert.equal(metricSignal(label).tone, 'neutral');
  assert.equal(supportSignal(null).label, 'Unknown');
  assert.equal(supportSignal(0).label, 'Inside Support Zone');
  assert.equal(metricSignal('Accelerating').tone, 'positive');
});

test('retired and obsolete quality rules disable the whole saved expression', () => {
  const { hasDisabledFilter } = require('../src/stockMetrics.ts');
  for (const [field, value] of [['eps', 'Strong'], ['valuation', 'Cheap'], ['industry_strength', 'Ahead of market'], ['fcf_margin', 'Strong']]) {
    assert.equal(hasDisabledFilter({ operator: 'or', groups: [{ conditions: [{ field, value }, { field: 'revenue', value: 'High Growth' }] }] }), true);
  }
});

test('AI research preserves dropped raw figures, source metadata and anomaly warnings', () => {
  const { prepareStockAnalysis } = require('../src/aiAnalysis.ts');
  const stock = JSON.parse(fs.readFileSync(path.join(__dirname, '../public/data/open-data/snapshots/GOOG.json'), 'utf8'));
  const prompt = prepareStockAnalysis([stock], 'All stocks').prompt;
  for (const text of ['raw_financial_metrics', 'eps_gaap_growth_yoy', 'peg', 'net_margin', 'screening_metrics', 'net income exceeds operating income', 'not independent verification']) assert.ok(prompt.includes(text), text);
});

test('watchlist badge calculations agree with every stock-card filter', () => {
  const fresh = structuredClone(stocks[0]);
  const today = new Date().toISOString().slice(0, 10);
  fresh.price_opportunity.current_price.as_of = today;
  fresh.industry_relative_strength = { value: 7, end_date: today };
  const samples = [...stocks, fresh];
  const fields = STOCK_METRICS.flatMap(metric => metric.field === 'support' ? SUPPORT_TIMEFRAMES.map(timeframe => timeframe.field) : [metric.field]);
  const expected = samples.map(stock => fields.map(field => {
    const timeframe = SUPPORT_TIMEFRAMES.find(item => item.field === field);
    return timeframe ? supportSignal(stock.price_opportunity[timeframe.metric]?.value).label : stockMetricForField(field).getSignal(stock).label;
  }));
  const result = spawnSync('python3', ['-c', [
    'import json, sys',
    'from evaluate_saved_filters import signal_for',
    'payload = json.load(sys.stdin)',
    'print(json.dumps([[signal_for(stock, field) for field in payload["fields"]] for stock in payload["stocks"]]))',
  ].join('\n')], {
    cwd: path.join(__dirname, '../../scripts'),
    input: JSON.stringify({ stocks: samples, fields }),
    encoding: 'utf8',
    maxBuffer: 16 * 1024 * 1024,
  });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), expected);
});

test('editing saved support conditions groups matching values and preserves distinct requirements', () => {
  const rules = [
    { id: 'short', field: 'support_1m', values: ['Inside Support Zone', 'Near Support'] },
    { id: 'growth', field: 'revenue', values: ['High Growth'] },
    { id: 'long', field: 'support_5y', values: ['Near Support', 'Inside Support Zone'] },
    { id: 'medium', field: 'support_6m', values: ['Inside Support Zone'] },
  ];
  const grouped = groupSupportTimeframes(rules);
  assert.equal(grouped.length, 3);
  assert.deepEqual(grouped[0].timeframes, ['support_1m', 'support_5y']);
  assert.deepEqual(grouped[2].timeframes, ['support_6m']);
  assert.equal(rules[0].timeframes, undefined, 'opening the editor must not mutate the original rules');
  const saved = expressionFromMetricRules(grouped, { operator: 'and', groups: [] });
  const reopened = groupSupportTimeframes(metricRulesFromExpression(saved).rules);
  assert.deepEqual(reopened.map(({ field, values, timeframes }) => ({ field, values, timeframes })),
    grouped.map(({ field, values, timeframes }) => ({ field, values, timeframes })));
  const ids = saved.groups.flatMap(group => [group.id, ...group.conditions.map(condition => condition.id)]);
  assert.equal(new Set(ids).size, ids.length);
});

test('multiple selected timeframes require each timeframe and accept any selected value', () => {
  const expression = expressionFromMetricRules([
    { id: 'support', field: 'support_1m', timeframes: ['support_1m', 'support_5y'], values: ['Inside Support Zone', 'Near Support'] },
    { id: 'growth', field: 'revenue', values: ['High Growth', 'Moderate Growth'] },
  ], { operator: 'and', groups: [] });
  const samples = [
    [1, 1, 25, true], [1, 4, 12, true], [4, 1, 25, true], [4, 4, 25, true],
    [20, 1, 25, false], [1, 20, 25, false], [1, 1, -5, false], [null, 1, 25, false],
  ].map(([short, long, revenue, matches]) => {
    const stock = structuredClone(stocks[0]);
    stock.price_opportunity.support_1m_distance = { value: short };
    stock.price_opportunity.support_5y_distance = { value: long };
    stock.business_health.revenue_growth_yoy = { value: revenue };
    stock.screening.metrics.revenue = { value: revenue, status: revenue >= 20 ? "High Growth" : revenue >= 8 ? "Moderate Growth" : revenue >= 0 ? "Flat" : "Declining" };
    return { stock, matches };
  });
  const result = spawnSync('python3', ['-c', [
    'import json, sys',
    'from evaluate_saved_filters import expression_matches',
    'payload = json.load(sys.stdin)',
    'print(json.dumps([expression_matches(sample["stock"], payload["expression"]) for sample in payload["samples"]]))',
  ].join('\n')], {
    cwd: path.join(__dirname, '../../scripts'),
    input: JSON.stringify({ expression, samples }), encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), samples.map(sample => sample.matches));
});
