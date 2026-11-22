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
let mapCountry = null;
let mapMessage = '';
let displayedTrade = null;
let departedAt = 0;
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
    me.onState((state) => {
      if (S?.round !== state.round || S?.phase !== state.phase) mapMessage = '';
      const previousTrades = S?.round === state.round ? S.transactions_this_round.length : 0;
      const latest = state.transactions_this_round.length - 1;
      if (latest >= previousTrades) {
        displayedTrade = latest;
        // Joining partway through a round shows the latest route without replaying it.
        departedAt = S ? performance.now() : 0;
      } else if (S?.round !== state.round || displayedTrade > latest) {
        displayedTrade = null;
        departedAt = 0;
      }
      S = state;
      stateAt = Date.now();
      draw();
    });
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

// Positions are in percent of the map artwork. A country is a real button so the
// same map works with a touch screen, a mouse, and a keyboard.
const MAP_POSITIONS = {
  // Western continent
  Mineria: [13, 14, 'west'], Grainia: [19, 39, 'west'], Tropia: [12, 65, 'west'], Oilia: [34, 50, 'west'],
  // Eastern continent
  Technia: [66, 23, 'east'], Mechania: [89, 34, 'east'], Novia: [72, 54, 'east'],
  // Southern continent
  Agrea: [36, 81, 'south'], Ferria: [56, 86, 'south'],
};

function worldMap() {
  const markers = Object.entries(MAP_POSITIONS).filter(([country]) => S.countries.includes(country));
  return `<section id="world" class="panel world-panel">
    <h2>세계 무역 지도</h2>
    <p class="atlas-help">지도를 끌어 이동하고, 휠이나 두 손가락 또는 +·−로 크기를 바꿔 보세요. 나라를 누르면 시장이 열려요.</p>
    <p class="atlas-flat-help">나라를 누르면 판매 물건과 교역로를 볼 수 있어요.</p>
    <div class="world-layout">
      <div class="route-view">
        <div class="atlas-frame" data-atlas-country="${esc(S.country)}">
        <div class="world-map" role="group" aria-label="세계지도에서 나라 고르기">
          <canvas class="atlas-canvas" tabindex="0" aria-label="3D 지도. 화살표로 이동, 더하기와 빼기로 확대·축소, 0으로 처음 보기"></canvas>
          <span class="atlas-cargo-badge" aria-hidden="true" hidden></span>
          <span class="atlas-cargo-badge" aria-hidden="true" hidden></span>
          <span class="ocean-surface" aria-hidden="true"></span>
          <span class="map-compass" aria-hidden="true">북<span>✦</span></span>
          <span class="map-route" aria-hidden="true" hidden></span>
          <div class="delivery-layer" aria-hidden="true"></div>
          ${markers.map(([country, [x, y]]) => `
            <button type="button" class="country-marker ${country === S.country ? 'our-country' : ''}"
              style="--map-x:${x}%;--map-y:${y}%" data-act="map-select" data-country="${country}"
              aria-controls="world-country" aria-pressed="false">
              ${country === S.country ? '<span aria-hidden="true">★</span><span class="sr-only">우리 나라 </span>' : ''}
              ${esc(gname(country))}
            </button>`).join('')}
        </div>
          <div class="atlas-controls" role="group" aria-label="지도 카메라">
            <button type="button" data-camera="in" aria-label="지도 확대" title="지도 확대">+</button>
            <button type="button" data-camera="out" aria-label="지도 축소" title="지도 축소">−</button>
            <button type="button" data-camera="left" aria-label="왼쪽으로 돌리기" title="왼쪽으로 돌리기">↶</button>
            <button type="button" data-camera="right" aria-label="오른쪽으로 돌리기" title="오른쪽으로 돌리기">↷</button>
            <button type="button" data-camera="reset" aria-label="처음 시점" title="처음 시점">⌂</button>
          </div>
        </div>
        <section id="route-cargo" class="route-cargo" aria-label="교역로와 운송 물건"></section>
      </div>
      <div id="world-country" class="world-country" role="region" aria-label="선택한 나라"></div>
    </div>
  </section>`;
}

function routeCoordinates(start, end) {
  // Measure height against width using the map's 3:2 aspect ratio.
  const dx = end[0] - start[0];
  const dy = (end[1] - start[1]) * 2 / 3;
  return `--route-x:${start[0]}%;--route-y:${start[1]}%;--end-x:${end[0]}%;--end-y:${end[1]}%;` +
    `--route-length:${Math.hypot(dx, dy)}%;--route-angle:${Math.atan2(dy, dx)}rad`;
}

const cargoName = (leg) => `${leg.label}${genTxt(leg.good, leg.gen)} ${leg.qty}개`;
const TRIP_MS = 5200;

// The hand-painted map has a road junction, harbor and offshore way point per continent.
const CONTINENT_ROUTES = {
  west: { junction: [18, 46], harbor: [34, 56], offshore: [42, 61] },
  east: { junction: [68, 42], harbor: [61, 46], offshore: [58, 52] },
  south: { junction: [47, 80], harbor: [55, 70], offshore: [54, 65] },
};

function shipmentStages(leg, airRoutes = false) {
  const start = MAP_POSITIONS[leg.seller];
  const end = MAP_POSITIONS[leg.buyer];
  const origin = CONTINENT_ROUTES[start[2]];
  const destination = CONTINENT_ROUTES[end[2]];
  if (origin === destination) {
    return [{ type: 'truck', points: [start, origin.junction, end], from: 0, to: 1 }];
  }
  if (airRoutes && leg.good === 'electronics') {
    return [{ type: 'plane', points: [start, [start[0] * .5 + end[0] * .5, (start[1] + end[1]) / 2 - 7], end], from: 0, to: 1 }];
  }
  return [
    { type: 'truck', points: [start, origin.junction, origin.harbor], from: 0, to: .23 },
    { type: 'ship', points: [origin.harbor, origin.offshore, destination.offshore, destination.harbor], from: .23, to: .77 },
    { type: 'truck', points: [destination.harbor, destination.junction, end], from: .77, to: 1 },
  ];
}

function animateShipment(vehicle, stage, elapsed) {
  const { points, from, to } = stage;
  const distances = [0];
  for (let i = 1; i < points.length; i++) {
    const [a, b] = [points[i - 1], points[i]];
    distances.push(distances[i - 1] + Math.hypot(b[0] - a[0], (b[1] - a[1]) * 2 / 3));
  }
  const offsets = distances.map((distance) => distance / distances.at(-1));
  const timing = { duration: (to - from) * TRIP_MS, delay: from * TRIP_MS - elapsed, fill: 'forwards' };
  vehicle.animate(points.map(([x, y], i) => ({
    offset: offsets[i], left: `${x}%`, top: `${y}%`, visibility: i === points.length - 1 ? 'hidden' : 'visible',
  })), timing);
  const sprite = vehicle.querySelector('img');
  sprite.animate(points.map(([x], i) => {
    const next = points[i + 1];
    const facingLeft = next ? next[0] < x : x < points[i - 1][0];
    return { offset: offsets[i], transform: `scaleX(${facingLeft ? -1 : 1})`, easing: 'steps(1, end)' };
  }), { ...timing, fill: 'both' });
}

