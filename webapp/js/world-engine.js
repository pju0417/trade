// 세계 지도 엔진: version2/world-map-demo.html의 createWorldMap을 그대로 옮긴 것(three.js r128, 전역 THREE).
// 데모를 고치면 이 파일의 createWorldMap도 같이 바꾼다. 게임 쪽 연결은 world-map.js가 맡는다.
import { MeshoptDecoder } from '../assets/world/vendor/meshopt_decoder.module.js';

const root = new URL('../assets/world/', import.meta.url);
let engine;
function script(src) {
  return new Promise((resolve, reject) => {
    const tag = document.createElement('script'); tag.src = src;
    tag.onload = resolve; tag.onerror = () => reject(new Error(`${src}를 불러오지 못했어요.`));
    document.head.append(tag);
  });
}
// three r128은 전역 스크립트라 한 번만 넣는다(게임의 다른 화면은 three를 쓰지 않는다).
function loadEngine() {
  engine ||= (async () => {
    if (!window.THREE?.WebGLRenderer || window.THREE.REVISION !== '128') await script(new URL('vendor/three-r128.min.js', root).href);
    if (!window.THREE.GLTFLoader) await script(new URL('vendor/GLTFLoader-r128.js', root).href);
    await MeshoptDecoder.ready;
    return window.THREE;
  })().catch(error => { engine = null; throw error; });
  return engine;
}
export async function createWorld(container, options = {}) {
  const THREE = await loadEngine();
  return createWorldMap(container, THREE, { GLTFLoader: THREE.GLTFLoader, MeshoptDecoder, modelBase: new URL('models/', root).href, ...options });
}

