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
const { CONTEXTUAL_METRICS, contextualMetric, contextualHistory, contextualValue, formatContextualValue } = require('../src/contextualMetrics.ts');
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

test('contextual values have no classifications and cannot restore saved-filter rules', () => {
  for (const definition of CONTEXTUAL_METRICS) {
    assert.equal('getSignal' in definition, false);
    assert.equal('options' in definition, false);
    assert.equal(stockMetricForField(definition.key), undefined);
    assert.equal(filterExpressionMatches(googFixture, { operator: 'or', groups: [{ operator: 'or', conditions: [
      { field: definition.key, value: 'Cheap' }, { field: 'revenue', value: 'Growing' },
    ] }] }), false);
  }
  const forward = CONTEXTUAL_METRICS.find(m => m.key === 'forward_pe');
  assert.equal(formatContextualValue(40, forward), '40×');
  assert.equal(formatContextualValue(10, forward), '10×');
  assert.equal(formatContextualValue(null, forward), '—');
  assert.equal(contextualValue({ value: Infinity }), null);
  assert.equal(formatContextualValue(0, { format: 'percent' }), '0%');
});

test('contextual cards respect rejected projections instead of exposing unsafe raw fallbacks', () => {
  const stock = structuredClone(googFixture);
  const definition = CONTEXTUAL_METRICS.find(m => m.key === 'forward_pe');
  stock.metrics.forward_pe = { value: 10 };
  stock.screening.metrics.forward_pe = { value: 40, estimate_as_of: '2000-01-01', price_as_of: '2000-01-01', warnings: [] };
  assert.equal(contextualValue(contextualMetric(stock, definition)), null);
  delete stock.screening.metrics.forward_pe;
  assert.equal(contextualMetric(stock, definition), undefined);
  const gross = CONTEXTUAL_METRICS.find(m => m.key === 'gross_margin');
  assert.equal(contextualMetric(stock, gross), stock.screening.financial_details.gross_margin);
});

test('contextual charts preserve units and annual versus quarterly measurement bases', () => {
  const stock = JSON.parse(fs.readFileSync(path.join(__dirname, '../public/data/open-data/snapshots/GOOG.json'), 'utf8'));
  for (const key of ['price_to_sales', 'fcf_yield', 'pe', 'ev_to_ebitda']) {
    const definition = CONTEXTUAL_METRICS.find(m => m.key === key);
    const points = contextualHistory(stock, definition);
    assert.ok(points.length > 0);
    assert.equal(points.at(-1).value, stock.historical_series.valuation_history.at(-1).metrics[definition.historyKey].value);
    assert.match(definition.historyTitle, /Annual/);
  }
  const fcf = CONTEXTUAL_METRICS.find(m => m.key === 'fcf_margin');
  assert.equal(contextualHistory(stock, fcf).at(-1).value, stock.historical_series.quarterly_fundamentals.at(-1).metrics.fcf_margin.value);
  assert.match(fcf.historyTitle, /separate from TTM/);
  const eps = CONTEXTUAL_METRICS.find(m => m.key === 'eps_gaap_growth_yoy');
  assert.ok(Math.abs(contextualHistory(stock, eps).at(-1).value - stock.metrics.eps_gaap_growth_yoy.value) < 1e-6);
  for (const definition of CONTEXTUAL_METRICS.filter(m => ['forward_pe', 'peg'].includes(m.key))) {
    assert.deepEqual(contextualHistory(stock, definition), [], 'Never fabricate unavailable ratio history');
  }
});


test('every visible card exposes only factual selectable labels', () => {
  const forbidden = /^(Unknown|Needs Review|Computed Metric|Unavailable|Insufficient Data|Fair|Cheap|Attractive)$/;
  for (const metric of STOCK_METRICS) {
    assert.ok(metric.options.length > 0);
    for (const label of metric.options) assert.equal(forbidden.test(label), false, label);
    for (const stock of stocks) {
      if (metric.getValue(stock) != null) assert.ok(metric.options.includes(metric.getSignal(stock).label));
    }
  }
});

