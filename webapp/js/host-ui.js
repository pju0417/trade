// Functional teacher page (no visual design): runs the engine and the classroom room.
import { EngineClient } from './engine-client.js';
import { HostController, ORIGINAL, browserStorage } from './host.js';
import { makeTransport } from './transport.js';
import { FIREBASE_CONFIG } from './config.js';
import { esc, $, render, fmt } from './dom.js';

const KO = { Tropia: '트로피아', Grainia: '그레니아', Oilia: '오일리아', Mechania: '메카니아', Mineria: '미네리아', Technia: '테크니아' };
const drafts = {};
let engine = null;
let host = null;
let status = '엔진을 불러오는 중…(처음에는 10초쯤 걸릴 수 있어요)';
let lastMsg = '';
const mode = FIREBASE_CONFIG ? 'firebase' : 'local';

const roomCode = () => Array.from({ length: 5 }, () => 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'[Math.floor(Math.random() * 32)]).join('');

function savedGames() {
  const out = [];
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    if (k.startsWith('trade-game-host-')) {
      try { out.push(JSON.parse(localStorage.getItem(k))); } catch (e) { /* ignore */ }
    }
  }
  return out.sort((a, b) => String(b.saved).localeCompare(String(a.saved)));
}

function setup() {
  const saved = savedGames();
  if (drafts.room === undefined) drafts.room = roomCode();
  render($('#app'), `
    <h1>무역 게임 · 선생님</h1>
    <p>${esc(status)}</p>
    <p>연결 방식: ${mode === 'firebase' ? 'Firebase(학생 기기 접속)' : '<b>로컬 시험 모드</b> — 같은 브라우저의 다른 탭에서만 학생 화면이 연결돼요. 실제 수업은 js/config.js에 Firebase 설정이 필요해요.'}</p>
    <h2>새 게임</h2>
    <p><label>방 코드 <input data-k="room" size="8"></label></p>
    <p>학생이 맡을 나라: ${ORIGINAL.map((n, i) => `<label><input type="checkbox" data-k="stu-${n}" value="${n}" ${i % 2 === 0 ? 'checked' : ''}> ${KO[n]}</label>`).join(' ')}</p>
    <p><label>시드(비우면 무작위) <input data-k="seed" size="10"></label></p>
    <p><button data-act="new" ${engine ? '' : 'disabled'}>새 게임 시작</button></p>
    ${saved.length ? `<h2>이어하기</h2><ul>${saved.map((s) => `<li>방 ${esc(s.room)} · ${esc(s.saved)} · 학생 ${s.students.map((n) => KO[n]).join(', ')} · 행동 ${s.log.length}개
      <button data-act="resume" data-room="${esc(s.room)}" ${engine ? '' : 'disabled'}>이어하기</button>
      <button data-act="forget" data-room="${esc(s.room)}">기록 삭제</button></li>`).join('')}</ul>` : ''}
    <p id="msg">${esc(lastMsg)}</p>`, drafts);
  for (const n of ORIGINAL) {
    const box = $(`[data-k="stu-${n}"]`);
    if (drafts['stu-' + n] !== undefined) box.checked = drafts['stu-' + n] === true;
    box.onchange = () => { drafts['stu-' + n] = box.checked; };
  }
}

function link(country) {
  const u = new URL('student.html', location.href);
  u.search = `?room=${host.room}&country=${country}`;
  return u.href;
}

