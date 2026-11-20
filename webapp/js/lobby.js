// First page: links and each server's current head count (read without a lasting connection).
import { serverList, countOnline } from './transport.js';
import { esc } from './dom.js';

const servers = serverList();
async function draw() {
  const rows = [];
  for (const s of servers) {
    let n = '?';
    try { n = await countOnline(s); } catch (e) { /* unreachable server */ }
    const full = typeof n === 'number' && n >= s.capacity;
    rows.push(`<tr><td>${esc(s.name)}</td><td>${n}명 / ${s.capacity}명</td><td>${full ? '<b>가득 참</b>' : '여유 있음'}</td></tr>`);
  }
  document.querySelector('#servers').innerHTML = `<table><tr><th>서버</th><th>지금 접속</th><th></th></tr>${rows.join('')}</table>`;
}
draw();
setInterval(draw, 15000);
