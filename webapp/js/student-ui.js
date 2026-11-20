// Functional student page (no visual design). Uses only StudentClient and the state it receives.
import { StudentClient } from './student-client.js';
import { openServer, parseRoomCode, serverList } from './transport.js';
import { esc, $, render, num, fmt } from './dom.js';

const drafts = {};
let me = null;
let S = null;
let stateAt = 0;
let lastMsg = '';
let leavePresence = null;
const MODE = { teacher: '선생님이 넘겨요', ready: '모두 준비하면 넘어가요', ready_timer: '모두 준비하거나 시간이 끝나면 넘어가요' };

const params = new URLSearchParams(location.search);
for (const k of ['room', 'country', 'pin']) if (params.get(k)) drafts['join-' + k] = params.get(k);

const COUNTRIES = { Tropia: '트로피아', Grainia: '그레니아', Oilia: '오일리아', Mechania: '메카니아', Mineria: '미네리아', Technia: '테크니아' };

function joinForm() {
  render($('#app'), `
    <h1>무역 게임 · 학생</h1>
    <p><label>방 코드 <input data-k="join-room" autocomplete="off" placeholder="예: 1-K7QPM-2"></label></p>
    <p><label>나라 <select data-k="join-country">${Object.entries(COUNTRIES).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select></label></p>
    <p><label>접속 번호 <input data-k="join-pin" inputmode="numeric" autocomplete="off"></label></p>
    <p><button data-act="join">들어가기</button></p>
    <p id="msg">${esc(lastMsg)}</p>`, drafts);
}

async function join() {
  const parsed = parseRoomCode(drafts['join-room']);
  const country = drafts['join-country'] || 'Tropia';
  const pin = (drafts['join-pin'] || '').trim();
  if (!parsed || !pin) { lastMsg = '방 코드(예: 1-K7QPM-2)와 접속 번호를 입력해 주세요.'; return joinForm(); }
  if (!serverList().some((x) => x.id === parsed.server)) { lastMsg = '이 방 코드의 서버가 이 화면에 설정되어 있지 않아요. 선생님께 주소를 확인해 주세요.'; return joinForm(); }
  lastMsg = '연결 중…'; joinForm();
  const server = await openServer(parsed.server);
  const transport = server.room(parsed.code);
  me = new StudentClient({ transport, country, token: pin });
  me.onState((state) => { S = state; stateAt = Date.now(); draw(); });
  const r = await me.connect();
  lastMsg = r.msg;
  if (!r.ok) { me = null; transport.close(); joinForm(); return; }
  leavePresence = server.presence.join({ role: 'student', room: parsed.code, country });
  history.replaceState(null, '', `?room=${parsed.code}&country=${country}`);
  draw();
}

const label = (g) => (S ? S.goods[g] : g);
const gname = (n) => (S ? S.names[n] : n);
const genTxt = (good, gen) => (good === 'machine' || good === 'electronics' ? ` ${gen}세대` : '');
const goodOptions = (sel) => Object.keys(S.goods).map((g) => `<option value="${g}" ${g === sel ? 'selected' : ''}>${S.goods[g]}</option>`).join('');

function txText(t) {
  const legs = t.legs.map((l) => `${gname(l.seller)}→${gname(l.buyer)} ${l.label}${genTxt(l.good, l.gen)} ${l.qty}개`).join(', ');
  const cash = t.cash ? ` / ${gname(t.cash.payer)}→${gname(t.cash.payee)} ${t.cash.amount}G` : '';
  return `[${{ market: '시장', direct: '직접', barter: '물물교환' }[t.channel]}] ${legs}${cash}`;
}

function offerText(o) {
  const side = (s) => (s ? `${S.goods[s.good]}${genTxt(s.good, s.gen)} ${s.qty}개` : '');
  if (o.kind === 'sell') return `${gname(o.from)}이(가) ${gname(o.to)}에 ${side(o.give)}을(를) ${o.cash}G에 팔기`;
  if (o.kind === 'buy') return `${gname(o.from)}이(가) ${gname(o.to)}에게서 ${side(o.get)}을(를) ${o.cash}G에 사기`;
  return `${gname(o.from)}의 ${side(o.give)} ↔ ${gname(o.to)}의 ${side(o.get)}`;
}

