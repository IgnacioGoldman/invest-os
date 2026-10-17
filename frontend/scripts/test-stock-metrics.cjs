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
