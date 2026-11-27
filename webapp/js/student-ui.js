// Student view: a full-screen world map with a strategy-game HUD.
//   top left   resources (money and every good: icon + number, red badge when short at settlement)
//   left       menu (market, direct trade, investment, goals, log)
//   window     opens by itself when a phase starts (market in listing/trading, investment, result)
//   top right  notifications (shortages, offers to me, action results, phase changes)
//   bottom right  "turn" button = ready for the next phase
// All game actions go through StudentClient; the engine checks every rule.
import { StudentClient } from './student-client.js';
import { openServer, parseRoomCode, serverList, LOCAL_FLAG } from './transport.js';
import { esc, $, render, num, fmt } from './dom.js';
import { updateWorldMap, applyMapBackground } from './world-map.js';
import { goodIcon, uiIcon } from './good-icons.js';
import { createAdvisor } from './advisor-ui.js';

applyMapBackground($('#entry-map'));

const drafts = {};
let me = null;
let S = null;
let stateAt = 0;
let lastMsg = '';
let leavePresence = null;
let joining = false;
let world = null;          // 3D world (world-engine.js) or null
let worldFallback = false; // 2D atlas when WebGL is not available
let win = null;            // open window: market | trade | invest | goals | log | result | nation
let marketTab = 'buy';
let nationKey = null;
let phaseKey = null;
let advisor = null;       // 마루 선장(조언 캐릭터)
const toasts = [];         // {id, kind, icon, title, text, actions, until, sig}
const dismissed = new Set();
let toastSeq = 0;

const MODE = { teacher: '선생님이 넘겨요', ready: '모두 준비하면 넘어가요', ready_timer: '모두 준비하거나 시간이 끝나면 넘어가요' };
const COUNTRIES = { Tropia: '트로피아', Grainia: '그레니아', Oilia: '오일리아', Mechania: '메카니아', Mineria: '미네리아', Technia: '테크니아' };
const START_DIST = 50; // camera distance of the first view (world home view = about 100)
const GOODS = ['wheat', 'banana', 'fuel', 'ore', 'machine', 'electronics'];
const GEN_GOODS = ['machine', 'electronics'];
const PARTS = { export: '수출', industry: '산업', living: '생활', trade: '무역', utilization: '물건 활용', cash: '현금' };
const PHASE_START = {
  listing: ['listing', '판매 등록이 시작됐어요', '남는 물건을 시장에 내놓으세요. AI 나라 가격을 보고 정하면 좋아요.'],
  trading: ['trading', '거래가 시작됐어요', '필요한 물건을 사거나 다른 나라에 직접 거래를 제안하세요.'],
  invest: ['invest', '투자 시간이에요', '산업을 키우고 다음 라운드 주력 산업을 정하세요.'],
  finished: ['finished', '게임이 끝났어요', '우리 나라 목표 달성도를 확인하세요.'],
};

const params = new URLSearchParams(location.search);
for (const k of ['room', 'country', 'pin']) if (params.get(k)) drafts['join-' + k] = params.get(k);

// ---------------------------------------------------------------- joining
function joinForm() {
  $('#game').hidden = true;
  $('#app').hidden = false;
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
    lastMsg = r.ok ? '' : r.msg;
    if (!r.ok) { me = null; transport.close(); return; }
    leavePresence = server.presence.join({ role: 'student', room: parsed.code, country });
    advisor = createAdvisor({ root: $('#advisor'), storageKey: `trade-advisor-tour:${parsed.code}:${country}`, onAction: advisorAction });
    history.replaceState(null, '', `?room=${parsed.code}&country=${country}${LOCAL_FLAG ? '&local=1' : ''}`);
    draw();
  } catch (err) {
    transport?.close();
    me = null;
    S = null;
    lastMsg = err.message;
  } finally {
    joining = false;
    if (!me) joinForm();
  }
}

// ---------------------------------------------------------------- helpers
const label = (g) => (S ? S.goods[g] : g);
const gname = (n) => (S ? S.names[n] || n : n);
const genTxt = (good, gen) => (GEN_GOODS.includes(good) ? ` ${gen}세대` : '');
const icon = (g) => `<span class="g-${g}">${goodIcon(g)}</span>`;
const goodOptions = (sel) => GOODS.map((g) => `<option value="${g}" ${g === sel ? 'selected' : ''}>${S.goods[g]}</option>`).join('');
const mmss = (ms) => `${Math.floor(ms / 60000)}:${String(Math.floor((ms % 60000) / 1000)).padStart(2, '0')}`;
const left = (v) => (v === null || v === undefined ? null : (S.room.paused ? v : Math.max(0, v - (Date.now() - stateAt))));
const trading = () => S.phase === 'trading';
const selling = () => S.phase === 'listing' || S.phase === 'trading';
const incoming = (o) => o.status === 'pending' && o.to === S.country && trading();
const shortages = () => (S.phase === 'invest' || S.phase === 'finished' ? [] : S.settlement.rows.filter((r) => r.short > 0));
const myResult = () => Object.values(S.results || {}).find((r) => r.label === S.label);

