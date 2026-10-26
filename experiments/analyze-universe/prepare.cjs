// Run the real Analyze formatter without changing or importing the browser app.
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const ts = require(path.join(root, 'frontend/node_modules/typescript'));
const hash = value => crypto.createHash('sha256').update(value).digest('hex');

require.extensions['.ts'] = (module, filename) => {
  const originalRequire = module.require.bind(module);
  module.require = id => id.endsWith('.md?raw')
    ? { default: fs.readFileSync(path.resolve(path.dirname(filename), id.slice(0, -4)), 'utf8') }
    : originalRequire(id);
  module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText, filename);
};

function prepare(output, preparedAt = new Date().toISOString()) {
  if (fs.existsSync(output)) throw new Error('Use a new run directory; frozen runs are never overwritten.');
  const dataPath = path.join(root, 'frontend/public/data/open-data/stocks.json');
  const universePath = path.join(root, 'frontend/public/data/stocks/universe.json');
  const data = fs.readFileSync(dataPath);
  const snapshots = JSON.parse(data);
  const universe = JSON.parse(fs.readFileSync(universePath));
  const symbols = snapshots.map(s => s.ticker);
  const expected = universe.filter(s => s.active).map(s => s.symbol);
  if (!symbols.length || new Set(symbols).size !== symbols.length
      || JSON.stringify([...symbols].sort()) !== JSON.stringify([...expected].sort())) {
    throw new Error('Dataset must contain every active universe symbol exactly once.');
  }
  // Freeze both new Date() and Date.now(): support/estimate freshness is date-sensitive.
  const RealDate = Date;
  const instant = RealDate.parse(preparedAt);
  if (!Number.isFinite(instant)) throw new Error('Invalid preparation timestamp.');
  global.Date = class extends RealDate {
    constructor(...args) { super(...(args.length ? args : [instant])); }
    static now() { return instant; }
  };
  let brief;
  try {
    const { prepareStockAnalysis } = require(path.join(root, 'frontend/src/aiAnalysis.ts'));
    brief = prepareStockAnalysis(snapshots, 'All stocks');
  } finally { global.Date = RealDate; }
  const sourcePaths = ['frontend/src/aiAnalysis.ts', 'frontend/src/aiBriefData.ts',
    'frontend/src/prompts/stock-analysis.md', 'frontend/src/stockMetrics.ts', 'frontend/src/metricStatus.ts'];
  const sourceHashes = Object.fromEntries(sourcePaths.map(p => [p, hash(fs.readFileSync(path.join(root, p)))]));
  const manifest = {
    experiment: 'unfiltered-existing-analyze', schema_version: 1, prepared_at: preparedAt,
    git_revision: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(),
    count: symbols.length, symbols, dataset_path: path.relative(root, dataPath),
    dataset_sha256: hash(data), prompt_sha256: hash(brief.prompt), source_sha256: sourceHashes,
    dataset_kind: 'Exact list snapshots passed by MobileStockExplorer.prepareSelectedStocks',
    filter_name: 'All stocks', filtered: false,
    scoring: 'Existing descriptive tags; equal importance to business quality and valuation; no numerical score.',
    quarterly_history: 'Static Analyze list snapshots contain 1 fundamentals quarter, 12 revenue quarters, and 2 annual rows; full detail histories are not substituted.',
    market_dates: [...new Set(snapshots.map(s => s.price_opportunity.current_price?.as_of))].sort(),
    snapshot_dates: [...new Set(snapshots.map(s => s.generated_at))].sort(),
  };
  fs.mkdirSync(output, { recursive: true });
  fs.writeFileSync(path.join(output, 'snapshots.json.gz'), zlib.gzipSync(data, { mtime: 0 }));
  fs.writeFileSync(path.join(output, 'universe.json'), JSON.stringify(universe, null, 2) + '\n');
  fs.writeFileSync(path.join(output, 'analysis-prompt.md'), brief.prompt);
  fs.writeFileSync(path.join(output, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
  for (const p of sourcePaths) {
    const target = path.join(output, 'source', p);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.copyFileSync(path.join(root, p), target);
  }
  return manifest;
}

module.exports = { prepare };
if (require.main === module) {
  if (!process.argv[2]) throw new Error('Usage: node prepare.cjs RUN_DIRECTORY [ISO_TIMESTAMP]');
  const manifest = prepare(path.resolve(process.argv[2]), process.argv[3]);
  console.log(JSON.stringify({ count: manifest.count, prompt_sha256: manifest.prompt_sha256 }));
}
