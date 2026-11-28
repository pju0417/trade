// Advisor character "마루 선장" for the student screen.
// - First time a student enters a game: a short tour of the screen (resource bar, goals, turn button).
// - Every phase: concrete advice computed from the student's own state (surplus to sell, shortages to buy,
//   the cheapest seller, which industry to invest in), with a button that opens the right window.
// The advisor only reads the state and suggests; it never sends game actions itself.
//
//   const adv = createAdvisor({ root: element, storageKey, onAction: (action) => {...} });
//   adv.update(state)    // after every state change
import { esc } from './dom.js';
import { goodIcon } from './good-icons.js';

const NAME = '마루 선장';
const GEN_GOODS = ['machine', 'electronics'];

// Original 2D character: a round-faced harbour captain with a navy cap and a compass badge.
function face(mood) {
  const brow = mood === 'warn' ? 'M27 33 l8 -3 M53 30 l8 3' : mood === 'happy' ? 'M27 31 q4 -4 8 -1 M53 30 q4 -3 8 1' : 'M27 32 l8 -1 M53 31 l8 1';
  const mouth = mood === 'warn' ? 'M38 58 q6 -4 12 0' : mood === 'happy' ? 'M35 54 q9 10 18 0' : 'M37 55 q7 6 14 0';
  return `<svg viewBox="0 0 88 88" aria-hidden="true">
    <circle cx="44" cy="46" r="40" fill="#1d4b5c"/>
    <path d="M14 78 q30 -22 60 0 v10 h-60z" fill="#2f5d73"/><path d="M38 70 l6 8 l6 -8" fill="#f3ead2"/>
    <ellipse cx="44" cy="48" rx="22" ry="24" fill="#f1c9a2"/>
    <path d="M22 56 q22 26 44 0 q-4 14 -22 16 q-18 -2 -22 -16z" fill="#d8d2c4"/>
    <circle class="eye" cx="35" cy="42" r="3" fill="#24323a"/><circle class="eye" cx="53" cy="42" r="3" fill="#24323a"/>
    <path d="${brow}" stroke="#6b5a48" stroke-width="2.4" stroke-linecap="round" fill="none"/>
    <path d="${mouth}" stroke="#7a3b2a" stroke-width="2.6" stroke-linecap="round" fill="none"/>
    <circle cx="29" cy="51" r="3.5" fill="#e9a58c" opacity=".55"/><circle cx="59" cy="51" r="3.5" fill="#e9a58c" opacity=".55"/>
    <path d="M18 30 q26 -22 52 0 l3 6 h-58z" fill="#16324a"/><rect x="16" y="32" width="56" height="6" rx="3" fill="#0f2537"/>
    <circle cx="44" cy="24" r="6" fill="#e9c46a"/><path d="M44 19 l1.6 5 l-1.6 5 l-1.6 -5z" fill="#16324a"/>
  </svg>`;
}

// 받침에 맞는 조사: j('바나나', '이', '가') → '바나나가'
function j(word, withB, withoutB) {
  const w = String(word), c = w.charCodeAt(w.length - 1);
  const has = c >= 0xac00 && c <= 0xd7a3 ? (c - 0xac00) % 28 !== 0 : false;
  return w + (has ? withB : withoutB);
}
const icon = (g) => `<span class="g-${g}">${goodIcon(g)}</span>`;
const genTxt = (g, gen) => (GEN_GOODS.includes(g) ? ` ${gen}세대` : '');

function needOf(S, good) { return S.settlement.rows.filter((r) => r.good === good).reduce((a, r) => a + r.need, 0); }
function freeOf(S, good) { return S.stock.filter((r) => r.good === good).reduce((a, r) => a + r.free, 0); }
function listedOf(S, good) { return S.my_orders.filter((o) => o.good === good).reduce((a, o) => a + o.qty, 0); }
function cheapest(S, good) { return S.market.filter((o) => o.good === good && o.seller !== S.country).sort((a, b) => a.price - b.price)[0]; }

