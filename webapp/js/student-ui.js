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
  Mineria: [13, 21, 'west'], Grainia: [19, 39, 'west'], Tropia: [12, 65, 'west'], Oilia: [30, 48, 'west'],
  // Eastern continent
  Technia: [65, 26, 'east'], Mechania: [88, 38, 'east'], Novia: [72, 54, 'east'],
  // Southern continent
  Agrea: [37, 83, 'south'], Ferria: [56, 86, 'south'],
};

function worldMap() {
  const markers = Object.entries(MAP_POSITIONS).filter(([country]) => S.countries.includes(country));
  return `<section id="world" class="panel world-panel">
    <h2>세계 무역 지도</h2>
    <p class="atlas-help">다른 나라를 누르면 판매 물건과 교역로가 열려요.</p>
    <p class="atlas-flat-help">나라를 누르면 판매 물건과 교역로를 볼 수 있어요.</p>
    <div class="world-layout">
      <div class="route-view">
        <div class="atlas-frame showing-harbor" data-atlas-country="${esc(S.country)}">
          <div class="harbor-view">
            <div class="harbor-window" tabindex="0" role="group" aria-label="항구에서 갈 곳 고르기">
              <div class="harbor-picture">
                <img src="art/harbor-panorama.webp" alt="벽돌 창고 앞에 배가 정박해 있고, 시장 광장 너머로 밀밭과 풍차가 보여요." draggable="false" fetchpriority="high">
                <div class="harbor-water" aria-hidden="true"></div>
                <div class="harbor-deliveries" aria-hidden="true"></div>
                <img class="harbor-steamer" src="art/harbor-steamer.webp" alt="" draggable="false">
                ${[['warehouse','창고'],['market','시장'],['farm','농경지'],['quay','부두']].map(([site,name]) =>
                  `<button type="button" class="harbor-site site-${site}" data-harbor="${site}" aria-label="${name} 열기"><span>${name}</span></button>`).join('')}
              </div>
            </div>
            <div class="harbor-tools">
              <button type="button" data-harbor="world">세계 전체 보기</button>
              <button type="button" data-harbor="in" aria-label="항구 그림 확대">＋</button>
              <button type="button" data-harbor="out" aria-label="항구 그림 축소">−</button>
              <button type="button" data-harbor="labels" aria-pressed="false">장소 이름</button>
              <span>건물을 눌러 창고와 시장을 열어 보세요.</span>
            </div>
          </div>
          <button type="button" class="harbor-return" data-harbor="home">항구 전경 보기</button>
        <div class="world-map" role="group" aria-label="세계지도에서 나라 고르기">
          <canvas class="atlas-canvas" tabindex="0" aria-label="3D 지도. 화살표로 이동, 더하기와 빼기로 확대·축소, 0으로 세계 전체 보기"></canvas>
          <button type="button" class="atlas-inset" data-camera="reset" aria-label="작은 지도로 세계 전체 보기"><span>세계 전체</span></button>
          <span class="atlas-cargo-badge" aria-hidden="true" hidden></span>
          <span class="atlas-cargo-badge" aria-hidden="true" hidden></span>
          <span class="atlas-landmark" data-site="warehouse" aria-hidden="true" hidden></span>
          <span class="atlas-landmark" data-site="production" aria-hidden="true" hidden></span>
          <span class="atlas-landmark" data-site="harbor" aria-hidden="true" hidden></span>
          <span class="ocean-surface" aria-hidden="true"></span>
          <span class="map-compass" aria-hidden="true">북<span>✦</span></span>
          <span class="map-route" aria-hidden="true" hidden></span>
          <div class="delivery-layer" aria-hidden="true"></div>
          ${markers.map(([country, [x, y]]) => `
            <button type="button" class="country-marker ${country === S.country ? 'our-country' : ''}"
              style="--map-x:${x}%;--map-y:${y}%" data-act="map-select" data-country="${country}"
              aria-controls="world-country" aria-pressed="false">
              <span class="country-name">${country === S.country ? '<span aria-hidden="true">★</span><span class="sr-only">우리 나라 </span>' : ''}
              ${esc(gname(country))}</span>
            </button>`).join('')}
        </div>
          <div class="atlas-controls" role="group" aria-label="지도 카메라">
            <button type="button" data-camera="in" aria-label="지도 확대" title="지도 확대">+</button>
            <button type="button" data-camera="out" aria-label="지도 축소" title="지도 축소">−</button>
            <button type="button" data-camera="left" aria-label="왼쪽으로 돌리기" title="왼쪽으로 돌리기">↶</button>
            <button type="button" data-camera="right" aria-label="오른쪽으로 돌리기" title="오른쪽으로 돌리기">↷</button>
            <button type="button" data-camera="reset" aria-label="세계 전체 보기" title="세계 전체 보기">세계 전체</button>
            <button type="button" data-camera="town">마을 보기</button>
            <button type="button" data-camera="port">항구 보기</button>
            <button type="button" data-camera="warehouse">창고 확대</button>
            <button type="button" data-camera="berth">하역 확대</button>
            <button type="button" data-camera="scenic" aria-pressed="true">풍경만 보기</button>
            <output class="atlas-zoom" aria-label="지도 확대 배율" aria-live="off">1×</output>
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
const VEHICLE_ART = {
  ship: { file: 'harbor-steamer.webp', width: .86, unit: 3 },
  truck: { file: 'cargo-truck.webp', width: .56, unit: 4 },
  plane: { file: 'trade-plane.webp', width: .88, unit: 5 },
};

// The hand-painted map has a road junction, harbor and offshore way point per continent.
const CONTINENT_ROUTES = {
  west: { junction: [20, 45], harbor: [34, 53], offshore: [36, 54.1] },
  east: { junction: [74, 45], harbor: [72, 59], offshore: [71.5, 61.6] },
  south: { junction: [47, 82], harbor: [61.4, 91.6], offshore: [65.8, 94.5] },
};

// Ordered offshore waypoints keep both renderers on the same navigable channels.
const SEA_LANES = {
  west: { east: [[52.5,52.9], [68.7,61.6]],
    south: [[55.1,64.3], [63,65.5], [72,64], [75,71], [74,76], [73,87]] },
  east: { south: [[72,64], [75,71], [74,76], [73,87]] },
};

function seaLane(from, to, departure = CONTINENT_ROUTES[from].harbor, arrival = CONTINENT_ROUTES[to].harbor) {
  const turns = SEA_LANES[from]?.[to] || [...SEA_LANES[to][from]].reverse();
  return [departure, CONTINENT_ROUTES[from].offshore, ...turns, CONTINENT_ROUTES[to].offshore, arrival];
}

function shipmentStages(leg) {
  const start = MAP_POSITIONS[leg.seller];
  const end = MAP_POSITIONS[leg.buyer];
  const origin = CONTINENT_ROUTES[start[2]];
  const destination = CONTINENT_ROUTES[end[2]];
  if (origin === destination) {
    return [{ type: 'truck', points: [start, origin.junction, end], from: 0, to: 1 }];
  }
  if (leg.good === 'electronics') {
    return [{ type: 'plane', points: [start, [start[0] * .5 + end[0] * .5, (start[1] + end[1]) / 2 - 7], end], from: 0, to: 1 }];
  }
  return [
    { type: 'truck', points: [start, origin.junction, origin.harbor], from: 0, to: .23 },
    { type: 'ship', points: seaLane(start[2], end[2]), from: .23, to: .77 },
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
      <img src="art/${VEHICLE_ART[stage.type].file}" alt="" draggable="false">
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

  const layer = $('.delivery-layer');
  const routeKey = JSON.stringify([legs, departedAt]);
  if (layer.dataset.routeKey !== routeKey) {
    layer.dataset.routeKey = routeKey;
    const elapsed = departedAt ? performance.now() - departedAt : TRIP_MS;
    if (!tradeAtlas?.ready) drawShipments(layer, legs, elapsed);
  }

  const seaCargo = legs.filter((leg) => (leg.seller === S.country || leg.buyer === S.country) &&
    leg.good !== 'electronics' && MAP_POSITIONS[leg.seller][2] !== MAP_POSITIONS[leg.buyer][2]);
  showHarborCargo(seaCargo, departedAt);

  const cargo = $('#route-cargo');
  render(cargo, `<h3>교역로의 물건</h3>
    ${legs.length ? `<ul class="cargo-legs">${legs.map((leg) => `<li>${icon(leg.good)}<div>
      <strong>${esc(cargoName(leg))}</strong><small>${esc(gname(leg.seller))} → ${esc(gname(leg.buyer))} · ${MAP_POSITIONS[leg.seller][2] === MAP_POSITIONS[leg.buyer][2] ? '화물차' : leg.good === 'electronics' ? '비행기' : '화물차와 배'}</small></div>
    </li>`).join('')}</ul>
    ${tradeAtlas?.ready ? '<p id="shipment-stage" role="status">교역로 확인 중</p>' : ''}
    <div class="actions"><button type="button" data-act="replay-route" data-index="${displayedTrade}">운송 다시 보기</button>
    ${seaCargo.length ? '<button type="button" data-act="harbor-delivery">항구에서 짐 보기</button>' : ''}
    ${tradeAtlas?.ready ? '<button type="button" data-act="follow-shipment" aria-pressed="false">화물 따라가기</button>' : ''}</div>`
    : '<p>거래가 성사되면 이곳에 보낸 물건과 교역로가 표시돼요.</p>'}
    ${S.transactions_this_round.length > 1 ? `<label>이번 라운드 교역로
      <select id="trade-route-choice" data-k="route-history"><option value="">교역로 고르기</option>
      ${S.transactions_this_round.map((t, i) => `<option value="${i}">${i + 1}. ${esc(t.legs.map(cargoName).join(' ↔ '))} · ${esc(gname(t.legs[0].seller))} → ${esc(gname(t.legs[0].buyer))}</option>`).join('')}
      </select></label>` : ''}`, drafts);
  const choice = $('#trade-route-choice');
  if (choice) choice.value = displayedTrade ?? '';
  tradeAtlas?.setRoute(country, legs, departedAt);
  tradeAtlas?.updateRouteStatus(performance.now());
}

function showHarborCargo(legs, departure) {
  const layer = $('.harbor-deliveries');
  if (!layer) return;
  const key = JSON.stringify([legs, departure]);
  if (layer.dataset.key === key) return;
  layer.dataset.key = key;
  const elapsed = performance.now() - departure;
  const active = legs.length && departure && elapsed < TRIP_MS;
  layer.replaceChildren();
  if (!active) return;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  for (const [i, leg] of legs.entries()) {
    const vessel = document.createElement('div');
    vessel.className = 'harbor-load';
    const ship = document.createElement('img');
    ship.src = 'art/harbor-steamer.webp';
    ship.alt = '';
    const tag = document.createElement('span');
    tag.textContent = cargoName(leg);
    vessel.append(ship, tag);
    layer.append(vessel);
    const dock = { left: (32 + i*11) + '%', top: (76 + i*6) + '%' };
    const sea = { left: '-17%', top: '69%' };
    const arriving = leg.buyer === S.country;
    if (!arriving) ship.style.transform = 'scaleX(-1)';
    Object.assign(vessel.style, dock);
    if (!reduced) {
      const frames = arriving ? [sea, { ...dock, offset: .75 }, dock]
        : [dock, { ...dock, offset: .25 }, sea];
      vessel.animate(frames, { duration: TRIP_MS, delay: -elapsed, fill: 'both' });
    }
    setTimeout(() => vessel.remove(), TRIP_MS - elapsed);
  }
}

function openTradeMap() {
  const frame = $('.atlas-frame');
  if (!frame?.classList.contains('showing-harbor')) return;
  frame.classList.remove('showing-harbor');
  frame.closest('#world').scrollIntoView({ block: 'start' });
  if (tradeAtlas?.ready) tradeAtlas.changeCamera('reset');
  else if (tradeAtlas) tradeAtlas.camera = { x: 0, z: 0, zoom: 1, yaw: 0 };
}

function bindHarbor(frame) {
  if (!frame || frame.dataset.harborBound) return;
  frame.dataset.harborBound = 'true';
  const view = $('.harbor-window', frame);
  const picture = $('.harbor-picture', frame);
  const pointers = new Map();
  let zoom = 1, x = 0, y = 0, dragged = false;
  const drawView = () => {
    const width = view.clientWidth, height = view.clientHeight;
    x = within(x, width * (1 - zoom), 0);
    y = within(y, height * (1 - zoom), 0);
    picture.style.transform = `translate(${x}px,${y}px) scale(${zoom})`;
  };
  // Reapply the current fractional pan if the student rotates the tablet.
  let previousWidth = 0;
  const resize = new ResizeObserver(() => {
    if (!view.isConnected) { resize.disconnect(); return; }
    if (!view.clientWidth) return;
    if (previousWidth) {
      x *= view.clientWidth / previousWidth;
      y *= view.clientWidth / previousWidth;
    }
    previousWidth = view.clientWidth;
    drawView();
  });
  resize.observe(view);
  const setZoom = (next, cx = view.clientWidth / 2, cy = view.clientHeight / 2) => {
    next = within(next, 1, 4);
    x = cx - (cx - x) * next / zoom;
    y = cy - (cy - y) * next / zoom;
    zoom = next;
    drawView();
  };
  view.addEventListener('keydown', (event) => {
    if (event.target !== view) return;
    const arrows = { ArrowRight: [-48,0], ArrowLeft: [48,0], ArrowUp: [0,48], ArrowDown: [0,-48] };
    if (arrows[event.key]) {
      event.preventDefault();
      x += arrows[event.key][0];
      y += arrows[event.key][1];
      drawView();
    }
    if (['+','=','-','0'].includes(event.key)) {
      event.preventDefault();
      setZoom(event.key === '0' ? 1 : zoom * (event.key === '-' ? 1/1.5 : 1.5));
    }
  });
  view.addEventListener('wheel', (event) => {
    event.preventDefault();
    const rect = view.getBoundingClientRect();
    setZoom(zoom * Math.exp(-event.deltaY * .002), event.clientX - rect.left, event.clientY - rect.top);
  }, { passive: false });
  view.addEventListener('pointerdown', (event) => {
    if (event.button !== 0) return;
    if (!pointers.size) dragged = false;
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    event.target.setPointerCapture(event.pointerId);
  });
  view.addEventListener('pointermove', (event) => {
    const old = pointers.get(event.pointerId);
    if (!old) return;
    const dx = event.clientX - old.x, dy = event.clientY - old.y;
    if (!dragged && pointers.size === 1 && Math.hypot(dx, dy) < 5) return;
    dragged = true;
    const other = [...pointers.entries()].find(([id]) => id !== event.pointerId)?.[1];
    if (other) {
      const before = Math.hypot(old.x - other.x, old.y - other.y);
      const after = Math.hypot(event.clientX - other.x, event.clientY - other.y);
      const rect = view.getBoundingClientRect();
      if (before > 2) setZoom(zoom * after / before, (old.x + other.x)/2 - rect.left, (old.y + other.y)/2 - rect.top);
      x += dx/2; y += dy/2;
    } else { x += dx; y += dy; }
    old.x = event.clientX; old.y = event.clientY;
    drawView();
  });
  for (const type of ['pointerup','pointercancel','lostpointercapture']) {
    view.addEventListener(type, (event) => pointers.delete(event.pointerId));
  }
  frame.addEventListener('click', (event) => {
    const control = event.target.closest('[data-harbor]');
    if (!control || (dragged && view.contains(control) && event.detail)) return;
    const action = control.dataset.harbor;
    if (action === 'home') {
      if (tradeAtlas) tradeAtlas.following = false;
      tradeAtlas?.updateFollowControl();
      frame.classList.add('showing-harbor');
      setZoom(1);
      $('.harbor-tools button', frame).focus({ preventScroll: true });
    } else if (action === 'world' || action === 'quay') {
      openTradeMap();
      $('.country-marker.our-country', frame)?.focus({ preventScroll: true });
    } else if (action === 'in' || action === 'out') {
      setZoom(zoom * (action === 'in' ? 1.5 : 1/1.5));
    } else if (action === 'labels') {
      control.setAttribute('aria-pressed', String(view.classList.toggle('show-names')));
    } else {
      const destination = action === 'farm' ? (S.phase === 'invest' ? 'industry' : 'settlement')
        : action === 'market' && S.phase === 'invest' ? null : action;
      if (!destination) { openTradeMap(); return; }
      const heading = document.querySelector(`#${destination} h2`);
      if (heading) {
        heading.tabIndex = -1;
        heading.focus({ preventScroll: true });
        heading.closest('section').scrollIntoView({ block: 'start' });
      }
    }
  });
}

