const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const ts = require('typescript');

require.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText, filename);
const { stockFromRouteSegment, stockRoutePath } = require('../src/stockRoutes.ts');
const stocks = JSON.parse(fs.readFileSync(path.join(__dirname, '../public/data/open-data/stocks.json'), 'utf8'));

test('every stock URL resolves back to its own ticker under root and Pages hosting', () => {
  for (const base of ['/', '/invest-os/', '/invest-os']) {
    const prefix = base.endsWith('/') ? base : `${base}/`;
    for (const stock of stocks) {
      const url = stockRoutePath(stock, base);
      assert.equal(url, `${prefix}${encodeURIComponent(stock.ticker)}`);
      const segment = decodeURIComponent(url.slice(prefix.length));
      assert.equal(stockFromRouteSegment(stocks, segment)?.ticker, stock.ticker);
      assert.equal(stockFromRouteSegment(stocks, segment.toLowerCase())?.ticker, stock.ticker);
    }
  }
});

test('DTM, AMD and AMAT open the selected stock regardless of dataset order', () => {
  for (const rows of [stocks, [...stocks].reverse()]) {
    for (const ticker of ['DTM', 'AMD', 'AMAT']) {
      const stock = rows.find((item) => item.ticker === ticker);
      assert.ok(stock, ticker);
      const segment = stockRoutePath(stock, '/').slice(1);
      assert.equal(stockFromRouteSegment(rows, segment)?.ticker, ticker);
    }
    assert.equal(stockFromRouteSegment(rows, 'DT')?.ticker, 'DT');
  }
});

test('unambiguous legacy company links remain supported and collisions are rejected', () => {
  const rows = [
    { ticker: 'DTM', name: 'DT Midstream, Inc.' },
    { ticker: 'DT', name: 'Dynatrace, Inc.' },
    { ticker: 'AMD', name: 'Advanced Micro Devices' },
    { ticker: 'AEIS', name: 'Advanced Energy Industries' },
    { ticker: 'AMAT', name: 'Applied Materials' },
    { ticker: 'AAOI', name: 'Applied Optoelectronics' },
  ];
  for (const ordered of [rows, [...rows].reverse()]) {
    assert.equal(stockFromRouteSegment(ordered, 'Dynatrace')?.ticker, 'DT');
    assert.equal(stockFromRouteSegment(ordered, 'DT')?.ticker, 'DT');
    assert.equal(stockFromRouteSegment(ordered, 'Advanced'), null);
    assert.equal(stockFromRouteSegment(ordered, 'Applied'), null);
  }
  const legacy = [{ ticker: 'TEST', name: 'Example-Company, Inc.' }];
  assert.equal(stockFromRouteSegment(legacy, 'example-company')?.ticker, 'TEST');
});

test('ticker punctuation and URL encoding preserve distinct listing symbols', () => {
  const rows = ['BRK.B', 'BRK-B', 'NIBE-B.ST', 'A/B'].map((ticker, index) => ({ ticker, name: `Company${index} Holdings` }));
  for (const stock of rows) {
    const segment = decodeURIComponent(stockRoutePath(stock, '/').slice(1));
    assert.equal(stockFromRouteSegment(rows, segment)?.ticker, stock.ticker);
  }
  assert.equal(stockRoutePath(rows[3], '/'), '/A%2FB');
  assert.equal(stockFromRouteSegment(rows, 'BRKB'), null);
});

test('empty and unknown routes do not select a stock', () => {
  for (const segment of [null, '', '---', 'unknown-company']) {
    assert.equal(stockFromRouteSegment(stocks, segment), null);
  }
});
