// Fun layer for the student screen. Reads the state only; never sends game actions and never changes scores.
//   - trade feedback: my new sales / purchases → coins fly into the money tile, '출항!' / '입항!' notice, sound
//   - round start card: last round's summary (sold, bought, money, export bar, people's mood) + 바닷길 신문
//   - badges (업적): earned once, stored per room/country in this browser, shown in the goals window and at the end
//   - end ceremony: grade medal, confetti, badges
//   - sound: synthesized with WebAudio (no files), on/off saved on this device
//
//   const fun = createFun({ root, storageKey, toast: (t) => {}, onAction: (a) => {} });
//   fun.update(state);  fun.badgesHtml();  fun.soundOn() / fun.toggleSound()
import { esc } from './dom.js';
import { goodIcon, uiIcon } from './good-icons.js';

const GOOD = ['wheat', 'banana', 'fuel', 'ore', 'machine', 'electronics'];
const store = {
  get: (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } },
};

// ---------------------------------------------------------------- sound (WebAudio, synthesized)
let ac = null;
function tone(freq, t0, dur, type = 'sine', vol = 0.12) {
  if (!ac) return;
  const o = ac.createOscillator(), g = ac.createGain(), t = ac.currentTime + t0;
  o.type = type; o.frequency.setValueAtTime(freq, t);
  g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(vol, t + 0.01); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  o.connect(g).connect(ac.destination); o.start(t); o.stop(t + dur + 0.02);
}
const SFX = {
  coin: () => { tone(988, 0, 0.09, 'square', 0.05); tone(1319, 0.07, 0.18, 'square', 0.05); },
  ship: () => { tone(196, 0, 0.5, 'triangle', 0.1); tone(147, 0.05, 0.6, 'triangle', 0.08); },
  badge: () => { [523, 659, 784, 1047].forEach((f, i) => tone(f, i * 0.08, 0.25, 'triangle', 0.09)); },
  round: () => { tone(392, 0, 0.6, 'sine', 0.12); tone(523, 0.12, 0.7, 'sine', 0.1); },
  fanfare: () => { [523, 523, 659, 784, 1047].forEach((f, i) => tone(f, i * 0.14, i === 4 ? 0.9 : 0.16, 'square', 0.06)); },
};

// ---------------------------------------------------------------- badges
const BADGES = [
  ['first-export', '첫 수출', '다른 나라에 처음으로 물건을 팔았어요', 'ship'],
  ['first-import', '첫 수입', '다른 나라 물건을 처음으로 들여왔어요', 'trade'],
  ['direct', '협상가', '직접 거래를 성사시켰어요', 'mail'],
  ['barter', '물물교환', '돈 없이 물건끼리 바꿨어요', 'trading'],
  ['bigseller', '큰손', '한 라운드에 물건을 10개 넘게 팔았어요', 'market'],
  ['partners5', '세계의 친구', '다섯 나라와 거래했어요', 'nation'],
  ['industry', '공장 확장', '대표 산업을 키웠어요', 'invest'],
  ['export50', '수출 반환점', '수출 목표의 절반을 채웠어요', 'goals'],
  ['export100', '수출 목표 달성', '수출 목표를 다 채웠어요', 'result'],
  ['thrifty', '알뜰 살림', '4라운드까지 연료·광물을 급히 사지 않았어요', 'coin'],
  ['happy', '행복한 나라', '국민 만족도가 90을 넘었어요', 'happy'],
];

function txKey(t) { return JSON.stringify([t.channel, t.legs.map((l) => [l.seller, l.buyer, l.good, l.gen, l.qty]), t.cash]); }

