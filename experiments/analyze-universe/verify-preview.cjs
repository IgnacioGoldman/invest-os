const { chromium } = require('../../frontend/node_modules/playwright-core');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');

(async () => {
  const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 1000 }, acceptDownloads: true });
    const page = await context.newPage(), errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const url = 'file://' + path.join(__dirname, 'runs/2026-10-25/ranking.html');
    await page.goto(url);
    const data = await page.locator('#playground-data').evaluate(node => JSON.parse(node.textContent));
    const audit = JSON.parse(fs.readFileSync(path.join(__dirname, 'runs/2026-10-25/filter-research/support-audit.json')));
    const visibleSymbols = () => page.locator('tbody tr:visible').evaluateAll(rows => rows.map(row => row.dataset.symbol));
    const card = id => page.locator(`.filter-card[data-filter-id="${id}"]`);
    const field = index => page.getByLabel(`Condition ${index} metric`, { exact: true });
    const comparison = index => page.getByLabel(`Condition ${index} comparison`, { exact: true });
    const value = index => page.getByLabel(`Condition ${index} value`, { exact: true });
    const captureRates = () => page.locator('.capture-bar').evaluateAll(bars => bars.map(bar => Number(bar.dataset.percent)));
    async function assertCapture(symbols) {
      const retained = new Set(symbols);
      const expectedRates = Array.from({ length: 10 }, (_, index) => data.stocks.filter(stock =>
        stock.rank > index * 20 && stock.rank <= (index + 1) * 20 && retained.has(stock.symbol)).length * 5);
      assert.deepEqual(await captureRates(), expectedRates, 'Each chart bar is the retained share of its 20 original ranks');
      assert.equal(await page.locator('.capture-bar').evaluateAll(bars => bars.reduce((sum, bar) => sum + Number(bar.dataset.retained), 0)), symbols.length);
    }
    async function numericRule(index, key, operator, target) {
      await field(index).selectOption(key);
      await comparison(index).selectOption(operator);
      await value(index).fill(String(target));
    }
    async function save(name) {
      await page.locator('#filter-name').fill(name);
      await page.getByRole('button', { name: 'Save filter', exact: true }).click();
      assert.equal(await page.locator('#filter-builder').isVisible(), false);
    }
    assert.equal(await page.locator('tbody tr').count(), 200);
    assert.equal(await page.locator('thead th').count(), 10);
    assert.equal(await page.locator('td.red-flags').count(), 200);
    assert.equal(await page.locator('td.green-flags').count(), 200);
    assert.equal(await page.locator('tbody tr:visible').count(), 200);
    assert.deepEqual(await captureRates(), Array(10).fill(100));
    assert.match(await page.locator('#capture-summary').textContent(), /200 of 200 stocks retained \(100% overall\)/);
    assert.equal(await page.locator('#filter-builder').evaluate(node => node.nextElementSibling.id), 'capture-panel');
    assert.equal(await page.getByText('Method and evidence limits', { exact: true }).count(), 0);
    assert.equal(await page.locator('#financial-refresh, #flag-explanation, #support-only, #financial-filter').count(), 0);
    for (const preset of data.presets) {
      await card(preset.id).click();
      assert.deepEqual(await visibleSymbols(), preset.symbols, `${preset.name} must match the actual app evaluator`);
      await assertCapture(preset.symbols);
      assert.equal(await page.locator('#edit-filter').isVisible(), false);
      assert.equal(await page.locator('#delete-filter').isVisible(), false);
      assert.equal(await card(preset.id).getAttribute('aria-pressed'), 'true');
    }
    await card('default:test-1').click();
    await page.locator('#customize-filter').click();
    assert.equal(await page.locator('.condition').count(), 4);
    assert.equal(await page.getByLabel('Condition 3 timeframe: 1M', { exact: true }).isChecked(), true);
    assert.equal(await page.getByLabel('Condition 3 timeframe: 1Y', { exact: true }).isChecked(), false);
    await save('Pullback experiment');
    const savedId = await page.locator('.filter-card[aria-pressed=true]').getAttribute('data-filter-id');
    assert.deepEqual(await visibleSymbols(), data.presets[0].symbols);
    await page.reload();
    await card(savedId).click();
    assert.deepEqual(await visibleSymbols(), data.presets[0].symbols, 'Custom filters survive reload');

    // Build the previous support + three financial rules from scratch.
    await page.locator('#new-filter').click();
    await numericRule(1, 'revenue', 'gt', 0);
    await page.locator('#add-rule').click();
    await numericRule(2, 'operating_margin', 'gt', 0);
    await page.locator('#add-rule').click();
    await numericRule(3, 'red_flag_count', 'lte', 1);
    await page.locator('#add-rule').click();
    await field(4).selectOption('support');
    const expected = data.stocks.filter(stock => audit.stocks[stock.symbol].at_or_near_support
      && audit.stocks[stock.symbol].passes_financial_rules).map(stock => stock.symbol);
    assert.equal(expected.length, audit.pass_all_three);
    assert.ok((await page.locator('#preview-count').textContent()).startsWith(`${expected.length} of 200`));
    await assertCapture(expected);
    assert.match(await page.locator('#capture-summary').textContent(), /^Draft:/);
    await save('Financial + support');
    assert.deepEqual(await visibleSymbols(), expected, 'Custom numeric/support conditions match the independent audit');
    assert.equal((await visibleSymbols()).includes('BMY'), false, 'Partial zero-detected red flags must not pass numeric rules');

    // Edit, OR logic, stable original ranks, search, sorting, and export.
    await page.locator('#edit-filter').click();
    await page.getByRole('button', { name: 'Remove condition 4', exact: true }).click();
    await page.getByRole('button', { name: 'Remove condition 3', exact: true }).click();
    await numericRule(1, 'rank', 'eq', 1);
    await numericRule(2, 'rank', 'eq', 200);
    await page.locator('#rule-logic').selectOption('or');
    assert.match(await page.locator('#preview-count').textContent(), /^2 of 200/);
    assert.deepEqual(await captureRates(), [5, 0, 0, 0, 0, 0, 0, 0, 0, 5], 'Draft capture includes ranks 1 and 200 in the correct end groups');
    await save('Rank endpoints');
    const endpoints = [data.stocks[0].symbol, data.stocks[199].symbol];
    assert.deepEqual(await visibleSymbols(), endpoints);
    await page.locator('#sort').selectOption('rank-desc');
    assert.deepEqual(await visibleSymbols(), [...endpoints].reverse());
    await page.locator('#search').fill(endpoints[0]);
    assert.deepEqual(await visibleSymbols(), [endpoints[0]]);
    await page.locator('#search').fill('no-matching-symbol-xyz');
    assert.equal(await page.locator('#empty-results').isVisible(), true);
    assert.equal(await page.locator('#export-results').isDisabled(), true);
    assert.deepEqual(await captureRates(), [5, 0, 0, 0, 0, 0, 0, 0, 0, 5], 'Search does not change the filter capture distribution');
    await page.locator('#search').fill('');
    const downloadPromise = page.waitForEvent('download');
    await page.locator('#export-results').click();
    const download = await downloadPromise;
    const downloaded = fs.readFileSync(await download.path(), 'utf8');
    assert.equal(download.suggestedFilename(), 'rank-endpoints-ranking.csv');
    assert.ok(downloaded.includes('"200","MSTR"'));
    assert.ok(downloaded.includes('"1","ADBE"'));
    assert.equal(downloaded.trim().split('\r\n').length, 3);

    page.once('dialog', dialog => dialog.dismiss());
    await page.locator('#delete-filter').click();
    assert.equal(await page.locator('#active-name').textContent(), 'Rank endpoints');
    page.once('dialog', dialog => dialog.accept());
    await page.locator('#delete-filter').click();
    assert.equal(await page.locator('#active-name').textContent(), 'All stocks');
    assert.equal(await page.locator('tbody tr:visible').count(), 200);

    // Unknown green counts are excluded; quality/valuation use review tags.
    await page.locator('#new-filter').click();
    await numericRule(1, 'green_flag_count', 'gte', 2);
    await page.locator('#add-rule').click();
    await field(2).selectOption('business_quality');
    await page.getByLabel('Condition 2 value: Solid', { exact: true }).check();
    await page.locator('#add-rule').click();
    await field(3).selectOption('review_valuation');
    await page.getByLabel('Condition 3 value: Fair', { exact: true }).check();
    await save('Green quality');
    const greenExpected = data.stocks.filter(stock => stock.metrics.green_flag_count.value != null
      && stock.metrics.green_flag_count.value >= 2 && ['Strong', 'Solid'].includes(stock.business_quality)
      && ['Cheap', 'Fair'].includes(stock.valuation)).map(stock => stock.symbol);
    await page.locator('#sort').selectOption('rank-asc');
    assert.deepEqual(await visibleSymbols(), greenExpected);

    await page.locator('#new-filter').click();
    await field(1).selectOption('support');
    for (const timeframe of data.timeframes) await page.getByLabel(`Condition 1 timeframe: ${timeframe.label}`, { exact: true }).uncheck();
    await page.locator('#filter-name').fill('No timeframes');
    await page.getByRole('button', { name: 'Save filter', exact: true }).click();
    assert.match(await page.locator('#form-error').textContent(), /at least one timeframe/);
    assert.equal(await page.locator('#capture-chart svg').count(), 0, 'Invalid drafts must not display stale or fabricated capture bars');
    await page.getByLabel('Condition 1 timeframe: 1M', { exact: true }).check();
    await page.locator('#filter-name').fill('Pullback');
    await page.getByRole('button', { name: 'Save filter', exact: true }).click();
    assert.match(await page.locator('#form-error').textContent(), /unique filter name/);
    await numericRule(1, 'revenue', 'gt', 0);
    await value(1).fill('');
    assert.match(await page.locator('#preview-count').textContent(), /finite number/);
    await page.locator('#close-builder').click();
    await assertCapture(greenExpected);

    // A valid filter retaining nothing has ten zero bars and a 0% baseline.
    await page.locator('#new-filter').click();
    await numericRule(1, 'rank', 'gt', 200);
    assert.deepEqual(await captureRates(), Array(10).fill(0));
    assert.match(await page.locator('#capture-summary').textContent(), /0 of 200 stocks retained \(0% overall\)/);
    await page.locator('.capture-bar').last().focus();
    assert.match(await page.locator('#capture-detail').textContent(), /Ranks 181–200: 0 of 20 retained \(0%\)/);
    await page.locator('#close-builder').click();

    await card('all').click();
    const bmy = page.locator('tr[data-symbol="BMY"]');
    assert.equal(await bmy.locator('.red-flags > strong').textContent(), '0 detected');
    assert.match(await bmy.locator('.red-flags').textContent(), /3\/4 assessed/);
    assert.match(await bmy.locator('.flags-not-assessed').textContent(), /Consecutive margin deterioration/);
    assert.match(await bmy.locator('.flags-not-assessed').textContent(), /FY2025 Q1/);
    for (const [symbol, stock] of Object.entries(audit.stocks)) {
      const row = page.locator(`tr[data-symbol="${symbol}"]`);
      for (const [color, key] of [['red', 'red_flag_count'], ['green', 'green_flag_count']]) {
        const metric = stock.flag_metrics[key];
        const outsideScope = metric.checks.length && metric.checks.every(group => group.state === 'not_applicable');
        const expectedLabel = outsideScope ? 'Not applicable' : metric.value != null ? String(metric.value)
          : metric.coverage.assessed ? `${metric.observed_count} detected` : 'Not assessed';
        assert.equal(await row.locator(`.${color}-flags > strong`).textContent(), expectedLabel, `${symbol}: ${color} assessment`);
        for (const missing of stock.flags_not_assessed[color]) {
          assert.ok((await row.locator('.flags-not-assessed').textContent()).includes(missing.reason), `${symbol}: missing ${missing.id}`);
        }
      }
    }
    const anip = page.locator('tr[data-symbol="ANIP"]');
    await anip.locator('.green-flags summary').click();
    assert.match(await anip.locator('.green-flags details').textContent(), /Revenue YoY growth ≥ 8%/);
    await anip.locator('.green-flags summary').click();
    await card('default:test-1').click();
    await page.locator('#capture-panel').screenshot({ path: '/private/tmp/invest-ranked-capture-1280.png' });
    await page.screenshot({ path: '/private/tmp/invest-universe-1280.png' });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: '/private/tmp/invest-universe-390.png' });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, 'Only the cards and table should scroll horizontally');
    assert.deepEqual(errors, []);

    const restricted = await browser.newContext();
    await restricted.addInitScript(() => {
      Storage.prototype.getItem = () => { throw new Error('Storage blocked'); };
      Storage.prototype.setItem = () => { throw new Error('Storage blocked'); };
    });
    const limitedPage = await restricted.newPage();
    await limitedPage.goto(url);
    assert.equal(await limitedPage.locator('tbody tr:visible').count(), 200);
    assert.equal(await limitedPage.locator('#storage-message').isVisible(), true);
    await limitedPage.locator('#new-filter').click();
    await limitedPage.locator('#filter-name').fill('Session filter');
    await limitedPage.getByRole('button', { name: 'Save filter', exact: true }).click();
    assert.equal(await limitedPage.locator('#active-name').textContent(), 'Session filter');
    await restricted.close();
    console.log('Browser verified: ranked capture deciles for all/preset/custom/draft/empty filters, original-rank boundaries, search independence, keyboard inspection, app preset parity, rule audit parity, persistence, editing/deleting, CSV export, mobile layout and storage fallback.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