function drawShipments(layer, legs, elapsed) {
  const active = [];
  layer.innerHTML = legs.map((leg, i) => shipmentStages(leg).map((stage) => {
    const path = stage.points.slice(1).map((point, j) =>
      `<span class="map-route delivery-line delivery-line-${i} delivery-${stage.type}-line" style="${routeCoordinates(stage.points[j], point)}"></span>`).join('');
    if (elapsed >= stage.to * TRIP_MS) return path;
    active.push(stage);
    return `${path}<span class="delivery-vehicle delivery-vehicle-${i} delivery-${stage.type}"
      data-seller="${esc(leg.seller)}" data-buyer="${esc(leg.buyer)}" data-vehicle="${stage.type}">
      <span class="vehicle-cargo">${esc(cargoName(leg))}</span>
      <img src="art/cargo-${stage.type}.webp" alt="" draggable="false">
    </span>`;
  }).join('')).join('');
  if (!matchMedia('(prefers-reduced-motion: reduce)').matches) {
    layer.querySelectorAll('.delivery-vehicle').forEach((vehicle, i) => animateShipment(vehicle, active[i], elapsed));
  }
}

function drawMapRoute(country) {
  const preview = $('.map-route');
  if (!preview) return;
  const trade = S.transactions_this_round[displayedTrade];
  const legs = trade?.legs.filter((leg) => MAP_POSITIONS[leg.seller] && MAP_POSITIONS[leg.buyer]) || [];
  preview.hidden = Boolean(legs.length) || country === S.country || !MAP_POSITIONS[country];
  if (!preview.hidden) preview.style.cssText = routeCoordinates(MAP_POSITIONS[S.country], MAP_POSITIONS[country]);

  tradeAtlas?.setRoute(country, legs, departedAt);
  const layer = $('.delivery-layer');
  const routeKey = JSON.stringify([legs, departedAt]);
  if (layer.dataset.routeKey !== routeKey) {
    layer.dataset.routeKey = routeKey;
    const elapsed = departedAt ? performance.now() - departedAt : TRIP_MS;
    if (!tradeAtlas?.ready) drawShipments(layer, legs, elapsed);
  }

  const cargo = $('#route-cargo');
  render(cargo, `<h3>교역로의 물건</h3>
    ${legs.length ? `<ul class="cargo-legs">${legs.map((leg) => `<li>${icon(leg.good)}<div>
      <strong>${esc(cargoName(leg))}</strong><small>${esc(gname(leg.seller))} → ${esc(gname(leg.buyer))} · ${MAP_POSITIONS[leg.seller][2] === MAP_POSITIONS[leg.buyer][2] ? '화물차' : tradeAtlas?.ready && leg.good === 'electronics' ? '비행기' : '화물차와 배'}</small></div>
    </li>`).join('')}</ul>
    <button type="button" data-act="replay-route" data-index="${displayedTrade}">운송 다시 보기</button>`
    : '<p>거래가 성사되면 이곳에 보낸 물건과 교역로가 표시돼요.</p>'}
    ${S.transactions_this_round.length > 1 ? `<label>이번 라운드 교역로
      <select id="trade-route-choice" data-k="route-history"><option value="">교역로 고르기</option>
      ${S.transactions_this_round.map((t, i) => `<option value="${i}">${i + 1}. ${esc(t.legs.map(cargoName).join(' ↔ '))} · ${esc(gname(t.legs[0].seller))} → ${esc(gname(t.legs[0].buyer))}</option>`).join('')}
      </select></label>` : ''}`, drafts);
  const choice = $('#trade-route-choice');
  if (choice) choice.value = displayedTrade ?? '';
}

function playRoute(index) {
  if (!S.transactions_this_round[index]) return;
  displayedTrade = index;
  departedAt = performance.now();
  drawMapRoute(mapCountry || S.country);
}

document.addEventListener('change', (e) => {
  if (e.target.id !== 'trade-route-choice') return;
  if (e.target.value) playRoute(num(e.target.value));
  else {
    displayedTrade = null;
    departedAt = 0;
    drawMapRoute(mapCountry || S.country);
  }
});

function drawWorldCountry() {
  const panel = $('#world-country');
  if (!panel) return;
  const country = mapCountry || S.country;
  const ours = country === S.country;
  drawMapRoute(country);
  const canTrade = S.phase === 'trading' && S.is_student && !ours;
  const selling = S.market.filter((order) => order.seller === country).sort((a, b) => a.price - b.price);
  for (const marker of document.querySelectorAll('.country-marker')) {
    const pressed = String(marker.dataset.country === country);
    if (marker.getAttribute('aria-pressed') !== pressed) marker.setAttribute('aria-pressed', pressed);
  }
  const orders = selling.map((o) => `<li>
    <div class="map-order-title">${icon(o.good)}<div><strong>${esc(o.label)}${genTxt(o.good, o.gen)}</strong><small>${o.qty}개 판매 중</small></div></div>
    <p class="map-order-price">개당 <strong>${o.price}G</strong><small>기준 ${o.reference}G</small></p>
    ${canTrade ? `<div class="buy-actions">
      <input data-k="map-qty-${o.oid}" aria-label="${esc(o.label)}${genTxt(o.good, o.gen)} 구매 수량" type="number" min="1" max="${o.qty}" value="1">
      <button data-act="map-buy" data-oid="${o.oid}">사기</button>
    </div>` : ''}
  </li>`).join('');
  render(panel, `
    <div class="world-country-heading"><h3>${esc(gname(country))}</h3>
      <span class="tag">${ours ? '우리 나라' : S.students.includes(country) ? '학생 운영' : 'AI 운영'}</span></div>
    <p class="map-message" role="status">${esc(mapMessage)}</p>
    <h4>시장에 내놓은 물건</h4>
    ${orders ? `<ul class="map-orders">${orders}</ul>` : '<p>지금 시장에 내놓은 물건이 없어요.</p>'}
    ${ours ? '<a class="map-warehouse" href="#warehouse">우리 창고 보기 ↓</a>'
      : canTrade ? `<button data-act="map-offer" data-country="${country}">직접 거래 제안하기</button>`
        : S.is_student ? '<p class="map-hint">물건을 사거나 제안하려면 거래 단계까지 기다려 주세요.</p>'
          : '<p class="map-hint">지금은 AI가 우리 나라를 운영해요.</p>'}
  `, drafts);
}