const mmss = (ms) => `${Math.floor(ms / 60000)}:${String(Math.floor((ms % 60000) / 1000)).padStart(2, '0')}`;
const left = (v) => (v === null || v === undefined ? null : (S.room.paused ? v : Math.max(0, v - (Date.now() - stateAt))));

// progress bar: mode, time left, who is ready, my ready button. The structure is rebuilt only
// when it changes; the clock numbers are updated in place every second (buttons stay clickable).
let barHtml = '';
function drawBar() {
  const bar = $('#bar');
  if (!S || !S.room || S.phase === 'finished') { bar.innerHTML = ''; barHtml = ''; return; }
  const R = S.room;
  const mine = R.ready.includes(S.country);
  const shortages = S.phase !== 'invest' ? S.settlement.rows.filter((r) => r.short > 0) : [];
  const warn = shortages.length ? `정산 때 ${shortages.map((r) => `${r.label} ${r.short}개`).join(', ')}가 모자라요.` : '';
  const html = `<p>방 ${esc(R.code)} · ${esc(MODE[R.mode])}${R.paused ? ' · <b>잠시 멈춤</b>' : ''}
    <span id="clock"></span> · 준비 ${R.ready.length}/${R.need.length} <b id="countdown"></b></p>
    <p>${S.is_student ? `<button data-act="ready" data-on="${mine ? 0 : 1}">${mine ? '준비 취소' : '준비 완료'}</button>` : ''}
    ${warn && !mine ? ` <b>${esc(warn)}</b>` : ''}</p>`;
  if (html !== barHtml) { bar.innerHTML = html; barHtml = html; }
  const dl = left(R.deadline_ms); const cd = left(R.countdown_ms);
  $('#clock').textContent = dl !== null ? ` · 남은 시간 ${mmss(dl)}` : '';
  $('#countdown').textContent = cd !== null ? ` · ${Math.ceil(cd / 1000)}초 뒤 다음 단계` : '';
}
setInterval(drawBar, 1000);

