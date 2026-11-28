// Run: node webapp/tests/ui_fun.cjs OUTDIR [W H]
// Playwright serves the repository files itself (no web server needed) and blocks every outside host.
// Fun layer (fun-ui.js) on play.html, seed 7, Tropia: sale → '출항!' notice + coins, round 2 start card
// (last round summary + 바닷길 신문), badges in the goals window, end ceremony with medal; teacher screen
// trade-route replay. Prints PASS/FAIL per check, exits 1 on any failure.
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
(async () => {
  const b = await chromium.launch();
  // ---------------- student (solo play)
  let ctx = await context(b), p = await ctx.newPage(); const errs = [];
  p.on('pageerror', (e) => errs.push(e.message));
  await p.goto('http://test.local/webapp/play.html?local=1');
  await p.waitForSelector('button[data-act=new]:not([disabled])', { timeout: 120000 });
  await p.fill('input[data-k=seed]', '7'); await p.click('button[data-act=new]');
  await p.waitForSelector('#bar-handle:not([hidden])', { timeout: 60000 }); await p.click('#bar-handle');
  const fr = p.frameLocator('iframe[data-country=Tropia]');
  await fr.locator('[data-adv=tour-skip]').click({ timeout: 60000 });
  if (await fr.locator('[data-adv=close]').count()) await fr.locator('[data-adv=close]').click();
  const closeCards = async () => { while (await fr.locator('.fun-card [data-fun=close]').count()) { await fr.locator('.fun-card [data-fun=close]').first().click(); await p.waitForTimeout(200); } };
  const nextPhase = async () => { const t = await p.textContent('#bar b'); await p.click('#bar button[data-act=adv]'); await p.waitForFunction((t) => document.querySelector('#bar b').textContent !== t, t, { timeout: 30000 }); await p.waitForTimeout(600); };
  // seed 7: nobody buys bananas until round 3 (everyone sells them); go to round 3 and sell cheaply there
  for (let k = 0; k < 6; k++) { await closeCards(); await nextPhase(); }
  await fr.locator('.fun-card.round').waitFor({ timeout: 20000 }).catch(() => {});
  const card = (await fr.locator('.fun-card.round').count()) ? await fr.locator('.fun-card.round').innerText() : '';
  check('round start card with last round summary', /3라운드 시작/.test(card) && /2라운드 결산/.test(card) && /판 것/.test(card), card.replace(/\s+/g, ' ').slice(0, 120));
  check('round card has 바닷길 신문 headlines', /바닷길 신문/.test(card) && (await fr.locator('.fun-news li').count()) >= 1, `${await fr.locator('.fun-news li').count()} headline(s)`);
  await p.waitForTimeout(1500); await p.screenshot({ path: `${OUT}/fun-round.png` });
  await closeCards();
  if (await fr.locator('[data-adv=close]').count()) await fr.locator('[data-adv=close]').click();
  await fr.locator('#hud-menu button[data-win=market]').click().catch(() => {});
  if (!(await fr.locator('input[data-k="lq-banana-1"]').count())) { await fr.locator('#hud-menu button[data-win=market]').click(); }
  if (await fr.locator('.subtabs button', { hasText: '팔기' }).count()) await fr.locator('.subtabs button', { hasText: '팔기' }).click();
  const free = Number((await fr.locator('#hud-top .res').nth(2).innerText()).trim().split(/\s+/)[0]) || 20;
  await fr.locator('input[data-k="lq-banana-1"]').fill(String(free));
  await fr.locator('input[data-k="lp-banana-1"]').fill('5');
  await fr.locator('button[data-act=list][data-good=banana]').click(); await p.waitForTimeout(500);
  await fr.locator('.turn-dial').click(); // → trading (AI first purchase happens now)
  await p.waitForTimeout(2500);
  const toasts = await fr.locator('#toasts').innerText();
  check('sale shows "출항!" notice', /출항!/.test(toasts), toasts.replace(/\s+/g, ' ').slice(0, 160));
  check('first export badge notice', /배지: 첫 수출/.test(toasts));
  await p.screenshot({ path: `${OUT}/fun-sale.png` });
  await fr.locator('#hud-menu button[data-win=goals]').click(); await p.waitForTimeout(400);
  const got = await fr.locator('#window .fun-badge.got').count();
  check('badges listed in goals window', (await fr.locator('#window .fun-badge').count()) >= 10 && got >= 1, `${got} earned`);
  await fr.locator('#hud-menu button[data-act=sound]').click(); await p.waitForTimeout(200);
  check('sound toggle switches off', (await fr.locator('#hud-menu button[data-act=sound]').getAttribute('aria-pressed')) === 'false');
  // play to the end with the teacher-style 'next phase' button, closing round cards
  for (let k = 0; k < 40; k++) {
    if (await fr.locator('.fun-card.ceremony').count()) break;
    if (await fr.locator('.fun-card.round').count()) await fr.locator('.fun-card [data-fun=close]').first().click();
    if (!(await p.$('#bar button[data-act=adv]'))) { await p.waitForTimeout(800); continue; }
    const t = await p.textContent('#bar b'); await p.click('#bar button[data-act=adv]');
    await p.waitForFunction((t) => document.querySelector('#bar b').textContent !== t, t, { timeout: 30000 });
  }
  await fr.locator('.fun-card.ceremony').waitFor({ timeout: 20000 }).catch(() => {});
  const cer = (await fr.locator('.fun-card.ceremony').count()) ? await fr.locator('.fun-card.ceremony').innerText() : '';
  check('end ceremony with medal, score and badges', /항해를 마쳤어요/.test(cer) && /모은 배지/.test(cer), cer.replace(/\s+/g, ' ').slice(0, 100));
  await p.waitForTimeout(1200); await p.screenshot({ path: `${OUT}/fun-ceremony.png` });
  check('student: no page errors', !errs.length, errs.join('; '));
  await ctx.close();
  // ---------------- teacher replay
  ctx = await context(b); p = await ctx.newPage(); const errs2 = [];
  p.on('pageerror', (e) => errs2.push(e.message)); p.on('dialog', (d) => d.accept());
  await p.goto('http://test.local/webapp/host.html?local=1');
  await p.waitForSelector('button[data-act=new]:not([disabled])', { timeout: 120000 });
  await p.selectOption('[data-k=mode]', 'teacher'); await p.click('button[data-act=new]');
  await p.waitForSelector('.room-card', { timeout: 60000 });
  for (let k = 0; k < 9; k++) { await p.click('button[data-act=advall]').catch(() => {}); await p.waitForTimeout(500); }
  await p.click('button[data-act=sel] >> nth=0'); await p.waitForTimeout(6000);
  await p.click('button[data-act=replay]'); await p.waitForTimeout(700);
  const note = await p.textContent('#replay-note').catch(() => '');
  check('teacher: trade-route replay runs', /라운드 무역로/.test(note), note);
  await p.screenshot({ path: `${OUT}/fun-replay.png` });
  check('teacher: no page errors', !errs2.length, errs2.join('; '));
  await ctx.close(); await b.close();
  console.log(failed ? `${failed} check(s) failed` : 'all checks passed');
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error('FAIL', e.message.split('\n')[0]); process.exit(1); });