function playRoute(index) {
  if (!S.transactions_this_round[index]) return;
  openTradeMap();
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
  bindHarbor($('.atlas-frame'));
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
        if ($('.atlas-frame.showing-harbor') && $('[data-act="harbor-delivery"]')) {
          departedAt = performance.now();
          drawMapRoute(mapCountry || S.country);
        } else playRoute(S.transactions_this_round.length - 1);
      }
    }
  }
}

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-act]');
  if (!el) return;
  e.preventDefault();
  if (el.dataset.act === 'harbor-delivery') {
    $('.harbor-return')?.click();
    departedAt = performance.now();
    drawMapRoute(mapCountry || S.country);
    $('#world').scrollIntoView({ block: 'start' });
    return;
  }
  if (el.dataset.act === 'follow-shipment') {
    if (tradeAtlas?.ready && displayedTrade !== null) {
      openTradeMap();
      tradeAtlas.following = !tradeAtlas.following;
      tradeAtlas.scenic = false;
      if (tradeAtlas.following) {
        $('#world').scrollIntoView({ block: 'start' });
        playRoute(displayedTrade);
      }
      tradeAtlas.updateFollowControl();
    }
    return;
  }
  if (el.dataset.act === 'replay-route') {
    $('#world').scrollIntoView({ block: 'start' });
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

const CONTINENTAL_ZOOM = 2.4;
const ATLAS_VERTEX = `#version 300 es
  layout(location = 0) in vec3 position;
  layout(location = 1) in vec3 color;
  layout(location = 2) in vec2 materialUV;
  out vec2 uv;
  uniform mat4 camera;
  out vec3 p;
  out vec3 rgb;
  void main() {
    uv = materialUV;
    p = position;
    rgb = color;
    gl_Position = camera * vec4(position, 1.);
  }`;

const ATLAS_FRAGMENT = `#version 300 es
  precision highp float;
  uniform highp sampler2DShadow shadows;
  float light(vec3 position) {
    vec3 uv = vec3((position.xz - position.y * vec2(.70,.50)) / vec2(20.,14.) + .5, .5-position.y*.20-.002);
    return .64 + .36 * texture(shadows, uv);
  }
  uniform sampler2D materials;
  uniform sampler2D regionalPainting;
  uniform sampler2D continentalRelief;
  uniform sampler2D vehicleSprite;
  uniform float zoom;
  in vec2 uv;
  uniform int layer;
  uniform float time;
  in vec3 p;
  in vec3 rgb;
  out vec4 pixel;
  float noise(vec2 v) {
    vec2 i = floor(v), f = fract(v);
    f *= f * (3. - 2. * f);
    vec4 h = fract(sin(mod(dot(i, vec2(17.13, 43.71)) + vec4(0.,17.13,43.71,60.84), 6.28318)) * 1273.43);
    return mix(mix(h.x,h.y,f.x), mix(h.z,h.w,f.x), f.y);
  }
  void main() {
    if (layer == 3) {
      pixel = texture(vehicleSprite, uv);
      if (pixel.a < .08) discard;
      return;
    }
    if (layer == 2) {
      vec3 albedo = uv.x < 0. ? rgb : rgb * texture(materials, uv).rgb;
      pixel = vec4(albedo * light(p), 1.);
      return;
    }
    // The painting follows world coordinates through rotation, zoom and every terrain triangle.
    vec2 mapUV = p.xz / vec2(18., 12.) + .5;
    float margin = min(min(mapUV.x, mapUV.y), min(1.-mapUV.x, 1.-mapUV.y));
    vec2 waveUV = .00034 * vec2(sin(p.z*12.+time), cos(p.x*13.-time*.7));
    vec2 sampleUV = mapUV + (rgb.r < 0. ? waveUV : vec2(0.));
    vec3 paint = texture(continentalRelief, sampleUV).rgb;
    // Regional artwork contains individual roofs and ships. Reveal it only after zooming in.
    float regional = smoothstep(${CONTINENTAL_ZOOM}, 5.4, zoom);
    if (regional > 0.) paint = mix(paint, texture(regionalPainting, sampleUV).rgb, regional);
    float ink = smoothstep(-.005,.016,margin) * (1.-smoothstep(3.5,11.,zoom));
    float grain = noise(p.xz * 4.) * .7 + noise(p.xz * 23.) * .3;
    if (layer == 1 && rgb.r > 0.) {
      vec3 n = normalize(cross(dFdx(p), dFdy(p)));
      float sunlight = abs(dot(n, normalize(vec3(-.46, 1., -.37))));
      vec3 grass = mix(vec3(.32,.46,.21), vec3(.69,.72,.37), grain);
      vec3 rock = mix(vec3(.42,.45,.40), vec3(.76,.73,.59), grain);
      vec3 ground = mix(grass, rock, smoothstep(.28,.68,p.y) * (1. - abs(n.y)*.56));
      ground = mix(ground, vec3(.88,.89,.79), smoothstep(.73,.94,p.y));
      ground = mix(vec3(.84,.75,.51), ground, smoothstep(.008,.14,rgb.r));
      pixel = vec4(mix(ground * (.73 + sunlight*.36) * light(p), paint * (.95 + .065*sunlight), ink), 1.);
    } else {
      float depth = layer == 1 ? -rgb.r : 1.;
      vec3 sea = mix(vec3(.21,.65,.59),vec3(.055,.32,.43), smoothstep(0.,.65,depth));
      float swell = sin(p.z*19. + sin(p.x*7.-time*.8));
      float wave = sin(p.z*111.+p.x*15.+grain*7.+time*2.1) * .65 + .35*swell;
      float surf = (1. - smoothstep(.01,.15,depth)) * smoothstep(-.65,.7,sin(depth*132.-time*2.2+grain));
      vec3 coast = mix(sea, vec3(.87,.91,.77), surf*.74);
      pixel = vec4(mix(coast, paint, ink) + vec3(.04,.07,.06)*smoothstep(.49,.93,wave)*grain,1.);
    }
  }`;

function atlasProgram(gl, vertex = ATLAS_VERTEX, fragment = ATLAS_FRAGMENT) {
  const program = gl.createProgram();
  const shaders = [[gl.VERTEX_SHADER, vertex], [gl.FRAGMENT_SHADER, fragment]].map(([type, source]) => {
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
    if (!distance) return -.85;
    const [r, g, b] = art.subarray(i * 4, i * 4 + 3);
    const snow = Math.max(0, (Math.min(r, g, b) - 80) / 145);
    const ridges = Math.sin(i % TERRAIN_WIDTH * .47) * Math.sin(Math.floor(i / TERRAIN_WIDTH) * .37);
    const inland = Math.min(1, distance / 10);
    return .05 + inland * (.13 + snow ** 1.65 * .93 + ridges * .06);
  });
  // Taper the outermost terrain cells into the surrounding sea.
  for (let i = 0; i < elevation.length; i++) {
    const x = i % TERRAIN_WIDTH, z = Math.floor(i / TERRAIN_WIDTH);
    const edge = Math.min(x, TERRAIN_WIDTH-1-x, z, TERRAIN_DEPTH-1-z);
    elevation[i] = Math.min(elevation[i], (edge-3)*.22);
  }
  const raw = elevation.slice();
  for (const country of Object.values(MAP_POSITIONS)) {
    const centerX = country[0] / 100 * (TERRAIN_WIDTH - 1);
    const centerZ = country[1] / 100 * (TERRAIN_DEPTH - 1);
    const index = Math.round(centerZ) * TERRAIN_WIDTH + Math.round(centerX);
    const level = within(raw[index], .11, .5);
    for (let z = Math.max(0, Math.floor(centerZ - 9)); z <= Math.min(TERRAIN_DEPTH - 1, Math.ceil(centerZ + 9)); z++) {
      for (let x = Math.max(0, Math.floor(centerX - 9)); x <= Math.min(TERRAIN_WIDTH - 1, Math.ceil(centerX + 9)); x++) {
        const i = z * TERRAIN_WIDTH + x;
        if (raw[i] <= 0) continue;
        const blend = within((9 - Math.hypot(x - centerX, z - centerZ)) / 4, 0, 1);
        elevation[i] = raw[i] + (level - raw[i]) * blend;
      }
    }
  }
  // Give each settlement a continuous terrace large enough for streets and fields.
  for (const location of Object.values(MAP_POSITIONS)) {
    const [cx, cz] = mapXZ(location);
    const level = Math.max(.15, elevation[Math.round(location[1] * .01 * (TERRAIN_DEPTH-1)) * TERRAIN_WIDTH
      + Math.round(location[0] * .01 * (TERRAIN_WIDTH-1))]);
    for (let i = 0; i < elevation.length; i++) {
      const x = (i % TERRAIN_WIDTH / (TERRAIN_WIDTH-1) - .5) * MAP_WIDTH - cx;
      const z = (Math.floor(i / TERRAIN_WIDTH) / (TERRAIN_DEPTH-1) - .5) * MAP_DEPTH - cz;
      const edge = 1.54 - Math.hypot(x,z) + .09*Math.sin(7*x+2*z);
      elevation[i] = Math.max(elevation[i], Math.min(level, edge*.75));
    }
  }
  // Cut navigable water alongside each quay, including where a town meets the dock.
  for (const region of Object.keys(CONTINENT_ROUTES)) {
    const dock = dockLayout(region);
    const [dx,dz] = dock.point(0);
    for (let i=0; i<elevation.length; i++) {
      const x=(i%TERRAIN_WIDTH/(TERRAIN_WIDTH-1)-.5)*MAP_WIDTH-dx;
      const z=(Math.floor(i/TERRAIN_WIDTH)/(TERRAIN_DEPTH-1)-.5)*MAP_DEPTH-dz;
      const forward=x*Math.cos(dock.yaw)+z*Math.sin(dock.yaw);
      const side=z*Math.cos(dock.yaw)-x*Math.sin(dock.yaw);
      const terrace = Math.min(-forward+.10, 1.23-Math.abs(side), forward+1.22);
      if (terrace > 0) elevation[i] = Math.min(.18, Math.max(elevation[i], terrace*.8));
      const inlet=Math.min(forward-.01, 1.43-Math.abs(side), 1.95-forward);
      elevation[i]=Math.min(elevation[i], .06-inlet*.96);
    }
  }
  const vertices = [];
  const indices = [];
  for (let v = 0; v < TERRAIN_DEPTH; v++) {
    for (let u = 0; u < TERRAIN_WIDTH; u++) {
      const i = v * TERRAIN_WIDTH + u;
      vertices.push((u / (TERRAIN_WIDTH - 1) - .5) * MAP_WIDTH, Math.max(-.045, elevation[i]),
        (v / (TERRAIN_DEPTH - 1) - .5) * MAP_DEPTH, elevation[i], 0, 0, -1, -1);
      if (u && v) indices.push(i, i - 1, i - TERRAIN_WIDTH, i - 1, i - TERRAIN_WIDTH - 1, i - TERRAIN_WIDTH);
    }
  }
  return { vertices, indices, elevation };
}

const shade = (c, scale) => c.map((value) => value * scale);
function triangle(output, a, b, c, color) {
  for (const point of [a, b, c]) output.push(...point, ...color, -1, -1);
}
function quad(output, a, b, c, d, color) {
  triangle(output, a, b, c, color);
  triangle(output, a, c, d, color);
}

// The four quadrants contain brick frontage, plaster frontage, slate and boards.
function materialFace(output, a, b, c, d, material, tint) {
  const x = ((material % 2) + 2 * Math.floor(material / 4)) * .25;
  const y = (Math.floor(material / 2) % 2) * .5;
  const left = x + .002, right = x + .248, top = y + .002, bottom = y + .498;
  for (const [point, u, v] of [
    [a, left, bottom], [b, right, bottom], [c, right, top],
    [a, left, bottom], [c, right, top], [d, left, top],
  ]) output.push(...point, ...tint, u, v);
}

function piece(output, x, y, z, width, height, depth, color, yaw = 0, material = null) {
  const cos = Math.cos(yaw);
  const sin = Math.sin(yaw);
  const p = (u, h, v) => [x + u * cos - v * sin, y + h, z + u * sin + v * cos];
  const w = width / 2, d = depth / 2;
  const a = p(-w, 0, -d), b = p(w, 0, -d), c = p(w, 0, d), e = p(-w, 0, d);
  const f = p(-w, height, -d), g = p(w, height, -d), h = p(w, height, d), j = p(-w, height, d);
  if (material !== null) {
    materialFace(output, f, g, h, j, material, color);
    for (const [lowerA, lowerB, upperB, upperA, light] of [
      [a,b,g,f,.91], [b,c,h,g,.98], [c,e,j,h,.85], [e,a,f,j,1],
    ]) materialFace(output, lowerA, lowerB, upperB, upperA, material, shade(color, light));
    return;
  }
  quad(output, f, j, h, g, color);
  quad(output, a, b, g, f, shade(color, .74));
  quad(output, b, c, h, g, shade(color, .87));
  quad(output, c, e, j, h, shade(color, .63));
  quad(output, e, a, f, j, shade(color, .95));
}

function modelVehicle(output, type, x, y, z, yaw) {
  const scale = type === 'truck' ? .52 : 1;
  const at = (forward, up, side, w, h, d, color) => piece(output,
    x + scale*(forward*Math.cos(yaw) - side*Math.sin(yaw)), y + scale*up,
    z + scale*(forward*Math.sin(yaw) + side*Math.cos(yaw)), w*scale, h*scale, d*scale, color, yaw);
  const gold = [.97, .68, .29], pale = [.95, .9, .72], navy = [.14, .23, .3];
  if (type === 'truck') {
    at(0, .048, 0, .35, .065, .16, navy);
    at(.096, .1, 0, .144, .115, .158, [.92, .42, .12]);
    at(.133, .155, 0, .04, .048, .161, [.55, .78, .81]);
    at(-.092, .112, 0, .146, .083, .143, gold);
    for (const forward of [-.114, .105]) for (const side of [-.081, .081]) at(forward, .016, side, .075, .075, .043, navy);
  } else if (type === 'ship') {
    const hullPoint = (u,h,v) => [x+u*Math.cos(yaw)-v*Math.sin(yaw), y+h, z+u*Math.sin(yaw)+v*Math.cos(yaw)];
    const rail = [[-.26,-.067],[-.18,-.105],[.14,-.101],[.32,0],[.14,.101],[-.18,.105],[-.26,.067]];
    for (let i=0;i<rail.length;i++) {
      const [a,b]=rail[i], [c,d]=rail[(i+1)%rail.length];
      quad(output,hullPoint(a*.9,.003,b*.76),hullPoint(c*.9,.003,d*.76),hullPoint(c,.10,d),hullPoint(a,.10,b),shade(navy,.77+i*.04));
      triangle(output,hullPoint(a,.10,b),hullPoint(c,.10,d),hullPoint(0,.10,0),[.72,.55,.32]);
    }
    at(.12,.11,0,.012,.26,.014,[.43,.33,.23]);
    triangle(output,hullPoint(.12,.368,0),hullPoint(.12,.318,0),hullPoint(.024,.345,.014),[.9,.44,.20]);
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

function mooredVessel(mesh, x, z, yaw) {
  const pt = (u, h, v) => [x+u*Math.cos(yaw)-v*Math.sin(yaw),h,z+u*Math.sin(yaw)+v*Math.cos(yaw)];
  const stations = [[-.43,.067],[-.33,.115],[-.18,.131],[.13,.128],[.28,.10],[.46,.008]];
  for (let i=1; i<stations.length; i++) {
    const [a,wa]=stations[i-1], [b,wb]=stations[i];
    materialFace(mesh,pt(a,.122,-wa),pt(b,.122,-wb),pt(b,.122,wb),pt(a,.122,wa),3,[1.08,1.02,.87]);
    for (const side of [-1,1]) {
      const hull = (u,h,w) => pt(u,h,w*side);
      materialFace(mesh,hull(a,-.02,wa*.57),hull(b,-.02,wb*.57),hull(b,.127,wb),hull(a,.127,wa),3,[.45,.44,.39]);
      quad(mesh,hull(a,.094,wa*.94),hull(b,.094,wb*.94),hull(b,.103,wb*.98),hull(a,.103,wa*.98),[.85,.68,.41]);
    }
  }
  const rope = (a,b) => quad(mesh,a,[a[0]+.002,a[1],a[2]+.002],[b[0]+.002,b[1],b[2]+.002],b,[.28,.24,.19]);
  for (const u of [-.19,.145]) {
    const [mx,,mz] = pt(u,0,0);
    piece(mesh,mx,.122,mz,.012,.48,.012,[.48,.32,.19],yaw);
    for (const height of [.33,.46]) {
      const span = height>.4 ? .126 : .16;
      piece(mesh,mx,height,mz,.012,.011,span*2,[.43,.30,.20],yaw);
      // Furled canvas drapes from each yard in uneven folds.
      for (let panel=0;panel<6;panel++) {
        const a = (panel/3-1)*span, b = ((panel+1)/3-1)*span;
        quad(mesh,pt(u+.01,height,a),pt(u+.01,height,b),pt(u+.022,height-.032+(panel%2)*.008,b),
          pt(u+.023,height-.031-((panel+1)%2)*.008,a),shade([.87,.81,.65],.88+(panel%3)*.05));
      }
    }
    for (const side of [-1,1]) for (const offset of [-.09,.06]) rope(pt(u,.565,0),pt(u+offset,.127,side*.115));
  }
  const linen = [.88,.82,.65];
  const head = pt(.151,.53,0), tack = pt(.393,.164,0), clew = pt(.197,.192,.027);
  const belly = pt(.245,.274,.044);
  triangle(mesh,head,belly,clew,shade(linen,.90));
  triangle(mesh,head,tack,belly,linen);
  triangle(mesh,belly,tack,clew,shade(linen,.96));
  rope(pt(-.40,.13,0),pt(-.19,.595,0)); rope(pt(-.19,.595,0),pt(.145,.595,0));
  rope(pt(.145,.595,0),pt(.45,.13,0));
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

// Local scenery is modelled in world coordinates. The miniature town uses the
// same warehouse gates and docks as the route animation.
const TOWN_PRODUCTION = {
  Mineria: '광산', Grainia: '밀 농장', Tropia: '바나나 농장', Oilia: '연료 작업장',
  Technia: '전자제품 공장', Mechania: '기계 공장', Novia: '공장',
  Agrea: '농장', Ferria: '광산',
};
const FARM_TOWNS = new Set(['Grainia', 'Tropia', 'Agrea']);
const NEAR_ZOOM = 5.6;
const MIN_ATLAS_ZOOM = .8;
const MAX_ATLAS_ZOOM = 36;
const ATLAS_DETAIL_ZOOM = 24;
const LOCAL_VIEWS = new Set(['town', 'port', 'warehouse', 'berth']);
const ATLAS_TRIP_MS = 10400;

function dockLayout(continent) {
  const { harbor, offshore } = CONTINENT_ROUTES[continent];
  const [[x, z], [hx, hz]] = [mapXZ(harbor), mapXZ(offshore)];
  const yaw = Math.atan2(hz - z, hx - x);
  const c = Math.cos(yaw), s = Math.sin(yaw);
  const point = (forward, side = 0) => [x + forward * c - side * s, z + forward * s + side * c];
  const mapPoint = (forward, side) => worldUV(...point(forward, side)).map((v) => v * 100);
  return { harbor, offshore, yaw, point, apron: mapPoint(-.08, -.04), berth: mapPoint(.57, .26) };
}

function settlementLayout(country) {
  const [x, z, area] = MAP_POSITIONS[country];
  const [cx, cz] = mapXZ([x, z]);
  const [hx, hz] = mapXZ(CONTINENT_ROUTES[area].harbor);
  const distance = Math.hypot(cx - hx, cz - hz);
  const offset = Math.max(0, 1.6 - distance) / Math.max(.01, distance);
  const wx = cx + (cx - hx) * offset, wz = cz + (cz - hz) * offset;
  const [jx, jz] = mapXZ(CONTINENT_ROUTES[area].junction);
  const yaw = Math.atan2(jz - wz, jx - wx);
  const c = Math.cos(yaw), s = Math.sin(yaw);
  const point = (forward, side = 0) => [wx + forward * c - side * s, wz + forward * s + side * c];
  const gate = worldUV(...point(-.23, .05)).map((v) => v * 100);
  return { yaw, point, gate, area };
}

function gable(build, x, y, z, w, d, rise, color, yaw, slate = false) {
  const c = Math.cos(yaw), s = Math.sin(yaw);
  const q = (a, h, b) => [x + a * c - b * s, y + h, z + a * s + b * c];
  const a = q(-w / 2, 0, -d / 2), b = q(w / 2, 0, -d / 2);
  const f = q(-w / 2, rise, 0), g = q(w / 2, rise, 0);
  const e = q(-w / 2, 0, d / 2), h = q(w / 2, 0, d / 2);
  if (slate) {
    materialFace(build, a, b, g, f, 2, shade(color, .88));
    materialFace(build, h, e, f, g, 2, color);
  } else {
    quad(build, a, f, g, b, shade(color, .88));
    quad(build, f, e, h, g, color);
  }
  triangle(build, a, e, f, shade(color, .68));
  triangle(build, b, g, h, shade(color, .77));
}

function atlasBuilding(build, x, y, z, w, h, d, wall, roof, yaw, warehouse = false) {
  piece(build, x, y - .02, z, w * 1.07, .055, d * 1.07, [.34, .31, .23], yaw);
  const tint = wall.map((value) => .74 + value * .32);
  const roofTint = roof.map((value) => .67 + value * .83);
  piece(build, x, y + .02, z, w, h, d, tint, yaw, warehouse ? 0 : 1);
  gable(build, x, y + h + .02, z, w * 1.09, d * 1.11, d * .39, roofTint, yaw, true);
  const detail = (u, v, dy, width, height, depth, color) => piece(build,
    x + u * Math.cos(yaw) - v * Math.sin(yaw), y + dy, z + u * Math.sin(yaw) + v * Math.cos(yaw),
    width, height, depth, color, yaw);
  detail(w*.31, -d*.18, h+.025, .025, d*.58, .029, [.55,.36,.28]);
  detail(w*.31, -d*.18, h+.024+d*.58, .034, .012, .037, [.32,.30,.26]);
  // Dormers break the roof line and cast real shadows onto the slate.
  for (const u of (warehouse ? [-.26, .26] : [0])) {
    const v = d * .28, dw = w * (warehouse ? .19 : .24);
    const [dx, dz] = [x + u*w*Math.cos(yaw)-v*Math.sin(yaw), z + u*w*Math.sin(yaw)+v*Math.cos(yaw)];
    const base = y + h + .02 + d*.12;
    piece(build, dx, base, dz, dw, d*.18, d*.27, [.72,.65,.52], yaw);
    detail(u*w, v+d*.138, base-y+.004, dw*.60, d*.13, .004, [.18,.22,.21]);
    gable(build, dx, base+d*.18, dz, dw*1.16, d*.31, dw*.31, [.32,.33,.30], yaw);
  }
}

function atlasTree(build, x, y, z, scale, salt) {
  piece(build, x, y, z, .035 * scale, .16 * scale, .035 * scale, [.36, .24, .14]);
  const hues = [[.29,.47,.21],[.41,.54,.22],[.21,.43,.29],[.52,.58,.25]];
  const color = hues[salt%4];
  const rings = [[.105,.058],[.18,.123],[.26,.114],[.327,.069],[.36,.012]];
  const crowns = rings.map(([h,r],row)=>Array.from({length:7},(_,i)=>{
    const angle=i*Math.PI*2/7 + salt*.53 + (row%2)*.24;
    const radius=r*scale*(1+.1*Math.sin(i*7+salt));
    return [x+Math.cos(angle)*radius,y+h*scale,z+Math.sin(angle)*radius];
  }));
  for (let row=1;row<crowns.length;row++) for(let i=0;i<7;i++) {
    const next=(i+1)%7;
    const tint=.73+row*.068+.09*Math.cos(i*.90+salt*.53);
    materialFace(build,crowns[row-1][i],crowns[row-1][next],crowns[row][next],crowns[row][i],6,shade(color.map((c)=>.71+c),tint));
  }
}

function bananaPlant(mesh, x, y, z, seed) {
  const stem = [.51, .49, .22];
  piece(mesh, x, y, z, .025, .17, .023, stem);
  for (let i = 0; i < 7; i++) {
    const angle = i * 2.4 + seed;
    const dx = Math.cos(angle), dz = Math.sin(angle);
    const tip = [x + dx * .108, y + .15 + (i % 3) * .012, z + dz * .108];
    const ridge = [x + dx * .057, y + .208, z + dz * .057];
    const base = [x, y + .164, z];
    for (const side of [-1, 1]) {
      const edge = [ridge[0] - dz * side * .024, ridge[1] - .019, ridge[2] + dx * side * .024];
      quad(mesh, base, ridge, tip, edge, side > 0 ? [.30, .53, .23] : [.40, .61, .25]);
    }
  }
  piece(mesh, x + .021, y + .10, z, .029, .041, .025, [.89, .71, .23]);
}

function millSails(mesh, mill, time) {
  const { x, y, z, yaw } = mill;
  const point = (right, up) => [x + right * Math.cos(yaw), y + up, z + right * Math.sin(yaw)];
  for (let i = 0; i < 4; i++) {
    const angle = time * .57 + i * Math.PI / 2 + .42;
    const arm = (r, w) => point(r * Math.cos(angle) - w * Math.sin(angle), r * Math.sin(angle) + w * Math.cos(angle));
    quad(mesh, arm(0, -.006), arm(.20, -.006), arm(.20, .006), arm(0, .006), [.42, .32, .20]);
    quad(mesh, arm(.075, .006), arm(.198, .006), arm(.18, .042), arm(.078, .036), [.94, .86, .63]);
  }
}

function atlasCrate(build, x, y, z, yaw, size = .093) {
  piece(build, x, y, z, size, size * .84, size, [1.12, 1.04, .88], yaw, 3);
  piece(build, x, y + size * .83, z, size * 1.05, size * .105, size * 1.04, [.98, .76, .42], yaw);
}

function addSettlement(build, country, surface, treeSeed) {
  const { yaw, point, area } = settlementLayout(country);
  const dock = dockLayout(area);
  const [ox, oz] = dock.point(0);
  const onQuay = (x, z) => {
    const dx = x - ox, dz = z - oz;
    const forward = dx*Math.cos(dock.yaw) + dz*Math.sin(dock.yaw);
    const side = dz*Math.cos(dock.yaw) - dx*Math.sin(dock.yaw);
    return forward > -.53 && forward < .96 && Math.abs(side) < 1.24;
  };
  const wall = [.82, .71, .53], tile = [.53, .19, .11], wood = [.66, .47, .29];
  const place = (u, v, size, colors, warehouse = false) => {
    const [x, z] = point(u, v);
    const y = surface(x, z);
    if (y >= -.015 && (warehouse || !onQuay(x,z))) atlasBuilding(build, x, y, z, ...size, ...colors, yaw, warehouse);
  };
  place(-.24, -.17, [.38, .2, .26], [wall, tile], true);
  for (const [u, v, w, h, color] of [
    [-.5, .17, .18, .145, tile], [-.26,.25,.17,.155,[.4,.23,.15]], [-.02,.29,.19,.14,tile],
    [.25,.32,.21,.19,[.26,.38,.4]], [.48,.26,.19,.145,tile], [.54,-.18,.18,.14,[.37,.44,.35]],
  ]) place(u, v, [w, h, .146], [wall, color]);

  for (const [u, v] of [[-.08,-.16], [.025,-.19], [.018,-.28], [-.085,-.28]]) {
    const [x, z] = point(u, v);
    const y = surface(x, z);
    if (y >= 0) atlasCrate(build, x, y + .028, z, yaw, .083);
  }

  if (FARM_TOWNS.has(country)) {
    const [fx, fz] = point(.34, -.42);
    if (surface(fx, fz) > 0) {
      for (let row = 0; row < 7; row++) {
        const [x, z] = point(.38, -.66 + row * .056);
        const y = surface(x, z);
        piece(build, x, y + .005, z, .47, .02, .042, row % 2 ? [.66, .44, .15] : [.39, .28, .11], yaw);
        for (let plot = 0; plot < 6; plot++) {
          const [px, pz] = point(.18 + plot * .075, -.66 + row * .056);
          const height = .033 + ((plot + row) % 3) * .012;
          if (country === 'Tropia' && row % 2 === 0 && plot % 2 === 0) {
            bananaPlant(build, px, surface(px, pz) + .018, pz, plot + row);
          } else if (country !== 'Tropia') piece(build, px, surface(px, pz) + .02, pz, .036, height, .028, [.8, .68, .22], yaw);
        }
      }
    }
  } else {
    place(.35, -.42, [.36, .23, .25], [[.66,.51,.37], [.33,.24,.19]]);
    for (const [u, v] of [[.39,-.49],[.52,-.46]]) {
      const [x, z] = point(u, v);
      const y = surface(x, z);
      if (y < 0) continue;
      piece(build, x, y, z, .059, .41, .065, [.56, .34, .26], yaw);
      piece(build, x, y + .39, z, .089, .036, .09, [.27, .27, .25], yaw);
    }
  }

  // Perimeter streets enclose small residential blocks around the market square.
  const slate = [.26,.39,.42];
  const street = (u,v,w,d) => {
    const [x,z] = point(u,v);
    if (!onQuay(x,z)) piece(build,x,surface(x,z)+.006,z,w,.019,d,[1.12,1.07,.96],yaw,4);
  };
  street(0,.53,1.86,.083);
  street(-.72,0,.087,1.16);
  street(.72,0,.087,1.16);
  street(0,-.76,1.55,.083);
  street(-.45,-.52,.49,.40);
  for (let block=0; block<7; block++) {
    const u = -.86+block*.28;
    for (const v of [.71,.94]) {
      const roof = [tile,slate,[.63,.31,.16]][(block+treeSeed+(v>.8?1:0))%3];
      place(u,v,[.195,.14+(block%3)*.023,.16],[[.89,.80,.62],roof]);
    }
  }
  // Canvas awnings and trestles face the cobbled square.
  for (let i=0;i<3;i++) {
    const [x,z] = point(-.61+i*.15,-.53);
    const y=surface(x,z);
    piece(build,x,y+.023,z,.119,.088,.078,wood,yaw);
    for (let band=0;band<5;band++) {
      const [bx,bz]=point(-.665+i*.15+band*.027,-.53);
      gable(build,bx,y+.13,bz,.028,.13,.03,band%2 ? [.95,.85,.64] : [.68,.24,.14],yaw);
    }
  }
  const [tx,tz]=point(-.52,-.91);
  const ty=surface(tx,tz);
  atlasBuilding(build,tx,ty,tz,.31,.25,.21,wall,slate,yaw);
  piece(build,tx,ty+.23,tz,.15,.25,.15,[.85,.76,.55],yaw);
  const cap = [tx,ty+.70,tz];
  const corners = [[-.10,-.10],[.10,-.10],[.10,.10],[-.10,.10]].map(([a,b])=>{
    const [x,z]=point(-.52+a,-.91+b);
    return [x,ty+.48,z];
  });
  corners.forEach((a,i)=>triangle(build,a,corners[(i+1)%4],cap,shade(slate,.8+i*.1)));
  for (let i=0;i<4;i++) {
    const [x,z]=point(.96,-.66+i*.32);
    piece(build,x,surface(x,z)+.012,z,.31,.016,.29,[.50,.42,.20],yaw);
    for (let row=0;row<8;row++) {
      const [fx,fz]=point(.96,-.78+i*.32+row*.034);
      piece(build,fx,surface(fx,fz)+.031,fz,.292,.025,.023,
        i%2 ? [.69,.69,.26] : [.40,.56,.23],yaw);
    }
  }
  for (let i = 0; i < 18; i++) {
    const angle = i * 2.399 + treeSeed;
    if (Math.sin(angle) > .40) continue; // Keep the residential streets clear.
    const [x, z] = point(Math.cos(angle) * (.68 + i % 4 * .075), Math.sin(angle) * (.62 + i % 3 * .068));
    const y = surface(x, z);
    if (y > .04 && !onQuay(x,z)) atlasTree(build, x, y, z, .8 + (i % 5) * .13, i + treeSeed);
  }

  const [x, z] = point(.11, .14);
  const plaza = surface(x, z);
  if (plaza > 0) piece(build, x, plaza + .006, z, .22, .018, .16, wood, yaw);
}

function addHarbor(build, continent, surface) {
  const { point, yaw } = dockLayout(continent);
  const at = (forward, side, y, w, h, d, color, material = null) => {
    const [x, z] = point(forward, side);
    piece(build, x, y, z, w, h, d, color, yaw, material);
  };
  const timber = [.4, .28, .16], iron = [.29, .37, .37];
  at(.33, -.045, .075, .89, .104, .39, [1.12,1.06,.92], 3);
  for (let i = 0; i < 11; i++) at(-.07 + i * .078, -.045, .179, .008, .007, .38, shade(timber, .88));
  for (const u of [.02, .22, .43, .66]) for (const side of [-.22, .135]) {
    at(u, side, -.05, .046, .263, .046, timber);
  }
  for (const [u, v] of [[.36,-.11],[.47,-.105],[.57,-.11],[.36,-.035],[.47,-.035]]) {
    const [x, z] = point(u, v);
    atlasCrate(build, x, .19, z, yaw);
  }
  const [x, z] = point(-.22, .065);
  atlasBuilding(build, x, Math.max(.05, surface(x, z)), z, .32, .22, .23, [.83, .7, .49], [.37, .25, .16], yaw, true);

  // A continuous quay carries the trading hall, the loading sheds and the public market.
  at(-.12, .02, -.055, .46, .23, 2.17, [.97,.95,.86], 7);
  at(-.12, .02, .176, .46, .018, 2.17, [1.12,1.12,1.05], 4);
  for (const v of [.47,.84]) {
    const [wx,wz] = point(-.20,v);
    atlasBuilding(build, wx, Math.max(.195,surface(wx,wz)), wz, .32,.29,.28,
      [.86,.68,.56],[.42,.42,.39],yaw+Math.PI/2,true);
    for (const u of [.02,.09]) {
      const [cx,cz] = point(u,v+.02);
      atlasCrate(build,cx,.20,cz,yaw,.059);
    }
  }
  for (const v of [-.48,-.73,-.97]) {
    for (const u of [-.24,-.01]) {
      const [sx,sz] = point(u,v);
      const ground = Math.max(.195,surface(sx,sz));
      piece(build,sx,ground,sz,.13,.093,.082,[.83,.78,.65],yaw,3);
      for (let stripe=0;stripe<7;stripe++) {
        const [ax,az] = point(u+(stripe-3)*.021,v);
        gable(build,ax,ground+.107,az,.021,.135,.036,
          stripe%2 ? [.94,.86,.68] : [.64,.28,.19],yaw);
      }
    }
  }
  // The upper street and orchard sit uphill from the loading sheds.
  for (const [u,v] of [[-.60,.88],[-.62,.59],[-.66,.31],[-.93,.74]]) {
    const [hx,hz] = point(u,v);
    const ground = surface(hx,hz);
    if (ground > .025) atlasBuilding(build,hx,ground,hz,.21,.19,.17,
      [.90,.83,.70],[.56,.37,.29],yaw+Math.PI/2);
  }
  const [fx, fz] = point(-.86,-.13);
  const fieldY = Math.max(.14,surface(fx,fz));
  piece(build,fx,fieldY,fz,.55,.032,.52,[1.17,1.10,.93],yaw,5);
  for (const v of [-.40,.14]) {
    for (const u of [-1.12,-.94,-.76,-.59]) {
      const [px,pz] = point(u,v);
      piece(build,px,fieldY+.03,pz,.009,.043,.009,[.45,.33,.21],yaw);
    }
    const [rx,rz] = point(-.85,v);
    piece(build,rx,fieldY+.058,rz,.55,.009,.008,[.58,.45,.32],yaw);
  }
  // A moored two-masted vessel gives the stone quay a visible loading berth.
  const [shipX,shipZ] = point(.30,.70);
  mooredVessel(build, shipX, shipZ, yaw + Math.PI/2);
  // Porters and market shoppers give the architecture a consistent human scale.
  for (let i=0; i<15; i++) {
    const [px,pz] = point(-.05+.05*Math.sin(i*2.1), -.99+i*.14);
    const ground = .197;
    const coat = i%3 ? [.27,.32,.33] : [.55,.36,.23];
    piece(build,px,ground,pz,.012,.028,.013,[.20,.19,.17],yaw);
    piece(build,px,ground+.025,pz,.021,.029,.014,coat,yaw);
    piece(build,px,ground+.054,pz,.014,.016,.013,[.77,.59,.42],yaw);
  }

  const [lx,lz] = point(.66,-.39);
  const stone = [.76,.72,.60], ochre = [.69,.31,.17];
  const tapered = (base, height, lower, upper, color) => {
    const corners = (y,r) => Array.from({length:8},(_,i)=>[
      lx+r*Math.cos(i*Math.PI/4),y,lz+r*Math.sin(i*Math.PI/4)]);
    const bottom=corners(base,lower), top=corners(base+height,upper);
    for (let i=0;i<8;i++) {
      quad(build,bottom[i],bottom[(i+1)%8],top[(i+1)%8],top[i],shade(color,.81+.17*Math.cos(i*.78)));
      triangle(build,top[i],top[(i+1)%8],[lx,base+height,lz],color);
    }
  };
  tapered(-.05,.22,.16,.14,stone);
  tapered(.17,.16,.086,.076,stone);
  tapered(.33,.09,.076,.068,ochre);
  tapered(.42,.12,.068,.059,stone);
  tapered(.54,.025,.089,.089,[.27,.32,.30]);
  tapered(.565,.072,.054,.054,[1.,.80,.40]);
  tapered(.637,.065,.079,.008,[.25,.36,.34]);

  // Gantry with a boom over the berth and the hook above the load position.
  for (const side of [-.105, .07]) at(.43, side, .18, .047, .34, .043, iron);
  at(.43, .026, .48, .068, .05, .31, iron);
  at(.45, .16, .52, .05, .039, .32, [.84, .58, .23]);
  at(.45, .281, .31, .014, .22, .014, [.32, .27, .2]);
  at(.45, .281, .295, .04, .028, .028, [.77, .57, .3]);
}

function atlasShipment(leg) {
  const start = settlementLayout(leg.seller), end = settlementLayout(leg.buyer);
  const first = CONTINENT_ROUTES[start.area], last = CONTINENT_ROUTES[end.area];
  if (start.area === end.area) {
    return [{ type: 'truck', points: [start.gate, first.junction, end.gate], from: 0, to: 1,
      caption: '화물차가 창고로 가는 중' }];
  }
  if (leg.good === 'electronics') return shipmentStages(leg).map((stage) => ({
    ...stage, caption: '비행기가 화물을 운송하는 중',
  }));
  const origin = dockLayout(start.area), destination = dockLayout(end.area);
  return [
    { type: 'truck', points: [start.gate, first.junction, origin.apron], from: 0, to: .22, caption: '출발지 창고에서 항구로 가는 중' },
    { type: 'load', points: [origin.apron, origin.berth], from: .22, to: .36, dock: origin,
      caption: '출발 항구에서 배에 짐을 싣는 중' },
    { type: 'ship', points: seaLane(start.area, end.area, origin.berth, destination.berth),
      from: .36, to: .70, caption: '화물선이 바다를 건너는 중' },
    { type: 'unload', points: [destination.berth, destination.apron], from: .70, to: .84, dock: destination,
      caption: '도착 항구에서 배의 짐을 내리는 중' },
    { type: 'truck', points: [destination.apron, last.junction, end.gate], from: .84, to: 1,
      caption: '도착지 창고로 가는 중' },
  ];
}

class TradeAtlas {
  constructor(viewport) {
    this.viewport = viewport;
    this.canvas = $('.atlas-canvas', viewport);
    this.gl = this.canvas.getContext('webgl2', { alpha: false, antialias: true, preserveDrawingBuffer: true, powerPreference: 'low-power' });
    if (!this.gl) throw new Error('WebGL is unavailable');
    const info = this.gl.getExtension('WEBGL_debug_renderer_info');
    this.software = Boolean(info && /swiftshader|llvmpipe|software/i.test(this.gl.getParameter(info.UNMASKED_RENDERER_WEBGL)));
    const dock = dockLayout(MAP_POSITIONS[S.country][2]);
    const [x, z] = dock.point(-.10, .03);
    this.camera = { x, z, zoom: 8, yaw: 2.32 - dock.yaw };
    this.scenic = true;
    this.visible = true;
    this.motion = matchMedia('(prefers-reduced-motion: reduce)');
    this.pointers = new Map();
    this.routes = [];
    this.labels = [...viewport.querySelectorAll('.country-marker')];
  }

  async init() {
    const [art, relief, ocean, materials, ...vehicles] = await Promise.all([
      atlasImage('art/world-map.webp'), atlasImage('art/world-relief.webp'), atlasImage('art/ocean-mask.webp'),
      atlasImage('art/harbor-materials.webp'), ...Object.values(VEHICLE_ART).map(({ file }) => atlasImage('art/' + file)),
    ]);
    if (this.disposed) return;
    const gl = this.gl;
    this.program = atlasProgram(gl);
    gl.useProgram(this.program);
    this.uniform = Object.fromEntries(['camera', 'time', 'layer', 'zoom', 'vehicleSprite'].map((key) => [key, gl.getUniformLocation(this.program, key)]));
    const terrain = atlasTerrain(imagePixels(art), imagePixels(ocean));
    this.elevation = terrain.elevation;
    this.terrain = this.buffer(terrain.vertices, terrain.indices);
    const water = [];
    quad(water, [-24, -.05, -21], [24, -.05, -21], [24, -.05, 21], [-24, -.05, 21], [0, 0, 0]);
    this.water = this.buffer(water);
    this.props = this.buffer(this.scenery());
    this.bakeSunlight();
    const textures = [[1, materials, 'materials'], [2, art, 'regionalPainting'], [6, relief, 'continentalRelief']];
    this.vehicleRatios = {};
    Object.entries(VEHICLE_ART).forEach(([type, asset], index) => {
      const image = vehicles[index];
      this.vehicleRatios[type] = image.height / image.width;
      textures.push([asset.unit, image, 'vehicleSprite']);
    });
    for (const [unit, texture, sampler] of textures) {
      gl.activeTexture(gl.TEXTURE0 + unit);
      gl.bindTexture(gl.TEXTURE_2D, gl.createTexture());
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, texture);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.generateMipmap(gl.TEXTURE_2D);
      gl.uniform1i(gl.getUniformLocation(this.program, sampler), unit);
    }
    this.spriteBuffer = this.buffer([]);
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

  bakeSunlight() {
    // Buildings and terrain stay in place, so their shadow map only needs one draw.
    const gl = this.gl;
    const sun = atlasProgram(gl, `#version 300 es
      layout(location=0) in vec3 p;
      void main() {
        gl_Position=vec4((p.xz-p.y*vec2(.70,.50))/vec2(10.,7.), -p.y*.4, 1.);
      }`, `#version 300 es
      precision mediump float;
      void main() {}`);
    const depth = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, depth);
    gl.texStorage2D(gl.TEXTURE_2D, 1, gl.DEPTH_COMPONENT24, 2048, 2048);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_COMPARE_MODE, gl.COMPARE_REF_TO_TEXTURE);
    for (const key of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_2D,key,gl.LINEAR);
    for (const key of [gl.TEXTURE_WRAP_S,gl.TEXTURE_WRAP_T]) gl.texParameteri(gl.TEXTURE_2D,key,gl.CLAMP_TO_EDGE);
    const frame = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER,frame);
    gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.DEPTH_ATTACHMENT,gl.TEXTURE_2D,depth,0);
    gl.drawBuffers([gl.NONE]);
    gl.readBuffer(gl.NONE);
    if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE) throw new Error('그림자 준비 실패');
    gl.useProgram(sun);
    gl.viewport(0,0,2048,2048);
    gl.enable(gl.DEPTH_TEST);
    gl.clear(gl.DEPTH_BUFFER_BIT);
    gl.bindVertexArray(this.terrain.vao);
    gl.drawElements(gl.TRIANGLES,this.terrain.count,gl.UNSIGNED_SHORT,0);
    for (const mesh of [this.props, ...this.districts.map((district) => district.mesh)]) {
      gl.bindVertexArray(mesh.vao);
      gl.drawArrays(gl.TRIANGLES, 0, mesh.count);
    }
    gl.bindFramebuffer(gl.FRAMEBUFFER,null);
    gl.deleteFramebuffer(frame);
    gl.deleteProgram(sun);
    gl.useProgram(this.program);
    gl.uniform1i(gl.getUniformLocation(this.program,'shadows'),0);
  }

  buffer(vertices, indices) {
    const gl = this.gl;
    const vao = gl.createVertexArray();
    gl.bindVertexArray(vao);
    const vbo = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(vertices), gl.STATIC_DRAW);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 32, 0);
    gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 32, 12);
    gl.enableVertexAttribArray(0);
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(2, 2, gl.FLOAT, false, 32, 24);
    gl.enableVertexAttribArray(2);
    if (indices) {
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, gl.createBuffer());
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array(indices), gl.STATIC_DRAW);
    }
    return { vao, vbo, indexed: Boolean(indices), count: indices?.length ?? vertices.length / 8 };
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
    const surface = this.surface.bind(this);
    this.mills = [];
    this.districts = [];
    for (const [i, country] of Object.keys(MAP_POSITIONS).entries()) {
      const town = settlementLayout(country);
      const { junction } = CONTINENT_ROUTES[town.area];
      const localRoad = [-.58, .62].map((u) => worldUV(...town.point(u, .05)).map((v) => v * 100));
      this.routeRibbon(output, makeCraft('truck', localRoad), [.54, .43, .27], .057);
      this.routeRibbon(output, makeCraft('truck', [town.gate, junction]), [.49, .42, .29], .035);
      const buildings = [];
      addSettlement(buildings, country, surface, i);
      if (country === 'Grainia' || country === 'Agrea') {
        const [x, z] = town.point(.88, -.88);
        const y = surface(x, z);
        atlasBuilding(buildings, x, y, z, .18, .28, .17, [.87, .76, .56], [.38, .25, .18], town.yaw);
        const [hx, hz] = town.point(.88, -.773);
        this.mills.push({ x: hx, y: y + .24, z: hz, yaw: town.yaw });
      }
      this.districts.push({ center: mapXZ(MAP_POSITIONS[country]), mesh: this.buffer(buildings) });
    }
    for (const region of Object.keys(CONTINENT_ROUTES)) {
      const dock = dockLayout(region);
      this.routeRibbon(output, makeCraft('truck', [CONTINENT_ROUTES[region].junction, dock.apron]), [.53, .43, .29], .04);
      addHarbor(output, region, surface);
    }
    const centers = Object.values(MAP_POSITIONS).map(mapXZ);
    for (let i=0;i<1250;i++) {
      const x = ((i*.61803399)%1-.5)*MAP_WIDTH;
      const z = ((i*.75487767)%1-.5)*MAP_DEPTH;
      const y = surface(x,z);
      if (y<.10 || y>.69 || Math.sin(x*3.1)+Math.cos(z*3.3)<.13) continue;
      if (centers.some(([cx,cz])=>Math.hypot(cx-x,cz-z)<1.37)) continue;
      atlasTree(output,x,y,z,.65+(i%7)*.13,i);
    }
    return output;
  }

  traffic() {
    const { west, east, south } = CONTINENT_ROUTES;
    return [
      makeCraft('truck', [MAP_POSITIONS.Tropia, west.junction, MAP_POSITIONS.Grainia]),
      makeCraft('truck', [MAP_POSITIONS.Mechania, east.junction, MAP_POSITIONS.Novia]),
      makeCraft('truck', [MAP_POSITIONS.Agrea, south.junction, MAP_POSITIONS.Ferria]),
      makeCraft('ship', seaLane('west', 'east')),
      makeCraft('ship', seaLane('east', 'south')),
      makeCraft('plane', [MAP_POSITIONS.Agrea, [41, 69], [28, 68], MAP_POSITIONS.Tropia]),
    ];
  }

  setRoute(country, legs, departed) {
    const key = JSON.stringify([country, legs, departed]);
    if (key === this.routeKey) return;
    this.routeKey = key;
    this.selectedCountry = country;
    if (!legs.length) this.following = false;
    this.preview = country !== S.country ? [MAP_POSITIONS[S.country], MAP_POSITIONS[country]] : null;
    this.routes = legs.map((leg) => ({
      cargo: cargoName(leg), seller: leg.seller, buyer: leg.buyer,
      stages: atlasShipment(leg).map(({ type, points, from, to, caption, dock }) =>
        ({ ...makeCraft(type, points, from, to), caption, dock })),
    }));
    this.departed = departed;
    if (this.ready) {
      const old = this.activeRoads;
      const paths = [];
      if (!this.routes.length && this.preview?.every(Boolean)) {
        this.routeRibbon(paths, makeCraft('truck', this.preview), [.95, .82, .49], .028, true);
      }
      this.routes.forEach(({ stages }, i) => stages.forEach((stage) => {
        if (!stage.dock) this.routeRibbon(paths, stage, i ? [.54, .94, .97] : [1., .81, .36], .039, stage.type === 'plane');
      }));
      this.activeRoads = this.buffer(paths);
      if (old) { this.gl.deleteBuffer(old.vbo); this.gl.deleteVertexArray(old.vao); }
      this.render();
    }
  }

  projection(width, height, zoom = this.camera.zoom) {
    const halfW = Math.max(9.02, 5.65 * width / height) / zoom;
    return { halfW, halfH: halfW * height / width, pitch: this.pitch(width, zoom) };
  }

  lookHeight(x = this.camera.x, z = this.camera.z) {
    return (Math.max(0, this.surface(x, z)) + .22) * within((this.camera.zoom - 2) / 10, 0, 1);
  }

  matrices(width, height) {
    const { x, z, yaw } = this.camera;
    const y = this.lookHeight();
    const { halfW, halfH, pitch } = this.projection(width, height);
    const sy = Math.sin(yaw), cy = Math.cos(yaw), sp = Math.sin(pitch), cp = Math.cos(pitch);
    const right = [cy / halfW, 0, -sy / halfW];
    const up = [-sy * sp / halfH, cp / halfH, -cy * sp / halfH];
    const depth = [-sy * cp / 30, -sp / 30, -cy * cp / 30];
    return new Float32Array([
      right[0], up[0], depth[0], 0, right[1], up[1], depth[1], 0, right[2], up[2], depth[2], 0,
      -x * right[0] - z * right[2], -x * up[0] - y * up[1] - z * up[2],
      -x * depth[0] - y * depth[1] - z * depth[2], 1,
    ]);
  }

  mapOffset(screen, projection, ground, look) {
    const { yaw } = this.camera;
    const { halfW, halfH, pitch } = projection;
    const across = screen.x * halfW;
    const down = ((ground - look) * Math.cos(pitch) - screen.y * halfH) / Math.sin(pitch);
    return [across * Math.cos(yaw) + down * Math.sin(yaw), -across * Math.sin(yaw) + down * Math.cos(yaw)];
  }

  zoomAround(factor, point) {
    const camera = this.camera;
    const next = within(camera.zoom * factor, MIN_ATLAS_ZOOM, MAX_ATLAS_ZOOM);
    if (!point || next === camera.zoom) { camera.zoom = next; return; }
    const rect = this.canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const screen = {
      x: (point.x - rect.left) / rect.width * 2 - 1,
      y: 1 - (point.y - rect.top) / rect.height * 2,
    };
    const oldProjection = this.projection(rect.width, rect.height);
    const oldLook = this.lookHeight();
    let ground = Math.max(0, this.surface(camera.x, camera.z));
    // Refine the ground point under the cursor before changing scale and tilt.
    for (let i = 0; i < 3; i++) {
      const [dx, dz] = this.mapOffset(screen, oldProjection, ground, oldLook);
      ground = Math.max(0, this.surface(camera.x + dx, camera.z + dz));
    }
    const [dx, dz] = this.mapOffset(screen, oldProjection, ground, oldLook);
    const [anchorX, anchorZ] = [camera.x + dx, camera.z + dz];
    camera.zoom = next;
    const newProjection = this.projection(rect.width, rect.height);
    for (let i = 0; i < 3; i++) {
      const [shiftX, shiftZ] = this.mapOffset(screen, newProjection, ground, this.lookHeight());
      camera.x = within(anchorX - shiftX, -9, 9);
      camera.z = within(anchorZ - shiftZ, -6, 6);
    }
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

  vehicle(output, sprites, type, x, y, z, heading) {
    if (this.camera.zoom > 3.5) {
      modelVehicle(output, type, x, y, z, heading);
      return;
    }
    const { yaw } = this.camera;
    const pitch = this.pitch(this.viewport.clientWidth, this.camera.zoom);
    const flip = Math.cos(yaw + heading) < 0;
    // Keep small vehicles readable while their ground positions follow the 3D routes.
    const width = VEHICLE_ART[type].width * within((this.camera.zoom - CONTINENTAL_ZOOM) / 1.1, .15, 1);
    const height = width * this.vehicleRatios[type];
    for (const [u,v] of [[0,1],[1,1],[1,0],[0,1],[1,0],[0,0]]) {
      const right = (u-.5)*width, up = (.92-v)*height;
      const forward = -Math.sin(pitch)*up;
      sprites[type].push(x + Math.cos(yaw)*right + Math.sin(yaw)*forward, y + Math.cos(pitch)*up,
        z - Math.sin(yaw)*right + Math.cos(yaw)*forward, 1,1,1, flip ? 1-u : u,v);
    }
  }

  craft(output, sprites, stage, progress) {
    const [x, z, yaw] = craftLocation(stage, progress);
    if (this.camera.zoom <= CONTINENTAL_ZOOM) {
      // Track the shipment as a cartographic point at its actual position.
      return this.project(x, Math.max(0, this.surface(x, z)) + .06, z);
    }
    if (stage.dock) {
      const { dock } = stage;
      const [bx, bz] = mapXZ(dock.berth);
      const [tx, tz] = mapXZ(dock.apron);
      this.vehicle(output, sprites, 'ship', bx, .012, bz, dock.yaw);
      this.vehicle(output, sprites, 'truck', tx, Math.max(.18, this.surface(tx, tz)), tz, dock.yaw);
      const y = .14 + Math.sin(progress * Math.PI) * .32;
      atlasCrate(output, x, y, z, dock.yaw, .123);
      const [cx, cz] = dock.point(.43, .18);
      const wire = [.31, .26, .17];
      triangle(output, [cx, .53, cz], [x - .008, y + .09, z], [x + .008, y + .09, z], wire);
      return this.project(x, y + .22, z);
    }
    const y = stage.type === 'plane' ? .69 + Math.sin(progress * Math.PI) * .34
      : stage.type === 'ship' ? .012 : Math.max(.012, this.surface(x, z));
    this.vehicle(output, sprites, stage.type, x, y, z, yaw);
    return this.project(x, y + .31, z);
  }

  render(now = performance.now()) {
    if (!this.ready || this.disposed) return;
    const width = this.viewport.clientWidth, height = this.viewport.clientHeight;
    if (!width || !height) return;
    const gl = this.gl;
    const ratio = Math.min(devicePixelRatio, this.software ? 1 : 1.5);
    const w = Math.round(width * ratio), h = Math.round(height * ratio);
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w;
      this.canvas.height = h;
    }
    gl.viewport(0, 0, w, h);
    gl.clearColor(.055, .22, .27, 1);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    const elapsed = this.departed ? (now - this.departed) / ATLAS_TRIP_MS : 2;
    const lead = this.routes[0];
    const activeStage = lead?.stages.find((stage) => elapsed < stage.end);
    this.updateCamera(now, elapsed, activeStage, lead);
    this.matrix = this.matrices(width, height);
    gl.uniformMatrix4fv(this.uniform.camera, false, this.matrix);
    this.viewport.classList.toggle('scenic', this.scenic && this.camera.zoom > 3.6);
    const scenicPressed = String(this.scenic && this.camera.zoom > 3.6);
    if (this.scenicButton.getAttribute('aria-pressed') !== scenicPressed) this.scenicButton.setAttribute('aria-pressed', scenicPressed);
    this.updateRouteStatus(now, activeStage);
    const zoomText = `${Math.round(this.camera.zoom * 10) / 10}×`;
    if (this.zoomDisplay.textContent !== zoomText) this.zoomDisplay.textContent = zoomText;
    const clock = this.motion.matches ? 0 : now / 1000;
    gl.uniform1f(this.uniform.time, clock % 180.0);
    const draw = (buffer, mode) => {
      gl.uniform1i(this.uniform.layer, mode);
      gl.bindVertexArray(buffer.vao);
      if (buffer.indexed) gl.drawElements(gl.TRIANGLES, buffer.count, gl.UNSIGNED_SHORT, 0);
      else gl.drawArrays(gl.TRIANGLES, 0, buffer.count);
    };
    gl.uniform1f(this.uniform.zoom, this.camera.zoom);
    draw(this.water, 0);
    draw(this.terrain, 1);
    const continental = this.camera.zoom <= CONTINENTAL_ZOOM;
    this.viewport.classList.toggle('continental', continental);
    const localDetail = this.camera.zoom >= 5;
    if (localDetail) draw(this.props, 2);
    // Skip the detailed houses of distant nations when the camera is over a single town.
    const { halfW, halfH, pitch } = this.projection(width, height);
    const visibleRadius = Math.hypot(halfW, halfH / Math.sin(pitch)) + 2.5;
    for (const { center: [x, z], mesh } of this.districts) {
      if (localDetail && Math.hypot(x - this.camera.x, z - this.camera.z) <= visibleRadius) draw(mesh, 2);
    }
    if (!continental && this.camera.zoom < 3.6) draw(this.ambientRoads, 2);
    if (this.activeRoads) draw(this.activeRoads, 2);
    const mesh = [], sprites = { ship: [], truck: [], plane: [] };
    if (localDetail) for (const mill of this.mills) millSails(mesh, mill, clock);
    if (!continental && !this.motion.matches) for (const [i, { forward, reverse }] of this.ambient.entries()) {
      if (this.camera.zoom > 12 && forward.type === 'plane') continue; // Keep dock and street close-ups clear.
      const travel = (clock / (22 + i * 2) + i * .27) % 2;
      this.craft(mesh, sprites, travel < 1 ? forward : reverse, travel % 1);
    }
    for (const [i, badge] of this.badges.entries()) {
      const route = this.routes[i];
      let position;
      if (route) for (const stage of route.stages) {
        if (!this.motion.matches && elapsed >= stage.begin && elapsed < stage.end) {
          position = this.craft(mesh, sprites, stage, (elapsed - stage.begin) / (stage.end - stage.begin));
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
    this.dynamic.count = mesh.length / 8;
    draw(this.dynamic, 2);
    for (const [type, vertices] of Object.entries(sprites)) {
      if (!vertices.length) continue;
      gl.uniform1i(this.uniform.vehicleSprite, VEHICLE_ART[type].unit);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.spriteBuffer.vbo);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(vertices), gl.STREAM_DRAW);
      this.spriteBuffer.count = vertices.length / 8;
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
      draw(this.spriteBuffer, 3);
      gl.disable(gl.BLEND);
    }
    const detailCountry = this.following && lead ? (elapsed < .53 ? lead.seller : lead.buyer) : this.selectedCountry;
    const labelKey = JSON.stringify([width, height, this.camera, detailCountry]);
    if (this.labelKey === labelKey) return;
    this.labelKey = labelKey;
    const near = this.camera.zoom > 3.6;
    for (const label of this.labels) {
      const [x, z] = settlementLayout(label.dataset.country).point(0);
      const [left, top] = this.project(x, Math.max(0, this.surface(x, z)) + (near ? 1.02 : .37), z);
      label.style.setProperty('--map-x', `${left}%`);
      label.style.setProperty('--map-y', `${top}%`);
      label.style.visibility = left < 4 || left > 96 || top < 5 || top > 95 ? 'hidden' : '';
    }
    this.inset.hidden = !near;
    const [u, v] = worldUV(this.camera.x, this.camera.z);
    this.inset.style.setProperty('--where-x', (within(u,.02,.98)*100)+'%');
    this.inset.style.setProperty('--where-y', (within(v,.02,.98)*100)+'%');
    this.updateLandmarks(near, detailCountry || S.country);
  }

  updateLandmarks(near, country) {
    const town = settlementLayout(country);
    const dock = dockLayout(town.area);
    const markers = {
      warehouse: [...town.point(-.24, -.17), '창고'],
      production: [...town.point(.35, -.42), TOWN_PRODUCTION[country]],
      harbor: [...dock.point(.38, .1), '공동 항구'],
    };
    for (const label of this.landmarks) {
      const [x, z, name] = markers[label.dataset.site];
      const [left, top] = this.project(x, Math.max(.12, this.surface(x, z)) + .37, z);
      label.hidden = !near || left < 7 || left > 93 || top < 7 || top > 93;
      if (!label.hidden) {
        label.textContent = name;
        label.style.left = `${left}%`;
        label.style.top = `${top}%`;
      }
    }
  }

  pitch(width, zoom) {
    const overhead = width < 500 ? 1.39 : 1.30;
    return overhead + (.67 - overhead) * within((zoom - 1.7) / 3.5, 0, 1);
  }

  updateRouteStatus(now, activeStage) {
    const lead = this.routes[0];
    const elapsed = this.departed ? (now - this.departed) / ATLAS_TRIP_MS : 2;
    const stage = activeStage ?? lead?.stages.find((step) => elapsed < step.end);
    const stageText = $('#shipment-stage', this.viewport.closest('.route-view'));
    const caption = lead ? (this.motion.matches || !stage ? '도착지 창고로 운송 완료' : stage.caption) : '';
    if (stageText && stageText.textContent !== caption) stageText.textContent = caption;
    this.updateFollowControl();
  }

  updateFollowControl() {
    const control = $('[data-act="follow-shipment"]', this.viewport.closest('.route-view'));
    if (!control) return;
    const pressed = String(Boolean(this.following));
    if (control.getAttribute('aria-pressed') !== pressed) control.setAttribute('aria-pressed', pressed);
    const label = this.following ? '따라가기 멈추기' : '화물 따라가기';
    if (control.textContent !== label) control.textContent = label;
  }

  updateCamera(now, elapsed, activeStage, route) {
    if (this.following && route && !this.motion.matches) {
      const stage = activeStage || route.stages.at(-1);
      const progress = activeStage ? within((elapsed - stage.begin) / (stage.end - stage.begin), 0, 1) : 1;
      const [x, z] = craftLocation(stage, progress);
      const zoom = stage.dock ? 19 : stage.type === 'truck' ? 12 : stage.type === 'plane' ? 4.5 : 7;
      const blend = this.lastCameraFrame ? 1 - Math.exp(-Math.max(0, now - this.lastCameraFrame) / 140) : .12;
      this.camera.x += (x - this.camera.x) * blend;
      this.camera.z += (z - this.camera.z) * blend;
      this.camera.zoom += (zoom - this.camera.zoom) * blend;
    } else if (this.cameraMotion) {
      const { started, from, target } = this.cameraMotion;
      const t = within((now - started) / 370, 0, 1);
      const ease = t * t * (3 - 2 * t);
      for (const key of ['x', 'z']) this.camera[key] = from[key] + (target[key] - from[key]) * ease;
      this.camera.zoom = from.zoom * (target.zoom / from.zoom) ** ease;
      if (t === 1) this.cameraMotion = null;
    }
    this.lastCameraFrame = now;
  }

  localView(place) {
    const country = this.selectedCountry || S.country;
    const town = settlementLayout(country);
    const dock = dockLayout(town.area);
    const points = {
      town: town.point(0),
      port: dock.point(.19, .03),
      warehouse: town.point(-.24, -.12),
      berth: dock.point(.43, .16),
    };
    const [x, z] = points[place];
    const target = { x, z, zoom: place === 'warehouse' || place === 'berth' ? ATLAS_DETAIL_ZOOM : NEAR_ZOOM };
    if (this.motion.matches) Object.assign(this.camera, target);
    else this.cameraMotion = { started: performance.now(), from: { ...this.camera }, target };
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
    if (action === 'scenic') {
      this.following = false;
      const overview = this.camera.zoom <= 3.6;
      this.scenic = overview || !this.scenic;
      if (overview) this.localView('port');
      this.render();
      return;
    }
    if (LOCAL_VIEWS.has(action) || action === 'reset') this.scenic = action === 'port';
    this.following = false;
    this.cameraMotion = null;
    if (LOCAL_VIEWS.has(action)) {
      this.localView(action);
      if (this.viewport.getBoundingClientRect().top < $('#status').getBoundingClientRect().bottom) {
        this.viewport.closest('#world').scrollIntoView({ block: 'start' });
      }
    }
    const camera = this.camera;
    if (action === 'reset') Object.assign(camera, { x: 0, z: 0, zoom: 1, yaw: 0 });
    if (action === 'left' || action === 'right') camera.yaw += action === 'right' ? .23 : -.23;
    if (typeof action === 'number') this.zoomAround(action, point);
    this.render();
  }

  pan(dx, dy, zoom = this.camera.zoom) {
    this.following = false;
    this.cameraMotion = null;
    const { yaw } = this.camera;
    const width = this.viewport.clientWidth, height = this.viewport.clientHeight;
    if (!width || !height) return;
    const { halfW, pitch } = this.projection(width, height, zoom);
    const worldPerPixel = 2 * halfW / width;
    const across = -dx * worldPerPixel, down = -dy * worldPerPixel / Math.sin(pitch);
    this.camera.x = within(this.camera.x + across * Math.cos(yaw) + down * Math.sin(yaw), -9, 9);
    this.camera.z = within(this.camera.z - across * Math.sin(yaw) + down * Math.cos(yaw), -6, 6);
  }

  controls() {
    const canvas = this.canvas;
    this.badges = [...this.viewport.querySelectorAll('.atlas-cargo-badge')];
    this.landmarks = [...this.viewport.querySelectorAll('.atlas-landmark')];
    this.inset = $('.atlas-inset',this.viewport);
    this.zoomDisplay = $('.atlas-zoom', this.viewport.parentElement);
    this.scenicButton = $('[data-camera="scenic"]', this.viewport.parentElement);
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
      if (action === 'port') {
        $('.harbor-return', this.viewport.parentElement).click();
        return;
      }
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
