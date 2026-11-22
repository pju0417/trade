// Teacher setup and classroom dashboard.
import { EngineClient } from './engine-client.js';
import { ClassHost, ORIGINAL, DEFAULT_SETTINGS, browserStorage, savedClasses } from './host.js';
import { openServer, serverList, countOnline, LOCAL_FLAG } from './transport.js';
import { esc, $, render, fmt, num } from './dom.js';

const KO = { Tropia: '트로피아', Grainia: '그레니아', Oilia: '오일리아', Mechania: '메카니아', Mineria: '미네리아', Technia: '테크니아' };
const PHASE = { listing: '판매 등록', trading: '거래', invest: '투자', finished: '끝' };
const MODE = { teacher: '선생님이 넘김', ready: '모두 준비하면 넘어감', ready_timer: '모두 준비하거나 시간이 끝나면 넘어감' };
const drafts = {};
let engine = null;
let cls = null;
let S = null; // latest class summary
let summaryAt = 0;
let selected = null;
let status = '엔진을 불러오는 중…(처음에는 10초쯤 걸릴 수 있어요)';
let lastMsg = '';
let counts = {}; // server id -> online count (or error text)

const servers = serverList();
const isLocal = servers.every((s) => s.local);

async function refreshCounts() {
  for (const s of servers) {
    try { counts[s.id] = await countOnline(s); } catch (e) { counts[s.id] = '?'; }
  }
  if (!cls) setup();
}

const mmss = (ms) => (ms === null || ms === undefined ? '-' : `${Math.floor(ms / 60000)}:${String(Math.floor((ms % 60000) / 1000)).padStart(2, '0')}`);

function setup() {
  if (drafts.rooms === undefined) Object.assign(drafts, {
    rooms: '1', mode: DEFAULT_SETTINGS.mode, first: 'yes', countdown: String(DEFAULT_SETTINGS.countdownSec),
    t_listing: String(DEFAULT_SETTINGS.timer.listing), t_trading: String(DEFAULT_SETTINGS.timer.trading), t_invest: String(DEFAULT_SETTINGS.timer.invest),
    server: (servers.find((s) => s.local && LOCAL_FLAG) || servers[0]).id, expected: '',
  });
  const saved = savedClasses(browserStorage);
  render($('#app'), `
    <header class="cover host-cover">
      <a class="back" href="index.html${LOCAL_FLAG ? '?local=1' : ''}">← 첫 화면</a>
      <p class="eyebrow">무역 게임 · 선생님</p><h1>수업 준비</h1>
      <p role="status">${esc(status)}</p>
    </header>
    <section class="panel">
    ${isLocal ? '<p><b>로컬 시험 모드</b> — 같은 브라우저의 다른 탭에서 학생 화면을 열어 주세요.</p>' : ''}
    <h2>서버</h2>
    <div class="card-grid">${servers.map((s) => `<label class="choice good-card"><input type="radio" name="srv" value="${s.id}" ${drafts.server === s.id ? 'checked' : ''}>
      <span><strong>${esc(s.name)}</strong><small>지금 접속 ${typeof counts[s.id] === 'number' ? counts[s.id] + '명' : '확인 중 또는 알 수 없음'} · 정원 ${s.capacity}명</small></span></label>`).join('')}</div>
    <p><button data-act="counts">접속 인원 새로 보기</button></p>
    </section><section class="panel"><h2>새 수업</h2>
    <p><label>방 개수 <input data-k="rooms" type="number" min="1" max="20" size="3"></label>
       (한 방 = 한 게임. 학생이 많으면 방을 여러 개 만들고, 한 나라를 모둠이 함께 맡을 수 있어요)</p>
    <fieldset><legend>방마다 학생이 맡을 나라</legend><div class="choices">${ORIGINAL.map((n, i) => `<label class="choice"><input type="checkbox" class="stu" data-k="stu-${n}" value="${n}" ${i % 2 === 0 ? 'checked' : ''}> ${KO[n]}</label>`).join('')}</div></fieldset>
    <p><label>예상 학생 수(접속 기기 수) <input data-k="expected" type="number" min="1" size="4" placeholder="자동"></label></p>
    <div class="fields"><label>진행 방식 <select data-k="mode">${Object.entries(MODE).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select></label>
       <label>첫 라운드 <select data-k="first"><option value="yes">1라운드는 선생님이 넘김</option><option value="no">1라운드도 같은 방식</option></select></label></div>
    <fieldset><legend>단계 시간 (초)</legend><div class="fields">
      <label>판매 등록 <input data-k="t_listing" type="number" min="0"></label>
      <label>거래 <input data-k="t_trading" type="number" min="0"></label>
      <label>투자 <input data-k="t_invest" type="number" min="0"></label>
      <label>모두 준비 후 기다림 <input data-k="countdown" type="number" min="0" max="30"></label>
    </div></fieldset>
    <p><button data-act="new" ${engine ? '' : 'disabled'}>수업 만들기</button></p>
    </section>${saved.length ? `<section class="panel"><h2>이어하기</h2><ul class="saved-list">${saved.map((m) => `<li>수업 ${esc(m.cls)} · 서버 ${esc(m.server)} · 방 ${m.rooms.length}개 · ${esc(m.saved)}
      <button data-act="resume" data-cls="${esc(m.cls)}" ${engine ? '' : 'disabled'}>이어하기</button>
      <button data-act="forget" data-cls="${esc(m.cls)}">기록 삭제</button></li>`).join('')}</ul></section>` : ''}
    <p id="msg" role="status">${esc(lastMsg)}</p>`, drafts);
  for (const r of document.querySelectorAll('input[name="srv"]')) r.onchange = () => { drafts.server = r.value; };
}