function offerFromMap(country) {
  if (S.phase !== 'trading' || !S.is_student || country === S.country || !S.countries.includes(country)) return;
  const select = $('[data-k="of-to"]');
  if (!select) return;
  drafts['of-to'] = country;
  select.value = country;
  $('.offer-form').scrollIntoView({ block: 'start' });
  select.focus({ preventScroll: true });
}

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
  const results = result ? `<section id="outcome" class="panel result">
    <h2>결과 · 우리 나라 목표 달성도</h2>
    <div class="score"><strong>${fmt(result.total)}<small>점</small></strong><span>${esc(result.grade)} 등급</span></div>
    <dl class="card-grid score-grid">${Object.entries(PARTS).map(([k, title]) => `<div><dt>${title}</dt><dd>${fmt(result.parts[k])}점</dd></div>`).join('')}</dl>
  </section>` : '';
  const progress = `<section id="progress" class="panel"><h2>진행 상황</h2><p><strong>다른 나라에서 쓰인 우리 물건</strong> · ${fmt(p.export_value, 0)} / 목표 ${p.export_target}G</p>
    ${p.export_target > 0 ? `<progress aria-label="수출 목표 달성도" value="${Math.min(p.export_value, p.export_target)}" max="${p.export_target}"></progress>` : ''}
    <dl class="metrics progress-metrics"><div><dt>대표 산업을 키웠나요?</dt><dd>${p.main_levelled ? '키웠어요' : '아직이에요'}</dd></div>
    <div><dt>평균 만족도</dt><dd>${fmt(p.avg_happy)}</dd></div><div><dt>운영 자원 부족</dt><dd>${p.operating_short_days}일</dd></div>
    <div><dt>급히 산 자원 비용</dt><dd>${p.emergency_paid}G</dd></div></dl></section>`;
  const warehouse = `<section id="warehouse" class="panel"><h2>창고</h2><div class="card-grid">${stock || '<p>창고에 물건이 없어요.</p>'}</div>
    <h3>내 판매 목록</h3>${mine ? `<div class="table-scroll"><table><thead><tr><th>물건</th><th>수량</th><th>가격</th><th>관리</th></tr></thead><tbody>${mine}</tbody></table></div>`
      : '<p>시장에 내놓은 물건이 없어요.</p>'}</section>`;
  const marketPanel = `<section id="market" class="panel"><h2>시장</h2><p>${trading ? '같은 물건은 개당 가격이 싼 것부터 보여요.' : '지금은 가격을 살펴보세요. 물건은 거래 단계에서 살 수 있어요.'}</p>
    <div class="card-grid market-grid">${market || '<p>시장에 나온 물건이 없어요.</p>'}</div></section>`;
  const direct = `<section id="offers" class="panel"><h2>직접 거래</h2>
    <ul class="offer-list">${offers || '<li>아직 주고받은 제안이 없어요.</li>'}</ul>
    <div class="offer-form">
      <div class="fields"><label>제안할 나라 <select data-k="of-to">${others.map((n) => `<option value="${n}">${esc(S.names[n])}${S.students.includes(n) ? ' (학생)' : ''}</option>`).join('')}</select></label>
      <label>거래 방법 <select data-k="of-kind"><option value="sell">팔기</option><option value="buy">사기</option><option value="barter">물물교환</option></select></label></div>
      ${offerSide('give', '내가 줄 물건', 'banana')}
      ${offerSide('get', '내가 받을 물건', 'wheat')}
      <div class="fields"><label class="offer-cash">물건값 전체(G) <input data-k="of-cash" type="number" min="1"></label>
      <button data-act="offer">제안하기</button></div>
    </div></section>`;
  const investment = `<section id="industry" class="panel"><h2>투자</h2>
    <p>대표 산업 ${esc(label(S.main))} · 이번 주력 ${esc(label(S.focus))}</p>
    <div class="card-grid">${inv || '<p>지금 투자할 수 있는 산업이 없어요.</p>'}</div>
    <div class="fields"><label>다음 라운드 주력 산업 <select data-k="focus">${Object.keys(S.levels).map((g) => `<option value="${g}" ${g === S.next_focus ? 'selected' : ''}>${esc(label(g))}</option>`).join('')}</select></label>
    <button data-act="focus">정하기</button></div></section>`;

  const destinations = {
    listing: [['warehouse', '📦', '창고'], ['market', '⚓', '시장']],
    trading: [['market', '⚓', '시장'], ['offers', '🤝', '직접 거래'], ['warehouse', '📦', '창고']],
    invest: [['industry', '⚙️', '산업'], ['warehouse', '📦', '창고']],
    finished: [['outcome', '🏅', '결과']],
  };
  const places = [...(TASK[S.phase] ? [['world', '🧭', '세계 지도']] : []), ...destinations[S.phase], ['progress', '📜', '목표'], ['settlement', '🌾', '정산']];
  const phaseNames = { listing: '판매 등록', trading: '거래', invest: '투자' };
  const phaseTrack = `<ol class="phase-track" aria-label="라운드 진행 순서">${Object.entries(phaseNames).map(([key, name]) =>
    `<li${key === S.phase ? ' aria-current="step"' : ''}>${name}</li>`).join('')}</ol>`;
  const mapNav = `<nav class="map-nav" aria-label="나라 운영 메뉴">${places.map(([id, mark, title]) =>
    `<a href="#${id}"><span aria-hidden="true">${mark}</span>${title}</a>`).join('')}</nav>`;

  const active = document.activeElement;
  const previousMap = $('.atlas-frame');
  const mapInput = active.closest('#world') && active.dataset.k;
  const mapMarker = active.matches('.country-marker') && active.dataset.country;
  const wasMapControl = previousMap?.contains(active);
  $('#status').hidden = false;
  render($('#identity'), `<h1>${esc(S.label)} · ${S.round}라운드 · ${esc(S.phase_label)}</h1>
    <span class="cash">국고 <strong>${S.cash}G</strong></span>`, drafts);
  drawBar();
  render($('#app'), `
    <div class="command-map">
      ${TASK[S.phase] ? phaseTrack : ''}
      ${mapNav}
      ${TASK[S.phase] ? `<div class="task"><strong>지금 할 일</strong> <span>${S.is_student ? TASK[S.phase] : '지금은 AI가 우리 나라를 운영해요.'}</span></div>` : ''}
    </div>
    <p id="msg" role="status">${esc(lastMsg)}</p>
    ${results}
    ${TASK[S.phase] ? worldMap() : ''}
    ${S.phase === 'invest' ? investment : ''}
    ${trading ? direct + marketPanel : ''}
    ${S.phase !== 'finished' ? warehouse : ''}
    ${S.phase === 'listing' ? marketPanel : ''}
    ${progress}
    <section id="settlement" class="panel"><h2>이번 라운드 정산</h2>
      <p>판매 중인 물건은 정산에 쓸 수 없어요.</p>
      <div class="table-scroll"><table><thead><tr><th>물건</th><th>쓰임</th><th>필요</th><th>창고</th><th>상태</th></tr></thead><tbody>${st}</tbody></table></div>
      <p>연료는 ${S.operating_schedule.fuel.join('·')}라운드, 광물은 ${S.operating_schedule.ore.join('·')}라운드에 써요.</p>
    </section>
    <section class="panel"><h2>이번 라운드 거래</h2><ul>${S.transactions_this_round.map((t) => `<li>${esc(txText(t))}</li>`).join('') || '<li>아직 거래가 없어요.</li>'}</ul></section>`, drafts);
  const frame = $('.atlas-frame');
  if (frame && previousMap && frame !== previousMap && frame.dataset.atlasCountry === previousMap.dataset.atlasCountry) {
    frame.replaceWith(previousMap);
  }
  updateAtlas($('.world-map'));
  drawWorldCountry();
  if (active !== document.activeElement) {
    if (mapInput) $(`#world [data-k="${CSS.escape(mapInput)}"]`)?.focus({ preventScroll: true });
    if (mapMarker) $(`.country-marker[data-country="${CSS.escape(mapMarker)}"]`)?.focus({ preventScroll: true });
    else if (wasMapControl && active.isConnected) active.focus({ preventScroll: true });
  }
  syncOfferForm();
}