export function createFun({ root, storageKey, toast, onAction }) {
  const earned = new Set(JSON.parse(store.get(storageKey + ':badges') || '[]'));
  const seenTx = new Set(); // round|txKey of my trades already celebrated
  const partners = new Set(JSON.parse(store.get(storageKey + ':partners') || '[]'));
  let S = null, ready = false, roundStart = {}, lastOfRound = {}, shownRound = 0, ceremonyShown = store.get(storageKey + ':ceremony') === '1';
  let sound = store.get('trade-sound') !== '0';
  const play = (k) => { if (!sound) return; try { ac ||= new (window.AudioContext || window.webkitAudioContext)(); if (ac.state === 'suspended') ac.resume(); SFX[k](); } catch (e) { /* no audio */ } };
  // browsers allow audio only after a user gesture: unlock on the first click
  document.addEventListener('pointerdown', () => { if (sound && !ac) try { ac = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { /* no audio */ } }, { once: true });

  root.addEventListener('click', (e) => {
    const b = e.target.closest('[data-fun]'); if (!b) return;
    e.preventDefault(); e.stopPropagation();
    if (b.dataset.fun === 'close') close();
    else if (b.dataset.fun === 'go') { close(); onAction(b.dataset.do); }
  });
  function close() { root.innerHTML = ''; root.hidden = true; }
  function show(html, cls = '') {
    root.hidden = false;
    root.innerHTML = `<div class="fun-backdrop" data-fun="close"></div><div class="fun-card ${cls}" role="dialog">${html}</div>`;
  }

  // ---- trades
  function coins(n) {
    const target = document.querySelector('#hud-top .money'); if (!target) return;
    const t = target.getBoundingClientRect(), x0 = innerWidth * 0.55, y0 = innerHeight * 0.45;
    for (let k = 0; k < Math.min(10, Math.max(3, n)); k++) {
      const c = document.createElement('span'); c.className = 'fun-coin'; c.innerHTML = uiIcon('coin');
      c.style.left = `${x0 + (Math.random() - 0.5) * 120}px`; c.style.top = `${y0 + (Math.random() - 0.5) * 80}px`;
      document.body.appendChild(c);
      setTimeout(() => { c.style.transform = `translate(${t.left + 14 - parseFloat(c.style.left)}px, ${t.top + 10 - parseFloat(c.style.top)}px) scale(.6)`; c.style.opacity = '0.2'; }, 30 + k * 70);
      setTimeout(() => c.remove(), 1100 + k * 70);
    }
    target.classList.remove('fun-pulse'); void target.offsetWidth; target.classList.add('fun-pulse');
  }
  function trades() {
    const me = S.country, out = [];
    for (const t of S.transactions_this_round || []) {
      const key = S.round + '|' + txKey(t); if (seenTx.has(key)) continue; seenTx.add(key);
      for (const l of t.legs) {
        if (l.seller === me && l.buyer !== me) { partners.add(l.buyer); out.push({ kind: 'sell', l, t }); }
        if (l.buyer === me && l.seller !== me) { partners.add(l.seller); out.push({ kind: 'buy', l, t }); }
      }
    }
    store.set(storageKey + ':partners', JSON.stringify([...partners]));
    return out;
  }
  function celebrate(list) {
    const sold = list.filter((x) => x.kind === 'sell'), bought = list.filter((x) => x.kind === 'buy');
    const name = (n) => S.names[n] || n;
    if (sold.length) {
      const items = sold.map((x) => `${S.goods[x.l.good]} ${x.l.qty}개 → ${name(x.l.buyer)}`).join(', ');
      const cash = sold.reduce((a, x) => a + (x.t.cash && x.t.cash.payee === S.country ? x.t.cash.amount : 0), 0);
      toast({ kind: 'ok', icon: 'ship', title: '출항!', text: items + (cash ? ` (+${cash}G)` : ''), ms: 4500 });
      coins(sold.reduce((a, x) => a + x.l.qty, 0)); play('coin'); setTimeout(() => play('ship'), 180);
    }
    if (bought.length) {
      toast({ kind: '', icon: 'trade', title: '입항!', text: bought.map((x) => `${S.goods[x.l.good]} ${x.l.qty}개 ← ${name(x.l.seller)}`).join(', '), ms: 4000 });
      if (!sold.length) play('ship');
    }
  }

  // ---- badges
  function checkBadges() {
    const me = S.country, p = S.progress, mine = (S.transactions_this_round || []);
    const has = (fn) => mine.some(fn);
    const soldThisRound = mine.reduce((a, t) => a + t.legs.filter((l) => l.seller === me && l.buyer !== me).reduce((b, l) => b + l.qty, 0), 0);
    const ok = {
      'first-export': has((t) => t.legs.some((l) => l.seller === me && l.buyer !== me)),
      'first-import': has((t) => t.legs.some((l) => l.buyer === me && l.seller !== me)),
      direct: has((t) => t.channel === 'direct'),
      barter: has((t) => t.channel === 'barter'),
      bigseller: soldThisRound > 10,
      partners5: partners.size >= 5,
      industry: p.main_levelled,
      export50: p.export_target > 0 && p.export_value >= p.export_target / 2,
      export100: p.export_target > 0 && p.export_value >= p.export_target,
      thrifty: S.round >= 4 && (S.happiness || []).length >= 4 && !p.emergency_paid,
      happy: (S.happiness || []).length > 0 && S.happiness[S.happiness.length - 1] >= 90,
    };
    const fresh = BADGES.filter(([id]) => ok[id] && !earned.has(id));
    for (const [id, title, text, ico] of fresh) {
      earned.add(id);
      if (ready) { toast({ kind: 'ok', icon: ico, title: `배지: ${title}`, text, ms: 5000, badge: true }); play('badge'); }
    }
    if (fresh.length) store.set(storageKey + ':badges', JSON.stringify([...earned]));
  }
  function badgesHtml() {
    return `<div class="fun-badges">${BADGES.map(([id, title, text, ico]) => `<div class="fun-badge ${earned.has(id) ? 'got' : ''}" title="${esc(text)}"><span class="fb-ico">${uiIcon(ico)}</span><b>${esc(title)}</b><small>${earned.has(id) ? esc(text) : '아직'}</small></div>`).join('')}</div>`;
  }

  // ---- round start card: summary of round r-1 + newspaper
  function mood(h) { return h == null ? 'neutral' : h >= 85 ? 'happy' : h >= 65 ? 'neutral' : 'sad'; }
  function news(prev, start) {
    const out = [];
    const L = (g) => S.goods[g];
    // prices: biggest change of the reference price since the start of last round
    if (start && start.quotes) {
      const ch = GOOD.map((g) => ({ g, a: start.quotes[g][1], b: S.quotes[g][1] })).filter((x) => x.a && x.b && x.a !== x.b).sort((x, y) => Math.abs(y.b - y.a) / y.a - Math.abs(x.b - x.a) / x.a);
      if (ch[0]) out.push(`${goodIcon(ch[0].g)} <b>${esc(L(ch[0].g))}값 ${ch[0].b > ch[0].a ? '올라' : '내려'}</b> — 기준 가격 ${ch[0].a}G → ${ch[0].b}G`);
    }
    // supply: the good with the most units on the market right now
    const qty = {}; for (const o of S.market) if (o.seller !== S.country) qty[o.good] = (qty[o.good] || 0) + o.qty;
    const glut = Object.entries(qty).sort((a, b) => b[1] - a[1])[0];
    if (glut && glut[1] >= 6) out.push(`${goodIcon(glut[0])} <b>시장에 ${esc(L(glut[0]))} 넘쳐</b> — 지금 ${glut[1]}개가 나와 있어요`);
    // industry: a country that levelled up since the start of last round
    if (start && start.profiles && S.profiles) {
      for (const [k, pr] of Object.entries(S.profiles)) {
        if (k === S.country) continue;
        const before = (start.profiles[k] || {}).levels || {};
        const up = Object.entries(pr.levels || {}).find(([g, lv]) => lv > (before[g] || 0));
        if (up) { out.push(`${goodIcon(up[0])} <b>${esc(S.names[k] || k)}, ${esc(L(up[0]))} 산업 키워</b> — 이제 Lv.${up[1]}`); break; }
      }
    }
    // the biggest exporter of last round
    if (prev && prev.world_trades) {
      const sold = {}; for (const t of prev.world_trades) for (const l of t.legs) if (l.seller !== l.buyer) { sold[l.seller] = sold[l.seller] || {}; sold[l.seller][l.good] = (sold[l.seller][l.good] || 0) + l.qty; }
      const top = Object.entries(sold).map(([k, gs]) => [k, Object.entries(gs).sort((a, b) => b[1] - a[1])[0], Object.values(gs).reduce((a, b) => a + b, 0)]).sort((a, b) => b[2] - a[2])[0];
      if (top) out.push(`${uiIcon('ship')} <b>지난 라운드 바다의 큰손: ${esc(S.names[top[0]] || top[0])}</b> — ${esc(L(top[1][0]))} 등 ${top[2]}개 수출`);
    }
    return out.slice(0, 3);
  }
  function eventHtml() {
    const e = S.event; if (!e) return '';
    const mine = e.country === S.country || (!e.country && (S.levels || {})[e.good] !== undefined);
    return `<section class="fun-event ${e.delta > 0 ? 'good' : 'bad'}"><span class="ev-ico">${goodIcon(e.good)}</span>
      <div><small>세계 사건${mine ? ' · <b>우리 나라</b>' : ''}</small><h3>${esc(e.title)}</h3><p>${esc(e.text)}</p></div></section>`;
  }
  function roundCard() {
    const r = S.round - 1, prev = lastOfRound[r], start = roundStart[r];
    if (!prev || !start) {
      if (S.event) { show(`<header class="fun-head"><span class="fun-emblem">${uiIcon('news')}</span><h2>${S.round}라운드</h2><button class="fun-x" data-fun="close" aria-label="닫기">×</button></header>${eventHtml()}<p class="fun-actions"><button class="btn" data-fun="close">알겠어요</button></p>`, 'round'); play('round'); }
      return;
    }
    const me = S.country, name = (n) => S.names[n] || n;
    const legs = (prev.transactions_this_round || []).flatMap((t) => t.legs);
    const sold = legs.filter((l) => l.seller === me && l.buyer !== me), bought = legs.filter((l) => l.buyer === me && l.seller !== me);
    const p = S.progress, before = start.progress, pct = (v) => (p.export_target > 0 ? Math.min(100, v / p.export_target * 100) : 0);
    const h = (S.happiness || [])[r - 1], m = mood(h), cash = S.cash - start.cash, emer = (p.emergency_paid || 0) - (before.emergency_paid || 0);
    const list = (xs, arrow) => xs.length ? xs.map((l) => `<li>${goodIcon(l.good)} ${esc(S.goods[l.good])} ${l.qty}개 ${arrow} ${esc(name(arrow === '→' ? l.buyer : l.seller))}</li>`).join('') : '<li class="none">없어요</li>';
    const headlines = news(prev, start);
    show(`<header class="fun-head"><span class="fun-emblem">${uiIcon('news')}</span><h2>${S.round}라운드 시작</h2><button class="fun-x" data-fun="close" aria-label="닫기">×</button></header>
      ${eventHtml()}
      <div class="fun-cols">
        <section class="fun-summary"><h3>${r}라운드 결산</h3>
          <div class="fun-mood mood-${m}">${uiIcon(m)}<span>국민 만족도 <b>${h == null ? '-' : Math.round(h)}</b></span></div>
          <div class="fun-stat"><span>돈</span><b class="${cash >= 0 ? 'up' : 'down'}">${cash >= 0 ? '+' : ''}${cash}G</b></div>
          ${emer ? `<div class="fun-stat warn"><span>급히 산 연료·광물</span><b class="down">-${emer}G</b></div>` : ''}
          <div class="fun-export"><span>수출 목표 ${Math.round(p.export_value)} / ${p.export_target}G</span><div class="bar"><i class="was" style="width:${pct(before.export_value)}%"></i><i class="now" style="--to:${pct(p.export_value)}%"></i></div></div>
          <div class="fun-lists"><div><h4>판 것</h4><ul>${list(sold, '→')}</ul></div><div><h4>산 것</h4><ul>${list(bought, '←')}</ul></div></div>
        </section>
        <section class="fun-news"><h3 class="paper">바닷길 신문 <small>${S.round}라운드</small></h3>
          <ul>${headlines.length ? headlines.map((x) => `<li>${x}</li>`).join('') : '<li>조용한 바다였어요. 이번 라운드는 어떤 소식이 생길까요?</li>'}</ul>
        </section>
      </div>
      <p class="fun-actions"><button class="btn" data-fun="close">${S.round}라운드 시작하기</button></p>`, 'round');
    play('round');
  }

  // ---- end ceremony
  function ceremony() {
    const r = Object.values(S.results || {}).find((x) => x.label === S.label); if (!r) return;
    ceremonyShown = true; store.set(storageKey + ':ceremony', '1');
    const medal = { A: 'gold', B: 'silver', C: 'bronze' }[r.grade] || 'anchor';
    const confetti = Array.from({ length: 36 }, (_, k) => `<i style="--x:${Math.round(Math.random() * 100)}%;--d:${(Math.random() * 1.2).toFixed(2)}s;--h:${k * 37 % 360}"></i>`).join('');
    show(`<div class="fun-confetti">${confetti}</div>
      <header class="fun-head"><span class="fun-emblem">${uiIcon('result')}</span><h2>항해를 마쳤어요!</h2><button class="fun-x" data-fun="close" aria-label="닫기">×</button></header>
      <div class="fun-medal medal-${medal}"><span class="medal-grade">${esc(r.grade)}</span></div>
      <p class="fun-score"><b>${r.total.toFixed(1)}</b>점 · ${esc(S.label)}</p>
      <h3>모은 배지 ${earned.size} / ${BADGES.length}</h3>${badgesHtml()}
      <p class="fun-actions"><button class="btn" data-fun="go" data-do="result">점수 자세히 보기</button></p>`, 'ceremony');
    play('fanfare');
  }

  return {
    badgesHtml,
    soundOn: () => sound,
    toggleSound() { sound = !sound; store.set('trade-sound', sound ? '1' : '0'); if (sound) play('coin'); return sound; },
    update(state) {
      S = state;
      if (!roundStart[S.round]) roundStart[S.round] = { cash: S.cash, progress: { ...S.progress }, quotes: S.quotes, profiles: S.profiles };
      lastOfRound[S.round] = { transactions_this_round: S.transactions_this_round, world_trades: S.world_trades };
      const list = trades();
      if (ready && list.length) celebrate(list);
      checkBadges();
      if (!ready) { ready = true; shownRound = S.round; if (S.phase === 'finished' && ceremonyShown) return; }
      if (S.phase === 'finished') { if (!ceremonyShown) ceremony(); return; }
      if (S.round > shownRound) { shownRound = S.round; roundCard(); }
    },
  };
}
