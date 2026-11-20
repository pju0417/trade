// Student view. All game actions go through StudentClient.
import { StudentClient } from './student-client.js';
import { openServer, parseRoomCode, serverList, LOCAL_FLAG } from './transport.js';
import { esc, $, render, num, fmt } from './dom.js';

const drafts = {};
let me = null;
let S = null;
let stateAt = 0;
let lastMsg = '';
let leavePresence = null;
let joining = false;
const MODE = { teacher: '선생님이 넘겨요', ready: '모두 준비하면 넘어가요', ready_timer: '모두 준비하거나 시간이 끝나면 넘어가요' };

const params = new URLSearchParams(location.search);
for (const k of ['room', 'country', 'pin']) if (params.get(k)) drafts['join-' + k] = params.get(k);

const COUNTRIES = { Tropia: '트로피아', Grainia: '그레니아', Oilia: '오일리아', Mechania: '메카니아', Mineria: '미네리아', Technia: '테크니아' };

function joinForm() {
  render($('#app'), `
    <section class="panel join-panel">
    <a class="back" href="index.html${LOCAL_FLAG ? '?local=1' : ''}">← 첫 화면</a>
    <h1>학생 입장</h1>
    <p>선생님이 알려 준 방 코드와 접속 번호를 입력하세요.</p>
    <p><label>방 코드 <input data-k="join-room" autocomplete="off" placeholder="예: 1-K7QPM-2"></label></p>
    <p><label>나라 <select data-k="join-country">${Object.entries(COUNTRIES).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select></label></p>
    <p><label>접속 번호 <input data-k="join-pin" inputmode="numeric" autocomplete="off"></label></p>
    <p><button data-act="join" ${joining ? 'disabled' : ''}>${joining ? '연결 중…' : '들어가기'}</button></p>
    <p id="msg" role="status">${esc(lastMsg)}</p></section>`, drafts);
}