test('revenue filter choices use current card tags and preserve the Flat growth band', () => {
  const { metricFilterOptions } = require('../src/stockMetrics.ts');
  const options = metricFilterOptions('revenue');
  assert.deepEqual(options.map(option => option.label), ['Strong', 'Solid', 'Flat', 'Weak']);
  assert.deepEqual(options.map(option => option.value), ['Strong', 'Solid', 'Flat growth', 'Weak']);
  const expressions = options.map(option => expressionFromMetricRules([
    { id: 'revenue', field: 'revenue', values: [option.value] },
  ], { operator: 'and', groups: [] }));
  const samples = [-5, 0, .01, 7.99, 8, 19.99, 20, 35].map(value => {
    const stock = structuredClone(googFixture);
    const strength = value >= 20 ? 'Strong' : value >= 8 ? 'Solid' : value >= 0 ? 'Flat' : 'Weak';
    Object.assign(stock.screening.metrics.revenue, { value, strength, validated: true,
      status: value > 0 ? 'Growing' : value < 0 ? 'Declining' : 'Flat', valid_until: '2999-01-01' });
    expressions.forEach((expression, index) => {
      const parsed = metricRulesFromExpression(expression);
      assert.equal(parsed.logicChanged, false);
      assert.deepEqual(parsed.rules[0].values, [options[index].value]);
      const reopened = expressionFromMetricRules(parsed.rules, expression);
      assert.equal(filterExpressionMatches(stock, expression), strength === options[index].label);
      assert.equal(filterExpressionMatches(stock, reopened), strength === options[index].label);
    });
    return stock;
  });
  const result = spawnSync('python3', ['-c', [
    'import json, sys', 'from evaluate_saved_filters import expression_matches',
    'payload=json.load(sys.stdin)',
    'print(json.dumps([[expression_matches(s, e) for s in payload["stocks"]] for e in payload["expressions"]]))',
  ].join('\n')], { cwd: path.join(__dirname, '../../scripts'), input: JSON.stringify({ expressions, stocks: samples }), encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), expressions.map(e => samples.map(s => filterExpressionMatches(s, e))));
});

test('editing legacy direction rules uses equivalent numeric comparisons without changing matches', () => {
  for (const [label, comparison] of [['Growing', 'gt'], ['Flat', 'eq'], ['Declining', 'lt']]) {
    const original = expressionFromMetricRules([
      { id: 'legacy-revenue', field: 'revenue', values: [label] },
    ], { operator: 'and', groups: [] });
    const parsed = metricRulesFromExpression(original);
    assert.equal(parsed.logicChanged, false);
    assert.equal(parsed.rules[0].comparison, comparison);
    assert.deepEqual(parsed.rules[0].values, ['0']);
    assert.equal(original.groups[0].conditions[0].value, label, 'Opening must not mutate saved data');
    const reopened = expressionFromMetricRules(parsed.rules, original);
    for (const value of [-5, 0, .01, 5, 15, 25, null]) {
      const stock = structuredClone(googFixture);
      Object.assign(stock.screening.metrics.revenue, { value, validated: value != null,
        status: value > 0 ? 'Growing' : value < 0 ? 'Declining' : 'Flat', valid_until: '2999-01-01' });
      assert.equal(filterExpressionMatches(stock, reopened), filterExpressionMatches(stock, original), `${label}: ${value}`);
    }
  }
  for (const [field, oldLabel, currentLabel] of [['revenue', 'High Growth', 'Strong'],
    ['revenue', 'Moderate Growth', 'Solid'], ['momentum', 'Stable', 'Steady']]) {
    const original = expressionFromMetricRules([{ id: 'legacy', field, values: [oldLabel] }], { operator: 'and', groups: [] });
    const parsed = metricRulesFromExpression(original);
    assert.equal(parsed.logicChanged, false);
    assert.deepEqual(parsed.rules[0].values, [currentLabel]);
  }
});

test('all support timeframes resolve to the shared context definition', () => {
  for (const timeframe of SUPPORT_TIMEFRAMES) assert.equal(stockMetricForField(timeframe.field), stockMetricForField('support'));
});

test('growth pattern, business-performance facts and the derived Red Flag Count are registered', () => {
  assert.deepEqual(STOCK_METRICS.filter(metric => !metric.context).map(metric => metric.key),
    ['revenue', 'momentum', 'revenue_consistency', 'operating_margin', 'operating_margin_trend', 'red_flag_count']);
  for (const field of ['eps', 'industry_strength', 'valuation', 'fcf_margin', 'forward_pe', 'balance_sheet', 'gross_margin', 'price_to_sales', 'fcf_yield']) assert.equal(stockMetricForField(field), undefined);
});

