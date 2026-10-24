const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const ts = require('typescript');
const { spawnSync } = require('node:child_process');

// Use the app's existing TypeScript dependency; the production build checks types.
require.extensions['.ts'] = (module, filename) => {
  const originalRequire = module.require.bind(module);
  module.require = (id) => id.endsWith('.md?raw')
    ? { default: fs.readFileSync(path.resolve(path.dirname(filename), id.slice(0, -4)), 'utf8') }
    : originalRequire(id);
  module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText, filename);
};
const { STOCK_METRICS, SUPPORT_TIMEFRAMES, stockMetricForField, visibleStockMetrics, supportMetric } = require('../src/stockMetrics.ts');
const { metricRulesFromExpression, expressionFromMetricRules, filterExpressionMatches, groupSupportTimeframes } = require('../src/metricFilterRules.ts');
const stocks = JSON.parse(fs.readFileSync(path.join(__dirname, '../public/data/open-data/stocks.json'), 'utf8'));
// Freeze the requested accounting regression independently of daily refreshes.
const googFixture = JSON.parse(fs.readFileSync(path.join(__dirname, '../../scripts/fixtures/goog-q2-2026.json'), 'utf8'));
const projectedFixture = spawnSync('python3', ['-c', [
  'import json, sys', 'from datetime import date',
  'from evaluate_saved_filters import build_screening_metrics',
  'print(json.dumps(build_screening_metrics(json.load(sys.stdin), date(2026, 10, 24))))',
].join('\n')], { cwd: path.join(__dirname, '../../scripts'), input: JSON.stringify(googFixture), encoding: 'utf8' });
assert.equal(projectedFixture.status, 0, projectedFixture.stderr);
googFixture.screening = JSON.parse(projectedFixture.stdout);


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

test('four business-performance facts and the derived Red Flag Count are registered', () => {
  assert.deepEqual(STOCK_METRICS.filter(metric => !metric.context).map(metric => metric.key),
    ['revenue', 'momentum', 'operating_margin', 'operating_margin_trend', 'red_flag_count']);
  for (const field of ['eps', 'industry_strength', 'valuation', 'fcf_margin', 'forward_pe', 'balance_sheet', 'gross_margin', 'price_to_sales', 'fcf_yield']) assert.equal(stockMetricForField(field), undefined);
});

