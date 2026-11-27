// Run: node webapp/tests/map_audit.cjs [json-out]
// Playwright serves the repository files itself (no web server needed) and blocks every outside host.
// Needs the preinstalled Playwright + Chromium (require('playwright')).
// World map audit on the demo: floating/buried houses and props, airports on slopes, dangling roads. All counts should be 0 (roadOverWater 1 = harbour quay).
const { chromium } = require('playwright'); const fs = require('fs'), path = require('path'); const ROOT = require('path').resolve(__dirname, '../..');
const T = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.glb': 'model/gltf-binary' };
(async () => {
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 900, height: 600 } });
  await ctx.route(/^https?:\/\/(?!test\.local)/, (r) => r.abort());
  await ctx.route('http://test.local/**', (route) => { const f = path.join(ROOT, decodeURIComponent(new URL(route.request().url()).pathname)); if (!fs.existsSync(f) || fs.statSync(f).isDirectory()) return route.fulfill({ status: 404, body: '' }); route.fulfill({ status: 200, body: fs.readFileSync(f), contentType: T[path.extname(f)] || 'application/octet-stream' }); });
  const p = await ctx.newPage(); const errs = []; p.on('pageerror', (e) => errs.push(e.message));
  const t0 = Date.now();
  await p.goto('http://test.local/version2/world-map-demo.html?nodemo&test&panel=0');
  await p.waitForFunction(() => window.worldMap, null, { timeout: 60000 });
  const built = Date.now() - t0;
  const a = await p.evaluate(() => worldMap.audit());
  const counts = Object.fromEntries(Object.entries(a).map(([k, v]) => [k, v.length]));
  console.log('build ms', built, JSON.stringify(counts));
  for (const k of Object.keys(a)) if (a[k].length) console.log(k, JSON.stringify(a[k].slice(0, 6)));
  if (process.argv[2]) fs.writeFileSync(process.argv[2], JSON.stringify(a));
  console.log('errors', errs); await b.close();
})().catch((e) => { console.error('FAIL', e.message.split('\n')[0]); process.exit(1); });