async function join() {
  const parsed = parseRoomCode(drafts['join-room']);
  const country = drafts['join-country'] || 'Tropia';
  const pin = (drafts['join-pin'] || '').trim();
  if (!parsed || !pin) { lastMsg = '방 코드(예: 1-K7QPM-2)와 접속 번호를 입력해 주세요.'; return joinForm(); }
  if (!serverList().some((x) => x.id === parsed.server)) { lastMsg = '이 방 코드의 서버가 이 화면에 설정되어 있지 않아요. 선생님께 주소를 확인해 주세요.'; return joinForm(); }
  if (joining) return;
  joining = true;
  lastMsg = '';
  joinForm();
  let transport;
  try {
    const server = await openServer(parsed.server);
    transport = server.room(parsed.code);
    me = new StudentClient({ transport, country, token: pin });
    me.onState((state) => { S = state; stateAt = Date.now(); draw(); });
    const r = await me.connect();
    lastMsg = r.msg;
    if (!r.ok) { me = null; transport.close(); return; }
    leavePresence = server.presence.join({ role: 'student', room: parsed.code, country });
    history.replaceState(null, '', `?room=${parsed.code}&country=${country}${LOCAL_FLAG ? '&local=1' : ''}`);
    draw();
  } catch (err) {
    transport?.close();
    me = null;
    S = null;
    $('#status').hidden = true;
    lastMsg = err.message;
  } finally {
    joining = false;
    if (!me) joinForm();
  }
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
function drawBar() {
  const bar = $('#bar');
  if (!S || !S.room || S.phase === 'finished') { render(bar, '', drafts); return; }
  const R = S.room;
  const mine = R.ready.includes(S.country);
  const shortages = S.phase !== 'invest' ? S.settlement.rows.filter((r) => r.short > 0) : [];
  const warn = shortages.length ? `정산 때 ${shortages.map((r) => `${r.label} ${r.short}개`).join(', ')}가 모자라요.` : '';
  const html = `<div class="round-readout"><p>방 ${esc(R.code)} · ${esc(MODE[R.mode])}${R.paused ? ' · <b>잠시 멈춤</b>' : ''}
    <span id="clock"></span> · 준비 ${R.ready.length}/${R.need.length} 나라 <b id="countdown"></b></p>
    ${warn ? `<p class="shortage">${esc(warn)}</p>` : ''}</div>
    <div class="ready-zone">${S.is_student ? `<button data-act="ready" data-on="${mine ? 0 : 1}">${mine ? '준비 취소' : '준비 완료'}</button>` : ''}
    </div>`;
  render(bar, html, drafts);
  updateClock();
}

function updateClock() {
  if (!S?.room || S.phase === 'finished') return;
  const R = S.room;
  const dl = left(R.deadline_ms); const cd = left(R.countdown_ms);
  const clock = $('#clock');
  const countdown = $('#countdown');
  const time = dl !== null ? ` · 남은 시간 ${mmss(dl)}` : '';
  const next = cd !== null ? ` · ${Math.ceil(cd / 1000)}초 뒤 다음 단계` : '';
  if (clock.textContent !== time) clock.textContent = time;
  if (countdown.textContent !== next) countdown.textContent = next;
}
setInterval(updateClock, 1000);

const ICON = { wheat: '🌾', banana: '🍌', fuel: '⛽', ore: '🪨', machine: '⚙️', electronics: '📱' };
const icon = (good) => `<span class="good-icon" aria-hidden="true">${ICON[good] || ''}</span>`;
const TASK = {
  listing: '창고를 보고 남는 물건을 시장에 내놓으세요.',
  trading: '필요한 물건을 사거나 다른 나라에 직접 거래를 제안하세요.',
  invest: '산업을 키우고 다음 라운드에 힘쓸 주력 산업을 정하세요.',
};
const PARTS = { export: '수출', industry: '산업', living: '생활', trade: '무역', utilization: '물건 활용', cash: '현금' };

function offerSide(side, title, selected) {
  return `<fieldset class="offer-${side}"><legend>${title}</legend><div class="fields">
    <label>물건 <select data-k="of-${side}-good">${goodOptions(selected)}</select></label>
    <label class="generation">세대 <input data-k="of-${side}-gen" type="number" min="1" max="3" value="1"></label>
    <label>수량 <input data-k="of-${side}-qty" type="number" min="1" value="1"></label>
  </div></fieldset>`;
}

function showGeneration(form, side) {
  const good = form.querySelector(`[data-k="of-${side}-good"]`).value;
  const input = form.querySelector(`[data-k="of-${side}-gen"]`);
  input.closest('label').hidden = !['machine', 'electronics'].includes(good);
}

function syncOfferForm() {
  const form = $('.offer-form');
  if (!form) return;
  const kind = $('[data-k="of-kind"]', form).value;
  $('.offer-give', form).hidden = kind === 'buy';
  $('.offer-get', form).hidden = kind === 'sell';
  $('.offer-cash', form).hidden = kind === 'barter';
  for (const side of ['give', 'get']) showGeneration(form, side);
}
document.addEventListener('change', (e) => {
  if (e.target.closest('.offer-form')) syncOfferForm();
});

function draw() {
  if (!S) return;
  drawBar();
  const trading = S.phase === 'trading';
  const listing = S.phase === 'listing' || trading;
  const st = S.settlement.rows.map((r) => `<tr><td>${esc(r.label)}</td><td>${esc(r.purpose)}</td><td>${r.need}</td><td>${r.have}</td><td>${r.short ? `<b>${r.short}개 부족</b>` : '충분'}</td></tr>`).join('');
  const stock = S.stock.map((r) => {
    const k = `${r.good}-${r.gen}`;
    return `<article class="good-card"><h3>${icon(r.good)}${esc(r.label)}${genTxt(r.good, r.gen)}</h3>
      <dl class="metrics"><div><dt>창고</dt><dd>${r.free}개</dd></div><div><dt>판매 중</dt><dd>${r.listed}개</dd></div>
        <div><dt>기준 가격</dt><dd>${S.quotes[r.good][r.gen]}G</dd></div></dl>
      ${listing && r.free ? `<div class="fields stock-fields">
        <label>수량 <input data-k="lq-${k}" type="number" min="1" max="${r.free}"></label>
        <label>개당 가격(G) <input data-k="lp-${k}" type="number" min="1"></label>
        <button data-act="list" data-good="${r.good}" data-gen="${r.gen}">내놓기</button></div>` : ''}
    </article>`;
  }).join('');
  const mine = S.my_orders.map((o) => `<tr><td>${esc(o.label)}${genTxt(o.good, o.gen)}</td><td>${o.qty}</td><td>${o.price}G</td>
    <td>${listing ? `<input data-k="rp-${o.oid}" type="number" min="1" size="4" placeholder="새 가격"><button data-act="reprice" data-oid="${o.oid}">가격 변경</button>
    <button data-act="cancel" data-oid="${o.oid}">거두기</button>` : ''}</td></tr>`).join('');
  const groups = new Map();
  for (const offer of S.market.filter((o) => o.seller !== S.country)) {
    if (!groups.has(offer.good)) groups.set(offer.good, []);
    groups.get(offer.good).push(offer);
  }
  const market = [...groups].map(([good, items]) => `<article class="good-card market-card">
    <h3>${icon(good)}${esc(label(good))}</h3>
    <ul class="market-list">${items.sort((a, b) => a.price - b.price).map((o) => {
      const price = o.price < o.reference ? '기준보다 쌈' : o.price > o.reference ? '기준보다 비쌈' : '기준과 같음';
      return `<li><div><strong>${esc(o.seller_label)}</strong><small>${o.seller_is_student ? '학생 · ' : ''}${genTxt(o.good, o.gen).trim() ? genTxt(o.good, o.gen).trim() + ' · ' : ''}${o.qty}개 판매 중</small></div>
        <div><strong>${o.price}G</strong><small>기준 ${o.reference}G · <span class="${o.price > o.reference ? 'warn-text' : ''}">${price}</span></small></div>
        ${trading ? `<div class="buy-actions"><input aria-label="${esc(o.seller_label)} ${esc(o.label)} 구매 수량" data-k="bq-${o.oid}" type="number" min="1" max="${o.qty}" value="1">
          <button data-act="buy" data-oid="${o.oid}">사기</button></div>` : ''}</li>`;
    }).join('')}</ul></article>`).join('');
  const others = S.countries.filter((n) => n !== S.country);
  const incoming = (o) => trading && o.status === 'pending' && o.to === S.country;
  const offers = S.offers.slice().reverse().sort((a, b) => Number(incoming(b)) - Number(incoming(a))).map((o) => {
    const status = { pending: '기다리는 중', accepted: '성사', rejected: '거절', cancelled: '취소', expired: '만료' }[o.status];
    const btn = o.status === 'pending' && trading
      ? (o.to === S.country ? `<button data-act="respond" data-id="${o.id}" data-acc="1">수락</button><button data-act="respond" data-id="${o.id}" data-acc="0">거절</button>`
        : `<button data-act="withdraw" data-id="${o.id}">취소</button>`) : '';
    return `<li class="${incoming(o) ? 'incoming' : ''}">
      ${incoming(o) ? '<strong>나에게 온 제안</strong>' : ''}<p>${o.round}라운드 · ${esc(offerText(o))}</p>
      <span class="tag">${status}</span>${o.note ? ` <small>${esc(o.note)}</small>` : ''} <div class="actions">${btn}</div></li>`;
  }).join('');
  const inv = S.invest_options.map((o) => {
    const materials = [o.ore && `광물 ${o.ore}개`, o.machine_gen && `기계 ${o.machine_gen}세대 이상`].filter(Boolean);
    return `<article class="good-card"><h3>${icon(o.good)}${esc(o.label)}</h3>
      ${o.main ? '<span class="tag">대표 산업</span>' : o.new_industry ? '<span class="tag">새 산업</span>' : ''}
      <dl class="metrics"><div><dt>레벨</dt><dd>${o.level} → ${o.next_level}</dd></div><div><dt>비용</dt><dd>${o.cost}G</dd></div></dl>
      <p>필요한 재료: ${materials.join(', ') || '없음'}</p>
      ${o.ok ? `<button data-act="invest" data-good="${o.good}">투자</button>` : `<p class="warn-text">${esc(o.reasons.join(' · '))}</p>`}</article>`;
  }).join('');
  const p = S.progress;
  const result = Object.values(S.results || {}).find((r) => r.label === S.label);
  const results = result ? `<section class="panel result">
    <h2>결과 · 우리 나라 목표 달성도</h2>
    <div class="score"><strong>${fmt(result.total)}<small>점</small></strong><span>${esc(result.grade)} 등급</span></div>
    <dl class="card-grid score-grid">${Object.entries(PARTS).map(([k, title]) => `<div><dt>${title}</dt><dd>${fmt(result.parts[k])}점</dd></div>`).join('')}</dl>
  </section>` : '';
  const progress = `<section class="panel"><h2>진행 상황</h2><p><strong>다른 나라에서 쓰인 우리 물건</strong> · ${fmt(p.export_value, 0)} / 목표 ${p.export_target}G</p>
    ${p.export_target > 0 ? `<progress aria-label="수출 목표 달성도" value="${Math.min(p.export_value, p.export_target)}" max="${p.export_target}"></progress>` : ''}
    <dl class="metrics progress-metrics"><div><dt>대표 산업을 키웠나요?</dt><dd>${p.main_levelled ? '키웠어요' : '아직이에요'}</dd></div>
    <div><dt>평균 만족도</dt><dd>${fmt(p.avg_happy)}</dd></div><div><dt>운영 자원 부족</dt><dd>${p.operating_short_days}일</dd></div>
    <div><dt>급히 산 자원 비용</dt><dd>${p.emergency_paid}G</dd></div></dl></section>`;
  const warehouse = `<section class="panel"><h2>창고</h2><div class="card-grid">${stock || '<p>창고에 물건이 없어요.</p>'}</div>
    <h3>내 판매 목록</h3>${mine ? `<div class="table-scroll"><table><thead><tr><th>물건</th><th>수량</th><th>가격</th><th>관리</th></tr></thead><tbody>${mine}</tbody></table></div>`
      : '<p>시장에 내놓은 물건이 없어요.</p>'}</section>`;
  const marketPanel = `<section class="panel"><h2>시장</h2><p>${trading ? '같은 물건은 개당 가격이 싼 것부터 보여요.' : '지금은 가격을 살펴보세요. 물건은 거래 단계에서 살 수 있어요.'}</p>
    <div class="card-grid market-grid">${market || '<p>시장에 나온 물건이 없어요.</p>'}</div></section>`;
  const direct = `<section class="panel"><h2>직접 거래</h2>
    <ul class="offer-list">${offers || '<li>아직 주고받은 제안이 없어요.</li>'}</ul>
    <div class="offer-form">
      <div class="fields"><label>제안할 나라 <select data-k="of-to">${others.map((n) => `<option value="${n}">${esc(S.names[n])}${S.students.includes(n) ? ' (학생)' : ''}</option>`).join('')}</select></label>
      <label>거래 방법 <select data-k="of-kind"><option value="sell">팔기</option><option value="buy">사기</option><option value="barter">물물교환</option></select></label></div>
      ${offerSide('give', '내가 줄 물건', 'banana')}
      ${offerSide('get', '내가 받을 물건', 'wheat')}
      <div class="fields"><label class="offer-cash">물건값 전체(G) <input data-k="of-cash" type="number" min="1"></label>
      <button data-act="offer">제안하기</button></div>
    </div></section>`;
  const investment = `<section class="panel"><h2>투자</h2>
    <p>대표 산업 ${esc(label(S.main))} · 이번 주력 ${esc(label(S.focus))}</p>
    <div class="card-grid">${inv || '<p>지금 투자할 수 있는 산업이 없어요.</p>'}</div>
    <div class="fields"><label>다음 라운드 주력 산업 <select data-k="focus">${Object.keys(S.levels).map((g) => `<option value="${g}" ${g === S.next_focus ? 'selected' : ''}>${esc(label(g))}</option>`).join('')}</select></label>
    <button data-act="focus">정하기</button></div></section>`;

  $('#status').hidden = false;
  render($('#identity'), `<h1>${esc(S.label)} · ${S.round}라운드 · ${esc(S.phase_label)}</h1>
    <span class="cash">돈 <strong>${S.cash}G</strong></span>`, drafts);
  drawBar();
  render($('#app'), `
    ${TASK[S.phase] ? `<div class="task"><strong>지금 할 일</strong> <span>${S.is_student ? TASK[S.phase] : '지금은 AI가 우리 나라를 운영해요.'}</span></div>` : ''}
    <p id="msg" role="status">${esc(lastMsg)}</p>
    ${results}
    ${S.phase === 'invest' ? investment : ''}
    ${trading ? direct + marketPanel : ''}
    ${S.phase !== 'finished' ? warehouse : ''}
    ${S.phase === 'listing' ? marketPanel : ''}
    ${progress}
    <section class="panel"><h2>이번 라운드 정산</h2>
      <p>판매 중인 물건은 정산에 쓸 수 없어요.</p>
      <div class="table-scroll"><table><thead><tr><th>물건</th><th>쓰임</th><th>필요</th><th>창고</th><th>상태</th></tr></thead><tbody>${st}</tbody></table></div>
      <p>연료는 ${S.operating_schedule.fuel.join('·')}라운드, 광물은 ${S.operating_schedule.ore.join('·')}라운드에 써요.</p>
    </section>
    <section class="panel"><h2>이번 라운드 거래</h2><ul>${S.transactions_this_round.map((t) => `<li>${esc(txText(t))}</li>`).join('') || '<li>아직 거래가 없어요.</li>'}</ul></section>`, drafts);
  syncOfferForm();
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
    const side = (p, g) => {
      const good = d(`of-${p}-good`) || g;
      const gen = ['machine', 'electronics'].includes(good) ? num(d(`of-${p}-gen`) || 1) : 1;
      return { good, gen, qty: num(d(`of-${p}-qty`) || 1) };
    };
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
  if (el) { e.preventDefault(); el.disabled = true; act(el).catch((err) => { lastMsg = err.message; S ? draw() : joinForm(); }).finally(() => { el.disabled = false; }); }
});

window.addEventListener('pagehide', () => { if (leavePresence) leavePresence(); });
joinForm();
if (drafts['join-room'] && drafts['join-pin']) join();