function createWorldMap(container, THREE, opts) {
  opts = opts || {};
  // Tripo 3D 모델 폴더(GLB). 비우면(opts.modelBase = '') 코드로 만든 도형만 쓴다.
  var MODEL_BASE = opts.modelBase === undefined ? 'assets/models/web/' : opts.modelBase;
  var USE_MODELS = !!(MODEL_BASE && opts.GLTFLoader && opts.MeshoptDecoder);
  // ───────────────────────── 상수 ─────────────────────────
  // 세계 크기 비율: 나라 배치·모양은 그대로 두고 전체 크기만 바꾼다(1 = 처음 크기). 항구·집·나무 크기는 그대로다.
  var S = opts.worldScale || 0.55;
  // political: false → 멀리서도 정치 색 지도 대신 자연 지형·깊은 바다를 비스듬히 본다(게임 지도). farTilt = 가장 멀리서의 기울기(도)
  var POLITICAL = opts.political !== false, FAR_TILT = opts.farTilt != null ? opts.farTilt : (POLITICAL ? 3 : 34);
  var WX = Math.round(100 * S), WZ = Math.round(62 * S), CELL = 0.25, FW = Math.round(2 * WX / CELL), FH = Math.round(2 * WZ / CELL);
  var GROUND_Y = 0.12, QUAY_TOP = 0.2;
  var DMIN = 1.6, DMAX = Math.round(190 * S);
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
    outback:   { c: [0.71, 0.61, 0.42], forest: 0.05 },
    island:    { c: [0.42, 0.63, 0.34], forest: 0.5 }
  };
  NATIONS.forEach(function (n) { n.b = BIOMES.indexOf(n.biome); n.x *= S; n.z *= S; n.r *= S; });
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
  var N = NATIONS.length, BDV = new Float32Array(FW * FH), FLD = new Float32Array(FW * FH), F = new Float32Array(FW * FH), ID = new Int8Array(FW * FH), HG = new Float32Array(FW * FH), FOR = new Float32Array(FW * FH), CON = new Uint8Array(FW * FH);
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
        var xd = x / S, zd = z / S; // 모양을 만드는 잡음은 처음 크기 좌표로 계산해서 비율이 바뀌어도 모양이 같다
        var n1 = fbm3(xd * 0.045 + 3, zd * 0.045 + 9, 1), n2 = fbm3(xd * 0.045 + 21, zd * 0.045 + 2, 2);
        var wx = x + (fbm3(xd * 0.028 + 40, zd * 0.028 + 13, 13) - 0.5) * 22 * S, wz = z + (fbm3(xd * 0.028 - 31, zd * 0.028 + 60, 14) - 0.5) * 22 * S;
        var best = 1e9, best2 = 1e9, bi = 0, bi2 = 0, k;
        for (k = 0; k < N; k++) { var dx = wx - NATIONS[k].x, dz = wz - NATIONS[k].z; var d = Math.sqrt(dx * dx + dz * dz) / NATIONS[k].r + ((n1 - 0.5) * COS[k] + (n2 - 0.5) * SIN[k]) * 0.55; dn[k] = d; if (d < best) { best2 = best; bi2 = bi; best = d; bi = k; } else if (d < best2) { best2 = d; bi2 = k; } }
        // 국경까지 거리(부호 있음): 두 나라 사이에서 정확히 0을 지나므로 확대해도 국경선이 끊기지 않는다
        BDV[idx] = clamp((best2 - best) / 0.12, 0, 1) * (bi < bi2 ? 1 : -1);
        var land = 1 - best;
        for (k = 0; k < BR.length; k++) { var b = BR[k], ex = b[2] - b[0], ez = b[3] - b[1], tt = clamp(((wx - b[0]) * ex + (wz - b[1]) * ez) / (ex * ex + ez * ez), 0.2, 0.8), qx = wx - b[0] - ex * tt, qz = wz - b[1] - ez * tt; land = Math.max(land, 1 - Math.sqrt(qx * qx + qz * qz) / b[4] - 0.25); }
        var isl = (fbm3(xd * 0.07 + 100, zd * 0.07, 15) - 0.69) * 4 - Math.max(0, best - 1.9) * 3; land = Math.max(land, isl);
        var f = land + (fbm3(xd * 0.11, zd * 0.11, 3) - 0.5) * 0.5 + (vnoise(xd * 0.4 + 7, zd * 0.4, 5) - 0.5) * 0.04;
        f -= sstep(WX - 14 * S, WX - 3 * S, Math.abs(x)) * 1.5 + sstep(WZ - 12 * S, WZ - 3 * S, Math.abs(z)) * 1.5;
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
          var r = fbm3(xd * 0.085 + 50, zd * 0.085 - 20, 4), ridge = 1 - Math.abs(2 * r - 1); ridge = ridge * ridge * ridge;
          var hills = fbm3(xd * 0.25, zd * 0.25, 6);
          h = 0.04 + sstep(0, 0.35, f) * 0.2 + mnt * ridge * 2.4 * sstep(0.05, 0.45, f) + (hills - 0.5) * 0.2 * (0.4 + mnt);
          h = Math.min(Math.max(h, Math.min(0.03, f * 3.2)), f * 3.2); // 해안에서 높이가 0부터 이어지게(끊기면 해안선이 톱니가 됨)
          // 자연색
          c = [0, 0, 0]; for (k = 0; k < BIOMES.length; k++) { var bc = BIO[BIOMES[k]].c; c[0] += bc[0] * bAmt[k]; c[1] += bc[1] * bAmt[k]; c[2] += bc[2] * bAmt[k]; }
          var pl = bAmt[1];
          FLD[idx] = sstep(0.3, 0.75, pl) * 0.8;
          if (bAmt[3] > 0.05) { var s = Math.sin(x * 0.9 + z * 0.4 + fbm3(x * 0.2, z * 0.2, 8) * 6); var m = 1 + s * 0.06 * bAmt[3]; c = [c[0] * m, c[1] * m, c[2] * m]; }
          if (bAmt[4] > 0.05) c = mixc(c, [0.14, 0.36, 0.15], bAmt[4] * sstep(0.45, 0.6, fbm3(xd * 0.3, zd * 0.3, 9)) * 0.6);
          if (bAmt[5] > 0.05) c = mixc(c, [0.58, 0.48, 0.34], bAmt[5] * sstep(0.55, 0.72, vnoise(x * 1.3, z * 1.3, 10)) * 0.6);
          var patch = sstep(0.4, 0.58, fbm3(xd * 0.3 + 11, zd * 0.3 + 7, 11));
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

  // ───────────────────────── 강 (산에서 바다까지 흐르고, 골짜기를 판다) ─────────────────────────
  // RD = 물가까지 거리(물 위는 음수), RSF = 그 자리 물 높이. 마을·집·풍경은 RD로 강을 피하고, 길은 다리처럼 물 위로 올라간다.
  var RD = new Float32Array(FW * FH).fill(9), RSF = new Float32Array(FW * FH), RIVERS = [];
  (function makeRivers() {
    // 흐름 지형: 넓게 흐린 높이 + 땅 깊이(바다 쪽으로 갈수록 낮아짐) → 웅덩이에 갇히지 않고 바다로 간다
    var B = new Float32Array(HG), T = new Float32Array(FW * FH), K = 4, i, j, k, a;
    for (var pass = 0; pass < 2; pass++) {
      for (j = 0; j < FH; j++) { a = 0; for (i = -K; i <= K; i++) a += B[j * FW + clamp(i, 0, FW - 1)]; for (i = 0; i < FW; i++) { T[j * FW + i] = a / (2 * K + 1); a += B[j * FW + clamp(i + K + 1, 0, FW - 1)] - B[j * FW + clamp(i - K, 0, FW - 1)]; } }
      for (i = 0; i < FW; i++) { a = 0; for (j = -K; j <= K; j++) a += T[clamp(j, 0, FH - 1) * FW + i]; for (j = 0; j < FH; j++) { B[j * FW + i] = a / (2 * K + 1); a += T[clamp(j + K + 1, 0, FH - 1) * FW + i] - T[clamp(j - K, 0, FH - 1) * FW + i]; } }
    }
    function flow(x, z) { return sampleArr(B, x, z) + Math.max(0, landAt(x, z)) * 1.1; }
    function nearPort(x, z, d) { for (var q = 0; q < NATIONS.length; q++) if (Math.hypot(NATIONS[q].port.x - x, NATIONS[q].port.z - z) < d) return true; return false; }
    var r = rng32(9001), srcs = [], STEP = 0.3;
    for (var t = 0; t < 60000 && srcs.length < 26; t++) {
      var x = (r() * 2 - 1) * WX, z = (r() * 2 - 1) * WZ, f = landAt(x, z), h = heightAt(x, z);
      if (f < 0.22 || h < 0.5 || h > 1.5 || nearPort(x, z, 6)) continue;
      var ok = true; for (k = 0; k < srcs.length; k++) if (Math.hypot(srcs[k][0] - x, srcs[k][1] - z) < 8 * S + 3) { ok = false; break; } if (!ok) continue;
      srcs.push([x, z]);
    }
    var taken = new Set();
    function trace(src, si) {
      var x = src[0], z = src[1], pts = [[x, z]], dirA = null, seen = new Set(), done = false, joined = false;
      for (var st = 0; st < 700; st++) {
        var best = 1e9, bx = 0, bz = 0, ba = 0;
        for (var q = 0; q < 16; q++) {
          var aa = q / 16 * Math.PI * 2; if (dirA !== null && Math.cos(aa - dirA) < 0.1) continue;
          var nx = x + Math.cos(aa) * STEP, nz = z + Math.sin(aa) * STEP, key = Math.floor(nx / 0.25) + ',' + Math.floor(nz / 0.25);
          if (seen.has(key)) continue;
          var sc = flow(nx, nz) + (dirA !== null ? (1 - Math.cos(aa - dirA)) * 0.012 : 0) + (vnoise(nx * 0.9, nz * 0.9, 77 + si) - 0.5) * 0.03 + (nearPort(nx, nz, 3.6) ? 5 : 0);
          if (sc < best) { best = sc; bx = nx; bz = nz; ba = aa; }
        }
        if (best > 4 || Math.abs(bx) > WX - 1 || Math.abs(bz) > WZ - 1) break;
        seen.add(Math.floor(x / 0.25) + ',' + Math.floor(z / 0.25));
        x = bx; z = bz; dirA = ba; pts.push([x, z]);
        if (landAt(x, z) < -0.04) { done = true; break; }
        if (taken.has(Math.floor(x / 0.5) + ',' + Math.floor(z / 0.5)) && pts.length > 4) { done = true; joined = true; break; }
      }
      if (!done || pts.length < (joined ? 10 : 14)) return false; // 세계가 작아 강도 짧다(14걸음 ≈ 4칸 이상만)
      // 부드럽게(Chaikin 2번)
      for (var it = 0; it < 2; it++) { var sm = [pts[0]]; for (k = 0; k < pts.length - 1; k++) { var p0 = pts[k], p1 = pts[k + 1]; sm.push([p0[0] * 0.75 + p1[0] * 0.25, p0[1] * 0.75 + p1[1] * 0.25], [p0[0] * 0.25 + p1[0] * 0.75, p0[1] * 0.25 + p1[1] * 0.75]); } sm.push(pts[pts.length - 1]); pts = sm; }
      pts.forEach(function (pp) { taken.add(Math.floor(pp[0] / 0.5) + ',' + Math.floor(pp[1] / 0.5)); });
      // 물 높이는 하류로 갈수록 내려가기만 한다. 폭은 하류로 갈수록 넓어진다
      var n = pts.length, surf = [], wid = [], sv = heightAt(pts[0][0], pts[0][1]) - 0.01;
      for (k = 0; k < n; k++) { sv = Math.max(0.004, Math.min(sv, heightAt(pts[k][0], pts[k][1]) - 0.004)); if (landAt(pts[k][0], pts[k][1]) < 0) sv = Math.min(sv, 0.004); surf.push(sv); wid.push(lerp(0.035, 0.11, Math.pow(k / (n - 1), 0.8))); }
      // 하구: 바다에 가까울수록 넓어지고(삼각강), 물 높이가 바다 밑으로 내려가 바다 물에 자연스럽게 섞인다
      var mouth = [], fade = [], low = 1e9;
      for (k = 0; k < n; k++) { var m = 1 - sstep(0.0, 0.06, landAt(pts[k][0], pts[k][1])); mouth.push(m); wid[k] *= 1 + 1.3 * m * m; low = Math.min(low, lerp(surf[k], -0.008, m)); surf[k] = low; fade.push(1 - sstep(0.3, 0.9, m)); }
      RIVERS.push({ pts: pts, surf: surf, wid: wid, mouth: mouth, fade: fade, ni: nationAt(src[0], src[1]) }); return true;
    }
    srcs.forEach(trace);
    // 강이 하나도 없는 나라(평야·사막)는 나라 안쪽 높은 곳 몇 군데에서 다시 시도한다
    NATIONS.forEach(function (n, ni) {
      if (RIVERS.some(function (rv) { return rv.ni === ni; })) return;
      var cands = [];
      for (var t = 0; t < 3000; t++) { var x = n.cx + (r() * 2 - 1) * n.r, z = n.cz + (r() * 2 - 1) * n.r, f = landAt(x, z); if (f < 0.25 || nationAt(x, z) !== ni || nearPort(x, z, 5)) continue; cands.push([x, z, heightAt(x, z) + f * 0.4]); }
      cands.sort(function (a, b) { return b[2] - a[2]; });
      for (var c = 0, tried = 0; c < cands.length && tried < 8; c += 37) { tried++; if (trace(cands[c], 50 + ni * 10 + tried)) break; }
    });
    // 골짜기 파기 + 물가 칠하기 + 숲·밭 치우기
    RIVERS.forEach(function (rv) {
      var pts = rv.pts;
      for (var k = 0; k < pts.length; k++) {
        var px = pts[k][0], pz = pts[k][1], w = rv.wid[k], sv = rv.surf[k], mo = rv.mouth[k], Rc = w + 0.75, c = Math.ceil(Rc / CELL), i0 = Math.floor((px + WX) / CELL), j0 = Math.floor((pz + WZ) / CELL);
        for (var dj = -c; dj <= c; dj++) for (var di = -c; di <= c; di++) {
          var ii = i0 + di, jj = j0 + dj; if (ii < 0 || jj < 0 || ii >= FW || jj >= FH) continue;
          var idx = jj * FW + ii, cx = -WX + (ii + 0.5) * CELL, cz = -WZ + (jj + 0.5) * CELL, d = Math.hypot(cx - px, cz - pz); if (d > Rc) continue;
          var edge = d - w;
          if (edge < RD[idx]) { RD[idx] = edge; RSF[idx] = sv; }
          var bed = sv - 0.018, tgt = lerp(bed, HG[idx], sstep(w + 0.3, Rc, d)); if (mo > 0) tgt = Math.min(tgt, lerp(HG[idx], -0.03, mo * (1 - sstep(w * 0.6, w + 0.2, d)))); if (tgt < HG[idx]) HG[idx] = tgt;
          if (HG[idx] < 0.002 && F[idx] > 0) RD[idx] = Math.min(RD[idx], -0.01); // 하구 물길(바다 높이 아래)도 물로 친다
          if (F[idx] <= 0) continue;
          var o = idx * 4, wet = 1 - sstep(w - 0.02, w + 0.12, d), bank = (1 - sstep(w + 0.1, w + 0.32, d)) * (1 - wet);
          if (wet > 0) { natData[o] = lerp(natData[o], 0.3 * 255, wet * 0.6); natData[o + 1] = lerp(natData[o + 1], 0.42 * 255, wet * 0.6); natData[o + 2] = lerp(natData[o + 2], 0.4 * 255, wet * 0.6); }
          if (bank > 0) { natData[o] = lerp(natData[o], 0.6 * 255, bank * 0.18); natData[o + 1] = lerp(natData[o + 1], 0.58 * 255, bank * 0.18); natData[o + 2] = lerp(natData[o + 2], 0.42 * 255, bank * 0.18); }
          if (edge < 0.15) FOR[idx] = 0; if (edge < 0.3) FLD[idx] = 0;
        }
      }
    });
  })();
  function riverAt(x, z, pad) { return RD[cellIdx(x, z)] < (pad || 0); }

  // ───────────────────────── 도시·마을 (수도 1곳 + 마을 2~3곳, 길, 밭) ─────────────────────────
  var STYLES = {
    temperate: { walls: ['#e9d9b8', '#dcc49a', '#efe0c2', '#d6b98e', '#e4cfa6'], roofs: ['#b8532f', '#a2452b', '#c46a3d', '#8a4a32', '#7a5a48'], house: 'gable', farm: [[0.86, 0.74, 0.36], [0.55, 0.67, 0.3], [0.67, 0.53, 0.34], [0.47, 0.6, 0.28]], farmW: 2.6 },
    plains:    { walls: ['#e8d6b0', '#d9bf93', '#c98c5c', '#ead9b6'], roofs: ['#8a4a32', '#a2452b', '#6e4a38'], house: 'gable', farm: [[0.86, 0.74, 0.36], [0.55, 0.67, 0.3], [0.67, 0.53, 0.34], [0.93, 0.84, 0.52]], farmW: 3.2 },
    boreal:    { walls: ['#8a6446', '#9b7656', '#76543c', '#c9b294'], roofs: ['#4d5a4c', '#5a4e44', '#6b5a48'], house: 'gable', farm: [[0.5, 0.6, 0.35], [0.62, 0.66, 0.4]], farmW: 1.4 },
    desert:    { walls: ['#e8d5ae', '#ddc597', '#f0e2c4', '#d6b98a'], roofs: ['#e8d5ae'], house: 'flat', farm: [[0.42, 0.58, 0.27], [0.52, 0.64, 0.3]], farmW: 1.1 },
    tropical:  { walls: ['#efc3a2', '#eed58f', '#9fd1bd', '#efe3c8', '#c3d99a'], roofs: ['#c96a3d', '#b5523b', '#d9a066'], house: 'gable', hut: true, farm: [[0.2, 0.42, 0.18], [0.3, 0.5, 0.22], [0.55, 0.62, 0.3]], farmW: 2.0 },
    outback:   { walls: ['#f1e6d6', '#e2c9a6', '#d8b48c'], roofs: ['#8e938f', '#a08a6c', '#7f7466'], house: 'gable', farm: null, farmW: 0 },
    island:    { walls: ['#ffffff', '#f4f6f7', '#eaf2f8'], roofs: ['#2e86c1', '#3498db', '#1f618d'], house: 'flat', farm: [[0.5, 0.66, 0.34], [0.62, 0.7, 0.4]], farmW: 1.2 }
  };
  var MODERN = { Technia: 1, Novia: 0.9, Oilia: 0.75, Mechania: 0.6, Grainia: 0.2, Mineria: 0.3, Ferria: 0.15, Tropia: 0.3, Agrea: 0.25 };
  var GLASS = ['#7fb3d5', '#a9cce3', '#85929e', '#d6eaf8', '#5d6d7e', '#aab7b8'];
  var BLD = { wall: [], roof: [], dome: [], cone: [], cyl: [] }, ROADS = [], SETTLE = [];
  function farFromSettle(x, z, gap) { for (var k = 0; k < SETTLE.length; k++) { var s = SETTLE[k]; if (Math.hypot(x - s.x, z - s.z) < s.R + gap) return false; } return true; }
  function siteOK(x, z, R, loose) {
    if (landAt(x, z) < 0.1 || riverAt(x, z, R * 0.8)) return false; var h0 = heightAt(x, z); if (h0 > (loose ? 0.9 : 0.5)) return false;
    for (var a = 0; a < 8; a++) { var px = x + Math.cos(a * 0.785) * R, pz = z + Math.sin(a * 0.785) * R; if (landAt(px, pz) < 0.03 || Math.abs(heightAt(px, pz) - h0) > (loose ? 0.6 : 0.4)) return false; }
    return true;
  }
  NATIONS.forEach(function (n) {
    var r = rng32(n.i * 31337 + 3), best = null, bs = 1e9, big = n.cells > 9000 * S * S, R = clamp(n.r * 0.16, 1.2, 2.4), t, x, z;
    // 항구 도시: 부두 바로 뒤. 격자 길·빽빽한 집·창고만 있고 밭은 없다
    var pR = big ? 1.1 : 0.9; SETTLE.push({ n: n, x: n.port.x - n.port.sx * (0.3 + pR), z: n.port.z - n.port.sz * (0.3 + pR), R: pR, capital: false, port: true, portAng: Math.atan2(n.port.sz, n.port.sx) });
    for (var relax = 1; relax >= 0.2 && !best; relax -= 0.4) {
      for (t = 0; t < 3000; t++) {
        x = n.cx + (r() * 2 - 1) * n.r * 0.75; z = n.cz + (r() * 2 - 1) * n.r * 0.75;
        if (nationAt(x, z) !== n.i || !siteOK(x, z, R * (relax < 1 ? 0.8 : 1), relax < 1)) continue;
        var dp = Math.hypot(x - n.port.x, z - n.port.z); if (dp < (R + 3 + 1.5 * S) * relax) continue;
        var sc = Math.hypot(x - n.cx, z - n.cz) + heightAt(x, z) * 6 + Math.max(0, dp - 14 * S) * 0.3;
        if (sc < bs) { bs = sc; best = [x, z]; }
      }
    }
    if (best) SETTLE.push({ n: n, x: best[0], z: best[1], R: R, capital: true });
    var want = big ? 3 : 2, made = 0;
    for (t = 0; t < 9000 && made < want; t++) {
      var rl = t < 5000 ? 1 : t < 7000 ? 0.7 : 0.45; // 작은 나라는 마을 간격을 조금씩 줄여서 찾는다
      x = n.cx + (r() * 2 - 1) * n.r * 1.1; z = n.cz + (r() * 2 - 1) * n.r * 1.1;
      var tr = (0.85 + r() * 0.4) * (rl < 1 ? 0.8 : 1);
      if (nationAt(x, z) !== n.i || !siteOK(x, z, tr, rl < 1) || !farFromSettle(x, z, (3.5 + 2 * S) * rl) || Math.hypot(x - n.port.x, z - n.port.z) < (3.5 + 1.5 * S) * rl) continue;
      SETTLE.push({ n: n, x: x, z: z, R: tr, capital: false }); made++;
    }
  });
  // 길: 수도↔항구, 마을↔가장 가까운 수도·항구·마을(같은 나라)
  function clearForest(x, z, rad) { var c = Math.ceil(rad / CELL); var i0 = Math.floor((x + WX) / CELL), j0 = Math.floor((z + WZ) / CELL); for (var dj = -c; dj <= c; dj++) for (var di = -c; di <= c; di++) { var i = i0 + di, j = j0 + dj; if (i >= 0 && j >= 0 && i < FW && j < FH) FOR[j * FW + i] = 0; } }
  function makeRoad(ax, az, bx, bz, w, seed) {
    var L = Math.hypot(bx - ax, bz - az); if (L < 0.3) return false;
    var cnt = Math.max(2, Math.ceil(L / 0.3)), px = -(bz - az) / L, pz = (bx - ax) / L, pts = [];
    for (var i = 0; i <= cnt; i++) {
      var t = i / cnt, wob = Math.sin(t * Math.PI) * (vnoise(t * 3, seed, 21) - 0.5) * Math.min(L * 0.1, 0.9);
      var x = ax + (bx - ax) * t + px * wob, z = az + (bz - az) * t + pz * wob;
      if (landAt(x, z) < 0.015) return false;
      pts.push([x, z]);
    }
    pts.forEach(function (p) { clearForest(p[0], p[1], 0.3); });
    ROADS.push({ pts: pts, w: w }); return true;
  }
  NATIONS.forEach(function (n) {
    var mine = SETTLE.filter(function (s) { return s.n === n; }), cap = mine.filter(function (s) { return s.capital; })[0], ptown = mine.filter(function (s) { return s.port; })[0], pq = ptown ? { x: ptown.x, z: ptown.z } : { x: n.port.x - n.port.sx * 0.75, z: n.port.z - n.port.sz * 0.75 };
    var nodes = [pq]; if (cap) { if (!makeRoad(cap.x, cap.z, pq.x, pq.z, 0.075, n.i * 10)) cap.noRoad = true; nodes.push(cap); }
    mine.forEach(function (s, k) {
      if (s.capital || s.port) return;
      var order = nodes.slice().sort(function (a, b) { return Math.hypot(a.x - s.x, a.z - s.z) - Math.hypot(b.x - s.x, b.z - s.z); });
      for (var q = 0; q < order.length; q++) if (makeRoad(s.x, s.z, order[q].x, order[q].z, 0.06, n.i * 10 + k + 1)) break;
      if (q === order.length) s.noRoad = true; else s.roadAng = Math.atan2(order[q].z - s.z, order[q].x - s.x); // 마을 큰길을 이 길과 한 줄로 잇는다
      nodes.push(s);
    });
  });
  // 도시 바닥·밭을 자연색 텍스처에 칠하고 숲을 치운다
  SETTLE.forEach(function (s, si) {
    var st = STYLES[s.n.biome], farm = st.farm && !s.port ? s.R + st.farmW * (s.capital ? 1.2 : 0.8) : s.R, ang = si * 0.7, ca = Math.cos(ang), sa = Math.sin(ang);
    var c = Math.ceil(farm / CELL), i0 = Math.floor((s.x + WX) / CELL), j0 = Math.floor((s.z + WZ) / CELL);
    for (var dj = -c; dj <= c; dj++) for (var di = -c; di <= c; di++) {
      var i = i0 + di, j = j0 + dj; if (i < 0 || j < 0 || i >= FW || j >= FH) continue;
      var idx = j * FW + i; if (F[idx] <= 0.02) continue;
      var dx = di * CELL, dz = dj * CELL, d = Math.hypot(dx, dz) + (vnoise(i * 0.3, j * 0.3, 30 + si) - 0.5) * 0.8; if (d > farm) continue;
      var o = idx * 4, col, w;
      if (d < s.R * 0.95) { col = s.port ? [0.6, 0.57, 0.52] : [0.64, 0.61, 0.55]; w = s.port || s.capital ? 0.72 : 0.6; FOR[idx] = 0; }
      else {
        if (!st.farm) continue; FLD[idx] = Math.max(FLD[idx], 0.85 * (1 - sstep(farm - 0.9, farm, d))); FOR[idx] *= 0.15; continue;
      }
      natData[o] = lerp(natData[o], col[0] * 255, w); natData[o + 1] = lerp(natData[o + 1], col[1] * 255, w); natData[o + 2] = lerp(natData[o + 2], col[2] * 255, w);
    }
  });
  // 도시 안에는 밭 무늬가 없게(다른 마을의 밭 테두리가 겹쳐도 지운다), 항구 도시는 둘레도 조금 비운다
  SETTLE.forEach(function (s) {
    var rr = s.R * (s.port ? 1.25 : 1.02), c = Math.ceil(rr / CELL), i0 = Math.floor((s.x + WX) / CELL), j0 = Math.floor((s.z + WZ) / CELL);
    for (var dj = -c; dj <= c; dj++) for (var di = -c; di <= c; di++) {
      var i = i0 + di, j = j0 + dj; if (i < 0 || j < 0 || i >= FW || j >= FH) continue;
      var idx = j * FW + i, d = Math.hypot(di * CELL, dj * CELL); if (d > rr) continue;
      FLD[idx] = Math.min(FLD[idx], sstep(s.R * 0.92, rr, d)); if (s.port) FOR[idx] *= sstep(s.R, rr, d);
    }
  });
  // 건물 목록 (x, y, z, 너비, 높이, 깊이, 회전, r, g, b)
  function pick(a, r) { return a[Math.floor(r() * a.length)]; }
  function addB(type, x, y, z, sx, sy, sz, ry, col) { var c = Array.isArray(col) ? col : hexRGB(col); BLD[type].push(x, y, z, sx, sy, sz, ry, c[0], c[1], c[2]); }
  // 집: 종류(HV) 0 오두막(박공) 1 2층 목조 주택 2 ㄱ자 집 3 모임지붕 4 평지붕 5 유리 빌딩 6 둥근 초가
  // 벽·지붕 색은 집마다 따로, 창문·문·목재 무늬는 셰이더가 실제 크기에 맞춰 그린다. HSINK = 땅에 묻는 깊이(비탈에서 틈이 안 보이게)
  var HOUSES = [], HSINK = 0.015;
  function addH(v, x, y, z, w, h, d, ry, wall, roof) { HOUSES.push({ v: v, x: x, y: y, z: z, w: w, h: h, d: d, ry: ry, wall: Array.isArray(wall) ? wall : hexRGB(wall), roof: Array.isArray(roof) ? roof : hexRGB(roof) }); }
  function house(st, x, z, ry, r, capital) {
    var y = heightAt(x, z) - HSINK, w = 0.07 + r() * 0.04, d = 0.06 + r() * 0.035, h = 0.035 + r() * 0.03 + HSINK, wall = pick(st.walls, r), roof = pick(st.roofs, r);
    if (st.hut && !capital && r() < 0.75) { addH(6, x, y, z, w, h, w, r() * 6.283, wall, [0.72, 0.6, 0.38]); return; }
    if (st.house === 'gable') { var q = r(), v = q < 0.14 ? 2 : q < 0.3 ? 3 : (capital ? q < 0.62 : q < 0.4) ? 1 : 0; addH(v, x, y, z, w, v === 1 ? h * 0.72 : h, d, ry, wall, roof); }
    else { addH(4, x, y, z, w, h + 0.01, d, ry, wall, roof); if (r() < 0.15) addB('dome', x, y + h + 0.01, z, w * 0.3, w * 0.3, w * 0.3, 0, [0.96, 0.95, 0.92]); }
  }
  SETTLE.forEach(function (s, si) {
    var r = rng32(si * 7907 + 11), st = STYLES[s.n.biome], mod = MODERN[s.n.key] || 0.2, h0 = heightAt(s.x, s.z), ang = s.port ? (r(), s.portAng) : s.roadAng != null ? (r(), s.roadAng) : r() * Math.PI, ca = Math.cos(ang), sa = Math.sin(ang), nc = hexRGB(s.n.color);
    s.ang = ang;
    if (s.capital) {
      var P = 0.15, nn = Math.ceil(s.R / P);
      for (var i = -nn; i <= nn; i++) for (var j = -nn; j <= nn; j++) {
        if (i % 5 === 0 || j % 5 === 0) continue;
        var lx = i * P + (r() - 0.5) * 0.03, lz = j * P + (r() - 0.5) * 0.03, d = Math.hypot(lx, lz) / s.R;
        if (d > 1 || d < (USE_MODELS ? 0.3 : 0.13) || r() > 1 - d * d * 0.75) continue;
        var x = s.x + lx * ca - lz * sa, z = s.z + lx * sa + lz * ca;
        if (landAt(x, z) < 0.03 || riverAt(x, z, 0.06) || Math.abs(heightAt(x, z) - h0) > 0.4) continue;
        var y = heightAt(x, z) - 0.03;
        if (d < 0.45 && r() < mod * (1 - d * 1.6)) { var tw = 0.08 + r() * 0.05, th = (0.18 + r() * 0.45) * mod * (1 - d) + 0.14; addH(5, x, y, z, tw, th, tw, ang, pick(GLASS, r), [0.92, 0.94, 0.96]); }
        else if (d < 0.6 && r() < 0.4) { var fw = 0.1 + r() * 0.04, fd = 0.09 + r() * 0.03; if (st.house === 'gable') addH(1, x, y + 0.03 - HSINK, z, fw, 0.06 + r() * 0.025, fd, ang, pick(st.walls, r), pick(st.roofs, r)); else addH(4, x, y + 0.03 - HSINK, z, fw, 0.1 + r() * 0.05, fd, ang, pick(st.walls, r), pick(st.roofs, r)); }
        else house(st, x, z, ang + (r() < 0.5 ? 0 : Math.PI / 2), r, true);
      }
      // 시청(지붕이 나라 색) + 깃발
      if (!USE_MODELS) { addB('wall', s.x, h0 - 0.03, s.z, 0.26, 0.15, 0.2, ang, [0.96, 0.94, 0.88]); addB('dome', s.x, h0 + 0.12, s.z, 0.08, 0.08, 0.08, 0, nc); }
      var fo = USE_MODELS ? 0.36 : 0.2, fx = s.x + fo * ca, fz = s.z + fo * sa; addB('cyl', fx, h0, fz, 0.005, 0.32, 0.005, 0, [0.35, 0.35, 0.35]); addB('wall', fx + 0.035, h0 + 0.26, fz, 0.07, 0.045, 0.005, 0, nc);
      ROADS.push({ pts: [[s.x - s.R * ca, s.z - s.R * sa], [s.x + s.R * ca, s.z + s.R * sa]], w: 0.1 }); ROADS.push({ pts: [[s.x + s.R * sa, s.z - s.R * ca], [s.x - s.R * sa, s.z + s.R * ca]], w: 0.1 });
      ROADS.push({ disc: [s.x, s.z, 0.34] });
    } else if (s.port) {
      // 로컬 x축 = 바다 쪽. 4칸마다 길, 길 사이에 집이 빽빽하고 바다 쪽 줄은 창고
      var P2 = 0.13, n2 = Math.ceil(s.R / P2);
      for (var i2 = -n2; i2 <= n2; i2++) for (var j2 = -n2; j2 <= n2; j2++) {
        if (i2 % 4 === 0 || j2 % 4 === 0) continue;
        var lx2 = i2 * P2, lz2 = j2 * P2, d2 = Math.hypot(lx2, lz2) / s.R;
        if (d2 > 1 || r() > 1.1 - d2 * d2 * 0.45) continue;
        if (USE_MODELS && Math.hypot(lx2, lz2) < 0.22) continue;
        var x3 = s.x + lx2 * ca - lz2 * sa, z3 = s.z + lx2 * sa + lz2 * ca;
        if (landAt(x3, z3) < 0.03 || riverAt(x3, z3, 0.06) || Math.abs(heightAt(x3, z3) - h0) > 0.4) continue;
        if (lx2 > s.R * 0.4 && r() < 0.75) addH(4, x3, heightAt(x3, z3) - HSINK, z3, 0.11 + r() * 0.025, 0.045 + r() * 0.015 + HSINK, 0.085, ang, ['#c9c2b4', '#b8b0a2', '#d6cfc0', '#a8604a'][Math.floor(r() * 4)], '#8a8f94');
        else house(st, x3, z3, ang + (r() < 0.5 ? 0 : Math.PI / 2), r, true);
      }
      for (var g2 = -n2; g2 <= n2; g2++) {
        if (g2 % 4) continue; var c2 = g2 * P2; if (Math.abs(c2) >= s.R * 0.98) continue; var hl = Math.sqrt(s.R * s.R - c2 * c2);
        ROADS.push({ pts: [[s.x - hl * ca - c2 * sa, s.z - hl * sa + c2 * ca], [s.x + hl * ca - c2 * sa, s.z + hl * sa + c2 * ca]], w: 0.055 });
        ROADS.push({ pts: [[s.x + c2 * ca + hl * sa, s.z + c2 * sa - hl * ca], [s.x + c2 * ca - hl * sa, s.z + c2 * sa + hl * ca]], w: 0.055 });
      }
      ROADS.push({ pts: [[s.x, s.z], [s.n.port.x - s.n.port.sx * 0.1, s.n.port.z - s.n.port.sz * 0.1]], w: 0.075 });
    } else {
      var cnt = Math.round(22 + s.R * 38);
      for (var k = 0; k < cnt * 3 && cnt > 0; k++) {
        var onStreet = r() < 0.55, rad = s.R * Math.sqrt(r()), a2 = r() * Math.PI * 2, ox, oz;
        if (onStreet) { var along = (r() * 1.7 - 0.7) * s.R, side = (r() < 0.5 ? -1 : 1) * (0.09 + r() * 0.05); ox = along * ca - side * sa; oz = along * sa + side * ca; }
        else { ox = Math.cos(a2) * rad; oz = Math.sin(a2) * rad; if (Math.hypot(ox, oz) < 0.12) continue; }
        if (USE_MODELS && Math.hypot(ox, oz) < 0.2) continue; // 가운데는 마을 모델 자리
        var x2 = s.x + ox, z2 = s.z + oz; if (landAt(x2, z2) < 0.03 || riverAt(x2, z2, 0.06) || Math.abs(heightAt(x2, z2) - h0) > 0.35) continue;
        house(st, x2, z2, onStreet ? ang : r() * Math.PI, r, false); cnt--;
      }
      if (!USE_MODELS) { addB('wall', s.x, h0 - 0.03, s.z, 0.12, 0.1, 0.1, ang, [0.95, 0.93, 0.88]); addB('roof', s.x, h0 + 0.07, s.z, 0.13, 0.06, 0.11, ang, nc); }
      // 큰길: 바깥 길 쪽(+)으로는 그 길과 이어지고, 반대쪽은 마을 끝 집에서 멈춘다(들판 한가운데서 끊기지 않게)
      ROADS.push({ pts: [[s.x - s.R * 0.7 * ca, s.z - s.R * 0.7 * sa], [s.x + s.R * ca, s.z + s.R * sa]], w: 0.07 });
    }
  });
  // 농가: 밭 사이 곳곳에 살림집 + 헛간(빈 들판을 채운다)
  var FARMS = [];
  SETTLE.forEach(function (s, si) {
    var st = STYLES[s.n.biome]; if (!st.farm || s.port) return;
    var r = rng32(si * 6007 + 29), farR = s.R + st.farmW * (s.capital ? 1.2 : 0.8), want = Math.round((s.capital ? 7 : 4) * Math.min(1.4, st.farmW / 2)), h0 = heightAt(s.x, s.z);
    for (var t = 0, k = 0; t < 200 && k < want; t++) {
      var a = r() * Math.PI * 2, d = lerp(s.R + 0.4, farR - 0.15, r()), x = s.x + Math.cos(a) * d, z = s.z + Math.sin(a) * d;
      if (landAt(x, z) < 0.06 || riverAt(x, z, 0.3) || Math.abs(heightAt(x, z) - h0) > 0.5 || !farFromSettle(x, z, 0.25)) continue;
      var ok = true; for (var q = 0; q < FARMS.length; q++) if (Math.hypot(FARMS[q].x - x, FARMS[q].z - z) < 0.7) { ok = false; break; } if (!ok) continue;
      var ry = r() * Math.PI, c = Math.cos(ry), sn = Math.sin(ry), bx2 = x + 0.13 * c, bz2 = z - 0.13 * sn;
      if (st.house === 'gable') {
        addH(r() < 0.5 ? 2 : 0, x, heightAt(x, z) - HSINK, z, 0.08 + r() * 0.02, 0.05 + HSINK, 0.065, ry, pick(st.walls, r), pick(st.roofs, r));
        addH(0, bx2, heightAt(bx2, bz2) - HSINK, bz2, 0.07, 0.055 + HSINK, 0.13, ry, ['#9c4a32', '#8a6a4a', '#7b5a43'][Math.floor(r() * 3)], '#5b4a3f');
      } else {
        addH(4, x, heightAt(x, z) - HSINK, z, 0.08, 0.05 + HSINK, 0.07, ry, pick(st.walls, r), pick(st.roofs, r));
        addH(4, bx2, heightAt(bx2, bz2) - HSINK, bz2, 0.07, 0.04 + HSINK, 0.1, ry, pick(st.walls, r), pick(st.roofs, r));
      }
      for (var cj = -2; cj <= 2; cj++) for (var ci = -2; ci <= 2; ci++) FOR[cellIdx(x + ci * CELL * 0.5, z + cj * CELL * 0.5)] = 0;
      FARMS.push({ x: x, z: z, ry: ry, s: s }); k++;
    }
  });

  // 공항: 나라마다 수도 근처 평평한 땅에 활주로 하나(땅을 고르고 숲을 치운다). 터미널·격납고는 집 목록에 넣는다
  var AIRPORTS = [], RWL = 1.1;
  NATIONS.forEach(function (n, ni) {
    var cap = SETTLE.filter(function (s) { return s.n === n && s.capital; })[0], r = rng32(ni * 9419 + 3), best = null, bs = 1e9;
    var cx = cap ? cap.x : n.cx, cz = cap ? cap.z : n.cz;
    for (var t = 0; t < 4000; t++) {
      var a = r() * Math.PI * 2, d = 2.2 + r() * 4.5, x = cx + Math.cos(a) * d, z = cz + Math.sin(a) * d, ry = r() * Math.PI, c = Math.cos(ry), sn = Math.sin(ry);
      if (nationAt(x, z) !== ni || landAt(x, z) < 0.12 || !farFromSettle(x, z, 0.9)) continue;
      var h0 = heightAt(x, z), ok = h0 < 0.7, k;
      for (k = -3; k <= 3 && ok; k++) { var px = x + c * RWL * k / 6, pz = z - sn * RWL * k / 6; if (landAt(px, pz) < 0.08 || riverAt(px, pz, 0.45) || Math.abs(heightAt(px, pz) - h0) > 0.14) ok = false; }
      if (!ok || Math.hypot(n.port.x - x, n.port.z - z) < 3) continue;
      for (k = 0; k < FARMS.length; k++) if (Math.hypot(FARMS[k].x - x, FARMS[k].z - z) < 0.9) { ok = false; break; } if (!ok) continue;
      var sc = d + Math.abs(heightAt(x + c * 0.5, z - sn * 0.5) - heightAt(x - c * 0.5, z + sn * 0.5)) * 20; if (sc < bs) { bs = sc; best = [x, z, ry, h0]; }
    }
    if (!best) return;
    var ap = { n: n, x: best[0], z: best[1], ry: best[2], h: Math.max(best[3], 0.03) + 0.004 }; AIRPORTS.push(ap);
    if (cap) { var ac = Math.cos(ap.ry), as = Math.sin(ap.ry); makeRoad(cap.x, cap.z, ap.x + 0.5 * as, ap.z + 0.5 * ac, 0.06, ni * 10 + 7); }
    var c0 = Math.cos(ap.ry), s0 = Math.sin(ap.ry), R2 = RWL / 2 + 0.35, cc = Math.ceil(R2 / CELL), i0 = Math.floor((ap.x + WX) / CELL), j0 = Math.floor((ap.z + WZ) / CELL);
    for (var dj = -cc; dj <= cc; dj++) for (var di = -cc; di <= cc; di++) {
      var ii = i0 + di, jj = j0 + dj; if (ii < 0 || jj < 0 || ii >= FW || jj >= FH) continue;
      var idx = jj * FW + ii, wx = -WX + (ii + 0.5) * CELL - ap.x, wz = -WZ + (jj + 0.5) * CELL - ap.z, lx = wx * c0 - wz * s0, lz = wx * s0 + wz * c0;
      var e = Math.max(Math.abs(lx) - RWL / 2, Math.max(-0.14 - lz, lz - 0.62)), w = 1 - sstep(0, 0.3, e); if (w <= 0) continue;
      HG[idx] = lerp(HG[idx], ap.h - 0.004, w); FOR[idx] = 0; FLD[idx] *= 1 - w;
      var o = idx * 4; natData[o] = lerp(natData[o], 0.52 * 255, w * 0.35); natData[o + 1] = lerp(natData[o + 1], 0.58 * 255, w * 0.35); natData[o + 2] = lerp(natData[o + 2], 0.4 * 255, w * 0.35);
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
  if (!POLITICAL) { var vign = document.createElement('div'); vign.style.cssText = 'position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse at 50% 48%, rgba(0,0,0,0) 58%, rgba(6,22,38,0.38) 100%);'; container.appendChild(vign); }
  var scene = new THREE.Scene();
  var SKY = new THREE.Color('#cfe0ea');
  if (!POLITICAL) SKY = new THREE.Color('#1b4a6b');
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
  for (var pi = 0; pi < FW * FH; pi++) { seen[pi] = polData[pi * 4 + 3] > 0 ? 1 : 0; }
  // 국경선용 텍스처: R = 부호 있는 국경 거리(0.5가 국경), G = 부호 없는 거리(진짜 국경 근처인지)
  var bdData = new Uint8Array(FW * FH * 4);
  for (pi = 0; pi < FW * FH; pi++) { var land0 = polData[pi * 4 + 3] > 0; bdData[pi * 4] = land0 ? clamp(127.5 + BDV[pi] * 127.5, 0, 255) : 255; bdData[pi * 4 + 1] = land0 ? Math.abs(BDV[pi]) * 255 : 255; bdData[pi * 4 + 3] = 255; }
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
  var natTex = dataTex(natData, true), polTex = dataTex(polData, false), polColTex = dataTex(polCol, true), bdTex = dataTex(bdData, true);
  var terrU = { uMix: { value: 1 }, uSel: { value: -1 }, uMe: { value: -1 }, uDetail: { value: 0 }, uBorder: { value: 1 }, uRelief: { value: 0 }, uPol: { value: polTex }, uPolC: { value: polColTex }, uBd: { value: bdTex }, uTexel: { value: new THREE.Vector2(1 / FW, 1 / FH) } };
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
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying vec2 vXZ;\nvarying float vY;\nvarying vec3 vNrm;').replace('#include <begin_vertex>', '#include <begin_vertex>\nvXZ = position.xz; vY = position.y; vNrm = normal;');
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', [
      '#include <common>', 'uniform float uMix; uniform float uSel; uniform float uMe; uniform float uDetail; uniform float uBorder; uniform float uRelief;', 'varying vec3 vNrm;', 'uniform sampler2D uPol; uniform sampler2D uPolC; uniform sampler2D uBd; uniform vec2 uTexel;', 'varying vec2 vXZ;', 'varying float vY;',
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
        '  vec3 rn = normalize(vec3(vNrm.x * 5.0, vNrm.y, vNrm.z * 5.0)); float hs = clamp(dot(rn, normalize(vec3(-0.55, 0.62, -0.35))), 0.0, 1.0);',
        '  diffuseColor.rgb *= mix(1.0, 0.5 + 0.75 * hs + 0.12 * smoothstep(0.6, 1.6, vY), uRelief * smoothstep(0.02, 0.15, vY));',
        '  float a0 = texture2D(uPol, vUv).a;',
        '  float land = smoothstep(-0.004, 0.02, vY);',
        '  vec3 pcol = texture2D(uPolC, vUv).rgb;',
        '  vec2 bt = texture2D(uBd, vUv).rg; float bv = bt.r * 2.0 - 1.0; float near = 1.0 - smoothstep(0.25, 0.45, bt.g);',
        '  float bd = (1.0 - smoothstep(0.0, 0.06, abs(bv))) * land * near;',
        '  float coast = 0.0;',
        '#if __VERSION__ >= 300',
        '  bd = (1.0 - smoothstep(0.0, fwidth(bv) * 1.3 + 0.0001, abs(bv))) * land * near;',
        '  coast = (1.0 - smoothstep(0.0, fwidth(vY) * 1.6 + 0.0001, vY)) * step(0.0, vY);',
        '#endif',
        '  float nid = floor(a0 * 255.0 / 20.0 + 0.5) - 1.0;',
        '  diffuseColor.rgb = mix(diffuseColor.rgb, pcol, uMix * land);',
        '  if (land > 0.5 && a0 > 0.02 && abs(nid - uSel) < 0.5) diffuseColor.rgb = mix(diffuseColor.rgb, vec3(1.0, 0.94, 0.6), 0.45);',
        '  float me = (a0 > 0.02 && abs(nid - uMe) < 0.5) ? 1.0 : 0.0;',
        '  diffuseColor.rgb = mix(diffuseColor.rgb, mix(vec3(0.17, 0.21, 0.26), vec3(0.12, 0.35, 0.85), me), clamp(bd * (0.4 + 0.6 * uMix) + coast * uMix * 0.85, 0.0, 1.0) * uBorder);'
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
  if (!POLITICAL) OCEAN_NAT = new THREE.Color('#24687c'); // 게임 지도: 예전 지도처럼 짙은 청록 바다
  var oceanMat = new THREE.MeshPhongMaterial({ color: OCEAN_POL.clone(), specular: new THREE.Color(0x000000), shininess: 60, normalMap: waveTex, normalScale: new THREE.Vector2(0, 0), transparent: true, opacity: 0.95, depthWrite: false });
  // 바다 깊이·해안 거리 텍스처: R = 깊이, G = 가장 가까운 땅까지 거리(셀 16칸까지)
  var seaU = { uDep: { value: null }, uGame: { value: 0 }, uTime: { value: 0 }, uWorld: { value: new THREE.Vector2(WX, WZ) } };
  (function () {
    var N = FW * FH, dd = new Uint8Array(N * 4), dist0 = new Float32Array(N), MAXC = 16;
    for (var j = 0; j < FH; j++) for (var i = 0; i < FW; i++) {
      var k = j * FW + i, h = heightAt(-WX + (i + 0.5) * CELL, -WZ + (j + 0.5) * CELL);
      dd[k * 4] = clamp(-h / 0.9 * 255, 0, 255); dd[k * 4 + 3] = 255;
      dist0[k] = h > 0 ? 0 : MAXC;
    }
    // 대각선까지 보는 2회 훑기 거리(계단 모양 줄무늬가 생기지 않게) + 부드럽게 두 번 흐리기
    var D2 = Math.SQRT2, ii, jj, kk;
    for (jj = 0; jj < FH; jj++) for (ii = 0; ii < FW; ii++) { kk = jj * FW + ii; var v = dist0[kk];
      if (ii > 0) v = Math.min(v, dist0[kk - 1] + 1); if (jj > 0) { v = Math.min(v, dist0[kk - FW] + 1); if (ii > 0) v = Math.min(v, dist0[kk - FW - 1] + D2); if (ii < FW - 1) v = Math.min(v, dist0[kk - FW + 1] + D2); } dist0[kk] = v; }
    for (jj = FH - 1; jj >= 0; jj--) for (ii = FW - 1; ii >= 0; ii--) { kk = jj * FW + ii; v = dist0[kk];
      if (ii < FW - 1) v = Math.min(v, dist0[kk + 1] + 1); if (jj < FH - 1) { v = Math.min(v, dist0[kk + FW] + 1); if (ii < FW - 1) v = Math.min(v, dist0[kk + FW + 1] + D2); if (ii > 0) v = Math.min(v, dist0[kk + FW - 1] + D2); } dist0[kk] = Math.min(v, MAXC); }
    for (var bp = 0; bp < 2; bp++) { var tmp = dist0.slice(); for (jj = 1; jj < FH - 1; jj++) for (ii = 1; ii < FW - 1; ii++) { kk = jj * FW + ii; if (tmp[kk] === 0) continue; dist0[kk] = (tmp[kk] * 4 + tmp[kk - 1] + tmp[kk + 1] + tmp[kk - FW] + tmp[kk + FW]) / 8; } }
    for (k = 0; k < N; k++) dd[k * 4 + 1] = dist0[k] / MAXC * 255;
    var t = new THREE.DataTexture(dd, FW, FH, THREE.RGBAFormat); t.magFilter = t.minFilter = THREE.LinearFilter; t.generateMipmaps = false; t.needsUpdate = true; seaU.uDep.value = t;
  })();
  oceanMat.onBeforeCompile = function (sh) {
    for (var k in seaU) sh.uniforms[k] = seaU[k];
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying vec3 vWP;').replace('#include <begin_vertex>', '#include <begin_vertex>\nvWP = (modelMatrix * vec4(transformed, 1.0)).xyz;');
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', [
      '#include <common>', 'varying vec3 vWP; uniform sampler2D uDep; uniform float uGame; uniform float uTime; uniform vec2 uWorld;',
      'float sh21(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7)))*43758.5453); }',
      'float sn2(vec2 p){ vec2 i=floor(p); vec2 f=fract(p); f=f*f*(3.0-2.0*f); return mix(mix(sh21(i),sh21(i+vec2(1.0,0.0)),f.x), mix(sh21(i+vec2(0.0,1.0)),sh21(i+vec2(1.0,1.0)),f.x), f.y); }'].join('\n'))
      .replace('#include <color_fragment>', [
        '#include <color_fragment>',
        '  vec2 duv = (vWP.xz + uWorld) / (2.0 * uWorld);',
        '  vec2 dt2 = texture2D(uDep, clamp(duv, 0.001, 0.999)).rg; float inside = step(0.0, duv.x) * step(duv.x, 1.0) * step(0.0, duv.y) * step(duv.y, 1.0);',
        '  float dep = mix(1.0, dt2.r, inside), cd = mix(1.0, dt2.g, inside);',
        '  float nz = sn2(vWP.xz * 0.35) * 0.6 + sn2(vWP.xz * 1.3) * 0.4;',
        '  vec3 shallow = vec3(0.36, 0.74, 0.72), mid = vec3(0.14, 0.50, 0.62), deepC = vec3(0.06, 0.26, 0.42);',
        '  vec3 wc = mix(shallow, mid, smoothstep(0.0, 0.22, dep + cd * 0.25)); wc = mix(wc, deepC, smoothstep(0.25, 0.85, dep * 0.7 + cd * 0.5 + (nz - 0.5) * 0.15));',
        // surf: a bright line at the shore + thin wave lines moving towards the land
        '  float wv = fract(cd * 6.0 - uTime * 0.12 + nz * 0.6); float lines = smoothstep(0.0, 0.06, wv) * (1.0 - smoothstep(0.06, 0.16, wv)) * (1.0 - smoothstep(0.08, 0.36, cd)) * smoothstep(0.35, 0.7, sn2(vWP.xz * 2.2 + uTime * 0.05));',
        '  float shore = 1.0 - smoothstep(0.0, 0.05, cd + (nz - 0.5) * 0.03);',
        '  wc = mix(wc, vec3(0.93, 0.97, 0.98), clamp(lines * 0.45 + shore * 0.45, 0.0, 1.0));',
        '  diffuseColor.rgb = mix(diffuseColor.rgb, wc, uGame);',
        '  diffuseColor.a = mix(diffuseColor.a, mix(0.62, 0.97, smoothstep(0.0, 0.18, dep + cd * 0.3)) + shore * 0.3, uGame);'
      ].join('\n'));
  };
  var ocean = new THREE.Mesh(new THREE.PlaneGeometry(600, 400), oceanMat); ocean.rotation.x = -Math.PI / 2; ocean.receiveShadow = true; ocean.renderOrder = 1; scene.add(ocean);
  // 구름: 멀리서 볼 때만 바다 위로 천천히 흘러간다(가까이 가면 사라진다)
  var CLOUDS = [], cloudTex = (function () {
    var S2 = 256, cv = document.createElement('canvas'); cv.width = S2; cv.height = S2 / 2; var cx = cv.getContext('2d'), r = rng32(77);
    for (var i = 0; i < 26; i++) {
      var x = S2 * (0.18 + r() * 0.64), y = S2 / 2 * (0.42 + r() * 0.3), rad = 18 + r() * 34 * (1 - Math.abs(x / S2 - 0.5)), g = cx.createRadialGradient(x, y - rad * 0.2, rad * 0.1, x, y, rad);
      g.addColorStop(0, 'rgba(255,255,255,0.95)'); g.addColorStop(0.55, 'rgba(246,249,252,0.75)'); g.addColorStop(1, 'rgba(225,234,242,0)'); cx.fillStyle = g; cx.beginPath(); cx.arc(x, y, rad, 0, Math.PI * 2); cx.fill();
    }
    return new THREE.CanvasTexture(cv);
  })();
  (function () {
    var r = rng32(4242), made = 0;
    for (var t = 0; t < 3000 && made < 26; t++) {
      var x = (r() * 2 - 1) * WX * 1.15, z = (r() * 2 - 1) * WZ * 1.15;
      // 비스듬히 보면 구름은 땅에서 카메라 쪽(+z)으로 밀려 보인다. 그 자리까지 포함해 땅을 가리지 않는 곳에만 띄운다
      var sc = 6 + r() * 7, cy = 6 + r() * 4, zs = z + cy * 0.75, clear = true;
      for (var q = 0; q < 25 && clear; q++) { var qx = x + (q % 5 - 2) * sc * 0.3, qz = zs + (Math.floor(q / 5) - 2) * sc * 0.2; if (landAt(qx, qz) > 0.01) clear = false; }
      if (!clear) continue;
      var sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: cloudTex, transparent: true, depthWrite: false, opacity: 0, fog: false }));
      sp.scale.set(sc, sc * 0.5, 1); sp.position.set(x, cy, z); sp.renderOrder = 5; sp.visible = false;
      sp.userData = { a: 0.55 + r() * 0.35, v: 0.35 + r() * 0.45, f: 1 }; scene.add(sp); CLOUDS.push(sp); made++;
    }
  })();
  function updateClouds(z, dt) {
    var op = POLITICAL ? 0 : sstep(0.62, 0.85, z);
    CLOUDS.forEach(function (c) {
      c.position.x += c.userData.v * dt; if (c.position.x > WX * 1.3) c.position.x = -WX * 1.3; // 바람 따라 계속 흘러간다
      c.visible = op > 0.01; if (!c.visible) return;
      // 땅 위를 지날 때는 옅어져서 나라를 가리지 않는다(화면에서 구름 밑으로 보이는 땅을 본다)
      var zs = c.position.z + c.position.y * 0.75, hw = c.scale.x * 0.35, land = 0;
      for (var q = -1; q <= 1; q++) if (landAt(c.position.x + q * hw, zs) > 0.01) land++;
      c.userData.f += ((land ? 0.22 : 1) - c.userData.f) * Math.min(1, dt * 1.5);
      c.material.opacity = op * c.userData.a * c.userData.f;
    });
  }
  // 멀리서 보는 도시: 마을마다 집 덩어리(벽 + 지붕). 카메라가 멀어질수록 커져서 축소해도 도시가 보인다
  var farCityU = { value: 1 }, FAR_CITY = [];
  (function () {
    var W = [], R = []; // [x, y, z, w, h, d, ry, r, g, b]
    SETTLE.forEach(function (s, si) {
      var st = STYLES[s.n.biome], r = rng32(si * 3571 + 9), flat = st.house === 'flat', nc = hexRGB(s.n.color);
      var cnt = Math.round((s.capital ? 50 : s.port ? 36 : 24) * clamp(s.R, 0.8, 1.6)), ang = r() * Math.PI;
      for (var t = 0, k = 0; t < cnt * 4 && k < cnt; t++) {
        var rad = s.R * 0.75 * Math.pow(r(), 0.65), a = r() * Math.PI * 2, x = s.x + Math.cos(a) * rad, z = s.z + Math.sin(a) * rad;
        if (landAt(x, z) < 0.03) continue;
        var core = 1 - rad / s.R, tall = s.capital ? 1 + core * 2.2 : s.port ? 1 + core * 0.8 : 1;
        var w = 0.09 + r() * 0.03, h = (0.05 + r() * 0.03) * tall, d = 0.08 + r() * 0.03, ry = ang + (r() < 0.5 ? 0 : Math.PI / 2) + (r() - 0.5) * 0.3, y = heightAt(x, z) - 0.01;
        var wc = hexRGB(pick(st.walls, r)), rc = s.port && r() < 0.4 ? [0.55, 0.57, 0.6] : flat ? wc : hexRGB(pick(st.roofs, r));
        W.push([x, y, z, w, h, d, ry].concat(wc)); R.push([x, y, z, w, h, d, ry].concat(rc)); k++;
      }
      if (s.capital) { // 수도 한가운데 랜드마크: 나라 색 지붕의 높은 건물
        var y0 = heightAt(s.x, s.z) - 0.01; W.push([s.x, y0, s.z, 0.13, 0.26, 0.13, ang, 0.93, 0.91, 0.86]); R.push([s.x, y0, s.z, 0.13, 0.26, 0.13, ang].concat(nc));
      }
    });
    var wallG = new THREE.BoxGeometry(1, 1, 1); wallG.translate(0, 0.5, 0);
    var roofG = new THREE.ConeGeometry(0.74, 0.55, 4); roofG.rotateY(Math.PI / 4); roofG.translate(0, 1.27, 0);
    [[wallG, W], [roofG, R]].forEach(function (pr) {
      var list = pr[1], mat = new THREE.MeshLambertMaterial();
      mat.onBeforeCompile = function (sh) { sh.uniforms.uS = farCityU; sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nuniform float uS;').replace('#include <begin_vertex>', '#include <begin_vertex>\ntransformed *= uS;'); };
      var m = new THREE.InstancedMesh(pr[0], mat, list.length), mm = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler(), col = new THREE.Color();
      list.forEach(function (b, i) { e.set(0, b[6], 0); q.setFromEuler(e); mm.compose(new THREE.Vector3(b[0], b[1], b[2]), q, new THREE.Vector3(b[3], b[4], b[5])); m.setMatrixAt(i, mm); m.setColorAt(i, col.setRGB(b[7], b[8], b[9])); });
      m.instanceMatrix.needsUpdate = true; m.frustumCulled = false; m.visible = false; scene.add(m); FAR_CITY.push(m);
    });
  })();
  var deep = new THREE.Mesh(new THREE.PlaneGeometry(600, 400), new THREE.MeshBasicMaterial({ color: 0x1b4a6b })); deep.rotation.x = -Math.PI / 2; deep.position.y = -0.95; scene.add(deep);
  // 강물: 강 길을 따라 띠 메시(물 높이는 하류로만 내려감). 잔물결 무늬가 흐른다
  var riverTex = waveTex.clone(); riverTex.needsUpdate = true; riverTex.repeat.set(1, 1);
  var riverMat = new THREE.MeshPhongMaterial({ color: new THREE.Color('#3b7480'), specular: new THREE.Color(0x1e2a2e), shininess: 30, normalMap: riverTex, normalScale: new THREE.Vector2(0.3, 0.3), transparent: true, opacity: 0.9, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 });
  // 멀리서도 강이 보이게: 카메라가 멀면 폭을 넓힌다(골짜기 안에서만, 최대 0.32)
  var riverW = { value: 0 };
  riverMat.onBeforeCompile = function (sh) {
    sh.uniforms.uRW = riverW;
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nuniform float uRW; attribute vec3 aOff; attribute vec2 aEF; varying vec2 vEF;').replace('#include <begin_vertex>', '#include <begin_vertex>\ntransformed.xz += aOff.xy * max(0.0, uRW - aOff.z); vEF = aEF;');
    // 가장자리는 흐리게(땅에 스며들게), 하구에서는 투명해져 바다 물이 이어받는다
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying vec2 vEF;').replace('#include <color_fragment>', '#include <color_fragment>\n  diffuseColor.a *= (1.0 - smoothstep(0.45, 1.0, abs(vEF.x))) * vEF.y;');
  };
  (function () {
    var pos = [], uv = [], idx = [], off = [], ef = [];
    RIVERS.forEach(function (rv) {
      var p = rv.pts, n = p.length, base = pos.length / 3, along = 0;
      for (var k = 0; k < n; k++) {
        var a = p[Math.max(0, k - 1)], b = p[Math.min(n - 1, k + 1)], dx = b[0] - a[0], dz = b[1] - a[1], l = Math.hypot(dx, dz) || 1, nx = -dz / l, nz = dx / l, w = rv.wid[k], y = rv.surf[k] + 0.004;
        if (k > 0) along += Math.hypot(p[k][0] - p[k - 1][0], p[k][1] - p[k - 1][1]);
        pos.push(p[k][0] + nx * w, y, p[k][1] + nz * w, p[k][0], y, p[k][1], p[k][0] - nx * w, y, p[k][1] - nz * w); uv.push(along * 2.2, 0, along * 2.2, w * 2.2, along * 2.2, w * 4.4); off.push(nx, nz, w, 0, 0, w, -nx, -nz, w);
        var fd = rv.fade[k] * Math.min(1, k / 4); ef.push(-1, fd, 0, fd, 1, fd);
        if (k > 0) { var q = base + k * 3; idx.push(q - 3, q - 2, q, q - 2, q + 1, q, q - 2, q - 1, q + 1, q - 1, q + 2, q + 1); }
      }
    });
    if (!pos.length) return;
    var g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2)); g.setAttribute('aOff', new THREE.Float32BufferAttribute(off, 3)); g.setAttribute('aEF', new THREE.Float32BufferAttribute(ef, 2)); g.setIndex(idx); g.computeVertexNormals();
    if (g.attributes.normal.array[1] < 0) { for (var k = 0; k < idx.length; k += 3) { var tmp = idx[k + 1]; idx[k + 1] = idx[k + 2]; idx[k + 2] = tmp; } g.setIndex(idx); g.computeVertexNormals(); } // 면이 위를 보게
    var rm = new THREE.Mesh(g, riverMat); rm.receiveShadow = true; rm.renderOrder = 1; scene.add(rm);
  })();

  // ───────────────────────── 지오메트리 합치기 도우미 ─────────────────────────
  var _e = new THREE.Euler(), _q = new THREE.Quaternion();
  function mergeParts(parts) {
    var gs = [], total = 0;
    parts.forEach(function (p) { var g = p.g.index ? p.g.toNonIndexed() : p.g.clone(); g.applyMatrix4(p.m); gs.push({ g: g, c: p.c }); total += g.attributes.position.count; });
    var pos = new Float32Array(total * 3), nor = new Float32Array(total * 3), col = new Float32Array(total * 3), kind = new Float32Array(total), hasK = false, off = 0;
    parts.forEach(function (p, i) { gs[i].k = p.k || 0; if (p.k) hasK = true; });
    gs.forEach(function (it) { var n = it.g.attributes.position.count; pos.set(it.g.attributes.position.array, off * 3); nor.set(it.g.attributes.normal.array, off * 3); for (var k = 0; k < n; k++) { col[(off + k) * 3] = it.c[0]; col[(off + k) * 3 + 1] = it.c[1]; col[(off + k) * 3 + 2] = it.c[2]; kind[off + k] = it.k; } off += n; it.g.dispose(); });
    var G = new THREE.BufferGeometry(); G.setAttribute('position', new THREE.BufferAttribute(pos, 3)); G.setAttribute('normal', new THREE.BufferAttribute(nor, 3)); G.setAttribute('color', new THREE.BufferAttribute(col, 3));
    if (hasK) G.setAttribute('kind', new THREE.BufferAttribute(kind, 1)); // 집 부분 종류(1 벽, 2 지붕, 3 목조 벽, 4 평지붕 벽, 5 유리 벽, 0 고정 색)
    G.computeBoundingSphere(); return G;
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
    var mesh = new THREE.Mesh(mergeParts(P), lambertVC); mesh.castShadow = false; mesh.receiveShadow = true; return mesh; // 그림자는 바다 밑바닥에 떨어져 배가 떠 보이므로 끈다
  }
  // 물거품 텍스처: 오른쪽(+x)이 뱃머리. 뱃머리 물결 + 뒤로 퍼지는 V자 항적
  var PORT_SCALE = 0.3, SHIP_SCALE = 0.45; // 항구·배 크기(1 = 처음 크기). 집 한 채 ≈ 0.1
  var wakeTex = (function () {
    var W2 = 256, H2 = 64, cv = document.createElement('canvas'); cv.width = W2; cv.height = H2; var cx = cv.getContext('2d');
    for (var i = 0; i < 900; i++) {
      var u = Math.random(), x = W2 * (1 - u * 0.95) - 20, side = Math.random() < 0.5 ? -1 : 1, spread = 4 + u * 26, y = H2 / 2 + side * spread * (0.55 + Math.random() * 0.45), a = (1 - u) * 0.5;
      cx.fillStyle = 'rgba(255,255,255,' + a.toFixed(3) + ')'; cx.beginPath(); cx.arc(x, y, 1.2 + Math.random() * 2.2 * (1 - u * 0.5), 0, Math.PI * 2); cx.fill();
    }
    var g = cx.createRadialGradient(W2 - 46, H2 / 2, 2, W2 - 46, H2 / 2, 30); g.addColorStop(0, 'rgba(255,255,255,0.75)'); g.addColorStop(1, 'rgba(255,255,255,0)');
    cx.fillStyle = g; cx.beginPath(); cx.ellipse(W2 - 46, H2 / 2, 44, 15, 0, 0, Math.PI * 2); cx.fill();
    var t = new THREE.CanvasTexture(cv); return t;
  })();
  var ringTex = (function () {
    var S2 = 128, cv = document.createElement('canvas'); cv.width = cv.height = S2; var cx = cv.getContext('2d'), g = cx.createRadialGradient(S2 / 2, S2 / 2, S2 * 0.18, S2 / 2, S2 / 2, S2 / 2);
    g.addColorStop(0, 'rgba(255,255,255,0.55)'); g.addColorStop(0.5, 'rgba(255,255,255,0.18)'); g.addColorStop(1, 'rgba(255,255,255,0)'); cx.fillStyle = g; cx.fillRect(0, 0, S2, S2);
    return new THREE.CanvasTexture(cv);
  })();
  var wakeGeo = new THREE.PlaneGeometry(0.78, 0.17); wakeGeo.rotateX(-Math.PI / 2); wakeGeo.translate(-0.2, 0.004, 0);
  var ringGeo = new THREE.PlaneGeometry(0.46, 0.13); ringGeo.rotateX(-Math.PI / 2); ringGeo.translate(0, 0.004, 0);
  function addFoam(ship, moving) {
    var m = new THREE.Mesh(moving ? wakeGeo : ringGeo, new THREE.MeshBasicMaterial({ map: moving ? wakeTex : ringTex, transparent: true, depthWrite: false, opacity: moving ? 0.85 : 0.6 }));
    m.renderOrder = 2; m.userData.foam = true; ship.add(m); return m;
  }
  function makePort(n) {
    var r = rng32(n.i * 7919 + 17), g = new THREE.Group(), P = [], pt = n.port, t = GOODS[n.good].port;
    var ry = Math.atan2(pt.sx, pt.sz);
    g.position.set(pt.x, 0, pt.z); g.rotation.y = ry; g.scale.setScalar(PORT_SCALE); // 집 크기와 맞게 항구 전체(부두·크레인·정박한 배)를 줄인다
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
    // 항구 마을 (여기까지가 부두·설비 = Tripo 항구 모델이 오면 숨긴다)
    var termN = P.length;
    var term = new THREE.Mesh(mergeParts(P.slice(0, termN)), lambertVC); term.castShadow = true; term.receiveShadow = true; g.add(term);
    if (P.length > termN) { var mesh = new THREE.Mesh(mergeParts(P.slice(termN)), lambertVC); mesh.castShadow = true; mesh.receiveShadow = true; g.add(mesh); }
    var slot = new THREE.Group(); slot.position.set(0.6, QUAY_TOP, -0.3); g.add(slot);
    var LP = []; Cyl(LP, 0.03, 0.04, 0.2, 0, 0, 0, '#f4f4f0', 10); Cyl(LP, 0.042, 0.042, 0.02, 0, 0.08, 0, '#d1495b', 10); Cyl(LP, 0.035, 0.035, 0.04, 0, 0.2, 0, '#f6e7a1', 10); Cone(LP, 0.045, 0.05, 0, 0.24, 0, '#d1495b', 10);
    var lh = new THREE.Mesh(mergeParts(LP), lambertVC); lh.castShadow = true; slot.add(lh);
    var ships = []; for (i = 0; i < 2; i++) { var s = makeShip(t, r); addFoam(s, false); s.scale.setScalar(SHIP_SCALE / PORT_SCALE); s.position.set(i ? 0.55 : -0.45, 0, 1.12); s.rotation.y = i ? Math.PI : 0; g.add(s); ships.push({ m: s }); } // 부두에 정박
    var flame = null;
    if (t === 'oil') { flame = new THREE.Mesh(new THREE.ConeGeometry(0.02, 0.06, 6), new THREE.MeshBasicMaterial({ color: 0xff8a2a })); flame.position.set(0.3, QUAY_TOP + 0.39, 0.2); g.add(flame); }
    g.visible = false; scene.add(g);
    return { n: n, g: g, slot: slot, ships: ships, flame: flame, custom: null, term: term, type: t };
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
  function farFromFarms(x, z) { for (var k = 0; k < SETTLE.length; k++) { var s = SETTLE[k], st = STYLES[s.n.biome], fr = st.farm && !s.port ? s.R + st.farmW * (s.capital ? 1.2 : 0.8) : s.R + 0.3; if (Math.hypot(x - s.x, z - s.z) < fr + 0.3) return false; } for (k = 0; k < FARMS.length; k++) if (Math.hypot(FARMS[k].x - x, FARMS[k].z - z) < 0.6) return false; return true; }
  // 나라마다 건물 자리 후보(항구 뒤쪽 땅)
  NATIONS.forEach(function (n) {
    var r = rng32(n.i * 104729 + 5), spots = [], pt = n.port;
    for (var t = 0; t < 4000 && spots.length < 40; t++) {
      var a = r() * Math.PI * 2, d = 2.6 + r() * 5.5, x = pt.x + Math.cos(a) * d - pt.sx * 1.5, z = pt.z + Math.sin(a) * d - pt.sz * 1.5;
      if (nationAt(x, z) !== n.i || landAt(x, z) < 0.06 || riverAt(x, z, 0.3) || heightAt(x, z) > 0.75 || !farFromSettle(x, z, 0.5)) continue;
      if (t < 2600 && !farFromFarms(x, z)) continue; // 처음에는 밭 둘레도 피한다(자리가 모자라면 풀어 준다)
      var ok = true; for (var s = 0; s < spots.length; s++) if (Math.hypot(spots[s][0] - x, spots[s][1] - z) < 0.55) { ok = false; break; }
      if (!ok) continue; spots.push([x, z, r() * Math.PI * 2]);
      FOR[cellIdx(x, z)] = 0;
    }
    n.spots = spots;
    // 산업 건물 자리마다 자갈 마당(밭 무늬·숲 없음)
    spots.forEach(function (sp) {
      var c = Math.ceil(0.32 / CELL), i0 = Math.floor((sp[0] + WX) / CELL), j0 = Math.floor((sp[1] + WZ) / CELL);
      for (var dj = -c; dj <= c; dj++) for (var di = -c; di <= c; di++) {
        var i = i0 + di, j = j0 + dj; if (i < 0 || j < 0 || i >= FW || j >= FH) continue;
        var idx = j * FW + i, d = Math.hypot(di * CELL, dj * CELL); if (d > 0.32) continue;
        var w = 1 - sstep(0.16, 0.32, d), o = idx * 4; FOR[idx] *= 1 - w; FLD[idx] *= 1 - w; natData[o + 3] = Math.round(natData[o + 3] * (1 - w));
        natData[o] = lerp(natData[o], 0.62 * 255, w * 0.55); natData[o + 1] = lerp(natData[o + 1], 0.58 * 255, w * 0.55); natData[o + 2] = lerp(natData[o + 2], 0.5 * 255, w * 0.55);
      }
    });
  });
  natTex.needsUpdate = true;
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
          if (cnt[t] >= PCAP) break; var sp = n.spots[si], y = heightAt(sp[0], sp[1]), s = 0.85;
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
    // 지형 메시는 0.5 간격 삼각형이라 골짜기에서는 실제 높이보다 위에 있다. 길이 그 밑에 묻혀 끊겨 보이지 않게 메시 높이도 본다
    function meshH(x, z) {
      var st = CELL * 2, gx = (x + WX) / st, gz = (z + WZ) / st, i = Math.floor(gx), j = Math.floor(gz), fx = gx - i, fz = gz - j, x0 = -WX + i * st, z0 = -WZ + j * st;
      var ha = heightAt(x0, z0), hb = heightAt(x0 + st, z0), hc = heightAt(x0, z0 + st), hd = heightAt(x0 + st, z0 + st);
      return fx + fz < 1 ? ha + (hb - ha) * fx + (hc - ha) * fz : hd + (hc - hd) * (1 - fx) + (hb - hd) * (1 - fz);
    }
    function vtx(x, z) { var y = Math.max(heightAt(x, z), meshH(x, z), 0.02) + 0.02, ci = cellIdx(x, z); if (RD[ci] < 0.3) y = Math.max(y, RSF[ci] + 0.03 * (1 - sstep(0.1, 0.3, RD[ci])) + 0.008); pos.push(x, y, z); return pos.length / 3 - 1; }
    ROADS.forEach(function (rd) {
      if (rd.disc) { var cx = rd.disc[0], cz = rd.disc[1], rr = rd.disc[2], c0 = vtx(cx, cz), prev = -1, first = -1; for (var q = 0; q <= 16; q++) { var aa = q / 16 * Math.PI * 2, v = q === 16 ? first : vtx(cx + Math.cos(aa) * rr, cz + Math.sin(aa) * rr); if (q === 0) first = v; if (prev >= 0) idx.push(c0, v, prev); prev = v; } return; }
      var p = rd.pts, w = rd.w / 2, L = [], R = [];
      var dense = []; for (var i = 0; i < p.length - 1; i++) { var sl = Math.hypot(p[i + 1][0] - p[i][0], p[i + 1][1] - p[i][1]), nsub = Math.max(1, Math.ceil(sl / 0.1)); for (var u = 0; u < nsub; u++) dense.push([lerp(p[i][0], p[i + 1][0], u / nsub), lerp(p[i][1], p[i + 1][1], u / nsub)]); } dense.push(p[p.length - 1]);
      for (i = 0; i < dense.length; i++) {
        var a2 = dense[Math.max(0, i - 1)], b2 = dense[Math.min(dense.length - 1, i + 1)], dx = b2[0] - a2[0], dz = b2[1] - a2[1], l = Math.hypot(dx, dz) || 1, nx = -dz / l * w, nz = dx / l * w;
        L.push(vtx(dense[i][0] + nx, dense[i][1] + nz)); R.push(vtx(dense[i][0] - nx, dense[i][1] - nz));
        if (i > 0) idx.push(L[i - 1], R[i - 1], L[i], R[i - 1], R[i], L[i]);
      }
    });
    var g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setIndex(idx); g.computeVertexNormals();
    var roadMat = new THREE.MeshLambertMaterial({ color: 0x8c7b62, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2, side: THREE.DoubleSide });
    var rm = new THREE.Mesh(g, roadMat); rm.receiveShadow = true; rm.visible = false; scene.add(rm); cityMeshes.push(rm);
  })();

  // ───────────────────────── 집 (종류별 인스턴스 + 창문·문·목재 무늬 셰이더) ─────────────────────────
  var _he = new THREE.Euler(0, 0, 0, 'YXZ'), _hq = new THREE.Quaternion(), _hv = new THREE.Vector3(), _hs = new THREE.Vector3(1, 1, 1);
  function part(P, g, x, y, z, rx, ry, col, k) { _he.set(rx || 0, ry || 0, 0, 'YXZ'); _hq.setFromEuler(_he); P.push({ g: g, m: new THREE.Matrix4().compose(new THREE.Vector3(x, y, z), _hq.clone(), _hs), c: C(col), k: k }); }
  function bx(P, w, h, d, x, y, z, col, k, rx, ry) { part(P, new THREE.BoxGeometry(w, h, d), x, y, z, rx, ry, col, k); }
  // 박공지붕: 벽 색 삼각 박공 + 처마가 나온 지붕판 두 장. alongZ면 용마루가 z 방향
  function gable(P, cx, cz, base, span, len, rise, alongZ) {
    var r0 = alongZ ? Math.PI / 2 : 0, c0 = Math.cos(r0), s0 = Math.sin(r0);
    function at(lx, ly, lz, rx, g, col, k) { part(P, g, cx + lx * c0 + lz * s0, ly, cz - lx * s0 + lz * c0, rx, r0, col, k); }
    var sh = new THREE.Shape([new THREE.Vector2(-span / 2, 0), new THREE.Vector2(span / 2, 0), new THREE.Vector2(0, rise)]);
    var pg = new THREE.ExtrudeGeometry(sh, { depth: len, bevelEnabled: false }); pg.translate(0, 0, -len / 2); pg.rotateY(Math.PI / 2);
    at(0, base, 0, 0, pg, '#ffffff', 1);
    var ov = 0.1, dz = span / 2 + ov, dy = rise + 0.08 + 0.02, a = Math.atan2(dy, dz), L = Math.hypot(dz, dy), my = base - 0.08 + dy / 2;
    at(0, my, dz / 2, a, new THREE.BoxGeometry(len + 0.12, 0.05, L), '#ffffff', 2);
    at(0, my, -dz / 2, -a, new THREE.BoxGeometry(len + 0.12, 0.05, L), '#ffffff', 2);
  }
  var HGEO = (function () {
    var V = [], P, BRICK = '#8d4b3a';
    P = []; bx(P, 1, 1, 1, 0, 0.5, 0, '#ffffff', 1); gable(P, 0, 0, 1, 1, 1, 0.6, false); bx(P, 0.1, 0.5, 0.1, 0.28, 1.3, -0.2, BRICK, 0); V[0] = P;
    P = []; bx(P, 1, 1.7, 1, 0, 0.85, 0, '#ffffff', 3); gable(P, 0, 0, 1.7, 1, 1, 0.55, false); bx(P, 0.1, 0.5, 0.1, -0.28, 2.0, 0.2, BRICK, 0); V[1] = P;
    P = []; bx(P, 1, 1, 1, 0, 0.5, 0, '#ffffff', 1); gable(P, 0, 0, 1, 1, 1, 0.6, false); bx(P, 0.5, 0.85, 0.7, 0.22, 0.425, 0.8, '#ffffff', 1); gable(P, 0.22, 0.8, 0.85, 0.5, 0.75, 0.42, true); bx(P, 0.1, 0.5, 0.1, -0.3, 1.3, -0.2, BRICK, 0); V[2] = P;
    P = []; bx(P, 1, 1, 1, 0, 0.5, 0, '#ffffff', 1); var pyr = new THREE.ConeGeometry(0.86, 0.6, 4); pyr.rotateY(Math.PI / 4); part(P, pyr, 0, 1.27, 0, 0, 0, '#ffffff', 2); bx(P, 0.1, 0.45, 0.1, 0.25, 1.25, 0.18, BRICK, 0); V[3] = P;
    P = []; bx(P, 1, 1, 1, 0, 0.5, 0, '#ffffff', 4); bx(P, 1.04, 0.1, 0.06, 0, 1.05, 0.49, '#ffffff', 4); bx(P, 1.04, 0.1, 0.06, 0, 1.05, -0.49, '#ffffff', 4); bx(P, 0.06, 0.1, 1.04, 0.49, 1.05, 0, '#ffffff', 4); bx(P, 0.06, 0.1, 1.04, -0.49, 1.05, 0, '#ffffff', 4);
    bx(P, 0.3, 0.28, 0.3, -0.25, 1.14, -0.2, '#ffffff', 4); bx(P, 0.42, 0.03, 0.22, 0, 0.66, 0.6, '#b07a45', 0); V[4] = P;
    P = []; bx(P, 1, 1, 1, 0, 0.5, 0, '#ffffff', 5); bx(P, 1.06, 0.03, 1.06, 0, 1.015, 0, '#e4e8ec', 0); bx(P, 0.4, 0.08, 0.4, 0.15, 1.07, 0.1, '#9aa5ad', 0); V[5] = P;
    P = []; part(P, new THREE.CylinderGeometry(0.5, 0.5, 1, 10), 0, 0.5, 0, 0, 0, '#ffffff', 1); part(P, new THREE.ConeGeometry(0.74, 0.95, 10), 0, 1.47, 0, 0, 0, '#ffffff', 2); V[6] = P;
    return V.map(mergeParts);
  })();
  var houseMat = new THREE.MeshLambertMaterial({ vertexColors: true });
  houseMat.onBeforeCompile = function (sh) {
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nattribute float kind; attribute vec3 iRoof; varying float vKind; varying vec3 vLP; varying vec3 vLN; varying vec3 vScl; varying vec2 vSeed;')
      .replace('#include <color_vertex>', '#include <color_vertex>\n  vColor.rgb = color * (kind > 1.5 && kind < 2.5 ? iRoof : kind > 0.5 ? instanceColor : vec3(1.0));\n  vKind = kind; vLP = position; vLN = normal; vScl = vec3(length(instanceMatrix[0].xyz), length(instanceMatrix[1].xyz), length(instanceMatrix[2].xyz)); vSeed = instanceMatrix[3].xz;');
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying float vKind; varying vec3 vLP; varying vec3 vLN; varying vec3 vScl; varying vec2 vSeed;\nfloat hh1(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7)))*43758.5453); }\nfloat hn2(vec2 p){ vec2 i=floor(p); vec2 f=fract(p); f=f*f*(3.0-2.0*f); return mix(mix(hh1(i),hh1(i+vec2(1.0,0.0)),f.x), mix(hh1(i+vec2(0.0,1.0)),hh1(i+vec2(1.0,1.0)),f.x), f.y); }')
      .replace('#include <color_fragment>', [
        '#include <color_fragment>',
        '  float hgt = vLP.y * vScl.y - ' + HSINK.toFixed(3) + ';',
        '  bool isWall = (vKind > 0.5 && vKind < 1.5) || vKind > 2.5;',
        '  if (isWall && abs(vLN.y) < 0.5) {',
        '    bool fz = abs(vLN.z) > abs(vLN.x);',
        '    float u = fz ? vLP.x * vScl.x : vLP.z * vScl.z;',
        '    if (vKind > 4.5) {',
        '      float cu = fract(u / 0.018 + 0.5), cv = fract(hgt / 0.024);',
        '      diffuseColor.rgb *= mix(0.7, 1.18, step(0.22, cv) * step(cv, 0.86)) * mix(0.82, 1.0, step(0.1, cu));',
        '    } else {',
        '      float eave = (vKind > 2.5 && vKind < 3.5 ? 1.7 : 1.0) * vScl.y - ' + HSINK.toFixed(3) + ' - 0.006;',
        '      float cu = fract(u / 0.036 + 0.5), cv = fract(hgt / 0.038), body = step(hgt, eave) * step(0.004, hgt);',
        '      float win = step(0.37, cu) * step(cu, 0.63) * step(0.36, cv) * step(cv, 0.76) * body;',
        '      float sill = (step(0.33, cu) * step(cu, 0.67) * step(0.32, cv) * step(cv, 0.8) * body) * (1.0 - win);',
        '      float door = (fz && vLN.z > 0.0) ? step(abs(u), 0.0065) * step(hgt, 0.026) : 0.0;',
        '      if (vKind > 2.5 && vKind < 3.5) { float beam = min(1.0, step(cv, 0.07) + step(0.93, cu) + step(cu, 0.07)); diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.33, 0.23, 0.16), beam * body * (1.0 - win)); }',
        '      diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.42, 0.3, 0.2), sill * (1.0 - door));',
        '      diffuseColor.rgb = mix(diffuseColor.rgb, mix(vec3(0.2, 0.22, 0.24), vec3(0.36, 0.33, 0.28), step(0.56, cv)), win * (1.0 - door));',
        '      diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.38, 0.24, 0.14), door);',
        '      diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.5, 0.46, 0.4) * (0.85 + 0.3 * hn2(vec2(u, hgt) * 900.0)), 1.0 - step(0.006, hgt));',
        '    }',
        '  }',
        '  if (vKind > 1.5 && vKind < 2.5) { float row = fract(hgt / 0.011); float tile = hh1(floor(vec2((vLP.x + vLP.z) * vScl.x / 0.012, hgt / 0.011)) + vSeed * 13.0); diffuseColor.rgb *= (0.76 + 0.24 * smoothstep(0.0, 0.35, row)) * (0.88 + 0.2 * tile); }',
        '  float grime = hn2((vLP.xz * vScl.xz + vSeed) * 140.0 + vec2(0.0, hgt * 160.0)) * 0.6 + hn2((vLP.xz * vScl.xz + vSeed) * 420.0 + hgt * 400.0) * 0.4;',
        '  if (vKind > 0.5 && vKind < 4.5) diffuseColor.rgb *= (0.86 + 0.2 * grime) * mix(0.78, 1.0, smoothstep(0.0, 0.03, hgt));',
        '  diffuseColor.rgb *= vec3(1.04, 1.0, 0.93);'
      ].join('\n'));
  };
  (function () {
    var byV = HGEO.map(function () { return []; }); HOUSES.forEach(function (h) { byV[h.v].push(h); });
    var col = new THREE.Color(), mtx = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler(), p = new THREE.Vector3(), s = new THREE.Vector3();
    byV.forEach(function (list, v) {
      if (!list.length) return;
      var g = HGEO[v].clone(), roof = new Float32Array(list.length * 3);
      var m = new THREE.InstancedMesh(g, houseMat, list.length);
      list.forEach(function (h, i) {
        e.set(0, h.ry, 0); q.setFromEuler(e); mtx.compose(p.set(h.x, h.y, h.z), q, s.set(h.w, h.h, h.d)); m.setMatrixAt(i, mtx);
        m.setColorAt(i, col.setRGB(h.wall[0], h.wall[1], h.wall[2])); roof[i * 3] = h.roof[0]; roof[i * 3 + 1] = h.roof[1]; roof[i * 3 + 2] = h.roof[2];
      });
      g.setAttribute('iRoof', new THREE.InstancedBufferAttribute(roof, 3));
      m.instanceMatrix.needsUpdate = true; m.frustumCulled = false; m.castShadow = true; m.receiveShadow = true; m.visible = false; scene.add(m); cityMeshes.push(m);
      bldCount += list.length;
    });
  })();


  // ───────────────────────── 공항·비행기 ─────────────────────────
  var AP_BLD = null, APK = {}; AIRPORTS.forEach(function (ap) { APK[ap.n.key] = ap; });
  (function () {
    if (!AIRPORTS.length) return;
    var P = [];
    AIRPORTS.forEach(function (ap) {
      var c0 = Math.cos(ap.ry), s0 = Math.sin(ap.ry);
      function ap3(g, lx, ly, lz, col) { part(P, g, ap.x + lx * c0 + lz * s0, ap.h + ly, ap.z - lx * s0 + lz * c0, 0, ap.ry, col, 0); }
      ap3(new THREE.BoxGeometry(RWL, 0.008, 0.085), 0, 0.004, 0, '#4b5057');
      for (var k = 0; k < 9; k++) ap3(new THREE.BoxGeometry(0.05, 0.0025, 0.006), -RWL / 2 + 0.1 + k * 0.113, 0.0085, 0, '#eef0f2');
      ap3(new THREE.BoxGeometry(0.06, 0.0025, 0.07), -RWL / 2 + 0.04, 0.0085, 0, '#eef0f2'); ap3(new THREE.BoxGeometry(0.06, 0.0025, 0.07), RWL / 2 - 0.04, 0.0085, 0, '#eef0f2');
      ap3(new THREE.BoxGeometry(0.75, 0.006, 0.03), 0, 0.003, 0.085, '#5d636a'); ap3(new THREE.BoxGeometry(0.4, 0.006, 0.09), 0.02, 0.003, 0.15, '#7c8289');
    });
    var m = new THREE.Mesh(mergeParts(P), lambertVC); m.receiveShadow = true; m.castShadow = true; m.visible = false; scene.add(m); cityMeshes.push(m);
    // 터미널·관제탑·격납고(코드 도형). Tripo 공항 모델이 오면 숨기고 모델로 바꾼다
    P = [];
    AIRPORTS.forEach(function (ap) {
      var c0 = Math.cos(ap.ry), s0 = Math.sin(ap.ry);
      function ap3(g, lx, ly, lz, col) { part(P, g, ap.x + lx * c0 + lz * s0, ap.h + ly, ap.z - lx * s0 + lz * c0, 0, ap.ry, col, 0); }
      ap3(new THREE.BoxGeometry(0.22, 0.05, 0.09), 0.1, 0.025, 0.3, '#e3e6e8'); ap3(new THREE.BoxGeometry(0.2, 0.012, 0.02), 0.1, 0.03, 0.25, '#6f9bb3');
      var hg = new THREE.CylinderGeometry(0.06, 0.06, 0.16, 12, 1, false, 0, Math.PI); hg.rotateZ(Math.PI / 2); hg.rotateY(Math.PI / 2); ap3(hg, -0.22, 0, 0.32, '#b8c0c6');
      ap3(new THREE.CylinderGeometry(0.008, 0.011, 0.11, 8), 0.3, 0.055, 0.3, '#e9ecee'); ap3(new THREE.CylinderGeometry(0.018, 0.016, 0.022, 8), 0.3, 0.12, 0.3, '#5f8fa8'); ap3(new THREE.CylinderGeometry(0.02, 0.02, 0.006, 8), 0.3, 0.134, 0.3, '#e9ecee');
    });
    AP_BLD = new THREE.Mesh(mergeParts(P), lambertVC); AP_BLD.receiveShadow = true; AP_BLD.castShadow = true; AP_BLD.visible = false; scene.add(AP_BLD); cityMeshes.push(AP_BLD);
  })();
  function planeGeo(tail) {
    var P = [], body = new THREE.CylinderGeometry(0.0085, 0.006, 0.11, 8); body.rotateZ(Math.PI / 2); P.push({ g: body, m: new THREE.Matrix4(), c: C('#f4f6f7') });
    var nose = new THREE.SphereGeometry(0.0085, 8, 6); nose.scale(1.6, 1, 1); nose.translate(0.055, 0, 0); P.push({ g: nose, m: new THREE.Matrix4(), c: C('#f4f6f7') });
    bx(P, 0.03, 0.003, 0.125, 0.004, -0.002, 0, '#dfe4e8'); bx(P, 0.016, 0.003, 0.046, -0.048, 0.002, 0, '#dfe4e8');
    bx(P, 0.022, 0.026, 0.003, -0.049, 0.014, 0, tail, 0); bx(P, 0.11, 0.003, 0.0172, 0.0, 0.0, 0, tail, 0);
    bx(P, 0.016, 0.007, 0.007, 0.008, -0.007, 0.03, '#9aa5ad'); bx(P, 0.016, 0.007, 0.007, 0.008, -0.007, -0.03, '#9aa5ad');
    return mergeParts(P);
  }
  var CRUISE = 2.3, PSPEED = 1.7, PLANE_MESHES = [], PLANE_MODEL = null;
  function newPlane(color) {
    var mesh = PLANE_MODEL ? new THREE.Mesh(PLANE_MODEL.geo, PLANE_MODEL.mat) : new THREE.Mesh(planeGeo(color), lambertVC);
    mesh.castShadow = true; mesh.rotation.order = 'YXZ'; mesh.userData.color = color; PLANE_MESHES.push(mesh); return mesh;
  }
  // 공항마다 계류장에 비행기 한 대(무역이 없을 때도 공항이 비어 보이지 않게)
  AIRPORTS.forEach(function (ap) {
    var m = newPlane(ap.n.color), c0 = Math.cos(ap.ry), s0 = Math.sin(ap.ry), lx = 0.02, lz = 0.15;
    m.position.set(ap.x + lx * c0 + lz * s0, ap.h + 0.012, ap.z - lx * s0 + lz * c0); m.rotation.set(0, ap.ry + Math.PI, 0); m.visible = false; scene.add(m); cityMeshes.push(m);
  });
  // 이륙: 활주로를 따라 달리다 떠오름 → 순항 → 내려와 상대 공항 활주로에 내림 (t: 0~1)
  function runEnd(ap, sgn) { return [ap.x + Math.cos(ap.ry) * RWL * 0.45 * sgn, ap.z - Math.sin(ap.ry) * RWL * 0.45 * sgn]; }
  function planePose(A, B, t, out) {
    var dx = B.x - A.x, dz = B.z - A.z, L = Math.hypot(dx, dz) || 1;
    var sa = (dx * Math.cos(A.ry) - dz * Math.sin(A.ry)) > 0 ? 1 : -1, sb = (dx * Math.cos(B.ry) - dz * Math.sin(B.ry)) > 0 ? 1 : -1;
    var A0 = runEnd(A, -sa), A1 = runEnd(A, sa), B0 = runEnd(B, -sb), B1 = runEnd(B, sb), tr = 0.9 / (L + 2);
    out.pitch = 0;
    if (t < tr) { var u = t / tr; out.x = lerp(A0[0], A1[0], u); out.z = lerp(A0[1], A1[1], u); out.y = A.h + 0.012 + Math.max(0, u - 0.6) * 0.3; out.hx = A1[0] - A0[0]; out.hz = A1[1] - A0[1]; out.pitch = u > 0.6 ? 0.15 : 0; return out; }
    if (t > 1 - tr) { var u2 = (t - (1 - tr)) / tr; out.x = lerp(B0[0], B1[0], u2); out.z = lerp(B0[1], B1[1], u2); out.y = B.h + 0.012 + Math.max(0, 0.4 - u2) * 0.3; out.hx = B1[0] - B0[0]; out.hz = B1[1] - B0[1]; return out; }
    var v = (t - tr) / (1 - 2 * tr), sx = A1[0], sz = A1[1], ex = B0[0], ez = B0[1];
    function at(vv, o) { var bend = Math.sin(Math.PI * vv) * L * 0.06; o[0] = lerp(sx, ex, vv) - dz / L * bend; o[1] = lerp(sz, ez, vv) + dx / L * bend; o[2] = lerp(A.h + 0.12, B.h + 0.12, vv) + (CRUISE - 0.12) * sstep(0, 0.22, vv) * (1 - sstep(0.78, 1, vv)); return o; }
    var p0 = at(v, [0, 0, 0]), p1 = at(Math.min(1, v + 0.01), [0, 0, 0]), p2 = at(Math.max(0, v - 0.01), [0, 0, 0]);
    out.x = p0[0]; out.z = p0[1]; out.y = p0[2]; out.hx = p1[0] - p2[0]; out.hz = p1[1] - p2[1];
    out.pitch = clamp(Math.atan2(p1[2] - p2[2], Math.hypot(p1[0] - p2[0], p1[1] - p2[1]) + 1e-6), -0.25, 0.25); return out;
  }
  function flightLen(A, B) { return Math.hypot(B.x - A.x, B.z - A.z) + 2; }
  // 시간으로 보는 비행 한 구간(A→B): 활주로 끝에서 대기 → 천천히 가속하며 활주 → 이륙·상승 → 순항 → 하강·착륙 → 감속 → 대기
  var P_WAIT = 3, P_ROLL = 6.5;
  function planeLeg(A, B) { return 2 * P_WAIT + 2 * P_ROLL + Math.hypot(B.x - A.x, B.z - A.z) / PSPEED; }
  function planeAt(A, B, t, out) {
    var dx = B.x - A.x, dz = B.z - A.z, sa = (dx * Math.cos(A.ry) - dz * Math.sin(A.ry)) > 0 ? 1 : -1, sb = (dx * Math.cos(B.ry) - dz * Math.sin(B.ry)) > 0 ? 1 : -1;
    var A0 = runEnd(A, -sa), A1 = runEnd(A, sa), B0 = runEnd(B, -sb), B1 = runEnd(B, sb), tf = Math.hypot(dx, dz) / PSPEED, k;
    out.pitch = 0;
    if (t < P_WAIT + P_ROLL) { // 출발 공항: 활주로 끝에서 기다렸다가 점점 빨라지며 달리고, 끝 무렵 떠오른다
      k = Math.max(0, t - P_WAIT) / P_ROLL; k = k * k;
      out.x = lerp(A0[0], A1[0], k); out.z = lerp(A0[1], A1[1], k); out.y = A.h + 0.012 + Math.max(0, k - 0.6) * 0.3; out.hx = A1[0] - A0[0]; out.hz = A1[1] - A0[1]; out.pitch = k > 0.6 ? 0.14 : 0; return out;
    }
    t -= P_WAIT + P_ROLL;
    if (t > tf) { // 도착 공항: 내려앉아 점점 느려지며 달리다가 활주로 끝에서 멈춘다
      k = Math.min(1, (t - tf) / P_ROLL); k = 1 - (1 - k) * (1 - k);
      out.x = lerp(B0[0], B1[0], k); out.z = lerp(B0[1], B1[1], k); out.y = B.h + 0.012 + Math.max(0, 0.3 - k) * 0.35; out.hx = B1[0] - B0[0]; out.hz = B1[1] - B0[1]; out.pitch = k < 0.3 ? -0.05 : 0; return out;
    }
    return planePose(A, B, 0.9 / (Math.hypot(dx, dz) + 2) + t / tf * (1 - 1.8 / (Math.hypot(dx, dz) + 2)), out);
  }

  // ───────────────────────── 마을 풍경 (풍차·풍력 발전기·건초·가축·장터·우물·정원 나무·고깃배·바위) ─────────────────────────
  var DECO_GEO = (function () {
    var o = {}, P, k;
    P = []; Cyl(P, 0.045, 0.065, 0.2, 0, 0, 0, '#efe6d3', 8); Cone(P, 0.062, 0.07, 0, 0.2, 0, '#7a4e35', 8); bx(P, 0.022, 0.04, 0.02, 0.055, 0.02, 0, '#5a3d2b'); bx(P, 0.03, 0.025, 0.03, 0.058, 0.2, 0, '#6b4a33'); o.mill = mergeParts(P);
    P = []; for (k = 0; k < 4; k++) { var ga = new THREE.BoxGeometry(0.004, 0.17, 0.004); ga.translate(0, 0.09, 0); ga.rotateX(k * Math.PI / 2); P.push({ g: ga, m: new THREE.Matrix4(), c: C('#6b4a33') }); var gs = new THREE.BoxGeometry(0.003, 0.12, 0.034); gs.translate(0, 0.11, 0.019); gs.rotateX(k * Math.PI / 2); P.push({ g: gs, m: new THREE.Matrix4(), c: C('#f1ead8') }); } o.millBlades = mergeParts(P);
    P = []; Cyl(P, 0.0045, 0.008, 0.26, 0, 0, 0, '#f4f6f7', 8); bx(P, 0.034, 0.016, 0.016, 0.006, 0.267, 0, '#eef1f3'); o.turbine = mergeParts(P);
    P = []; for (k = 0; k < 3; k++) { var gb = new THREE.BoxGeometry(0.003, 0.11, 0.01); gb.translate(0, 0.055, 0); gb.rotateX(k * Math.PI * 2 / 3); P.push({ g: gb, m: new THREE.Matrix4(), c: C('#f7f9fa') }); } var hub = new THREE.SphereGeometry(0.006, 6, 4); P.push({ g: hub, m: new THREE.Matrix4(), c: C('#dfe4e8') }); o.turbineBlades = mergeParts(P);
    P = []; var bale = new THREE.CylinderGeometry(0.016, 0.016, 0.024, 10); bale.rotateZ(Math.PI / 2); bale.translate(0, 0.014, 0); P.push({ g: bale, m: new THREE.Matrix4(), c: C('#d8b65a') }); o.hay = mergeParts(P);
    P = []; Blob(P, 0.015, 0.75, 0, 0.02, 0, '#f2efe6'); bx(P, 0.009, 0.009, 0.008, 0.017, 0.024, 0, '#3b3330'); [[-0.007, -0.005], [-0.007, 0.005], [0.007, -0.005], [0.007, 0.005]].forEach(function (l) { bx(P, 0.003, 0.012, 0.003, l[0], 0.006, l[1], '#3b3330'); }); o.sheep = mergeParts(P);
    P = []; bx(P, 0.034, 0.016, 0.015, 0, 0.02, 0, '#7a4b2e'); bx(P, 0.012, 0.011, 0.01, 0.021, 0.026, 0, '#5e3a24'); [[-0.012, -0.005], [-0.012, 0.005], [0.012, -0.005], [0.012, 0.005]].forEach(function (l) { bx(P, 0.004, 0.014, 0.004, l[0], 0.007, l[1], '#4a2f1d'); }); o.cow = mergeParts(P);
    P = []; Cyl(P, 0.018, 0.018, 0.016, 0, 0, 0, '#9e9a90', 10); Cyl(P, 0.014, 0.014, 0.017, 0, 0, 0, '#2e4f63', 10); bx(P, 0.004, 0.04, 0.004, -0.015, 0.02, 0, '#6b4a33'); bx(P, 0.004, 0.04, 0.004, 0.015, 0.02, 0, '#6b4a33'); Roof(P, 0.04, 0.015, 0.03, 0, 0.04, 0, '#7a4e35', Math.PI / 2); o.well = mergeParts(P);
    ['#c0392b', '#2e86de', '#e1b12c'].forEach(function (aw, i) {
      P = []; [[-0.022, -0.014], [0.022, -0.014], [-0.022, 0.014], [0.022, 0.014]].forEach(function (l) { bx(P, 0.003, 0.032, 0.003, l[0], 0.016, l[1], '#6b4a33'); });
      bx(P, 0.044, 0.014, 0.012, 0, 0.007, 0.008, '#a77a4c'); bx(P, 0.012, 0.008, 0.008, -0.01, 0.018, 0.008, ['#e67e22', '#27ae60', '#f4d03f'][i]); bx(P, 0.012, 0.008, 0.008, 0.008, 0.018, 0.008, ['#8e44ad', '#c0392b', '#27ae60'][i]);
      Roof(P, 0.054, 0.012, 0.04, 0, 0.032, 0, aw, 0); o['stall' + i] = mergeParts(P);
    });
    P = []; Cyl(P, 0.005, 0.007, 0.035, 0, 0, 0, '#6b4a33', 5); Blob(P, 0.03, 0.9, 0, 0.058, 0, '#5c8f3c'); Blob(P, 0.02, 0.9, 0.012, 0.072, 0.006, '#6fa346'); o.gtree = mergeParts(P);
    P = []; Cyl(P, 0.004, 0.006, 0.1, 0, 0, 0, '#8d6e63', 5, 0.12); Blob(P, 0.04, 0.3, -0.012, 0.1, 0, '#3e8e41'); o.palm = mergeParts(P);
    P = []; var hs = new THREE.Shape([new THREE.Vector2(-0.05, -0.016), new THREE.Vector2(0.03, -0.016), new THREE.Vector2(0.058, 0), new THREE.Vector2(0.03, 0.016), new THREE.Vector2(-0.05, 0.016)]);
    var hg = new THREE.ExtrudeGeometry(hs, { depth: 0.016, bevelEnabled: false }); hg.rotateX(-Math.PI / 2); hg.translate(0, -0.006, 0); P.push({ g: hg, m: new THREE.Matrix4(), c: C('#7b5236') });
    bx(P, 0.09, 0.003, 0.026, -0.004, 0.01, 0, '#a57b52'); Cyl(P, 0.0018, 0.0018, 0.085, 0.004, 0.01, 0, '#5a3d2b', 5);
    var ss = new THREE.Shape([new THREE.Vector2(0, 0), new THREE.Vector2(0, 0.07), new THREE.Vector2(-0.045, 0)]); var sg = new THREE.ExtrudeGeometry(ss, { depth: 0.002, bevelEnabled: false }); sg.translate(0.002, 0.018, -0.001); P.push({ g: sg, m: new THREE.Matrix4(), c: C('#f6f1e4') }); o.boat = mergeParts(P);
    P = []; Blob(P, 0.02, 0.6, 0, 0.003, 0, '#8f897c'); Blob(P, 0.012, 0.7, 0.016, 0.0, 0.007, '#7f796d'); o.rock = mergeParts(P);
    return o;
  })();
  var DECO = {}; Object.keys(DECO_GEO).forEach(function (t) { DECO[t] = []; });
  (function placeDeco() {
    // 집과 겹치지 않게: 0.12 칸 격자에 집 자리를 넣어 둔다
    var HG2 = new Map(), GC = 0.12;
    function hk(i, j) { return i + ',' + j; }
    HOUSES.forEach(function (h) { var key = hk(Math.floor(h.x / GC), Math.floor(h.z / GC)); var a = HG2.get(key); if (!a) HG2.set(key, a = []); a.push(h); });
    function free(x, z, rad) {
      for (var ai = 0; ai < AIRPORTS.length; ai++) if (Math.hypot(AIRPORTS[ai].x - x, AIRPORTS[ai].z - z) < RWL / 2 + 0.3 + rad) return false;
      var i0 = Math.floor(x / GC), j0 = Math.floor(z / GC);
      for (var di = -1; di <= 1; di++) for (var dj = -1; dj <= 1; dj++) { var a = HG2.get(hk(i0 + di, j0 + dj)); if (!a) continue; for (var k = 0; k < a.length; k++) { var h = a[k], hr = Math.max(h.w, h.d) * (h.v === 2 ? 0.9 : 0.6); if (Math.hypot(h.x - x, h.z - z) < hr + rad) return false; } }
      return true;
    }
    function put(t, x, z, ry, s, extra) { var a = [x, heightAt(x, z), z, ry, s]; if (extra) a.push.apply(a, extra); DECO[t].push(a); }
    function dry(x, z) { return landAt(x, z) > 0.05 && !riverAt(x, z, 0.05); }
    var GRASS = { temperate: 1, plains: 1, boreal: 1, island: 1, outback: 1, tropical: 1 };
    SETTLE.forEach(function (s, si) {
      var r = rng32(si * 5113 + 77), st = STYLES[s.n.biome], b = s.n.biome, h0 = heightAt(s.x, s.z), ang = s.ang || 0, mod = MODERN[s.n.key] || 0.2;
      var farR = st.farm ? s.R + st.farmW * (s.capital ? 1.2 : 0.8) : s.R + 1.2, t, k, a, d, x, z;
      // 장터와 우물 (가운데 광장 둘레)
      var ring = USE_MODELS ? (s.capital ? 0.44 : 0.27) : (s.capital ? 0.24 : 0.17), ns = s.capital ? 7 : 3 + Math.floor(r() * 2);
      for (k = 0; k < ns; k++) { a = ang + (k + 0.5) / ns * Math.PI * 2; x = s.x + Math.cos(a) * ring; z = s.z + Math.sin(a) * ring; if (dry(x, z) && free(x, z, 0.02)) put('stall' + (k % 3), x, z, -a + Math.PI / 2, 1); }
      for (t = 0; t < 20; t++) { a = r() * Math.PI * 2; x = s.x + Math.cos(a) * (ring + 0.06); z = s.z + Math.sin(a) * (ring + 0.06); if (dry(x, z) && free(x, z, 0.02)) { put('well', x, z, r() * 6.28, 1); break; } }
      // 정원 나무 (집 사이)
      var tree = b === 'tropical' || b === 'desert' || b === 'island' ? 'palm' : 'gtree', nt = Math.round((s.capital ? 18 : 10) * (b === 'outback' ? 0.4 : 1));
      for (t = 0, k = 0; t < nt * 8 && k < nt; t++) { a = r() * Math.PI * 2; d = s.R * (0.3 + r() * 0.85); x = s.x + Math.cos(a) * d; z = s.z + Math.sin(a) * d; if (!dry(x, z) || !free(x, z, 0.03)) continue; put(tree, x, z, r() * 6.28, 0.8 + r() * 0.5); k++; }
      // 풍차(밀밭 마을) / 풍력 발전기(산업이 발달한 나라)
      if (st.farm && !s.port && (b === 'temperate' || b === 'plains' || b === 'boreal')) {
        var nm = s.capital ? 2 : 1;
        for (t = 0, k = 0; t < 80 && k < nm; t++) { a = r() * Math.PI * 2; d = lerp(s.R + 0.3, farR * 0.85, r()); x = s.x + Math.cos(a) * d; z = s.z + Math.sin(a) * d; if (!dry(x, z) || Math.abs(heightAt(x, z) - h0) > 0.45) continue; FOR[cellIdx(x, z)] = 0; put('mill', x, z, r() * 6.28, 1.15, [r() * 6.28, 0.9 + r() * 0.5]); k++; }
      }
      if (mod >= 0.6 && !s.port) {
        for (t = 0, k = 0; t < 120 && k < (s.capital ? 4 : 2); t++) { a = r() * Math.PI * 2; d = farR + 0.4 + r() * 1.2; x = s.x + Math.cos(a) * d; z = s.z + Math.sin(a) * d; if (!dry(x, z) || nationAt(x, z) !== s.n.i || !farFromSettle(x, z, 0.3)) continue; FOR[cellIdx(x, z)] = 0; put('turbine', x, z, r() * 6.28, 1, [r() * 6.28, 1.6 + r() * 0.6]); k++; }
      }
      // 건초 더미 (밭 위에 몇 개씩 모여)
      if (st.farm && !s.port && b !== 'tropical' && b !== 'desert') {
        for (t = 0, k = 0; t < 60 && k < (s.capital ? 7 : 4); t++) {
          a = r() * Math.PI * 2; d = lerp(s.R + 0.2, farR, r()); x = s.x + Math.cos(a) * d; z = s.z + Math.sin(a) * d; if (!dry(x, z) || sampleArr(FLD, x, z) < 0.3) continue;
          var nb = 3 + Math.floor(r() * 4), ry0 = r() * 6.28; for (var q = 0; q < nb; q++) put('hay', x + (r() - 0.5) * 0.14, z + (r() - 0.5) * 0.14, ry0 + (r() - 0.5) * 0.4, 0.9 + r() * 0.3); k++;
        }
      }
      // 가축 (풀밭에 무리 지어)
      if (GRASS[b] && !s.port) {
        var herds = s.capital ? 3 : 2;
        for (t = 0, k = 0; t < 80 && k < herds; t++) {
          a = r() * Math.PI * 2; d = lerp(s.R + 0.25, farR + 0.5, r()); x = s.x + Math.cos(a) * d; z = s.z + Math.sin(a) * d;
          if (!dry(x, z) || FOR[cellIdx(x, z)] > 0.25 || Math.abs(heightAt(x, z) - h0) > 0.5) continue;
          var kind = b === 'plains' || b === 'tropical' ? 'cow' : b === 'island' ? 'sheep' : r() < 0.5 ? 'sheep' : 'cow', na = 4 + Math.floor(r() * 4);
          for (q = 0; q < na; q++) { var ax = x + (r() - 0.5) * 0.22, az = z + (r() - 0.5) * 0.22; if (dry(ax, az)) { FOR[cellIdx(ax, az)] *= 0.3; put(kind, ax, az, r() * 6.28, 1); } }
          k++;
        }
      }
      // 고깃배 (마을 앞바다)
      var boats = [];
      for (t = 0; t < 140 && boats.length < (s.capital ? 3 : 2); t++) {
        a = r() * Math.PI * 2; d = s.R + 0.3 + r() * 3.2; x = s.x + Math.cos(a) * d; z = s.z + Math.sin(a) * d; var lf = landAt(x, z);
        if (lf > -0.05 || lf < -0.3) continue; var ok = true; for (q = 0; q < boats.length; q++) if (Math.hypot(boats[q][0] - x, boats[q][1] - z) < 0.35) ok = false; if (!ok) continue;
        boats.push([x, z]); DECO.boat.push([x, 0, z, r() * 6.28, 1, r() * 6.28, 0.2 + r() * 0.25]);
      }
    });
    // 농가 마당: 건초 몇 개, 나무 한두 그루, 가끔 가축
    FARMS.forEach(function (f, fi) {
      var r = rng32(fi * 811 + 5), b = f.s.n.biome, c = Math.cos(f.ry), sn = Math.sin(f.ry), x, z, k;
      for (k = 0; k < 3; k++) { x = f.x - 0.12 * sn + (r() - 0.5) * 0.08 + 0.06 * c; z = f.z - 0.12 * c + (r() - 0.5) * 0.08 - 0.06 * sn; if (dry(x, z) && free(x, z, 0.015)) put(b === 'desert' || b === 'tropical' ? 'palm' : 'hay', x, z, f.ry + (r() - 0.5) * 0.5, 1); }
      for (k = 0; k < 2; k++) { x = f.x + (r() - 0.5) * 0.36; z = f.z + (r() - 0.5) * 0.36; if (dry(x, z) && free(x, z, 0.03)) put(b === 'tropical' || b === 'desert' || b === 'island' ? 'palm' : 'gtree', x, z, r() * 6.28, 0.9 + r() * 0.4); }
      if (GRASS[b] && r() < 0.5) for (k = 0; k < 3; k++) { x = f.x + 0.2 * sn + (r() - 0.5) * 0.12; z = f.z + 0.2 * c + (r() - 0.5) * 0.12; if (dry(x, z) && free(x, z, 0.02)) put(b === 'plains' ? 'cow' : 'sheep', x, z, r() * 6.28, 1); }
    });
    // 바위: 산·언덕에 많이, 해안·들판에 조금
    var rr = rng32(4242), nr = 0, CAPR = 2200;
    for (var t2 = 0; t2 < 60000 && nr < CAPR; t2++) {
      var x2 = (rr() * 2 - 1) * WX, z2 = (rr() * 2 - 1) * WZ, f = landAt(x2, z2); if (f < 0.012) continue;
      var h = heightAt(x2, z2), pr = sstep(0.6, 1.1, h) * 0.8 + (f < 0.04 ? 0.14 : 0.003);
      if (rr() > pr || riverAt(x2, z2, 0.04) || !farFromSettle(x2, z2, 0.25) || AIRPORTS.some(function (ap) { return Math.hypot(ap.x - x2, ap.z - z2) < RWL / 2 + 0.4; })) continue;
      var nearPort = false; for (var pi2 = 0; pi2 < NATIONS.length; pi2++) if (Math.hypot(NATIONS[pi2].port.x - x2, NATIONS[pi2].port.z - z2) < 2.6) { nearPort = true; break; } if (nearPort) continue;
      put('rock', x2, z2, rr() * 6.28, (0.6 + rr() * 0.9) * (h > 0.9 ? 1.8 : 1)); nr++;
    }
  })();
  var decoMesh = {}, ANIM = { millBlades: 'mill', turbineBlades: 'turbine' };
  function setInst(m, i, x, y, z, rx, ry, s) { _he.set(rx, ry, 0, 'YXZ'); _hq.setFromEuler(_he); _hv.set(x, y, z); m.setMatrixAt(i, new THREE.Matrix4().compose(_hv, _hq, _hs.set(s, s, s))); _hs.set(1, 1, 1); }
  Object.keys(DECO_GEO).forEach(function (t) {
    var src = ANIM[t] || t, list = DECO[src]; if (!list.length) return;
    var m = new THREE.InstancedMesh(DECO_GEO[t], lambertVC, list.length);
    if (!ANIM[t]) list.forEach(function (a, i) { setInst(m, i, a[0], a[1] - 0.004, a[2], 0, a[3], a[4]); });
    m.instanceMatrix.needsUpdate = true; m.frustumCulled = false; m.castShadow = t !== 'rock' && t !== 'hay'; m.receiveShadow = true; m.visible = false;
    if (ANIM[t] || t === 'boat') m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    scene.add(m); cityMeshes.push(m); decoMesh[t] = m;
  });
  // 풍차·발전기 날개는 돌고, 고깃배는 천천히 떠다닌다
  var HUB = { millBlades: [0.072, 0.2, 1.15], turbineBlades: [0.025, 0.267, 1] };
  function updateDeco(t) {
    Object.keys(ANIM).forEach(function (bt) {
      var m = decoMesh[bt]; if (!m) return; var hb = HUB[bt];
      DECO[ANIM[bt]].forEach(function (a, i) { var s = a[4], c = Math.cos(a[3]), sn = Math.sin(a[3]); setInst(m, i, a[0] + hb[0] * c * s, a[1] - 0.004 + hb[1] * s, a[2] - hb[0] * sn * s, t * a[6] + a[5], a[3], s); });
      m.instanceMatrix.needsUpdate = true;
    });
    var bm = decoMesh.boat; if (!bm) return;
    DECO.boat.forEach(function (a, i) { var th = t * a[6] * 0.25 + a[5], R = 0.09; setInst(bm, i, a[0] + Math.cos(th) * R, Math.sin(t * 1.7 + a[5]) * 0.003, a[2] + Math.sin(th) * R, Math.sin(t * 1.3 + a[5]) * 0.06, -th - Math.PI / 2, 1); });
    bm.instanceMatrix.needsUpdate = true;
  }

  // ───────────────────────── 무역로 (게임 거래에서 만듦) ─────────────────────────
  var routeW = { value: 0.2 }, routes = [], routeGroup = new THREE.Group(), traffic = new THREE.Group(); scene.add(routeGroup); scene.add(traffic);
  // 바닷길: 0.5칸 격자에서 A*로 항구 앞바다끼리 잇고(해안 가까이는 비싸게), 보이는 데까지 곧게 편 뒤 부드럽게 만든다
  var SG = 0.5, SGW = Math.ceil(2 * WX / SG), SGH = Math.ceil(2 * WZ / SG), SEA = null, seaCache = {};
  function seaGrid() {
    if (SEA) return SEA; SEA = new Float32Array(SGW * SGH);
    for (var j = 0; j < SGH; j++) for (var i = 0; i < SGW; i++) {
      var x = -WX + (i + 0.5) * SG, z = -WZ + (j + 0.5) * SG, k = j * SGW + i; if (landAt(x, z) > -0.05) continue;
      var near = 0; for (var a = 0; a < 8; a++) if (landAt(x + Math.cos(a * 0.785) * 0.9, z + Math.sin(a * 0.785) * 0.9) > -0.02) near++;
      SEA[k] = 1 + near * 0.6;
    }
    return SEA;
  }
  function portFront(n) { return [n.port.x + n.port.sx * 1.45, n.port.z + n.port.sz * 1.45]; }
  function seaOpen(ax, az, bx, bz) { var L = Math.hypot(bx - ax, bz - az), n = Math.ceil(L / 0.2); for (var k = 1; k < n; k++) if (landAt(lerp(ax, bx, k / n), lerp(az, bz, k / n)) > -0.035) return false; return true; }
  function seaPath(na, nb) {
    var key = na.key + '>' + nb.key; if (seaCache[key]) return seaCache[key];
    var G = seaGrid(), A = portFront(na), B = portFront(nb);
    function cellOf(p) { var i0 = clamp(Math.floor((p[0] + WX) / SG), 0, SGW - 1), j0 = clamp(Math.floor((p[1] + WZ) / SG), 0, SGH - 1); for (var r = 0; r < 8; r++) for (var dj = -r; dj <= r; dj++) for (var di = -r; di <= r; di++) { var i = i0 + di, j = j0 + dj; if (i >= 0 && j >= 0 && i < SGW && j < SGH && G[j * SGW + i] > 0) return j * SGW + i; } return -1; }
    var s0 = cellOf(A), e0 = cellOf(B), pts = [A];
    if (s0 >= 0 && e0 >= 0) {
      var N = SGW * SGH, g = new Float32Array(N).fill(1e9), came = new Int32Array(N).fill(-1), closed = new Uint8Array(N), heap = [], ex = e0 % SGW, ez = (e0 / SGW) | 0;
      function hval(k) { return Math.hypot(k % SGW - ex, ((k / SGW) | 0) - ez); }
      function push(k, f) { heap.push([f, k]); var c = heap.length - 1; while (c > 0) { var pa = (c - 1) >> 1; if (heap[pa][0] <= heap[c][0]) break; var t = heap[pa]; heap[pa] = heap[c]; heap[c] = t; c = pa; } }
      function pop() { var top = heap[0], last = heap.pop(); if (heap.length) { heap[0] = last; var c = 0; for (;;) { var l = 2 * c + 1, r = l + 1, m = c; if (l < heap.length && heap[l][0] < heap[m][0]) m = l; if (r < heap.length && heap[r][0] < heap[m][0]) m = r; if (m === c) break; var t = heap[m]; heap[m] = heap[c]; heap[c] = t; c = m; } } return top[1]; }
      g[s0] = 0; push(s0, hval(s0)); var found = false;
      while (heap.length) {
        var k = pop(); if (closed[k]) continue; closed[k] = 1; if (k === e0) { found = true; break; }
        var ci = k % SGW, cj = (k / SGW) | 0;
        for (var dj = -1; dj <= 1; dj++) for (var di = -1; di <= 1; di++) {
          if (!di && !dj) continue; var ni = ci + di, nj = cj + dj; if (ni < 0 || nj < 0 || ni >= SGW || nj >= SGH) continue;
          var nk = nj * SGW + ni; if (!G[nk] || closed[nk]) continue;
          var ng = g[k] + (di && dj ? 1.414 : 1) * G[nk]; if (ng < g[nk]) { g[nk] = ng; came[nk] = k; push(nk, ng + hval(nk)); }
        }
      }
      if (found) {
        var cells = []; for (var c = e0; c >= 0; c = came[c]) cells.push([-WX + (c % SGW + 0.5) * SG, -WZ + (((c / SGW) | 0) + 0.5) * SG]); cells.reverse();
        var raw = [A].concat(cells, [B]), q = 0; pts = [A];
        while (q < raw.length - 1) { var far = q + 1; for (var t2 = raw.length - 1; t2 > q + 1; t2--) if (seaOpen(raw[q][0], raw[q][1], raw[t2][0], raw[t2][1])) { far = t2; break; } pts.push(raw[far]); q = far; }
      } else pts.push(B);
    } else pts.push(B);
    if (pts[pts.length - 1] !== B) pts.push(B);
    // 긴 직선은 중간 점을 넣어 부드러운 곡선이 땅을 덜 스치게
    var dense = [pts[0]]; for (var k2 = 1; k2 < pts.length; k2++) { var a2 = pts[k2 - 1], b2 = pts[k2], L2 = Math.hypot(b2[0] - a2[0], b2[1] - a2[1]), ns = Math.max(1, Math.ceil(L2 / 3)); for (var u = 1; u <= ns; u++) dense.push([lerp(a2[0], b2[0], u / ns), lerp(a2[1], b2[1], u / ns)]); }
    seaCache[key] = dense; return dense;
  }
  var SHIPGEO = {}, _pose = {};
  function clearRoutes() {
    routes.forEach(function (r) { r.tube.geometry.dispose(); r.mat.dispose(); r.vehicles.forEach(function (v) { if (v.own) v.m.geometry.dispose(); var pi = PLANE_MESHES.indexOf(v.m); if (pi >= 0) PLANE_MESHES.splice(pi, 1); }); });
    routes = []; while (routeGroup.children.length) routeGroup.remove(routeGroup.children[0]); while (traffic.children.length) traffic.remove(traffic.children[0]);
  }
  function setTrades(trades) {
    clearRoutes();
    var agg = {}, order = [];
    (trades || []).forEach(function (t) { (t.legs || []).forEach(function (l) { if (!NK[l.seller] || !NK[l.buyer] || l.seller === l.buyer) return; var k = l.seller + '>' + l.buyer + '>' + l.good; if (!agg[k]) { agg[k] = { s: l.seller, b: l.buyer, good: l.good, qty: 0 }; order.push(k); } agg[k].qty += l.qty || 1; }); });
    var pairCount = {};
    order.forEach(function (k, ri) {
      var a0 = agg[k], NA = NK[a0.s], NB = NK[a0.b], info = GOODS[a0.good] || { color: '#888888', port: 'container' };
      // 전자제품은 비행기(가볍고 비싼 물건), 나머지는 배
      var air = a0.good === 'electronics' && APK[a0.s] && APK[a0.b], pk = [a0.s, a0.b].sort().join('|') + (air ? 'A' : 'S'), slot = pairCount[pk] = (pairCount[pk] || 0) + 1;
      var curve, pts3 = [];
      if (air) { for (var q = 0; q <= 48; q++) { planePose(APK[a0.s], APK[a0.b], q / 48, _pose); pts3.push(new THREE.Vector3(_pose.x, _pose.y + (slot - 1) * 0.15, _pose.z)); } }
      else {
        var sp = seaPath(NA, NB), off = (slot - 1) * 0.22 * (a0.s < a0.b ? 1 : -1);
        // 부두에서 출발해 부두에 닿는다: 항구 바로 앞(정박 자리)에서 바다 쪽으로 곧게 나간다
        function berth(n, d) { return new THREE.Vector3(n.port.x + n.port.sx * d, 0.03, n.port.z + n.port.sz * d); }
        pts3.push(berth(NA, 0.4), berth(NA, 0.9));
        for (var q2 = 0; q2 < sp.length; q2++) {
          var a = sp[Math.max(0, q2 - 1)], b = sp[Math.min(sp.length - 1, q2 + 1)], dx = b[0] - a[0], dz = b[1] - a[1], l = Math.hypot(dx, dz) || 1, o = q2 === 0 || q2 === sp.length - 1 ? 0 : off;
          pts3.push(new THREE.Vector3(sp[q2][0] - dz / l * o, 0.03, sp[q2][1] + dx / l * o));
        }
        pts3.push(berth(NB, 0.9), berth(NB, 0.4));
      }
      pts3 = pts3.filter(function (v) { return isFinite(v.x) && isFinite(v.z); }); var kept = []; pts3.forEach(function (v) { if (!kept.length || v.distanceTo(kept[kept.length - 1]) > 0.05) kept.push(v); }); pts3 = kept; if (!pts3.length) pts3.push(new THREE.Vector3(NA.port.x, 0.03, NA.port.z)); if (pts3.length < 2) pts3.push(pts3[0].clone().add(new THREE.Vector3(0.1, 0, 0))); // 겹친 점이 있으면 곡선 길이가 NaN이 된다
      curve = new THREE.CatmullRomCurve3(pts3, false, 'centripetal');
      var mat = new THREE.MeshBasicMaterial({ color: new THREE.Color(info.color), transparent: true, opacity: 0.8, depthWrite: false });
      mat.onBeforeCompile = function (sh) { sh.uniforms.uW = routeW; sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nuniform float uW;').replace('#include <begin_vertex>', 'vec3 transformed = position - normal + normal * uW;'); };
      var tube = new THREE.Mesh(new THREE.TubeGeometry(curve, Math.max(64, pts3.length * 6), 1, 6, false), mat); tube.frustumCulled = false; tube.renderOrder = 2; routeGroup.add(tube);
      var vehicles = [], nd = clamp(Math.ceil(a0.qty / 2), 1, 3), len = curve.getLength(); if (!isFinite(len)) { curve = new THREE.LineCurve3(pts3[0], pts3[pts3.length - 1]); len = curve.getLength(); } var rr = rng32(ri * 131 + 7);
      for (var i = 0; i < nd; i++) {
        var v;
        if (air) { v = { m: newPlane(NA.color), own: !PLANE_MODEL, plane: true }; }
        else {
          var type = info.port || 'container', mname = SHIP_MODEL[type], sm;
          if (SHIPGEO[mname]) { sm = new THREE.Mesh(SHIPGEO[mname].geo, SHIPGEO[mname].mat); v = { m: sm, own: false }; } else { sm = makeShip(type, rr); v = { m: sm, own: true }; }
          v.model = mname; addFoam(sm, true); sm.rotation.order = 'YXZ';
        }
        v.off = i / nd; traffic.add(v.m); vehicles.push(v);
      }
      routes.push({ curve: curve, tube: tube, mat: mat, vehicles: vehicles, air: !!air, A: APK[a0.s], B: APK[a0.b], speed: air ? 1 / (2 * planeLeg(APK[a0.s], APK[a0.b])) : 0.45 / Math.max(len, 1), dwell: air ? 0 : Math.min(0.12, 2.5 / Math.max(len, 1)), ease: air ? 0 : Math.min(0.3, 1.2 / Math.max(len, 1)), info: a0 });
    });
    legendDirty = true;
  }
  var _tp = new THREE.Vector3(), _tt = new THREE.Vector3();
  function updateTraffic(rOp) {
    var sc = clamp(dist * 0.05, 1, 6), ssc = sc * SHIP_SCALE;
    routes.forEach(function (r) {
      r.tube.visible = rOp > 0.01; r.mat.opacity = 0.75 * rOp;
      r.vehicles.forEach(function (v) {
        var u = (((clock * r.speed + v.off) % 1) + 1) % 1 /* 시작 직후 clock이 음수여도 0~1 */, env = sstep(0, 0.025, u) * (1 - sstep(0.975, 1, u));
        if (r.air) { // 두 공항을 오간다(순간이동 없음). u 앞 절반은 A→B, 뒤 절반은 B→A
          var T1 = planeLeg(r.A, r.B), tt = u * 2 * T1; if (tt < T1) planeAt(r.A, r.B, tt, _pose); else planeAt(r.B, r.A, tt - T1, _pose);
          v.m.position.set(_pose.x, _pose.y, _pose.z); v.m.rotation.set(0, Math.atan2(-_pose.hz, _pose.hx), _pose.pitch); v.m.scale.setScalar(sc); return; }
        // 배는 두 항구 사이를 오간다(갈 때 u 0~0.5, 올 때 0.5~1). 부두에서 잠깐 멈췄다가 천천히 출발·도착한다
        var ph = u * 2, fwd = ph < 1, pp = fwd ? ph : 2 - ph, dw = r.dwell;
        pp = clamp((pp - dw) / (1 - 2 * dw), 0, 1); var ea = r.ease; pp = pp < ea ? pp * pp / (2 * ea) / (1 - ea) : pp > 1 - ea ? 1 - (1 - pp) * (1 - pp) / (2 * ea) / (1 - ea) : (pp - ea / 2) / (1 - ea);
        r.curve.getPointAt(pp, _tp); r.curve.getTangentAt(pp, _tt);
        v.m.position.set(_tp.x, Math.sin(clock * 1.6 + v.off * 9) * 0.0015, _tp.z); v.m.rotation.set(Math.sin(clock * 1.1 + v.off * 7) * 0.035, Math.atan2(-_tt.z, _tt.x) + (fwd ? 0 : Math.PI), 0); v.m.scale.setScalar(ssc);
      });
    });
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
      if (!POLITICAL) {
        var main = prof.main || n.good, lv = prof.levels && prof.levels[main] ? prof.levels[main] : 0, kind = isMe ? '우리 나라' : stu ? '학생' : prof.evaluated === false ? 'AI 전용' : 'AI';
        l.el.style.minWidth = '104px'; l.el.style.padding = '6px 9px 6px 8px'; l.el.style.borderRadius = '5px'; l.el.style.textAlign = 'left'; l.el.style.boxShadow = '0 3px 12px rgba(7,28,40,0.35)';
        l.el.style.background = isMe ? 'linear-gradient(115deg,rgba(56,92,67,0.94),rgba(33,62,53,0.94))' : 'linear-gradient(115deg,rgba(242,229,188,0.93),rgba(215,199,154,0.93))';
        l.el.style.border = isMe ? '2px solid #efd08b' : '1px solid rgba(147,167,135,0.8)'; l.el.style.color = isMe ? '#fff1c6' : '#1f2a24';
        l.el.innerHTML = '<div style="display:flex;justify-content:space-between;gap:8px;align-items:baseline;"><span style="font-weight:800;font-size:14px;">' + esc(names[n.key] || n.ko) + '</span><span style="font-size:10px;font-weight:600;opacity:0.75;">' + kind + '</span></div><div style="font-size:12px;font-weight:600;margin-top:2px;">' + (GOODS[main] ? GOODS[main].icon + ' ' + GOODS[main].ko : '') + (lv ? ' <b>Lv.' + lv + '</b>' : '') + '</div>';
        return;
      }
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
  if (opts.natBar === false) natBar.style.display = 'none'; // 게임 화면이 좁을 때 아래쪽 나라 버튼 줄을 숨긴다
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

  // ───────────────────────── Tripo 3D 모델 (assets/models/web) ─────────────────────────
  // 코드 도형으로 먼저 그려 두고, 모델이 도착하면 같은 자리에서 바꿔 끼운다(실패해도 도형은 남는다).
  // fit: size = 바닥 최대 변 길이, rot = 세로축 회전, y = 높이 보정(배는 물에 잠기는 깊이), ship = 배(긴 쪽을 x축, 선교를 -x로 돌림)
  var PORT_MODEL = { container: 'port_container', fruit: 'port_fruit', oil: 'port_oil', ore: 'port_ore', grain: 'port_grain' };
  var SHIP_MODEL = { container: 'ship_container', fruit: 'ship_container', oil: 'ship_oil', ore: 'ship_bulk', grain: 'ship_bulk' };
  var PROP_MODEL = { factory: 'prop_factory', tech: 'prop_tech', pump: 'prop_oilfield', mine: 'prop_mine', farm: 'prop_farm', palm: 'prop_plantation' };
  var MODEL_FIT = {
    port_container: { size: 1.9, rot: 0 }, port_fruit: { size: 1.9, rot: 0 }, port_oil: { size: 1.9, rot: 0 }, port_ore: { size: 1.9, rot: 0 }, port_grain: { size: 1.9, rot: Math.PI },
    ship_container: { size: 0.36, ship: true, y: -0.2 }, ship_oil: { size: 0.38, ship: true, y: -0.2 }, ship_bulk: { size: 0.36, ship: true, y: -0.2 },
    prop_factory: { size: 0.36 }, prop_tech: { size: 0.32 }, prop_oilfield: { size: 0.36 }, prop_mine: { size: 0.38 }, prop_farm: { size: 0.38 }, prop_plantation: { size: 0.38 },
    city_capital: { size: 0.72, rot: 0 }, city_harbor_town: { size: 0.44, rot: 0 },
    airport_terminal: { size: 0.5, rot: 0 }, plane_cargo: { size: 0.14, plane: true }
  };
  if (opts.modelFit) Object.keys(opts.modelFit).forEach(function (k) { MODEL_FIT[k] = Object.assign({}, MODEL_FIT[k], opts.modelFit[k]); });
  var modelGroups = [], modelsLoaded = 0, modelsFailed = 0;
  // 압축(양자화)된 속성을 보통 float로 풀어야 r128에서 행렬을 곱할 수 있다
  function toFloatAttr(a) {
    if (!a) return a;
    var src = a.array, n = a.count, k = a.itemSize, out = new Float32Array(n * k), d = 1, get = ['getX', 'getY', 'getZ', 'getW'];
    if (a.normalized) d = src instanceof Int8Array ? 127 : src instanceof Uint8Array ? 255 : src instanceof Int16Array ? 32767 : src instanceof Uint16Array ? 65535 : 1;
    // getX…는 interleaved(바이트 간격 있는) 속성도 제자리에서 읽는다(r128은 정규화를 풀지 않으므로 직접 나눈다)
    for (var i = 0; i < n; i++) for (var c = 0; c < k; c++) { var v = a[get[c]](i); out[i * k + c] = a.normalized ? Math.max(v / d, -1) : v; }
    return new THREE.BufferAttribute(out, k);
  }
  function prepModel(gltf, name) {
    var fit = MODEL_FIT[name] || { size: 0.3 }, src = null;
    gltf.scene.updateMatrixWorld(true);
    gltf.scene.traverse(function (o) { if (o.isMesh && !src) src = o; });
    if (!src) return null;
    var geo = new THREE.BufferGeometry();
    ['position', 'normal', 'uv'].forEach(function (k) { if (src.geometry.attributes[k]) geo.setAttribute(k, toFloatAttr(src.geometry.attributes[k])); });
    if (src.geometry.index) geo.setIndex(src.geometry.index);
    geo.applyMatrix4(src.matrixWorld);
    geo.computeBoundingBox(); var b = geo.boundingBox;
    if (fit.ship) {
      // 긴 쪽을 x축으로, 높은 구조물(선교)이 많은 쪽을 -x(배 뒤)로
      if (b.max.z - b.min.z > b.max.x - b.min.x) geo.rotateY(Math.PI / 2);
      geo.computeBoundingBox(); b = geo.boundingBox;
      var p = geo.attributes.position, hy = b.min.y + (b.max.y - b.min.y) * 0.6, cx = (b.min.x + b.max.x) / 2, front = 0, back = 0;
      for (var i = 0; i < p.count; i++) if (p.getY(i) > hy) { if (p.getX(i) > cx) front++; else back++; }
      if ((front > back) !== !!fit.flip) geo.rotateY(Math.PI);
    }
    if (fit.plane) {
      // 꼬리 날개(가장 높은 부분)가 있는 쪽이 뒤: 동체를 x축으로, 기수를 +x로 돌린다
      var pp = geo.attributes.position, ty = b.min.y + (b.max.y - b.min.y) * 0.7, mx = (b.min.x + b.max.x) / 2, mz = (b.min.z + b.max.z) / 2, sx = 0, sz = 0, nt = 0;
      for (var pi3 = 0; pi3 < pp.count; pi3++) if (pp.getY(pi3) > ty) { sx += pp.getX(pi3) - mx; sz += pp.getZ(pi3) - mz; nt++; }
      if (nt) { sx /= nt; sz /= nt; if (Math.abs(sz) > Math.abs(sx)) { geo.rotateY(Math.PI / 2); var tmp = sx; sx = sz; sz = -tmp; } if (sx > 0) geo.rotateY(Math.PI); }
      geo.computeBoundingBox(); b = geo.boundingBox;
    }
    if (fit.rot) geo.rotateY(fit.rot);
    geo.computeBoundingBox(); b = geo.boundingBox;
    var sc = fit.size / Math.max(b.max.x - b.min.x, b.max.z - b.min.z, 1e-6), hgt = (b.max.y - b.min.y) * sc;
    geo.translate(-(b.min.x + b.max.x) / 2, -b.min.y, -(b.min.z + b.max.z) / 2); geo.scale(sc, sc, sc);
    geo.translate(0, (fit.y || 0) * hgt, 0);
    if (!geo.attributes.normal) geo.computeVertexNormals();
    geo.computeBoundingBox(); geo.computeBoundingSphere();
    var map = src.material && src.material.map ? src.material.map : null;
    if (map) { map.encoding = THREE.LinearEncoding; map.anisotropy = renderer.capabilities.getMaxAnisotropy(); map.needsUpdate = true; }
    var mat = new THREE.MeshLambertMaterial({ map: map, color: map ? 0xffffff : 0xcccccc });
    return { geo: geo, mat: mat };
  }
  function applyModel(name, m) {
    if (PROP_MODEL) Object.keys(PROP_MODEL).forEach(function (t) { if (PROP_MODEL[t] === name && propMesh[t]) { propMesh[t].geometry = m.geo; propMesh[t].material = m.mat; } });
    ports.forEach(function (p) {
      if (PORT_MODEL[p.type] === name) {
        var pm = new THREE.Mesh(m.geo, m.mat); pm.castShadow = true; pm.receiveShadow = true; p.g.add(pm); p.model = pm;
        p.term.visible = false; if (!p.custom) p.slot.visible = false; if (p.flame) p.flame.visible = false;
      }
      if (SHIP_MODEL[p.type] === name) p.ships.forEach(function (s) { s.m.geometry = m.geo; s.m.material = m.mat; });
    });
    if (name.indexOf('ship_') === 0) { SHIPGEO[name] = m; routes.forEach(function (r) { r.vehicles.forEach(function (v) { if (v.model === name) { if (v.own) v.m.geometry.dispose(); v.m.geometry = m.geo; v.m.material = m.mat; v.own = false; } }); }); }
    if (name === 'plane_cargo') { PLANE_MODEL = m; PLANE_MESHES.forEach(function (pm) { pm.geometry.dispose(); pm.geometry = m.geo; pm.material = m.mat; }); routes.forEach(function (r) { r.vehicles.forEach(function (v) { if (v.plane) v.own = false; }); }); }
    if (name === 'airport_terminal' && AIRPORTS.length) {
      var ag = new THREE.Group();
      AIRPORTS.forEach(function (ap) { var am = new THREE.Mesh(m.geo, m.mat), c0 = Math.cos(ap.ry), s0 = Math.sin(ap.ry); am.castShadow = true; am.receiveShadow = true; am.position.set(ap.x + 0.05 * c0 + 0.36 * s0, ap.h - 0.004, ap.z - 0.05 * s0 + 0.36 * c0); am.rotation.y = ap.ry; ag.add(am); });
      if (AP_BLD) { AP_BLD.visible = false; var bi = cityMeshes.indexOf(AP_BLD); if (bi >= 0) cityMeshes.splice(bi, 1); }
      scene.add(ag); cityMeshes.push(ag); modelGroups.push(ag);
    }
    if (name === 'city_capital' || name === 'city_harbor_town') {
      var grp = new THREE.Group();
      SETTLE.forEach(function (s) {
        if (s.capital !== (name === 'city_capital')) return;
        var cm = new THREE.Mesh(m.geo, m.mat); cm.castShadow = true; cm.receiveShadow = true;
        cm.position.set(s.x, heightAt(s.x, s.z) - 0.02, s.z); cm.rotation.y = -(s.ang || 0); grp.add(cm);
      });
      scene.add(grp); cityMeshes.push(grp); modelGroups.push(grp);
    }
  }
  if (USE_MODELS) {
    var _ml = new opts.GLTFLoader(); _ml.setMeshoptDecoder(opts.MeshoptDecoder);
    Object.keys(MODEL_FIT).forEach(function (name) {
      _ml.load(MODEL_BASE + name + '.glb', function (g) {
        var m = prepModel(g, name); if (m) { applyModel(name, m); modelsLoaded++; } else modelsFailed++;
      }, undefined, function (err) { modelsFailed++; console.warn('[world-map] 모델 불러오기 실패:', name, err && err.message ? err.message : err); });
    });
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
    port.slot.children.forEach(function (ch) { ch.visible = false; }); port.slot.visible = true;
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
  var HOME = [-10 * S, 2 * S, 185 * S], target = new THREE.Vector3(HOME[0], GROUND_Y, HOME[1]), dist = HOME[2], fly = null;
  if (opts.start) { target.x = opts.start[0]; target.z = opts.start[1]; dist = opts.start[2]; }
  var raycaster = new THREE.Raycaster(), groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -GROUND_Y), _ndc = new THREE.Vector2();
  // 레이어(숲·도시·항구·정치 색)는 실제 카메라 거리로 정한다(세계 크기를 바꿔도 같은 거리에서 같은 것이 보이게)
  function layerZ() { return (Math.log(dist) - Math.log(DMIN)) / (Math.log(190) - Math.log(DMIN)); }
  function zoomT() { return (Math.log(dist) - Math.log(DMIN)) / (Math.log(DMAX) - Math.log(DMIN)); }
  function tiltFor(z) { return (FAR_TILT + (58 - FAR_TILT) * (1 - sstep(0.12, 0.88, z))) * Math.PI / 180; }
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
    var z = layerZ(), polMix = POLITICAL ? sstep(0.55, 0.78, z) : 0, detail = 1 - sstep(0.3, 0.6, z);
    terrU.uMix.value = polMix; terrU.uRelief.value = POLITICAL ? 0 : sstep(0.25, 0.6, z); terrU.uDetail.value = detail; terrU.uBorder.value = sstep(0.3, 0.5, z);
    oceanMat.color.copy(OCEAN_POL).lerp(OCEAN_NAT, 1 - polMix); oceanMat.opacity = POLITICAL ? lerp(0.72, 0.96, polMix) : lerp(0.72, 0.9, sstep(0.35, 0.7, z));
    seaU.uGame.value = 1 - polMix; seaU.uTime.value = clock; updateClouds(z, dt);
    oceanMat.specular.setScalar(0.35 * detail); oceanMat.normalScale.set(0.6 * detail, 0.6 * detail);
    waveTex.offset.x += dt * 0.004; waveTex.offset.y += dt * 0.0025; riverTex.offset.x -= dt * 0.35; riverMat.normalScale.set(0.3 * detail + 0.05, 0.3 * detail + 0.05); riverW.value = Math.min(0.2, dist * 0.0022);
    scene.fog.near = dist * 1.7; scene.fog.far = dist * 5.5;
    var sh = clamp(dist * 0.75, 1.2, 9); sun.shadow.camera.left = -sh; sun.shadow.camera.right = sh; sun.shadow.camera.top = sh; sun.shadow.camera.bottom = -sh; sun.shadow.camera.near = 0.1; sun.shadow.camera.far = 60; sun.shadow.camera.updateProjectionMatrix();
    sun.position.set(target.x + SUN_DIR.x * 25, SUN_DIR.y * 25, target.z + SUN_DIR.z * 25); sun.target.position.set(target.x, 0, target.z); sun.target.updateMatrixWorld();
    var rOp = sstep(0.38, 0.55, z); routeW.value = dist * 0.0017;
    updateTraffic(rOp);
    legend.style.display = rOp > 0.3 && opts.legend !== false ? 'block' : 'none'; if (legendDirty) refreshLegend();
    updateTrees(z);
    if (growT < 1) growT = Math.min(1, growT + dt * 2.2); growU.value = sstep(0, 1, growT);
    var propVis = z < 0.63; // 항구·산업 건물도 마을 집과 같은 거리에서 함께 보인다(따로 튀어나오지 않게)
    PROP_TYPES.forEach(function (t) { propMesh[t].visible = propVis; });
    ports.forEach(function (p) {
      var dx = p.n.port.x - target.x, dz = p.n.port.z - target.z; p.g.visible = propVis && dx * dx + dz * dz < Math.pow(dist * 2.2 + 4, 2);
      if (!p.g.visible) return;
      if (p.flame) { var f = 0.85 + Math.sin(clock * 23 + p.n.i) * 0.12 + Math.sin(clock * 37) * 0.08; p.flame.scale.set(f, f * 1.2, f); }
    });
    var cityVis = z < 0.63; cityMeshes.forEach(function (m) { m.visible = cityVis; }); if (cityVis) updateDeco(clock);
    var farVis = !POLITICAL && z >= 0.6; FAR_CITY.forEach(function (m) { m.visible = farVis; }); farCityU.value = Math.max(1, dist / 24); // 가까이서는 진짜 집, 멀리서는 커지는 집 덩어리
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
    home: HOME.slice(), worldScale: S,
    getState: function () { return { x: target.x, z: target.z, dist: dist, zoom: zoomT(), trees: treeCount, calls: renderer.info.render.calls, routes: routes.length, buildings: bldCount, deco: Object.keys(DECO).reduce(function (n, t) { return n + DECO[t].length; }, 0), settlements: SETTLE.length, airports: AIRPORTS.length, traffic: routes.reduce(function (n, r) { return n + r.vehicles.length; }, 0), airRoutes: routes.filter(function (r) { return r.air; }).length, vehicles: [].concat.apply([], routes.map(function (r) { return r.vehicles.map(function (v) { return [Math.round(v.m.position.x * 10) / 10, Math.round(v.m.position.y * 100) / 100, Math.round(v.m.position.z * 10) / 10, r.air ? 1 : 0]; }); })), rivers: RIVERS.map(function (r) { return [Math.round(r.pts[0][0] * 10) / 10, Math.round(r.pts[0][1] * 10) / 10, r.pts.length]; }), props: PROP_TYPES.reduce(function (s, t) { return s + propMesh[t].count; }, 0) }; },
    nations: NATIONS.map(function (n) { return { key: n.key, ko: n.ko, good: n.good, port: { x: n.port.x, z: n.port.z }, center: { x: n.cx, z: n.cz }, cells: n.cells }; }),
    settlements: SETTLE.map(function (s) { return { nation: s.n.key, capital: s.capital, port: !!s.port, noRoad: !!s.noRoad, x: s.x, z: s.z, r: s.R }; }),
    roads: function () { return ROADS.filter(function (r) { return r.pts; }).map(function (r) { return { w: r.w, pts: r.pts }; }); },
    loadFile: loadFile, placeModel: placeModel,
    landAt: landAt, // 확인용: 0보다 크면 땅
    decoSpots: function (t) { return (DECO[t] || []).map(function (a) { return [a[0], a[2]]; }); }, // 확인용: 풍경 물건 자리
    setRoutesVisible: function (v) { routeGroup.visible = !!v; legend.style.visibility = v ? '' : 'hidden'; },
    models: function () { return { loaded: modelsLoaded, failed: modelsFailed, total: USE_MODELS ? Object.keys(MODEL_FIT).length : 0 }; },
    dispose: function () {
      cancelAnimationFrame(raf); if (demo && demo.timer) clearInterval(demo.timer); if (ro) ro.disconnect(); else window.removeEventListener('resize', onResize);
      clearRoutes(); scene.traverse(function (o) { if (o.geometry) o.geometry.dispose(); });
      renderer.dispose(); if (canvas.parentNode) canvas.parentNode.removeChild(canvas); if (ui.parentNode) ui.parentNode.removeChild(ui);
    }
  };
}
