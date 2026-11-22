import { esc, render } from './dom.js';
import { goodIcon } from './good-icons.js';

const NS = 'http://www.w3.org/2000/svg';
const LAYOUT_URL = new URL('../assets/map/layout.json', import.meta.url);
const instances = new WeakMap();
let sequence = 0;
let layoutRequest;
const text = (el, value) => { if (el.textContent !== String(value)) el.textContent = String(value); };
const names = { Tropia: '트로피아', Grainia: '그레니아', Oilia: '오일리아', Mechania: '메카니아', Mineria: '미네리아', Technia: '테크니아', Novia: '노비아', Agrea: '아그레아', Ferria: '페리아' };
const goods = { wheat: '밀', banana: '바나나', fuel: '연료', ore: '광물', machine: '기계', electronics: '전자제품' };
const channels = { market: '시장', direct: '직접 거래', barter: '물물교환' };
function svg(tag, attrs = {}) {
  const node = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  return node;
}
function validPoint(point) { return Array.isArray(point) && point.length === 2 && point.every(Number.isFinite); }
function getLayout() {
  layoutRequest ||= fetch(LAYOUT_URL).then(r => { if (!r.ok) throw new Error('지도 좌표 파일을 읽지 못했어요.'); return r.json(); }).then(layout => {
    if (!Array.isArray(layout.viewBox) || layout.viewBox.length !== 4 || !layout.viewBox.every(Number.isFinite) || layout.viewBox[2] <= 0 || layout.viewBox[3] <= 0) throw new Error('지도 크기를 확인해 주세요.');
    for (const key of Object.keys(names)) {
      const c = layout.countries?.[key];
      if (!c || !['position', 'port', 'label'].every(k => validPoint(c[k]))) throw new Error(`${names[key]}의 지도 좌표를 확인해 주세요.`);
    }
    if (typeof layout.background !== 'string' || !layout.background) throw new Error('지도 배경 파일을 확인해 주세요.');
    return layout;
  });
  return layoutRequest;
}

// Group repeated transactions on the same route without dropping any goods or quantities.
export function tradeRoutes(trades = []) {
  const routes = new Map();
  for (const trade of trades) for (const leg of trade.legs || []) {
    if (!names[leg.seller] || !names[leg.buyer] || leg.seller === leg.buyer || !(leg.qty > 0)) continue;
    const channel = channels[trade.channel] ? trade.channel : 'direct';
    const pair = channel === 'barter' ? [leg.seller, leg.buyer].sort() : [leg.seller, leg.buyer];
    const key = `${channel}:${pair.join(':')}`;
    if (!routes.has(key)) routes.set(key, { key, channel, seller: pair[0], buyer: pair[1], legs: [], qty: 0 });
    const route = routes.get(key); route.legs.push(leg); route.qty += leg.qty;
  }
  return routes;
}
function curve(a, b, channel) {
  const dx = b[0] - a[0], dy = b[1] - a[1], length = Math.hypot(dx, dy) || 1;
  const bend = Math.min(length * .18, 110) + (channel === 'market' ? 20 : channel === 'barter' ? -25 : 0);
  const mid = [(a[0] + b[0]) / 2 - dy / length * bend, (a[1] + b[1]) / 2 + dx / length * bend];
  return { d: `M${a.join(',')} Q${mid.join(',')} ${b.join(',')}`, mid };
}