async function act(el) {
  const a = el.dataset.act;
  if (a === 'join') return join();
  if (!me) return;
  let r;
  const beforeTrade = { round: S?.round, count: S?.transactions_this_round.length };
  const d = (k) => drafts[k];
  if (a === 'list') {
    const k = `${el.dataset.good}-${el.dataset.gen}`;
    r = await me.list(el.dataset.good, num(d('lq-' + k)), num(d('lp-' + k)), num(el.dataset.gen));
    if (r.ok) { delete drafts['lq-' + k]; delete drafts['lp-' + k]; }
  } else if (a === 'reprice') r = await me.reprice(num(el.dataset.oid), num(d('rp-' + el.dataset.oid)));
  else if (a === 'cancel') r = await me.cancel(num(el.dataset.oid));
  else if (a === 'buy' || a === 'map-buy') {
    const fromMap = a === 'map-buy';
    const oid = num(el.dataset.oid);
    const country = mapCountry || S.country;
    const key = `${fromMap ? 'map-qty' : 'bq'}-${oid}`;
    r = await me.buy(oid, num(d(key) || 1));
    if (fromMap && country === (mapCountry || S.country)) mapMessage = r.msg;
  }
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
  if (r) {
    lastMsg = r.msg;
    draw();
    const confirmed = r.ok && (a === 'buy' || a === 'map-buy' ||
      (a === 'offer' && r.accepted) || (a === 'respond' && el.dataset.acc === '1'));
    const map = $('.world-map');
    if (confirmed && map && S.round === beforeTrade.round && S.transactions_this_round.length > beforeTrade.count) {
      const rect = map.getBoundingClientRect();
      if (rect.bottom <= $('#status').getBoundingClientRect().bottom || rect.top >= innerHeight) {
        $('#world').scrollIntoView({ block: 'start' });
        playRoute(S.transactions_this_round.length - 1);
      }
    }
  }
}

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-act]');
  if (!el) return;
  e.preventDefault();
  if (el.dataset.act === 'replay-route') {
    playRoute(num(el.dataset.index));
    return;
  }
  if (el.dataset.act === 'map-select') {
    mapCountry = el.dataset.country;
    mapMessage = '';
    const latestOnRoute = S.transactions_this_round.findLastIndex((t) =>
      t.legs.some((leg) => mapCountry !== S.country && (leg.seller === mapCountry || leg.buyer === mapCountry)));
    displayedTrade = latestOnRoute === -1 ? null : latestOnRoute;
    departedAt = 0;
    drawWorldCountry();
    return;
  }
  if (el.dataset.act === 'map-offer') {
    offerFromMap(el.dataset.country);
    return;
  }
  el.disabled = true;
  act(el).catch((err) => { lastMsg = err.message; S ? draw() : joinForm(); }).finally(() => { el.disabled = false; });
});

// The atlas is a WebGL heightfield. Coordinates use a width of 18 and depth of 12
// so the same port and road waypoints serve both the 3D map and the 2D fallback.
const MAP_WIDTH = 18;
const MAP_DEPTH = 12;
const TERRAIN_WIDTH = 145;
const TERRAIN_DEPTH = 97;
const within = (value, low, high) => Math.max(low, Math.min(high, value));
const mapXZ = ([u, v]) => [(u / 100 - .5) * MAP_WIDTH, (v / 100 - .5) * MAP_DEPTH];
const worldUV = (x, z) => [x / MAP_WIDTH + .5, z / MAP_DEPTH + .5];

const ATLAS_VERTEX = `#version 300 es
  layout(location = 0) in vec3 position;
  layout(location = 1) in vec3 color;
  uniform mat4 camera;
  out vec3 p;
  out vec3 rgb;
  void main() {
    p = position;
    rgb = color;
    gl_Position = camera * vec4(position, 1.);
  }`;

const ATLAS_FRAGMENT = `#version 300 es
  precision mediump float;
  uniform sampler2D atlas;
  uniform sampler2D ocean;
  uniform int layer;
  uniform float time;
  in vec3 p;
  in vec3 rgb;
  out vec4 pixel;
  void main() {
    vec2 uv = vec2(p.x / 18., p.z / 12.) + .5;
    vec3 art = texture(atlas, uv).rgb;
    if (layer == 2) {
      pixel = vec4(rgb, 1.);
    } else if (layer == 1) {
      if (texture(ocean, uv).a > .55 || min(min(uv.x, uv.y), min(1. - uv.x, 1. - uv.y)) < .017) discard;
      vec3 normal = normalize(cross(dFdx(p), dFdy(p)));
      float sun = max(0., dot(normal, normalize(vec3(-.65, 1., .35))));
      float coast = clamp(1. - p.y * 2.6, 0., 1.);
      vec3 ground = mix(art, art * vec3(1.07, 1.025, .95), .55);
      ground = ground * (.66 + sun * .46) + vec3(.07, .055, .04) * coast;
      pixel = vec4(ground, 1.);
    } else {
      float waves = sin(p.x * 18. + p.z * 5. + time * 1.4) * .46
        + sin(p.z * 23. - p.x * 9. - time * 1.7) * .32
        + sin(p.x * 42. + p.z * 19. + time * 2.1) * .22;
      vec3 water = mix(vec3(.025, .22, .27), max(art * 1.06, vec3(.025, .14, .19)), .57);
      float edge = smoothstep(.01, .1, min(min(uv.x, uv.y), min(1. - uv.x, 1. - uv.y)));
      float shimmer = smoothstep(.52, .94, waves);
      vec3 openSea = vec3(.028, .19, .244) + vec3(.008, .026, .03) * sin(p.x * .23 + p.z * .08);
      pixel = vec4(mix(openSea, water, edge) + vec3(.039, .081, .092) * shimmer, 1.);
    }
  }`;