function txText(t) {
  const legs = t.legs.map((l) => `${gname(l.seller)}→${gname(l.buyer)} ${l.label}${genTxt(l.good, l.gen)} ${l.qty}개`).join(', ');
  const cash = t.cash ? ` / ${gname(t.cash.payer)}→${gname(t.cash.payee)} ${t.cash.amount}G` : '';
  return `[${{ market: '시장', direct: '직접', barter: '물물교환' }[t.channel]}] ${legs}${cash}`;
}
function offerText(o) {
  const side = (s) => (s ? `${S.goods[s.good]}${genTxt(s.good, s.gen)} ${s.qty}개` : '');
  if (o.kind === 'sell') return `${gname(o.from)} → ${gname(o.to)}: ${side(o.give)}을(를) ${o.cash}G에 팔기`;
  if (o.kind === 'buy') return `${gname(o.from)} → ${gname(o.to)}: ${side(o.get)}을(를) ${o.cash}G에 사기`;
  return `${gname(o.from)}의 ${side(o.give)} ↔ ${gname(o.to)}의 ${side(o.get)}`;
}

// ---------------------------------------------------------------- map
async function ensureWorld() {
  if (world || worldFallback || ensureWorld.busy) return;
  ensureWorld.busy = true;
  try {
    const { createWorld } = await import('./world-engine.js');
    world = await createWorld($('#world'), {
      panel: false, political: false, theme: 'game', card: false, me: S.country, natBar: !matchMedia('(max-width: 700px)').matches,
      onSelect: (key) => { if (key && key !== S?.country) openNation(key); },
    });
    world.update(S);
    // Start like a strategy game: our country in the middle, neighbours and their cards around it.
    const home = world.nations?.find((n) => n.key === S.country);
    // Shift the target left so our country sits to the right of the window on wide screens.
    const shift = innerWidth > 900 ? START_DIST * 0.22 : 0;
    if (home) setTimeout(() => world?.flyTo(home.center.x - shift, home.center.z, START_DIST, 1.6), 400);
  } catch (e) {
    worldFallback = true;
    $('#world').classList.add('fallback');
    updateWorldMap($('#world'), S, { onPropose: (k) => { openTrade(k); } });
  } finally { ensureWorld.busy = false; }
}
function updateMap() {
  if (world) world.update(S);
  else if (worldFallback) updateWorldMap($('#world'), S, { onPropose: (k) => { openTrade(k); } });
  else ensureWorld();
}

// ---------------------------------------------------------------- HUD: resources and turn
function stockOf(good) {
  const rows = S.stock.filter((r) => r.good === good);
  return { free: rows.reduce((a, r) => a + r.free, 0), listed: rows.reduce((a, r) => a + r.listed, 0), rows };
}
function drawTop() {
  const short = new Map();
  for (const r of shortages()) short.set(r.good, (short.get(r.good) || 0) + r.short);
  const res = GOODS.map((g) => {
    const s = stockOf(g); const sh = short.get(g);
    const gens = GEN_GOODS.includes(g) && s.rows.length ? s.rows.map((r) => `${r.gen}세대 ${r.free}개`).join(', ') : '';
    const tip = `${label(g)}: 창고 ${s.free}개${s.listed ? `, 판매 중 ${s.listed}개` : ''}${gens ? ` (${gens})` : ''}${sh ? ` · 정산 때 ${sh}개 모자람` : ''}`;
    return `<div class="res${sh ? ' short' : ''}" ${sh ? `data-short="-${sh}"` : ''} title="${esc(tip)}" aria-label="${esc(tip)}">${icon(g)}<b>${s.free}</b>${s.listed ? `<small>+${s.listed}</small>` : ''}</div>`;
  }).join('');
  const phase = S.phase === 'finished' ? '게임 끝' : `${S.round}라운드 · ${S.phase_label}`;
  render($('#hud-top'), `
    <div class="res money" title="돈">${uiIcon('coin', 'coin')}<b>${S.cash}<small class="unit">G</small></b></div>${res}
    <div class="res turn"><strong>${esc(S.label)} · ${esc(phase)}</strong><span id="clock">${S.room?.paused ? '잠시 멈춤' : ''}</span></div>`, drafts);
  updateClock();
}