test('GOOG displays the requested signed facts and comparable operating-margin trend', () => {
  const now = Date.now;
  Date.now = () => Date.parse('2026-10-24T12:00:00Z');
  try {
    const stock = googFixture;
    const cards = visibleStockMetrics(stock, false);
    assert.equal(cards.length, 5);
    const values = cards.map(m => [Number(m.getValue(stock).toFixed(2)), m.getSignal(stock).label]);
    assert.deepEqual(values, [[24.23, 'Growing'], [8, 'Accelerating'], [34.03, 'Profitable'], [1.6, 'Improving'], [0, 'Complete assessment']]);
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
  const stock = googFixture;
  const prompt = prepareStockAnalysis([stock], 'All stocks').prompt;
  for (const text of ['raw_financial_metrics', 'eps_gaap_growth_yoy', 'peg', 'net_margin', 'screening_metrics', 'red_flag_count', 'observed_count', 'coverage', 'net income exceeds operating income', 'not independent verification']) assert.ok(prompt.includes(text), text);
});

test('Markdown AI instructions render single and comparison briefs with literal filter names', () => {
  const { prepareStockAnalysis } = require('../src/aiAnalysis.ts');
  const filterName = 'Growth $& {{subject}}';
  for (const snapshots of [[googFixture], [googFixture, { ...googFixture, ticker: 'TEST' }]]) {
    const brief = prepareStockAnalysis(snapshots, filterName);
    const subject = snapshots.length === 1
      ? 'Evaluate GOOG as a potential investment.'
      : 'Compare GOOG, TEST as potential investments.';
    assert.ok(brief.prompt.startsWith(`${subject}\n\n`));
    assert.ok(brief.prompt.includes(`Stock screen: ${filterName}\n`));
    assert.match(brief.prompt, /Prepared: \d{4}-\d{2}-\d{2}T/);
    assert.ok(brief.prompt.includes('## Invest OS data\n\n### GOOG'));
    assert.match(brief.prompt, /\| Rank \| Stock \| Business (?:score|quality score \+ tag) \| Valuation score(?: \+ tag)? \| Brief rationale \|/);
    assert.ok(brief.prompt.includes('two integer scores from 0 to 100'));
    assert.ok(brief.prompt.includes('equal-weight average'));
    assert.ok(brief.prompt.includes('Do not review, critique or suggest improvements to Invest OS'));
    assert.ok(brief.preview.includes('rank all selected stocks'));
    assert.equal(brief.prompt.includes('{{preparedAt}}'), false);
    assert.equal(brief.prompt.includes('{{filterName}}'), false);
    assert.equal(brief.prompt.split('```json').length - 1, snapshots.length);
  }
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

test('test 1 requires growth and profit with support on any selected timeframe', () => {
  const { DEFAULT_FILTERS } = require('../src/defaultFilters.ts');
  const preset = DEFAULT_FILTERS.find(filter => filter.name === 'test 1');
  assert.ok(preset.isDefault);
  const expression = preset.expression;
  const parsed = metricRulesFromExpression(expression);
  assert.equal(parsed.logicChanged, false);
  const rules = groupSupportTimeframes(parsed.rules);
  assert.equal(rules.length, 3);
  assert.equal(rules[2].timeframeMatch, 'any');
  assert.deepEqual(rules[2].timeframes, ['support_1m', 'support_3m', 'support_6m']);
  const cases = [null, 1, 4, 20].flatMap(short => [null, 1, 4, 20].flatMap(medium =>
    [null, 1, 4, 20].map(long => [short, medium, long, 25, 12])));
  cases.push([1, 1, 1, -5, 12], [1, 1, 1, 0, 12], [1, 1, 1, null, 12],
    [1, 1, 1, 25, -5], [1, 1, 1, 25, null]);
  const samples = cases.map(([short, medium, long, revenue, margin]) => {
    const businessMatches = revenue != null && revenue > 0 && margin != null && margin >= 0;
    const supports = [short, medium, long].map(value => value === 1 || value === 4);
    const matches = businessMatches && supports.some(Boolean);
    const matchesAll = businessMatches && supports.every(Boolean);
    const stock = structuredClone(stocks[0]);
    const today = new Date().toISOString().slice(0,10);
    stock.price_opportunity.current_price = { value: 100, as_of: today };
    const support = value => {
      const midpoint = value == null ? 100 : 100 / (1 + value / 100);
      return { value, as_of: today, source: 'yfinance_history', tier: 'computed_from_public_facts', notes: `Support zone: $${(midpoint*.975).toFixed(8)}-$${(midpoint*1.025).toFixed(8)}; midpoint $${midpoint}` };
    };
    stock.price_opportunity.support_1m_distance = support(short);
    stock.price_opportunity.support_3m_distance = support(medium);
    stock.price_opportunity.support_6m_distance = support(long);
    stock.business_health.revenue_growth_yoy = { value: revenue };
    stock.screening.metrics.revenue = { value: revenue, validated: true, valid_until: "2999-01-01", status: revenue > 0 ? "Growing" : revenue === 0 ? "Flat" : "Declining" };
    stock.screening.metrics.operating_margin = { value: margin, validated: margin != null, valid_until: "2999-01-01", status: margin == null ? "Unknown" : margin >= 0 ? "Profitable" : "Loss-making" };
    return { stock, matches, matchesAll };
  });
  const roundTrip = expressionFromMetricRules(rules, expression);
  const allExpression = expressionFromMetricRules(rules.map(rule => ({ ...rule, timeframeMatch: 'all' })), expression);
  const allRoundTrip = expressionFromMetricRules(groupSupportTimeframes(metricRulesFromExpression(allExpression).rules), allExpression);
  for (const sample of samples) {
    assert.equal(filterExpressionMatches(sample.stock, expression), sample.matches);
    assert.equal(filterExpressionMatches(sample.stock, roundTrip), sample.matches);
    assert.equal(filterExpressionMatches(sample.stock, allExpression), sample.matchesAll);
    assert.equal(filterExpressionMatches(sample.stock, allRoundTrip), sample.matchesAll);
  }
  const result = spawnSync('python3', ['-c', [
    'import json, sys',
    'from evaluate_saved_filters import expression_matches',
    'payload = json.load(sys.stdin)',
    'print(json.dumps([[expression_matches(sample["stock"], expression) for sample in payload["samples"]] for expression in payload["expressions"]]))',
  ].join('\n')], {
    cwd: path.join(__dirname, '../../scripts'),
    input: JSON.stringify({ expressions: [expression, roundTrip, allExpression, allRoundTrip], samples }), encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), [samples.map(sample => sample.matches), samples.map(sample => sample.matches), samples.map(sample => sample.matchesAll), samples.map(sample => sample.matchesAll)]);
});

test('GOOG matches test 1 through its valid 6M zone even without 1M or 3M support', () => {
  const { DEFAULT_FILTERS } = require('../src/defaultFilters.ts');
  const priceFixture = JSON.parse(fs.readFileSync(path.join(__dirname, '../../scripts/fixtures/goog-support-2026-10-23.json'), 'utf8'));
  const stock = structuredClone(googFixture);
  Object.assign(stock.price_opportunity, priceFixture.price_opportunity);
  const originalNow = Date.now;
  Date.now = () => Date.parse('2026-10-24T12:00:00Z');
  try {
    assert.equal(supportMetric(stock, 'support_1m'), null);
    assert.equal(supportMetric(stock, 'support_3m'), null);
    assert.equal(supportMetric(stock, 'support_6m').signal.label, 'Inside Support Zone');
    const expression = DEFAULT_FILTERS.find(filter => filter.name === 'test 1').expression;
    assert.equal(filterExpressionMatches(stock, expression), true);
    const parsed = metricRulesFromExpression(expression);
    assert.equal(parsed.logicChanged, false);
    const reopened = expressionFromMetricRules(groupSupportTimeframes(parsed.rules), expression);
    assert.equal(filterExpressionMatches(stock, reopened), true);
    stock.screening.metrics.operating_margin = { ...stock.screening.metrics.operating_margin, status: 'Loss-making', value: -1 };
    assert.equal(filterExpressionMatches(stock, expression), false, 'support must not bypass the profitability requirement');
  } finally {
    Date.now = originalNow;
  }
});

test('Red Flag Count distinguishes complete zero, partial lower bounds and expired data', () => {
  const { redFlagDisplay, redFlagValue } = require('../src/stockMetrics.ts');
  const now = Date.now;
  Date.now = () => Date.parse('2026-10-24T12:00:00Z');
  try {
    const stock = structuredClone(googFixture);
    assert.equal(redFlagValue(stock), 0);
    assert.equal(redFlagDisplay(stock), '0');
    const metric = stock.screening.metrics.red_flag_count;
    metric.coverage.complete = false;
    metric.coverage.assessed = 2;
    metric.validated = false;
    metric.value = null;
    metric.status = 'Partial assessment';
    assert.equal(redFlagValue(stock), null);
    assert.equal(redFlagDisplay(stock), 'Not fully assessed');
    assert.ok(visibleStockMetrics(stock, false).some(m => m.key === 'red_flag_count'));
    metric.observed_count = 1;
    assert.equal(redFlagDisplay(stock), '≥1');
    metric.valid_until = '2000-01-01';
    assert.equal(redFlagValue(stock), null);
    assert.equal(visibleStockMetrics(stock, false).some(m => m.key === 'red_flag_count'), false);
  } finally { Date.now = now; }
});

test('numeric custom filters persist comparisons and agree with Python on coverage and boundaries', () => {
  const now = Date.now;
  Date.now = () => Date.parse('2026-10-24T12:00:00Z');
  try {
    const base = structuredClone(googFixture);
    Object.assign(base.price_opportunity, JSON.parse(fs.readFileSync(path.join(__dirname, '../../scripts/fixtures/goog-support-2026-10-23.json'), 'utf8')).price_opportunity);
    const expression = expressionFromMetricRules([
      { id: 'growth', field: 'revenue', comparison: 'gt', values: ['15'] },
      { id: 'margin', field: 'operating_margin', comparison: 'gt', values: ['15'] },
      { id: 'support', field: 'support_6m', timeframeMatch: 'any', values: ['Inside Support Zone', 'Near Support'] },
      { id: 'flags', field: 'red_flag_count', comparison: 'lte', values: ['1'] },
    ], { operator: 'and', groups: [] });
    const parsed = metricRulesFromExpression(expression);
    assert.equal(parsed.logicChanged, false);
    assert.deepEqual(parsed.rules.map(rule => rule.comparison), ['gt', 'gt', undefined, 'lte']);
    const reopened = expressionFromMetricRules(groupSupportTimeframes(parsed.rules), expression);
    const samples = [];
    for (const count of [0, 1, 2, 3]) {
      const stock = structuredClone(base);
      Object.assign(stock.screening.metrics.red_flag_count, { value: count, observed_count: count });
      samples.push({ stock, matches: count <= 1 });
    }
    for (const mutate of [
      stock => { delete stock.screening.metrics.red_flag_count; },
      stock => { stock.screening.metrics.red_flag_count.valid_until = '2000-01-01'; },
      stock => { stock.screening.metrics.red_flag_count.coverage.complete = false; },
      stock => { stock.screening.metrics.red_flag_count.value = null; },
      stock => { stock.screening.metrics.red_flag_count.status = 'Unknown'; },
      stock => { stock.screening.metrics.revenue.value = 15; },
      stock => { stock.screening.metrics.operating_margin.value = 15; },
    ]) {
      const stock = structuredClone(base); mutate(stock); samples.push({ stock, matches: false });
    }
    for (const sample of samples) {
      assert.equal(filterExpressionMatches(sample.stock, expression), sample.matches);
      assert.equal(filterExpressionMatches(sample.stock, reopened), sample.matches);
    }
    const boundaryExpressions = ['lt', 'lte', 'eq', 'gte', 'gt'].map(comparison => expressionFromMetricRules([
      { id: 'flags', field: 'red_flag_count', comparison, values: ['0'] },
    ], { operator: 'and', groups: [] }));
    assert.deepEqual(boundaryExpressions.map(e => filterExpressionMatches(base, e)), [false, true, true, true, false]);
    const invalidExpressions = ['', 'NaN', 'Infinity', '-1', '1.5', '0x1'].map(value => ({ operator: 'or', groups: [{ operator: 'or', conditions: [
      { id: 'bad', field: 'red_flag_count', comparison: 'lte', value },
      { id: 'good', field: 'revenue', value: 'Growing' },
    ] }] }));
    for (const invalid of invalidExpressions) assert.equal(filterExpressionMatches(base, invalid), false);
    const expressions = [expression, reopened, ...boundaryExpressions, ...invalidExpressions];
    const paritySamples = [...samples, ...stocks.map(stock => ({ stock }))];
    const result = spawnSync('python3', ['-c', [
      'import json, sys', 'from datetime import datetime, timezone',
      'from unittest.mock import patch', 'from evaluate_saved_filters import expression_matches',
      'class FrozenDatetime(datetime):', ' @classmethod', ' def now(cls, tz=None): return cls(2026,10,24,12,tzinfo=timezone.utc)',
      'payload=json.load(sys.stdin)', "with patch('evaluate_saved_filters.datetime', FrozenDatetime):",
      ' print(json.dumps([[expression_matches(s["stock"], e) for s in payload["samples"]] for e in payload["expressions"]]))',
    ].join('\n')], { cwd: path.join(__dirname, '../../scripts'), input: JSON.stringify({ expressions, samples: paritySamples }), encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(JSON.parse(result.stdout), expressions.map(e => paritySamples.map(s => filterExpressionMatches(s.stock, e))));
  } finally { Date.now = now; }
});
