import { serverList, countOnline, LOCAL_FLAG } from './transport.js';
import { $, esc, render } from './dom.js';
import { applyMapBackground } from './world-map.js';

applyMapBackground($('#title-map'));

if (LOCAL_FLAG) for (const link of document.querySelectorAll('.entry')) link.search = '?local=1';

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