test('GOOG displays the requested signed facts and comparable operating-margin trend', () => {
  const now = Date.now;
  Date.now = () => Date.parse('2026-10-24T12:00:00Z');
  try {
    const stock = googFixture;
    const cards = visibleStockMetrics(stock, false);
    assert.equal(cards.length, 6);
    const values = cards.filter(m => m.format !== "label").map(m => [Number(m.getValue(stock).toFixed(2)), m.getSignal(stock).label]);
    assert.deepEqual(values, [[24.23, 'Strong'], [8, 'Accelerating'], [34.03, 'Profitable'], [1.6, 'Improving'], [0, 'Complete assessment']]);
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

test('support restores proximity colors while business direction and earnings keep their styling', () => {
  const { metricSignal } = require('../src/metricStatus.ts');
  assert.equal(metricSignal('At Support').tone, 'strong');
  assert.equal(metricSignal('Near Support').tone, 'positive');
  assert.equal(metricSignal('Above Support').tone, 'warning');
  for (const label of ['Growing', 'Accelerating', 'Improving']) assert.equal(metricSignal(label).tone, 'positive');
  for (const label of ['Profitable', 'Stable', 'Steady', 'Flat', 'Unknown', 'This week', 'Next 30 days']) assert.equal(metricSignal(label).tone, 'neutral');
});

test('retired and obsolete quality rules disable the whole saved expression', () => {
  const { hasDisabledFilter } = require('../src/stockMetrics.ts');
  for (const [field, value] of [['eps', 'Strong'], ['valuation', 'Cheap'], ['industry_strength', 'Ahead of market'], ['fcf_margin', 'Strong'], ['forward_pe', 'Estimate'], ['balance_sheet', 'Computed Metric']]) {
    assert.equal(hasDisabledFilter({ operator: 'or', groups: [{ conditions: [{ field, value }, { field: 'revenue', value: 'Growing' }] }] }), true);
  }
});

test('compact AI research preserves financial substance, sources, coverage and anomaly warnings', () => {
  const { prepareStockAnalysis } = require('../src/aiAnalysis.ts');
  const stock = googFixture;
  const prompt = prepareStockAnalysis([stock], 'All stocks').prompt;
  for (const text of ['net_income_ttm', 'eps_gaap_growth_yoy', 'peg', 'net_margin', 'red_flags', 'observed_count', 'coverage', 'net income exceeds operating income', 'not independent verification']) assert.ok(prompt.includes(text), text);
  const data = JSON.parse(prompt.split('```json\n')[1].split('```')[0]);
  assert.equal(data.metrics.net_income_ttm.v, Number((stock.metrics.net_income_ttm.value / 1e6).toPrecision(7)));
  assert.equal(data.red_flags.count, stock.screening.metrics.red_flag_count.value);
  assert.deepEqual(data.red_flags.coverage, stock.screening.metrics.red_flag_count.coverage);
  assert.ok(data.sources.some(s => s.startsWith('sec_companyfacts:')));
  assert.equal(new Set(data.sources).size, data.sources.length);
  assert.equal(data.quarters.length, Math.min(8, stock.historical_series.quarterly_fundamentals.length));
  assert.equal(data.revenue_quarters.length, Math.min(12, stock.historical_series.quarterly_revenue.length));
  assert.equal('raw_financial_metrics' in data, false);
  assert.equal('screening_metrics' in data, false);
});

test('compact AI data preserves currencies, per-share units, zeroes, proxies and source references', () => {
  const { compactAnalysisStock } = require('../src/aiBriefData.ts');
  const stock = structuredClone(googFixture);
  stock.price_currency = 'USD';
  stock.metrics.revenue_ttm.currency = 'SGD';
  stock.metrics.cash.value = null;
  stock.metrics.capex_ttm.value = 0;
  stock.metrics.roic = { value: -0.000001, tier: 'proxy_estimate', as_of: '2026-06-30', source: 'test:proxy', notes: 'Proxy using incomplete invested capital.' };
  stock.valuation_inputs = { revenue: { ...stock.metrics.revenue_ttm, value: 123000000, currency: undefined, notes: 'Converted from SGD into USD.' } };
  const row = stock.historical_series.quarterly_fundamentals.at(-1);
  row.metrics.eps_diluted = { value: 0.27, tier: 'exact_public_fact', source: 'sec_companyfacts:us-gaap/EarningsPerShareDiluted:USD/shares:10-Q:2026-06-30', as_of: row.as_of, notes: '' };
  const before = structuredClone(stock);
  const data = compactAnalysisStock(stock);
  assert.deepEqual(stock, before, 'copying must not alter stored research data');
  assert.equal(data.currency, 'SGD');
  assert.equal(data.market.currency, 'USD');
  assert.equal(data.market.price.ccy, 'USD');
  assert.equal(data.valuation_basis.revenue.ccy, 'USD');
  assert.equal(data.valuation_basis.revenue.v, 123);
  assert.equal(data.metrics.capex_ttm.v, 0);
  assert.equal(data.metrics.cash, undefined);
  assert.ok(data.missing_metrics.includes('cash'));
  assert.equal(data.metrics.roic.v, -0.000001);
  assert.equal(data.metrics.roic.t, 'p');
  assert.match(data.metrics.roic.caution, /incomplete/);
  assert.equal(data.quarters.at(-1).values.eps_diluted.v, 0.27);
  function checkReferences(value) {
    if (Array.isArray(value)) return value.forEach(checkReferences);
    if (!value || typeof value !== 'object') return;
    if (value.s) for (const id of value.s) assert.ok(Number.isInteger(id) && id > 0 && id <= data.sources.length);
    Object.values(value).forEach(checkReferences);
  }
  checkReferences(data);
  assert.ok(JSON.stringify(data).length < JSON.stringify(stock, null, 2).length / 2, 'deduplicate metadata rather than dropping the histories');
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
    assert.ok(brief.prompt.includes('## Invest OS data\n\nCompact data key:'));
    assert.ok(brief.prompt.includes('prices (including support zones) and EPS are per share'));
    assert.ok(brief.prompt.includes('### GOOG'));
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
    { id: 'short', field: 'support_1m', values: ['At Support', 'Near Support'] },
    { id: 'growth', field: 'revenue', values: ['Strong'] },
    { id: 'long', field: 'support_5y', values: ['Near Support', 'At Support'] },
    { id: 'medium', field: 'support_6m', values: ['At Support'] },
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

test('test 1 requires Strong or Solid growth, profit, support on any selected timeframe and zero assessed red flags', () => {
  const { DEFAULT_FILTERS } = require('../src/defaultFilters.ts');
  const preset = DEFAULT_FILTERS.find(filter => filter.name === 'test 1');
  assert.ok(preset.isDefault);
  const expression = preset.expression;
  const parsed = metricRulesFromExpression(expression);
  assert.equal(parsed.logicChanged, false);
  const rules = groupSupportTimeframes(parsed.rules);
  assert.equal(rules.length, 4);
  assert.deepEqual(rules[0].values, ['Strong', 'Solid']);
  assert.equal(rules[0].comparison, undefined);
  assert.equal(rules[2].timeframeMatch, 'any');
  assert.deepEqual(rules[2].timeframes, ['support_1m', 'support_3m', 'support_6m']);
  assert.equal(rules[3].field, 'red_flag_count');
  assert.equal(rules[3].comparison, 'eq');
  assert.deepEqual(rules[3].values, ['0']);
  const cases = [null, 1, 4, 20].flatMap(short => [null, 1, 4, 20].flatMap(medium =>
    [null, 1, 4, 20].map(long => [short, medium, long, 25, 12])));
  cases.push([1, 1, 1, -5, 12], [1, 1, 1, 0, 12], [1, 1, 1, null, 12],
    [1, 1, 1, 7.99, 12], [1, 1, 1, 8, 12], [1, 1, 1, 19.99, 12], [1, 1, 1, 20, 12],
    [1, 1, 1, 25, -5], [1, 1, 1, 25, null], [1, 1, 1, 25, 12, 1], [1, 1, 1, 25, 12, 2]);
  const samples = cases.map(([short, medium, long, revenue, margin, redFlags = 0]) => {
    const businessMatches = revenue != null && revenue >= 8 && margin != null && margin >= 0 && redFlags === 0;
    const supports = [short, medium, long].map(value => value === 1 || value === 4);
    const matches = businessMatches && supports.some(Boolean);
    const matchesAll = businessMatches && supports.every(Boolean);
    const stock = structuredClone(googFixture);
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
    stock.screening.metrics.revenue = { value: revenue, validated: revenue != null, valid_until: "2999-01-01", status: revenue > 0 ? "Growing" : revenue === 0 ? "Flat" : "Declining",
      strength: revenue == null ? 'Unknown' : revenue >= 20 ? 'Strong' : revenue >= 8 ? 'Solid' : revenue >= 0 ? 'Flat' : 'Weak' };
    stock.screening.metrics.operating_margin = { value: margin, validated: margin != null, valid_until: "2999-01-01", status: margin == null ? "Unknown" : margin >= 0 ? "Profitable" : "Loss-making" };
    Object.assign(stock.screening.metrics.red_flag_count, { value: redFlags, observed_count: redFlags, valid_until: '2999-01-01' });
    return { stock, matches, matchesAll };
  });
  for (const mutate of [
    stock => { delete stock.screening.metrics.red_flag_count; },
    stock => { stock.screening.metrics.red_flag_count.value = null; },
    stock => { stock.screening.metrics.red_flag_count.validated = false; },
    stock => { stock.screening.metrics.red_flag_count.valid_until = '2000-01-01'; },
    stock => { stock.screening.metrics.red_flag_count.coverage.complete = false; },
    stock => { stock.screening.metrics.red_flag_count.status = 'Partial assessment'; },
  ]) {
    const stock = structuredClone(samples.find(sample => sample.matchesAll).stock);
    mutate(stock);
    samples.push({ stock, matches: false, matchesAll: false });
  }
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
    assert.equal(supportMetric(stock, 'support_6m').signal.label, 'At Support');
    const legacy = { operator: 'and', groups: [{ id: 'support', operator: 'or', conditions: [
      { id: 'support-6m', field: 'support_6m', value: 'Inside Support Zone' },
    ] }] };
    assert.equal(filterExpressionMatches(stock, legacy), true);
    const restored = metricRulesFromExpression(legacy);
    assert.equal(restored.logicChanged, false);
    assert.deepEqual(restored.rules[0].values, ['At Support']);
    assert.equal(legacy.groups[0].conditions[0].value, 'Inside Support Zone');
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
      { id: 'support', field: 'support_6m', timeframeMatch: 'any', values: ['At Support', 'Near Support'] },
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


test('consistency is categorical, exportable and combines with numeric growth and momentum filters', () => {
  const stock = structuredClone(googFixture);
  const m = stock.screening.metrics;
  m.revenue_consistency = { ...m.momentum, value: null, status: 'Steady', validated: true, valid_until: '2999-01-01' };
  m.revenue = { ...m.revenue, value: 22, strength: 'Strong', valid_until: '2999-01-01' };
  m.momentum.valid_until = '2999-01-01';
  const expression = { operator: 'and', groups: [
    { operator: 'and', conditions: [{ field: 'revenue', comparison: 'gt', value: '15' }] },
    { operator: 'and', conditions: [{ field: 'momentum', value: 'Accelerating' }] },
    { operator: 'and', conditions: [{ field: 'revenue_consistency', value: 'Steady' }] },
  ] };
  assert.equal(filterExpressionMatches(stock, expression), true);
  assert.equal(stockMetricForField('revenue_consistency').getValue(stock), null);
  assert.ok(visibleStockMetrics(stock, false).some(m => m.key === 'revenue_consistency'));
  assert.equal(filterExpressionMatches(stock, { operator: 'and', groups: [{ conditions: [{ field: 'revenue', value: 'Growing' }] }] }), true);
  m.revenue_consistency.validated = false;
  assert.equal(filterExpressionMatches(stock, expression), false);
  assert.ok(!visibleStockMetrics(stock, false).some(m => m.key === 'revenue_consistency'));
});


test('Priced for Perfection contributes once to the existing count, filters and compact evidence', () => {
  const { compactAnalysisStock } = require('../src/aiBriefData.ts');
  const { redFlagValue } = require('../src/stockMetrics.ts');
  for (const ticker of ['SHOP', 'ALAB']) {
    const stock = structuredClone(stocks.find(s => s.ticker === ticker));
    const risk = stock.screening.metrics.red_flag_count;
    const group = risk.flags.find(g => g.id === 'priced_for_perfection');
    assert.ok(group);
    assert.deepEqual(group.triggered_rules, ['priced_for_perfection']);
    assert.equal(risk.max_count, 4);
    assert.equal(redFlagValue(stock), risk.value);
    assert.ok(risk.observed_count >= 1);
    assert.equal(filterExpressionMatches(stock, { operator: 'and', groups: [{ conditions: [
      { field: 'red_flag_count', comparison: 'eq', value: '0' },
    ] }] }), false);
    const brief = compactAnalysisStock(stock);
    const v = brief.red_flags.detected.find(g => g.group === 'Priced for Perfection').rules[0].values;
    const original = group.checks[0].values;
    assert.equal(v.market_cap, Number((original.market_cap / 1e6).toPrecision(7)));
    assert.equal(v.revenue_ttm, Number((original.revenue_ttm / 1e6).toPrecision(7)));
    assert.equal(v.price_to_sales, Number(original.price_to_sales.toPrecision(7)));
  }
});