function drawTurn() {
  if (!S.room || S.phase === 'finished') { render($('#hud-turn'), '', drafts); return; }
  const R = S.room; const mine = R.ready.includes(S.country);
  const next = { listing: '거래로', trading: '투자로', invest: '다음 라운드로' }[S.phase] || '다음으로';
  // 턴 다이얼: 바깥 고리 = 준비한 나라 수, 가운데 = 지금 단계 그림, 아래 = 누르면 할 일
  const C = 2 * Math.PI * 46, frac = R.need.length ? R.ready.length / R.need.length : 0;
  const ring = `<svg class="turn-ring" viewBox="0 0 104 104" aria-hidden="true"><circle cx="52" cy="52" r="46" class="track"/><circle cx="52" cy="52" r="46" class="fill" stroke-dasharray="${(C * frac).toFixed(1)} ${C.toFixed(1)}"/></svg>`;
  const dial = (cls, attrs, label, sub) => `<button class="turn-dial ${cls}" ${attrs}>${ring}<span class="dial-core">${uiIcon(mine ? 'check' : S.phase)}</span><span class="dial-label">${label}${sub ? `<small>${sub}</small>` : ''}</span></button>`;
  const btn = !S.is_student ? dial('waiting', 'disabled', 'AI 운영 중', '')
    : mine ? dial('waiting', 'data-act="ready" data-on="0"', '준비 끝', '누르면 취소')
      : dial('', 'data-act="ready" data-on="1"', '준비 완료', next);
  render($('#hud-turn'), `<div class="turn-note">${esc(MODE[R.mode])} · 준비 <b>${R.ready.length}/${R.need.length}</b><b id="countdown"></b></div>${btn}`, drafts);
  updateClock();
}

function updateClock() {
  if (!S?.room || S.phase === 'finished') return;
  const R = S.room;
  const dl = left(R.deadline_ms); const cd = left(R.countdown_ms);
  const clock = $('#clock'); const countdown = $('#countdown');
  const time = R.paused ? '잠시 멈춤' : dl !== null ? `남은 시간 ${mmss(dl)}` : MODE[R.mode];
  if (clock && clock.textContent !== time) clock.textContent = time;
  const nx = cd !== null ? ` · ${Math.ceil(cd / 1000)}초 뒤 넘어가요` : '';
  if (countdown && countdown.textContent !== nx) countdown.textContent = nx;
}
setInterval(updateClock, 1000);

// ---------------------------------------------------------------- menu
function drawMenu() {
  const inc = S.offers.filter(incoming).length;
  const items = [
    ['market', 'market', '시장', selling(), 0],
    ['trade', 'trade', '거래', trading(), inc],
    ['invest', 'invest', '투자', S.phase === 'invest', 0],
    ['goals', 'goals', '목표', false, shortages().length],
    ['log', 'log', '기록', false, 0],
  ];
  if (S.phase === 'finished') items.unshift(['result', 'result', '결과', true, 0]);
  render($('#hud-menu'), items.map(([k, ico, t, hot, badge]) => `<button data-act="win" data-win="${k}" aria-pressed="${win === k}" class="${hot ? 'hot' : ''}">
    <span class="ico">${uiIcon(ico)}</span>${t}${badge ? `<span class="badge">${badge}</span>` : ''}</button>`).join(''), drafts);
}

// ---------------------------------------------------------------- notifications
function pushToast(t) {
  const id = ++toastSeq;
  toasts.push({ id, ...t, until: t.ms ? Date.now() + t.ms : null });
  drawToasts();
  if (t.ms) setTimeout(() => { const i = toasts.findIndex((x) => x.id === id); if (i >= 0) { toasts.splice(i, 1); drawToasts(); } }, t.ms);
}
function persistentToasts() {
  const out = [];
  if (S.room?.paused) out.push({ sig: 'paused', kind: 'warn', icon: 'pause', title: '잠시 멈췄어요', text: '선생님이 게임을 멈췄어요. 시간도 멈춰 있어요.' });
  if (!S.is_student && S.phase !== 'finished') out.push({ sig: 'ai', kind: 'warn', icon: 'ai', title: 'AI가 운영 중', text: '지금은 선생님이 우리 나라를 AI에게 맡겼어요.' });
  const sh = shortages();
  if (sh.length) {
    const sig = 'short:' + S.round + ':' + sh.map((r) => `${r.good}${r.short}`).join(',');
    out.push({ sig, kind: 'warn', icon: 'warn', title: '정산 때 모자라요',
      text: sh.map((r) => `${r.label} ${r.short}개 (${r.purpose})`).join(', ') + (trading() ? '. 시장에서 사거나 거래를 제안하세요.' : '. 거래 단계에서 구할 수 있어요.'),
      actions: [['시장 열기', 'market'], ['자세히', 'goals']] });
  }
  for (const o of S.offers.filter(incoming)) {
    out.push({ sig: 'offer:' + o.id, kind: '', icon: 'mail', title: `${gname(o.from)}의 제안`, text: offerText(o),
      actions: [['수락', `respond:${o.id}:1`], ['거절', `respond:${o.id}:0`]] });
  }
  return out.filter((t) => !dismissed.has(t.sig));
}
function drawToasts() {
  if (!S) return;
  const list = [...persistentToasts(), ...toasts];
  render($('#toasts'), list.map((t) => `<div class="toast ${t.kind || ''}" role="status"><span class="t-ico">${uiIcon(t.icon || 'bell')}</span>
    <div class="t-body"><b>${esc(t.title)}</b>${esc(t.text || '')}
    ${t.actions ? `<div class="t-actions">${t.actions.map(([txt, a]) => `<button class="btn ${a.endsWith(':0') ? 'ghost' : ''}" data-act="toast" data-do="${esc(a)}">${esc(txt)}</button>`).join('')}</div>` : ''}</div>
    <button class="x" data-act="dismiss" data-sig="${esc(t.sig || '')}" data-id="${t.id || ''}" aria-label="알림 닫기">×</button></div>`).join(''), drafts);
}

