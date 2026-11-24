// 지도 묶음 만들기: node webapp/map/build.mjs
//   world-map.js              웹앱 화면에서 import 하는 ES 모듈 (THREE는 호출할 때 넘김)
//   index.html                데모 페이지 (vendor/의 three r128 사용, GitHub Pages에서 바로 열림)
//   dist/world-map-demo.html  한 파일짜리 데모 (three는 CDN) — PC용
//   dist/world-map-demo.jsx   iPad(claude.ai 아티팩트) 테스트용 — GLB 불러오기 없음
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const DIR = path.dirname(fileURLToPath(import.meta.url));
const core = fs.readFileSync(path.join(DIR, 'src/map-core.js'), 'utf8');
const banner = '// 자동 생성 파일 — 고치려면 webapp/map/src/map-core.js를 고치고 `node webapp/map/build.mjs`를 실행한다.\n';
const CDN = 'https://cdn.jsdelivr.net/npm/three@0.128.0';

fs.writeFileSync(path.join(DIR, 'world-map.js'), banner + core + '\nexport { createWorldMap };\nexport default createWorldMap;\n');

const head = (title) => `<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>${title}</title>
<link rel="icon" href="data:,">
<style>html,body{margin:0;height:100%;background:#cfe0ea;overflow:hidden;overscroll-behavior:none;}#map{position:fixed;inset:0;}</style>
</head>
<body>
<div id="map"></div>
`;
// 주소 뒤 옵션: ?me=Tropia (우리 나라 표시), ?nodemo (가짜 거래 끄기), ?panel=0 (설명 패널 숨김)
const startJs = `
  var Q = new URLSearchParams(location.search);
  window.worldMap = createWorldMap(document.getElementById('map'), THREE, {
    demo: !Q.has('nodemo'), me: Q.get('me') || null, panel: Q.get('panel') !== '0',
    GLTFLoader: THREE.GLTFLoader, preserve: Q.has('test'), demoInterval: Q.has('test') ? 600000 : 8000
  });
`;

fs.writeFileSync(path.join(DIR, 'index.html'), head('무역 게임 세계 지도') + `<script src="vendor/three.min.js"></script>
<script src="vendor/GLTFLoader.js"></script>
<script type="module">
  import { createWorldMap } from './world-map.js';${startJs}</script>
</body>
</html>
`);

fs.mkdirSync(path.join(DIR, 'dist'), { recursive: true });
fs.writeFileSync(path.join(DIR, 'dist/world-map-demo.html'), head('무역 게임 세계 지도 (데모)') + `<script src="${CDN}/build/three.min.js"></script>
<script src="${CDN}/examples/js/loaders/GLTFLoader.js"></script>
<script>
${core}
${startJs}</script>
</body>
</html>
`);

fs.writeFileSync(path.join(DIR, 'dist/world-map-demo.jsx'), `// 무역 게임 세계 지도 데모 (iPad 테스트용). 자동 생성 — 원본은 webapp/map/src/map-core.js
// GLB 불러오기는 HTML 버전에서만 된다(이 환경엔 GLTFLoader가 없다).
import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';

${core}

export default function TradeWorldMap() {
  const ref = useRef(null);
  useEffect(() => {
    const map = createWorldMap(ref.current, THREE, { demo: true, me: 'Tropia' });
    return () => map.dispose();
  }, []);
  return <div ref={ref} style={{ position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh', background: '#cfe0ea', overflow: 'hidden', touchAction: 'none' }} />;
}
`);
for (const f of ['world-map.js', 'index.html', 'dist/world-map-demo.html', 'dist/world-map-demo.jsx']) console.log(f, fs.statSync(path.join(DIR, f)).size);
