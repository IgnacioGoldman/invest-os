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
const { STOCK_METRICS, SUPPORT_TIMEFRAMES, stockMetricForField, visibleStockMetrics, supportMetric } = require('../src/stockMetrics.ts');
const { metricRulesFromExpression, expressionFromMetricRules, groupSupportTimeframes } = require('../src/metricFilterRules.ts');
const stocks = JSON.parse(fs.readFileSync(path.join(__dirname, '../public/data/open-data/stocks.json'), 'utf8'));

test('every visible card exposes only factual selectable labels', () => {
  const forbidden = /^(Unknown|Needs Review|Computed Metric|Unavailable|Insufficient Data|Strong|Solid|Fair|Cheap|Attractive)$/;
  for (const metric of STOCK_METRICS) {
    assert.ok(metric.options.length > 0);
    for (const label of metric.options) assert.equal(forbidden.test(label), false, label);
    for (const stock of stocks) {
      if (metric.getValue(stock) != null) assert.ok(metric.options.includes(metric.getSignal(stock).label));
    }
  }
});

test('all support timeframes resolve to the shared context definition', () => {
  for (const timeframe of SUPPORT_TIMEFRAMES) assert.equal(stockMetricForField(timeframe.field), stockMetricForField('support'));
});

test('only four business-performance cards remain', () => {
  assert.deepEqual(STOCK_METRICS.filter(metric => !metric.context).map(metric => metric.key),
    ['revenue', 'momentum', 'operating_margin', 'operating_margin_trend']);
  for (const field of ['eps', 'industry_strength', 'valuation', 'fcf_margin', 'forward_pe', 'balance_sheet', 'gross_margin', 'price_to_sales', 'fcf_yield']) assert.equal(stockMetricForField(field), undefined);
});

test('GOOG displays the requested signed facts and comparable operating-margin trend', () => {
  const now = Date.now;
  Date.now = () => Date.parse('2026-10-24T12:00:00Z');
  try {
    const stock = stocks.find(s => s.ticker === 'GOOG');
    const cards = visibleStockMetrics(stock, false);
    assert.equal(cards.length, 4);
    const values = cards.map(m => [Number(m.getValue(stock).toFixed(2)), m.getSignal(stock).label]);
    assert.deepEqual(values, [[24.23, 'Growing'], [8, 'Accelerating'], [34.03, 'Profitable'], [1.6, 'Improving']]);
  } finally { Date.now = now; }
});

test('missing, invalid or expired business inputs remove cards instead of rendering placeholders', () => {
  const stock = structuredClone(stocks.find(s => s.ticker === 'GOOG'));
  delete stock.screening;
  assert.deepEqual(visibleStockMetrics(stock, false), []);
  stock.screening = { metrics: Object.fromEntries(['revenue', 'momentum', 'operating_margin', 'operating_margin_trend'].map(key => [key,
    { value: 5, status: 'Computed Metric', validated: true, valid_until: '2999-01-01' }])) };
  assert.deepEqual(visibleStockMetrics(stock, false), []);
  stock.screening.metrics.revenue = { value: 5, status: 'Growing', validated: true, valid_until: '2999-01-01' };
  assert.deepEqual(visibleStockMetrics(stock, false).map(m => m.key), ['revenue']);
  stock.screening.metrics.revenue.valid_until = '2000-01-01';
  assert.deepEqual(visibleStockMetrics(stock, false), []);
});

test('missing context is hidden; bare support distances do not establish a valid zone', () => {
  const stock = structuredClone(stocks[0]);
  stock.price_opportunity = { current_price: { value: 100, as_of: new Date().toISOString().slice(0,10) }, support_1m_distance: { value: 1 } };
  stock.metrics = {};
  assert.deepEqual(visibleStockMetrics(stock, true), []);
  assert.equal(supportMetric(stock), null);
});

test('earnings context requires a valid strictly future date and ordered window', () => {
  const { upcomingEarningsMetric } = require('../src/stockMetrics.ts');
  const now = Date.now;
  Date.now = () => Date.parse('2026-10-24T12:00:00Z');
  try {
    const stock = structuredClone(stocks[0]);
    for (const date of ['2026-02-30', '2026-10-24', '2026-10-23', '2026-11-03/2026-11-01']) {
      stock.price_opportunity.days_to_next_earnings = { value: 8, source: `yfinance:calendar:Earnings Date:${date}`, as_of: '2026-10-24' };
      assert.equal(upcomingEarningsMetric(stock).value, null);
    }
    stock.price_opportunity.days_to_next_earnings = { value: 4, source: 'yfinance:calendar:Earnings Date:2026-10-28', as_of: '2026-10-24' };
    assert.equal(upcomingEarningsMetric(stock).value, 4);
  } finally { Date.now = now; }
});

test('green identifies business direction, while all market context stays neutral', () => {
  const { metricSignal } = require('../src/metricStatus.ts');
  for (const label of ['Growing', 'Accelerating', 'Improving']) assert.equal(metricSignal(label).tone, 'positive');
  for (const label of ['Profitable', 'Stable', 'Steady', 'Flat', 'Inside Support Zone', 'Near Support', 'Above Support', 'This week', 'Next 30 days']) assert.equal(metricSignal(label).tone, 'neutral');
});

test('retired and obsolete quality rules disable the whole saved expression', () => {
  const { hasDisabledFilter } = require('../src/stockMetrics.ts');
  for (const [field, value] of [['eps', 'Strong'], ['valuation', 'Cheap'], ['industry_strength', 'Ahead of market'], ['fcf_margin', 'Strong'], ['forward_pe', 'Estimate'], ['balance_sheet', 'Computed Metric']]) {
    assert.equal(hasDisabledFilter({ operator: 'or', groups: [{ conditions: [{ field, value }, { field: 'revenue', value: 'Growing' }] }] }), true);
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
    return timeframe ? supportMetric(stock, timeframe.field)?.signal.label ?? "Unknown" : stockMetricForField(field).getSignal(stock).label;
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
    { id: 'growth', field: 'revenue', values: ['Growing'] },
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
    { id: 'growth', field: 'revenue', values: ['Growing'] },
  ], { operator: 'and', groups: [] });
  const samples = [
    [1, 1, 25, true], [1, 4, 12, true], [4, 1, 25, true], [4, 4, 25, true],
    [20, 1, 25, false], [1, 20, 25, false], [1, 1, -5, false], [null, 1, 25, false],
  ].map(([short, long, revenue, matches]) => {
    const stock = structuredClone(stocks[0]);
    const today = new Date().toISOString().slice(0,10);
    stock.price_opportunity.current_price = { value: 100, as_of: today };
    const support = value => {
      const midpoint = value == null ? 100 : 100 / (1 + value / 100);
      return { value, as_of: today, source: 'yfinance_history', tier: 'computed_from_public_facts', notes: `Support zone: $${(midpoint*.975).toFixed(8)}-$${(midpoint*1.025).toFixed(8)}; midpoint $${midpoint}` };
    };
    stock.price_opportunity.support_1m_distance = support(short);
    stock.price_opportunity.support_5y_distance = support(long);
    stock.business_health.revenue_growth_yoy = { value: revenue };
    stock.screening.metrics.revenue = { value: revenue, validated: true, valid_until: "2999-01-01", status: revenue > 0 ? "Growing" : revenue === 0 ? "Flat" : "Declining" };
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