// ---------------------------------------------------------------- windows
function openWin(k) { win = k; drawWindow(); drawMenu(); }
function openNation(key) { nationKey = key; openWin('nation'); }
function openTrade(to) { if (to) drafts['of-to'] = to; openWin('trade'); }

function marketWindow() {
  const groups = new Map();
  for (const o of S.market.filter((x) => x.seller !== S.country)) {
    if (!groups.has(o.good)) groups.set(o.good, []);
    groups.get(o.good).push(o);
  }
  const buy = [...groups].map(([good, items]) => `<h3>${icon(good)} ${esc(label(good))} <small class="win-note">내 창고 ${stockOf(good).free}개</small></h3><ul class="rows">${items.sort((a, b) => a.price - b.price).map((o) => {
    const cls = o.price < o.reference ? 'cheap' : o.price > o.reference ? 'dear' : '';
    return `<li class="row"><div class="name"><b>${esc(o.seller_label)}</b><small>${o.seller_is_student ? '학생 · ' : ''}${genTxt(o.good, o.gen).trim() ? genTxt(o.good, o.gen).trim() + ' · ' : ''}${o.qty}개 판매 중</small></div>
      <div class="price ${cls}">${o.price}G<small>기준 ${o.reference}G</small></div>
      ${trading() ? `<div class="controls">${stepper('bq-' + o.oid, { max: o.qty, label: '구매 수량', unit: '개' })}<button class="btn" data-act="buy" data-oid="${o.oid}">사기</button></div>` : ''}</li>`;
  }).join('')}</ul>`).join('');
  const sell = S.stock.filter((r) => r.free > 0).map((r) => {
    const k = `${r.good}-${r.gen}`;
    return `<li class="row">${icon(r.good)}<div class="name"><b>${esc(r.label)}${genTxt(r.good, r.gen)}</b><small>창고 ${r.free}개 · 기준 ${S.quotes[r.good][r.gen]}G</small></div>
      <div class="controls"><label class="inline">수량${stepper('lq-' + k, { max: r.free, label: '내놓을 수량', unit: '개' })}</label>
      <label class="inline">개당${stepper('lp-' + k, { max: 999, value: S.quotes[r.good][r.gen], label: '개당 가격', unit: 'G' })}</label>
      <button class="btn" data-act="list" data-good="${r.good}" data-gen="${r.gen}">내놓기</button></div></li>`;
  }).join('');
  const mine = S.my_orders.map((o) => `<li class="row">${icon(o.good)}<div class="name"><b>${esc(o.label)}${genTxt(o.good, o.gen)} ${o.qty}개</b><small>기준 ${o.reference}G</small></div>
    <div class="price">${o.price}G</div>
    <div class="controls">${stepper('rp-' + o.oid, { max: 999, value: o.price, label: '새 가격', unit: 'G' })}<button class="btn ghost" data-act="reprice" data-oid="${o.oid}">가격 변경</button>
    <button class="btn ghost" data-act="cancel" data-oid="${o.oid}">거두기</button></div></li>`).join('');
  const tab = selling() ? marketTab : 'buy';
  const body = tab === 'buy'
    ? `<p class="win-note">${trading() ? '같은 물건은 싼 것부터 보여요. 초록은 기준보다 쌈, 빨강은 비쌈.' : '지금은 가격만 볼 수 있어요. 물건은 거래 단계에서 살 수 있어요.'}</p>${buy || '<p>시장에 나온 물건이 없어요.</p>'}`
    : `<p class="win-note">판매 중인 물건은 정산에 쓸 수 없어요. 안 팔린 물건은 거래 단계가 끝나면 창고로 돌아와요.</p>
       <h3>창고에서 내놓기</h3><ul class="rows">${sell || '<li class="row">창고에 내놓을 물건이 없어요.</li>'}</ul>
       <h3>내 판매 목록</h3><ul class="rows">${mine || '<li class="row">시장에 내놓은 물건이 없어요.</li>'}</ul>`;
  return [`시장 · ${S.phase_label}`, `${selling() ? `<div class="subtabs"><button data-act="mtab" data-tab="buy" aria-pressed="${tab === 'buy'}">사기</button><button data-act="mtab" data-tab="sell" aria-pressed="${tab === 'sell'}">팔기 (${S.my_orders.length})</button></div>` : '<p class="win-note">시장은 판매 등록·거래 단계에 열려요.</p>'}${body}`];
}

