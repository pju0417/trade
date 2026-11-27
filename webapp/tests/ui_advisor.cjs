// Run: node webapp/tests/ui_advisor.cjs OUTDIR [W H]
// Playwright serves the repository files itself (no web server needed) and blocks every outside host.
// Needs the preinstalled Playwright + Chromium (require('playwright')).
// Advisor '마루 선장': 6-step tour, listing/trading/invest advice, buttons (sell tab, filled buy offer).
const { chromium } = require('playwright'); const fs = require('fs'), path = require('path'); const ROOT = require('path').resolve(__dirname, '../..');
const [OUT, W, H] = [process.argv[2], Number(process.argv[3] || 1280), Number(process.argv[4] || 860)];
const T = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.wasm': 'application/wasm', '.zip': 'application/zip', '.glb': 'model/gltf-binary', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.svg': 'image/svg+xml' };
(async () => {
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: W, height: H } });
  await ctx.route(/^https?:\/\/(?!test\.local)/, (r) => r.abort());
  await ctx.route('http://test.local/**', (route) => { const f = path.join(ROOT, decodeURIComponent(new URL(route.request().url()).pathname)); if (!fs.existsSync(f) || fs.statSync(f).isDirectory()) return route.fulfill({ status: 404, body: 'nf' }); route.fulfill({ status: 200, body: fs.readFileSync(f), contentType: T[path.extname(f)] || 'application/octet-stream' }); });
  const p = await ctx.newPage(); const errs = [];
  p.on('pageerror', (e) => errs.push('page:' + e.message)); p.on('console', (m) => { if (m.type() === 'error') errs.push('console:' + m.text()); });
  await p.goto('http://test.local/webapp/play.html?local=1');
  await p.waitForSelector('button[data-act=new]:not([disabled])', { timeout: 120000 });
  await p.fill('input[data-k=seed]', '7'); await p.click('button[data-act=new]'); await p.waitForSelector('#bar-handle:not([hidden])', { timeout: 60000 }); await p.click('#bar-handle');
  const fr = p.frameLocator('iframe[data-country=Tropia]');
  await fr.locator('#advisor .advisor-bubble').waitFor({ timeout: 60000 });
  await p.waitForTimeout(6000);
  const texts = [];
  for (let i = 0; i < 6; i++) {
    texts.push((await fr.locator('#advisor .advisor-bubble p').innerText()).slice(0, 60));
    if (i === 1 || i === 4) await p.screenshot({ path: `${OUT}/adv-tour${i}-${W}.png` });
    await fr.locator('[data-adv=tour-next]').click(); await p.waitForTimeout(300);
  }
  console.log('tour:', texts.join(' | '));
  await p.waitForTimeout(500);
  console.log('listing tip:', await fr.locator('#advisor .advisor-bubble p').innerText());
  await p.screenshot({ path: `${OUT}/adv-listing-${W}.png` });
  await fr.locator('[data-adv=go]').click(); await p.waitForTimeout(500);
  console.log('window after go:', await fr.locator('#window .win-head h2').innerText(), '| tab:', await fr.locator('.subtabs [aria-pressed=true]').innerText());
  await fr.locator('.turn-dial').click();
  await fr.locator('#window .win-head h2', { hasText: '거래' }).waitFor({ timeout: 15000 }); await p.waitForTimeout(1200);
  console.log('trading tip:', await fr.locator('#advisor .advisor-bubble p').innerText());
  await p.screenshot({ path: `${OUT}/adv-trading-${W}.png` });
  await fr.locator('[data-adv=go]').click(); await p.waitForTimeout(500);
  const form = await fr.locator('.offer-form').evaluate((f) => ['of-to', 'of-kind', 'of-get-good', 'of-get-qty', 'of-cash'].map((k) => k + '=' + f.querySelector(`[data-k="${k}"]`).value).join(' '));
  console.log('offer form:', form);
  await fr.locator('[data-act=offer]').click(); await p.waitForTimeout(800);
  console.log('offer result toast:', (await fr.locator('#toasts').innerText()).replace(/\s+/g, ' ').slice(-90));
  await p.screenshot({ path: `${OUT}/adv-offer-${W}.png` });
  await fr.locator('.turn-dial').click();
  await fr.locator('#window .win-head h2', { hasText: '투자' }).waitFor({ timeout: 15000 }); await p.waitForTimeout(1200);
  console.log('invest tip:', await fr.locator('#advisor .advisor-bubble p').innerText());
  await p.screenshot({ path: `${OUT}/adv-invest-${W}.png` });
  console.log('errors:', errs); await b.close();
})().catch((e) => { console.error('FAIL', e.message.split('\n')[0]); process.exit(1); });
