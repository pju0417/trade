// Solo play ("혼자 해 보기"): one person plays one or more countries against the AI on this
// device. The engine runs in this page (ClassHost on the local test server, one room) and every
// chosen country gets the normal student screen in an iframe that joins automatically.
// Nothing is sent to Firebase. Games are saved in this browser under their own prefix, so they
// do not appear in the teacher screen's "이어하기" list.
import { EngineClient } from './engine-client.js';
import { ClassHost, ORIGINAL, savedClasses } from './host.js';
import { openServer, LOCAL_FLAG } from './transport.js';
import { esc, $, render, num } from './dom.js';

// The local test server is offered only with ?local=1 (transport.js), so make sure it is there.
if (!LOCAL_FLAG) location.replace('play.html?local=1');

const KO = { Tropia: '트로피아', Grainia: '그레니아', Oilia: '오일리아', Mechania: '메카니아', Mineria: '미네리아', Technia: '테크니아' };
const PHASE = { listing: '판매 등록', trading: '거래', invest: '투자', finished: '끝' };
const PREFIX = 'trade-play:';
const storage = {
  get: (k) => localStorage.getItem(PREFIX + k),
  set: (k, v) => localStorage.setItem(PREFIX + k, v),
  remove: (k) => localStorage.removeItem(PREFIX + k),
  keys: () => Array.from({ length: localStorage.length }, (_, i) => localStorage.key(i))
    .filter((k) => k && k.startsWith(PREFIX)).map((k) => k.slice(PREFIX.length)),
};
// Ready → next phase right away; round 1 is not teacher-led; no phase timer.
const SETTINGS = { mode: 'ready', firstRoundTeacher: false, countdownSec: 1, timer: { listing: 0, trading: 0, invest: 0 } };

const drafts = { seed: '' };
let engine = null;
let status = '엔진을 불러오는 중…(처음에는 10초쯤 걸릴 수 있어요)';
let lastMsg = '';
let cls = null;
let S = null;
let shown = null;

function setup() {
  $('#bar').hidden = true;
  $('#frames').innerHTML = '';
  $('#app').hidden = false;
  const saved = savedClasses(storage);
  render($('#app'), `
    <header class="cover host-cover">
      <a class="back" href="index.html">← 첫 화면</a>
      <p class="eyebrow">무역 게임 · 혼자 해 보기</p><h1>시뮬레이션 플레이</h1>
      <p>내가 맡을 나라를 고르면 나머지 나라는 AI가 맡아요. 이 기기 안에서만 돌아가고 서버에 접속하지 않아요.</p>
      <p role="status">${esc(status)}</p>
    </header>
    <section class="panel"><h2>새 게임</h2>
    <fieldset><legend>내가 맡을 나라 (여러 개 고르면 위쪽 버튼으로 오가며 해요)</legend><div class="choices">
      ${ORIGINAL.map((n, i) => `<label class="choice"><input type="checkbox" class="stu" data-k="stu-${n}" value="${n}" ${i === 0 ? 'checked' : ''}> ${KO[n]}</label>`).join('')}
    </div></fieldset>
    <p><label>시드(비우면 무작위, 같은 시드 = 같은 시작) <input data-k="seed" type="number" min="0" size="10"></label></p>
    <p><small>내가 맡은 나라가 모두 "준비 완료"를 누르면 바로 다음 단계로 넘어가요. 위쪽의 "다음 단계"로 언제든 넘길 수도 있어요. 시간 제한은 없어요.</small></p>
    <p><button data-act="new" ${engine ? '' : 'disabled'}>게임 시작</button></p>
    </section>
    ${saved.length ? `<section class="panel"><h2>이어하기</h2><ul class="saved-list">${saved.map((m) => {
      const room = JSON.parse(storage.get('trade-room-' + m.rooms[0]) || '{}');
      return `<li>${(room.students || []).map((n) => KO[n]).join('·')} · 시드 ${room.seed ?? '?'} · ${esc(m.saved)}
      <button data-act="resume" data-cls="${esc(m.cls)}" ${engine ? '' : 'disabled'}>이어하기</button>
      <button data-act="forget" data-cls="${esc(m.cls)}">삭제</button></li>`;
    }).join('')}</ul></section>` : ''}
    <p id="msg" role="status">${esc(lastMsg)}</p>`, drafts);
}

function studentSrc(code, country, pin) {
  return `student.html?room=${encodeURIComponent(code)}&country=${country}&pin=${pin}&local=1`;
}