// [−] 값 [+] : 숫자 칸을 직접 치지 않고 눌러서 정한다(칸에 직접 쳐도 된다)
function stepper(key, { min = 1, max = 999, value = 1, step = 1, unit = '', label = '' } = {}) {
  return `<span class="stepper" data-min="${min}" data-max="${max}" data-step="${step}"${label ? ` aria-label="${esc(label)}"` : ''}>
    <button type="button" data-act="step" data-k="${key}" data-d="-1" aria-label="${esc(label)} 줄이기">−</button><input data-k="${key}" type="number" inputmode="numeric" min="${min}" max="${max}" value="${value}"${label ? ` aria-label="${esc(label)}"` : ''}>${unit ? `<i>${unit}</i>` : ''}<button type="button" data-act="step" data-k="${key}" data-d="1" aria-label="${esc(label)} 늘리기">+</button></span>`;
}
function offerSide(side, title, selected) {
  return `<div class="line offer-${side}"><b style="min-width:84px">${title}</b>
    <label>물건 <select data-k="of-${side}-good">${goodOptions(selected)}</select></label>
    <label class="generation">세대 ${stepper(`of-${side}-gen`, { max: 3, label: '세대' })}</label>
    <label>수량 ${stepper(`of-${side}-qty`, { label: '수량', unit: '개' })}</label></div>`;
}
function tradeWindow() {
  const others = S.countries.filter((n) => n !== S.country);
  const offers = S.offers.slice().reverse().sort((a, b) => Number(incoming(b)) - Number(incoming(a))).map((o) => {
    const status = { pending: '기다리는 중', accepted: '성사', rejected: '거절', cancelled: '취소', expired: '만료' }[o.status];
    const btn = o.status === 'pending' && trading()
      ? (o.to === S.country ? `<button class="btn" data-act="respond" data-id="${o.id}" data-acc="1">수락</button><button class="btn ghost" data-act="respond" data-id="${o.id}" data-acc="0">거절</button>`
        : `<button class="btn ghost" data-act="withdraw" data-id="${o.id}">취소</button>`) : '';
    return `<li class="row ${incoming(o) ? 'incoming' : ''}"><div class="name">${incoming(o) ? '<span class="tag">나에게 온 제안</span> ' : ''}${esc(offerText(o))}
      <small>${o.round}라운드 · ${status}${o.note ? ' · ' + esc(o.note) : ''}</small></div><div class="controls">${btn}</div></li>`;
  }).join('');
  const form = trading() ? `<div class="form offer-form">
      <div class="line"><label>나라 <select data-k="of-to">${others.map((n) => `<option value="${n}">${esc(gname(n))}${S.students.includes(n) ? ' (학생)' : ''}</option>`).join('')}</select></label>
      <label>방법 <select data-k="of-kind"><option value="sell">팔기</option><option value="buy">사기</option><option value="barter">물물교환</option></select></label></div>
      ${offerSide('give', '내가 줄 것', 'banana')}${offerSide('get', '내가 받을 것', 'wheat')}
      <div class="line"><label class="offer-cash">물건값 전체 ${stepper('of-cash', { max: 9999, value: 10, step: 5, label: '물건값 전체', unit: 'G' })}</label>
      <button class="btn" data-act="offer">제안하기</button></div></div>`
    : '<p class="win-note">직접 거래는 거래 단계에서 할 수 있어요. 지도에서 나라를 누르면 그 나라 정보를 볼 수 있어요.</p>';
  return ['직접 거래', `${form}<h3>주고받은 제안</h3><ul class="rows">${offers || '<li class="row">아직 제안이 없어요.</li>'}</ul>`];
}