function atlasProgram(gl) {
  const program = gl.createProgram();
  const shaders = [[gl.VERTEX_SHADER, ATLAS_VERTEX], [gl.FRAGMENT_SHADER, ATLAS_FRAGMENT]].map(([type, source]) => {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader));
    gl.attachShader(program, shader);
    return shader;
  });
  gl.linkProgram(program);
  shaders.forEach((shader) => gl.deleteShader(shader));
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
  return program;
}

const atlasImage = (src) => new Promise((resolve, reject) => {
  const picture = new Image();
  picture.onload = () => resolve(picture);
  picture.onerror = reject;
  picture.src = src;
});

function imagePixels(image) {
  const canvas = document.createElement('canvas');
  canvas.width = TERRAIN_WIDTH;
  canvas.height = TERRAIN_DEPTH;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
  return ctx.getImageData(0, 0, canvas.width, canvas.height).data;
}

function atlasTerrain(art, mask) {
  const { length } = mask;
  const coast = new Uint8Array(length / 4);
  // A distance grid creates a low shoreline and rising inland terrain.
  for (let i = 0; i < coast.length; i++) coast[i] = mask[i * 4 + 3] > 115 ? 0 : 24;
  for (let i = 0; i < coast.length; i++) {
    if (i % TERRAIN_WIDTH) coast[i] = Math.min(coast[i], coast[i - 1] + 1);
    if (i >= TERRAIN_WIDTH) coast[i] = Math.min(coast[i], coast[i - TERRAIN_WIDTH] + 1);
  }
  for (let i = coast.length - 1; i >= 0; i--) {
    if (i % TERRAIN_WIDTH < TERRAIN_WIDTH - 1) coast[i] = Math.min(coast[i], coast[i + 1] + 1);
    if (i + TERRAIN_WIDTH < coast.length) coast[i] = Math.min(coast[i], coast[i + TERRAIN_WIDTH] + 1);
  }
  const elevation = Float32Array.from(coast, (distance, i) => {
    if (!distance) return -.065;
    const [r, g, b] = art.subarray(i * 4, i * 4 + 3);
    const snow = Math.max(0, (Math.min(r, g, b) - 80) / 145);
    const ridges = Math.sin(i % TERRAIN_WIDTH * .47) * Math.sin(Math.floor(i / TERRAIN_WIDTH) * .37);
    const inland = Math.min(1, distance / 10);
    return .05 + inland * (.13 + snow ** 1.65 * .93 + ridges * .06);
  });
  const vertices = [];
  const indices = [];
  for (let v = 0; v < TERRAIN_DEPTH; v++) {
    for (let u = 0; u < TERRAIN_WIDTH; u++) {
      const i = v * TERRAIN_WIDTH + u;
      vertices.push((u / (TERRAIN_WIDTH - 1) - .5) * MAP_WIDTH, elevation[i],
        (v / (TERRAIN_DEPTH - 1) - .5) * MAP_DEPTH, 0, 0, 0);
      if (u && v) indices.push(i, i - 1, i - TERRAIN_WIDTH, i - 1, i - TERRAIN_WIDTH - 1, i - TERRAIN_WIDTH);
    }
  }
  return { vertices, indices, elevation };
}

const shade = (c, scale) => c.map((value) => value * scale);
function triangle(output, a, b, c, color) {
  for (const point of [a, b, c]) output.push(...point, ...color);
}
function quad(output, a, b, c, d, color) {
  triangle(output, a, b, c, color);
  triangle(output, a, c, d, color);
}

function piece(output, x, y, z, width, height, depth, color, yaw = 0) {
  const cos = Math.cos(yaw);
  const sin = Math.sin(yaw);
  const p = (u, h, v) => [x + u * cos - v * sin, y + h, z + u * sin + v * cos];
  const w = width / 2, d = depth / 2;
  const a = p(-w, 0, -d), b = p(w, 0, -d), c = p(w, 0, d), e = p(-w, 0, d);
  const f = p(-w, height, -d), g = p(w, height, -d), h = p(w, height, d), j = p(-w, height, d);
  quad(output, f, j, h, g, color);
  quad(output, a, b, g, f, shade(color, .74));
  quad(output, b, c, h, g, shade(color, .87));
  quad(output, c, e, j, h, shade(color, .63));
  quad(output, e, a, f, j, shade(color, .95));
}

function modelVehicle(output, type, x, y, z, yaw) {
  const at = (forward, up, side, w, h, d, color) => piece(output,
    x + forward * Math.cos(yaw) - side * Math.sin(yaw), y + up,
    z + forward * Math.sin(yaw) + side * Math.cos(yaw), w, h, d, color, yaw);
  const gold = [.97, .68, .29], pale = [.95, .9, .72], navy = [.14, .23, .3];
  if (type === 'truck') {
    at(0, .048, 0, .35, .065, .16, navy);
    at(.096, .1, 0, .144, .115, .158, [.92, .42, .12]);
    at(.133, .155, 0, .04, .048, .161, [.55, .78, .81]);
    at(-.092, .112, 0, .146, .083, .143, gold);
    for (const forward of [-.114, .105]) for (const side of [-.081, .081]) at(forward, .016, side, .075, .075, .043, navy);
  } else if (type === 'ship') {
    at(-.035, .005, 0, .48, .091, .194, [.4, .20, .13]);
    at(.22, .025, 0, .1, .07, .125, [.57, .28, .16]);
    at(-.03, .095, 0, .395, .027, .17, gold);
    at(-.134, .12, 0, .127, .128, .126, pale);
    at(-.145, .246, 0, .056, .088, .052, navy);
    at(.055, .12, -.04, .12, .052, .068, [.77, .38, .14]);
    at(.055, .12, .041, .12, .054, .069, gold);
  } else {
    at(0, .03, 0, .52, .076, .091, pale);
    at(.14, .096, 0, .13, .032, .062, [.28, .67, .76]);
    at(.014, .046, 0, .156, .036, .5, [.91, .33, .14]);
    at(-.197, .046, 0, .095, .026, .227, pale);
    at(-.2, .074, 0, .089, .123, .029, [.91, .33, .14]);
    for (const side of [-.12, .12]) at(.05, .012, side, .115, .059, .064, navy);
  }
}

function makeCraft(type, points, begin = 0, end = 1) {
  const nodes = points.map(mapXZ);
  const lengths = [0];
  for (let i = 1; i < nodes.length; i++) {
    lengths.push(lengths[i - 1] + Math.hypot(nodes[i][0] - nodes[i - 1][0], nodes[i][1] - nodes[i - 1][1]));
  }
  return { type, nodes, lengths, begin, end };
}