// 도움 수준(교사가 고름, state.room.advisor): many = 매 라운드 코치, normal = 1라운드 코치 → 2~3라운드 질문 힌트
// → 4라운드부터 규칙 경고만(전략 힌트는 선장을 눌렀을 때만), alerts = 규칙 경고만, off = 선장 없음.
export const ADVISOR_LEVELS = { many: '많이', normal: '보통(점점 줄어듦)', alerts: '경고만', off: '끔' };
export function stageFor(level, round) {
  if (level === 'many') return 'coach';
  if (level === 'alerts' || level === 'off') return 'quiet';
  return round <= 1 ? 'coach' : round <= 3 ? 'hint' : 'quiet';
}

// 조언 목록: {id, type: 'rule' | 'strategy', mood, text(html), action?: [버튼 글, onAction 값]}
// rule = 모르면 손해 보는 규칙 사실(모자람, 다음 라운드 연료·광물, 받은 제안, 투자 마감) → 늘 알려 준다.
// strategy = 무엇을 얼마에 팔고 언제 투자할지 → 결과를 비슷하게 만들기 쉬워서 단계에 따라 줄인다.
//   coach = 구체적 예시(숫자는 칸에 채우지 않음), hint = 사실 + 질문, quiet = 학생이 선장을 눌렀을 때만 hint.
export function adviceFor(S, stage = 'coach') {
  const tips = [];
  const L = (g) => S.goods[g];
  const coach = stage === 'coach';
  const R = (id, mood, text, action) => tips.push({ id, type: 'rule', mood, text, action });
  const T = (id, mood, text, action) => tips.push({ id, type: 'strategy', mood, text, action });
  if (S.phase === 'finished') {
    const r = Object.values(S.results || {}).find((x) => x.label === S.label);
    if (r) R('end', r.total >= 80 ? 'happy' : '', r.total >= 80 ? `훌륭해요! <b>${r.grade}등급</b>이에요. 무역으로 우리 나라를 잘 키웠어요.` : `<b>${r.grade}등급</b>이에요. 점수표에서 어느 부분이 낮은지 보고 다음에는 그 부분을 노려 봐요.`, ['결과 보기', 'result']);
    return tips;
  }
  if (!S.is_student) return [{ id: 'ai', type: 'rule', mood: '', text: '지금은 선생님이 우리 나라를 AI에게 맡겼어요. 다시 맡게 되면 알려 줄게요.' }];
  const short = S.settlement.rows.filter((r) => r.short > 0);
  const nextR = S.round + 1, sched = S.operating_schedule || { fuel: [], ore: [] };
  const upcoming = [['fuel', sched.fuel], ['ore', sched.ore]].filter(([g, rs]) => rs.includes(nextR) && freeOf(S, g) - needOf(S, g) < 1).map(([g]) => g);
  const makersOf = (good) => Object.entries(S.profiles || {}).filter(([k, pr]) => k !== S.country && S.countries.includes(k) && pr.levels && pr.levels[good] > 0).map(([k]) => k);

  if (S.phase === 'listing') {
    if (short.length) R('pre-short', 'warn', `이번 정산에 ${short.map((r) => `${icon(r.good)} <b>${esc(r.label)} ${r.short}개</b>`).join(', ')}가 모자라요. 다음 <b>거래</b> 단계에서 구해야 해요.`, ['시장 가격 보기', 'market:buy']);
    const surplus = S.stock.filter((r) => r.free > 0).map((r) => ({ ...r, extra: r.free - (r.gen === 1 || !GEN_GOODS.includes(r.good) ? needOf(S, r.good) : 0) })).filter((r) => r.extra > 0).sort((a, b) => (b.good === S.main) - (a.good === S.main) || b.extra - a.extra);
    if (surplus.length) {
      const g = surplus[0], q = S.quotes[g.good][g.gen], rival = cheapest(S, g.good), name = esc(j(g.label + genTxt(g.good, g.gen), '이', '가'));
      T('sell-' + g.good, '', coach
        ? `${icon(g.good)} <b>${name}</b> 이번 정산에 쓰고도 <b>${g.extra}개</b> 남아요. 예를 들어 절반쯤 내놓고 나머지는 남겨 둘 수 있어요. 기준 가격은 <b>${q}G</b>${rival ? `, 지금 가장 싸게 파는 나라는 ${esc(rival.seller_label)} ${rival.price}G` : ''}예요. 다른 나라가 사서 쓰면 <b>수출 점수</b>가 올라가요.`
        : `${icon(g.good)} <b>${name}</b> <b>${g.extra}개</b> 남아요. 몇 개를 팔고 몇 개를 남길까요? 다른 나라보다 싸게 팔면 잘 팔리지만 돈은 덜 벌고, 비싸게 팔면 안 팔릴 수도 있어요.`,
        ['팔기 창 열기', 'market:sell']);
    } else if (coach && S.my_orders.length) T('listed', 'happy', `좋아요! 시장에 물건을 ${S.my_orders.reduce((a, o) => a + o.qty, 0)}개 내놓았어요. 다 했으면 오른쪽 아래 <b>준비 완료</b>를 눌러요.`);
  }
  if (S.phase === 'trading') {
    for (const r of short) {
      const c = cheapest(S, r.good), makers = makersOf(r.good), names = makers.map((k) => S.names[k] || k), what = `${icon(r.good)} <b>${esc(j(r.label, '이', '가'))}</b> <b>${r.short}개</b> 모자라요(${esc(r.purpose)}).`;
      if (!coach) R('short-' + r.good, 'warn', `${what} 정산 전에 구해야 해요. 시장과 직접 거래 중 어디가 나을까요?`, ['시장 열기', 'market:buy']);
      else if (c) R('short-' + r.good, 'warn', `${what} <b>${esc(j(c.seller_label, '이', '가'))}</b> <b>${c.price}G</b>에 팔고 있어요. 정산 전에 구해 두세요.`, ['시장 열기', 'market:buy']);
      else R('short-' + r.good, 'warn', `${what} 시장에는 없어요. ${names.length ? `<b>${esc(names.join('·'))}</b>에서 만들어요. ` : ''}<b>직접 사겠다고 제안</b>해 보세요. 값은 여러분이 정해요(기준 가격 개당 ${S.quotes[r.good][1]}G). 그 나라도 남는 게 없으면 거절해요.`, ['제안서 쓰기', `trade:${makers[0] || ''}:${r.good}:${r.short}:`]);
    }
    const inc = S.offers.filter((o) => o.status === 'pending' && o.to === S.country);
    if (inc.length) R('offer', '', `다른 나라에서 제안이 <b>${inc.length}개</b> 왔어요. 우리에게 이득인지 보고 수락하거나 거절해요.`, ['제안 보기', 'trade']);
    for (const g of upcoming) R('next-' + g, 'warn', `다음 ${nextR}라운드에 나라를 운영하려면 ${icon(g)} <b>${esc(L(g))} 1묶음</b>이 필요해요. 없으면 급히 사느라 돈이 들고 생활 점수도 깎여요.`, ['시장 열기', 'market:buy']);
    if (coach && !short.length && !inc.length) T('ok-trade', 'happy', `이번 정산에 필요한 물건은 다 있어요. 남는 물건이 팔리길 기다리거나, 다 했으면 <b>준비 완료</b>를 눌러요.`);
  }
  if (S.phase === 'invest') {
    const main = S.invest_options.find((o) => o.main), any = S.invest_options.filter((o) => o.ok);
    const lastChance = S.round >= 6 && S.round <= 7 && !S.progress.main_levelled;
    if (lastChance) R('inv-deadline', 'warn', `투자는 <b>7라운드까지</b>예요. 대표 산업을 한 번도 안 키우면 산업 점수 15점을 못 받아요.`, ['투자 창 열기', 'invest']);
    if (!S.progress.main_levelled && main && !lastChance) T('inv-main', main.ok ? '' : 'warn', main.ok
      ? (coach ? `대표 산업 ${icon(main.good)} <b>${esc(j(main.label, '을', '를'))}</b> 한 번 키우면 <b>산업 점수 15점</b>을 다 받아요. 비용은 <b>${main.cost}G</b>예요.`
        : `대표 산업을 한 번이라도 키우면 산업 점수 15점이에요. 언제 키울까요? 일찍 키우면 물건을 더 많이 만들고, 늦게 키우면 그동안 돈을 아낄 수 있어요(투자는 7라운드까지).`)
      : `대표 산업 ${icon(main.good)} <b>${esc(j(main.label, '은', '는'))}</b> 아직 못 키워요: ${esc(main.reasons.join(', '))}.`, ['투자 창 열기', 'invest']);
    else if (coach && S.progress.main_levelled && any.length) T('inv-more', 'happy', `대표 산업은 이미 키웠어요. 돈이 넉넉하면 더 키울 수 있어요. 다음 라운드에 살 물건 값은 남겨 두세요.`, ['투자 창 열기', 'invest']);
    if (S.cash < 60) T('cash-low', 'warn', coach ? `돈이 <b>${S.cash}G</b>밖에 없어요. 다음 라운드에 모자란 물건을 사려면 돈을 조금 남겨 두는 게 좋아요.` : `돈이 <b>${S.cash}G</b> 남았어요. 다음 라운드에 무엇을 사야 하는지 먼저 생각해 봐요.`);
    for (const g of upcoming) R('next-inv-' + g, 'warn', `다음 라운드에 ${icon(g)} <b>${esc(j(L(g), '이', '가'))}</b> 필요해요. 투자하고 남은 돈으로 살 수 있는지 확인해요.`);
  }
  if (coach && !tips.length) T('idle-' + S.phase, '', '지금 할 일은 다 했어요. 오른쪽 아래 <b>준비 완료</b>를 눌러 다음 단계로 가요.');
  return tips;
}