function investWindow() {
  const inv = S.invest_options.map((o) => {
    const mats = [o.ore && `광물 ${o.ore}개`, o.machine_gen && `기계 ${o.machine_gen}세대 이상`].filter(Boolean);
    return `<li class="row">${icon(o.good)}<div class="name"><b>${esc(o.label)} Lv.${o.level} → ${o.next_level}</b>
      <small>${o.main ? '대표 산업 · ' : o.new_industry ? '새 산업 · ' : ''}재료: ${mats.join(', ') || '없음'}</small>
      ${o.ok ? '' : `<small class="dear">${esc(o.reasons.join(' · '))}</small>`}</div>
      <div class="price">${o.cost}G</div>${o.ok ? `<button class="btn" data-act="invest" data-good="${o.good}">투자</button>` : ''}</li>`;
  }).join('');
  const focus = `<div class="form"><div class="line"><label>다음 라운드 주력 산업 <select data-k="focus">${Object.keys(S.levels).map((g) => `<option value="${g}" ${g === S.next_focus ? 'selected' : ''}>${esc(label(g))}</option>`).join('')}</select></label>
    <button class="btn" data-act="focus">정하기</button></div></div>`;
  return ['투자', `<p>대표 산업 <b>${esc(label(S.main))}</b> · 이번 주력 <b>${esc(label(S.focus))}</b> · 다음 주력 <b>${esc(label(S.next_focus))}</b></p>
    ${S.phase === 'invest' ? '' : '<p class="win-note">투자는 투자 단계에서 할 수 있어요(1~7라운드, 라운드당 1번).</p>'}
    <h3>산업 키우기</h3><ul class="rows">${inv || '<li class="row">지금 투자할 수 있는 산업이 없어요.</li>'}</ul>
    ${S.phase === 'invest' ? `<h3>주력 산업</h3>${focus}` : ''}`];
}

function goalsWindow() {
  const p = S.progress;
  const pct = p.export_target > 0 ? Math.min(100, p.export_value / p.export_target * 100) : 0;
  const st = S.settlement.rows.map((r) => `<tr><td>${icon(r.good)} ${esc(r.label)}</td><td>${esc(r.purpose)}</td><td>${r.need}</td><td>${r.have}</td><td class="${r.short ? 'bad' : ''}">${r.short ? `${r.short}개 부족` : '충분'}</td></tr>`).join('');
  return ['우리 나라 목표', `
    <h3>수출 목표</h3><p>다른 나라에서 쓰인 우리 물건 <b>${fmt(p.export_value, 0)}</b> / ${p.export_target}G</p>
    <div class="bar"><i style="width:${pct}%"></i></div>
    <div class="stat"><span>대표 산업(${esc(label(S.main))})을 키웠나요?</span><b>${p.main_levelled ? '키웠어요' : '아직이에요'}</b></div>
    <div class="stat"><span>평균 만족도</span><b>${fmt(p.avg_happy)}</b></div>
    <div class="stat"><span>운영 자원 부족</span><b>${p.operating_short_days}일</b></div>
    <div class="stat"><span>급히 산 자원 비용</span><b>${p.emergency_paid}G</b></div>
    <h3>이번 라운드 정산</h3><table><thead><tr><th>물건</th><th>쓰임</th><th>필요</th><th>창고</th><th>상태</th></tr></thead><tbody>${st}</tbody></table>
    <p class="win-note">판매 중인 물건은 정산에 쓸 수 없어요. 연료는 ${S.operating_schedule.fuel.join('·')}라운드, 광물은 ${S.operating_schedule.ore.join('·')}라운드에 써요.</p>`];
}

function logWindow() {
  const mine = S.transactions_this_round.map((t) => `<li class="row">${esc(txText(t))}</li>`).join('');
  return ['이번 라운드 기록', `<h3>우리 나라 거래</h3><ul class="rows">${mine || '<li class="row">아직 거래가 없어요.</li>'}</ul>
    <h3>세계의 거래</h3><ul class="rows">${(S.world_trades || []).map((t) => `<li class="row">${esc(txText(t))}</li>`).join('') || '<li class="row">아직 거래가 없어요.</li>'}</ul>`];
}