function craftLocation({ nodes, lengths }, progress) {
  const distance = within(progress, 0, 1) * lengths.at(-1);
  let i = 1;
  while (i < lengths.length - 1 && lengths[i] < distance) i++;
  const weight = (distance - lengths[i - 1]) / (lengths[i] - lengths[i - 1] || 1);
  const [[ax, az], [bx, bz]] = [nodes[i - 1], nodes[i]];
  return [ax + (bx - ax) * weight, az + (bz - az) * weight, Math.atan2(bz - az, bx - ax)];
}

class TradeAtlas {
  constructor(viewport) {
    this.viewport = viewport;
    this.canvas = $('.atlas-canvas', viewport);
    this.gl = this.canvas.getContext('webgl2', { alpha: false, antialias: true, powerPreference: 'low-power' });
    if (!this.gl) throw new Error('WebGL is unavailable');
    const info = this.gl.getExtension('WEBGL_debug_renderer_info');
    this.software = Boolean(info && /swiftshader|llvmpipe|software/i.test(this.gl.getParameter(info.UNMASKED_RENDERER_WEBGL)));
    this.camera = { x: 0, z: 0, zoom: 1, yaw: -.12 };
    this.visible = true;
    this.motion = matchMedia('(prefers-reduced-motion: reduce)');
    this.pointers = new Map();
    this.routes = [];
    this.labels = [...viewport.querySelectorAll('.country-marker')];
  }

  async init() {
    const [art, ocean] = await Promise.all([atlasImage('art/world-map.webp'), atlasImage('art/ocean-mask.webp')]);
    if (this.disposed) return;
    const gl = this.gl;
    this.program = atlasProgram(gl);
    gl.useProgram(this.program);
    this.uniform = Object.fromEntries(['camera', 'time', 'layer'].map((key) => [key, gl.getUniformLocation(this.program, key)]));
    for (const [i, image] of [art, ocean].entries()) {
      gl.activeTexture(gl.TEXTURE0 + i);
      gl.bindTexture(gl.TEXTURE_2D, gl.createTexture());
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.generateMipmap(gl.TEXTURE_2D);
      gl.uniform1i(gl.getUniformLocation(this.program, i ? 'ocean' : 'atlas'), i);
    }
    const terrain = atlasTerrain(imagePixels(art), imagePixels(ocean));
    this.elevation = terrain.elevation;
    this.terrain = this.buffer(terrain.vertices, terrain.indices);
    const water = [];
    quad(water, [-24, -.05, -21], [24, -.05, -21], [24, -.05, 21], [-24, -.05, 21], [0, 0, 0]);
    this.water = this.buffer(water);
    this.props = this.buffer(this.scenery());
    this.dynamic = this.buffer([]);
    this.ambient = this.traffic().map((craft) => ({
      forward: craft,
      reverse: makeCraft(craft.type, craft.nodes.map(([x, z]) => worldUV(x, z).map((value) => value * 100)).reverse()),
    }));
    const roads = [];
    for (const { forward } of this.ambient) this.routeRibbon(roads, forward, [.39, .53, .46], .013, forward.type === 'plane');
    this.ambientRoads = this.buffer(roads);
    gl.enable(gl.DEPTH_TEST);
    this.ready = true;
    this.viewport.classList.add('is-3d');
    this.canvas.addEventListener('webglcontextlost', () => {
      if (this !== tradeAtlas) return;
      this.viewport.classList.remove('is-3d');
      this.viewport.dataset.atlasUnavailable = 'true';
      for (const label of this.labels) {
        const [x, y] = MAP_POSITIONS[label.dataset.country];
        label.style.setProperty('--map-x', `${x}%`);
        label.style.setProperty('--map-y', `${y}%`);
        label.style.visibility = '';
      }
      this.destroy();
      tradeAtlas = null;
      $('.delivery-layer', this.viewport).dataset.routeKey = '';
      drawMapRoute(mapCountry || S.country);
    }, { once: true });
    this.controls();
    this.resize = new ResizeObserver(() => this.render());
    this.resize.observe(this.viewport);
    this.intersection = new IntersectionObserver(([entry]) => {
      this.visible = entry.isIntersecting;
      if (this.visible) this.startFrames();
    });
    this.intersection.observe(this.viewport);
    this.motionListener = () => { this.render(); this.startFrames(); };
    this.motion.addEventListener('change', this.motionListener);
    this.render();
    this.startFrames();
  }