function studentLink(code, country) {
  const u = new URL('student.html', location.href);
  u.search = `?room=${encodeURIComponent(code)}&country=${country}${code.startsWith('L-') ? '&local=1' : ''}`;
  return u.href;
}

function leftMs(info, key) {
  const v = info[key];
  if (v === null || v === undefined) return null;
  return info.paused ? v : Math.max(0, v - (Date.now() - summaryAt));
}

function dashboard() {
  if (!S) return;
  const srv = servers.find((s) => s.id === S.server) || servers[0];
  const rows = S.rooms.map((r, i) => {
    const v = r.view; const info = r.info;
    return `<article class="room-card">
      <header><h3>${i + 1}번 방</h3><span class="tag">${esc(r.code)}</span></header>
      <p class="room-phase">${v.round}R ${PHASE[v.phase]}</p>
      <p>${esc(MODE[info.mode])}</p>
      <dl class="metrics"><div><dt>남은 시간</dt><dd class="clock" data-room="${esc(r.code)}" data-time="deadline_ms"></dd></div>
      <div><dt>준비한 나라</dt><dd>${info.ready.length}/${info.need.length}</dd></div>
      <div><dt>접속</dt><dd>${r.online.length}대</dd></div><div><dt>기다리는 제안</dt><dd>${v.pending_offers}개</dd></div></dl>
      <p class="clock next-clock" data-room="${esc(r.code)}" data-time="countdown_ms"></p>
      <div class="actions">${v.phase === 'finished' ? '' : `<button data-act="adv" data-code="${esc(r.code)}">이 방 다음 단계</button>`}
      <button data-act="sel" data-code="${esc(r.code)}" aria-expanded="${selected === r.code}">자세히</button></div>
    </article>`;
  }).join('');
  const room = S.rooms.find((r) => r.code === selected);
  render($('#app'), `
    <header class="cover host-cover"><p class="eyebrow">${esc(srv.name)} · 접속 ${S.server_online}/${srv.capacity}명</p>
      <h1>수업 ${esc(S.cls)} ${S.paused ? '<span class="tag attention">일시정지</span>' : ''}</h1>
      <div class="actions primary-actions"><button data-act="advall">모든 방 다음 단계</button>
       <button data-act="${S.paused ? 'resume-all' : 'pause'}">${S.paused ? '다시 시작' : '모든 방 일시정지'}</button></div>
      <div class="actions secondary-actions"><button data-act="pins" aria-expanded="${Boolean(drafts.showPins)}">접속 정보 전체 보기</button>
       <button data-act="finish">수업 끝내기</button><button data-act="leave">처음 화면으로</button></div>
    </header>
    <p id="msg" role="status">${esc(lastMsg)}</p>
    <section class="panel"><h2>방 현황</h2><div class="room-grid">${rows}</div></section>
    <section class="panel"><h2>진행 설정</h2><div class="fields">
     <label>진행 방식 <select data-k="d_mode">${Object.entries(MODE).map(([k, t]) => `<option value="${k}" ${k === S.settings.mode ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
     <label>첫 라운드 <select data-k="d_first"><option value="yes" ${S.settings.firstRoundTeacher ? 'selected' : ''}>1라운드는 선생님이 넘김</option><option value="no" ${S.settings.firstRoundTeacher ? '' : 'selected'}>1라운드도 같은 방식</option></select></label>
     <label>판매 (초) <input data-k="d_tl" type="number" value="${S.settings.timer.listing}"></label>
     <label>거래 (초) <input data-k="d_tt" type="number" value="${S.settings.timer.trading}"></label>
     <label>투자 (초) <input data-k="d_ti" type="number" value="${S.settings.timer.invest}"></label>
     <button data-act="settings">적용</button></div><p><small>설정을 바꾸면 지금 단계의 시간을 처음부터 다시 셉니다.</small></p></section>
    ${drafts.showPins ? pinsHtml() : ''}
    ${room ? roomHtml(room) : ''}
    ${S.rooms.some((r) => r.view.results) ? resultsHtml() : ''}`, drafts);
  updateClocks();
}

function pinsHtml() {
  return `<section class="panel pins"><h2>접속 정보 (학생에게 알려 주세요)</h2><button data-act="print-pins">방별 접속 정보 인쇄</button>
    ${S.rooms.map((r, i) => `<article class="pin-sheet"><h3>${i + 1}번 방 · 방 코드 <b>${esc(r.code)}</b></h3><table><tr><th>나라</th><th>접속 번호</th></tr>
    ${Object.entries(r.tokens).map(([n, p]) => `<tr><td>${KO[n]}</td><td><b>${p}</b></td></tr>`).join('')}</table></article>`).join('')}</section>`;
}

function roomHtml(r) {
  const t = r.view;
  const pins = Object.entries(r.tokens).map(([n, p]) => {
    const isStu = t.students.includes(n);
    const on = r.online.filter((x) => x === n).length;
    return `<tr><td>${KO[n]}</td><td><b>${p}</b></td><td>${isStu ? '학생' : 'AI'}</td><td>${on ? `접속 ${on}대` : '-'}</td>
      <td>${r.info.ready.includes(n) ? '준비 완료' : ''}</td>
      <td><button data-act="ctl" data-code="${esc(r.code)}" data-country="${n}" data-mode="${isStu ? 'ai' : 'student'}">${isStu ? 'AI에게 맡기기' : '학생에게 돌려주기'}</button></td>
      <td><a href="${esc(studentLink(r.code, n))}" target="_blank">학생 화면 열기</a> · <a href="harbor.html?country=${encodeURIComponent(n)}" target="_blank">항구 외형 미리보기</a></td></tr>`;
  }).join('');
  const nations = t.nations.map((n) => `<tr><td>${esc(n.label)}${n.student ? ' (학생)' : ''}</td><td>${n.cash}G</td>
    <td>${Object.entries(n.levels).map(([g, lv]) => `${t.goods[g]} ${lv}`).join(', ')}</td><td>${t.goods[n.focus]}</td>
    <td>${fmt(n.happy, 0)}</td><td>${n.listed}</td><td>${n.progress ? `${fmt(n.progress.export_value, 0)}/${n.progress.export_target}` : '-'}</td>
    <td>${n.progress ? n.progress.operating_short_days : '-'}</td></tr>`).join('');
  return `<section class="panel room-detail"><h2>방 ${esc(r.code)} · 시드 ${t.seed} · 기록된 행동 ${t.log_length}개</h2>
    <div class="table-scroll"><table><tr><th>나라</th><th>접속 번호</th><th>운영</th><th>접속</th><th>준비</th><th></th><th></th></tr>${pins}</table></div>
    <div class="table-scroll"><table><tr><th>나라</th><th>돈</th><th>산업 레벨</th><th>주력</th><th>만족도</th><th>판매 중</th><th>쓰인 수출/목표</th><th>운영 부족</th></tr>${nations}</table></div>
    <p><button data-act="export" data-code="${esc(r.code)}">이 방 행동 기록 내려받기</button></p></section>`;
}

function resultsHtml() {
  return `<section class="panel"><h2>결과 (나라별 목표 달성도)</h2><div class="table-scroll"><table class="host-results"><tr><th>방</th><th>나라</th><th>점수</th><th>등급</th><th>수출</th><th>산업</th><th>생활</th><th>무역</th><th>활용</th><th>현금</th></tr>
    ${S.rooms.filter((r) => r.view.results).map((r) => Object.values(r.view.results).filter((x) => x.student).map((x) => `<tr><td>${esc(r.code)}</td><td>${esc(x.label)}</td>
      <td>${fmt(x.total)}</td><td>${x.grade}</td>${['export', 'industry', 'living', 'trade', 'utilization', 'cash'].map((k) => `<td>${fmt(x.parts[k])}</td>`).join('')}</tr>`).join('')).join('')}</table></div></section>`;
}

function onSummary(s) { S = s; summaryAt = Date.now(); dashboard(); }

async function startClass(fn) {
  const server = await openServer(drafts.server || servers[0].id);
  cls = new ClassHost({ engine, server, storage: browserStorage, onChange: onSummary });
  await fn(cls);
  cls.startTicker(500);
  onSummary(cls.summary());
}

async function act(el) {
  const a = el.dataset.act;
  if (a === 'counts') { await refreshCounts(); return; }
  if (a === 'new') {
    const students = [...document.querySelectorAll('.stu')].filter((b) => b.checked).map((b) => b.value);
    const rooms = num(drafts.rooms);
    if (!students.length || !(rooms >= 1 && rooms <= 20)) { lastMsg = '방 개수(1~20)와 학생 나라를 정해 주세요.'; return setup(); }
    const info = servers.find((s) => s.id === drafts.server) || servers[0];
    const need = (num(drafts.expected) || rooms * students.length) + 1;
    const online = typeof counts[info.id] === 'number' ? counts[info.id] : 0;
    if (online + need > info.capacity && !confirm(`${info.name}에 지금 ${online}명이 접속해 있어요. ${need}명이 더 들어오면 정원(${info.capacity}명)을 넘을 수 있어요. 그래도 만들까요?`)) return;
    drafts.server = info.id;
    const settings = {
      mode: drafts.mode, firstRoundTeacher: drafts.first !== 'no', countdownSec: num(drafts.countdown),
      timer: { listing: num(drafts.t_listing), trading: num(drafts.t_trading), invest: num(drafts.t_invest) },
    };
    lastMsg = '수업을 만드는 중…'; setup();
    try {
      await startClass((c) => c.create({ students, rooms, settings }));
      lastMsg = '수업을 만들었어요. "접속 정보 전체 보기"로 방 코드와 접속 번호를 알려 주세요.';
      drafts.showPins = true;
    } catch (e) { lastMsg = e.message; cls = null; return setup(); }
    return dashboard();
  }
  if (a === 'resume') {
    const meta = savedClasses(browserStorage).find((m) => m.cls === el.dataset.cls);
    drafts.server = meta.server;
    lastMsg = '기록을 다시 재생하는 중…'; setup();
    await startClass((c) => c.restore(meta));
    lastMsg = '이어서 진행해요.';
    return dashboard();
  }
  if (a === 'forget') {
    if (!confirm('이 수업 기록을 지울까요? 되돌릴 수 없어요.')) return;
    const meta = savedClasses(browserStorage).find((m) => m.cls === el.dataset.cls);
    for (const code of meta.rooms) browserStorage.remove('trade-room-' + code);
    browserStorage.remove('trade-class-' + meta.cls);
    return setup();
  }
  if (!cls) return;
  if (a === 'adv') { const r = await cls.advance(el.dataset.code); lastMsg = r.msg; }
  else if (a === 'advall') {
    const pending = S.rooms.reduce((x, r) => x + r.view.pending_offers, 0);
    if (pending && !confirm(`기다리는 제안이 ${pending}개 있어요. 거래 단계가 끝나면 취소돼요. 넘어갈까요?`)) return;
    await cls.advanceAll(); lastMsg = '모든 방을 다음 단계로 넘겼어요.';
  } else if (a === 'pause') { await cls.pause(); lastMsg = '모든 방을 멈췄어요. 시간도 멈춰요.'; }
  else if (a === 'resume-all') { await cls.resume(); lastMsg = '다시 시작했어요.'; }
  else if (a === 'settings') {
    await cls.setSettings({ mode: drafts.d_mode || S.settings.mode, firstRoundTeacher: (drafts.d_first || (S.settings.firstRoundTeacher ? 'yes' : 'no')) !== 'no',
      timer: { listing: num(drafts.d_tl ?? S.settings.timer.listing), trading: num(drafts.d_tt ?? S.settings.timer.trading), invest: num(drafts.d_ti ?? S.settings.timer.invest) } });
    lastMsg = '진행 방식을 바꿨어요.';
  } else if (a === 'sel') { selected = selected === el.dataset.code ? null : el.dataset.code; }
  else if (a === 'print-pins') { window.print(); return; }
  else if (a === 'pins') { drafts.showPins = !drafts.showPins; }
  else if (a === 'ctl') { const r = await cls.teacherAction(el.dataset.code, { type: 'set_controller', country: el.dataset.country, mode: el.dataset.mode }); lastMsg = r.msg; }
  else if (a === 'export') {
    const data = await cls.room(el.dataset.code).exportLog();
    const u = URL.createObjectURL(new Blob([JSON.stringify(data)], { type: 'application/json' }));
    Object.assign(document.createElement('a'), { href: u, download: `trade-game-${el.dataset.code}.json` }).click();
    URL.revokeObjectURL(u);
    return;
  } else if (a === 'finish') {
    if (!confirm('수업을 끝낼까요? 학생 화면 연결이 끊기고 서버에서 이 수업 자료를 지워요(이 컴퓨터의 기록은 남아요).')) return;
    await cls.finish({ clearServer: true }); cls = null; S = null; lastMsg = '수업을 끝냈어요.'; return setup();
  } else if (a === 'leave') { cls.stopTicker(); cls = null; S = null; lastMsg = ''; return setup(); }
  dashboard();
}

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-act]');
  if (el) { e.preventDefault(); el.disabled = true; act(el).catch((err) => { lastMsg = err.message; cls ? dashboard() : setup(); }).finally(() => { el.disabled = false; }); }
});
function updateClocks() {
  if (!S) return;
  for (const clock of document.querySelectorAll('.clock')) {
    const room = S.rooms.find((r) => r.code === clock.dataset.room);
    if (!room) continue;
    const left = leftMs(room.info, clock.dataset.time);
    const value = clock.dataset.time === 'countdown_ms'
      ? (left === null ? '' : `${Math.ceil(left / 1000)}초 뒤 다음 단계`)
      : (room.view.phase === 'finished' ? '–' : mmss(left));
    if (clock.textContent !== value) clock.textContent = value;
  }
}
setInterval(updateClocks, 1000);
window.addEventListener('beforeunload', (e) => { if (cls) { e.preventDefault(); e.returnValue = ''; } });

setup();
refreshCounts();
setInterval(() => { if (!cls) refreshCounts(); }, 15000);
engine = new EngineClient();
engine.init().then((info) => { status = `엔진 준비됨 (Python ${info.python.split(' ')[0]})`; if (!cls) setup(); })
  .catch((e) => { status = '엔진을 불러오지 못했어요: ' + e.message; if (!cls) setup(); });