function game(t) {
  if (!t) return;
  const nations = t.nations.map((n) => `<tr><td>${esc(n.label)}${n.student ? ' (학생)' : ''}</td><td>${n.cash}G</td>
    <td>${Object.entries(n.levels).map(([g, lv]) => `${t.goods[g]} ${lv}`).join(', ')}</td><td>${t.goods[n.focus]}</td>
    <td>${fmt(n.happy, 0)}</td><td>${Object.entries(n.stock).filter(([, v]) => v).map(([g, v]) => `${t.goods[g]} ${v}`).join(', ')}</td>
    <td>${n.listed}</td><td>${n.progress ? `${fmt(n.progress.export_value, 0)}/${n.progress.export_target}` : '-'}</td>
    <td>${n.progress ? n.progress.operating_short_days : '-'}</td><td>${n.invested_this_round ? '투자함' : ''}</td></tr>`).join('');
  const students = Object.entries(host.tokens).map(([n, pin]) => {
    const isStu = t.students.includes(n);
    return `<tr><td>${KO[n]}</td><td><b>${pin}</b></td><td>${isStu ? '학생' : 'AI'}</td>
      <td><button data-act="ctl" data-country="${n}" data-mode="${isStu ? 'ai' : 'student'}">${isStu ? 'AI에게 맡기기' : '학생에게 돌려주기'}</button></td>
      <td><a href="${esc(link(n))}" target="_blank">학생 화면 열기</a></td></tr>`;
  }).join('');
  const addable = ORIGINAL.filter((n) => !host.tokens[n]);
  const results = t.results ? `<h2>결과 (나라별 목표 달성도)</h2><table><tr><th>나라</th><th>맡은 이</th><th>점수</th><th>등급</th><th>수출</th><th>산업</th><th>생활</th><th>무역</th><th>활용</th><th>현금</th><th>쓰인 수출/목표</th><th>운영 부족</th></tr>
    ${Object.values(t.results).map((r) => `<tr><td>${esc(r.label)}</td><td>${r.student ? '학생' : 'AI'}</td><td>${fmt(r.total)}</td><td>${r.grade}</td>
    ${['export', 'industry', 'living', 'trade', 'utilization', 'cash'].map((k) => `<td>${fmt(r.parts[k])}</td>`).join('')}
    <td>${fmt(r.export_value, 0)}/${r.export_target}</td><td>${r.operating_short_days}일</td></tr>`).join('')}</table>` : '';
  render($('#app'), `
    <h1>방 ${esc(host.room)} · ${t.round}라운드 · ${esc(t.phase_label)}</h1>
    <p>${mode === 'local' ? '로컬 시험 모드 · ' : ''}시드 ${t.seed} · 기록된 행동 ${t.log_length}개 · 기다리는 직접 거래 제안 ${t.pending_offers}개 · 이번 라운드 거래 ${t.transactions_this_round}건</p>
    <p>${t.phase === 'finished' ? '' : `<button data-act="advance">다음 단계로 (${{ listing: '판매 등록 마감 → 거래', trading: '거래 마감 → 정산·투자', invest: '투자 마감 → 다음 라운드' }[t.phase]})</button>`}
      <button data-act="export">행동 기록 내려받기</button> <button data-act="leave">처음 화면으로</button></p>
    <p id="msg">${esc(lastMsg)}</p>
    ${results}
    <h2>학생 접속 정보</h2>
    <p>학생은 학생 화면에서 방 코드 <b>${esc(host.room)}</b>, 나라, 접속 번호를 입력해요.</p>
    <table><tr><th>나라</th><th>접속 번호</th><th>운영</th><th></th><th></th></tr>${students}</table>
    ${addable.length && t.phase !== 'finished' ? `<p>학생 나라 추가: ${addable.map((n) => `<button data-act="ctl" data-country="${n}" data-mode="student">${KO[n]}</button>`).join(' ')}</p>` : ''}
    <h2>나라 현황</h2>
    <table><tr><th>나라</th><th>돈</th><th>산업 레벨</th><th>주력</th><th>만족도</th><th>창고(판매 중 포함)</th><th>판매 중</th><th>쓰인 수출/목표</th><th>운영 부족</th><th></th></tr>${nations}</table>
    <h2>시장 (${t.market.length}건)</h2>
    <table><tr><th>파는 나라</th><th>물건</th><th>수량</th><th>가격</th><th>기준</th></tr>
    ${t.market.map((o) => `<tr><td>${esc(o.seller_label)}</td><td>${esc(o.label)}${o.gen > 1 ? ` ${o.gen}세대` : ''}</td><td>${o.qty}</td><td>${o.price}G</td><td>${o.reference}G</td></tr>`).join('')}</table>`, drafts);
}

async function act(el) {
  const a = el.dataset.act;
  if (a === 'new') {
    const students = ORIGINAL.filter((n) => $(`[data-k="stu-${n}"]`).checked);
    const room = (drafts.room || '').trim().toUpperCase();
    if (!room || !students.length) { lastMsg = '방 코드와 학생 나라를 정해 주세요.'; return setup(); }
    const seed = drafts.seed ? Number(drafts.seed) : undefined;
    lastMsg = '게임을 만드는 중…'; setup();
    host = new HostController({ engine, transport: await makeTransport(room, FIREBASE_CONFIG), room, storage: browserStorage, onChange: game });
    try { await host.newGame({ students, seed: Number.isInteger(seed) ? seed : undefined }); lastMsg = '게임을 시작했어요. 학생들에게 방 코드와 접속 번호를 알려 주세요.'; } catch (e) { lastMsg = e.message; host = null; return setup(); }
    return game(host.teacherView);
  }
  if (a === 'resume') {
    const saved = savedGames().find((s) => s.room === el.dataset.room);
    lastMsg = '기록을 다시 재생하는 중…'; setup();
    host = new HostController({ engine, transport: await makeTransport(saved.room, FIREBASE_CONFIG), room: saved.room, storage: browserStorage, onChange: game });
    await host.resume(saved);
    lastMsg = '이어서 진행해요.';
    return game(host.teacherView);
  }
  if (a === 'forget') {
    if (confirm('이 게임 기록을 지울까요? 되돌릴 수 없어요.')) localStorage.removeItem('trade-game-host-' + el.dataset.room);
    return setup();
  }
  if (!host) return;
  if (a === 'advance') {
    const t = host.teacherView;
    if (t.pending_offers && !confirm(`기다리는 제안이 ${t.pending_offers}개 있어요. 마감하면 취소돼요. 넘어갈까요?`)) return;
    const r = await host.teacherAction({ type: 'advance' });
    lastMsg = r.msg;
  } else if (a === 'ctl') {
    const r = await host.teacherAction({ type: 'set_controller', country: el.dataset.country, mode: el.dataset.mode });
    lastMsg = r.msg;
  } else if (a === 'export') {
    const data = await host.exportLog();
    const blob = new Blob([JSON.stringify(data)], { type: 'application/json' });
    const u = URL.createObjectURL(blob);
    Object.assign(document.createElement('a'), { href: u, download: `trade-game-${host.room}.json` }).click();
    URL.revokeObjectURL(u);
    return;
  } else if (a === 'leave') {
    host.transport.close(); host = null; lastMsg = ''; return setup();
  }
  game(host.teacherView);
}

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-act]');
  if (el) { e.preventDefault(); el.disabled = true; act(el).catch((err) => { lastMsg = err.message; }).finally(() => { el.disabled = false; }); }
});

setup();
engine = new EngineClient();
engine.init().then((info) => { status = `엔진 준비됨 (Python ${info.python.split(' ')[0]})`; setup(); })
  .catch((e) => { status = '엔진을 불러오지 못했어요: ' + e.message; setup(); });
