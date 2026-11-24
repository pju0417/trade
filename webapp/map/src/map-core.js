// 무역 게임 세계 지도 (three.js r128). 9개국이 사는 가상 세계를 코드로 만들어 그린다.
// createWorldMap(container, THREE, opts) → { update(state), setProfiles, setTrades, setMe, flyToNation, ... }
// 화면 계약은 webapp/map/README.md. 이 파일은 build.mjs가 world-map.js(ES 모듈)·데모 HTML·JSX로 감싼다.
function createWorldMap(container, THREE, opts) {
  opts = opts || {};
  // ───────────────────────── 상수 ─────────────────────────
  var WX = 100, WZ = 62, CELL = 0.25, FW = Math.round(2 * WX / CELL), FH = Math.round(2 * WZ / CELL);
  var GROUND_Y = 0.12, QUAY_TOP = 0.2;
  var DMIN = 1.6, DMAX = 190;
  var FONT = "'Pretendard','Apple SD Gothic Neo','Malgun Gothic','Noto Sans KR',sans-serif";
  var GOODS = {
    wheat:       { ko: '밀',       icon: '🌾', color: '#c8913a', port: 'grain',     prop: 'farm' },
    banana:      { ko: '바나나',   icon: '🍌', color: '#e8c51e', port: 'fruit',     prop: 'palm' },
    fuel:        { ko: '연료',     icon: '🛢️', color: '#e0533d', port: 'oil',       prop: 'pump' },
    ore:         { ko: '광물',     icon: '⛏️', color: '#8b5a2b', port: 'ore',       prop: 'mine' },
    machine:     { ko: '기계',     icon: '⚙️', color: '#5b6f82', port: 'container', prop: 'factory' },
    electronics: { ko: '전자제품', icon: '💻', color: '#2f6fd6', port: 'container', prop: 'tech' }
  };
  var GOOD_KEYS = ['wheat', 'banana', 'fuel', 'ore', 'machine', 'electronics'];
  // 나라 배치: 위치(x, z; 북쪽이 -z), 크기 r, 지형(biome), 산 많음(mount), 정치 지도 색
  var NATIONS = [
    { key: 'Mechania', ko: '메카니아', good: 'machine',     x: -62, z: -26, r: 15, biome: 'temperate', mount: 0.35, color: '#9fc7e0' },
    { key: 'Grainia',  ko: '그레니아', good: 'wheat',       x: -33, z: -20, r: 16, biome: 'plains',    mount: 0.05, color: '#f0d27a' },
    { key: 'Ferria',   ko: '페리아',   good: 'ore',         x: -50, z: -47, r: 12, biome: 'boreal',    mount: 1.0,  color: '#c3b6d9' },
    { key: 'Technia',  ko: '테크니아', good: 'electronics', x: 52,  z: -27, r: 16, biome: 'temperate', mount: 0.4,  color: '#a9d8b8' },
    { key: 'Novia',    ko: '노비아',   good: 'electronics', x: 80,  z: -43, r: 8,  biome: 'island',    mount: 0.25, color: '#f5b6c4' },
    { key: 'Oilia',    ko: '오일리아', good: 'fuel',        x: 3,   z: -5,  r: 17, biome: 'desert',    mount: 0.15, color: '#f4a978' },
    { key: 'Tropia',   ko: '트로피아', good: 'banana',      x: 29,  z: 17,  r: 13, biome: 'tropical',  mount: 0.3,  color: '#b9e08c' },
    { key: 'Mineria',  ko: '미네리아', good: 'ore',         x: 62,  z: 37,  r: 17, biome: 'outback',   mount: 0.6,  color: '#e8a3a0' },
    { key: 'Agrea',    ko: '아그레아', good: 'banana',      x: -46, z: 25,  r: 16, biome: 'tropical',  mount: 0.35, color: '#9fd6cf' }
  ];
  var NK = {}; NATIONS.forEach(function (n, i) { n.i = i; NK[n.key] = n; });
  // 같은 대륙에 있는 나라끼리는 땅으로 이어 준다
  var CONTINENTS = [['Mechania', 'Grainia'], ['Mechania', 'Ferria'], ['Grainia', 'Ferria'], ['Oilia', 'Tropia'], ['Technia', 'Oilia']];
  var BIOMES = ['temperate', 'plains', 'boreal', 'desert', 'tropical', 'outback', 'island'];
  var BIO = {
    temperate: { c: [0.45, 0.62, 0.32], forest: 0.55 },
    plains:    { c: [0.74, 0.69, 0.38], forest: 0.08 },
    boreal:    { c: [0.38, 0.48, 0.35], forest: 0.6 },
    desert:    { c: [0.88, 0.77, 0.53], forest: 0.0 },
    tropical:  { c: [0.24, 0.50, 0.23], forest: 0.85 },
    outback:   { c: [0.80, 0.47, 0.28], forest: 0.05 },
    island:    { c: [0.42, 0.63, 0.34], forest: 0.5 }
  };
  NATIONS.forEach(function (n) { n.b = BIOMES.indexOf(n.biome); });
  var names = {}; NATIONS.forEach(function (n) { names[n.key] = n.ko; });

  // ───────────────────────── 유틸 ─────────────────────────
  function clamp(x, a, b) { return x < a ? a : x > b ? b : x; }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function sstep(a, b, x) { var t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); }
  function hash2(x, y, s) { var h = (Math.imul(x | 0, 374761393) + Math.imul(y | 0, 668265263) + Math.imul(s | 0, 1442695041)) | 0; h = Math.imul(h ^ (h >>> 13), 1274126177); h ^= h >>> 16; return (h >>> 0) / 4294967296; }
  function vnoise(x, y, s) { var xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi; var u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf); var a = hash2(xi, yi, s), b = hash2(xi + 1, yi, s), c = hash2(xi, yi + 1, s), d = hash2(xi + 1, yi + 1, s); return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v; }
  function fbm3(x, y, s) { s = s || 0; return (vnoise(x, y, s + 3) * 0.5 + vnoise(x * 2.03, y * 2.03, s + 20) * 0.25 + vnoise(x * 4.1, y * 4.1, s + 37) * 0.125) / 0.875; }
  function rng32(seed) { var a = seed >>> 0; return function () { a = (a + 0x6D2B79F5) | 0; var t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
  function mixc(a, b, t) { return [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)]; }
  function hexRGB(h) { var c = new THREE.Color(h); return [c.r, c.g, c.b]; }
  function el(tag, style, html) { var e = document.createElement(tag); if (style) e.style.cssText = style; if (html != null) e.innerHTML = html; return e; }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  // ───────────────────────── 세계 만들기 (항상 같은 모양) ─────────────────────────
  var N = NATIONS.length, FLD = new Float32Array(FW * FH), F = new Float32Array(FW * FH), ID = new Int8Array(FW * FH), HG = new Float32Array(FW * FH), FOR = new Float32Array(FW * FH), CON = new Uint8Array(FW * FH);
  var natData = new Uint8Array(FW * FH * 4), polData = new Uint8Array(FW * FH * 4);
  var cSum = NATIONS.map(function () { return [0, 0, 0]; });
  (function generate() {
    var COS = NATIONS.map(function (n, k) { return Math.cos(k * 2.1 + 0.4); }), SIN = NATIONS.map(function (n, k) { return Math.sin(k * 2.1 + 0.4); });
    var BR = CONTINENTS.map(function (c) { var a = NK[c[0]], b = NK[c[1]]; return [a.x, a.z, b.x, b.z, Math.min(a.r, b.r) * 0.55]; });
    var dn = new Float32Array(N), bAmt = new Float32Array(BIOMES.length), POLC = NATIONS.map(function (n) { return hexRGB(n.color); });
    var SAND = [0.9, 0.84, 0.64], ROCK = [0.55, 0.52, 0.47], SNOW = [0.94, 0.96, 0.98], FORC = [0.18, 0.36, 0.19];
    for (var j = 0; j < FH; j++) {
      var z = -WZ + (j + 0.5) * CELL;
      for (var i = 0; i < FW; i++) {
        var x = -WX + (i + 0.5) * CELL, idx = j * FW + i, o = idx * 4;
        var n1 = fbm3(x * 0.045 + 3, z * 0.045 + 9, 1), n2 = fbm3(x * 0.045 + 21, z * 0.045 + 2, 2);
        var wx = x + (fbm3(x * 0.028 + 40, z * 0.028 + 13, 13) - 0.5) * 22, wz = z + (fbm3(x * 0.028 - 31, z * 0.028 + 60, 14) - 0.5) * 22;
        var best = 1e9, bi = 0, k;
        for (k = 0; k < N; k++) { var dx = wx - NATIONS[k].x, dz = wz - NATIONS[k].z; var d = Math.sqrt(dx * dx + dz * dz) / NATIONS[k].r + ((n1 - 0.5) * COS[k] + (n2 - 0.5) * SIN[k]) * 0.55; dn[k] = d; if (d < best) { best = d; bi = k; } }
        var land = 1 - best;
        for (k = 0; k < BR.length; k++) { var b = BR[k], ex = b[2] - b[0], ez = b[3] - b[1], tt = clamp(((wx - b[0]) * ex + (wz - b[1]) * ez) / (ex * ex + ez * ez), 0.2, 0.8), qx = wx - b[0] - ex * tt, qz = wz - b[1] - ez * tt; land = Math.max(land, 1 - Math.sqrt(qx * qx + qz * qz) / b[4] - 0.25); }
        var isl = (fbm3(x * 0.07 + 100, z * 0.07, 15) - 0.69) * 4 - Math.max(0, best - 1.9) * 3; land = Math.max(land, isl);
        var f = land + (fbm3(x * 0.11, z * 0.11, 3) - 0.5) * 0.5 + (vnoise(x * 0.4 + 7, z * 0.4, 5) - 0.5) * 0.04;
        f -= sstep(WX - 14, WX - 3, Math.abs(x)) * 1.5 + sstep(WZ - 12, WZ - 3, Math.abs(z)) * 1.5;
        F[idx] = f;
        var sw = 0, mnt = 0, fp = 0; for (k = 0; k < BIOMES.length; k++) bAmt[k] = 0;
        for (k = 0; k < N; k++) { var wk = Math.exp(-(dn[k] - best) * 4.5); sw += wk; dn[k] = wk; }
        for (k = 0; k < N; k++) { var w = dn[k] / sw; mnt += w * NATIONS[k].mount; bAmt[NATIONS[k].b] += w; fp += w * BIO[NATIONS[k].biome].forest; }
        var h, c;
        if (f <= 0) {
          ID[idx] = -1; h = Math.max(-0.9, f * 3.2);
          c = mixc([0.82, 0.79, 0.6], [0.1, 0.3, 0.45], sstep(0.0, 0.2, -f));
          polData[o] = 0; polData[o + 1] = 0; polData[o + 2] = 0; polData[o + 3] = 0;
        } else {
          ID[idx] = bi; cSum[bi][0] += x; cSum[bi][1] += z; cSum[bi][2]++;
          var r = fbm3(x * 0.085 + 50, z * 0.085 - 20, 4), ridge = 1 - Math.abs(2 * r - 1); ridge = ridge * ridge * ridge;
          var hills = fbm3(x * 0.25, z * 0.25, 6);
          h = 0.04 + sstep(0, 0.35, f) * 0.2 + mnt * ridge * 2.4 * sstep(0.05, 0.45, f) + (hills - 0.5) * 0.2 * (0.4 + mnt);
          h = Math.min(Math.max(h, Math.min(0.03, f * 3.2)), f * 3.2); // 해안에서 높이가 0부터 이어지게(끊기면 해안선이 톱니가 됨)
          // 자연색
          c = [0, 0, 0]; for (k = 0; k < BIOMES.length; k++) { var bc = BIO[BIOMES[k]].c; c[0] += bc[0] * bAmt[k]; c[1] += bc[1] * bAmt[k]; c[2] += bc[2] * bAmt[k]; }
          var pl = bAmt[1];
          FLD[idx] = sstep(0.3, 0.75, pl) * 0.8;
          if (bAmt[3] > 0.05) { var s = Math.sin(x * 0.9 + z * 0.4 + fbm3(x * 0.2, z * 0.2, 8) * 6); var m = 1 + s * 0.06 * bAmt[3]; c = [c[0] * m, c[1] * m, c[2] * m]; }
          if (bAmt[4] > 0.05) c = mixc(c, [0.14, 0.36, 0.15], bAmt[4] * sstep(0.45, 0.6, fbm3(x * 0.3, z * 0.3, 9)) * 0.6);
          if (bAmt[5] > 0.05) c = mixc(c, [0.6, 0.31, 0.18], bAmt[5] * sstep(0.55, 0.72, vnoise(x * 1.3, z * 1.3, 10)) * 0.6);
          var patch = sstep(0.4, 0.58, fbm3(x * 0.3 + 11, z * 0.3 + 7, 11));
          var prob = fp * lerp(patch, 1, bAmt[4] * 0.6) * sstep(0.03, 0.08, f) * (1 - sstep(0.8, 1.2, h));
          FOR[idx] = prob; CON[idx] = (bAmt[2] > 0.4 || h > 0.55) ? 1 : 0;
          c = mixc(c, FORC, prob * 0.35);
          c = mixc(SAND, c, sstep(0.012, 0.05, f));
          c = mixc(c, ROCK, sstep(0.7, 1.1, h));
          c = mixc(c, SNOW, sstep(1.45, 1.85, h + (n1 - 0.5) * 0.4));
          var bn = 0.92 + 0.16 * vnoise(x * 0.6, z * 0.6, 12); c = [c[0] * bn, c[1] * bn, c[2] * bn];
          var pc = POLC[bi]; polData[o] = pc[0] * 255; polData[o + 1] = pc[1] * 255; polData[o + 2] = pc[2] * 255; polData[o + 3] = (bi + 1) * 20;
        }
        HG[idx] = h;
        natData[o] = clamp(c[0] * 255, 0, 255); natData[o + 1] = clamp(c[1] * 255, 0, 255); natData[o + 2] = clamp(c[2] * 255, 0, 255);
      }
    }
  })();
  function sampleArr(A, x, z) {
    var fx = (x + WX) / CELL - 0.5, fz = (z + WZ) / CELL - 0.5, i = Math.floor(fx), j = Math.floor(fz), tx = fx - i, tz = fz - j;
    i = clamp(i, 0, FW - 2); j = clamp(j, 0, FH - 2);
    var a = A[j * FW + i], b = A[j * FW + i + 1], c = A[(j + 1) * FW + i], d = A[(j + 1) * FW + i + 1];
    return lerp(lerp(a, b, tx), lerp(c, d, tx), tz);
  }
  function cellIdx(x, z) { var i = clamp(Math.floor((x + WX) / CELL), 0, FW - 1), j = clamp(Math.floor((z + WZ) / CELL), 0, FH - 1); return j * FW + i; }
  function landAt(x, z) { return sampleArr(F, x, z); }
  function heightAt(x, z) { return sampleArr(HG, x, z); }
  function nationAt(x, z) { return ID[cellIdx(x, z)]; }
  NATIONS.forEach(function (n, k) { var s = cSum[k]; n.cx = s[2] ? s[0] / s[2] : n.x; n.cz = s[2] ? s[1] / s[2] : n.z; n.cells = s[2]; });

  // 항구 자리: 나라 해안 중 세계 가운데에 가장 가까운 곳(바다가 앞에, 땅이 뒤에 넉넉히 있는 곳)
  NATIONS.forEach(function (n, k) {
    var best = null, bs = -1e9;
    for (var j = 8; j < FH - 8; j += 2) for (var i = 8; i < FW - 8; i += 2) {
      var idx = j * FW + i; if (ID[idx] !== k) continue; var f = F[idx]; if (f < 0.02 || f > 0.08) continue;
      var x = -WX + (i + 0.5) * CELL, z = -WZ + (j + 0.5) * CELL;
      var gx = F[idx + 1] - F[idx - 1], gz = F[idx + FW] - F[idx - FW], gl = Math.hypot(gx, gz); if (gl < 1e-5) continue;
      var sx = -gx / gl, sz = -gz / gl;
      if (landAt(x + sx * 2.2, z + sz * 2.2) > -0.06 || landAt(x + sx * 1.2 - sz * 0.9, z + sz * 1.2 + sx * 0.9) > 0 || landAt(x + sx * 1.2 + sz * 0.9, z + sz * 1.2 - sx * 0.9) > 0) continue;
      if (landAt(x - sx * 2.4, z - sz * 2.4) < 0.1 || nationAt(x - sx * 2.4, z - sz * 2.4) !== k) continue;
      if (landAt(x - sx * 0.6 - sz * 1.0, z - sz * 0.6 + sx * 1.0) < 0.02 || landAt(x - sx * 0.6 + sz * 1.0, z - sz * 0.6 - sx * 1.0) < 0.02) continue;
      var score = -Math.hypot(x, z) - Math.hypot(x - n.x, z - n.z) * 0.6;
      if (score > bs) { bs = score; best = { x: x + sx * 0.25, z: z + sz * 0.25, sx: sx, sz: sz }; }
    }
    if (!best) best = { x: n.x, z: n.z, sx: 0, sz: 1 };
    n.port = best;
    // 항구 주변 평평하게, 숲 치우기
    for (var jj = 0; jj < FH; jj++) {
      var zz = -WZ + (jj + 0.5) * CELL; if (Math.abs(zz - best.z) > 3.2) continue;
      for (var ii = 0; ii < FW; ii++) {
        var xx = -WX + (ii + 0.5) * CELL, d = Math.hypot(xx - best.x, zz - best.z); if (d > 3.2) continue;
        var id2 = jj * FW + ii; if (F[id2] > 0) { var w = 1 - sstep(1.9, 3.1, d); HG[id2] = lerp(HG[id2], GROUND_Y, w); }
        if (d < 2.4) FOR[id2] = 0;
      }
    }
  });

  // ───────────────────────── 도시·마을 (수도 1곳 + 마을 2~3곳, 길, 밭) ─────────────────────────
  var STYLES = {
    temperate: { walls: ['#f3ece0', '#e8dcc6', '#f6f1e7', '#e2d3bd'], roofs: ['#c0583a', '#a8462f', '#5b6f82', '#8a5a44'], house: 'gable', farm: [[0.86, 0.74, 0.36], [0.55, 0.67, 0.3], [0.67, 0.53, 0.34], [0.47, 0.6, 0.28]], farmW: 2.6 },
    plains:    { walls: ['#f4efe4', '#e9dfcb', '#b5523b', '#f4efe4'], roofs: ['#6d4c41', '#8a5a44', '#5d6d7e'], house: 'gable', farm: [[0.86, 0.74, 0.36], [0.55, 0.67, 0.3], [0.67, 0.53, 0.34], [0.93, 0.84, 0.52]], farmW: 3.2 },
    boreal:    { walls: ['#7b5a43', '#8d6e58', '#6b4f3a', '#c9b9a6'], roofs: ['#3e4f45', '#4a4a4a', '#5b6f5f'], house: 'gable', farm: [[0.5, 0.6, 0.35], [0.62, 0.66, 0.4]], farmW: 1.4 },
    desert:    { walls: ['#e8d5ae', '#ddc597', '#f0e2c4', '#d6b98a'], roofs: ['#e8d5ae'], house: 'flat', farm: [[0.42, 0.58, 0.27], [0.52, 0.64, 0.3]], farmW: 1.1 },
    tropical:  { walls: ['#f7c8b4', '#f6e3a1', '#a8e0d2', '#f4f1e8', '#c8e6a6'], roofs: ['#c96a3d', '#b5523b', '#d9a066'], house: 'gable', hut: true, farm: [[0.2, 0.42, 0.18], [0.3, 0.5, 0.22], [0.55, 0.62, 0.3]], farmW: 2.0 },
    outback:   { walls: ['#f1e6d6', '#e2c9a6', '#d8b48c'], roofs: ['#9aa3a8', '#7f8a90', '#b0b8bc'], house: 'gable', farm: null, farmW: 0 },
    island:    { walls: ['#ffffff', '#f4f6f7', '#eaf2f8'], roofs: ['#2e86c1', '#3498db', '#1f618d'], house: 'flat', farm: [[0.5, 0.66, 0.34], [0.62, 0.7, 0.4]], farmW: 1.2 }
  };
  var MODERN = { Technia: 1, Novia: 0.9, Oilia: 0.75, Mechania: 0.6, Grainia: 0.2, Mineria: 0.3, Ferria: 0.15, Tropia: 0.3, Agrea: 0.25 };
  var GLASS = ['#7fb3d5', '#a9cce3', '#85929e', '#d6eaf8', '#5d6d7e', '#aab7b8'];
  var BLD = { wall: [], roof: [], dome: [], cone: [], cyl: [] }, ROADS = [], SETTLE = [];
  function farFromSettle(x, z, gap) { for (var k = 0; k < SETTLE.length; k++) { var s = SETTLE[k]; if (Math.hypot(x - s.x, z - s.z) < s.R + gap) return false; } return true; }
  function siteOK(x, z, R) {
    if (landAt(x, z) < 0.1) return false; var h0 = heightAt(x, z); if (h0 > 0.5) return false;
    for (var a = 0; a < 8; a++) { var px = x + Math.cos(a * 0.785) * R, pz = z + Math.sin(a * 0.785) * R; if (landAt(px, pz) < 0.03 || Math.abs(heightAt(px, pz) - h0) > 0.4) return false; }
    return true;
  }
  NATIONS.forEach(function (n) {
    var r = rng32(n.i * 31337 + 3), best = null, bs = 1e9, R = n.cells > 9000 ? 2.4 : 1.8, t, x, z;
    for (t = 0; t < 3000; t++) {
      x = n.cx + (r() * 2 - 1) * n.r * 0.75; z = n.cz + (r() * 2 - 1) * n.r * 0.75;
      if (nationAt(x, z) !== n.i || !siteOK(x, z, R)) continue;
      var dp = Math.hypot(x - n.port.x, z - n.port.z); if (dp < R + 4.5) continue;
      var sc = Math.hypot(x - n.cx, z - n.cz) + heightAt(x, z) * 6 + Math.max(0, dp - 14) * 0.3;
      if (sc < bs) { bs = sc; best = [x, z]; }
    }
    if (best) SETTLE.push({ n: n, x: best[0], z: best[1], R: R, capital: true });
    var want = n.cells > 9000 ? 3 : 2, made = 0;
    for (t = 0; t < 6000 && made < want; t++) {
      x = n.cx + (r() * 2 - 1) * n.r * 1.1; z = n.cz + (r() * 2 - 1) * n.r * 1.1;
      var tr = 0.85 + r() * 0.4;
      if (nationAt(x, z) !== n.i || !siteOK(x, z, tr) || !farFromSettle(x, z, 5.5) || Math.hypot(x - n.port.x, z - n.port.z) < 5) continue;
      SETTLE.push({ n: n, x: x, z: z, R: tr, capital: false }); made++;
    }
  });
  // 길: 수도↔항구, 마을↔가장 가까운 수도·항구·마을(같은 나라)
  function clearForest(x, z, rad) { var c = Math.ceil(rad / CELL); var i0 = Math.floor((x + WX) / CELL), j0 = Math.floor((z + WZ) / CELL); for (var dj = -c; dj <= c; dj++) for (var di = -c; di <= c; di++) { var i = i0 + di, j = j0 + dj; if (i >= 0 && j >= 0 && i < FW && j < FH) FOR[j * FW + i] = 0; } }
  function makeRoad(ax, az, bx, bz, w, seed) {
    var L = Math.hypot(bx - ax, bz - az); if (L < 0.3) return false;
    var cnt = Math.max(2, Math.ceil(L / 0.3)), px = -(bz - az) / L, pz = (bx - ax) / L, pts = [];
    for (var i = 0; i <= cnt; i++) {
      var t = i / cnt, wob = Math.sin(t * Math.PI) * (vnoise(t * 3, seed, 21) - 0.5) * Math.min(L * 0.3, 4);
      var x = ax + (bx - ax) * t + px * wob, z = az + (bz - az) * t + pz * wob;
      if (landAt(x, z) < 0.015) return false;
      pts.push([x, z]);
    }
    pts.forEach(function (p) { clearForest(p[0], p[1], 0.3); });
    ROADS.push({ pts: pts, w: w }); return true;
  }
  NATIONS.forEach(function (n) {
    var mine = SETTLE.filter(function (s) { return s.n === n; }), cap = mine.filter(function (s) { return s.capital; })[0], pq = { x: n.port.x - n.port.sx * 0.75, z: n.port.z - n.port.sz * 0.75 };
    var nodes = [pq]; if (cap) { makeRoad(cap.x, cap.z, pq.x, pq.z, 0.075, n.i * 10); nodes.push(cap); }
    mine.forEach(function (s, k) {
      if (s.capital) return;
      var order = nodes.slice().sort(function (a, b) { return Math.hypot(a.x - s.x, a.z - s.z) - Math.hypot(b.x - s.x, b.z - s.z); });
      for (var q = 0; q < order.length; q++) if (makeRoad(s.x, s.z, order[q].x, order[q].z, 0.06, n.i * 10 + k + 1)) break;
      nodes.push(s);
    });
  });
  // 도시 바닥·밭을 자연색 텍스처에 칠하고 숲을 치운다
  SETTLE.forEach(function (s, si) {
    var st = STYLES[s.n.biome], farm = st.farm ? s.R + st.farmW * (s.capital ? 1.2 : 0.8) : s.R, ang = si * 0.7, ca = Math.cos(ang), sa = Math.sin(ang);
    var c = Math.ceil(farm / CELL), i0 = Math.floor((s.x + WX) / CELL), j0 = Math.floor((s.z + WZ) / CELL);
    for (var dj = -c; dj <= c; dj++) for (var di = -c; di <= c; di++) {
      var i = i0 + di, j = j0 + dj; if (i < 0 || j < 0 || i >= FW || j >= FH) continue;
      var idx = j * FW + i; if (F[idx] <= 0.02) continue;
      var dx = di * CELL, dz = dj * CELL, d = Math.hypot(dx, dz) + (vnoise(i * 0.3, j * 0.3, 30 + si) - 0.5) * 0.8; if (d > farm) continue;
      var o = idx * 4, col, w;
      if (d < s.R * 0.95) { col = [0.64, 0.61, 0.55]; w = 0.55; FOR[idx] = 0; }
      else {
        if (!st.farm) continue; FLD[idx] = Math.max(FLD[idx], 0.85 * (1 - sstep(farm - 0.9, farm, d))); FOR[idx] *= 0.15; continue;
      }
      natData[o] = lerp(natData[o], col[0] * 255, w); natData[o + 1] = lerp(natData[o + 1], col[1] * 255, w); natData[o + 2] = lerp(natData[o + 2], col[2] * 255, w);
    }
  });
  // 건물 목록 (x, y, z, 너비, 높이, 깊이, 회전, r, g, b)
  function pick(a, r) { return a[Math.floor(r() * a.length)]; }
  function addB(type, x, y, z, sx, sy, sz, ry, col) { var c = Array.isArray(col) ? col : hexRGB(col); BLD[type].push(x, y, z, sx, sy, sz, ry, c[0], c[1], c[2]); }
  function house(st, x, z, ry, r, capital) {
    var y = heightAt(x, z) - 0.03, w = 0.07 + r() * 0.04, d = 0.06 + r() * 0.035, h = 0.05 + r() * 0.04 + 0.03;
    if (st.hut && !capital && r() < 0.75) { addB('cyl', x, y, z, w * 0.5, h, w * 0.5, 0, pick(st.walls, r)); addB('cone', x, y + h, z, w * 0.72, h * 0.9, w * 0.72, 0, [0.72, 0.6, 0.38]); return; }
    addB('wall', x, y, z, w, h, d, ry, pick(st.walls, r));
    if (st.house === 'gable') addB('roof', x, y + h, z, w * 1.1, h * 0.5, d * 1.08, ry, pick(st.roofs, r));
    else if (r() < 0.15) addB('dome', x, y + h, z, w * 0.3, w * 0.3, w * 0.3, 0, [0.96, 0.95, 0.92]);
  }
  SETTLE.forEach(function (s, si) {
    var r = rng32(si * 7907 + 11), st = STYLES[s.n.biome], mod = MODERN[s.n.key] || 0.2, h0 = heightAt(s.x, s.z), ang = r() * Math.PI, ca = Math.cos(ang), sa = Math.sin(ang), nc = hexRGB(s.n.color);
    s.ang = ang;
    if (s.capital) {
      var P = 0.15, nn = Math.ceil(s.R / P);
      for (var i = -nn; i <= nn; i++) for (var j = -nn; j <= nn; j++) {
        if (i % 5 === 0 || j % 5 === 0) continue;
        var lx = i * P + (r() - 0.5) * 0.03, lz = j * P + (r() - 0.5) * 0.03, d = Math.hypot(lx, lz) / s.R;
        if (d > 1 || d < 0.13 || r() > 1 - d * d * 0.75) continue;
        var x = s.x + lx * ca - lz * sa, z = s.z + lx * sa + lz * ca;
        if (landAt(x, z) < 0.03 || Math.abs(heightAt(x, z) - h0) > 0.4) continue;
        var y = heightAt(x, z) - 0.03;
        if (d < 0.45 && r() < mod * (1 - d * 1.6)) { var tw = 0.08 + r() * 0.05, th = (0.18 + r() * 0.45) * mod * (1 - d) + 0.14; addB('wall', x, y, z, tw, th, tw, ang, pick(GLASS, r)); addB('wall', x, y + th, z, tw * 1.05, 0.014, tw * 1.05, ang, [0.92, 0.94, 0.96]); }
        else if (d < 0.6 && r() < 0.4) { addB('wall', x, y, z, 0.1 + r() * 0.04, 0.12 + r() * 0.06, 0.09 + r() * 0.03, ang, pick(st.walls, r)); }
        else house(st, x, z, ang + (r() < 0.5 ? 0 : Math.PI / 2), r, true);
      }
      // 시청(지붕이 나라 색) + 깃발
      addB('wall', s.x, h0 - 0.03, s.z, 0.26, 0.15, 0.2, ang, [0.96, 0.94, 0.88]); addB('dome', s.x, h0 + 0.12, s.z, 0.08, 0.08, 0.08, 0, nc);
      var fx = s.x + 0.2 * ca, fz = s.z + 0.2 * sa; addB('cyl', fx, h0, fz, 0.005, 0.32, 0.005, 0, [0.35, 0.35, 0.35]); addB('wall', fx + 0.035, h0 + 0.26, fz, 0.07, 0.045, 0.005, 0, nc);
      ROADS.push({ pts: [[s.x - s.R * ca, s.z - s.R * sa], [s.x + s.R * ca, s.z + s.R * sa]], w: 0.1 }); ROADS.push({ pts: [[s.x + s.R * sa, s.z - s.R * ca], [s.x - s.R * sa, s.z + s.R * ca]], w: 0.1 });
      ROADS.push({ disc: [s.x, s.z, 0.34] });
    } else {
      var cnt = Math.round(22 + s.R * 38);
      for (var k = 0; k < cnt * 3 && cnt > 0; k++) {
        var onStreet = r() < 0.55, rad = s.R * Math.sqrt(r()), a2 = r() * Math.PI * 2, ox, oz;
        if (onStreet) { var along = (r() * 2 - 1) * s.R, side = (r() < 0.5 ? -1 : 1) * (0.09 + r() * 0.05); ox = along * ca - side * sa; oz = along * sa + side * ca; }
        else { ox = Math.cos(a2) * rad; oz = Math.sin(a2) * rad; if (Math.hypot(ox, oz) < 0.12) continue; }
        var x2 = s.x + ox, z2 = s.z + oz; if (landAt(x2, z2) < 0.03 || Math.abs(heightAt(x2, z2) - h0) > 0.35) continue;
        house(st, x2, z2, onStreet ? ang : r() * Math.PI, r, false); cnt--;
      }
      addB('wall', s.x, h0 - 0.03, s.z, 0.12, 0.1, 0.1, ang, [0.95, 0.93, 0.88]); addB('roof', s.x, h0 + 0.07, s.z, 0.13, 0.06, 0.11, ang, nc);
      ROADS.push({ pts: [[s.x - s.R * ca, s.z - s.R * sa], [s.x + s.R * ca, s.z + s.R * sa]], w: 0.07 });
    }
  });

  // ───────────────────────── 렌더러·장면 ─────────────────────────
  if (window.getComputedStyle(container).position === 'static') container.style.position = 'relative';
  container.style.overflow = 'hidden';
  var renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: !!opts.preserve });
  var isTouch = ('ontouchstart' in window) || navigator.maxTouchPoints > 0;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, isTouch ? 1.5 : 2));
  renderer.setSize(container.clientWidth || 800, container.clientHeight || 600);
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  var canvas = renderer.domElement;
  canvas.style.cssText = 'display:block;width:100%;height:100%;touch-action:none;outline:none;';
  container.appendChild(canvas);
  var scene = new THREE.Scene();
  var SKY = new THREE.Color('#cfe0ea');
  scene.background = SKY.clone(); scene.fog = new THREE.Fog(SKY.getHex(), 100, 400);
  var camera = new THREE.PerspectiveCamera(40, (container.clientWidth || 800) / (container.clientHeight || 600), 0.05, 3000);
  scene.add(new THREE.HemisphereLight(0xeaf3ff, 0x5e6b4f, 0.58));
  var sun = new THREE.DirectionalLight(0xfff1dc, 0.62);
  sun.castShadow = true; sun.shadow.mapSize.set(2048, 2048); sun.shadow.bias = -0.0004; sun.shadow.normalBias = 0.01;
  scene.add(sun); scene.add(sun.target);
  var SUN_DIR = new THREE.Vector3(-0.55, 1.0, 0.55).normalize();

  // ───────────────────────── 지형 메시 ─────────────────────────
  for (var fi = 0; fi < FW * FH; fi++) natData[fi * 4 + 3] = F[fi] > 0 ? clamp(FLD[fi] * 255, 0, 255) : 0;
  var polCol = new Uint8Array(polData), seen = new Uint8Array(FW * FH);
  for (var pi = 0; pi < FW * FH; pi++) seen[pi] = polData[pi * 4 + 3] > 0 ? 1 : 0;
  for (var it = 0; it < 10; it++) {
    var nxt = seen.slice();
    for (var pj = 1; pj < FH - 1; pj++) for (var pk = 1; pk < FW - 1; pk++) {
      var q0 = pj * FW + pk; if (seen[q0]) continue;
      var nb = seen[q0 - 1] ? q0 - 1 : seen[q0 + 1] ? q0 + 1 : seen[q0 - FW] ? q0 - FW : seen[q0 + FW] ? q0 + FW : -1;
      if (nb < 0) continue; polCol[q0 * 4] = polCol[nb * 4]; polCol[q0 * 4 + 1] = polCol[nb * 4 + 1]; polCol[q0 * 4 + 2] = polCol[nb * 4 + 2]; nxt[q0] = 1;
    }
    seen = nxt;
  }
  function dataTex(data, linear) { var t = new THREE.DataTexture(data, FW, FH, THREE.RGBAFormat); t.magFilter = t.minFilter = linear ? THREE.LinearFilter : THREE.NearestFilter; t.generateMipmaps = false; t.needsUpdate = true; return t; }
  var natTex = dataTex(natData, true), polTex = dataTex(polData, false), polColTex = dataTex(polCol, true);
  var terrU = { uMix: { value: 1 }, uSel: { value: -1 }, uMe: { value: -1 }, uDetail: { value: 0 }, uBorder: { value: 1 }, uPol: { value: polTex }, uPolC: { value: polColTex }, uTexel: { value: new THREE.Vector2(1 / FW, 1 / FH) } };
  var terrGeo = (function () {
    var step = 2, VW = FW / step + 1, VH = FH / step + 1, pos = new Float32Array(VW * VH * 3), uv = new Float32Array(VW * VH * 2);
    for (var j = 0; j < VH; j++) for (var i = 0; i < VW; i++) {
      var x = -WX + i * CELL * step, z = -WZ + j * CELL * step, k = j * VW + i;
      pos[k * 3] = x; pos[k * 3 + 1] = heightAt(x, z); pos[k * 3 + 2] = z; uv[k * 2] = (x + WX) / (2 * WX); uv[k * 2 + 1] = (z + WZ) / (2 * WZ);
    }
    var idx = new Uint32Array((VW - 1) * (VH - 1) * 6), p = 0;
    for (j = 0; j < VH - 1; j++) for (i = 0; i < VW - 1; i++) { var a = j * VW + i, b = a + 1, c = a + VW, d = c + 1; idx[p++] = a; idx[p++] = c; idx[p++] = b; idx[p++] = b; idx[p++] = c; idx[p++] = d; }
    var g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setAttribute('uv', new THREE.BufferAttribute(uv, 2)); g.setIndex(new THREE.BufferAttribute(idx, 1)); g.computeVertexNormals(); g.computeBoundingSphere(); return g;
  })();
  var terrMat = new THREE.MeshLambertMaterial({ map: natTex });
  terrMat.onBeforeCompile = function (sh) {
    for (var k in terrU) sh.uniforms[k] = terrU[k];
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying vec2 vXZ;\nvarying float vY;').replace('#include <begin_vertex>', '#include <begin_vertex>\nvXZ = position.xz; vY = position.y;');
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', [
      '#include <common>', 'uniform float uMix; uniform float uSel; uniform float uMe; uniform float uDetail; uniform float uBorder;', 'uniform sampler2D uPol; uniform sampler2D uPolC; uniform vec2 uTexel;', 'varying vec2 vXZ;', 'varying float vY;',
      'float h21(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7)))*43758.5453); }',
      'float vn2(vec2 p){ vec2 i=floor(p); vec2 f=fract(p); f=f*f*(3.0-2.0*f); return mix(mix(h21(i),h21(i+vec2(1.0,0.0)),f.x), mix(h21(i+vec2(0.0,1.0)),h21(i+vec2(1.0,1.0)),f.x), f.y); }'].join('\n'))
      .replace('#include <map_fragment>', [
        '#ifdef USE_MAP', '  vec4 texelColor = texture2D( map, vUv );', '  texelColor = mapTexelToLinear( texelColor );', '  diffuseColor.rgb *= texelColor.rgb;', '  float fa = texelColor.a;', '#else', '  float fa = 0.0;', '#endif',
        '  float dn = vn2(vXZ*14.0)*0.55 + vn2(vXZ*47.0)*0.45;',
        '  vec2 fq0 = vec2(vXZ.x * 0.8 + vXZ.y * 0.35, vXZ.y * 0.8 - vXZ.x * 0.35) / vec2(0.62, 0.46); vec2 fcell = floor(fq0); vec2 fq = fract(fq0); float fh = h21(fcell + 17.0);',
        '  vec3 fcol = fh < 0.38 ? vec3(0.88, 0.75, 0.36) : fh < 0.68 ? vec3(0.55, 0.67, 0.3) : fh < 0.86 ? vec3(0.67, 0.53, 0.34) : vec3(0.93, 0.84, 0.52);',
        '  fcol = mix(fcol, diffuseColor.rgb, 0.3); float fedge = min(min(fq.x, 1.0 - fq.x), min(fq.y, 1.0 - fq.y)); fcol *= mix(0.8, 1.0, smoothstep(0.0, 0.05, fedge)) * (0.95 + 0.05 * sin(fq0.x * 60.0));',
        '  diffuseColor.rgb = mix(diffuseColor.rgb, fcol, fa * step(0.2, h21(fcell + 3.0)));',
        '  diffuseColor.rgb *= mix(1.0, 0.82 + 0.34*dn, uDetail);',
        '  float a0 = texture2D(uPol, vUv).a;',
        '  float land = smoothstep(-0.004, 0.02, vY);',
        '  vec3 pcol = texture2D(uPolC, vUv).rgb;',
        '  vec2 hx = vec2(uTexel.x * 0.6, 0.0); vec2 hy = vec2(0.0, uTexel.y * 0.6);',
        '  float g = length(texture2D(uPolC, vUv + hx).rgb - texture2D(uPolC, vUv - hx).rgb) + length(texture2D(uPolC, vUv + hy).rgb - texture2D(uPolC, vUv - hy).rgb);',
        '  float bd = smoothstep(0.05, 0.2, g) * land;',
        '  float coast = 0.0;',
        '#if __VERSION__ >= 300',
        '  coast = (1.0 - smoothstep(0.0, fwidth(vY) * 1.6 + 0.0001, vY)) * step(0.0, vY);',
        '#endif',
        '  float nid = floor(a0 * 255.0 / 20.0 + 0.5) - 1.0;',
        '  diffuseColor.rgb = mix(diffuseColor.rgb, pcol, uMix * land);',
        '  if (land > 0.5 && a0 > 0.02 && abs(nid - uSel) < 0.5) diffuseColor.rgb = mix(diffuseColor.rgb, vec3(1.0, 0.94, 0.6), 0.45);',
        '  float me = (a0 > 0.02 && abs(nid - uMe) < 0.5) ? 1.0 : 0.0;',
        '  diffuseColor.rgb = mix(diffuseColor.rgb, mix(vec3(0.17, 0.21, 0.26), vec3(0.12, 0.35, 0.85), me), clamp(bd * (0.55 + 0.45 * uMix) + coast * uMix * 0.85, 0.0, 1.0) * uBorder);'
      ].join('\n'));
  };
  var terrain = new THREE.Mesh(terrGeo, terrMat); terrain.receiveShadow = true; scene.add(terrain);

  // ───────────────────────── 바다 ─────────────────────────
  var waveTex = (function () {
    var S = 256, P = 8, cv = document.createElement('canvas'); cv.width = cv.height = S;
    var cx = cv.getContext('2d'), id = cx.createImageData(S, S), H = new Float32Array(S * S);
    function tn(x, y, per, s) { var xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi, u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf); function hh(a, b) { return hash2(((a % per) + per) % per, ((b % per) + per) % per, s); } var A = hh(xi, yi), B = hh(xi + 1, yi), C = hh(xi, yi + 1), D = hh(xi + 1, yi + 1); return A + (B - A) * u + (C - A) * v + (A - B - C + D) * u * v; }
    for (var y = 0; y < S; y++) for (var x = 0; x < S; x++) H[y * S + x] = tn(x / S * P, y / S * P, P, 1) * 0.6 + tn(x / S * P * 2, y / S * P * 2, P * 2, 2) * 0.4;
    for (y = 0; y < S; y++) for (x = 0; x < S; x++) {
      var dx = H[y * S + (x + 1) % S] - H[y * S + (x - 1 + S) % S], dy = H[((y + 1) % S) * S + x] - H[((y - 1 + S) % S) * S + x];
      var nx = -dx * 6, ny = -dy * 6, l = Math.sqrt(nx * nx + ny * ny + 1), o = (y * S + x) * 4;
      id.data[o] = (nx / l * 0.5 + 0.5) * 255; id.data[o + 1] = (ny / l * 0.5 + 0.5) * 255; id.data[o + 2] = (1 / l * 0.5 + 0.5) * 255; id.data[o + 3] = 255;
    }
    cx.putImageData(id, 0, 0);
    var t = new THREE.CanvasTexture(cv); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(300, 200); return t;
  })();
  var OCEAN_POL = new THREE.Color('#b9d8ea'), OCEAN_NAT = new THREE.Color('#2f7aa6');
  var oceanMat = new THREE.MeshPhongMaterial({ color: OCEAN_POL.clone(), specular: new THREE.Color(0x000000), shininess: 60, normalMap: waveTex, normalScale: new THREE.Vector2(0, 0), transparent: true, opacity: 0.95, depthWrite: false });
  var ocean = new THREE.Mesh(new THREE.PlaneGeometry(600, 400), oceanMat); ocean.rotation.x = -Math.PI / 2; ocean.receiveShadow = true; ocean.renderOrder = 1; scene.add(ocean);
  var deep = new THREE.Mesh(new THREE.PlaneGeometry(600, 400), new THREE.MeshBasicMaterial({ color: 0x1b4a6b })); deep.rotation.x = -Math.PI / 2; deep.position.y = -0.95; scene.add(deep);

  // ───────────────────────── 지오메트리 합치기 도우미 ─────────────────────────
  var _e = new THREE.Euler(), _q = new THREE.Quaternion();
  function mergeParts(parts) {
    var gs = [], total = 0;
    parts.forEach(function (p) { var g = p.g.index ? p.g.toNonIndexed() : p.g.clone(); g.applyMatrix4(p.m); gs.push({ g: g, c: p.c }); total += g.attributes.position.count; });
    var pos = new Float32Array(total * 3), nor = new Float32Array(total * 3), col = new Float32Array(total * 3), off = 0;
    gs.forEach(function (it) { var n = it.g.attributes.position.count; pos.set(it.g.attributes.position.array, off * 3); nor.set(it.g.attributes.normal.array, off * 3); for (var k = 0; k < n; k++) { col[(off + k) * 3] = it.c[0]; col[(off + k) * 3 + 1] = it.c[1]; col[(off + k) * 3 + 2] = it.c[2]; } off += n; it.g.dispose(); });
    var G = new THREE.BufferGeometry(); G.setAttribute('position', new THREE.BufferAttribute(pos, 3)); G.setAttribute('normal', new THREE.BufferAttribute(nor, 3)); G.setAttribute('color', new THREE.BufferAttribute(col, 3)); G.computeBoundingSphere(); return G;
  }
  function M(x, y, z, ry, rz) { _e.set(0, ry || 0, rz || 0); _q.setFromEuler(_e); return new THREE.Matrix4().compose(new THREE.Vector3(x, y, z), _q.clone(), new THREE.Vector3(1, 1, 1)); }
  function C(h) { return Array.isArray(h) ? h : hexRGB(h); }
  function Box(P, w, h, d, x, y, z, col, ry, rz) { var g = new THREE.BoxGeometry(w, h, d); g.translate(0, h / 2, 0); P.push({ g: g, m: M(x, y, z, ry, rz), c: C(col) }); }
  function Cyl(P, r1, r2, h, x, y, z, col, seg, rz) { var g = new THREE.CylinderGeometry(r1, r2, h, seg || 12); g.translate(0, h / 2, 0); P.push({ g: g, m: M(x, y, z, 0, rz), c: C(col) }); }
  function Cone(P, r, h, x, y, z, col, seg) { var g = new THREE.ConeGeometry(r, h, seg || 8); g.translate(0, h / 2, 0); P.push({ g: g, m: M(x, y, z), c: C(col) }); }
  function Roof(P, w, h, len, x, y, z, col, ry) { var sh = new THREE.Shape([new THREE.Vector2(-w / 2, 0), new THREE.Vector2(w / 2, 0), new THREE.Vector2(0, h)]); var g = new THREE.ExtrudeGeometry(sh, { depth: len, bevelEnabled: false }); g.translate(0, 0, -len / 2); P.push({ g: g, m: M(x, y, z, ry), c: C(col) }); }
  function Blob(P, r, sy, x, y, z, col) { var g = new THREE.IcosahedronGeometry(r, 0); g.scale(1, sy, 1); P.push({ g: g, m: M(x, y, z), c: C(col) }); }

  // ───────────────────────── 항구 ─────────────────────────
  var lambertVC = new THREE.MeshLambertMaterial({ vertexColors: true });
  var CONT_COLS = ['#c0392b', '#2e86de', '#27ae60', '#f39c12', '#8e44ad', '#16a085', '#d35400', '#7f8c8d', '#e84393'];
  var FRUIT_COLS = ['#f4f6f6', '#f4f6f6', '#ecf0f1', '#f4d03f', '#58a55c', '#f4f6f6'];
  function makeShip(type, r) {
    var P = [], L = type === 'oil' ? 0.36 : 0.3, W = 0.065, Hh = 0.03;
    var sh = new THREE.Shape([new THREE.Vector2(-L / 2, -W / 2), new THREE.Vector2(L * 0.3, -W / 2), new THREE.Vector2(L / 2, 0), new THREE.Vector2(L * 0.3, W / 2), new THREE.Vector2(-L / 2, W / 2)]);
    var hg = new THREE.ExtrudeGeometry(sh, { depth: Hh, bevelEnabled: false }); hg.rotateX(-Math.PI / 2); hg.translate(0, -0.006, 0);
    P.push({ g: hg, m: new THREE.Matrix4(), c: C(type === 'oil' ? '#7a2f2f' : type === 'fruit' ? '#f2f3f4' : type === 'container' ? '#253b55' : '#3d4b3f') });
    Box(P, 0.05, 0.045, W * 0.8, -L / 2 + 0.04, Hh - 0.006, 0, '#f4f4f0');
    Box(P, 0.012, 0.025, 0.012, -L / 2 + 0.03, Hh + 0.039, 0, '#222');
    var cols = type === 'fruit' ? FRUIT_COLS : CONT_COLS;
    if (type === 'container' || type === 'fruit') { for (var i = 0; i < 5; i++) for (var j = 0; j < 2; j++) { var hgt = 1 + Math.floor(r() * 3); for (var k = 0; k < hgt; k++) Box(P, 0.036, 0.014, 0.026, -L / 2 + 0.09 + i * 0.038, Hh - 0.006 + k * 0.014, (j - 0.5) * 0.028, cols[Math.floor(r() * cols.length)]); } }
    else if (type === 'oil') { Box(P, L * 0.55, 0.006, 0.01, 0.03, Hh - 0.006, 0, '#c9b26a'); for (i = 0; i < 4; i++) Cyl(P, 0.012, 0.012, 0.01, -0.04 + i * 0.05, Hh - 0.006, 0, '#d8d8d8', 8); }
    else { for (i = 0; i < 5; i++) Box(P, 0.03, 0.01, 0.045, -L / 2 + 0.1 + i * 0.038, Hh - 0.006, 0, type === 'ore' ? '#8a3d22' : '#c8a64a'); }
    var mesh = new THREE.Mesh(mergeParts(P), lambertVC); mesh.castShadow = true; mesh.receiveShadow = true; return mesh;
  }
  function makePort(n) {
    var r = rng32(n.i * 7919 + 17), g = new THREE.Group(), P = [], pt = n.port, t = GOODS[n.good].port;
    var ry = Math.atan2(pt.sx, pt.sz);
    g.position.set(pt.x, 0, pt.z); g.rotation.y = ry;
    Box(P, 1.7, QUAY_TOP + 0.4, 1.05, 0, -0.4, 0, '#c7c1b3');
    Box(P, 1.7, 0.004, 0.03, 0, QUAY_TOP, 0.5, '#e9d36b');
    var i, j, k, h;
    if (t === 'container' || t === 'fruit') {
      var cranes = t === 'fruit' ? [-0.3, 0.1] : [-0.55, -0.18, 0.19], cols = t === 'fruit' ? FRUIT_COLS : CONT_COLS, crc = t === 'fruit' ? '#2e86ab' : '#e07a3f';
      cranes.forEach(function (x) {
        [[-0.05, 0.33], [0.05, 0.33], [-0.05, 0.47], [0.05, 0.47]].forEach(function (lg) { Box(P, 0.014, 0.2, 0.014, x + lg[0], QUAY_TOP, lg[1], crc); });
        Box(P, 0.016, 0.022, 0.5, x - 0.045, QUAY_TOP + 0.2, 0.56, crc); Box(P, 0.016, 0.022, 0.5, x + 0.045, QUAY_TOP + 0.2, 0.56, crc); Box(P, 0.11, 0.012, 0.014, x, QUAY_TOP + 0.2, 0.8, crc);
        Box(P, 0.07, 0.04, 0.07, x, QUAY_TOP + 0.22, 0.4, '#f0f0ea');
      });
      var cols2 = t === 'fruit' ? 8 : 12;
      for (i = 0; i < cols2; i++) for (j = 0; j < 7; j++) { if (r() < 0.15) continue; h = 1 + Math.floor(r() * (t === 'fruit' ? 2 : 4)); for (k = 0; k < h; k++) Box(P, 0.075, 0.026, 0.03, -0.72 + i * 0.088, QUAY_TOP + k * 0.026, -0.4 + j * 0.075, cols[Math.floor(r() * cols.length)]); }
      if (t === 'fruit') { Box(P, 0.3, 0.08, 0.2, -0.0 + 0.32, QUAY_TOP, 0.05, '#f2f3f4'); Roof(P, 0.3, 0.04, 0.2, 0.32, QUAY_TOP + 0.08, 0.05, '#58a55c'); }
      Box(P, 0.24, 0.07, 0.16, 0.62, QUAY_TOP, 0.12, '#e9e3d4'); Roof(P, 0.24, 0.04, 0.16, 0.62, QUAY_TOP + 0.07, 0.12, '#5b6f82');
    } else if (t === 'oil') {
      for (i = 0; i < 3; i++) for (j = 0; j < 3; j++) { var x0 = -0.66 + i * 0.22, z0 = -0.36 + j * 0.2; Cyl(P, 0.08, 0.08, 0.07, x0, QUAY_TOP, z0, '#dfe3e6', 18); Cyl(P, 0.07, 0.08, 0.008, x0, QUAY_TOP + 0.07, z0, '#c3c8cc', 18); }
      [[0.05, -0.32, 0.28], [0.14, -0.25, 0.22], [0.08, -0.12, 0.34]].forEach(function (tw) { Cyl(P, 0.022, 0.026, tw[2], tw[0], QUAY_TOP, tw[1], '#a9adb1', 10); Cyl(P, 0.028, 0.028, 0.008, tw[0], QUAY_TOP + tw[2] * 0.6, tw[1], '#e0533d', 10); });
      Box(P, 0.5, 0.02, 0.025, -0.25, QUAY_TOP + 0.05, 0.18, '#8c8f93');
      Cyl(P, 0.008, 0.012, 0.36, 0.3, QUAY_TOP, 0.2, '#8c8f93', 8);
      Box(P, 0.05, 0.03, 0.45, 0.25, 0.0, 0.72, '#9a958a'); Box(P, 0.12, 0.03, 0.06, 0.25, 0.0, 0.92, '#9a958a');
      Cyl(P, 0.006, 0.006, 0.08, 0.22, 0.03, 0.92, '#e0533d', 6); Cyl(P, 0.006, 0.006, 0.08, 0.28, 0.03, 0.92, '#e0533d', 6);
    } else if (t === 'ore') {
      for (i = 0; i < 4; i++) for (j = 0; j < 2; j++) Cone(P, 0.11 + r() * 0.02, 0.07 + r() * 0.03, -0.66 + i * 0.22, QUAY_TOP, -0.3 + j * 0.27, j ? '#9b4a2c' : '#7d3a22', 9);
      for (i = 0; i < 6; i++) Box(P, 0.012, 0.08, 0.012, -0.65 + i * 0.15, QUAY_TOP, 0.25, '#6d6d6d');
      Box(P, 0.95, 0.02, 0.03, -0.25, QUAY_TOP + 0.08, 0.25, '#d6a13a'); Box(P, 0.03, 0.02, 0.4, 0.2, QUAY_TOP + 0.1, 0.45, '#d6a13a');
      Box(P, 0.08, 0.12, 0.08, 0.2, QUAY_TOP, 0.3, '#5c6670');
      Box(P, 1.5, 0.008, 0.05, 0, QUAY_TOP, -0.47, '#4a4a4a'); for (i = 0; i < 8; i++) Box(P, 0.08, 0.03, 0.04, -0.6 + i * 0.1, QUAY_TOP + 0.008, -0.47, '#6b4a3a');
    } else if (t === 'grain') {
      for (i = 0; i < 5; i++) for (j = 0; j < 2; j++) { Cyl(P, 0.045, 0.045, 0.22, -0.6 + i * 0.1, QUAY_TOP, -0.32 + j * 0.1, '#efe6d0', 14); Cone(P, 0.045, 0.025, -0.6 + i * 0.1, QUAY_TOP + 0.22, -0.32 + j * 0.1, '#b9b2a2', 14); }
      Box(P, 0.1, 0.32, 0.1, -0.05, QUAY_TOP, -0.27, '#d8cdb3'); Box(P, 0.03, 0.03, 0.62, -0.05, QUAY_TOP + 0.2, 0.15, '#b7ab93');
      for (i = 0; i < 3; i++) Box(P, 0.012, 0.2, 0.012, -0.05, QUAY_TOP, -0.05 + i * 0.2, '#888');
      Box(P, 0.3, 0.06, 0.16, -0.45, QUAY_TOP, 0.18, '#d9d2c2'); Roof(P, 0.3, 0.05, 0.16, -0.45, QUAY_TOP + 0.06, 0.18, '#8a5a44');
    }
    // 항구 마을
    var ROOF = ['#b5523b', '#8a5a44', '#5b6f82', '#c46a3d', '#6d7f5a'], houses = 0;
    for (var tries = 0; tries < 900 && houses < 160; tries++) {
      var lx = (r() * 2 - 1) * 2.0, lz = -0.4 - r() * 1.8;
      if (Math.abs(lx) < 0.9 && lz > -0.65) continue; if (lx * lx + lz * lz > 4.2) continue;
      var wx = pt.x + lx * Math.cos(ry) + lz * Math.sin(ry), wz = pt.z - lx * Math.sin(ry) + lz * Math.cos(ry);
      if (landAt(wx, wz) < 0.03) continue; var gy = heightAt(wx, wz); if (gy > 0.6) continue;
      var hw = 0.045 + r() * 0.035, hd = 0.04 + r() * 0.03, hh = 0.03 + r() * 0.035, hr = Math.floor(r() * 4) * Math.PI / 2 + (r() - 0.5) * 0.2, big = r() < 0.08;
      if (big) { hw *= 1.6; hh *= 2.2; }
      Box(P, hw, hh + 0.05, hd, lx, gy - 0.05, lz, big ? '#d7dde2' : ['#efe8da', '#e6dcc8', '#f3efe6'][Math.floor(r() * 3)], hr);
      if (!big) Roof(P, hw * 1.08, hh * 0.6, hd * 1.05, lx, gy + hh, lz, ROOF[Math.floor(r() * ROOF.length)], hr);
      houses++;
    }
    var mesh = new THREE.Mesh(mergeParts(P), lambertVC); mesh.castShadow = true; mesh.receiveShadow = true; g.add(mesh);
    var slot = new THREE.Group(); slot.position.set(0.6, QUAY_TOP, -0.3); g.add(slot);
    var LP = []; Cyl(LP, 0.03, 0.04, 0.2, 0, 0, 0, '#f4f4f0', 10); Cyl(LP, 0.042, 0.042, 0.02, 0, 0.08, 0, '#d1495b', 10); Cyl(LP, 0.035, 0.035, 0.04, 0, 0.2, 0, '#f6e7a1', 10); Cone(LP, 0.045, 0.05, 0, 0.24, 0, '#d1495b', 10);
    var lh = new THREE.Mesh(mergeParts(LP), lambertVC); lh.castShadow = true; slot.add(lh);
    var ships = []; for (i = 0; i < 2; i++) { var s = makeShip(t, r); g.add(s); ships.push({ m: s, ph: i * Math.PI + r(), sp: 0.07 + r() * 0.03 }); }
    var flame = null;
    if (t === 'oil') { flame = new THREE.Mesh(new THREE.ConeGeometry(0.02, 0.06, 6), new THREE.MeshBasicMaterial({ color: 0xff8a2a })); flame.position.set(0.3, QUAY_TOP + 0.39, 0.2); g.add(flame); }
    g.visible = false; scene.add(g);
    return { n: n, g: g, slot: slot, ships: ships, flame: flame, custom: null };
  }
  var ports = NATIONS.map(makePort);

  // ───────────────────────── 산업 건물 (레벨이 오르면 늘어남) ─────────────────────────
  var PROP_GEO = (function () {
    var o = {}, P;
    P = []; Box(P, 0.22, 0.08, 0.14, 0, 0, 0, '#9aa5b1'); Roof(P, 0.11, 0.04, 0.14, -0.055, 0.08, 0, '#5b6f82'); Roof(P, 0.11, 0.04, 0.14, 0.055, 0.08, 0, '#5b6f82'); Cyl(P, 0.012, 0.016, 0.22, 0.08, 0, -0.05, '#c0392b', 8); Cyl(P, 0.017, 0.017, 0.02, 0.08, 0.15, -0.05, '#f4f4f0', 8); o.factory = mergeParts(P);
    P = []; Box(P, 0.08, 0.26, 0.08, 0, 0, 0, '#7fb3d5'); Box(P, 0.086, 0.02, 0.086, 0, 0.26, 0, '#eaf2f8'); Box(P, 0.14, 0.05, 0.1, 0.09, 0, 0.04, '#d6eaf8'); Cyl(P, 0.003, 0.003, 0.08, 0, 0.28, 0, '#555', 4); o.tech = mergeParts(P);
    P = []; Box(P, 0.13, 0.015, 0.05, 0, 0, 0, '#555'); Box(P, 0.01, 0.09, 0.01, 0, 0.015, -0.015, '#777', 0, 0.15); Box(P, 0.01, 0.09, 0.01, 0, 0.015, 0.015, '#777', 0, 0.15); Box(P, 0.17, 0.012, 0.014, 0, 0.1, 0, '#e0533d', 0, 0.2); Box(P, 0.025, 0.045, 0.02, 0.085, 0.09, 0, '#333'); Cyl(P, 0.035, 0.035, 0.05, -0.1, 0, 0.06, '#c0392b', 10); o.pump = mergeParts(P);
    P = [];[[-0.04, -0.04], [0.04, -0.04], [-0.04, 0.04], [0.04, 0.04]].forEach(function (p) { Box(P, 0.01, 0.16, 0.01, p[0], 0, p[1], '#6d4c41'); }); Box(P, 0.1, 0.02, 0.1, 0, 0.16, 0, '#5d4037'); Cyl(P, 0.03, 0.03, 0.01, 0, 0.18, 0, '#3e2723', 10, Math.PI / 2); Cone(P, 0.09, 0.06, 0.14, 0, 0.02, '#8a3d22', 9); Box(P, 0.08, 0.04, 0.06, -0.11, 0, 0.05, '#9a958a'); o.mine = mergeParts(P);
    P = []; Box(P, 0.12, 0.07, 0.09, 0, 0, 0, '#b5523b'); Roof(P, 0.13, 0.05, 0.095, 0, 0.07, 0, '#5d4037', Math.PI / 2); Cyl(P, 0.03, 0.03, 0.15, 0.1, 0, 0.02, '#d7ccc8', 12); Cone(P, 0.032, 0.03, 0.1, 0.15, 0.02, '#a1887f', 12); o.farm = mergeParts(P);
    P = [];[[0, 0, 0.1], [0.07, 0.05, -0.12], [-0.06, 0.06, 0.05]].forEach(function (p) { Cyl(P, 0.006, 0.009, 0.15, p[0], 0, p[1], '#8d6e63', 6, p[2]); Blob(P, 0.05, 0.4, p[0] - p[2] * 0.15, 0.15, p[1], '#3e8e41'); }); Box(P, 0.05, 0.03, 0.04, 0.04, 0, -0.06, '#f4d03f'); Box(P, 0.05, 0.03, 0.04, 0.04, 0.03, -0.06, '#f7dc6f'); o.palm = mergeParts(P);
    return o;
  })();
  var PROP_TYPES = Object.keys(PROP_GEO), PCAP = 140;
  var propMesh = {}; PROP_TYPES.forEach(function (t) { var m = new THREE.InstancedMesh(PROP_GEO[t], lambertVC, PCAP); m.count = 0; m.frustumCulled = false; m.castShadow = true; m.receiveShadow = true; m.visible = false; scene.add(m); propMesh[t] = m; });
  // 나라마다 건물 자리 후보(항구 뒤쪽 땅)
  NATIONS.forEach(function (n) {
    var r = rng32(n.i * 104729 + 5), spots = [], pt = n.port;
    for (var t = 0; t < 4000 && spots.length < 40; t++) {
      var a = r() * Math.PI * 2, d = 2.6 + r() * 5.5, x = pt.x + Math.cos(a) * d - pt.sx * 1.5, z = pt.z + Math.sin(a) * d - pt.sz * 1.5;
      if (nationAt(x, z) !== n.i || landAt(x, z) < 0.06 || heightAt(x, z) > 0.75 || !farFromSettle(x, z, 0.5)) continue;
      var ok = true; for (var s = 0; s < spots.length; s++) if (Math.hypot(spots[s][0] - x, spots[s][1] - z) < 0.55) { ok = false; break; }
      if (!ok) continue; spots.push([x, z, r() * Math.PI * 2]);
      FOR[cellIdx(x, z)] = 0;
    }
    n.spots = spots;
  });
  var COUNT_MAIN = [0, 3, 6, 10, 15], COUNT_OTHER = [0, 1, 3, 5, 8];
  function rebuildProps() {
    var cnt = {}; PROP_TYPES.forEach(function (t) { cnt[t] = 0; });
    NATIONS.forEach(function (n) {
      var prof = profiles[n.key], levels = prof && prof.levels ? prof.levels : {}; levels = Object.assign({}, levels);
      if (!levels[n.good]) levels[n.good] = 1;
      var si = 0, order = [n.good].concat(GOOD_KEYS.filter(function (g) { return g !== n.good; }));
      order.forEach(function (g) {
        var lv = clamp(levels[g] | 0, 0, 4), want = g === n.good ? COUNT_MAIN[lv] : COUNT_OTHER[lv], t = GOODS[g].prop, m = propMesh[t];
        for (var q = 0; q < want && si < n.spots.length; q++, si++) {
          if (cnt[t] >= PCAP) break; var sp = n.spots[si], y = heightAt(sp[0], sp[1]), s = 1.5;
          var c = Math.cos(sp[2]) * s, sn = Math.sin(sp[2]) * s, e = m.instanceMatrix.array, o = cnt[t] * 16;
          e[o] = c; e[o + 1] = 0; e[o + 2] = -sn; e[o + 3] = 0; e[o + 4] = 0; e[o + 5] = s; e[o + 6] = 0; e[o + 7] = 0; e[o + 8] = sn; e[o + 9] = 0; e[o + 10] = c; e[o + 11] = 0; e[o + 12] = sp[0]; e[o + 13] = y - 0.01; e[o + 14] = sp[1]; e[o + 15] = 1;
          cnt[t]++;
        }
      });
    });
    PROP_TYPES.forEach(function (t) { propMesh[t].count = cnt[t]; propMesh[t].instanceMatrix.needsUpdate = true; });
  }

  // ───────────────────────── 도시 건물·길 메시 ─────────────────────────
  var cityMeshes = [], bldCount = 0;
  (function () {
    var plain = new THREE.MeshLambertMaterial({ color: 0xffffff }), geos = {};
    geos.wall = new THREE.BoxGeometry(1, 1, 1); geos.wall.translate(0, 0.5, 0);
    var rs = new THREE.Shape([new THREE.Vector2(-0.5, 0), new THREE.Vector2(0.5, 0), new THREE.Vector2(0, 1)]); geos.roof = new THREE.ExtrudeGeometry(rs, { depth: 1, bevelEnabled: false }); geos.roof.translate(0, 0, -0.5);
    geos.dome = new THREE.SphereGeometry(1, 10, 5, 0, Math.PI * 2, 0, Math.PI / 2);
    geos.cone = new THREE.ConeGeometry(1, 1, 8); geos.cone.translate(0, 0.5, 0);
    geos.cyl = new THREE.CylinderGeometry(1, 1, 1, 8); geos.cyl.translate(0, 0.5, 0);
    Object.keys(BLD).forEach(function (t) {
      var a = BLD[t], n = a.length / 10; if (!n) return;
      var m = new THREE.InstancedMesh(geos[t], plain, n), e = m.instanceMatrix.array, col = new THREE.Color();
      for (var k = 0; k < n; k++) {
        var b = k * 10, c = Math.cos(a[b + 6]), s = Math.sin(a[b + 6]), o = k * 16;
        e[o] = c * a[b + 3]; e[o + 1] = 0; e[o + 2] = -s * a[b + 3]; e[o + 3] = 0; e[o + 4] = 0; e[o + 5] = a[b + 4]; e[o + 6] = 0; e[o + 7] = 0;
        e[o + 8] = s * a[b + 5]; e[o + 9] = 0; e[o + 10] = c * a[b + 5]; e[o + 11] = 0; e[o + 12] = a[b]; e[o + 13] = a[b + 1]; e[o + 14] = a[b + 2]; e[o + 15] = 1;
        m.setColorAt(k, col.setRGB(a[b + 7], a[b + 8], a[b + 9]));
      }
      m.instanceMatrix.needsUpdate = true; m.frustumCulled = false; m.castShadow = true; m.receiveShadow = true; m.visible = false; scene.add(m); cityMeshes.push(m);
      if (t === 'wall' || t === 'cyl') bldCount += n;
    });
    // 길: 지형을 따라가는 띠 + 수도 광장
    var pos = [], idx = [];
    function vtx(x, z) { pos.push(x, Math.max(heightAt(x, z), 0.02) + 0.014, z); return pos.length / 3 - 1; }
    ROADS.forEach(function (rd) {
      if (rd.disc) { var cx = rd.disc[0], cz = rd.disc[1], rr = rd.disc[2], c0 = vtx(cx, cz), prev = -1, first = -1; for (var q = 0; q <= 16; q++) { var aa = q / 16 * Math.PI * 2, v = q === 16 ? first : vtx(cx + Math.cos(aa) * rr, cz + Math.sin(aa) * rr); if (q === 0) first = v; if (prev >= 0) idx.push(c0, v, prev); prev = v; } return; }
      var p = rd.pts, w = rd.w / 2, L = [], R = [];
      var dense = []; for (var i = 0; i < p.length - 1; i++) { var sl = Math.hypot(p[i + 1][0] - p[i][0], p[i + 1][1] - p[i][1]), nsub = Math.max(1, Math.ceil(sl / 0.15)); for (var u = 0; u < nsub; u++) dense.push([lerp(p[i][0], p[i + 1][0], u / nsub), lerp(p[i][1], p[i + 1][1], u / nsub)]); } dense.push(p[p.length - 1]);
      for (i = 0; i < dense.length; i++) {
        var a2 = dense[Math.max(0, i - 1)], b2 = dense[Math.min(dense.length - 1, i + 1)], dx = b2[0] - a2[0], dz = b2[1] - a2[1], l = Math.hypot(dx, dz) || 1, nx = -dz / l * w, nz = dx / l * w;
        L.push(vtx(dense[i][0] + nx, dense[i][1] + nz)); R.push(vtx(dense[i][0] - nx, dense[i][1] - nz));
        if (i > 0) idx.push(L[i - 1], R[i - 1], L[i], R[i - 1], R[i], L[i]);
      }
    });
    var g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setIndex(idx); g.computeVertexNormals();
    var roadMat = new THREE.MeshLambertMaterial({ color: 0xb3a58a, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2, side: THREE.DoubleSide });
    var rm = new THREE.Mesh(g, roadMat); rm.receiveShadow = true; rm.visible = false; scene.add(rm); cityMeshes.push(rm);
  })();

  // ───────────────────────── 무역로 (게임 거래에서 만듦) ─────────────────────────
  var routeW = { value: 0.2 }, routes = [], routeGroup = new THREE.Group(); scene.add(routeGroup);
  var dotGeo = new THREE.SphereGeometry(1, 12, 8);
  function clearRoutes() { routes.forEach(function (r) { r.tube.geometry.dispose(); r.mat.dispose(); r.dots.forEach(function (d) { d.m.material.dispose(); }); }); routes = []; while (routeGroup.children.length) routeGroup.remove(routeGroup.children[0]); }
  function setTrades(trades) {
    clearRoutes();
    var agg = {}, order = [];
    (trades || []).forEach(function (t) { (t.legs || []).forEach(function (l) { if (!NK[l.seller] || !NK[l.buyer] || l.seller === l.buyer) return; var k = l.seller + '>' + l.buyer + '>' + l.good; if (!agg[k]) { agg[k] = { s: l.seller, b: l.buyer, good: l.good, qty: 0 }; order.push(k); } agg[k].qty += l.qty || 1; }); });
    var pairCount = {};
    order.forEach(function (k) {
      var a0 = agg[k], A = NK[a0.s].port, B = NK[a0.b].port, info = GOODS[a0.good] || { color: '#888888' };
      var pk = [a0.s, a0.b].sort().join('|'), slot = pairCount[pk] = (pairCount[pk] || 0) + 1;
      var a = new THREE.Vector3(A.x, 0.35, A.z), b = new THREE.Vector3(B.x, 0.35, B.z), len = a.distanceTo(b);
      var mid = a.clone().add(b).multiplyScalar(0.5); mid.y = len * 0.16 + (slot - 1) * Math.max(1.2, len * 0.05);
      var side = new THREE.Vector3(-(b.z - a.z), 0, b.x - a.x).normalize().multiplyScalar((slot - 1) * 0.8 * (a0.s < a0.b ? 1 : -1)); mid.add(side);
      var curve = new THREE.QuadraticBezierCurve3(a, mid, b);
      var mat = new THREE.MeshBasicMaterial({ color: new THREE.Color(info.color), transparent: true, opacity: 0.8, depthWrite: false });
      mat.onBeforeCompile = function (sh) { sh.uniforms.uW = routeW; sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nuniform float uW;').replace('#include <begin_vertex>', 'vec3 transformed = position - normal + normal * uW;'); };
      var tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 64, 1, 6, false), mat); tube.frustumCulled = false; tube.renderOrder = 2; routeGroup.add(tube);
      var dots = [], nd = clamp(Math.ceil(a0.qty / 2), 1, 4);
      for (var i = 0; i < nd; i++) { var d = new THREE.Mesh(dotGeo, new THREE.MeshBasicMaterial({ color: new THREE.Color(info.color), transparent: true })); d.renderOrder = 3; routeGroup.add(d); dots.push({ m: d, off: i / nd }); }
      routes.push({ curve: curve, tube: tube, mat: mat, dots: dots, speed: 1.2 / Math.max(len, 8), info: a0 });
    });
    legendDirty = true;
  }

  // ───────────────────────── 숲 (인스턴싱 + 구역별 생성) ─────────────────────────
  var growU = { value: 1 };
  function treeMat() { var m = new THREE.MeshLambertMaterial({ vertexColors: true }); m.onBeforeCompile = function (sh) { sh.uniforms.uGrow = growU; sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nuniform float uGrow;').replace('#include <begin_vertex>', '#include <begin_vertex>\ntransformed *= uGrow;'); }; return m; }
  var TP1 = []; Cone(TP1, 0.034, 0.1, 0, 0.022, 0, '#2f5a36', 6); Cone(TP1, 0.026, 0.07, 0, 0.07, 0, '#3a6b40', 6); Cyl(TP1, 0.006, 0.008, 0.025, 0, 0, 0, '#6b4a33', 5);
  var TP2 = []; Blob(TP2, 0.042, 1, 0, 0.068, 0, '#4f8a3a'); Cyl(TP2, 0.007, 0.009, 0.035, 0, 0, 0, '#6b4a33', 5);
  var CAP = 16000, _col = new THREE.Color(1, 1, 1);
  var treeMeshes = [new THREE.InstancedMesh(mergeParts(TP1), treeMat(), CAP), new THREE.InstancedMesh(mergeParts(TP2), treeMat(), CAP)];
  treeMeshes.forEach(function (tm) { tm.frustumCulled = false; tm.receiveShadow = true; for (var i = 0; i < CAP; i++) tm.setColorAt(i, _col); tm.count = 0; tm.instanceMatrix.setUsage(THREE.DynamicDrawUsage); scene.add(tm); });
  var CH = 4, chunkCache = new Map();
  function genChunk(cx, cy, lvl) {
    var key = cx + ',' + cy + ',' + lvl, hit = chunkCache.get(key); if (hit) return hit;
    if (chunkCache.size > 900) chunkCache.clear();
    var r = rng32(hash2(cx, cy, lvl * 7 + 1) * 4294967296), s = lvl === 2 ? 0.12 : 0.5, n = Math.round(CH / s), out = [];
    for (var i = 0; i < n; i++) for (var j = 0; j < n; j++) {
      var x = cx * CH + (i + r()) * s, z = cy * CH + (j + r()) * s, r1 = r(), r2 = r(), r3 = r(), r4 = r();
      if (Math.abs(x) > WX || Math.abs(z) > WZ) continue;
      var ci = cellIdx(x, z); if (r1 > FOR[ci]) continue;
      out.push(x, z, r2 * 6.283, 0.75 + r3 * 0.55, CON[ci] ? 0 : 1, r4, heightAt(x, z));
    }
    var arr = new Float32Array(out); chunkCache.set(key, arr); return arr;
  }
  var treeKey = '', treeLvl = 0, treeCount = 0, growT = 1;
  function updateTrees(z) {
    var lvl = z < 0.43 ? 2 : z < 0.64 ? 1 : 0;
    if (lvl === 0) { treeMeshes.forEach(function (t) { t.visible = false; }); treeKey = ''; treeLvl = 0; treeCount = 0; return; }
    var cX = target.x, cZ = target.z - dist * 0.35, R = lvl === 2 ? Math.max(3, dist * 1.5) : dist * 1.3;
    var x0 = Math.floor((cX - R) / CH), x1 = Math.floor((cX + R) / CH), y0 = Math.floor((cZ - R) / CH), y1 = Math.floor((cZ + R) / CH);
    var key = lvl + '|' + x0 + '|' + x1 + '|' + y0 + '|' + y1;
    treeMeshes.forEach(function (t) { t.visible = true; });
    if (key === treeKey) return;
    if (lvl !== treeLvl) growT = 0;
    treeKey = key; treeLvl = lvl;
    var list = [];
    for (var cx = x0; cx <= x1; cx++) for (var cy = y0; cy <= y1; cy++) { var dx = (cx + 0.5) * CH - cX, dy = (cy + 0.5) * CH - cZ; list.push([dx * dx + dy * dy, cx, cy]); }
    list.sort(function (a, b) { return a[0] - b[0]; });
    var cnt = [0, 0], big = lvl === 1 ? 3.4 : 1;
    for (var li = 0; li < list.length; li++) {
      var arr = genChunk(list[li][1], list[li][2], lvl);
      for (var k = 0; k < arr.length; k += 7) {
        var ty = arr[k + 4], tm = treeMeshes[ty], idx = cnt[ty]; if (idx >= CAP) continue;
        var s = arr[k + 3] * big, c = Math.cos(arr[k + 2]) * s, sn = Math.sin(arr[k + 2]) * s, e = tm.instanceMatrix.array, o = idx * 16;
        e[o] = c; e[o + 1] = 0; e[o + 2] = -sn; e[o + 3] = 0; e[o + 4] = 0; e[o + 5] = s; e[o + 6] = 0; e[o + 7] = 0; e[o + 8] = sn; e[o + 9] = 0; e[o + 10] = c; e[o + 11] = 0;
        e[o + 12] = arr[k]; e[o + 13] = arr[k + 6] - 0.01; e[o + 14] = arr[k + 1]; e[o + 15] = 1;
        var v = 0.82 + arr[k + 5] * 0.36; _col.setRGB(v * (lvl === 1 ? 0.88 : 1), v, v * 0.95); tm.setColorAt(idx, _col);
        cnt[ty]++;
      }
      if (cnt[0] >= CAP && cnt[1] >= CAP) break;
    }
    treeMeshes.forEach(function (tm, i) { tm.count = cnt[i]; tm.instanceMatrix.needsUpdate = true; tm.instanceColor.needsUpdate = true; });
    treeCount = cnt[0] + cnt[1];
  }

  // ───────────────────────── 화면 UI ─────────────────────────
  var profiles = {}, me = null, legendDirty = true;
  var ui = el('div', 'position:absolute;inset:0;pointer-events:none;font-family:' + FONT + ';color:#1f2933;'); container.appendChild(ui);
  var labelLayer = el('div', 'position:absolute;inset:0;pointer-events:none;overflow:hidden;'); ui.appendChild(labelLayer);
  var nationLabels = NATIONS.map(function (n) {
    var d = el('div', 'position:absolute;left:0;top:0;text-align:center;white-space:nowrap;will-change:transform;cursor:pointer;pointer-events:auto;user-select:none;-webkit-user-select:none;');
    d.addEventListener('pointerdown', function (ev) { ev.stopPropagation(); });
    d.addEventListener('click', function (ev) { ev.stopPropagation(); selectNation(n.i); });
    labelLayer.appendChild(d); return { el: d, n: n, pos: new THREE.Vector3(n.cx, 0.4, n.cz) };
  });
  var capLabels = SETTLE.filter(function (s) { return s.capital; }).map(function (s) {
    var d = el('div', 'position:absolute;left:0;top:0;background:rgba(255,255,255,0.92);border-radius:10px;padding:1px 8px;font-weight:800;font-size:12px;color:#1d2731;box-shadow:0 1px 3px rgba(0,0,0,0.18);white-space:nowrap;pointer-events:none;border-left:5px solid ' + s.n.color + ';');
    labelLayer.appendChild(d); return { el: d, s: s, pos: new THREE.Vector3(s.x, heightAt(s.x, s.z) + 0.55, s.z) };
  });
  var portLabels = ports.map(function (p) {
    var d = el('div', 'position:absolute;left:0;top:0;background:#ffffff;border:2px solid ' + GOODS[p.n.good].color + ';border-radius:14px;padding:2px 9px 2px 6px;font-weight:700;font-size:12px;color:#1f2933;box-shadow:0 1px 4px rgba(0,0,0,0.2);white-space:nowrap;cursor:pointer;pointer-events:auto;user-select:none;-webkit-user-select:none;');
    d.addEventListener('pointerdown', function (ev) { ev.stopPropagation(); });
    d.addEventListener('click', function (ev) { ev.stopPropagation(); flyToNation(p.n.key); });
    labelLayer.appendChild(d); return { el: d, p: p };
  });
  function levelsLine(n) {
    var prof = profiles[n.key]; if (!prof || !prof.levels) return GOODS[n.good].icon + ' ' + GOODS[n.good].ko;
    return GOOD_KEYS.filter(function (g) { return prof.levels[g] > 0; }).sort(function (a, b) { return (b === n.good) - (a === n.good); }).map(function (g) { return GOODS[g].icon + prof.levels[g]; }).join(' ');
  }
  function refreshLabels() {
    nationLabels.forEach(function (l) {
      var n = l.n, prof = profiles[n.key] || {}, isMe = me === n.key, stu = prof.student;
      var badge = isMe ? '<span style="display:inline-block;margin-left:4px;padding:0 6px;border-radius:8px;background:#2f6fd6;color:#ffffff;font-size:10px;vertical-align:2px;">우리 나라</span>' : stu ? '<span style="display:inline-block;margin-left:4px;padding:0 6px;border-radius:8px;background:#1f2933;color:#ffffff;font-size:10px;vertical-align:2px;">학생</span>' : '';
      l.el.innerHTML = '<div style="font-weight:800;font-size:14px;letter-spacing:0.5px;color:#1d2731;text-shadow:0 0 3px #ffffff,0 0 3px #ffffff,0 0 2px #ffffff;">' + esc(names[n.key] || n.ko) + badge + '</div><div style="font-size:11px;font-weight:700;color:#3a4652;text-shadow:0 0 3px #ffffff,0 0 3px #ffffff;">' + levelsLine(n) + '</div>';
    });
    portLabels.forEach(function (l) { var n = l.p.n; l.el.innerHTML = GOODS[n.good].icon + ' ' + esc(names[n.key] || n.ko) + ' 항구'; });
    capLabels.forEach(function (l) { l.el.innerHTML = '🏛️ ' + esc(names[l.s.n.key] || l.s.n.ko) + ' 수도'; });
  }
  var hasPanel = opts.panel !== false;
  var panel = el('div', 'position:absolute;left:12px;top:12px;width:258px;background:rgba(255,255,255,0.94);border:1px solid #d5dce3;border-radius:14px;box-shadow:0 4px 16px rgba(20,30,40,0.14);padding:12px 14px;pointer-events:auto;font-size:12px;line-height:1.5;' + (hasPanel ? '' : 'display:none;'));
  panel.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;"><div style="font-weight:800;font-size:14px;color:#14202b;">' + esc(opts.title || '무역 게임 세계 지도') + '</div><button data-k="fold" style="border:none;background:#eef2f6;color:#4a5866;border-radius:8px;padding:2px 8px;font-size:11px;cursor:pointer;font-family:inherit;">접기</button></div>' +
    '<div data-k="body"><div data-k="info" style="margin-top:6px;color:#3a4652;font-weight:600;"></div><div data-k="levels" style="display:flex;gap:4px;margin:8px 0;"></div><div data-k="layers"></div><div data-k="stats" style="margin-top:8px;color:#6a7784;font-size:11px;"></div><div data-k="glb"></div></div>';
  ui.appendChild(panel);
  function q(k) { return panel.querySelector('[data-k="' + k + '"]'); }
  var lvEls = ['세계', '대륙', '지역'].map(function (n, i) { var d = el('div', 'flex:1;text-align:center;padding:5px 0;border-radius:8px;font-weight:700;font-size:12px;background:#eef2f6;color:#7b8794;', (i + 1) + '단계 ' + n); q('levels').appendChild(d); return d; });
  var LAYERS = ['나라 색·국경', '무역로·화물 이동', '지형 색 (사막·들판·숲·산)', '숲: 큰 덩어리 (낮은 LOD)', '숲: 나무 한 그루씩 (높은 LOD)', '3D 항구·도시·산업 건물·그림자'];
  var layEls = LAYERS.map(function (n) { var d = el('div', 'display:flex;align-items:center;gap:6px;color:#9aa5b1;', '<span style="display:inline-block;width:9px;height:9px;border-radius:5px;background:#cfd6dd;"></span><span>' + n + '</span>'); q('layers').appendChild(d); return d; });
  var folded = !!opts.panelFolded;
  function applyFold() { q('body').style.display = folded ? 'none' : 'block'; q('fold').textContent = folded ? '펼치기' : '접기'; }
  q('fold').addEventListener('click', function () { folded = !folded; applyFold(); }); applyFold();

  var btnCss = 'width:44px;height:44px;border-radius:12px;border:1px solid #d5dce3;background:#ffffff;color:#1f2933;font-size:22px;font-weight:700;cursor:pointer;box-shadow:0 2px 8px rgba(20,30,40,0.12);display:flex;align-items:center;justify-content:center;font-family:inherit;padding:0;';
  var zoomBox = el('div', 'position:absolute;right:12px;top:12px;display:flex;flex-direction:column;gap:8px;pointer-events:auto;'); ui.appendChild(zoomBox);
  [['＋', function () { zoomBy(0.45); }], ['－', function () { zoomBy(2.2); }], ['🌍', function () { flyTo(HOME[0], HOME[1], HOME[2]); }]].forEach(function (b) { var e = el('button', btnCss, b[0]); e.addEventListener('click', b[1]); zoomBox.appendChild(e); });

  var legend = el('div', 'position:absolute;right:12px;top:172px;background:rgba(255,255,255,0.94);border:1px solid #d5dce3;border-radius:12px;padding:8px 10px;font-size:11px;font-weight:600;pointer-events:none;box-shadow:0 2px 8px rgba(20,30,40,0.12);display:none;'); ui.appendChild(legend);
  function refreshLegend() {
    var used = {}; routes.forEach(function (r) { used[r.info.good] = (used[r.info.good] || 0) + r.info.qty; });
    var keys = GOOD_KEYS.filter(function (g) { return used[g]; });
    legend.innerHTML = '<div style="font-weight:800;margin-bottom:4px;color:#14202b;">이번 라운드 거래</div>' + (keys.length ? keys.map(function (g) { return '<div style="display:flex;align-items:center;gap:6px;"><span style="display:inline-block;width:16px;height:4px;border-radius:2px;background:' + GOODS[g].color + ';"></span>' + GOODS[g].icon + ' ' + GOODS[g].ko + ' ' + used[g] + '개</div>'; }).join('') : '<div style="color:#7b8794;">아직 없음</div>');
    legendDirty = false;
  }

  var natBar = el('div', 'position:absolute;left:50%;bottom:12px;transform:translateX(-50%);max-width:calc(100% - 24px);display:flex;gap:6px;overflow-x:auto;padding:6px;background:rgba(255,255,255,0.94);border:1px solid #d5dce3;border-radius:14px;box-shadow:0 4px 16px rgba(20,30,40,0.14);pointer-events:auto;' + (opts.nationBar === false ? 'display:none;' : ''));
  var natBtns = NATIONS.map(function (n) { var b = el('button', 'flex:none;border:none;background:#f1f4f7;border-radius:10px;padding:7px 10px;font-size:12px;font-weight:700;color:#1f2933;cursor:pointer;white-space:nowrap;font-family:inherit;border-bottom:4px solid ' + n.color + ';'); b.addEventListener('click', function () { flyToNation(n.key); }); natBar.appendChild(b); return b; });
  function refreshNatBar() { natBtns.forEach(function (b, i) { var n = NATIONS[i]; b.innerHTML = GOODS[n.good].icon + ' ' + esc(names[n.key] || n.ko) + (me === n.key ? ' ★' : ''); }); }
  ui.appendChild(natBar);

  var card = el('div', 'position:absolute;left:12px;bottom:78px;min-width:210px;background:#ffffff;border:1px solid #d5dce3;border-radius:14px;box-shadow:0 4px 16px rgba(20,30,40,0.16);padding:12px 14px;pointer-events:auto;display:none;font-size:12px;'); ui.appendChild(card);
  var toast = el('div', 'position:absolute;left:50%;top:14px;transform:translateX(-50%);background:#1f2933;color:#ffffff;padding:8px 14px;border-radius:10px;font-size:13px;font-weight:600;opacity:0;transition:opacity 0.3s;pointer-events:none;white-space:nowrap;'); ui.appendChild(toast);
  var toastTimer = null;
  function showToast(t) { toast.textContent = t; toast.style.opacity = '1'; clearTimeout(toastTimer); toastTimer = setTimeout(function () { toast.style.opacity = '0'; }, 2600); }
  var help = el('div', 'position:absolute;right:12px;bottom:78px;background:rgba(31,41,51,0.82);color:#ffffff;padding:7px 11px;border-radius:10px;font-size:11px;transition:opacity 1s;pointer-events:none;', isTouch ? '한 손가락: 이동 · 두 손가락: 확대/축소 · 탭: 나라 보기' : '드래그: 이동 · 휠: 확대/축소 · 클릭: 나라 보기 · 더블클릭: 확대');
  ui.appendChild(help); setTimeout(function () { help.style.opacity = '0'; }, 7000);

  function selectNation(i) {
    if (i == null || i < 0) { card.style.display = 'none'; terrU.uSel.value = -1; return; }
    var n = NATIONS[i], prof = profiles[n.key] || {}; terrU.uSel.value = i;
    var lv = prof.levels || {}, rows = GOOD_KEYS.filter(function (g) { return lv[g] > 0; }).map(function (g) { return '<div style="display:flex;justify-content:space-between;gap:10px;"><span>' + GOODS[g].icon + ' ' + GOODS[g].ko + (g === prof.main || (!prof.main && g === n.good) ? ' <b style="color:#2f6fd6;">대표</b>' : '') + (g === prof.focus ? ' <b style="color:#d35400;">주력</b>' : '') + '</span><span style="font-weight:800;">Lv' + lv[g] + '</span></div>'; }).join('');
    var sold = 0, bought = 0; routes.forEach(function (r) { if (r.info.s === n.key) sold += r.info.qty; if (r.info.b === n.key) bought += r.info.qty; });
    card.innerHTML = '<div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;"><div><div style="font-weight:800;font-size:16px;color:#14202b;"><span style="display:inline-block;width:10px;height:10px;border-radius:3px;background:' + n.color + ';margin-right:6px;"></span>' + esc(names[n.key] || n.ko) + '</div><div style="color:#7b8794;font-size:11px;">대표 산업 ' + GOODS[prof.main || n.good].icon + ' ' + GOODS[prof.main || n.good].ko + (me === n.key ? ' · 우리 나라' : prof.student ? ' · 학생' : prof.evaluated === false ? ' · AI 전용' : ' · AI') + '</div></div><button data-x style="border:none;background:#eef2f6;border-radius:8px;width:26px;height:26px;cursor:pointer;font-size:14px;color:#4a5866;">✕</button></div>' +
      (rows ? '<div style="margin-top:8px;display:flex;flex-direction:column;gap:2px;">' + rows + '</div>' : '') +
      '<div style="margin-top:8px;color:#3a4652;">이번 라운드: 판 물건 <b>' + sold + '</b>개 · 산 물건 <b>' + bought + '</b>개</div>' +
      '<button data-go style="margin-top:10px;width:100%;border:none;background:#2f6fd6;color:#ffffff;border-radius:10px;padding:8px 0;font-weight:700;font-size:12px;cursor:pointer;font-family:inherit;">항구로 가기</button>';
    card.style.display = 'block';
    card.querySelector('[data-x]').onclick = function () { selectNation(-1); };
    card.querySelector('[data-go]').onclick = function () { flyToNation(n.key); };
    if (opts.onSelect) opts.onSelect(n.key);
  }

  // ───────────────────────── Tripo GLB 불러오기 ─────────────────────────
  function nearestPort() { var best = null, bd = 1e9; ports.forEach(function (p) { var dx = p.n.port.x - target.x, dz = p.n.port.z - target.z, d = dx * dx + dz * dz; if (d < bd) { bd = d; best = p; } }); return { p: best, d: Math.sqrt(bd) }; }
  function placeModel(obj, name, nationKey) {
    var np = nationKey && NK[nationKey] ? { p: ports[NK[nationKey].i], d: 0 } : nearestPort(), port = np.p;
    obj.traverse(function (o) {
      if (o.isMesh) {
        var mats = Array.isArray(o.material) ? o.material : [o.material];
        var conv = mats.map(function (m) { var map = m && m.map ? m.map : null; if (map) { map.encoding = THREE.LinearEncoding; map.needsUpdate = true; } return new THREE.MeshLambertMaterial({ map: map, color: map ? 0xffffff : (m && m.color ? m.color : 0xcccccc), vertexColors: !!(o.geometry && o.geometry.attributes.color) }); });
        o.material = Array.isArray(o.material) ? conv : conv[0]; o.castShadow = true; o.receiveShadow = true;
      }
    });
    var wrap = new THREE.Group(); wrap.add(obj);
    var box = new THREE.Box3().setFromObject(obj), size = box.getSize(new THREE.Vector3());
    obj.scale.multiplyScalar(0.36 / Math.max(size.x, size.z, size.y * 0.55, 1e-6));
    box.setFromObject(obj); var ctr = box.getCenter(new THREE.Vector3());
    obj.position.x -= ctr.x; obj.position.z -= ctr.z; obj.position.y -= box.min.y;
    if (port.custom) port.slot.remove(port.custom);
    port.slot.children.forEach(function (ch) { ch.visible = false; });
    port.slot.add(wrap); port.custom = wrap;
    port.g.updateMatrixWorld(true); var sw = port.slot.getWorldPosition(new THREE.Vector3());
    flyTo(sw.x, sw.z + 0.55, 2.4, np.d > 6 || dist > 8 ? null : 0.8);
    showToast('“' + name + '” → ' + (names[port.n.key] || port.n.ko) + ' 항구 등대 자리에 배치했어요');
  }
  function loadFile(file) {
    if (!opts.GLTFLoader) { showToast('이 버전에서는 GLB 불러오기를 지원하지 않아요'); return; }
    var url = URL.createObjectURL(file);
    new opts.GLTFLoader().load(url, function (gltf) { URL.revokeObjectURL(url); placeModel(gltf.scene, file.name); }, undefined, function (err) { URL.revokeObjectURL(url); showToast('불러오기 실패: ' + (err && err.message ? err.message : '파일 확인')); });
  }
  if (opts.GLTFLoader) {
    var gb = q('glb');
    gb.innerHTML = '<div style="height:1px;background:#e3e8ee;margin:10px 0;"></div><label style="display:block;text-align:center;background:#1f2933;color:#ffffff;border-radius:10px;padding:8px 0;font-weight:700;cursor:pointer;">Tripo 모델(GLB) 불러오기<input type="file" accept=".glb,.gltf" style="display:none;"></label><div style="color:#6a7784;font-size:11px;margin-top:6px;">화면에 가장 가까운 항구의 등대 자리에 놓여요. 파일을 지도에 끌어다 놓아도 돼요.</div>';
    gb.querySelector('input').addEventListener('change', function (e) { if (e.target.files[0]) loadFile(e.target.files[0]); e.target.value = ''; });
    container.addEventListener('dragover', function (e) { e.preventDefault(); });
    container.addEventListener('drop', function (e) { e.preventDefault(); var f = e.dataTransfer.files[0]; if (f) loadFile(f); });
  }

  // ───────────────────────── 카메라·조작 ─────────────────────────
  var HOME = [-10, 2, 185], target = new THREE.Vector3(HOME[0], GROUND_Y, HOME[1]), dist = HOME[2], fly = null;
  if (opts.start) { target.x = opts.start[0]; target.z = opts.start[1]; dist = opts.start[2]; }
  var raycaster = new THREE.Raycaster(), groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -GROUND_Y), _ndc = new THREE.Vector2();
  function zoomT() { return (Math.log(dist) - Math.log(DMIN)) / (Math.log(DMAX) - Math.log(DMIN)); }
  function tiltFor(z) { return (3 + 55 * (1 - sstep(0.12, 0.88, z))) * Math.PI / 180; }
  function updateCamera() {
    dist = clamp(dist, DMIN, DMAX); target.x = clamp(target.x, -WX, WX); target.z = clamp(target.z, -WZ, WZ);
    var t = tiltFor(zoomT()), gy = Math.max(GROUND_Y, heightAt(target.x, target.z) * sstep(0.5, 0.1, zoomT()));
    camera.position.set(target.x, gy + dist * Math.cos(t), target.z + dist * Math.sin(t));
    camera.lookAt(target.x, gy, target.z);
    camera.near = Math.max(0.02, dist * 0.02); camera.far = dist * 14 + 100; camera.updateProjectionMatrix(); camera.updateMatrixWorld();
  }
  function groundAt(cx, cy) { var rc = canvas.getBoundingClientRect(); _ndc.set((cx - rc.left) / rc.width * 2 - 1, -(cy - rc.top) / rc.height * 2 + 1); raycaster.setFromCamera(_ndc, camera); return raycaster.ray.intersectPlane(groundPlane, new THREE.Vector3()); }
  function zoomAt(cx, cy, f) { var p0 = groundAt(cx, cy); dist = clamp(dist * f, DMIN, DMAX); updateCamera(); var p1 = groundAt(cx, cy); if (p0 && p1) { target.x += p0.x - p1.x; target.z += p0.z - p1.z; } updateCamera(); }
  function zoomBy(f) { flyTo(target.x, target.z, dist * f, 0.5); }
  function flyTo(x, z, d, dur) {
    var sep = Math.hypot(x - target.x, z - target.z), ld0 = Math.log(dist), ld1 = Math.log(clamp(d, DMIN, DMAX));
    var bump = Math.max(0, Math.log(clamp(sep * 1.2, 1, DMAX)) - Math.max(ld0, ld1));
    fly = { t0: performance.now(), dur: (dur || (1.2 + Math.min(1.2, sep / 60))) * 1000, sx: target.x, sz: target.z, ex: x, ez: z, ld0: ld0, ld1: ld1, bump: bump };
  }
  function flyToNation(key, d) { var n = NK[key]; if (!n) return; var p = n.port; flyTo(p.x - p.sx * 0.6, p.z - p.sz * 0.6 + 0.4, d || 3.4); }
  var pointers = new Map(), drag = null, pinch = null, downInfo = null, lastTap = 0;
  function onDown(e) {
    if (canvas.setPointerCapture) canvas.setPointerCapture(e.pointerId);
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY }); fly = null;
    if (pointers.size === 1) { drag = { grab: groundAt(e.clientX, e.clientY) }; downInfo = { x: e.clientX, y: e.clientY, t: performance.now(), moved: false }; }
    else if (pointers.size === 2) { var pts = Array.from(pointers.values()); pinch = { d0: Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y), dist0: dist, grab: groundAt((pts[0].x + pts[1].x) / 2, (pts[0].y + pts[1].y) / 2) }; drag = null; if (downInfo) downInfo.moved = true; }
  }
  function onMove(e) {
    if (!pointers.has(e.pointerId)) return;
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (downInfo && Math.hypot(e.clientX - downInfo.x, e.clientY - downInfo.y) > 6) downInfo.moved = true;
    if (pinch && pointers.size >= 2) {
      var pts = Array.from(pointers.values()), mxp = (pts[0].x + pts[1].x) / 2, myp = (pts[0].y + pts[1].y) / 2;
      dist = clamp(pinch.dist0 * pinch.d0 / Math.max(Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y), 1), DMIN, DMAX); updateCamera();
      var cur = groundAt(mxp, myp); if (pinch.grab && cur) { target.x += pinch.grab.x - cur.x; target.z += pinch.grab.z - cur.z; } updateCamera();
    } else if (drag && drag.grab) { var c2 = groundAt(e.clientX, e.clientY); if (c2) { target.x += drag.grab.x - c2.x; target.z += drag.grab.z - c2.z; updateCamera(); } }
  }
  function onUp(e) {
    pointers.delete(e.pointerId);
    if (pointers.size < 2) pinch = null;
    if (pointers.size === 1) { var p = Array.from(pointers.values())[0]; drag = { grab: groundAt(p.x, p.y) }; }
    if (pointers.size === 0) {
      drag = null;
      if (downInfo && !downInfo.moved && performance.now() - downInfo.t < 450) {
        var now = performance.now(), g0 = groundAt(e.clientX, e.clientY);
        if (now - lastTap < 320) { if (g0) flyTo(g0.x, g0.z, dist * 0.4, 0.5); lastTap = 0; }
        else { lastTap = now; selectNation(g0 && landAt(g0.x, g0.z) > 0 ? nationAt(g0.x, g0.z) : -1); }
      }
      downInfo = null;
    }
  }
  function onWheel(e) { e.preventDefault(); fly = null; var dy = e.deltaMode === 1 ? e.deltaY * 30 : e.deltaY; zoomAt(e.clientX, e.clientY, Math.exp(clamp(dy, -200, 200) * 0.0016)); }
  function onKey(e) {
    var s = dist * 0.12;
    if (e.key === 'ArrowLeft' || e.key === 'a') target.x -= s; else if (e.key === 'ArrowRight' || e.key === 'd') target.x += s;
    else if (e.key === 'ArrowUp' || e.key === 'w') target.z -= s; else if (e.key === 'ArrowDown' || e.key === 's') target.z += s;
    else if (e.key === '+' || e.key === '=') zoomBy(0.5); else if (e.key === '-') zoomBy(2); else return;
    fly = null; updateCamera();
  }
  canvas.addEventListener('pointerdown', onDown); canvas.addEventListener('pointermove', onMove);
  canvas.addEventListener('pointerup', onUp); canvas.addEventListener('pointercancel', onUp);
  canvas.addEventListener('wheel', onWheel, { passive: false });
  canvas.tabIndex = 0; canvas.addEventListener('keydown', onKey);
  canvas.addEventListener('contextmenu', function (e) { e.preventDefault(); });
  function onResize() { var w = container.clientWidth, h = container.clientHeight; if (!w || !h) return; renderer.setSize(w, h); camera.aspect = w / h; updateCamera(); }
  var ro = window.ResizeObserver ? new ResizeObserver(onResize) : null; if (ro) ro.observe(container); else window.addEventListener('resize', onResize);

  // ───────────────────────── 게임 상태 연결 ─────────────────────────
  function setProfiles(p) { profiles = p || {}; rebuildProps(); refreshLabels(); if (terrU.uSel.value >= 0) selectNation(terrU.uSel.value); }
  function setMe(key) { me = NK[key] ? key : null; terrU.uMe.value = me ? NK[me].i : -1; refreshLabels(); refreshNatBar(); }
  function update(state) {
    if (!state) return;
    if (state.names) { for (var k in state.names) if (NK[k]) names[k] = state.names[k]; refreshNatBar(); }
    if (state.country !== undefined) setMe(state.country);
    if (state.profiles) setProfiles(state.profiles); else refreshLabels();
    if (state.world_trades) setTrades(state.world_trades);
    if (state.round != null) infoText = (state.round ? state.round + '라운드' : '') + (state.phase_label ? ' · ' + state.phase_label : '');
  }

  // 데모: 게임 없이 볼 때 라운드마다 가짜 거래·레벨을 만든다
  var demo = null, infoText = '';
  function demoRound() {
    var r = rng32(demo.round * 991 + 7), p = {};
    NATIONS.forEach(function (n, i) {
      var lv = demo.levels[n.key] || (demo.levels[n.key] = {}); if (!lv[n.good]) lv[n.good] = 1;
      if (demo.round > 1 && r() < 0.35) { var g = r() < 0.7 ? n.good : GOOD_KEYS[Math.floor(r() * 6)]; lv[g] = Math.min(4, (lv[g] || 0) + 1); }
      p[n.key] = { main: n.good, expand: null, focus: n.good, levels: Object.assign({}, lv), student: ['Tropia', 'Oilia', 'Mineria'].indexOf(n.key) >= 0, evaluated: i < 6 || ['Novia', 'Agrea', 'Ferria'].indexOf(n.key) < 0 };
    });
    var trades = [], nt = 8 + Math.floor(r() * 7);
    for (var t = 0; t < nt; t++) {
      var s = NATIONS[Math.floor(r() * N)], b = NATIONS[Math.floor(r() * N)]; if (s === b) continue;
      var lv2 = demo.levels[s.key], own = Object.keys(lv2), good = r() < 0.75 ? s.good : own[Math.floor(r() * own.length)];
      trades.push({ channel: r() < 0.5 ? 'market' : 'offer', legs: [{ seller: s.key, buyer: b.key, good: good, label: GOODS[good].ko, gen: 1, qty: 1 + Math.floor(r() * 4) }] });
    }
    update({ round: demo.round, phase_label: '데모', profiles: p, world_trades: trades });
    demo.round = demo.round % 9 + 1;
  }
  if (opts.demo) { demo = { round: 1, levels: {} }; demoRound(); demo.timer = setInterval(demoRound, opts.demoInterval || 8000); }
  else { refreshLabels(); rebuildProps(); setTrades([]); }
  setMe(opts.me || null); refreshNatBar();

  // ───────────────────────── 매 프레임 ─────────────────────────
  var _p = new THREE.Vector3(), _pp = {}, raf = 0, last = performance.now(), clock = 0, hudTick = 0;
  function setLayer(i, on) { var d = layEls[i]; d.style.color = on ? '#1f2933' : '#9aa5b1'; d.firstChild.style.background = on ? '#2bb673' : '#cfd6dd'; }
  function project(v, out) { _p.copy(v).project(camera); var w = canvas.clientWidth, h = canvas.clientHeight; out.x = (_p.x * 0.5 + 0.5) * w; out.y = (-_p.y * 0.5 + 0.5) * h; out.ok = _p.z < 1 && _p.x > -1.15 && _p.x < 1.15 && _p.y > -1.15 && _p.y < 1.15; return out; }
  function frame(now) {
    raf = requestAnimationFrame(frame);
    var dt = Math.min(0.05, (now - last) / 1000); last = now; clock += dt;
    if (fly) {
      var e = Math.min(1, (now - fly.t0) / fly.dur), k = e < 0.5 ? 4 * e * e * e : 1 - Math.pow(-2 * e + 2, 3) / 2;
      target.x = lerp(fly.sx, fly.ex, k); target.z = lerp(fly.sz, fly.ez, k); dist = Math.exp(lerp(fly.ld0, fly.ld1, k) + fly.bump * Math.sin(Math.PI * k));
      if (e >= 1) fly = null;
    }
    updateCamera();
    var z = zoomT(), polMix = sstep(0.55, 0.78, z), detail = 1 - sstep(0.3, 0.6, z);
    terrU.uMix.value = polMix; terrU.uDetail.value = detail; terrU.uBorder.value = sstep(0.62, 0.8, z);
    oceanMat.color.copy(OCEAN_POL).lerp(OCEAN_NAT, 1 - polMix); oceanMat.opacity = lerp(0.72, 0.96, polMix);
    oceanMat.specular.setScalar(0.35 * detail); oceanMat.normalScale.set(0.6 * detail, 0.6 * detail);
    waveTex.offset.x += dt * 0.004; waveTex.offset.y += dt * 0.0025;
    scene.fog.near = dist * 1.7; scene.fog.far = dist * 5.5;
    var sh = clamp(dist * 0.75, 1.2, 9); sun.shadow.camera.left = -sh; sun.shadow.camera.right = sh; sun.shadow.camera.top = sh; sun.shadow.camera.bottom = -sh; sun.shadow.camera.near = 0.1; sun.shadow.camera.far = 60; sun.shadow.camera.updateProjectionMatrix();
    sun.position.set(target.x + SUN_DIR.x * 25, SUN_DIR.y * 25, target.z + SUN_DIR.z * 25); sun.target.position.set(target.x, 0, target.z); sun.target.updateMatrixWorld();
    var rOp = sstep(0.38, 0.55, z), dotS = dist * 0.0045; routeW.value = dist * 0.0017;
    routes.forEach(function (r) { r.tube.visible = rOp > 0.01; r.mat.opacity = 0.75 * rOp; r.dots.forEach(function (d) { d.m.visible = rOp > 0.01; d.m.material.opacity = rOp; r.curve.getPoint((clock * r.speed + d.off) % 1, d.m.position); d.m.scale.setScalar(dotS); }); });
    legend.style.display = rOp > 0.3 && opts.legend !== false ? 'block' : 'none'; if (legendDirty) refreshLegend();
    updateTrees(z);
    if (growT < 1) growT = Math.min(1, growT + dt * 2.2); growU.value = sstep(0, 1, growT);
    var pScale = sstep(0.46, 0.38, z), propVis = pScale > 0.001;
    PROP_TYPES.forEach(function (t) { propMesh[t].visible = propVis; });
    ports.forEach(function (p) {
      var dx = p.n.port.x - target.x, dz = p.n.port.z - target.z; p.g.visible = propVis && dx * dx + dz * dz < Math.pow(dist * 2.2 + 4, 2);
      if (!p.g.visible) return;
      p.g.scale.set(1, Math.max(0.001, pScale), 1);
      p.ships.forEach(function (s) { var th = clock * s.sp * 2 * Math.PI + s.ph, ax = 0.78, bz = 0.34; s.m.position.set(Math.cos(th) * ax, 0, 1.38 + Math.sin(th) * bz); s.m.rotation.y = Math.atan2(-(Math.cos(th) * bz), -Math.sin(th) * ax); });
      if (p.flame) { var f = 0.85 + Math.sin(clock * 23 + p.n.i) * 0.12 + Math.sin(clock * 37) * 0.08; p.flame.scale.set(f, f * 1.2, f); }
    });
    var cityVis = z < 0.63; cityMeshes.forEach(function (m) { m.visible = cityVis; });
    var capOp = sstep(0.28, 0.36, z) * (1 - sstep(0.56, 0.64, z));
    capLabels.forEach(function (l) { if (capOp < 0.01) { l.el.style.display = 'none'; return; } project(l.pos, _pp); if (!_pp.ok) { l.el.style.display = 'none'; return; } l.el.style.display = 'block'; l.el.style.opacity = capOp; l.el.style.transform = 'translate(' + _pp.x.toFixed(1) + 'px,' + _pp.y.toFixed(1) + 'px) translate(-50%,-100%)'; });
    var cOp = sstep(0.5, 0.62, z);
    nationLabels.forEach(function (l) { if (cOp < 0.01) { l.el.style.display = 'none'; return; } project(l.pos, _pp); if (!_pp.ok) { l.el.style.display = 'none'; return; } l.el.style.display = 'block'; l.el.style.opacity = cOp; l.el.style.transform = 'translate(' + _pp.x.toFixed(1) + 'px,' + _pp.y.toFixed(1) + 'px) translate(-50%,-50%)'; });
    var pOp = 1 - sstep(0.6, 0.7, z);
    portLabels.forEach(function (l) {
      if (pOp < 0.01) { l.el.style.display = 'none'; return; }
      _p.set(l.p.n.port.x, z < 0.43 ? 0.7 : 0.4, l.p.n.port.z); project(_p.clone(), _pp);
      if (!_pp.ok) { l.el.style.display = 'none'; return; } l.el.style.display = 'block'; l.el.style.opacity = pOp;
      l.el.style.transform = 'translate(' + _pp.x.toFixed(1) + 'px,' + _pp.y.toFixed(1) + 'px) translate(-50%,-100%)';
    });
    renderer.render(scene, camera);
    if ((hudTick += dt) > 0.15 && hasPanel) {
      hudTick = 0;
      var lv = z > 0.64 ? 0 : z > 0.43 ? 1 : 2;
      lvEls.forEach(function (d, i) { d.style.background = i === lv ? '#2f6fd6' : '#eef2f6'; d.style.color = i === lv ? '#ffffff' : '#7b8794'; });
      setLayer(0, polMix > 0.5); setLayer(1, rOp > 0.1); setLayer(2, polMix <= 0.5); setLayer(3, treeLvl === 1); setLayer(4, treeLvl === 2); setLayer(5, propVis);
      q('info').textContent = infoText ? infoText + ' · 거래 ' + routes.reduce(function (s, r) { return s + r.info.qty; }, 0) + '개' : '';
      q('stats').textContent = '나무 ' + treeCount.toLocaleString() + '그루 · 그리기 호출 ' + renderer.info.render.calls + '회 · 카메라 거리 ' + dist.toFixed(1);
    }
  }
  updateCamera(); raf = requestAnimationFrame(frame);

  return {
    update: update, setProfiles: setProfiles, setTrades: setTrades, setMe: setMe,
    flyTo: flyTo, flyToNation: flyToNation, selectNation: function (key) { selectNation(NK[key] ? NK[key].i : -1); },
    setView: function (x, z, d) { fly = null; target.x = x; target.z = z; dist = d; updateCamera(); },
    getState: function () { return { x: target.x, z: target.z, dist: dist, zoom: zoomT(), trees: treeCount, calls: renderer.info.render.calls, routes: routes.length, buildings: bldCount, settlements: SETTLE.length, props: PROP_TYPES.reduce(function (s, t) { return s + propMesh[t].count; }, 0) }; },
    nations: NATIONS.map(function (n) { return { key: n.key, ko: n.ko, good: n.good, port: { x: n.port.x, z: n.port.z }, center: { x: n.cx, z: n.cz }, cells: n.cells }; }),
    settlements: SETTLE.map(function (s) { return { nation: s.n.key, capital: s.capital, x: s.x, z: s.z, r: s.R }; }),
    loadFile: loadFile, placeModel: placeModel,
    dispose: function () {
      cancelAnimationFrame(raf); if (demo && demo.timer) clearInterval(demo.timer); if (ro) ro.disconnect(); else window.removeEventListener('resize', onResize);
      clearRoutes(); scene.traverse(function (o) { if (o.geometry) o.geometry.dispose(); });
      renderer.dispose(); if (canvas.parentNode) canvas.parentNode.removeChild(canvas); if (ui.parentNode) ui.parentNode.removeChild(ui);
    }
  };
}