function nationWindow() {
  const key = nationKey; const p = S.profiles?.[key] || {};
  const listings = S.market.filter((o) => o.seller === key).sort((a, b) => a.price - b.price);
  const levels = Object.entries(p.levels || {}).filter(([, lv]) => lv > 0).map(([g, lv]) => `${icon(g)} ${esc(label(g))} Lv.${lv}`).join(' · ');
  const canTrade = trading() && S.countries.includes(key);
  return [gname(key), `<p>${p.student ? '학생이 운영해요' : 'AI가 운영해요'}${p.evaluated === false ? ' · AI 전용 나라' : ''}</p>
    <p>대표 산업 <b>${esc(label(p.main) || '-')}</b> · 주력 <b>${esc(label(p.focus) || '-')}</b></p><p>${levels}</p>
    <h3>시장에 내놓은 물건</h3><ul class="rows">${listings.map((o) => `<li class="row">${icon(o.good)}<div class="name"><b>${esc(o.label)}${genTxt(o.good, o.gen)}</b><small>${o.qty}개</small></div>
      <div class="price">${o.price}G<small>기준 ${o.reference}G</small></div>${trading() ? `<div class="controls">${stepper('bq-' + o.oid, { max: o.qty, label: '구매 수량', unit: '개' })}<button class="btn" data-act="buy" data-oid="${o.oid}">사기</button></div>` : ''}</li>`).join('') || '<li class="row">지금 내놓은 물건이 없어요.</li>'}</ul>
    ${S.countries.includes(key) ? `<p style="margin-top:12px"><button class="btn" data-act="propose" data-to="${key}" ${canTrade ? '' : 'disabled'}>${canTrade ? '직접 거래 제안하기' : '거래 단계에서 제안할 수 있어요'}</button></p>` : '<p class="win-note">이 나라와는 직접 거래할 수 없어요.</p>'}`];
}

function resultWindow() {
  const r = myResult();
  if (!r) return ['결과', '<p>결과를 계산하는 중이에요.</p>'];
  return ['결과 · 우리 나라 목표 달성도', `<p><span class="big-score">${fmt(r.total)}</span> 점 · <span class="tag" style="font-size:1.1rem">${esc(r.grade)} 등급</span></p>
    ${Object.entries(PARTS).map(([k, t]) => `<div class="stat"><span>${t}</span><b>${fmt(r.parts[k])}점</b></div>`).join('')}`];
}

const WINDOWS = { market: marketWindow, trade: tradeWindow, invest: investWindow, goals: goalsWindow, log: logWindow, nation: nationWindow, result: resultWindow };
function drawWindow() {
  const el = $('#window');
  if (!win || !S || !WINDOWS[win] || (win === 'nation' && !nationKey)) { el.hidden = true; render(el, '', drafts); return; }
  const [title, body] = WINDOWS[win]();
  el.hidden = false; el.className = `hud-window win-${win}`;
  const emblem = { market: 'market', trade: 'trade', invest: 'invest', goals: 'goals', log: 'log', result: 'result', nation: 'nation' }[win];
  render(el, `<header class="win-head"><span class="win-emblem">${uiIcon(emblem)}</span><h2>${esc(title)}</h2><button class="close" data-act="close" aria-label="창 닫기">×</button></header>
    <div class="win-body">${lastMsg ? `<p class="win-note" role="status">${esc(lastMsg)}</p>` : ''}${body}</div>`, drafts);
  syncOfferForm();
}

function syncOfferForm() {
  const form = $('.offer-form');
  if (!form) return;
  const kind = $('[data-k="of-kind"]', form).value;
  $('.offer-give', form).hidden = kind === 'buy';
  $('.offer-get', form).hidden = kind === 'sell';
  $('.offer-cash', form).hidden = kind === 'barter';
  for (const side of ['give', 'get']) {
    const good = form.querySelector(`[data-k="of-${side}-good"]`).value;
    form.querySelector(`[data-k="of-${side}-gen"]`).closest('label').hidden = !GEN_GOODS.includes(good);
  }
}
document.addEventListener('change', (e) => { if (e.target.closest('.offer-form')) syncOfferForm(); });

// ---------------------------------------------------------------- draw
function onPhase() {
  const key = `${S.round}:${S.phase}`;
  if (key === phaseKey) return;
  const first = phaseKey === null;
  phaseKey = key;
  lastMsg = '';
  // The market opens by itself on its turn; other phases open their own window.
  if (S.phase === 'listing') { marketTab = 'sell'; win = 'market'; }
  else if (S.phase === 'trading') { marketTab = 'buy'; win = 'market'; }
  else if (S.phase === 'invest') win = 'invest';
  else if (S.phase === 'finished') win = 'result';
  const [ico, title, text] = PHASE_START[S.phase] || [];
  if (title && !(first && S.phase === 'finished')) pushToast({ icon: ico, title: `${S.round}라운드 · ${title}`, text, ms: 5000, kind: 'ok' });
}

function draw() {
  if (!S) return;
  $('#app').hidden = true;
  $('#entry-map').style.display = 'none';
  $('#game').hidden = false;
  onPhase();
  updateMap();
  drawTop();
  drawMenu();
  drawTurn();
  drawWindow();
  drawToasts();
  advisor?.update(S);
}