function draw() {
  if (!S) return;
  drawBar();
  const trading = S.phase === 'trading';
  const listing = S.phase === 'listing' || trading;
  const st = S.settlement.rows.map((r) => `<tr><td>${esc(r.label)}</td><td>${esc(r.purpose)}</td><td>${r.need}</td><td>${r.have}</td><td>${r.short ? `<b>${r.short}개 부족</b>` : '충분'}</td></tr>`).join('');
  const stock = S.stock.map((r) => {
    const k = `${r.good}-${r.gen}`;
    return `<tr><td>${esc(r.label)}${genTxt(r.good, r.gen)}</td><td>${r.free}</td><td>${r.listed}</td>
      <td>${listing && r.free ? `<input data-k="lq-${k}" type="number" min="1" max="${r.free}" placeholder="수량" size="3">
      <input data-k="lp-${k}" type="number" min="1" placeholder="개당 G" size="4">
      <button data-act="list" data-good="${r.good}" data-gen="${r.gen}">내놓기</button> <small>기준 ${S.quotes[r.good][r.gen]}G</small>` : ''}</td></tr>`;
  }).join('');
  const mine = S.my_orders.map((o) => `<tr><td>${esc(o.label)}${genTxt(o.good, o.gen)}</td><td>${o.qty}</td><td>${o.price}G</td>
    <td>${listing ? `<input data-k="rp-${o.oid}" type="number" min="1" size="4" placeholder="새 가격"><button data-act="reprice" data-oid="${o.oid}">가격 변경</button>
    <button data-act="cancel" data-oid="${o.oid}">거두기</button>` : ''}</td></tr>`).join('');
  const market = S.market.filter((o) => o.seller !== S.country).map((o) => `<tr><td>${esc(o.seller_label)}${o.seller_is_student ? ' (학생)' : ''}</td>
    <td>${esc(o.label)}${genTxt(o.good, o.gen)}</td><td>${o.qty}</td><td>${o.price}G</td><td>${o.reference}G</td>
    <td>${trading ? `<input data-k="bq-${o.oid}" type="number" min="1" max="${o.qty}" value="1" size="3"><button data-act="buy" data-oid="${o.oid}">사기</button>` : ''}</td></tr>`).join('');
  const others = S.countries.filter((n) => n !== S.country);
  const offers = S.offers.slice().reverse().map((o) => {
    const status = { pending: '기다리는 중', accepted: '성사', rejected: '거절', cancelled: '취소', expired: '만료' }[o.status];
    const btn = o.status === 'pending' && trading
      ? (o.to === S.country ? `<button data-act="respond" data-id="${o.id}" data-acc="1">수락</button><button data-act="respond" data-id="${o.id}" data-acc="0">거절</button>`
        : `<button data-act="withdraw" data-id="${o.id}">취소</button>`) : '';
    return `<li>${o.round}R · ${esc(offerText(o))} — ${status}${o.note ? ` (${esc(o.note)})` : ''} ${btn}</li>`;
  }).join('');
  const inv = S.invest_options.map((o) => `<tr><td>${esc(o.label)}${o.main ? ' (대표)' : ''}${o.new_industry ? ' (새 산업)' : ''}</td>
    <td>${o.level} → ${o.next_level}</td><td>${o.cost}G</td><td>${o.ore ? `광물 ${o.ore}` : '-'}${o.machine_gen ? `, 기계 ${o.machine_gen}세대+` : ''}</td>
    <td>${o.ok ? `<button data-act="invest" data-good="${o.good}">투자</button>` : esc(o.reasons.join(', '))}</td></tr>`).join('');
  const p = S.progress;
  const results = S.results ? `<h2>결과</h2><table><tr><th>나라</th><th>점수</th><th>등급</th><th>수출</th><th>산업</th><th>생활</th><th>무역</th><th>활용</th><th>현금</th></tr>
    ${Object.values(S.results).filter((r) => r.label === S.label || r.student).map((r) => `<tr><td>${esc(r.label)}</td><td>${fmt(r.total)}</td><td>${r.grade}</td>
    ${['export', 'industry', 'living', 'trade', 'utilization', 'cash'].map((k) => `<td>${fmt(r.parts[k])}</td>`).join('')}</tr>`).join('')}</table>` : '';
  render($('#app'), `
    <h1>${esc(S.label)} · ${S.round}라운드 · ${esc(S.phase_label)}</h1>
    <p>돈 <b>${S.cash}G</b> · 대표 산업 ${label(S.main)} · 이번 주력 ${label(S.focus)} · 다음 주력 ${label(S.next_focus)} · 인구 ${S.population}명
      ${S.is_student ? '' : ' · <b>지금은 AI가 운영 중</b>'}</p>
    <p id="msg">${esc(lastMsg)}</p>
    ${results}
    <h2>이번 라운드 정산 (판매 중인 물건은 쓸 수 없어요)</h2>
    <table><tr><th>물건</th><th>쓰임</th><th>필요</th><th>창고</th><th>상태</th></tr>${st}</table>
    <p>연료 쓰는 날 ${S.operating_schedule.fuel.join('·')}라운드, 광물 쓰는 날 ${S.operating_schedule.ore.join('·')}라운드</p>
    <h2>창고</h2><table><tr><th>물건</th><th>창고</th><th>판매 중</th><th>내놓기</th></tr>${stock}</table>
    <h2>내 판매 목록</h2><table><tr><th>물건</th><th>수량</th><th>가격</th><th></th></tr>${mine || '<tr><td colspan="4">없음</td></tr>'}</table>
    <h2>시장 ${trading ? '' : '(사기는 거래 단계에서)'}</h2>
    <table><tr><th>파는 나라</th><th>물건</th><th>수량</th><th>가격</th><th>기준</th><th></th></tr>${market || '<tr><td colspan="6">없음</td></tr>'}</table>
    <h2>직접 거래 ${trading ? '' : '(거래 단계에서)'}</h2>
    ${trading ? `<p><select data-k="of-to">${others.map((n) => `<option value="${n}">${esc(S.names[n])}${S.students.includes(n) ? ' (학생)' : ''}</option>`).join('')}</select>
      <select data-k="of-kind"><option value="sell">팔기</option><option value="buy">사기</option><option value="barter">물물교환</option></select></p>
      <p>내가 줄 물건 <select data-k="of-give-good">${goodOptions('banana')}</select> 세대 <input data-k="of-give-gen" type="number" min="1" max="3" value="1" size="2"> 수량 <input data-k="of-give-qty" type="number" min="1" value="1" size="2"></p>
      <p>내가 받을 물건 <select data-k="of-get-good">${goodOptions('wheat')}</select> 세대 <input data-k="of-get-gen" type="number" min="1" max="3" value="1" size="2"> 수량 <input data-k="of-get-qty" type="number" min="1" value="1" size="2"></p>
      <p>금액(팔기·사기) <input data-k="of-cash" type="number" min="1" size="5"> G <button data-act="offer">제안하기</button></p>` : ''}
    <ul>${offers || '<li>없음</li>'}</ul>
    <h2>투자 ${S.phase === 'invest' ? '' : '(투자 단계에서)'}</h2>
    <table><tr><th>산업</th><th>레벨</th><th>비용</th><th>재료</th><th></th></tr>${inv}</table>
    ${S.phase === 'invest' ? `<p>다음 라운드 주력 산업 <select data-k="focus">${Object.keys(S.levels).map((g) => `<option value="${g}" ${g === S.next_focus ? 'selected' : ''}>${S.goods[g]}</option>`).join('')}</select>
      <button data-act="focus">정하기</button></p>` : ''}
    <h2>진행 상황</h2>
    <p>쓰인 수출 ${fmt(p.export_value, 0)} / 목표 ${p.export_target}G · 대표 산업 레벨 업 ${p.main_levelled ? '했음' : '아직'} ·
      평균 만족도 ${fmt(p.avg_happy)} · 운영 자원 부족 ${p.operating_short_days}일 · 긴급 조달 ${p.emergency_paid}G</p>
    <h2>이번 라운드 거래</h2><ul>${S.transactions_this_round.map((t) => `<li>${esc(txText(t))}</li>`).join('') || '<li>없음</li>'}</ul>`, drafts);
}