  buffer(vertices, indices) {
    const gl = this.gl;
    const vao = gl.createVertexArray();
    gl.bindVertexArray(vao);
    const vbo = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(vertices), gl.STATIC_DRAW);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 24, 0);
    gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 24, 12);
    gl.enableVertexAttribArray(0);
    gl.enableVertexAttribArray(1);
    if (indices) {
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, gl.createBuffer());
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array(indices), gl.STATIC_DRAW);
    }
    return { vao, vbo, indexed: Boolean(indices), count: indices?.length ?? vertices.length / 6 };
  }

  surface(x, z) {
    const [u, v] = worldUV(x, z);
    const col = within(u * (TERRAIN_WIDTH - 1), 0, TERRAIN_WIDTH - 1.001);
    const row = within(v * (TERRAIN_DEPTH - 1), 0, TERRAIN_DEPTH - 1.001);
    const i = Math.floor(row) * TERRAIN_WIDTH + Math.floor(col);
    const dx = col % 1, dz = row % 1;
    const a = this.elevation[i] * (1 - dx) + this.elevation[i + 1] * dx;
    const b = this.elevation[i + TERRAIN_WIDTH] * (1 - dx) + this.elevation[i + TERRAIN_WIDTH + 1] * dx;
    return a * (1 - dz) + b * dz;
  }

  scenery() {
    const output = [];
    for (const [i, country] of Object.values(MAP_POSITIONS).entries()) {
      const [x, z] = mapXZ(country);
      for (let j = 0; j < 9; j++) {
        const angle = j * 2.39 + i;
        const radius = .16 + j * .039;
        const bx = x + Math.cos(angle) * radius, bz = z + Math.sin(angle) * radius;
        const by = this.surface(bx, bz);
        if (by < 0) continue;
        const tall = .076 + (j % 3) * .035;
        piece(output, bx, by, bz, .105, tall, .088, [.9, .78, .53], angle);
        piece(output, bx, by + tall, bz, .118, .038, .1, [[.73,.29,.15],[.41,.54,.55],[.72,.41,.18]][i % 3], angle);
      }
    }
    for (const { harbor, offshore } of Object.values(CONTINENT_ROUTES)) {
      const [[x, z], [tx, tz]] = [mapXZ(harbor), mapXZ(offshore)];
      const angle = Math.atan2(tz - z, tx - x);
      piece(output, x + Math.cos(angle) * .19, .02, z + Math.sin(angle) * .19, .38, .065, .125, [.61, .44, .25], angle);
      piece(output, x, Math.max(0, this.surface(x, z)), z, .17, .12, .13, [.96, .8, .46], angle);
    }
    return output;
  }

  traffic() {
    const { west, east, south } = CONTINENT_ROUTES;
    return [
      makeCraft('truck', [MAP_POSITIONS.Tropia, west.junction, MAP_POSITIONS.Grainia]),
      makeCraft('truck', [MAP_POSITIONS.Mechania, east.junction, MAP_POSITIONS.Novia]),
      makeCraft('truck', [MAP_POSITIONS.Agrea, south.junction, MAP_POSITIONS.Ferria]),
      makeCraft('ship', [west.harbor, west.offshore, east.offshore, east.harbor]),
      makeCraft('ship', [east.harbor, east.offshore, south.offshore, south.harbor]),
      makeCraft('plane', [MAP_POSITIONS.Agrea, [41, 69], [28, 68], MAP_POSITIONS.Tropia]),
    ];
  }

  setRoute(country, legs, departed) {
    const key = JSON.stringify([country, legs, departed]);
    if (key === this.routeKey) return;
    this.routeKey = key;
    this.preview = country !== S.country ? [MAP_POSITIONS[S.country], MAP_POSITIONS[country]] : null;
    this.routes = legs.map((leg) => ({
      cargo: cargoName(leg),
      stages: shipmentStages(leg, true).map(({ type, points, from, to }) => makeCraft(type, points, from, to)),
    }));
    this.departed = departed;
    if (this.ready) {
      const old = this.activeRoads;
      const paths = [];
      if (!this.routes.length && this.preview?.every(Boolean)) {
        this.routeRibbon(paths, makeCraft('truck', this.preview), [.95, .82, .49], .028, true);
      }
      this.routes.forEach(({ stages }, i) => stages.forEach((stage) =>
        this.routeRibbon(paths, stage, i ? [.54, .94, .97] : [1., .81, .36], .039, stage.type === 'plane')));
      this.activeRoads = this.buffer(paths);
      if (old) { this.gl.deleteBuffer(old.vbo); this.gl.deleteVertexArray(old.vao); }
      this.render();
    }
  }

  matrices(width, height) {
    const { x, z, yaw, zoom } = this.camera;
    const pitch = width < 500 ? 1.17 : .96;
    const sy = Math.sin(yaw), cy = Math.cos(yaw), sp = Math.sin(pitch), cp = Math.cos(pitch);
    const halfW = Math.max(width < 500 ? 10.3 : 10.9, 5.95 * width / height) / zoom;
    const halfH = halfW * height / width;
    const right = [cy / halfW, 0, -sy / halfW];
    const up = [-sy * sp / halfH, cp / halfH, -cy * sp / halfH];
    const depth = [-sy * cp / 30, -sp / 30, -cy * cp / 30];
    return new Float32Array([
      right[0], up[0], depth[0], 0, right[1], up[1], depth[1], 0, right[2], up[2], depth[2], 0,
      -x * right[0] - z * right[2], -x * up[0] - z * up[2], -x * depth[0] - z * depth[2], 1,
    ]);
  }

  project(x, y, z) {
    const m = this.matrix;
    return [50 * (1 + x * m[0] + y * m[4] + z * m[8] + m[12]),
      50 * (1 - x * m[1] - y * m[5] - z * m[9] - m[13])];
  }

  routeRibbon(output, craft, color, width, dashed = false) {
    const steps = Math.max(2, Math.ceil(craft.lengths.at(-1) * 13));
    for (let i = 0; i < steps; i++) {
      if (dashed && i % 3 === 2) continue;
      const [ax, az] = craftLocation(craft, i / steps);
      const [bx, bz] = craftLocation(craft, (i + 1) / steps);
      const len = Math.hypot(bx - ax, bz - az) || 1;
      const dx = (bz - az) * width / len, dz = (ax - bx) * width / len;
      const y = (x, z) => Math.max(.003, this.surface(x, z)) + .055;
      quad(output, [ax + dx, y(ax, az), az + dz], [ax - dx, y(ax, az), az - dz],
        [bx - dx, y(bx, bz), bz - dz], [bx + dx, y(bx, bz), bz + dz], color);
    }
  }

  craft(output, stage, progress) {
    const [x, z, yaw] = craftLocation(stage, progress);
    const y = stage.type === 'plane' ? .69 + Math.sin(progress * Math.PI) * .34
      : stage.type === 'ship' ? .012 : Math.max(.012, this.surface(x, z));
    modelVehicle(output, stage.type, x, y, z, yaw);
    return this.project(x, y + .31, z);
  }

  render(now = performance.now()) {
    if (!this.ready || this.disposed) return;
    const width = this.viewport.clientWidth, height = this.viewport.clientHeight;
    if (!width || !height) return;
    const gl = this.gl;
    const ratio = Math.min(devicePixelRatio, this.software ? .85 : 1.5);
    const w = Math.round(width * ratio), h = Math.round(height * ratio);
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w;
      this.canvas.height = h;
    }
    gl.viewport(0, 0, w, h);
    gl.clearColor(.055, .22, .27, 1);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    this.matrix = this.matrices(width, height);
    gl.uniformMatrix4fv(this.uniform.camera, false, this.matrix);
    const clock = this.motion.matches ? 0 : now / 1000;
    gl.uniform1f(this.uniform.time, clock % 180.0);
    const draw = (buffer, mode) => {
      gl.uniform1i(this.uniform.layer, mode);
      gl.bindVertexArray(buffer.vao);
      if (buffer.indexed) gl.drawElements(gl.TRIANGLES, buffer.count, gl.UNSIGNED_SHORT, 0);
      else gl.drawArrays(gl.TRIANGLES, 0, buffer.count);
    };
    draw(this.water, 0);
    draw(this.terrain, 1);
    draw(this.props, 2);
    draw(this.ambientRoads, 2);
    if (this.activeRoads) draw(this.activeRoads, 2);
    const mesh = [];
    if (!this.motion.matches) for (const [i, { forward, reverse }] of this.ambient.entries()) {
      const travel = (clock / (22 + i * 2) + i * .27) % 2;
      this.craft(mesh, travel < 1 ? forward : reverse, travel % 1);
    }
    const elapsed = this.departed ? (now - this.departed) / TRIP_MS : 2;
    for (const [i, badge] of this.badges.entries()) {
      const route = this.routes[i];
      let position;
      if (route) for (const stage of route.stages) {
        if (!this.motion.matches && elapsed >= stage.begin && elapsed < stage.end) {
          position = this.craft(mesh, stage, (elapsed - stage.begin) / (stage.end - stage.begin));
        }
      }
      badge.hidden = !position || position.some((v) => v < 3 || v > 97);
      if (!badge.hidden) {
        badge.style.left = `${position[0]}%`;
        badge.style.top = `${position[1]}%`;
        if (badge.textContent !== route.cargo) badge.textContent = route.cargo;
      }
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, this.dynamic.vbo);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(mesh), gl.STREAM_DRAW);
    this.dynamic.count = mesh.length / 6;
    draw(this.dynamic, 2);
    const labelKey = JSON.stringify([width, height, this.camera]);
    if (this.labelKey === labelKey) return;
    this.labelKey = labelKey;
    for (const label of this.labels) {
      const [x, z] = mapXZ(MAP_POSITIONS[label.dataset.country]);
      const [left, top] = this.project(x, Math.max(0, this.surface(x, z)) + .37, z);
      label.style.setProperty('--map-x', `${left}%`);
      label.style.setProperty('--map-y', `${top}%`);
      label.style.visibility = left < 4 || left > 96 || top < 5 || top > 95 ? 'hidden' : '';
    }
  }

  startFrames() {
    if (this.frame || this.motion.matches || !this.visible || this.disposed) return;
    this.frame = requestAnimationFrame((time) => {
      this.frame = 0;
      if (!this.visible || !this.viewport.isConnected || this.disposed) return;
      if (time - (this.previousFrame || 0) > (this.software ? 42 : 26)) {
        this.previousFrame = time;
        this.render(time);
      }
      this.startFrames();
    });
  }

  changeCamera(action, point) {
    const camera = this.camera;
    if (action === 'reset') Object.assign(camera, { x: 0, z: 0, zoom: 1, yaw: -.12 });
    if (action === 'left' || action === 'right') camera.yaw += action === 'right' ? .23 : -.23;
    if (typeof action === 'number') {
      const previous = camera.zoom;
      camera.zoom = within(previous * action, .8, 5);
      if (point && camera.zoom !== previous) {
        const rect = this.canvas.getBoundingClientRect();
        const offset = 1 - previous / camera.zoom;
        this.pan(-(point.x - rect.left - rect.width / 2) * offset,
          -(point.y - rect.top - rect.height / 2) * offset, previous);
      }
    }
    this.render();
  }

  pan(dx, dy, zoom = this.camera.zoom) {
    const { yaw } = this.camera;
    const width = this.viewport.clientWidth, height = this.viewport.clientHeight;
    const worldPerPixel = 2 * Math.max(width < 500 ? 10.3 : 10.9, 5.95 * width / height) / width / zoom;
    const across = -dx * worldPerPixel, down = -dy * worldPerPixel / Math.sin(width < 500 ? 1.17 : .96);
    this.camera.x = within(this.camera.x + across * Math.cos(yaw) + down * Math.sin(yaw), -9, 9);
    this.camera.z = within(this.camera.z - across * Math.sin(yaw) + down * Math.cos(yaw), -6, 6);
  }

  controls() {
    const canvas = this.canvas;
    this.badges = [...this.viewport.querySelectorAll('.atlas-cargo-badge')];
    this.viewport.addEventListener('wheel', (event) => {
      if (this.disposed) return;
      event.preventDefault();
      this.changeCamera(Math.exp(-within(event.deltaY, -160, 160) * .003), { x: event.clientX, y: event.clientY });
    }, { passive: false });
    canvas.addEventListener('keydown', (event) => {
      const arrows = { ArrowLeft: [34, 0], ArrowRight: [-34, 0], ArrowUp: [0, 34], ArrowDown: [0, -34] };
      if (arrows[event.key]) { event.preventDefault(); this.pan(...arrows[event.key]); this.render(); }
      if (['+', '=', '-', '0'].includes(event.key)) {
        event.preventDefault();
        this.changeCamera(event.key === '0' ? 'reset' : event.key === '-' ? .8 : 1.25);
      }
    });
    const point = (event) => ({ x: event.clientX, y: event.clientY });
    canvas.addEventListener('pointerdown', (event) => {
      if (event.button !== 0 || this.pointers.size >= 2) return;
      canvas.setPointerCapture(event.pointerId);
      this.pointers.set(event.pointerId, point(event));
      canvas.classList.add('dragging');
    });
    canvas.addEventListener('pointermove', (event) => {
      const old = this.pointers.get(event.pointerId);
      if (!old) return;
      const next = point(event);
      const other = [...this.pointers].find(([id]) => id !== event.pointerId)?.[1];
      this.pointers.set(event.pointerId, next);
      if (other) {
        const prevDistance = Math.hypot(old.x - other.x, old.y - other.y);
        const newDistance = Math.hypot(next.x - other.x, next.y - other.y);
        if (prevDistance > 5) this.changeCamera(newDistance / prevDistance,
          { x: (next.x + other.x) / 2, y: (next.y + other.y) / 2 });
      } else {
        this.pan(next.x - old.x, next.y - old.y);
        this.render();
      }
    });
    for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) {
      canvas.addEventListener(type, (event) => {
        this.pointers.delete(event.pointerId);
        if (!this.pointers.size) canvas.classList.remove('dragging');
      });
    }
    this.viewport.parentElement.querySelectorAll('[data-camera]').forEach((button) => button.addEventListener('click', () => {
      const action = button.dataset.camera;
      this.changeCamera(action === 'in' ? 1.3 : action === 'out' ? 1 / 1.3 : action);
    }));
  }

  destroy() {
    this.disposed = true;
    cancelAnimationFrame(this.frame);
    this.resize?.disconnect();
    this.intersection?.disconnect();
    if (this.motionListener) this.motion.removeEventListener('change', this.motionListener);
    this.gl.getExtension('WEBGL_lose_context')?.loseContext();
  }
}

let tradeAtlas;
function updateAtlas(viewport) {
  if (tradeAtlas?.viewport === viewport) return;
  tradeAtlas?.destroy();
  tradeAtlas = null;
  if (!viewport || viewport.dataset.atlasUnavailable) return;
  try {
    const scene = new TradeAtlas(viewport);
    tradeAtlas = scene;
    scene.init().then(() => {
      if (scene === tradeAtlas && scene.ready) {
        scene.routeKey = null;
        drawMapRoute(mapCountry || S.country);
      }
    }).catch(() => {
      if (scene !== tradeAtlas) return;
      viewport.dataset.atlasUnavailable = 'true';
      viewport.classList.remove('is-3d');
      scene.destroy();
      tradeAtlas = null;
    });
  } catch {
    viewport.dataset.atlasUnavailable = 'true';
    // The regular map and all trade controls are still available without WebGL.
  }
}

window.addEventListener('pagehide', () => { if (leavePresence) leavePresence(); });
joinForm();
if (drafts['join-room'] && drafts['join-pin']) join();