// First-visit tour. target = CSS selector to highlight.
function tour(S) {
  const p = S.progress;
  return [
    { text: `안녕! 나는 <b>${NAME}</b>이야. ${esc(j(S.label, '을', '를'))} 함께 키워 보자. 처음이니까 화면부터 같이 볼까?` },
    { target: '#hud-top', text: '왼쪽 위는 <b>창고</b>야. 돈과 물건 6가지가 몇 개 있는지 보여 줘. 빨간 숫자는 <b>정산 때 모자란</b> 물건이야.' },
    { target: '#hud-menu', text: '왼쪽 메뉴로 <b>시장</b>·<b>거래</b>·<b>투자</b>·<b>목표</b> 창을 열 수 있어. 단계가 바뀌면 필요한 창이 저절로 열려.' },
    { target: '#hud-menu [data-win=goals]', text: `목표는 다른 나라가 우리 물건을 <b>${p.export_target}G</b>어치 써 주는 거야. 그리고 대표 산업을 한 번 키우고, 먹을 것·쓸 것을 모자라지 않게 챙기면 돼.` },
    { target: '#hud-turn', text: '한 라운드는 <b>판매 등록 → 거래 → 투자</b> 순서야. 할 일을 마치면 <b>준비 완료</b>를 눌러.' },
    { target: '#advisor .advisor-face', text: '헷갈리면 언제든 나를 눌러! 지금 무엇을 하면 좋은지 알려 줄게.' },
  ];
}

