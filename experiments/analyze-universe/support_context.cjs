// Reuse the archived app's support validation and labels at the experiment date.
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');
require('./prepare.cjs'); // Registers the existing TypeScript loader; does not prepare a run.

const directory = path.resolve(process.argv[2]);
const manifest = JSON.parse(fs.readFileSync(path.join(directory, 'manifest.json')));
const snapshots = JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(directory, 'snapshots.json.gz'))));
const RealDate = Date;
const instant = RealDate.parse(manifest.prepared_at);
global.Date = class extends RealDate {
  constructor(...args) { super(...(args.length ? args : [instant])); }
  static now() { return instant; }
};
try {
  const { supportMetric, SUPPORT_TIMEFRAMES } = require(path.join(directory, 'source/frontend/src/stockMetrics.ts'));
  const rows = Object.fromEntries(snapshots.map(snapshot => {
    const timeframes = SUPPORT_TIMEFRAMES.flatMap(timeframe => {
      const support = supportMetric(snapshot, timeframe.field);
      if (!support) return [];
      const bounds = /Support zone: \$?([\d,.]+)-\$?([\d,.]+)/.exec(support.metric.notes ?? '');
      return [{ timeframe: timeframe.label, status: support.signal.label,
        distance_pct: support.metric.value, zone: bounds.slice(1).map(v => Number(v.replace(/,/g, ''))),
        as_of: support.metric.as_of }];
    });
    // Any zone containing the quote takes precedence; otherwise use the smallest
    // absolute distance to a support midpoint. Ties retain app timeframe order.
    const nearest = [...timeframes].sort((a, b) =>
      Number(b.status === 'At Support') - Number(a.status === 'At Support')
      || Math.abs(a.distance_pct) - Math.abs(b.distance_pct))[0] ?? null;
    return [snapshot.ticker, { currency: snapshot.price_currency ?? null, nearest, timeframes }];
  }));
  process.stdout.write(JSON.stringify({ prepared_at: manifest.prepared_at, stocks: rows }));
} finally { global.Date = RealDate; }
