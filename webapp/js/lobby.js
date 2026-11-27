import { serverList, countOnline, LOCAL_FLAG } from './transport.js';
import { $, esc, render } from './dom.js';
import { applyMapBackground } from './world-map.js';
import { uiIcon } from './good-icons.js';

// 메뉴 아이콘(그린 아이콘)
for (const el of document.querySelectorAll('[data-icon]')) el.innerHTML = uiIcon(el.dataset.icon);
if (LOCAL_FLAG) for (const link of document.querySelectorAll('.entry')) link.search = '?local=1';

// 배경: 3D 세계 지도(게임과 같은 지도, 조작 버튼 없음). 무역 연습 장면(demo)으로 배·비행기가 오가고,
// 카메라가 나라들 사이를 천천히 날아다닌다. WebGL이 안 되면 2D 지도 그림을 깐다.
(async function titleWorld() {
  const host = $('#title-map');
  try {
    const { createWorld } = await import('./world-engine.js');
    const world = await createWorld(host, { panel: false, political: false, theme: 'game', controls: false, demo: true, demoInterval: 9000 });
    host.classList.add('live');
    const keys = world.nations.map((n) => n);
    const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
    let i = Math.floor(Math.random() * keys.length);
    const hop = () => { const n = keys[i++ % keys.length]; world.flyTo(n.center.x, n.center.z, 46, calm ? 0.01 : 7); };
    hop(); if (!calm) setInterval(hop, 11000);
  } catch (e) {
    applyMapBackground(host); // 3D가 안 되는 기기
  }
})();

const servers = serverList();
let reading = false;
async function draw() {
  if (reading) return;
  reading = true;
  try {
    const rows = await Promise.all(servers.map(async (s) => {
      let count;
      try { count = await countOnline(s); } catch { /* Show an unknown count. */ }
      const known = typeof count === 'number';
      const full = known && count >= s.capacity;
      return `<li><strong>${esc(s.name)}</strong><span>${known ? count : '?'}명 / ${s.capacity}명</span>
        <span class="tag ${full ? 'attention' : ''}">${!known ? '접속 확인 안 됨' : full ? '가득 참' : '여유 있음'}</span></li>`;
    }));
    render($('#servers'), `<ul class="server-list">${rows.join('')}</ul>`, {});
  } finally { reading = false; }
}
draw();
setInterval(draw, 15000);