function bar() {
  if (!S || !S.rooms.length) return;
  const r = S.rooms[0];
  const v = r.view;
  const mine = Object.keys(r.tokens);
  const ready = r.info.ready;
  render($('#bar'), `
    <span><b>${v.phase === 'finished' ? '게임 끝' : `${v.round}라운드 · ${PHASE[v.phase]}`}</b></span>
    <span>준비 ${ready.length}/${r.info.need.length}${r.info.countdown_ms !== null ? ' · 곧 넘어가요' : ''}</span>
    <span class="play-tabs">${mine.map((n) => `<button data-act="show" data-country="${n}" aria-pressed="${shown === n}">${KO[n]}${ready.includes(n) ? ' ✓' : ''}</button>`).join('')}</span>
    <span class="grow"></span>
    <small>시드 ${v.seed}</small>
    ${v.phase === 'finished' ? '' : '<button data-act="adv">다음 단계</button>'}
    <button data-act="export">기록 내려받기</button>
    <button data-act="leave">처음 화면</button>`, drafts);
}

function frames() {
  const r = S.rooms[0];
  const box = $('#frames');
  for (const [n, pin] of Object.entries(r.tokens)) {
    let f = box.querySelector(`iframe[data-country="${n}"]`);
    if (!f) {
      f = Object.assign(document.createElement('iframe'), { src: studentSrc(r.code, n, pin), title: `${KO[n]} 학생 화면` });
      f.dataset.country = n;
      box.appendChild(f);
    }
    f.hidden = n !== shown;
  }
}

function onSummary(s) {
  S = s;
  if (!shown && S.rooms.length) shown = Object.keys(S.rooms[0].tokens)[0];
  bar();
}

async function start(fn) {
  const server = await openServer('L');
  cls = new ClassHost({ engine, server, storage, onChange: onSummary });
  await fn(cls);
  cls.startTicker(300);
  $('#app').hidden = true;
  $('#bar').hidden = false;
  shown = null;
  onSummary(cls.summary());
  frames();
}

async function stop() {
  if (cls) await cls.finish({ clearServer: false });
  cls = null; S = null; shown = null;
}

async function act(el) {
  const a = el.dataset.act;
  if (a === 'new') {
    const students = [...document.querySelectorAll('.stu')].filter((b) => b.checked).map((b) => b.value);
    if (!students.length) { lastMsg = '나라를 1개 이상 골라 주세요.'; return setup(); }
    const seed = drafts.seed === '' ? null : num(drafts.seed);
    if (seed !== null && !(seed >= 0)) { lastMsg = '시드는 0 이상의 정수예요.'; return setup(); }
    lastMsg = '게임을 만드는 중…'; setup();
    try { await start((c) => c.create({ students, rooms: 1, settings: SETTINGS, seeds: seed === null ? null : [seed] })); lastMsg = ''; }
    catch (e) { lastMsg = e.message; await stop(); setup(); }
    return;
  }
  if (a === 'resume') {
    const meta = savedClasses(storage).find((m) => m.cls === el.dataset.cls);
    lastMsg = '기록을 다시 재생하는 중…'; setup();
    try { await start((c) => c.restore(meta)); lastMsg = ''; }
    catch (e) { lastMsg = '이어하지 못했어요: ' + e.message; await stop(); setup(); }
    return;
  }
  if (a === 'forget') {
    if (!confirm('이 게임 기록을 지울까요?')) return;
    const meta = savedClasses(storage).find((m) => m.cls === el.dataset.cls);
    for (const code of meta.rooms) storage.remove('trade-room-' + code);
    storage.remove('trade-class-' + meta.cls);
    return setup();
  }
  if (!cls) return;
  const code = S.rooms[0].code;
  if (a === 'show') { shown = el.dataset.country; frames(); bar(); }
  else if (a === 'adv') {
    if (S.rooms[0].view.pending_offers && !confirm('기다리는 제안이 있어요. 거래 단계가 끝나면 취소돼요. 넘어갈까요?')) return;
    const r = await cls.advance(code); if (!r.ok) alert(r.msg);
  } else if (a === 'export') {
    const data = await cls.room(code).exportLog();
    const u = URL.createObjectURL(new Blob([JSON.stringify(data)], { type: 'application/json' }));
    Object.assign(document.createElement('a'), { href: u, download: `trade-play-seed${data.seed}.json` }).click();
    URL.revokeObjectURL(u);
  } else if (a === 'leave') { await stop(); lastMsg = '이어하기에서 다시 열 수 있어요.'; setup(); }
}

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-act]');
  if (el) { e.preventDefault(); el.disabled = true; act(el).catch((err) => { lastMsg = err.message; if (!cls) setup(); else alert(err.message); }).finally(() => { el.disabled = false; }); }
});

setup();
engine = new EngineClient();
engine.init().then((info) => { status = `엔진 준비됨 (Python ${info.python.split(' ')[0]})`; if (!cls) setup(); })
  .catch((e) => { status = '엔진을 불러오지 못했어요: ' + e.message; if (!cls) setup(); });