export function createAdvisor({ root, storageKey, onAction }) {
  const store = {
    get: (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* private mode: keep in memory only */ } },
  };
  let S = null, tips = [], all = [], manual = false, idx = 0, open = false, seen = new Set(), steps = null, step = 0, lastPhase = null, highlighted = null;
  const muted = () => store.get('trade-advisor-muted') === '1';
  root.className = 'advisor';
  root.addEventListener('click', (e) => {
    const b = e.target.closest('[data-adv]'); if (!b) return;
    e.preventDefault(); e.stopPropagation();
    const a = b.dataset.adv;
    if (a === 'face') { if (steps) return draw(); open = !open; if (open && S) { idx = 0; manual = true; computeTips(); } }
    else if (a === 'next') idx = (idx + 1) % tips.length;
    else if (a === 'close') { open = false; tips.forEach((t) => seen.add(t.id)); manual = false; if (S) computeTips(); }
    else if (a === 'go') { open = false; seen.add(tips[idx].id); onAction(b.dataset.do); }
    else if (a === 'tour-next') { step++; if (step >= steps.length) endTour(); }
    else if (a === 'tour-skip') endTour();
    else if (a === 'mute') { store.set('trade-advisor-muted', muted() ? '0' : '1'); open = false; }
    draw();
  });
  function endTour() { steps = null; store.set(storageKey, 'done'); open = true; idx = 0; }
  function highlight(sel) {
    if (highlighted) highlighted.classList.remove('advisor-focus');
    highlighted = sel ? document.querySelector(sel) : null;
    if (highlighted) highlighted.classList.add('advisor-focus');
  }
  function draw() {
    if (!S) return;
    const t = steps ? null : tips[idx];
    const mood = steps ? 'happy' : (open && t ? t.mood : '');
    const unseen = !steps && tips.some((x) => !seen.has(x.id));
    let bubble = '';
    if (steps) {
      const st = steps[step];
      highlight(st.target);
      bubble = `<div class="advisor-bubble" role="dialog" aria-label="${NAME}의 안내"><b class="advisor-name">${NAME}</b><p>${st.text}</p>
        <div class="advisor-actions"><button class="btn" data-adv="tour-next">${step === steps.length - 1 ? '시작하기' : '다음'} (${step + 1}/${steps.length})</button><button class="btn ghost" data-adv="tour-skip">건너뛰기</button></div></div>`;
    } else {
      highlight(null);
      if (open && t) bubble = `<div class="advisor-bubble ${t.mood || ''}" role="status"><b class="advisor-name">${NAME}</b><p>${t.text}</p>
        <div class="advisor-actions">${t.action ? `<button class="btn" data-adv="go" data-do="${t.action[1]}">${t.action[0]}</button>` : ''}
        ${tips.length > 1 ? `<button class="btn ghost" data-adv="next">다른 조언 (${idx + 1}/${tips.length})</button>` : ''}
        <button class="btn ghost" data-adv="close">알겠어요</button></div>
        <button class="advisor-mute" data-adv="mute">${muted() ? '조언 자동으로 보이기' : '자동으로 열지 않기'}</button></div>`;
    }
    root.innerHTML = `<button class="advisor-face ${unseen && !open ? 'has-tip' : ''}" data-adv="face" aria-label="${NAME}: 조언 보기">${face(mood)}${unseen && !open ? '<span class="advisor-dot">!</span>' : ''}</button>${bubble}`;
  }
  let auto = [];
  // 저절로 보여 주는 조언(auto): 코치·힌트 단계는 전부, 조용한 단계는 규칙 경고만.
  // 선장을 누르면(manual) 전략 힌트까지(경고만 수준이면 규칙 경고만, 없으면 '스스로 정해 볼 차례').
  function computeTips() {
    const level = (S.room && S.room.advisor) || 'normal', stage = stageFor(level, S.round);
    all = adviceFor(S, stage === 'quiet' ? 'hint' : stage);
    auto = stage === 'quiet' ? all.filter((t) => t.type === 'rule') : all;
    const asked = level === 'alerts' ? auto : all;
    tips = manual ? (asked.length ? asked : [{ id: 'self', type: 'strategy', mood: 'happy', text: '이번에는 여러분이 스스로 정해 볼 차례예요. 목표 창에서 우리 나라 상황을 살펴봐요.', action: ['목표 보기', 'goals'] }]) : auto;
    if (idx >= tips.length) idx = 0;
  }
  return {
    update(state) {
      S = state;
      const level = (S.room && S.room.advisor) || 'normal';
      root.hidden = level === 'off';
      if (level === 'off') { highlight(null); root.innerHTML = ''; return; }
      computeTips();
      if (steps === null && store.get(storageKey) !== 'done' && S.phase !== 'finished' && S.is_student) { steps = tour(S); step = 0; }
      // a new phase, or a new warning, opens the bubble by itself (unless muted)
      const key = `${S.round}:${S.phase}`;
      const fresh = tips.filter((x) => !seen.has(x.id));
      if (!steps && !muted() && (key !== lastPhase || fresh.some((x) => x.mood === 'warn'))) {
        if (key !== lastPhase || !open) { open = fresh.length > 0; idx = Math.max(0, tips.indexOf(fresh[0])); }
      }
      if (key !== lastPhase) { seen = new Set(); lastPhase = key; manual = false; computeTips(); open = !steps && !muted() && tips.length > 0; idx = 0; }
      draw();
    },
  };
}
