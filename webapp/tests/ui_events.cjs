// Run: node webapp/tests/ui_events.cjs OUTDIR [W H]
// World event cards (RULES_v1 §10) on screen: solo play with events on (seed 7) shows the event on the
// round 2 start card and in the HUD; with events off nothing appears; teacher room card shows the event.
// Prints PASS/FAIL per check, exits 1 on any failure.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const ROOT = path.resolve(__dirname, '../..');
const [OUT, W, H] = [process.argv[2] || '.', Number(process.argv[3] || 1280), Number(process.argv[4] || 860)];
const T = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.wasm': 'application/wasm', '.zip': 'application/zip', '.glb': 'model/gltf-binary', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };
let failed = 0;
const check = (name, ok, extra = '') => { console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`); if (!ok) failed++; };
async function context(b) {
  const ctx = await b.newContext({ viewport: { width: W, height: H } });
  await ctx.route(/^https?:\/\/(?!test\.local)/, (r) => r.abort());
  await ctx.route('http://test.local/**', (route) => { const f = path.join(ROOT, decodeURIComponent(new URL(route.request().url()).pathname)); if (!fs.existsSync(f) || fs.statSync(f).isDirectory()) return route.fulfill({ status: 404, body: 'nf' }); route.fulfill({ status: 200, body: fs.readFileSync(f), contentType: T[path.extname(f)] || 'application/octet-stream' }); });
  return ctx;
}
async function solo(b, events) {
  const ctx = await context(b), p = await ctx.newPage(), errs = [];
  p.on('pageerror', (e) => errs.push(e.message));
  await p.goto('http://test.local/webapp/play.html?local=1');
  await p.waitForSelector('button[data-act=new]:not([disabled])', { timeout: 120000 });
  await p.fill('input[data-k=seed]', '7'); await p.selectOption('select[data-k=events]', events);
  await p.click('button[data-act=new]'); await p.waitForSelector('#bar-handle:not([hidden])', { timeout: 60000 }); await p.click('#bar-handle');
  const fr = p.frameLocator('iframe[data-country=Tropia]');
  await fr.locator('[data-adv=tour-skip]').click({ timeout: 60000 });
  for (let k = 0; k < 3; k++) { const t = await p.textContent('#bar b'); await p.click('#bar button[data-act=adv]'); await p.waitForFunction((t) => document.querySelector('#bar b').textContent !== t, t, { timeout: 30000 }); }
  await fr.locator('.fun-card.round').waitFor({ timeout: 20000 }).catch(() => {});
  await p.waitForTimeout(1200);
  const res = { card: (await fr.locator('.fun-event').count()) ? await fr.locator('.fun-event').innerText() : '', chip: (await fr.locator('#hud-top .event-chip').count()) ? await fr.locator('#hud-top .event-chip').innerText() : '' };
  await p.screenshot({ path: `${OUT}/events-${events}.png` });
  res.errs = errs; await ctx.close(); return res;
}
(async () => {
  const b = await chromium.launch();
  const on = await solo(b, 'random');
  check('events on: round 2 card shows the world event', /세계 사건/.test(on.card) && on.card.length > 10, on.card.replace(/\s+/g, ' '));
  check('events on: HUD shows this round\'s event', /이번 라운드 사건/.test(on.chip), on.chip.replace(/\s+/g, ' '));
  check('events on: no page errors', !on.errs.length, on.errs.join('; '));
  const off = await solo(b, 'off');
  check('events off: no event card or chip', !off.card && !off.chip);
  // teacher
  const ctx = await context(b), p = await ctx.newPage(), errs = [];
  p.on('pageerror', (e) => errs.push(e.message)); p.on('dialog', (d) => d.accept());
  await p.goto('http://test.local/webapp/host.html?local=1');
  await p.waitForSelector('button[data-act=new]:not([disabled])', { timeout: 120000 });
  await p.selectOption('[data-k=mode]', 'teacher'); await p.selectOption('[data-k=events]', 'random');
  await p.click('button[data-act=new]'); await p.waitForSelector('.room-card', { timeout: 60000 });
  for (let k = 0; k < 3; k++) { await p.click('button[data-act=advall]').catch(() => {}); await p.waitForTimeout(600); }
  const ev = (await p.locator('.room-event').count()) ? await p.locator('.room-event').first().innerText() : '';
  check('teacher: room card shows the event in round 2', /사건/.test(ev), ev);
  await p.screenshot({ path: `${OUT}/events-teacher.png` });
  check('teacher: no page errors', !errs.length, errs.join('; '));
  await ctx.close(); await b.close();
  console.log(failed ? `${failed} check(s) failed` : 'all checks passed');
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error('FAIL', e.message.split('\n')[0]); process.exit(1); });
