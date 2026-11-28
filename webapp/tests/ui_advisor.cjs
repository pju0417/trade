// Run: node webapp/tests/ui_advisor.cjs OUTDIR [W H]
// Playwright serves the repository files itself (no web server needed) and blocks every outside host.
// Needs the preinstalled Playwright + Chromium (require('playwright')).
// Advisor '마루 선장' by help level (play.html, seed 7, Tropia):
//   normal: tour 6 steps; R1 coach (example, no number filled in); R2 hint (question); R4 only rule warnings appear
//           by themselves, strategy hint only after clicking the captain
//   many:   R4 still coach   alerts: no strategy at all (click → rule or '스스로')   off: no captain
// Prints PASS/FAIL per check and exits 1 on any failure.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const ROOT = path.resolve(__dirname, '../..');
const [OUT, W, H] = [process.argv[2] || '.', Number(process.argv[3] || 1280), Number(process.argv[4] || 860)];
const T = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.wasm': 'application/wasm', '.zip': 'application/zip', '.glb': 'model/gltf-binary', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };
let failed = 0;
const check = (name, ok, extra = '') => { console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`); if (!ok) failed++; };

async function game(b, level) {
  const ctx = await b.newContext({ viewport: { width: W, height: H } });
  await ctx.route(/^https?:\/\/(?!test\.local)/, (r) => r.abort());
  await ctx.route('http://test.local/**', (route) => { const f = path.join(ROOT, decodeURIComponent(new URL(route.request().url()).pathname)); if (!fs.existsSync(f) || fs.statSync(f).isDirectory()) return route.fulfill({ status: 404, body: 'nf' }); route.fulfill({ status: 200, body: fs.readFileSync(f), contentType: T[path.extname(f)] || 'application/octet-stream' }); });
  const p = await ctx.newPage(); const errs = [];
  p.on('pageerror', (e) => errs.push(e.message));
  await p.goto('http://test.local/webapp/play.html?local=1');
  await p.waitForSelector('button[data-act=new]:not([disabled])', { timeout: 120000 });
  await p.fill('input[data-k=seed]', '7'); await p.selectOption('select[data-k=advisor]', level);
  await p.click('button[data-act=new]'); await p.waitForSelector('#bar-handle:not([hidden])', { timeout: 60000 }); await p.click('#bar-handle');
  const fr = p.frameLocator('iframe[data-country=Tropia]');
  await fr.locator('#game:not([hidden]) .turn-dial').waitFor({ timeout: 60000 });
  await p.waitForTimeout(3000);
  const bubble = async () => (await fr.locator('#advisor .advisor-bubble p').count()) ? (await fr.locator('#advisor .advisor-bubble p').innerText()) : '';
  const allTips = async () => { const out = []; for (let k = 0; k < 6; k++) { const t = await bubble(); if (!t || out.includes(t)) break; out.push(t); if (!(await fr.locator('[data-adv=next]').count())) break; await fr.locator('[data-adv=next]').click(); await p.waitForTimeout(150); } return out; };
  // the round start card (fun-ui.js) covers the screen: close it after each round change
  const closeCards = async () => { await p.waitForTimeout(400); while (await fr.locator('.fun-card [data-fun=close]').count()) { await fr.locator('.fun-card [data-fun=close]').first().click(); await p.waitForTimeout(150); } };
  const toRound = async (r) => { for (let k = 0; k < 40; k++) { const t = await p.textContent('#bar b'); if (t.startsWith(`${r}라운드 · 판매`)) return closeCards(); await p.click('#bar button[data-act=adv]'); await p.waitForFunction((t) => document.querySelector('#bar b').textContent !== t, t, { timeout: 30000 }); } };
  return { p, fr, errs, bubble, allTips, toRound, close: () => ctx.close() };
}

(async () => {
  const b = await chromium.launch();
  // ---- normal
  let g = await game(b, 'normal');
  const tour = [];
  for (let i = 0; i < 6; i++) { tour.push(await g.bubble()); await g.fr.locator('[data-adv=tour-next]').click(); await g.p.waitForTimeout(200); }
  check('normal: tour has 6 steps', tour.filter(Boolean).length === 6);
  let tips = await g.allTips();
  check('normal R1: coach example for selling', tips.some((t) => /예를 들어 절반쯤/.test(t)), tips.join(' | ').slice(0, 160));
  await g.fr.locator('[data-adv=close]').click();
  await g.fr.locator('.advisor-face').click(); await g.p.waitForTimeout(200);
  const sellIdx = (await g.allTips()).findIndex((t) => /남아요/.test(t));
  await g.fr.locator('.advisor-face').click(); await g.fr.locator('.advisor-face').click(); await g.p.waitForTimeout(200);
  for (let k = 0; k < sellIdx; k++) await g.fr.locator('[data-adv=next]').click();
  await g.fr.locator('[data-adv=go]').click(); await g.p.waitForTimeout(400);
  check('normal R1: sell button opens sell tab without filling a number', (await g.fr.locator('.subtabs [aria-pressed=true]').innerText()).startsWith('팔기') && (await g.fr.locator('input[data-k="lq-banana-1"]').inputValue()) === '1');
  await g.p.screenshot({ path: `${OUT}/advisor-normal-r1.png` });
  await g.toRound(2); await g.p.waitForTimeout(800);
  tips = await g.allTips();
  check('normal R2: hint is a question', tips.some((t) => /몇 개를 팔고 몇 개를 남길까요/.test(t)), tips.join(' | ').slice(0, 160));
  check('normal R2: no coach example', !tips.some((t) => /예를 들어/.test(t)));
  await g.toRound(4); await g.p.waitForTimeout(800);
  tips = await g.allTips();
  check('normal R4: no strategy tip appears by itself', !tips.some((t) => /몇 개를 팔고|예를 들어/.test(t)), tips.join(' | ').slice(0, 160));
  if (await g.fr.locator('[data-adv=close]').count()) await g.fr.locator('[data-adv=close]').click();
  await g.fr.locator('.advisor-face').click(); await g.p.waitForTimeout(300);
  tips = await g.allTips();
  check('normal R4: clicking the captain shows a hint', tips.some((t) => /몇 개를 팔고|스스로/.test(t)), tips.join(' | ').slice(0, 160));
  await g.p.screenshot({ path: `${OUT}/advisor-normal-r4.png` });
  check('normal: no page errors', !g.errs.length, g.errs.join('; '));
  await g.close();
  // ---- many
  g = await game(b, 'many'); await g.fr.locator('[data-adv=tour-skip]').click(); await g.toRound(4); await g.p.waitForTimeout(800);
  tips = await g.allTips();
  check('many R4: still coach examples', tips.some((t) => /예를 들어 절반쯤/.test(t)), tips.join(' | ').slice(0, 160));
  await g.close();
  // ---- alerts
  g = await game(b, 'alerts'); await g.fr.locator('[data-adv=tour-skip]').click(); await g.p.waitForTimeout(500);
  tips = await g.allTips();
  check('alerts R1: no strategy tip by itself', !tips.some((t) => /몇 개를 팔고|예를 들어/.test(t)), tips.join(' | ').slice(0, 160));
  if (await g.fr.locator('[data-adv=close]').count()) await g.fr.locator('[data-adv=close]').click();
  await g.fr.locator('.advisor-face').click(); await g.p.waitForTimeout(300);
  tips = await g.allTips();
  check('alerts R1: clicking shows no strategy', !tips.some((t) => /몇 개를 팔고|예를 들어/.test(t)), tips.join(' | ').slice(0, 160));
  await g.close();
  // ---- off
  g = await game(b, 'off'); await g.p.waitForTimeout(500);
  check('off: no captain on screen', !(await g.fr.locator('#advisor .advisor-face').count()) || !(await g.fr.locator('#advisor').isVisible()));
  await g.close();
  await b.close();
  console.log(failed ? `${failed} check(s) failed` : 'all checks passed');
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error('FAIL', e.message.split('\n')[0]); process.exit(1); });