async function act(el) {
  const a = el.dataset.act;
  if (a === 'join') return join();
  if (!me) return;
  let r;
  const d = (k) => drafts[k];
  if (a === 'list') {
    const k = `${el.dataset.good}-${el.dataset.gen}`;
    r = await me.list(el.dataset.good, num(d('lq-' + k)), num(d('lp-' + k)), num(el.dataset.gen));
    if (r.ok) { delete drafts['lq-' + k]; delete drafts['lp-' + k]; }
  } else if (a === 'reprice') r = await me.reprice(num(el.dataset.oid), num(d('rp-' + el.dataset.oid)));
  else if (a === 'cancel') r = await me.cancel(num(el.dataset.oid));
  else if (a === 'buy') r = await me.buy(num(el.dataset.oid), num(d('bq-' + el.dataset.oid) || 1));
  else if (a === 'offer') {
    const kind = d('of-kind') || 'sell';
    const side = (p, g) => ({ good: d(`of-${p}-good`) || g, gen: num(d(`of-${p}-gen`) || 1), qty: num(d(`of-${p}-qty`) || 1) });
    const to = d('of-to') || S.countries.find((n) => n !== S.country);
    const cash = num(d('of-cash'));
    r = kind === 'sell' ? await me.offerSell(to, side('give', 'banana'), cash)
      : kind === 'buy' ? await me.offerBuy(to, side('get', 'wheat'), cash)
        : await me.offerBarter(to, side('give', 'banana'), side('get', 'wheat'));
  } else if (a === 'respond') r = await me.respond(num(el.dataset.id), el.dataset.acc === '1');
  else if (a === 'withdraw') r = await me.withdraw(num(el.dataset.id));
  else if (a === 'ready') r = await me.ready(el.dataset.on === '1');
  else if (a === 'invest') r = await me.invest(el.dataset.good);
  else if (a === 'focus') r = await me.focus(d('focus') || S.next_focus);
  if (r) { lastMsg = r.msg; draw(); }
}

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-act]');
  if (el) { e.preventDefault(); el.disabled = true; act(el).finally(() => { el.disabled = false; }); }
});

const barEl = document.createElement('div');
barEl.id = 'bar';
$('#app').before(barEl);
window.addEventListener('pagehide', () => { if (leavePresence) leavePresence(); });
joinForm();
if (drafts['join-room'] && drafts['join-pin']) join();
