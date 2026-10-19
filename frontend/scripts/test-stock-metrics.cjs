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
const { createBuiltInPresetExpression, builtInPresetFor } = require('../src/builtInFilters.ts');
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

test('Forward P/E uses the earnings multiple even when other valuation measures are expensive', () => {
  const stock = structuredClone(stocks[0]);
  stock.valuation.forward_pe = { value: 15 };
  stock.valuation.price_to_sales = { value: 25 };
  assert.equal(stockMetricForField('forward_pe').getSignal(stock).label, 'Cheap');
});

test('industry statuses match the card and reject stale or mismatched dates', () => {
  const metric = stockMetricForField('industry_strength');
  const stock = structuredClone(stocks[0]);
  const today = new Date().toISOString().slice(0, 10);
  stock.price_opportunity.current_price.as_of = today;
  for (const [value, expected] of [[5, 'Ahead of market'], [4.99, 'In line with market'], [-4.99, 'In line with market'], [-5, 'Behind market'], [null, 'Unclear']]) {
    stock.industry_relative_strength = { value, end_date: today };
    assert.equal(metric.getSignal(stock).label, expected);
  }
  stock.industry_relative_strength = { value: 10, end_date: '2000-01-01' };
  stock.price_opportunity.current_price.as_of = '2000-01-01';
  assert.equal(metric.getSignal(stock).label, 'Unclear');
  stock.industry_relative_strength = { value: 10, end_date: today };
  assert.equal(metric.getSignal(stock).label, 'Unclear');
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

test('built-in filters use current card metrics and survive the simple builder unchanged', () => {
  for (const preset of ['support', 'pullback', 'earnings']) {
    const expression = createBuiltInPresetExpression(preset);
    const { rules, logicChanged } = metricRulesFromExpression(expression);
    assert.equal(logicChanged, false, `${preset} must use the builder's matching rules`);
    for (const rule of rules) {
      const metric = stockMetricForField(rule.field);
      assert.ok(metric, `${preset}: ${rule.field} must be a current stock-card metric`);
      for (const value of rule.values) assert.ok(metric.options.includes(value), `${rule.field}: ${value}`);
    }
    const saved = expressionFromMetricRules(groupSupportTimeframes(rules), expression);
    // IDs, icons, and display order must not affect preset recognition after editing.
    saved.icon = 'trend';
    saved.groups.reverse();
    for (const group of saved.groups) {
      group.id = 'new-group-id';
      group.conditions.reverse();
      for (const condition of group.conditions) condition.id = 'new-condition-id';
    }
    assert.equal(builtInPresetFor(saved), preset);
    saved.groups[0].conditions.pop();
    assert.equal(builtInPresetFor(saved), null, 'changing a selected value creates a custom filter');
  }
});

test('editing saved support conditions groups matching values and preserves distinct requirements', () => {
  const rules = [
    { id: 'short', field: 'support_1m', values: ['At support', 'Near support'] },
    { id: 'growth', field: 'revenue', values: ['Strong'] },
    { id: 'long', field: 'support_5y', values: ['Near support', 'At support'] },
    { id: 'medium', field: 'support_6m', values: ['At support'] },
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
    { id: 'support', field: 'support_1m', timeframes: ['support_1m', 'support_5y'], values: ['At support', 'Near support'] },
    { id: 'growth', field: 'revenue', values: ['Strong', 'Solid'] },
  ], { operator: 'and', groups: [] });
  const samples = [
    [1, 1, 25, true], [1, 4, 12, true], [4, 1, 25, true], [4, 4, 25, true],
    [20, 1, 25, false], [1, 20, 25, false], [1, 1, -5, false], [null, 1, 25, false],
  ].map(([short, long, revenue, matches]) => {
    const stock = structuredClone(stocks[0]);
    stock.price_opportunity.support_1m_distance = { value: short };
    stock.price_opportunity.support_5y_distance = { value: long };
    stock.business_health.revenue_growth_yoy = { value: revenue };
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

test('legacy support alternatives are not recognized as the updated built-in filter', () => {
  const expression = createBuiltInPresetExpression('pullback');
  const supportGroups = expression.groups.filter(group => group.conditions[0].field.startsWith('support_'));
  expression.groups = [
    { id: 'legacy-support', operator: 'or', conditions: supportGroups.flatMap(group => group.conditions) },
    ...expression.groups.filter(group => !supportGroups.includes(group)),
  ];
  assert.equal(builtInPresetFor(expression), null);
});

test('built-in screen expressions agree with the watchlist badge evaluator', () => {
  const presets = { 'builtin:support': 'support', 'builtin:pullback': 'pullback', 'builtin:earnings_this_week': 'earnings' };
  const expressions = Object.fromEntries(Object.entries(presets).map(([key, preset]) => {
    const expression = createBuiltInPresetExpression(preset);
    return [key, { operator: expression.operator, groups: expression.groups.map(group => ({
      operator: group.operator,
      conditions: group.conditions.map(({ field, value }) => ({ field, value })),
    })) }];
  }));
  const result = spawnSync('python3', ['-c', [
    'import json',
    'from evaluate_saved_filters import BUILT_IN_FILTERS',
    'print(json.dumps(BUILT_IN_FILTERS))',
  ].join('\n')], { cwd: path.join(__dirname, '../../scripts'), encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), expressions);
});
