// Run: node webapp/tests/ui_host.cjs OUTDIR TAG [W H]
// Playwright serves the repository files itself (no web server needed) and blocks every outside host.
// Needs the preinstalled Playwright + Chromium (require('playwright')).
// Teacher screen: setup, 2 rooms, access info, room detail, 9 rounds to results.
const { chromium } = require('playwright'); const fs = require('fs'), path = require('path'); const ROOT = require('path').resolve(__dirname, '../..');
const [OUT, TAG] = process.argv.slice(2), W = Number(process.argv[4] || 1366), H = Number(process.argv[5] || 900);
const T = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.wasm': 'application/wasm', '.zip': 'application/zip', '.glb': 'model/gltf-binary', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };
(async () => {
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: W, height: H } });
  await ctx.route(/^https?:\/\/(?!test\.local)/, (r) => r.abort());
  await ctx.route('http://test.local/**', (route) => { const f = path.join(ROOT, decodeURIComponent(new URL(route.request().url()).pathname)); if (!fs.existsSync(f) || fs.statSync(f).isDirectory()) return route.fulfill({ status: 404, body: 'nf' }); route.fulfill({ status: 200, body: fs.readFileSync(f), contentType: T[path.extname(f)] || 'application/octet-stream' }); });
  const p = await ctx.newPage(); const errs = []; p.on('pageerror', (e) => errs.push(e.message)); p.on('dialog', (d) => d.accept());
  await p.goto('http://test.local/webapp/host.html?local=1');
  await p.waitForSelector('button[data-act=new]:not([disabled])', { timeout: 120000 });
  await p.screenshot({ path: `${OUT}/${TAG}-1setup.png`, fullPage: true });
  await p.fill('[data-k=rooms]', '2'); await p.selectOption('[data-k=mode]', 'teacher');
  await p.click('button[data-act=new]');
  await p.waitForSelector('.room-card', { timeout: 60000 }); await p.waitForTimeout(1000);
  await p.screenshot({ path: `${OUT}/${TAG}-2pins.png`, fullPage: true });
  await p.click('button[data-act=pins]'); await p.waitForTimeout(300);
  await p.click('button[data-act=advall]'); await p.waitForTimeout(1500);
  await p.click('button[data-act=sel] >> nth=0'); await p.waitForTimeout(6000);
  await p.screenshot({ path: `${OUT}/${TAG}-3detail.png`, fullPage: true });
  for (let i = 0; i < 30; i++) { if (!(await p.$('button[data-act=advall]'))) break; await p.click('button[data-act=advall]').catch(() => {}); await p.waitForTimeout(500); const done = await p.evaluate(() => [...document.querySelectorAll('.room-phase')].every((e) => /끝/.test(e.textContent))); if (done) break; }
  await p.waitForTimeout(1500);
  await p.screenshot({ path: `${OUT}/${TAG}-4results.png`, fullPage: true });
  console.log('errors', errs); await b.close();
})().catch((e) => { console.error('FAIL', e.message.split('\n')[0]); process.exit(1); });
