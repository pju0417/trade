// Run: node webapp/tests/ui_play.cjs OUTDIR [W H]
// Playwright serves the repository files itself (no web server needed) and blocks every outside host.
// Needs the preinstalled Playwright + Chromium (require('playwright')).
// Student game screen on play.html (seed 7, Tropia): market window, stepper, list, buy, goals, invest, 9 rounds to results.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const ROOT = require('path').resolve(__dirname, '../..');
const OUT = process.argv[2];
const W = Number(process.argv[3] || 1280), H = Number(process.argv[4] || 860);
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
  '.wasm': 'application/wasm', '.zip': 'application/zip', '.glb': 'model/gltf-binary', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.svg': 'image/svg+xml' };
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: W, height: H } });
  await ctx.route(/^https?:\/\/(?!test\.local)/, (r) => r.abort());
  await ctx.route('http://test.local/**', (route) => {
    const u = new URL(route.request().url());
    const f = path.join(ROOT, decodeURIComponent(u.pathname));
    if (!f.startsWith(ROOT) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) return route.fulfill({ status: 404, body: 'nf' });
    route.fulfill({ status: 200, body: fs.readFileSync(f), contentType: TYPES[path.extname(f)] || 'application/octet-stream' });
  });
  const p = await ctx.newPage();
  const errs = [];
  p.on('pageerror', (e) => errs.push('page:' + e.message));
  p.on('console', (m) => { if (m.type() === 'error') errs.push('console:' + m.text()); });
  p.on('frameattached', () => {});
  ctx.on('page', () => {});
  await p.goto('http://test.local/webapp/play.html?local=1');
  await p.waitForSelector('button[data-act=new]:not([disabled])', { timeout: 120000 });
  await p.fill('input[data-k=seed]', '7');
  await p.click('button[data-act=new]'); await p.waitForSelector('#bar-handle:not([hidden])', { timeout: 60000 }); await p.click('#bar-handle');
  await p.waitForSelector('#bar:not([hidden]) button[data-act=adv]', { timeout: 60000 });
  const fr = p.frameLocator('iframe[data-country=Tropia]');
  const frame = () => p.frames().find((f) => f.url().includes('student.html'));
  await fr.locator('#game:not([hidden]) .turn-dial').waitFor({ timeout: 30000 });
  frame().on?.('pageerror', (e) => errs.push('frame:' + e.message));
  await p.waitForTimeout(9000);
  await p.screenshot({ path: `${OUT}/g1-listing-${W}.png` });
  console.log('window:', await fr.locator('#window .win-head h2').innerText());
  console.log('top:', (await fr.locator('#hud-top').innerText()).replace(/\s+/g, ' '));
  console.log('toasts:', (await fr.locator('#toasts').innerText()).replace(/\s+/g, ' '));
  if (process.argv[5] === 'quick') { console.log('errors:', errs); await b.close(); return; }
  // sell 3 bananas at quote price
  for (let i = 0; i < 2; i++) await fr.locator('[data-act=step][data-k="lq-banana-1"][data-d="1"]').click();
  console.log('stepper qty:', await fr.locator('input[data-k="lq-banana-1"]').inputValue(), 'price:', await fr.locator('input[data-k="lp-banana-1"]').inputValue());
  await fr.locator('button[data-act=list][data-good=banana]').click();
  await p.waitForTimeout(800);
  console.log('after list toasts:', (await fr.locator('#toasts').innerText()).replace(/\s+/g, ' '));
  await fr.locator('.turn-dial').click();
  await fr.locator('#window .win-head h2', { hasText: '거래' }).waitFor({ timeout: 15000 });
  await p.waitForTimeout(1500);
  await p.screenshot({ path: `${OUT}/g2-trading-${W}.png` });
  const buy = fr.locator('#window button[data-act=buy]').first();
  if (await buy.count()) { await buy.click(); await p.waitForTimeout(800); }
  console.log('after buy toasts:', (await fr.locator('#toasts').innerText()).replace(/\s+/g, ' '));
  await fr.locator('#hud-menu button[data-win=goals]').click();
  await p.waitForTimeout(500);
  await p.screenshot({ path: `${OUT}/g3-goals-${W}.png` });
  await fr.locator('.turn-dial').click();
  await fr.locator('#window .win-head h2', { hasText: '투자' }).waitFor({ timeout: 15000 });
  await p.waitForTimeout(800);
  await p.screenshot({ path: `${OUT}/g4-invest-${W}.png` });
  for (let i = 0; i < 40; i++) {
    const adv = await p.$('#bar button[data-act=adv]');
    if (!adv) break;
    const t = await p.textContent('#bar b');
    await adv.click();
    await p.waitForFunction((t) => document.querySelector('#bar b').textContent !== t, t, { timeout: 30000 });
  }
  await fr.locator('#window .big-score').waitFor({ timeout: 15000 });
  await p.waitForTimeout(1000);
  await p.screenshot({ path: `${OUT}/g5-result-${W}.png` });
  console.log('result:', (await fr.locator('#window').innerText()).replace(/\s+/g, ' ').slice(0, 120));
  console.log('errors:', errs);
  await b.close();
})().catch((e) => { console.error('FAIL', e.message.split('\n')[0]); process.exit(1); });