class WorldMap {
  constructor(element, options = {}) {
    this.element = element; this.options = options; this.id = `atlas-${++sequence}`;
    this.countryNodes = new Map(); this.routeNodes = new Map(); this.selected = null;
    element.classList.add('world-map');
    element.innerHTML = `<header class="atlas-heading"><div><p class="eyebrow">아홉 나라, 이어지는 바닷길</p><h2>세계 무역 지도</h2></div><span class="atlas-round"></span></header>
      <div class="map-surface"><img class="map-background" alt="아홉 나라의 섬과 바다를 그린 세계 지도"><svg class="trade-routes" aria-hidden="true"></svg><div class="map-labels"></div><span class="ocean-name">함께 잇는 바다</span><p class="map-loading" role="status">지도를 불러오는 중…</p></div>
      <div class="map-legend"><span><i class="legend-line market"></i>시장</span><span><i class="legend-line direct"></i>직접 거래</span><span><i class="legend-line barter"></i>물물교환</span><span class="route-total"></span><button class="route-toggle" type="button" aria-pressed="true">무역로 숨기기</button></div>
      <div class="country-inspector" aria-live="polite"></div><details class="route-log"><summary>이번 라운드 무역로 설명</summary><ul></ul></details>`;
    this.surface = element.querySelector('.map-surface'); this.routes = element.querySelector('.trade-routes');
    this.inspector = element.querySelector('.country-inspector');
    element.querySelector('.route-toggle').onclick = e => {
      const show = e.currentTarget.getAttribute('aria-pressed') !== 'true';
      e.currentTarget.setAttribute('aria-pressed', String(show)); e.currentTarget.textContent = show ? '무역로 숨기기' : '무역로 보기';
      this.routes.classList.toggle('routes-hidden', !show);
    };
    getLayout().then(layout => { this.layout = layout; this.build(); if (this.state) this.update(this.state); }).catch(err => { text(element.querySelector('.map-loading'), err.message); });
  }
  build() {
    const l = this.layout, [ox, oy, width, height] = l.viewBox;
    this.routes.setAttribute('viewBox', l.viewBox.join(' ')); this.routes.setAttribute('preserveAspectRatio', 'none');
    const defs = svg('defs');
    for (const channel of Object.keys(channels)) {
      const marker = svg('marker', { id: `${this.id}-${channel}`, viewBox: '0 0 12 12', refX: 10, refY: 6, markerWidth: 5, markerHeight: 5, orient: 'auto-start-reverse' });
      marker.append(svg('path', { d: 'M1 1 11 6 1 11Z', fill: channel === 'market' ? '#e8c57c' : channel === 'direct' ? '#8de4db' : '#ceacfb' })); defs.append(marker);
    }
    this.routes.append(defs);
    const background = this.element.querySelector('.map-background');
    background.src = new URL(l.background, LAYOUT_URL).href;
    background.onerror = () => { const note = this.element.querySelector('.map-loading'); note.hidden = false; text(note, '배경 그림을 불러오지 못했어요. 나라와 무역로는 계속 볼 수 있어요.'); };
    for (const [key, c] of Object.entries(l.countries)) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'map-country'; button.dataset.country = key;
      button.style.left = `${(c.label[0] - ox) / width * 100}%`; button.style.top = `${(c.label[1] - oy) / height * 100}%`;
      button.onclick = () => { this.selected = key; this.update(this.state); };
      this.element.querySelector('.map-labels').append(button); this.countryNodes.set(key, { button, signature: '' });
      const port = svg('circle', { cx: c.port[0], cy: c.port[1], r: 6, class: 'map-port' });
      this.routes.append(port);
      const center = svg('circle', { cx: c.position[0], cy: c.position[1], r: 63, class: 'country-halo', 'data-halo': key }); this.routes.append(center);
    }
    this.element.querySelector('.map-loading').hidden = true;
  }
  update(state) {
    this.state = state; if (!this.layout || !state) return;
    const profiles = state.profiles || {};
    this.selected ||= state.country || Object.keys(profiles)[0] || 'Tropia';
    this.element.classList.toggle('map-paused', Boolean(state.room?.paused));
    text(this.element.querySelector('.atlas-round'), `${state.round || 1}라운드`);
    for (const [key, entry] of this.countryNodes) {
      const p = profiles[key], name = state.names?.[key] || names[key] || key;
      const main = p?.main, level = p?.levels?.[main] ?? 0;
      const ours = key === state.country, selected = key === this.selected;
      const signature = JSON.stringify([name, main, level, p?.student, p?.evaluated, ours]);
      if (entry.signature !== signature) {
        const type = p ? (p.student ? '학생' : p.evaluated === false ? 'AI 전용' : 'AI') : '정보 대기';
        entry.button.innerHTML = `<span class="country-name">${esc(name)}${ours ? '<b>우리 나라</b>' : ''}</span><span class="country-industry">${goodIcon(main)}<span>${esc(state.goods?.[main] || goods[main] || '산업 정보 대기')}${p ? ` <strong>Lv.${esc(level)}</strong>` : ''}</span></span><span class="country-type">${type}</span><span class="country-buildings" aria-hidden="true">${[1,2,3,4].map(i => `<i class="${i <= level ? 'built' : ''}"></i>`).join('')}</span>`;
        entry.button.setAttribute('aria-label', `${name}${ours ? ', 우리 나라' : ''}, ${state.goods?.[main] || goods[main] || '산업 정보 대기'}, 레벨 ${level}, ${type}`);
        entry.button.classList.toggle('our-country', ours); entry.signature = signature;
      }
      if (entry.button.getAttribute('aria-pressed') !== String(selected)) entry.button.setAttribute('aria-pressed', String(selected));
      const halo = this.routes.querySelector(`[data-halo="${key}"]`); const className = `country-halo${ours ? ' ours' : ''}${selected ? ' selected' : ''}`;
      if (halo.getAttribute('class') !== className) halo.setAttribute('class', className);
    }
    this.updateRoutes(state.world_trades || []);
    this.updateInspector();
  }
  updateRoutes(trades) {
    const routes = tradeRoutes(trades); const descriptions = [];
    for (const [key, route] of routes) {
      const from = this.layout.countries[route.seller]?.port, to = this.layout.countries[route.buyer]?.port;
      if (!from || !to) continue;
      const { d, mid } = curve(from, to, route.channel);
      const description = `${channels[route.channel]} · ${names[route.seller]} ${route.channel === 'barter' ? '↔' : '→'} ${names[route.buyer]}: ${route.legs.map(l => `${names[l.seller]}의 ${goods[l.good] || l.label} ${l.qty}개${l.gen > 1 ? `(${l.gen}세대)` : ''}`).join(', ')}`;
      descriptions.push(description);
      let entry = this.routeNodes.get(key);
      if (!entry) {
        const group = svg('g', { class: `route route-${route.channel}`, 'data-route': key });
        const title = svg('title'), path = svg('path', { d, class: 'route-line', 'marker-end': `url(#${this.id}-${route.channel})` });
        if (route.channel === 'barter') path.setAttribute('marker-start', `url(#${this.id}-${route.channel})`);
        const packet = svg('g', { class: 'route-packet' }); packet.append(svg('circle', { r: 17, class: 'packet-back' }));
        const symbol = svg('g', { transform: 'translate(-10,-10) scale(.84)', fill: 'none', stroke: 'currentColor', 'stroke-width': 1.5, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' });
        // The SVG stays in the same DOM position when unrelated game state changes.
        symbol.innerHTML = goodIcon(route.legs[0].good).replace(/^<svg[^>]*>/, '').replace(/<\/svg>$/, ''); packet.append(symbol);
        const motion = svg('animateMotion', { path: d, dur: `${5 + this.routeNodes.size % 4}s`, repeatCount: 'indefinite', rotate: '0' }); packet.append(motion);
        const still = svg('circle', { cx: mid[0], cy: mid[1], r: 5, class: 'route-static-dot' });
        group.append(title, path, packet, still); this.routes.append(group); entry = { group, title, symbol, good: route.legs[0].good, signature: '' }; this.routeNodes.set(key, entry);
      }
      if (entry.good !== route.legs[0].good) {
        entry.symbol.innerHTML = goodIcon(route.legs[0].good).replace(/^<svg[^>]*>/, '').replace(/<\/svg>$/, '');
        entry.good = route.legs[0].good;
      }
      if (entry.signature !== description) { text(entry.title, description); entry.signature = description; }
    }
    for (const [key, entry] of this.routeNodes) if (!routes.has(key)) { entry.group.remove(); this.routeNodes.delete(key); }
    text(this.element.querySelector('.route-total'), `${trades.length}건 · ${routes.size}개 무역로`);
    const list = descriptions.map(d => `<li>${esc(d)}</li>`).join('') || '<li>이번 라운드에는 아직 거래가 없어요.</li>';
    render(this.element.querySelector('.route-log ul'), list, {});
    if (this.state.room?.paused) this.routes.pauseAnimations(); else this.routes.unpauseAnimations();
  }
  updateInspector() {
    const s = this.state, key = this.selected, p = s.profiles?.[key];
    const name = s.names?.[key] || names[key] || key;
    const listings = (s.market || []).filter(o => o.seller === key).sort((a,b) => a.price - b.price);
    const rows = listings.map(o => `<li>${goodIcon(o.good)}<span>${esc(o.label || goods[o.good])}${o.gen > 1 ? ` ${o.gen}세대` : ''} <b>${o.qty}개</b></span><strong>${o.price}G</strong></li>`).join('');
    const canPropose = this.options.onPropose && key !== s.country;
    const html = `<div class="inspector-title"><h3>${esc(name)}</h3><span>${p?.student ? '학생이 운영해요' : 'AI가 운영해요'}${p?.evaluated === false ? ' · AI 전용' : ''}</span></div><p class="inspector-main">대표 산업 ${esc(s.goods?.[p?.main] || goods[p?.main] || '정보 대기')} · 주력 ${esc(s.goods?.[p?.focus] || goods[p?.focus] || '정보 대기')}</p><ul class="country-listings">${rows || '<li>지금 시장에 내놓은 물건이 없어요.</li>'}</ul>${canPropose ? `<button type="button" class="map-propose" ${s.phase === 'trading' ? '' : 'disabled'}>${s.phase === 'trading' ? `${esc(name)}에 직접 거래 제안` : '거래 단계에서 제안할 수 있어요'}</button>` : ''}`;
    render(this.inspector, html, {});
    const button = this.inspector.querySelector('.map-propose'); if (button) button.onclick = () => this.options.onPropose(key);
  }
}
export function updateWorldMap(element, state, options = {}) {
  if (!element) return;
  if (!instances.has(element)) instances.set(element, new WorldMap(element, options));
  instances.get(element).update(state);
}

export async function applyMapBackground(element) {
  try { const layout = await getLayout(); element.style.backgroundImage = `url("${new URL(layout.background, LAYOUT_URL).href}")`; }
  catch { /* The title and game entrance remain usable without a background. */ }
}