// 입력값을 바꿀 때 화면에 이미 있는 칸에도 바로 넣는다(창이 열려 있으면 다시 그리지 않으므로)
function setDraft(k, v) {
  drafts[k] = String(v);
  for (const el of document.querySelectorAll(`[data-k="${CSS.escape(k)}"]`)) el.value = String(v);
}
// 조언 버튼: 알맞은 창을 연다(게임 행동은 학생이 직접 한다)
function advisorAction(a) {
  if (a.startsWith('market:')) { // 'market:sell:물건-세대:수량' → 팔기 탭에 수량을 채워 연다
    const [, tab, gk, qty] = a.split(':'); marketTab = tab; openWin('market'); if (gk && qty) setDraft('lq-' + gk, qty); return; }
  if (a.startsWith('trade:')) { // 'trade:나라:물건:수량:값' → 사기 제안서를 채워서 연다
    const [, to, good, qty, cash] = a.split(':');
    openWin('trade');
    for (const [k, v] of Object.entries({ 'of-kind': 'buy', 'of-get-good': good, 'of-get-qty': qty, 'of-cash': cash, ...(to ? { 'of-to': to } : {}) })) setDraft(k, v);
    syncOfferForm(); return;
  }
  openWin(a);
}

// ---------------------------------------------------------------- actions
async function act(el) {
  const a = el.dataset.act;
  if (a === 'join') return join();
  if (!me) return;
  if (a === 'win') { win = win === el.dataset.win ? null : el.dataset.win; return draw(); }
  if (a === 'step') {
    const box = el.closest('.stepper'), input = box.querySelector('input'), lo = Number(box.dataset.min), hi = Number(box.dataset.max), st = Number(box.dataset.step) || 1;
    let v = num(input.value); if (!Number.isFinite(v)) v = lo;
    v = Math.max(lo, Math.min(hi, v + st * Number(el.dataset.d))); input.value = v; drafts[el.dataset.k] = String(v);
    return;
  }
  if (a === 'close') { win = null; return draw(); }
  if (a === 'mtab') { marketTab = el.dataset.tab; return drawWindow(); }
  if (a === 'propose') { openTrade(el.dataset.to); return; }
  if (a === 'dismiss') {
    if (el.dataset.sig) dismissed.add(el.dataset.sig);
    const i = toasts.findIndex((t) => String(t.id) === el.dataset.id); if (i >= 0) toasts.splice(i, 1);
    return drawToasts();
  }
  if (a === 'toast') {
    const d = el.dataset.do;
    if (d.startsWith('respond:')) { const [, id, acc] = d.split(':'); return result(await me.respond(num(id), acc === '1')); }
    if (d === 'market') { marketTab = 'buy'; }
    return openWin(d);
  }
  let r;
  const d = (k) => (drafts[k] !== undefined ? drafts[k] : document.querySelector(`[data-k="${CSS.escape(k)}"]`)?.value);
  if (a === 'list') {
    const k = `${el.dataset.good}-${el.dataset.gen}`;
    const price = d('lp-' + k) === undefined || d('lp-' + k) === '' ? S.quotes[el.dataset.good][el.dataset.gen] : num(d('lp-' + k));
    r = await me.list(el.dataset.good, num(d('lq-' + k)), price, num(el.dataset.gen));
    if (r.ok) { delete drafts['lq-' + k]; delete drafts['lp-' + k]; }
  } else if (a === 'reprice') r = await me.reprice(num(el.dataset.oid), num(d('rp-' + el.dataset.oid)));
  else if (a === 'cancel') r = await me.cancel(num(el.dataset.oid));
  else if (a === 'buy') r = await me.buy(num(el.dataset.oid), num(d('bq-' + el.dataset.oid) || 1));
  else if (a === 'offer') {
    const kind = d('of-kind') || 'sell';
    const side = (p, g) => {
      const good = d(`of-${p}-good`) || g;
      const gen = GEN_GOODS.includes(good) ? num(d(`of-${p}-gen`) || 1) : 1;
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
  if (r) result(r);
}
function result(r) {
  // AI 나라에 보낸 제안은 ok:true여도 accepted:false면 거절이다
  const good = r.ok && r.accepted !== false;
  pushToast({ kind: good ? 'ok' : 'warn', icon: good ? 'check' : 'cross', title: !r.ok ? '안 됐어요' : r.accepted === false ? '거절됐어요' : r.accepted ? '거래 성사!' : '완료', text: r.msg, ms: good ? 3500 : 6000 });
  draw();
}

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-act]');
  if (el) { e.preventDefault(); el.disabled = true; act(el).catch((err) => { if (S) pushToast({ kind: 'warn', icon: 'cross', title: '오류', text: err.message, ms: 6000 }); else { lastMsg = err.message; joinForm(); } }).finally(() => { el.disabled = false; }); }
});
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && win) { win = null; draw(); } });

window.addEventListener('pagehide', () => { if (leavePresence) leavePresence(); });
joinForm();
if (drafts['join-room'] && drafts['join-pin']) join();
