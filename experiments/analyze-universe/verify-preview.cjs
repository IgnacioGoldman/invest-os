const { chromium } = require('../../frontend/node_modules/playwright-core');
const assert = require('node:assert/strict');
const path = require('node:path');
(async () => {
  const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('file://' + path.join(__dirname, 'runs/2026-10-25/ranking.html'));
    assert.equal(await page.locator('tbody tr').count(), 200);
    assert.equal(await page.locator('thead th').count(), 7);
    assert.equal(await page.locator('td.support').count(), 200);
    assert.equal(await page.locator('tbody tr:visible').count(), 64);
    assert.equal(await page.locator('tbody tr:visible').first().locator('td strong').first().textContent(), 'ANIP');
    await page.locator('#financial-filter').selectOption('pass');
    assert.equal(await page.locator('tbody tr:visible').count(), 33);
    await page.locator('#financial-filter').selectOption('fail');
    assert.equal(await page.locator('tbody tr:visible').count(), 31);
    assert.equal(await page.locator('tbody tr:visible').first().locator('td strong').first().textContent(), 'BMY');
    await page.locator('#financial-filter').selectOption('all');
    await page.locator('#support-only').uncheck();
    assert.equal(await page.locator('tbody tr:visible').count(), 200);
    assert.equal(await page.locator('tbody tr').first().locator('.support-above').textContent(), 'Above Support');
    const anip = page.locator('tbody tr').filter({ has: page.locator('td strong', { hasText: /^ANIP$/ }) });
    assert.equal(await anip.locator('.support-at').textContent(), 'At Support');
    await page.locator('#search').fill('ADBE');
    assert.equal(await page.locator('tbody tr:visible').count(), 1);
    await page.locator('#search').fill('Unknown');
    assert.ok(await page.locator('tbody tr:visible').count() > 0);
    await page.locator('#search').fill('');
    await page.locator('#support-only').check();
    await page.screenshot({ path: '/private/tmp/invest-universe-1280.png' });
    assert.deepEqual(errors, []);
    console.log('Browser verified: default 64 supported stocks, 33 passing / 31 excluded, original 200 available, rule details and search work.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
