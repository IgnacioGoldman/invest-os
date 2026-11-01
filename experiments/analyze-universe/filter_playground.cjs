// Project the saved experiment through the current app's metrics and presets.
// This reads only captured JSON and local source files; no APIs or credentials.
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');
require('./prepare.cjs');

function playgroundData(directory) {
  const root = path.resolve(__dirname, '../..');
  const manifest = JSON.parse(fs.readFileSync(path.join(directory, 'manifest.json')));
  const snapshots = JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(directory, 'snapshots.json.gz'))));
  const refreshPath = path.join(directory, 'financial-refresh.json');
  const refresh = fs.existsSync(refreshPath) ? JSON.parse(fs.readFileSync(refreshPath)) : null;
  const refreshed = refresh ? JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(directory, 'financial-refresh.json.gz')))) : null;
  const ranking = JSON.parse(fs.readFileSync(path.join(directory, 'ranking.json')));
  const audit = JSON.parse(fs.readFileSync(path.join(directory, 'filter-research/support-audit.json')));
  const RealDate = Date;
  const evaluatedOn = refresh?.evaluated_on ?? manifest.prepared_at.slice(0, 10);
  const instant = RealDate.parse(`${evaluatedOn}T12:00:00Z`);
  global.Date = class extends RealDate {
    constructor(...args) { super(...(args.length ? args : [instant])); }
    static now() { return instant; }
  };
  try {
    const { DEFAULT_FILTERS } = require(path.join(root, 'frontend/src/defaultFilters.ts'));
    const { STOCK_METRICS, DISABLED_FILTER_FIELDS, metricFilterOptions, SUPPORT_TIMEFRAMES, supportMetric } = require(path.join(root, 'frontend/src/stockMetrics.ts'));
    const { filterExpressionMatches, metricRulesFromExpression } = require(path.join(root, 'frontend/src/metricFilterRules.ts'));
    const definitions = STOCK_METRICS.filter(m => m.field !== 'support' && !DISABLED_FILTER_FIELDS.includes(m.field));
    const fields = definitions.map(m => ({ key: m.field, label: m.title, unit: m.format,
      numeric: ['percent', 'pp', 'count'].includes(m.format),
      options: m.field === 'red_flag_count' ? [] : metricFilterOptions(m.field).map(o => ({ value: o.value, label: o.label })) }));
    fields.push({ key: 'support', label: 'Proximity to Support', unit: 'support', numeric: false,
      options: ['At Support', 'Near Support', 'Above Support'].map(value => ({ value, label: value })) },
    { key: 'green_flag_count', label: 'Green Flag Count', unit: 'count', numeric: true, options: [] },
    { key: 'business_quality', label: 'Business quality (original review)', unit: 'label', numeric: false,
      options: ['Strong', 'Solid', 'Average', 'Weak', 'Poor', 'Unknown'].map(value => ({ value, label: value })) },
    { key: 'review_valuation', label: 'Valuation (original review)', unit: 'label', numeric: false,
      options: ['Cheap', 'Fair', 'Expensive', 'Unknown'].map(value => ({ value, label: value })) },
    { key: 'rank', label: 'Original rank', unit: 'count', numeric: true, options: [] });
    const bySymbol = Object.fromEntries(snapshots.map(original => {
      const snapshot = refreshed ? { ...original, screening: { ...original.screening,
        metrics: { ...original.screening?.metrics, ...refreshed[original.ticker] } } } : original;
      return [snapshot.ticker, snapshot];
    }));
    const stocks = ranking.map(row => {
      const snapshot = bySymbol[row.symbol];
      const metrics = Object.fromEntries(definitions.map(m => [m.field, {
        value: m.getValue(snapshot), label: m.getSignal(snapshot).label,
      }]));
      for (const timeframe of SUPPORT_TIMEFRAMES) {
        const support = supportMetric(snapshot, timeframe.field);
        metrics[timeframe.field] = { value: support?.metric.value ?? null, label: support?.signal.label ?? 'Unknown' };
      }
      metrics.green_flag_count = { value: audit.stocks[row.symbol].flag_metrics.green_flag_count.value, label: '' };
      metrics.business_quality = { value: null, label: row.business_quality };
      metrics.review_valuation = { value: null, label: row.valuation };
      metrics.rank = { value: row.rank, label: '' };
      return { ...row, metrics };
    });
    const presets = DEFAULT_FILTERS.map(preset => {
      const parsed = metricRulesFromExpression(preset.expression);
      if (parsed.logicChanged) throw new Error(`Cannot represent default filter: ${preset.name}`);
      return { id: preset.id, name: preset.name[0].toUpperCase() + preset.name.slice(1),
        description: preset.description, operator: 'and', rules: parsed.rules,
        // Reference membership lets the browser check parity with the app.
        symbols: ranking.filter(r => filterExpressionMatches(bySymbol[r.symbol], preset.expression)).map(r => r.symbol) };
    });
    return { evaluatedOn, quoteDates: manifest.market_dates, fields, presets, stocks,
      timeframes: SUPPORT_TIMEFRAMES.map(t => ({ key: t.field, label: t.label })) };
  } finally { global.Date = RealDate; }
}

module.exports = { playgroundData };
if (require.main === module) process.stdout.write(JSON.stringify(playgroundData(path.resolve(process.argv[2]))));
